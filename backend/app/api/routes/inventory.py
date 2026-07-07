import csv
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.inventory import InventoryLocationSummaryResponse
from app.services.inventory_reports import INVENTORY_BY_LOCATION_COLUMNS, build_inventory_summary, get_inventory_items, item_to_inventory_by_location_row

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/export/by-location")
def export_inventory_by_location(
    warehouse: str | None = None,
    inventory_location: str | None = None,
    default_location: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    under_par: bool | None = None,
    non_inventory: bool | None = None,
    db: Session = Depends(get_db),
) -> Response:
    items = get_inventory_items(
        db,
        warehouse=warehouse,
        inventory_location=inventory_location,
        default_location=default_location,
        category=category,
        brand=brand,
        under_par=under_par,
        non_inventory=non_inventory,
    )
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=INVENTORY_BY_LOCATION_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(item_to_inventory_by_location_row(item))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-inventory-by-location-export.csv"'},
    )


@router.get("/summary/by-location", response_model=InventoryLocationSummaryResponse)
def summarize_inventory_by_location(
    warehouse: str | None = None,
    inventory_location: str | None = None,
    default_location: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    under_par: bool | None = None,
    non_inventory: bool | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    items = get_inventory_items(
        db,
        warehouse=warehouse,
        inventory_location=inventory_location,
        default_location=default_location,
        category=category,
        brand=brand,
        under_par=under_par,
        non_inventory=non_inventory,
    )
    return build_inventory_summary(items)
