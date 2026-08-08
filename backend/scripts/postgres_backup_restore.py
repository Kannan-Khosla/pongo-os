#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
from urllib.parse import parse_qs, unquote, urlparse

from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg


def current_alembic_head() -> str:
    """Return the single schema revision represented by this checkout."""
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise SystemExit(
            "Restore verification requires exactly one Alembic head; "
            f"found {len(heads)}: {', '.join(heads) or 'none'}."
        )
    return heads[0]


def current_application_tables() -> set[str]:
    """Return every application table declared by the current ORM models."""
    # Import lazily so command help and backup creation do not initialize the
    # full model graph. The verifier, however, must prove that a restored
    # database can support the complete application represented by this
    # checkout rather than a hand-maintained subset of "important" tables.
    from app.models import Base

    return {table.name for table in Base.metadata.sorted_tables}


def validate_restored_schema(conn, expected_revision: str) -> str:
    revision_rows = list(conn.execute("SELECT version_num FROM alembic_version"))
    restored_revisions = [str(row[0]) for row in revision_rows]
    tables = {row[0] for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    required_tables = current_application_tables()
    missing_tables = sorted(required_tables - tables)

    if restored_revisions != [expected_revision] or missing_tables:
        raise SystemExit(
            "Restore verification failed: "
            f"restored_revisions={restored_revisions}, "
            f"expected_revision={expected_revision}, "
            f"missing_tables={missing_tables}"
        )
    return restored_revisions[0]


def connection(url: str) -> tuple[dict[str, str], str]:
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.path.strip("/"):
        raise SystemExit("A PostgreSQL database URL with an explicit database name is required.")
    query = parse_qs(parsed.query)
    env = os.environ.copy()
    env.update({
        "PGHOST": parsed.hostname or "localhost",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": unquote(parsed.username or "postgres"),
        "PGPASSWORD": unquote(parsed.password or ""),
    })
    if query.get("sslmode"):
        env["PGSSLMODE"] = query["sslmode"][0]
    return env, parsed.path.strip("/")


def backup(url: str, output: Path, overwrite: bool = False) -> None:
    if output.exists() and not overwrite:
        raise SystemExit(f"Backup already exists: {output}. Pass --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    env, database = connection(url)
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(output), database], env=env, check=True)
    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit("pg_dump completed without producing a backup file.")
    print(f"Backup created: {output} ({output.stat().st_size} bytes)")


def verify(backup_file: Path, target_url: str, keep: bool = False) -> None:
    if not backup_file.is_file() or backup_file.stat().st_size == 0:
        raise SystemExit("A non-empty custom-format backup is required.")
    env, database = connection(target_url)
    if not database.endswith("_restore_verify"):
        raise SystemExit("Safety stop: the restore target database name must end with _restore_verify.")
    expected_revision = current_alembic_head()
    subprocess.run(["dropdb", "--if-exists", database], env=env, check=True)
    try:
        subprocess.run(["createdb", database], env=env, check=True)
        subprocess.run(["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", database, str(backup_file)], env=env, check=True)
        with psycopg.connect(target_url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
            revision = validate_restored_schema(conn, expected_revision)
        print(f"Restore verified at revision {revision} in {database}.")
    finally:
        if not keep:
            subprocess.run(["dropdb", "--if-exists", database], env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and validate Pongo PostgreSQL backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("output", type=Path)
    backup_parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    backup_parser.add_argument("--overwrite", action="store_true")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("backup", type=Path)
    verify_parser.add_argument("--target-url", default=os.environ.get("RESTORE_VERIFY_DATABASE_URL", ""))
    verify_parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.command == "backup":
        backup(args.database_url, args.output, args.overwrite)
    else:
        verify(args.backup, args.target_url, args.keep)


if __name__ == "__main__":
    main()
