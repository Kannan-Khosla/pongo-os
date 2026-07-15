from tests.test_items_api import client, seed_item  # noqa: F401


class FakeWooClient:
    configured = True

    def __init__(self, records=None):
        self.records = records or []
        self.write_called = False

    def fetch_all_sellable_products_and_variations(self, statuses=None, limit=None):
        records = self.records
        return records[:limit] if limit else records

    def fetch_sellable_product_batch(self, page, per_page, statuses=None):
        return (self.records, False) if page == 1 else ([], False)

    def check_connection(self):
        return None


def simple_product(**overrides):
    product = {
        "id": 101,
        "type": "simple",
        "sku": "WOO-SIMPLE",
        "name": "Woo Simple Item",
        "short_description": "<p>Woo Simple Item</p>",
        "categories": [{"name": "Dog Food"}],
        "attributes": [{"name": "Brand", "options": ["North Paw"]}],
        "regular_price": "19.99",
        "sale_price": "17.99",
        "price": "17.99",
        "permalink": "https://example.invalid/product/woo-simple",
        "status": "publish",
        "manage_stock": True,
        "stock_quantity": 42,
        "stock_status": "instock",
        "weight": "2.5",
        "dimensions": {"length": "10", "width": "5", "height": "3"},
        "meta_data": [{"key": "barcode", "value": "WOO-BAR"}],
        "images": [{"src": "https://example.invalid/image.jpg"}],
    }
    product.update(overrides)
    return {"product": product, "variation": None}


def variation_product(**overrides):
    parent = {
        "id": 202,
        "type": "variable",
        "sku": "PARENT",
        "name": "Woo Variable Item",
        "categories": [{"name": "Treats"}],
        "attributes": [{"name": "Brand", "options": ["South Paw"]}],
        "status": "publish",
        "stock_status": "instock",
        "dimensions": {"length": "9", "width": "4", "height": "2"},
    }
    variation = {
        "id": 303,
        "sku": "WOO-VAR-SMALL",
        "attributes": [{"name": "Size", "option": "Small"}],
        "regular_price": "8.99",
        "sale_price": "",
        "price": "8.99",
        "permalink": "https://example.invalid/product/woo-variable?attribute_size=small",
        "status": "publish",
        "manage_stock": False,
        "stock_quantity": None,
        "stock_status": "instock",
        "weight": "1.2",
        "dimensions": {},
        "meta_data": [],
        "image": {"src": "https://example.invalid/variation.jpg"},
    }
    variation.update(overrides)
    return {"product": parent, "variation": variation}


def test_variation_parent_manage_stock_is_normalized(client, monkeypatch):
    record = variation_product(manage_stock="parent")
    record["product"]["manage_stock"] = True
    patch_woo_client(monkeypatch, [record])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    assert response.json()["created_count"] == 1


def patch_woo_client(monkeypatch, records):
    fake = FakeWooClient(records)
    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: fake)
    return fake


def test_woocommerce_status_returns_unconfigured_without_secrets(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.woocommerce.get_settings",
        lambda: type(
            "UnconfiguredWooSettings",
            (),
            {
                "woocommerce_base_url": "",
                "woocommerce_consumer_key": "",
                "woocommerce_consumer_secret": "",
                "woocommerce_timeout_seconds": 30,
                "woocommerce_page_size": 100,
                "woocommerce_order_sync_page_size": 100,
            },
        )(),
    )

    response = client.get("/api/integrations/woocommerce/status")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert "secret" not in body
    assert "WOOCOMMERCE_CONSUMER_SECRET" not in response.text


def test_woocommerce_preview_simple_product_with_sku_as_create(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product()])

    response = client.post("/api/integrations/woocommerce/products/preview", json={"include_statuses": ["publish"], "limit": 500})

    assert response.status_code == 200
    body = response.json()
    assert body["total_remote_records"] == 1
    assert body["create_count"] == 1
    assert body["preview_rows"][0]["action"] == "create"
    assert body["preview_rows"][0]["sku"] == "WOO-SIMPLE"


def test_woocommerce_preview_variation_with_sku_as_create(client, monkeypatch):
    patch_woo_client(monkeypatch, [variation_product()])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    row = response.json()["preview_rows"][0]
    assert row["remote_type"] == "variation"
    assert row["woo_product_id"] == 202
    assert row["woo_variation_id"] == 303
    assert row["action"] == "create"


def test_woocommerce_preview_skips_blank_sku(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product(sku="")])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    assert response.json()["skipped_count"] == 1
    assert response.json()["preview_rows"][0]["action"] == "skip"


def test_woocommerce_preview_matches_by_woo_ids_sku_and_barcode(client, monkeypatch):
    by_ids = seed_item(client, sku="LOCAL-IDS", wooProductId=101, wooVariationId=None)
    by_sku = seed_item(client, sku="WOO-SKU-MATCH")
    by_barcode = seed_item(client, sku="LOCAL-BAR", Barcode="REMOTE-BAR")
    records = [
        simple_product(id=101, sku="REMOTE-ID-SKU"),
        simple_product(id=102, sku="WOO-SKU-MATCH"),
        simple_product(id=103, sku="REMOTE-BAR-SKU", meta_data=[{"key": "barcode", "value": "REMOTE-BAR"}]),
    ]
    patch_woo_client(monkeypatch, records)

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    rows = response.json()["preview_rows"]
    assert rows[0]["local_item_id"] == by_ids["id"]
    assert rows[1]["local_item_id"] == by_sku["id"]
    assert rows[2]["local_item_id"] == by_barcode["id"]
    assert response.json()["matched_count"] == 3


def test_woocommerce_preview_prefers_unique_sku_before_barcode_fallback(client, monkeypatch):
    sku_item = seed_item(client, sku="REMOTE-SKU", Barcode="LOCAL-1")
    seed_item(client, sku="OTHER", Barcode="REMOTE-BAR")
    patch_woo_client(monkeypatch, [simple_product(sku="REMOTE-SKU", meta_data=[{"key": "barcode", "value": "REMOTE-BAR"}])])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    assert response.json()["conflict_count"] == 0
    assert response.json()["preview_rows"][0]["action"] == "update"
    assert response.json()["preview_rows"][0]["local_item_id"] == sku_item["id"]


def test_woocommerce_preview_does_not_write_to_database_or_stock(client, monkeypatch):
    seed_item(client, sku="KEEP-STOCK", **{"In Stock": 7})
    patch_woo_client(monkeypatch, [simple_product(sku="KEEP-STOCK", stock_quantity=99)])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    assert response.status_code == 200
    item = client.get("/api/items", params={"sku": "KEEP-STOCK"}).json()["items"][0]
    assert item["In Stock"] == 7
    assert item["wooProductId"] is None
    assert client.get("/api/stock-movements").json()["total"] == 0


def test_woocommerce_commit_creates_new_local_item_from_simple_product(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product()])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    item = client.get("/api/items", params={"sku": "WOO-SIMPLE"}).json()["items"][0]
    assert item["wooProductId"] == 101
    assert item["wooVariationId"] is None
    assert item["In Stock"] == 0
    assert item["wooStockQuantitySnapshot"] == 42


def test_woocommerce_commit_creates_new_local_item_from_variation(client, monkeypatch):
    patch_woo_client(monkeypatch, [variation_product()])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    item = client.get("/api/items", params={"sku": "WOO-VAR-SMALL"}).json()["items"][0]
    assert item["wooProductId"] == 202
    assert item["wooVariationId"] == 303
    assert item["Description"] == "Woo Variable Item - Small"


def test_woocommerce_commit_updates_existing_item_and_preserves_manual_fields(client, monkeypatch):
    seed_item(client, sku="WOO-SIMPLE", **{"In Stock": 11, "Allocated": 3, "Warehouse": "Manual Warehouse", "Inventory Location": "Manual Loc", "Unit Cost": 7})
    patch_woo_client(monkeypatch, [simple_product(stock_quantity=88)])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    item = client.get("/api/items", params={"sku": "WOO-SIMPLE"}).json()["items"][0]
    assert item["wooProductId"] == 101
    assert item["Description"] == "API Test Item"
    assert item["Brand"] == "Test Brand"
    assert item["Sales Price"] == 10.99
    assert item["In Stock"] == 11
    assert item["Allocated"] == 3
    assert item["Warehouse"] == "Manual Warehouse"
    assert item["Inventory Location"] == "Manual Loc"
    assert item["Unit Cost"] == 7
    assert item["wooStockQuantitySnapshot"] == 88


def test_batched_catalog_mapping_preserves_local_items_and_reports_duplicates(client, monkeypatch):
    mapped = seed_item(client, sku="MAP-ME", Barcode="KEEP-BAR", **{"In Stock": 6, "Unit Cost": 7})
    barcode_fallback = seed_item(client, sku="LOCAL-BARCODE", Barcode="FALLBACK-BAR")
    duplicate_a = seed_item(client, sku="DUPLICATE-LOCAL", Barcode="DUP-A")
    duplicate_b = seed_item(client, sku="DUPLICATE-LOCAL", Barcode="DUP-B")
    records = [
        simple_product(id=501, sku="MAP-ME", name="Remote Name", stock_quantity=99),
        simple_product(id=502, sku="REMOTE-BARCODE", meta_data=[{"key": "barcode", "value": "FALLBACK-BAR"}]),
        simple_product(id=503, sku="DUPLICATE-LOCAL"),
        simple_product(id=504, sku="NEW-FROM-WOO"),
        simple_product(id=505, sku="REMOTE-DUPLICATE"),
        simple_product(id=506, sku="remote-duplicate"),
    ]
    patch_woo_client(monkeypatch, records)

    preview = client.post("/api/integrations/woocommerce/products/preview", json={"page": 1, "per_page": 50}).json()

    assert preview["has_more"] is False
    assert preview["create_count"] == 1
    assert preview["update_count"] == 2
    assert preview["conflict_count"] == 3
    assert any("Duplicate local SKU" in error for error in preview["errors"])
    assert sum("Duplicate WooCommerce SKU" in error for error in preview["errors"]) == 2

    commit = client.post(
        "/api/integrations/woocommerce/products/commit",
        json={"page": 1, "per_page": 50, "blocked_skus": ["remote-duplicate"]},
    ).json()

    assert commit["created_count"] == 1
    assert commit["updated_count"] == 2
    assert commit["conflict_count"] == 3
    assert commit["unmatched_local_count"] == 2
    assert set(commit["unmatched_local_skus"]) == {"DUPLICATE-LOCAL"}
    mapped_after = client.get("/api/items", params={"sku": "MAP-ME"}).json()["items"][0]
    assert mapped_after["id"] == mapped["id"]
    assert mapped_after["wooProductId"] == 501
    assert mapped_after["Description"] == "API Test Item"
    assert mapped_after["Barcode"] == "KEEP-BAR"
    assert mapped_after["In Stock"] == 6
    assert mapped_after["Unit Cost"] == 7
    barcode_after = client.get("/api/items", params={"sku": "LOCAL-BARCODE"}).json()["items"][0]
    assert barcode_after["id"] == barcode_fallback["id"]
    assert barcode_after["wooProductId"] == 502
    assert client.get("/api/items", params={"sku": "NEW-FROM-WOO"}).json()["items"][0]["wooProductId"] == 504
    assert all(client.get(f"/api/items/{item['id']}").json()["wooProductId"] is None for item in [duplicate_a, duplicate_b])


def test_woocommerce_commit_stores_sync_run_and_errors_for_skips(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product(sku="")])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["sync_run_id"]
    assert body["skipped_count"] == 1
    detail = client.get(f"/api/integrations/woocommerce/sync-runs/{body['sync_run_id']}")
    assert detail.status_code == 200
    assert detail.json()["errors"][0]["error_message"]


def test_woocommerce_commit_never_creates_stock_movement_or_write_calls(client, monkeypatch):
    fake = patch_woo_client(monkeypatch, [simple_product()])

    client.post("/api/integrations/woocommerce/products/commit", json={})

    assert client.get("/api/stock-movements").json()["total"] == 0
    assert fake.write_called is False


def test_woocommerce_sync_runs_list(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product()])
    client.post("/api/integrations/woocommerce/products/commit", json={})

    response = client.get("/api/integrations/woocommerce/sync-runs")

    assert response.status_code == 200
    assert response.json()["total"] == 1
