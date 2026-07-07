from app.models.inventory import InventoryLocation
from app.schemas.locations import InventoryLocationCreate, InventoryLocationRead, InventoryLocationUpdate

CANONICAL_LOCATION_COLUMNS = [
    "Warehouse",
    "Location Code",
    "Location Name",
    "Description",
    "Zone",
    "Aisle",
    "Rack",
    "Shelf",
    "Bin",
    "Default",
    "Active",
]

LOCATION_CSV_FIELD_MAP = {
    "Warehouse": "warehouse",
    "Location Code": "location_code",
    "Location Name": "location_name",
    "Description": "description",
    "Zone": "zone",
    "Aisle": "aisle",
    "Rack": "rack",
    "Shelf": "shelf",
    "Bin": "bin",
    "Default": "is_default",
    "Active": "active",
}


def apply_location_payload(location: InventoryLocation, payload: InventoryLocationCreate | InventoryLocationUpdate, partial: bool = False) -> InventoryLocation:
    data = payload.model_dump(exclude_unset=partial)
    field_map = {
        "code": "location_code",
        "name": "location_name",
        "is_active": "active",
    }
    for field, value in data.items():
        target = field_map.get(field, field)
        if hasattr(location, target):
            setattr(location, target, value)
    return location


def location_to_read(location: InventoryLocation) -> InventoryLocationRead:
    return InventoryLocationRead(
        id=location.id,
        warehouse=location.warehouse or "",
        code=location.location_code or "",
        name=location.location_name or "",
        description=location.description,
        zone=location.zone,
        aisle=location.aisle,
        rack=location.rack,
        shelf=location.shelf,
        bin=location.bin,
        isDefault=location.is_default,
        isActive=location.active,
        createdAt=location.created_at,
        updatedAt=location.updated_at,
    )


def location_to_csv_row(location: InventoryLocation) -> dict[str, object]:
    return {column: getattr(location, attr) for column, attr in LOCATION_CSV_FIELD_MAP.items()}
