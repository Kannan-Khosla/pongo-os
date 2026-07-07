from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem
from app.services.calculations import calculate_inventory_value, calculate_sellable, calculate_storage_volume, calculate_under_par

INVENTORY_BY_LOCATION_COLUMNS = [
    "Warehouse",
    "Inventory Location",
    "Default Location",
    "SKU",
    "Barcode",
    "Description",
    "Category",
    "Brand",
    "In Stock",
    "Allocated",
    "Sellable",
    "Under Par",
    "On Order",
    "Par Level",
    "Unit Cost",
    "Inventory Value",
    "Weight",
    "Storage Length",
    "Storage Width",
    "Storage Height",
    "Storage Volume",
    "Manufacturer",
    "Manufacturer Website",
    "Client",
    "Unit of Measurement",
    "Recommended Retail Price",
    "Sales Price",
    "Default Econ Order",
    "Default Lead Time Days",
    "Assembly",
    "Serializable",
    "Track Lot",
    "Perishable",
    "Re-Order",
]


def build_inventory_items_query(
    warehouse: str | None = None,
    inventory_location: str | None = None,
    default_location: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    under_par: bool | None = None,
    non_inventory: bool | None = None,
):
    statement = select(InventoryItem)
    if warehouse:
        statement = statement.where(InventoryItem.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(InventoryItem.inventory_location == inventory_location)
    if default_location:
        statement = statement.where(InventoryItem.default_location == default_location)
    if category:
        statement = statement.where(InventoryItem.category == category)
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if non_inventory is not None:
        statement = statement.where(InventoryItem.non_inventory.is_(non_inventory))
    statement = statement.order_by(InventoryItem.warehouse.asc().nullslast(), InventoryItem.inventory_location.asc().nullslast(), InventoryItem.sku.asc().nullslast())
    return statement, under_par


def get_inventory_items(db: Session, **filters) -> list[InventoryItem]:
    statement, under_par = build_inventory_items_query(**filters)
    items = list(db.scalars(statement).all())
    if under_par is not None:
        items = [item for item in items if calculate_under_par(item.in_stock, item.par_level) is under_par]
    return items


def recalculate_item_fields(item: InventoryItem) -> dict[str, Decimal | bool]:
    sellable = calculate_sellable(item.in_stock, item.allocated)
    under_par = calculate_under_par(item.in_stock, item.par_level)
    storage_volume = calculate_storage_volume(item.storage_length, item.storage_width, item.storage_height)
    inventory_value = calculate_inventory_value(item.in_stock, item.unit_cost)
    return {
        "sellable": sellable,
        "under_par": under_par,
        "storage_volume": storage_volume,
        "inventory_value": inventory_value,
    }


def item_to_inventory_by_location_row(item: InventoryItem) -> dict[str, object]:
    calculated = recalculate_item_fields(item)
    return {
        "Warehouse": item.warehouse or "",
        "Inventory Location": item.inventory_location or "",
        "Default Location": item.default_location or "",
        "SKU": item.sku or "",
        "Barcode": item.barcode or "",
        "Description": item.description or "",
        "Category": item.category or "",
        "Brand": item.brand or "",
        "In Stock": item.in_stock or Decimal("0"),
        "Allocated": item.allocated or Decimal("0"),
        "Sellable": calculated["sellable"],
        "Under Par": calculated["under_par"],
        "On Order": item.on_order or Decimal("0"),
        "Par Level": item.par_level or Decimal("0"),
        "Unit Cost": item.unit_cost or Decimal("0"),
        "Inventory Value": calculated["inventory_value"],
        "Weight": item.weight or Decimal("0"),
        "Storage Length": item.storage_length or Decimal("0"),
        "Storage Width": item.storage_width or Decimal("0"),
        "Storage Height": item.storage_height or Decimal("0"),
        "Storage Volume": calculated["storage_volume"],
        "Manufacturer": item.manufacturer or "",
        "Manufacturer Website": item.manufacturer_website or "",
        "Client": item.client or "",
        "Unit of Measurement": item.unit_of_measurement or "",
        "Recommended Retail Price": item.recommended_retail_price or Decimal("0"),
        "Sales Price": item.sales_price or Decimal("0"),
        "Default Econ Order": item.default_econ_order or Decimal("0"),
        "Default Lead Time Days": item.default_lead_time_days or 0,
        "Assembly": item.assembly,
        "Serializable": item.serializable,
        "Track Lot": item.track_lot,
        "Perishable": item.perishable,
        "Re-Order": item.reorder,
    }


def build_inventory_summary(items: list[InventoryItem]) -> dict[str, object]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    totals = {
        "total_items": 0,
        "total_in_stock": Decimal("0"),
        "total_allocated": Decimal("0"),
        "total_sellable": Decimal("0"),
        "total_on_order": Decimal("0"),
        "total_inventory_value": Decimal("0"),
        "under_par_count": 0,
    }

    for item in items:
        calculated = recalculate_item_fields(item)
        warehouse = item.warehouse or ""
        inventory_location = item.inventory_location or ""
        key = (warehouse, inventory_location)
        group = groups.setdefault(
            key,
            {
                "warehouse": warehouse,
                "inventory_location": inventory_location,
                "item_count": 0,
                "total_in_stock": Decimal("0"),
                "total_allocated": Decimal("0"),
                "total_sellable": Decimal("0"),
                "total_on_order": Decimal("0"),
                "total_inventory_value": Decimal("0"),
                "under_par_count": 0,
            },
        )
        in_stock = item.in_stock or Decimal("0")
        allocated = item.allocated or Decimal("0")
        on_order = item.on_order or Decimal("0")
        group["item_count"] += 1
        group["total_in_stock"] += in_stock
        group["total_allocated"] += allocated
        group["total_sellable"] += calculated["sellable"]
        group["total_on_order"] += on_order
        group["total_inventory_value"] += calculated["inventory_value"]
        group["under_par_count"] += 1 if calculated["under_par"] else 0

        totals["total_items"] += 1
        totals["total_in_stock"] += in_stock
        totals["total_allocated"] += allocated
        totals["total_sellable"] += calculated["sellable"]
        totals["total_on_order"] += on_order
        totals["total_inventory_value"] += calculated["inventory_value"]
        totals["under_par_count"] += 1 if calculated["under_par"] else 0

    ordered_groups = sorted(groups.values(), key=lambda row: (str(row["warehouse"]), str(row["inventory_location"])))
    return {**totals, "groups": ordered_groups}
