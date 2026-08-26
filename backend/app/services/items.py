from app.models.inventory import InventoryItem
from app.schemas.items import InventoryItemCreate, InventoryItemUpdate
from app.services.calculations import calculate_sellable, calculate_storage_volume, calculate_under_par

CANONICAL_ITEM_COLUMNS = [
    "Client",
    "SKU",
    "Description",
    "Category",
    "Unit of Measurement",
    "Warehouse",
    "Inventory Location",
    "Default Location",
    "In Stock",
    "Allocated",
    "Sellable",
    "Under Par",
    "On Order",
    "Barcode",
    "Manufacturer",
    "Manufacturer Website",
    "Recommended Retail Price",
    "Sales Price",
    "Unit Cost",
    "Weight",
    "Default Econ Order",
    "Default Lead Time Days",
    "Par Level",
    "Assembly",
    "Serializable",
    "Track Lot",
    "Perishable",
    "Re-Order",
    "Storage Length",
    "Storage Width",
    "Storage Height",
    "Storage Volume",
    "Brand",
    "Tags",
]

CSV_FIELD_MAP = {
    "Client": "client",
    "SKU": "sku",
    "Description": "description",
    "Category": "category",
    "Unit of Measurement": "unit_of_measurement",
    "Warehouse": "warehouse",
    "Inventory Location": "inventory_location",
    "Default Location": "default_location",
    "In Stock": "in_stock",
    "Allocated": "allocated",
    "Sellable": "sellable",
    "Under Par": "under_par",
    "On Order": "on_order",
    "Barcode": "barcode",
    "Manufacturer": "manufacturer",
    "Manufacturer Website": "manufacturer_website",
    "Recommended Retail Price": "recommended_retail_price",
    "Sales Price": "sales_price",
    "Unit Cost": "unit_cost",
    "Weight": "weight",
    "Default Econ Order": "default_econ_order",
    "Default Lead Time Days": "default_lead_time_days",
    "Par Level": "par_level",
    "Assembly": "assembly",
    "Serializable": "serializable",
    "Track Lot": "track_lot",
    "Perishable": "perishable",
    "Re-Order": "reorder",
    "Storage Length": "storage_length",
    "Storage Width": "storage_width",
    "Storage Height": "storage_height",
    "Storage Volume": "storage_volume",
    "Brand": "brand",
    "Tags": "tags",
}


def apply_calculated_fields(item: InventoryItem) -> None:
    item.sellable = calculate_sellable(item.in_stock, item.allocated)
    item.under_par = calculate_under_par(item.in_stock, item.par_level)
    item.storage_volume = calculate_storage_volume(item.storage_length, item.storage_width, item.storage_height)


def apply_item_payload(item: InventoryItem, payload: InventoryItemCreate | InventoryItemUpdate, partial: bool = False) -> InventoryItem:
    data = payload.model_dump(by_alias=False, exclude_unset=partial)
    for field, value in data.items():
        if field in {"in_stock", "allocated", "sellable", "under_par", "storage_volume"}:
            continue
        if hasattr(item, field):
            setattr(item, field, value)
    item.source = item.source or "manual"
    apply_calculated_fields(item)
    return item


def item_to_csv_row(item: InventoryItem) -> dict[str, object]:
    apply_calculated_fields(item)
    row = {column: getattr(item, attr) for column, attr in CSV_FIELD_MAP.items()}
    row["Description"] = item.woo_name or item.description
    return row
