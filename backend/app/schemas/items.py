from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InventoryItemBase(BaseModel):
    client: str | None = Field(default=None, alias="Client")
    sku: str | None = Field(default=None, alias="SKU")
    description: str | None = Field(default=None, alias="Description")
    category: str | None = Field(default=None, alias="Category")
    unit_of_measurement: str | None = Field(default=None, alias="Unit of Measurement")
    warehouse: str | None = Field(default=None, alias="Warehouse")
    inventory_location: str | None = Field(default=None, alias="Inventory Location")
    default_location: str | None = Field(default=None, alias="Default Location")
    in_stock: float | None = Field(default=0, alias="In Stock")
    allocated: float | None = Field(default=0, alias="Allocated")
    sellable: float | None = Field(default=0, alias="Sellable")
    under_par: bool | None = Field(default=False, alias="Under Par")
    on_order: float | None = Field(default=0, alias="On Order")
    barcode: str | None = Field(default=None, alias="Barcode")
    manufacturer: str | None = Field(default=None, alias="Manufacturer")
    manufacturer_website: str | None = Field(default=None, alias="Manufacturer Website")
    recommended_retail_price: float | None = Field(default=None, alias="Recommended Retail Price")
    sales_price: float | None = Field(default=None, alias="Sales Price")
    unit_cost: float | None = Field(default=None, alias="Unit Cost")
    weight: float | None = Field(default=None, alias="Weight")
    default_econ_order: float | None = Field(default=None, alias="Default Econ Order")
    default_lead_time_days: int | None = Field(default=None, alias="Default Lead Time Days")
    par_level: float | None = Field(default=None, alias="Par Level")
    assembly: bool | None = Field(default=False, alias="Assembly")
    serializable: bool | None = Field(default=False, alias="Serializable")
    track_lot: bool | None = Field(default=False, alias="Track Lot")
    perishable: bool | None = Field(default=False, alias="Perishable")
    reorder: bool | None = Field(default=False, alias="Re-Order")
    storage_length: float | None = Field(default=None, alias="Storage Length")
    storage_width: float | None = Field(default=None, alias="Storage Width")
    storage_height: float | None = Field(default=None, alias="Storage Height")
    storage_volume: float | None = Field(default=None, alias="Storage Volume")
    brand: str | None = Field(default=None, alias="Brand")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InventoryItemCreate(InventoryItemBase):
    sku: str = Field(alias="SKU", min_length=1)
    image_url: str | None = Field(default=None, alias="imageUrl")
    active: bool = True
    non_inventory: bool = Field(default=False, alias="nonInventory")
    woo_product_id: int | None = Field(default=None, alias="wooProductId")
    woo_variation_id: int | None = Field(default=None, alias="wooVariationId")
    woo_product_type: str | None = Field(default=None, alias="wooProductType")
    woo_permalink: str | None = Field(default=None, alias="wooPermalink")
    woo_status: str | None = Field(default=None, alias="wooStatus")
    woo_manage_stock: bool | None = Field(default=None, alias="wooManageStock")
    woo_stock_status: str | None = Field(default=None, alias="wooStockStatus")
    woo_stock_quantity_snapshot: float | None = Field(default=None, alias="wooStockQuantitySnapshot")
    woo_sync_status: str | None = Field(default=None, alias="wooSyncStatus")
    woo_sync_error: str | None = Field(default=None, alias="wooSyncError")


class InventoryItemUpdate(InventoryItemBase):
    image_url: str | None = Field(default=None, alias="imageUrl")
    active: bool | None = None
    non_inventory: bool | None = Field(default=None, alias="nonInventory")
    woo_product_id: int | None = Field(default=None, alias="wooProductId")
    woo_variation_id: int | None = Field(default=None, alias="wooVariationId")
    woo_product_type: str | None = Field(default=None, alias="wooProductType")
    woo_permalink: str | None = Field(default=None, alias="wooPermalink")
    woo_status: str | None = Field(default=None, alias="wooStatus")
    woo_manage_stock: bool | None = Field(default=None, alias="wooManageStock")
    woo_stock_status: str | None = Field(default=None, alias="wooStockStatus")
    woo_stock_quantity_snapshot: float | None = Field(default=None, alias="wooStockQuantitySnapshot")
    woo_sync_status: str | None = Field(default=None, alias="wooSyncStatus")
    woo_sync_error: str | None = Field(default=None, alias="wooSyncError")


class InventoryItemRead(InventoryItemBase):
    id: int
    image_url: str | None = Field(default=None, alias="imageUrl")
    active: bool
    non_inventory: bool = Field(alias="nonInventory")
    woo_product_id: int | None = Field(default=None, alias="wooProductId")
    woo_variation_id: int | None = Field(default=None, alias="wooVariationId")
    woo_product_type: str | None = Field(default=None, alias="wooProductType")
    woo_permalink: str | None = Field(default=None, alias="wooPermalink")
    woo_status: str | None = Field(default=None, alias="wooStatus")
    woo_manage_stock: bool | None = Field(default=None, alias="wooManageStock")
    woo_stock_status: str | None = Field(default=None, alias="wooStockStatus")
    woo_stock_quantity_snapshot: float | None = Field(default=None, alias="wooStockQuantitySnapshot")
    woo_last_synced_at: datetime | None = Field(default=None, alias="wooLastSyncedAt")
    woo_sync_status: str | None = Field(default=None, alias="wooSyncStatus")
    woo_sync_error: str | None = Field(default=None, alias="wooSyncError")


class InventoryItemListResponse(BaseModel):
    items: list[InventoryItemRead]
    total: int

    model_config = ConfigDict(populate_by_name=True)
