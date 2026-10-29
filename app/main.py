import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import get_db
from app.models import Product as ProductRow

app = FastAPI()
router = APIRouter(prefix="/v1", tags=["products"])


# ---------- Schemas (what the API accepts and returns) ----------
class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0)


class Product(ProductIn):
    model_config = ConfigDict(from_attributes=True)  # allow reading database rows
    id: int


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    price_cents: int | None = Field(default=None, ge=0)
    stock: int | None = Field(default=None, ge=0)


class ProductPage(BaseModel):
    items: list[Product]
    total: int
    page: int
    limit: int


# ---------- Still in memory (Redis replaces this later) ----------
idempotency_store: dict[str, tuple[dict, Product]] = {}
ALLOWED_SORT_FIELDS = {"id", "name", "price_cents", "stock"}


# ---------- Standard error format ----------
def error_body(code: str, message: str, details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(f"HTTP_{exc.status_code}", str(exc.detail)),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(part) for part in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", "Invalid request", details),
    )


# ---------- Rate limiting ----------
RATE_LIMIT = 20
WINDOW = 10
hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/v1"):
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent = hits[ip]
        while recent and now - recent[0] > WINDOW:
            recent.popleft()
        if len(recent) >= RATE_LIMIT:
            retry_after = int(WINDOW - (now - recent[0])) + 1
            return JSONResponse(
                status_code=429,
                content=error_body("RATE_LIMITED", "Too many requests"),
                headers={"Retry-After": str(retry_after)},
            )
        recent.append(now)
    return await call_next(request)


# ---------- Helpers ----------
def get_active_or_404(db: Session, product_id: int) -> ProductRow:
    row = db.get(ProductRow, product_id)
    if row is None or not row.is_active:
        raise AppError(404, "PRODUCT_NOT_FOUND", "Product not found")
    return row


def commit_or_409(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "PRODUCT_NAME_EXISTS", "Product name already exists")


# ---------- Routes ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@router.get("/products", response_model=ProductPage)
def list_products(
    q: str | None = None,
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    sort: str = "id",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    if field not in ALLOWED_SORT_FIELDS:
        raise AppError(400, "INVALID_SORT_FIELD", "Invalid sort field")

    stmt = select(ProductRow).where(ProductRow.is_active.is_(True))
    if q:
        stmt = stmt.where(ProductRow.name.ilike(f"%{q}%"))
    if min_price is not None:
        stmt = stmt.where(ProductRow.price_cents >= min_price)
    if max_price is not None:
        stmt = stmt.where(ProductRow.price_cents <= max_price)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))

    column = getattr(ProductRow, field)
    order = column.desc() if descending else column.asc()
    items = db.scalars(
        stmt.order_by(order, ProductRow.id).offset((page - 1) * limit).limit(limit)
    ).all()

    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/products/{product_id}", response_model=Product)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return get_active_or_404(db, product_id)


@router.post("/products", status_code=201, response_model=Product)
def create_product(
    data: ProductIn,
    response: Response,
    idempotency_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    payload = data.model_dump()
    if idempotency_key and idempotency_key in idempotency_store:
        saved_payload, saved_product = idempotency_store[idempotency_key]
        if saved_payload != payload:
            raise AppError(
                422,
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key was already used with a different body",
            )
        response.status_code = 200
        return saved_product

    row = ProductRow(**payload)
    db.add(row)
    commit_or_409(db)
    db.refresh(row)

    product = Product.model_validate(row)
    if idempotency_key:
        idempotency_store[idempotency_key] = (payload, product)
    return product


@router.put("/products/{product_id}", response_model=Product)
def replace_product(product_id: int, data: ProductIn, db: Session = Depends(get_db)):
    row = get_active_or_404(db, product_id)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    row.updated_at = func.now()
    commit_or_409(db)
    db.refresh(row)
    return row


@router.patch("/products/{product_id}", response_model=Product)
def update_product(product_id: int, data: ProductPatch, db: Session = Depends(get_db)):
    row = get_active_or_404(db, product_id)
    changes = data.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise AppError(422, "VALIDATION_ERROR", "Fields cannot be set to null")
    for key, value in changes.items():
        setattr(row, key, value)
    row.updated_at = func.now()
    commit_or_409(db)
    db.refresh(row)
    return row


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    row = get_active_or_404(db, product_id)
    row.is_active = False  # soft delete: the row stays, so old orders can still point to it
    db.commit()
    return Response(status_code=204)


app.include_router(router)  # must stay LAST