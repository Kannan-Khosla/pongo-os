from math import ceil

from fastapi import FastAPI, Request, Response

app = FastAPI()
writes: list[dict] = []

CATALOG_PRODUCTS = [
    {
        "id": 910_000_001,
        "type": "simple",
        "name": "E2E Catalog Simple Product",
        "sku": "E2E-CATALOG-SIMPLE",
        "global_unique_id": "0009100001",
        "status": "publish",
        "purchasable": True,
        "description": "A simple product supplied by the isolated Woo contract.",
        "short_description": "Catalog contract simple product",
        "categories": [{"id": 91, "name": "Contract Products"}],
        "attributes": [{"name": "Brand", "options": ["Pongo Contract"]}],
        "regular_price": "19.99",
        "sale_price": "17.99",
        "price": "17.99",
        "permalink": "http://127.0.0.1:9000/product/e2e-catalog-simple",
        "manage_stock": True,
        "stock_quantity": 17,
        "stock_status": "instock",
        "weight": "1.25",
        "dimensions": {"length": "10", "width": "6", "height": "4"},
        "images": [],
    },
    {
        "id": 910_000_010,
        "type": "variable",
        "name": "E2E Catalog Variable Product",
        "sku": "E2E-CATALOG-PARENT",
        "global_unique_id": "0009100010",
        "status": "publish",
        "purchasable": True,
        "description": "A variable parent that must remain catalog context only.",
        "short_description": "Catalog contract variable parent",
        "categories": [{"id": 91, "name": "Contract Products"}],
        "attributes": [
            {"name": "Brand", "options": ["Pongo Contract"]},
            {"name": "Size", "variation": True, "options": ["Small"]},
        ],
        "regular_price": "24.99",
        "sale_price": "",
        "price": "24.99",
        "permalink": "http://127.0.0.1:9000/product/e2e-catalog-variable",
        "manage_stock": False,
        "stock_quantity": None,
        "stock_status": "instock",
        "weight": "",
        "dimensions": {"length": "", "width": "", "height": ""},
        "images": [],
        "variations": [910_000_011, 910_000_012],
    },
]

CATALOG_VARIATIONS = {
    910_000_010: [
        {
            "id": 910_000_011,
            "parent_id": 910_000_010,
            "name": "E2E Catalog Variable Product - Small",
            "sku": "E2E-CATALOG-VAR-SMALL",
            "global_unique_id": "0009100011",
            "status": "publish",
            "purchasable": True,
            "attributes": [{"name": "Size", "option": "Small"}],
            "regular_price": "24.99",
            "sale_price": "",
            "price": "24.99",
            "permalink": "http://127.0.0.1:9000/product/e2e-catalog-variable?size=small",
            "manage_stock": True,
            "stock_quantity": 4,
            "stock_status": "instock",
            "weight": "0.75",
            "dimensions": {"length": "8", "width": "5", "height": "3"},
            "image": None,
        },
        {
            "id": 910_000_012,
            "parent_id": 910_000_010,
            "name": "E2E Catalog Variable Product - Large",
            "sku": "E2E-CATALOG-VAR-LARGE",
            "global_unique_id": "0009100012",
            "status": "publish",
            "purchasable": True,
            "attributes": [{"name": "Size", "option": "Large"}],
            "regular_price": "29.99",
            "sale_price": "",
            "price": "29.99",
            "permalink": "http://127.0.0.1:9000/product/e2e-catalog-variable?size=large",
            "manage_stock": True,
            "stock_quantity": 7,
            "stock_status": "instock",
            "weight": "1.25",
            "dimensions": {"length": "12", "width": "7", "height": "5"},
            "image": None,
        },
    ],
}


def paginated(rows: list[dict], page: int, per_page: int, response: Response) -> list[dict]:
    safe_page = max(page, 1)
    safe_page_size = min(max(per_page, 1), 100)
    total_pages = ceil(len(rows) / safe_page_size) if rows else 0
    response.headers["X-WP-Total"] = str(len(rows))
    response.headers["X-WP-TotalPages"] = str(total_pages)
    start = (safe_page - 1) * safe_page_size
    return rows[start : start + safe_page_size]


@app.post("/reset")
def reset() -> dict:
    writes.clear()
    return {"status": "reset"}


@app.get("/writes")
def list_writes() -> dict:
    return {"writes": writes}


@app.get("/wp-json/wc/v3/products")
def list_products(
    response: Response,
    page: int = 1,
    per_page: int = 100,
    status: str = "any",
    orderby: str = "id",
    order: str = "asc",
) -> list[dict]:
    del status, orderby, order
    return paginated(CATALOG_PRODUCTS, page, per_page, response)


@app.get("/wp-json/wc/v3/products/{product_id}/variations")
def list_variations(
    product_id: int,
    response: Response,
    page: int = 1,
    per_page: int = 100,
    orderby: str = "id",
    order: str = "asc",
) -> list[dict]:
    del orderby, order
    return paginated(CATALOG_VARIATIONS.get(product_id, []), page, per_page, response)


@app.get("/wp-json/wc/v3/subscriptions")
def list_subscriptions(response: Response) -> list[dict]:
    response.headers["X-WP-Total"] = "0"
    response.headers["X-WP-TotalPages"] = "0"
    return []


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
