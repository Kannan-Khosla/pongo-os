from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.session import init_db, make_engine
from app.models.inventory import InventoryItem


def test_database_connection_can_initialize():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)

    table_names = set(inspect(engine).get_table_names())

    assert "inventory_items" in table_names
    assert "inventory_locations" in table_names
    assert "stock_movements" in table_names
    assert "routes" in table_names


def test_model_creation_for_inventory_item():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)

    with Session(engine) as session:
        item = InventoryItem(
            client="Pongo",
            sku="TEST-SKU",
            barcode="TEST-BARCODE",
            description="Test inventory item",
            unit_of_measurement="Each",
            warehouse="Main Warehouse",
            in_stock=10,
            allocated=2,
            sellable=8,
            active=True,
            source="manual",
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        assert item.id is not None
        assert item.sku == "TEST-SKU"
        assert item.barcode == "TEST-BARCODE"
