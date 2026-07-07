from pydantic import BaseModel


class InventoryLocationSummaryRow(BaseModel):
    warehouse: str
    inventory_location: str
    item_count: int
    total_in_stock: float
    total_allocated: float
    total_sellable: float
    total_on_order: float
    total_inventory_value: float
    under_par_count: int


class InventoryLocationSummaryResponse(BaseModel):
    groups: list[InventoryLocationSummaryRow]
    total_items: int
    total_in_stock: float
    total_allocated: float
    total_sellable: float
    total_on_order: float
    total_inventory_value: float
    under_par_count: int
