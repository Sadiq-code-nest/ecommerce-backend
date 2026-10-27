from fastapi import FastAPI, HTTPException, Response
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


@app.get("/products")
def list_products():
    return list(products.values())


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