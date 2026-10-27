import time
from collections import defaultdict, deque
from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()
router = APIRouter(prefix="/v1", tags=["products"])


# ---------- Schemas ----------
class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0)


class Product(ProductIn):
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


# ---------- In-memory data ----------
products: dict[int, Product] = {}
next_id = 1
idempotency_store: dict[str, tuple[dict, Product]] = {}
ALLOWED_SORT_FIELDS = {"id", "name", "price_cents", "stock"}


# ---------- Standard error format ----------
def error_body(code: str, message: str, details: list | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or []}}


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
):
    items = list(products.values())

    if q:
        items = [p for p in items if q.lower() in p.name.lower()]
    if min_price is not None:
        items = [p for p in items if p.price_cents >= min_price]
    if max_price is not None:
        items = [p for p in items if p.price_cents <= max_price]

    descending = sort.startswith("-")
    field = sort.removeprefix("-")
    if field not in ALLOWED_SORT_FIELDS:
        raise HTTPException(status_code=400, detail="Invalid sort field")
    items.sort(key=lambda p: getattr(p, field), reverse=descending)

    start = (page - 1) * limit
    return {
        "items": items[start : start + limit],
        "total": len(items),
        "page": page,
        "limit": limit,
    }


@router.get("/products/{product_id}", response_model=Product)
def get_product(product_id: int):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    return products[product_id]


@router.post("/products", status_code=201, response_model=Product)
def create_product(
    data: ProductIn,
    response: Response,
    idempotency_key: str | None = Header(default=None),
):
    global next_id

    payload = data.model_dump()
    if idempotency_key:
        if idempotency_key in idempotency_store:
            saved_payload, saved_product = idempotency_store[idempotency_key]
            if saved_payload != payload:
                raise HTTPException(
                    status_code=422,
                    detail="Idempotency-Key was already used with a different body",
                )
            response.status_code = 200
            return saved_product

    if any(p.name.lower() == data.name.lower() for p in products.values()):
        raise HTTPException(status_code=409, detail="Product name already exists")

    product = Product(id=next_id, **payload)
    products[next_id] = product
    next_id += 1
    if idempotency_key:
        idempotency_store[idempotency_key] = (payload, product)
    return product


@router.put("/products/{product_id}", response_model=Product)
def replace_product(product_id: int, data: ProductIn):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    products[product_id] = Product(id=product_id, **data.model_dump())
    return products[product_id]


@router.patch("/products/{product_id}", response_model=Product)
def update_product(product_id: int, data: ProductPatch):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    changes = data.model_dump(exclude_unset=True)
    updated = products[product_id].model_copy(update=changes)
    products[product_id] = updated
    return updated


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    del products[product_id]
    return Response(status_code=204)


app.include_router(router)  # must stay LAST: it copies the routes that exist at this moment