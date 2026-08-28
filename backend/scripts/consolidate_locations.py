#!/usr/bin/env python3
"""Dry-run or apply a one-location inventory consolidation."""

import argparse
import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.location_consolidation import consolidate_locations


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate all inventory into one existing physical location.")
    parser.add_argument("--target-location-id", required=True, type=int)
    parser.add_argument("--actor", default="system:location-consolidation")
    parser.add_argument("--idempotency-key", default="main-warehouse-001-consolidation-v1")
    parser.add_argument("--apply", action="store_true", help="Commit the consolidation. Without this flag the command is read-only.")
    args = parser.parse_args()

    with SessionLocal() as db:
        result = consolidate_locations(
            db,
            args.target_location_id,
            actor=args.actor,
            idempotency_key=args.idempotency_key,
            apply=args.apply,
        )
        if args.apply:
            db.commit()
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
