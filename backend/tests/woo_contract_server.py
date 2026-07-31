from fastapi import FastAPI, Request

app = FastAPI()
writes: list[dict] = []


@app.post("/reset")
def reset() -> dict:
    writes.clear()
    return {"status": "reset"}


@app.get("/writes")
def list_writes() -> dict:
    return {"writes": writes}


@app.api_route("/wp-json/wc/v3/products/{product_id}", methods=["PUT", "PATCH"])
async def update_product(product_id: int, request: Request) -> dict:
    payload = await request.json()
    writes.append({"entity": "product", "id": product_id, "payload": payload})
    return {"id": product_id, **payload}


@app.api_route("/wp-json/wc/v3/products/{product_id}/variations/{variation_id}", methods=["PUT", "PATCH"])
async def update_variation(product_id: int, variation_id: int, request: Request) -> dict:
    payload = await request.json()
    writes.append({"entity": "variation", "id": variation_id, "product_id": product_id, "payload": payload})
    return {"id": variation_id, "parent_id": product_id, **payload}


@app.api_route("/wp-json/wc/v3/orders/{order_id}", methods=["PUT", "PATCH"])
async def update_order(order_id: int, request: Request) -> dict:
    payload = await request.json()
    writes.append({"entity": "order", "id": order_id, "payload": payload})
    return {"id": order_id, **payload}
