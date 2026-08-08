from __future__ import annotations

import pytest

from scripts import postgres_backup_restore


class FakeScriptDirectory:
    def __init__(self, heads: list[str]):
        self.heads = heads

    def get_heads(self) -> list[str]:
        return self.heads


def test_current_alembic_head_is_discovered_from_migration_graph(monkeypatch):
    monkeypatch.setattr(
        postgres_backup_restore.ScriptDirectory,
        "from_config",
        lambda config: FakeScriptDirectory(["future_revision"]),
    )

    assert postgres_backup_restore.current_alembic_head() == "future_revision"


@pytest.mark.parametrize("heads", [[], ["head_a", "head_b"]])
def test_current_alembic_head_rejects_ambiguous_migration_graph(monkeypatch, heads):
    monkeypatch.setattr(
        postgres_backup_restore.ScriptDirectory,
        "from_config",
        lambda config: FakeScriptDirectory(heads),
    )

    with pytest.raises(SystemExit, match="exactly one Alembic head"):
        postgres_backup_restore.current_alembic_head()


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def __iter__(self):
        return iter(self.rows)


class FakeConnection:
    def __init__(self, *, revisions=None, tables=None):
        self.revisions = ["future_revision"] if revisions is None else revisions
        self.tables = {
            "inventory_items",
            "stock_movements",
            "orders",
            "users",
            "woo_stock_sync_jobs",
        } if tables is None else tables

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        if "alembic_version" in statement:
            return FakeResult([(revision,) for revision in self.revisions])
        if "pg_tables" in statement:
            return FakeResult([(table,) for table in sorted(self.tables)])
        return FakeResult([(0,)])


def test_verify_compares_restore_with_discovered_head(monkeypatch, tmp_path):
    backup_file = tmp_path / "backup.dump"
    backup_file.write_bytes(b"test backup")
    monkeypatch.setattr(postgres_backup_restore, "current_alembic_head", lambda: "future_revision")
    monkeypatch.setattr(
        postgres_backup_restore,
        "current_application_tables",
        lambda: {"inventory_items", "stock_movements", "orders", "users", "woo_stock_sync_jobs"},
    )
    monkeypatch.setattr(postgres_backup_restore.psycopg, "connect", lambda url: FakeConnection())
    monkeypatch.setattr(postgres_backup_restore.subprocess, "run", lambda *args, **kwargs: None)

    postgres_backup_restore.verify(
        backup_file,
        "postgresql://postgres:postgres@localhost/pongo_restore_verify",
    )


def test_validate_restore_rejects_unexpected_extra_revision(monkeypatch):
    monkeypatch.setattr(postgres_backup_restore, "current_application_tables", lambda: {"orders"})

    with pytest.raises(SystemExit, match="restored_revisions=.*future_revision.*unexpected_revision"):
        postgres_backup_restore.validate_restored_schema(
            FakeConnection(revisions=["future_revision", "unexpected_revision"], tables={"orders"}),
            "future_revision",
        )


def test_validate_restore_rejects_any_missing_orm_table(monkeypatch):
    monkeypatch.setattr(postgres_backup_restore, "current_application_tables", lambda: {"orders", "order_items"})

    with pytest.raises(SystemExit, match=r"missing_tables=\['order_items'\]"):
        postgres_backup_restore.validate_restored_schema(
            FakeConnection(tables={"orders"}),
            "future_revision",
        )
