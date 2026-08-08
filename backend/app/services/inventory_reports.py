from decimal import Decimal

from sqlalchemy import Numeric, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.inventory import InventoryItem, InventoryItemLocation
from app.services.calculations import calculate_inventory_value, calculate_sellable, calculate_storage_volume, calculate_under_par

INVENTORY_DATA_QUALITY_FILTERS = {
    "missing_barcode",
    "missing_brand",
    "missing_cost",
    "unmapped",
    "receiving",
    "missing_location",
}

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
    load_locations: bool = True,
):
    statement = select(InventoryItem)
    if load_locations:
        statement = statement.options(selectinload(InventoryItem.locations))
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


def parse_inventory_data_quality_filters(value: str | None) -> set[str]:
    if not value or not value.strip():
        return set()
    parsed = {part.strip().lower() for part in value.split(",") if part.strip()}
    invalid = parsed - INVENTORY_DATA_QUALITY_FILTERS
    if invalid:
        raise ValueError(f"Unsupported data_quality filter: {', '.join(sorted(invalid))}")
    return parsed


def item_matches_inventory_search(item: InventoryItem, search: str) -> bool:
    query = search.casefold()
    values = (
        item.sku,
        item.barcode,
        item.woo_name,
        item.description,
        item.category,
        item.brand,
        item.manufacturer,
        item.warehouse,
        item.inventory_location,
    )
    return any(query in str(value).casefold() for value in values if value is not None)


def item_matches_data_quality(item: InventoryItem, filters: set[str]) -> bool:
    locations = list(item.locations or [])
    usable_locations = [
        location
        for location in locations
        if location.active and str(location.warehouse or "").strip() and str(location.inventory_location or "").strip()
    ]
    checks = {
        "missing_barcode": not str(item.barcode or "").strip(),
        "missing_brand": not str(item.brand or "").strip(),
        "missing_cost": item.unit_cost is None,
        "unmapped": item.woo_product_id is None,
        "receiving": str(item.inventory_location or "").strip().casefold() == "receiving"
        or any(str(location.inventory_location or "").strip().casefold() == "receiving" for location in usable_locations),
        "missing_location": not usable_locations,
    }
    return any(checks[name] for name in filters)


def get_inventory_items(db: Session, **filters) -> list[InventoryItem]:
    search = str(filters.pop("search", "") or "").strip()
    quality_filters = parse_inventory_data_quality_filters(filters.pop("data_quality", None))
    statement, under_par = build_inventory_items_query(**filters)
    items = list(db.scalars(statement).all())
    if search:
        items = [item for item in items if item_matches_inventory_search(item, search)]
    if quality_filters:
        items = [item for item in items if item_matches_data_quality(item, quality_filters)]
    if under_par is not None:
        items = [item for item in items if calculate_under_par(item.in_stock, item.par_level) is under_par]
    return items


def query_inventory_summary(db: Session, **filters) -> dict[str, object]:
    search = str(filters.pop("search", "") or "").strip()
    quality_filters = parse_inventory_data_quality_filters(filters.pop("data_quality", None))
    statement, under_par = build_inventory_items_query(load_locations=False, **filters)
    if search:
        escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_search}%"
        statement = statement.where(or_(
            InventoryItem.sku.ilike(pattern, escape="\\"),
            InventoryItem.barcode.ilike(pattern, escape="\\"),
            InventoryItem.woo_name.ilike(pattern, escape="\\"),
            InventoryItem.description.ilike(pattern, escape="\\"),
            InventoryItem.category.ilike(pattern, escape="\\"),
            InventoryItem.brand.ilike(pattern, escape="\\"),
            InventoryItem.manufacturer.ilike(pattern, escape="\\"),
            InventoryItem.warehouse.ilike(pattern, escape="\\"),
            InventoryItem.inventory_location.ilike(pattern, escape="\\"),
        ))

    usable_location = InventoryItem.locations.any(and_(
        InventoryItemLocation.active.is_(True),
        func.trim(func.coalesce(InventoryItemLocation.warehouse, "")) != "",
        func.trim(func.coalesce(InventoryItemLocation.inventory_location, "")) != "",
    ))
    receiving_location = InventoryItem.locations.any(and_(
        InventoryItemLocation.active.is_(True),
        func.trim(func.coalesce(InventoryItemLocation.warehouse, "")) != "",
        func.lower(func.trim(func.coalesce(InventoryItemLocation.inventory_location, ""))) == "receiving",
    ))
    quality_predicates = {
        "missing_barcode": func.trim(func.coalesce(InventoryItem.barcode, "")) == "",
        "missing_brand": func.trim(func.coalesce(InventoryItem.brand, "")) == "",
        "missing_cost": InventoryItem.unit_cost.is_(None),
        "unmapped": InventoryItem.woo_product_id.is_(None),
        "receiving": or_(
            func.lower(func.trim(func.coalesce(InventoryItem.inventory_location, ""))) == "receiving",
            receiving_location,
        ),
        "missing_location": ~usable_location,
    }
    if quality_filters:
        statement = statement.where(or_(*(quality_predicates[name] for name in quality_filters)))

    under_par_predicate = and_(InventoryItem.par_level.is_not(None), InventoryItem.in_stock <= InventoryItem.par_level)
    if under_par is True:
        statement = statement.where(under_par_predicate)
    elif under_par is False:
        statement = statement.where(~under_par_predicate)

    warehouse = func.coalesce(InventoryItem.warehouse, "")
    inventory_location = func.coalesce(InventoryItem.inventory_location, "")
    aggregate_statement = statement.order_by(None).with_only_columns(
        warehouse.label("warehouse"),
        inventory_location.label("inventory_location"),
        func.count(InventoryItem.id).label("item_count"),
        func.coalesce(func.sum(InventoryItem.in_stock), 0).label("total_in_stock"),
        func.coalesce(func.sum(InventoryItem.allocated), 0).label("total_allocated"),
        func.coalesce(func.sum(InventoryItem.in_stock - InventoryItem.allocated), 0).label("total_sellable"),
        func.coalesce(func.sum(InventoryItem.on_order), 0).label("total_on_order"),
        func.coalesce(func.sum(cast(InventoryItem.in_stock * func.coalesce(InventoryItem.unit_cost, 0), Numeric(30, 5))), 0).label("total_inventory_value"),
        func.coalesce(func.sum(case((under_par_predicate, 1), else_=0)), 0).label("under_par_count"),
    ).group_by(warehouse, inventory_location).order_by(warehouse, inventory_location)
    groups = [dict(row._mapping) for row in db.execute(aggregate_statement).all()]
    totals = {
        "total_items": sum(int(group["item_count"] or 0) for group in groups),
        "total_in_stock": sum((group["total_in_stock"] or Decimal("0") for group in groups), Decimal("0")),
        "total_allocated": sum((group["total_allocated"] or Decimal("0") for group in groups), Decimal("0")),
        "total_sellable": sum((group["total_sellable"] or Decimal("0") for group in groups), Decimal("0")),
        "total_on_order": sum((group["total_on_order"] or Decimal("0") for group in groups), Decimal("0")),
        "total_inventory_value": sum((group["total_inventory_value"] or Decimal("0") for group in groups), Decimal("0")),
        "under_par_count": sum(int(group["under_par_count"] or 0) for group in groups),
    }
    return {**totals, "groups": groups}


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
        "Unit Cost": item.unit_cost if item.unit_cost is not None else "",
        "Inventory Value": calculated["inventory_value"] if item.unit_cost is not None else "",
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
