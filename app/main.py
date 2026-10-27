from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

app = FastAPI()


class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0)


class Product(ProductIn):
    id: int


products: dict[int, Product] = {}
next_id = 1


@app.get("/health")
def health():
    return {"status": "ok"}


ALLOWED_SORT_FIELDS = {"id", "name", "price_cents", "stock"}


@app.get("/products")
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

    total = len(items)
    start = (page - 1) * limit
    return {
        "items": items[start : start + limit],
        "total": total,
        "page": page,
        "limit": limit,
    }


@app.get("/products/{product_id}")
def get_product(product_id: int):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    return products[product_id]


@app.post("/products", status_code=201)
def create_product(data: ProductIn):
    global next_id
    product = Product(id=next_id, **data.model_dump())
    products[next_id] = product
    next_id += 1
    return product


@app.put("/products/{product_id}")
def replace_product(product_id: int, data: ProductIn):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    products[product_id] = Product(id=product_id, **data.model_dump())
    return products[product_id]


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    if product_id not in products:
        raise HTTPException(status_code=404, detail="Product not found")
    del products[product_id]
    return Response(status_code=204)