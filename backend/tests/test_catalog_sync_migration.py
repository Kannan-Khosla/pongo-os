from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem
from app.models.woocommerce import WooItemMapping


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def alembic(database_url: str, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=check,
    )


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def catalog_object_definitions(engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type IN ('table', 'index') AND (name LIKE '%catalog%' OR name LIKE 'uq_woo_map_active_%')"
        )).all()
    return {name: sql or "" for name, sql in rows}


def assert_catalog_objects(engine) -> None:
    inspector = inspect(engine)
    assert "woo_catalog_sync_rows" in inspector.get_table_names()
    assert {"request_key", "attempt_count", "updated_at"}.issubset(
        {column["name"] for column in inspector.get_columns("woocommerce_sync_runs")}
    )
    definitions = catalog_object_definitions(engine)
    expected = {
        "uq_woo_catalog_one_active",
        "uq_woo_catalog_request_key",
        "uq_woo_map_active_item",
        "uq_woo_map_active_product",
        "uq_woo_map_active_variation",
    }
    assert expected.issubset(definitions)
    assert "uq_woo_catalog_row_run_remote" in {
        constraint["name"] for constraint in inspector.get_unique_constraints("woo_catalog_sync_rows")
    }
    assert all(len(identifier) <= 63 for identifier in definitions)
    active = " ".join(definitions["uq_woo_catalog_one_active"].lower().split())
    assert "fetching_variations" in active
    assert "waiting_retry" in active
    assert "cancelling" in active
    variation = " ".join(definitions["uq_woo_map_active_variation"].lower().split())
    assert "woo_item_mappings (woo_variation_id)" in variation
    assert "woo_product_id, woo_variation_id" not in variation


def test_catalog_migration_fresh_head_and_down_up_are_exact(tmp_path):
    database_url = sqlite_url(tmp_path / "fresh.sqlite")
    alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    assert_catalog_objects(engine)

    alembic(database_url, "downgrade", "20260819_0040")
    downgraded = inspect(engine)
    assert "woo_catalog_sync_rows" not in downgraded.get_table_names()
    assert "request_key" not in {column["name"] for column in downgraded.get_columns("woocommerce_sync_runs")}

    alembic(database_url, "upgrade", "20260821_0041")
    assert_catalog_objects(engine)


def test_catalog_migration_fails_closed_on_legacy_mapping_conflicts(tmp_path):
    database_url = sqlite_url(tmp_path / "conflict.sqlite")
    alembic(database_url, "upgrade", "head")
    alembic(database_url, "downgrade", "20260819_0040")
    engine = create_engine(database_url)
    with Session(engine) as db:
        item = InventoryItem(
            sku="DUPLICATE-MAPPING-TARGET",
            in_stock=0,
            allocated=0,
            sellable=0,
            active=True,
            non_inventory=False,
        )
        db.add(item)
        db.flush()
        db.add_all([
            WooItemMapping(item_id=item.id, woo_product_id=701, active=True),
            WooItemMapping(item_id=item.id, woo_product_id=702, active=True),
        ])
        db.commit()

    result = alembic(database_url, "upgrade", "20260821_0041", check=False)

    assert result.returncode != 0
    assert "Catalog mapping uniqueness preflight failed" in result.stderr
    assert "local item" in result.stderr
    assert "woo_catalog_sync_rows" not in inspect(engine).get_table_names()
