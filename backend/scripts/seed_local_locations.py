#!/usr/bin/env python3
"""Idempotently seed the local Main Warehouse receiving location."""

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory import InventoryLocation


def main() -> None:
    with SessionLocal() as db:
        location = db.scalars(select(InventoryLocation).where(InventoryLocation.warehouse == "Main Warehouse", InventoryLocation.location_code == "RECEIVING")).one_or_none()
        if location is None:
            location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code="RECEIVING", location_name="Receiving", description="Default receiving and first-migration location", is_default=True, active=True)
            db.add(location)
        else:
            location.location_name = "Receiving"
            location.is_default = True
            location.active = True
        db.commit()
        print(f"Seeded Main Warehouse / Receiving (location id {location.id}).")


if __name__ == "__main__":
    main()
