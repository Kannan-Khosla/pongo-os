from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation
from app.models.order_metadata import OrderNote
from app.models.orders import Order
from app.models.picks import Pick, PickLine
from app.models.stock_mutations import StockMutationRequest
from app.models.woocommerce import WooStockSyncJob
from app.services.order_actions import completed_pick_idempotency_key
from app.services.woocommerce_stock_sync_jobs import process_next_stock_sync_job
from tests.test_allocations_api import synced_order
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_order_actions_api import action_settings, patch_action_client
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def completed_without_pick(client, monkeypatch, *, item_stock=8, quantity=2):
    item, order, _ = synced_order(
        client,
        monkeypatch,
        item_stock=item_stock,
        item_allocated=0,
        quantity=quantity,
    )
    completed = client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={
            "completion_mode": "complete_without_picking",
            "reason": "Legacy completion",
            "queue_woo_status_update": False,
        },
    )
    assert completed.status_code == 200, completed.text
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        stored.woo_status = "completed"
        stored.status = "completed"
        db.commit()
    return item, order


def test_order_notes_are_append_only_idempotent_and_visible_in_order_serializers(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    payload = {"note": "  Call before delivery  ", "idempotency_key": "note-order-501"}

    created = client.post(
        f"/api/orders/{order['id']}/notes",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    replay = client.post(
        f"/api/orders/{order['id']}/notes",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    conflict = client.post(
        f"/api/orders/{order['id']}/notes",
        json={"note": "Different note", "idempotency_key": payload["idempotency_key"]},
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert created.status_code == replay.status_code == 201
    assert replay.json() == created.json()
    assert conflict.status_code == 409
    assert created.json()["note"] == "Call before delivery"
    assert created.json()["note_type"] == "manual"
    assert created.json()["created_by"] == "pytest@example.com"
    notes = client.get(f"/api/orders/{order['id']}/notes").json()
    assert notes["total"] == 1
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["note_count"] == 1
    assert detail["latest_note"] == created.json()
    assert detail["internal_notes"] == [created.json()]
    listed = client.get("/api/orders/open").json()["orders"][0]
    assert listed["note_count"] == 1
    assert listed["latest_note"]["note"] == "Call before delivery"
    assert client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={"completion_mode": "complete_without_picking", "queue_woo_status_update": False},
    ).status_code == 200
    completed_row = client.get("/api/orders/completed").json()["orders"][0]
    assert completed_row["note_count"] == 1
    assert completed_row["latest_note"]["note"] == "Call before delivery"


def test_reusable_order_tags_preserve_order_and_explicit_no_highlight(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    priority = client.post("/api/orders/tags", json={"name": " Priority ", "color": "#12ab34"})
    delivery = client.post("/api/orders/tags", json={"name": "Delivery", "color": "#AABBCC"})

    assert priority.status_code == delivery.status_code == 201
    assert priority.json()["name"] == "Priority"
    assert priority.json()["color"] == "#12AB34"
    duplicate = client.post("/api/orders/tags", json={"name": "priority", "color": "#FFFFFF"})
    assert duplicate.status_code == 409

    priority_id = priority.json()["id"]
    delivery_id = delivery.json()["id"]
    duplicate_ids = client.put(
        f"/api/orders/{order['id']}/tags",
        json={"tag_ids": [priority_id, priority_id], "highlight_tag_id": priority_id},
    )
    unknown_id = client.put(
        f"/api/orders/{order['id']}/tags",
        json={"tag_ids": [999999], "highlight_tag_id": None},
    )
    assert duplicate_ids.status_code == 422
    assert unknown_id.status_code == 404
    highlighted = client.put(
        f"/api/orders/{order['id']}/tags",
        json={"tag_ids": [priority_id, delivery_id], "highlight_tag_id": delivery_id},
    )
    assert highlighted.status_code == 200, highlighted.text
    assert [tag["id"] for tag in highlighted.json()["tags"]] == [delivery_id, priority_id]
    assert highlighted.json()["highlight_tag_id"] == delivery_id
    assert highlighted.json()["highlight_color"] == "#AABBCC"
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["highlight_tag_id"] == delivery_id
    assert detail["highlight_color"] == "#AABBCC"

    no_highlight = client.put(
        f"/api/orders/{order['id']}/tags",
        json={"tag_ids": [priority_id, delivery_id], "highlight_tag_id": None},
    )
    assert no_highlight.status_code == 200
    assert [tag["id"] for tag in no_highlight.json()["tags"]] == [priority_id, delivery_id]
    assert no_highlight.json()["highlight_tag_id"] is None
    assert no_highlight.json()["highlight_color"] is None
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["highlight_tag_id"] is None
    assert detail["highlight_color"] is None
    assert client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={"completion_mode": "complete_without_picking", "queue_woo_status_update": False},
    ).status_code == 200
    completed_row = client.get("/api/orders/completed").json()["orders"][0]
    assert [tag["id"] for tag in completed_row["tags"]] == [priority_id, delivery_id]
    assert completed_row["highlight_tag_id"] is None


def test_record_completed_order_picked_is_atomic_terminal_and_idempotent(client, monkeypatch):
    _, order = completed_without_pick(client, monkeypatch)
    before = client.get(f"/api/orders/{order['id']}").json()
    fifo_calls = []
    monkeypatch.setattr(
        "app.services.order_workflow.auto_allocate_processing_orders_fifo",
        lambda *_args, **_kwargs: fifo_calls.append(True),
    )
    fake = patch_action_client(monkeypatch, woo_order(status="completed"))
    collection_reads = []

    def get_orders(order_ids):
        collection_reads.append(order_ids)
        return [fake.remote_order]

    fake.get_orders = get_orders
    fake.get_order = lambda _order_id: (_ for _ in ()).throw(AssertionError("bulk validation must use one collection read"))
    payload = {
        "order_ids": [order["id"]],
        "reason": "Counted by hand after legacy completion",
        "idempotency_key": "record-completed-picked-501",
    }

    first = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    replay = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    conflict = client.post(
        "/api/orders/completed/bulk/record-picked",
        json={**payload, "reason": "Different correction reason"},
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    selection_conflict = client.post(
        "/api/orders/completed/bulk/record-picked",
        json={**payload, "order_ids": [order["id"], 999999]},
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert first.status_code == replay.status_code == 200, first.text
    assert conflict.status_code == 409
    assert selection_conflict.status_code == 409
    assert replay.json() == first.json()
    assert first.json()["status"] == "completed"
    assert first.json()["results"][0]["replayed"] is False
    assert first.json()["results"][0]["pick_id"] == replay.json()["results"][0]["pick_id"]
    assert first.json()["results"][0]["woo_stock_sync_status"] == "queued"
    assert first.json()["results"][0]["woo_stock_sync_job_id"] is not None
    assert collection_reads == [[501]]
    assert fake.calls == []
    assert fifo_calls == []

    after = client.get(f"/api/orders/{order['id']}").json()
    assert after["local_status"] == "completed"
    assert after["completion_status"] == "completed"
    assert after["completed_without_picking"] is False
    assert after["completed_at"] == before["completed_at"]
    assert after["closed_at"] == before["closed_at"]
    assert after["lines"][0]["quantity_picked"] == 2
    assert after["lines"][0]["quantity_stock_reduced"] == 2
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 0
    assert client.get(
        "/api/stock-movements",
        params={"movement_type": "pick_stock_reduction"},
    ).json()["total"] == 1

    with Session(client.test_engine) as db:
        assert len(db.scalars(select(Pick).where(Pick.order_id == order["id"])).all()) == 1
        assert len(db.scalars(select(PickLine).where(PickLine.order_id == order["id"])).all()) == 1
        system_notes = list(
            db.scalars(
                select(OrderNote).where(
                    OrderNote.order_id == order["id"],
                    OrderNote.note_type == "system",
                )
            ).all()
        )
        assert len(system_notes) == 1
        assert system_notes[0].created_by == "pytest@example.com"
        assert "Counted by hand" in system_notes[0].note
        assert db.scalar(
            select(InventoryAuditEvent.id).where(
                InventoryAuditEvent.event_type == "pick_stock_reduction"
            ).limit(1)
        ) is not None
        job = db.get(WooStockSyncJob, first.json()["results"][0]["woo_stock_sync_job_id"])
        assert job.status == "queued"
        assert job.target_item_ids == [item["id"]]
        assert db.scalar(
            select(StockMutationRequest.id).where(
                StockMutationRequest.operation == "record_completed_order_picked",
                StockMutationRequest.idempotency_key
                == completed_pick_idempotency_key(payload["idempotency_key"], 999999),
            )
        ) is None

    sessions = sessionmaker(bind=client.test_engine, autoflush=False, autocommit=False)
    process_next_stock_sync_job(action_settings(), db_factory=sessions, client_factory=lambda _settings: fake)
    process_next_stock_sync_job(action_settings(), db_factory=sessions, client_factory=lambda _settings: fake)
    assert [call[0] for call in fake.calls] == ["update_product_stock"]


def test_record_completed_pick_retries_only_failed_durable_stock_job_queue(client, monkeypatch):
    _, order = completed_without_pick(client, monkeypatch)
    fake = patch_action_client(monkeypatch, woo_order(status="completed"))
    collection_reads = []
    fake.get_orders = lambda order_ids: collection_reads.append(order_ids) or [fake.remote_order]
    original_create_job = __import__(
        "app.services.order_actions",
        fromlist=["create_stock_sync_job"],
    ).create_stock_sync_job
    attempts = 0

    def fail_once(db, payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated queue outage")
        return original_create_job(db, payload)

    monkeypatch.setattr("app.services.order_actions.create_stock_sync_job", fail_once)
    payload = {
        "order_ids": [order["id"]],
        "idempotency_key": "record-picked-queue-retry-501",
    }

    pending = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    resolved = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert pending.status_code == resolved.status_code == 200
    assert pending.json()["status"] == "pending_stock_sync"
    assert pending.json()["results"][0]["status"] == "pending_stock_sync"
    assert pending.json()["results"][0]["woo_stock_sync_status"] == "queue_failed"
    assert "Retry this action safely" in pending.json()["results"][0]["woo_stock_sync_error"]
    assert resolved.json()["status"] == "completed"
    assert resolved.json()["results"][0]["status"] == "completed"
    assert resolved.json()["results"][0]["woo_stock_sync_status"] == "queued"
    assert resolved.json()["results"][0]["woo_stock_sync_job_id"] is not None
    assert collection_reads == [[501]]
    assert client.get(
        "/api/stock-movements",
        params={"movement_type": "pick_stock_reduction"},
    ).json()["total"] == 1


def test_record_completed_pick_partial_retry_queues_newly_successful_stock(client, monkeypatch):
    first_item, first_order = completed_without_pick(client, monkeypatch)
    second_item = seed_item(
        client,
        sku="SECOND-ORDER-SKU",
        Barcode="SECOND-ORDER-BAR",
        wooProductId=202,
        **{"In Stock": 1, "Allocated": 0},
    )
    second_remote = woo_order(
        id=502,
        number="1502",
        status="processing",
        line_items=[{
            **woo_order()["line_items"][0],
            "id": 9002,
            "product_id": 202,
            "sku": "SECOND-ORDER-SKU",
            "quantity": 2,
            "meta_data": [{"key": "barcode", "value": "SECOND-ORDER-BAR"}],
        }],
    )
    patch_woo_order_client(monkeypatch, [second_remote])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={})
    assert committed.status_code == 200, committed.text
    second_order = client.get("/api/orders/open").json()["orders"][0]
    completed = client.post(
        f"/api/orders/{second_order['id']}/complete/commit",
        json={
            "completion_mode": "complete_without_picking",
            "reason": "Legacy completion",
            "queue_woo_status_update": False,
        },
    )
    assert completed.status_code == 200, completed.text
    with Session(client.test_engine) as db:
        stored = db.get(Order, second_order["id"])
        stored.woo_status = "completed"
        stored.status = "completed"
        db.commit()

    remotes = {
        501: woo_order(id=501, status="completed"),
        502: {**second_remote, "status": "completed"},
    }
    fake = patch_action_client(monkeypatch, remotes[501])
    fake.get_orders = lambda order_ids: [remotes[order_id] for order_id in order_ids]
    payload = {
        "order_ids": [first_order["id"], second_order["id"]],
        "idempotency_key": "record-picked-partial-retry",
    }

    partial = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    assert partial.status_code == 200
    assert partial.json()["status"] == "partial"
    assert [result["status"] for result in partial.json()["results"]] == ["completed", "rejected"]

    with Session(client.test_engine) as db:
        item = db.get(InventoryItem, second_item["id"])
        location = db.scalar(select(InventoryItemLocation).where(
            InventoryItemLocation.inventory_item_id == second_item["id"],
            InventoryItemLocation.active.is_(True),
        ))
        item.in_stock = Decimal("3")
        item.sellable = Decimal("3")
        location.in_stock = Decimal("3")
        location.sellable = Decimal("3")
        db.commit()

    resolved = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "completed"
    assert [result["woo_stock_sync_status"] for result in resolved.json()["results"]] == ["queued", "queued"]
    with Session(client.test_engine) as db:
        jobs = list(db.scalars(select(WooStockSyncJob).order_by(WooStockSyncJob.id)).all())
        assert len(jobs) == 2
        assert {tuple(job.target_item_ids or []) for job in jobs} == {
            (first_item["id"],),
            (second_item["id"],),
        }


def test_record_completed_pick_fails_fast_when_collection_validation_is_unavailable(client, monkeypatch):
    _, order = completed_without_pick(client, monkeypatch)
    before = client.get(f"/api/orders/{order['id']}").json()
    fake = patch_action_client(monkeypatch, woo_order(status="completed"))
    fake.get_orders = lambda _order_ids: (_ for _ in ()).throw(RuntimeError("Woo timeout"))
    fake.get_order = lambda _order_id: (_ for _ in ()).throw(
        AssertionError("collection failure must not fan out into individual reads")
    )
    payload = {
        "order_ids": [order["id"]],
        "idempotency_key": "record-picked-collection-failure-501",
    }

    response = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "batch validation is unavailable" in response.json()["errors"][0]
    after = client.get(f"/api/orders/{order['id']}").json()
    assert after["completion_status"] == before["completion_status"]
    assert after["lines"][0]["quantity_picked"] == 0
    assert fake.calls == []


def test_record_completed_order_picked_rolls_back_shortage_and_rejects_remote_status_change(client, monkeypatch):
    _, order = completed_without_pick(client, monkeypatch, item_stock=1, quantity=2)
    before = client.get(f"/api/orders/{order['id']}").json()
    fake = patch_action_client(monkeypatch, woo_order(status="completed"))
    fake.get_orders = lambda _order_ids: [fake.remote_order]
    payload = {
        "order_ids": [order["id"]],
        "idempotency_key": "record-shortage-501",
    }

    shortage = client.post(
        "/api/orders/completed/bulk/record-picked",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert shortage.status_code == 200
    assert shortage.json()["status"] == "rejected"
    assert shortage.json()["failed_count"] == 1
    assert fake.calls == []
    after = client.get(f"/api/orders/{order['id']}").json()
    assert after["completion_status"] == "completed_without_picking"
    assert after["local_status"] == "completed"
    assert after["lines"][0]["quantity_allocated"] == 0
    assert after["lines"][0]["quantity_picked"] == 0
    assert after["completed_at"] == before["completed_at"]
    assert client.get(
        "/api/stock-movements",
        params={"movement_type": "pick_stock_reduction"},
    ).json()["total"] == 0

    fake.remote_order["status"] = "cancelled"
    changed = client.post(
        "/api/orders/completed/bulk/record-picked",
        json={**payload, "idempotency_key": "record-remote-changed-501"},
        headers={"Idempotency-Key": "record-remote-changed-501"},
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "rejected"
    assert "live WooCommerce order must still be completed" in changed.json()["errors"][0]
