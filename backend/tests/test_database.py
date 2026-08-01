from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.session import init_db, make_engine
from app.models.inventory import InventoryItem


def test_heroku_postgres_url_uses_psycopg_driver():
    engine = make_engine("postgres://user:password@localhost/pongo")

    assert engine.url.drivername == "postgresql+psycopg"


def test_database_connection_can_initialize():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)

    table_names = set(inspect(engine).get_table_names())

    assert "inventory_items" in table_names
    assert "inventory_locations" in table_names
    assert "stock_movements" in table_names
    assert "stock_mutation_requests" in table_names
    assert "routes" in table_names


def test_stock_mutation_uniqueness_and_inventory_checks_exist():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    inspector = inspect(engine)

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("stock_mutation_requests")
    }
    item_checks = {constraint["name"] for constraint in inspector.get_check_constraints("inventory_items")}
    location_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("inventory_item_locations")
    }

    assert "uq_stock_mutation_request_operation_key" in unique_constraints
    assert "ck_inventory_items_allocated_lte_stock" in item_checks
    assert "ck_inventory_item_locations_allocated_lte_stock" in location_checks


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
