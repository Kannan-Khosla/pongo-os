from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Lock

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import (
    Allocation,
    AllocationLine,
    Base,
    Fulfillment,
    FulfillmentLine,
    InventoryItem,
    InventoryItemLocation,
    InventoryLocation,
    MovementType,
    Order,
    OrderItem,
    Pick,
    PickLine,
    Receipt,
    ReceiptItem,
    Route,
    RouteStop,
    StockMovement,
    WooCommerceSyncRun,
    WooItemMapping,
)

_engine = None
_engine_lock = Lock()


def get_demo_engine():
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            engine = create_engine(
                "sqlite://",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(engine)
            seed_demo_data(engine)
            _engine = engine
    return _engine


def seed_demo_data(engine) -> None:
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        if db.scalar(select(func.count(InventoryItem.id))):
            return

        receiving = InventoryLocation(client="Demo Pet Supplies", warehouse="Main Warehouse", location_code="RECEIVING", location_name="Receiving", zone="Inbound", is_default=False, active=True)
        aisle_a = InventoryLocation(client="Demo Pet Supplies", warehouse="Main Warehouse", location_code="A-01", location_name="Aisle A / Shelf 1", zone="Food", aisle="A", shelf="1", is_default=True, active=True)
        aisle_b = InventoryLocation(client="Demo Pet Supplies", warehouse="Main Warehouse", location_code="B-02", location_name="Aisle B / Shelf 2", zone="Supplies", aisle="B", shelf="2", is_default=False, active=True)
        db.add_all([receiving, aisle_a, aisle_b])
        db.flush()

        item_specs = [
            ("DEMO-1001", "Demo Adult Dog Food – Chicken", "Dog Food", "Northstar Pets", "24", "2", "54.99", "31.50", aisle_a),
            ("DEMO-1002", "Demo Grain-Free Cat Food", "Cat Food", "Meadow & Co.", "14", "1", "38.99", "21.25", aisle_a),
            ("DEMO-1003", "Demo Dental Chews – Medium", "Treats", "BrightPaws", "6", "2", "18.49", "9.10", aisle_b),
            ("DEMO-1004", "Demo Lavender Cat Litter", "Cat Litter", "CleanHome", "3", "0", "22.99", "13.40", aisle_b),
            ("DEMO-1005", "Demo Rope Tug Toy", "Toys", "Playful Pack", "18", "0", "12.99", "5.25", aisle_b),
            ("DEMO-1006", "Demo Salmon Training Treats", "Treats", "Northstar Pets", "0", "0", "10.99", "4.60", aisle_a),
            ("DEMO-1007", "Demo Stainless Steel Bowl", "Bowls", "Everyday Pet", "11", "0", "16.99", "7.75", aisle_b),
            ("DEMO-1008", "Demo Puppy Pads – 50 Pack", "Training", "CleanHome", "9", "0", "29.99", "16.20", aisle_b),
        ]
        items: list[InventoryItem] = []
        item_locations: list[InventoryItemLocation] = []
        for index, (sku, name, category, brand, stock, allocated, price, cost, location) in enumerate(item_specs, start=1):
            stock_qty = Decimal(stock)
            allocated_qty = Decimal(allocated)
            item = InventoryItem(
                client="Demo Pet Supplies",
                sku=sku,
                barcode=f"900000000{index:03d}",
                description=name,
                category=category,
                brand=brand,
                unit_of_measurement="Each",
                warehouse="Main Warehouse",
                inventory_location=location.location_code,
                default_location=location.location_code,
                in_stock=stock_qty,
                allocated=allocated_qty,
                sellable=stock_qty - allocated_qty,
                under_par=stock_qty <= Decimal("6"),
                par_level=Decimal("6"),
                sales_price=Decimal(price),
                unit_cost=Decimal(cost),
                active=True,
                source="demo",
                woo_product_id=90_000 + index,
                woo_product_type="simple",
                woo_name=name,
                woo_status="publish",
                woo_manage_stock=True,
                woo_stock_status="instock" if stock_qty else "outofstock",
                woo_stock_quantity_snapshot=stock_qty,
                woo_last_synced_at=now - timedelta(minutes=15),
                woo_sync_status="synced",
            )
            db.add(item)
            db.flush()
            row = InventoryItemLocation(
                inventory_item_id=item.id,
                location_id=location.id,
                client="Demo Pet Supplies",
                warehouse="Main Warehouse",
                inventory_location=location.location_code,
                location_code=location.location_code,
                location_name=location.location_name,
                is_default_location=True,
                in_stock=stock_qty,
                allocated=allocated_qty,
                sellable=stock_qty - allocated_qty,
                par_level=Decimal("6"),
                under_par=stock_qty <= Decimal("6"),
                active=True,
            )
            db.add(row)
            db.add(WooItemMapping(item_id=item.id, woo_product_id=item.woo_product_id, woo_sku=sku, woo_name=name, mapping_source="demo", confidence=100, active=True, note="Mock storefront mapping"))
            items.append(item)
            item_locations.append(row)
        db.flush()

        addresses = [
            ("Demo Customer North", "7424 118 Avenue NW", "T5B 4M9"),
            ("Demo Customer West", "8882 170 Street NW", "T5T 4J2"),
            ("Demo Customer Central", "1 Sir Winston Churchill Square", "T5J 2R7"),
            ("Demo Customer South", "7000 143 Street NW", "T6H 4P3"),
            ("Demo Customer East", "10220 104 Avenue NW", "T5J 0H6"),
        ]
        orders: list[Order] = []
        order_lines: list[OrderItem] = []
        for index, (customer, address, postal) in enumerate(addresses, start=1):
            completed = index == 5
            picked = index == 4
            allocated = index in {2, 3, 4}
            status = "completed" if completed else "processing"
            local_status = "completed" if completed else "picked" if picked else "allocated" if allocated else "open"
            order = Order(
                woo_order_id=80_000 + index,
                woo_order_number=f"DEMO-{index:04d}",
                order_number=f"DEMO-{index:04d}",
                woo_status=status,
                status=status,
                local_status=local_status,
                completion_status="completed" if completed else "open",
                allocation_status="allocated" if allocated or completed else "unallocated",
                pick_status="picked" if picked or completed else "ready_to_pick" if allocated else "not_ready",
                customer_name=customer,
                customer_first_name="Demo",
                customer_last_name=customer.removeprefix("Demo Customer "),
                customer_email=f"customer{index}@example.test",
                customer_phone=f"780-555-01{index:02d}",
                shipping_address_1=address,
                shipping_city="Edmonton",
                shipping_state="AB",
                shipping_country="CA",
                shipping_zip=postal,
                shipping_phone=f"780-555-01{index:02d}",
                shipping_summary={"address_1": address, "city": "Edmonton", "state": "AB", "postcode": postal, "country": "CA"},
                currency="CAD",
                subtotal=Decimal("54.99"),
                shipping_total=Decimal("5.00"),
                tax_total=Decimal("3.00"),
                total=Decimal("62.99"),
                payment_method="demo_card",
                payment_method_title="Demo card",
                date_created=now - timedelta(days=6 - index),
                placed_on=now - timedelta(days=6 - index),
                date_completed=now - timedelta(days=1) if completed else None,
                completed_at=now - timedelta(days=1) if completed else None,
                is_historical_snapshot=False,
                historical_source_present=True,
                sync_status="synced",
                last_synced_at=now - timedelta(minutes=10),
                raw_woo_payload={"customer_note": "Mock delivery note: leave at reception."},
            )
            db.add(order)
            db.flush()
            item = items[index - 1]
            quantity = Decimal("2") if allocated else Decimal("1")
            line = OrderItem(
                order_id=order.id,
                woo_order_item_id=81_000 + index,
                woo_product_id=item.woo_product_id,
                inventory_item_id=item.id,
                line_number=1,
                sku=item.sku,
                barcode=item.barcode,
                description=item.description,
                name=item.description,
                quantity_ordered=quantity,
                quantity_allocated=quantity if allocated or completed else Decimal("0"),
                quantity_picked=quantity if picked or completed else Decimal("0"),
                quantity_fulfilled=quantity if completed else Decimal("0"),
                ordered_qty=quantity,
                allocated_qty=quantity if allocated or completed else Decimal("0"),
                picked_qty=quantity if picked or completed else Decimal("0"),
                fulfilled_qty=quantity if completed else Decimal("0"),
                unit_cost=item.unit_cost,
                unit_price=item.sales_price,
                line_subtotal=item.sales_price * quantity,
                line_total=item.sales_price * quantity,
                matched_status="matched",
                allocation_status="allocated" if allocated or completed else "unallocated",
                pick_status="picked" if picked or completed else "not_picked",
                status=local_status,
                brand=item.brand,
            )
            db.add(line)
            db.flush()
            orders.append(order)
            order_lines.append(line)

        receipt = Receipt(receipt_number="DEMO-RCV-0001", receipt_type="direct", status="posted", source="demo", client="Demo Pet Supplies", warehouse="Main Warehouse", reference_number="DEMO-SHIPMENT-01", created_by="demo-system", received_by="Demo Warehouse", received_date=date.today() - timedelta(days=2), received_at=now - timedelta(days=2), committed_at=now - timedelta(days=2), notes="Mock receiving record")
        db.add(receipt)
        db.flush()
        db.add(ReceiptItem(receipt_id=receipt.id, inventory_item_id=items[0].id, inventory_location_id=aisle_a.id, inventory_item_location_id=item_locations[0].id, line_status="posted", sku=items[0].sku, description=items[0].description, quantity=Decimal("12"), quantity_received=Decimal("12"), uom="Each", unit_cost=items[0].unit_cost, unit_cost_total=items[0].unit_cost * 12, sales_price=items[0].sales_price, brand=items[0].brand, client="Demo Pet Supplies", warehouse="Main Warehouse", inventory_location_name="A-01", default_location="A-01", received_date=date.today() - timedelta(days=2), po_or_receipt_number=receipt.receipt_number, name=items[0].description, notes="Mock delivery"))
        db.add(StockMovement(inventory_item_id=items[0].id, inventory_location_id=aisle_a.id, inventory_item_location_id=item_locations[0].id, sku=items[0].sku, barcode=items[0].barcode, movement_type=MovementType.receiving, quantity_change=Decimal("12"), old_stock=Decimal("12"), new_stock=Decimal("24"), warehouse="Main Warehouse", inventory_location_name="A-01", old_location_stock=Decimal("12"), new_location_stock=Decimal("24"), old_item_stock=Decimal("12"), new_item_stock=Decimal("24"), movement_source="demo", reference_number=receipt.receipt_number, unit_cost=items[0].unit_cost, reason="Mock receiving", reference_type="receipt", reference_id=receipt.id, created_by="demo-system", created_at=now - timedelta(days=2)))

        allocation = Allocation(allocation_number="DEMO-ALC-0001", status="posted", allocation_type="single_order", order_id=orders[1].id, woo_order_id=orders[1].woo_order_id, woo_order_number=orders[1].woo_order_number, notes="Mock allocation", created_by="demo-system", posted_at=now - timedelta(hours=8))
        db.add(allocation)
        db.flush()
        db.add(AllocationLine(allocation_id=allocation.id, order_id=orders[1].id, order_line_id=order_lines[1].id, item_id=items[1].id, inventory_item_location_id=item_locations[1].id, sku=items[1].sku, barcode=items[1].barcode, description=items[1].description, warehouse="Main Warehouse", inventory_location="A-01", quantity_ordered=Decimal("2"), quantity_previously_allocated=Decimal("0"), quantity_to_allocate=Decimal("2"), quantity_allocated_after=Decimal("2"), in_stock_before=Decimal("14"), allocated_before=Decimal("0"), sellable_before=Decimal("14"), allocated_after=Decimal("2"), sellable_after=Decimal("12"), shortage_quantity=Decimal("0"), status="allocated", notes="Mock allocation", auto_allocated=False, allocation_source="demo"))

        pick = Pick(pick_number="DEMO-PICK-0001", status="posted", pick_type="single_order", order_id=orders[3].id, woo_order_id=orders[3].woo_order_id, woo_order_number=orders[3].woo_order_number, notes="Mock pick", created_by="demo-system", posted_at=now - timedelta(hours=4))
        db.add(pick)
        db.flush()
        db.add(PickLine(pick_id=pick.id, order_id=orders[3].id, order_line_id=order_lines[3].id, item_id=items[3].id, inventory_item_location_id=item_locations[3].id, sku=items[3].sku, barcode=items[3].barcode, description=items[3].description, warehouse="Main Warehouse", inventory_location="B-02", quantity_ordered=Decimal("2"), quantity_allocated=Decimal("2"), quantity_previously_picked=Decimal("0"), quantity_to_pick=Decimal("2"), quantity_picked_after=Decimal("2"), remaining_to_pick=Decimal("0"), quantity_stock_reduced=Decimal("2"), stock_reduced_at=now - timedelta(hours=4), idempotency_key="demo-pick", status="picked", notes="Mock pick"))

        fulfillment = Fulfillment(fulfillment_number="DEMO-FUL-0001", status="posted", fulfillment_type="single_order", order_id=orders[4].id, woo_order_id=orders[4].woo_order_id, woo_order_number=orders[4].woo_order_number, notes="Mock completed order", created_by="demo-system", posted_at=now - timedelta(days=1))
        db.add(fulfillment)
        db.flush()
        db.add(FulfillmentLine(fulfillment_id=fulfillment.id, order_id=orders[4].id, order_line_id=order_lines[4].id, item_id=items[4].id, inventory_item_location_id=item_locations[4].id, sku=items[4].sku, barcode=items[4].barcode, description=items[4].description, warehouse="Main Warehouse", inventory_location="B-02", quantity_ordered=Decimal("2"), quantity_allocated=Decimal("2"), quantity_picked=Decimal("2"), quantity_previously_fulfilled=Decimal("0"), quantity_to_fulfill=Decimal("2"), unit_cost=items[4].unit_cost, quantity_fulfilled_after=Decimal("2"), remaining_to_fulfill=Decimal("0"), in_stock_before=Decimal("20"), allocated_before=Decimal("2"), sellable_before=Decimal("18"), in_stock_after=Decimal("18"), allocated_after=Decimal("0"), sellable_after=Decimal("18"), status="fulfilled", notes="Mock fulfillment"))

        route = Route(route_number="DEMO-ROUTE-001", status="finalized", route_name="Demo Edmonton Run", route_date=date.today(), driver_name="Demo Driver", vehicle_name="Demo Van", notes="Mock route", start_address="100 Demo Warehouse Road, Edmonton, AB", end_address="100 Demo Warehouse Road, Edmonton, AB", total_stops=2, total_distance=Decimal("18.50"), estimated_duration=55, estimated_duration_minutes=55, map_provider="google_maps", optimization_status="preview", created_by="demo-system", finalized_at=now - timedelta(hours=1))
        db.add(route)
        db.flush()
        for sequence, order in enumerate(orders[:2], start=1):
            db.add(RouteStop(route_id=route.id, stop_sequence=sequence, order_id=order.id, woo_order_id=order.woo_order_id, woo_order_number=order.woo_order_number, stop_number=sequence, customer_name=order.customer_name, customer_email=order.customer_email, customer_phone=order.customer_phone, shipping_summary=order.shipping_summary, delivery_notes="Mock delivery stop", local_status=order.local_status, stop_status="planned", address_1=order.shipping_address_1, city=order.shipping_city, state=order.shipping_state, country=order.shipping_country, zip=order.shipping_zip, phone=order.shipping_phone, geocode_status="not_requested", optimized_sequence=sequence, notes="Mock data"))

        db.add(WooCommerceSyncRun(sync_type="products", status="completed", started_at=now - timedelta(minutes=20), completed_at=now - timedelta(minutes=19), created_by="demo-system", total_remote_records=len(items), created_count=0, updated_count=0, matched_count=len(items), skipped_count=0, conflict_count=0, error_count=0, notes="Mock WooCommerce catalog sync"))
        db.commit()
