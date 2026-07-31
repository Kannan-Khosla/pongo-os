#!/usr/bin/env python3
"""Destructively reset only an allowlisted local development database."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

LOCAL_ENVIRONMENTS = {"local", "development", "test", "testing"}
LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "::1"}


def validate_reset_target(app_env: str, database_url: str, *, dyno: str | None = None) -> tuple[str, str]:
    environment = (app_env or "").strip().casefold()
    if environment not in LOCAL_ENVIRONMENTS:
        raise ValueError(f"Database reset is blocked in APP_ENV={app_env!r}.")
    if dyno:
        raise ValueError("Database reset is blocked on Heroku/DYNO environments.")
    url = make_url(database_url)
    if url.get_backend_name() not in {"sqlite", "postgresql"}:
        raise ValueError(f"Database reset is blocked for unsupported driver {url.get_backend_name()!r}.")
    if url.get_backend_name() == "postgresql" and url.host not in LOCAL_HOSTS:
        raise ValueError(f"Database reset is blocked for non-local host {url.host!r}.")
    if url.get_backend_name() == "sqlite":
        database = str(url.database or "")
        if database != ":memory:":
            path = Path(database).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            if BACKEND_ROOT not in path.parents:
                raise ValueError(f"SQLite reset is blocked outside the backend directory: {path}.")
    return url.host or "local-file", url.database or ":memory:"


def reset_database(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            path = Path(url.database).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            path.unlink(missing_ok=True)
        return
    engine_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(engine_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation.")
    args = parser.parse_args()
    settings = get_settings()
    try:
        host, database = validate_reset_target(settings.app_env, settings.database_url, dyno=os.getenv("DYNO"))
    except ValueError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    print(f"Target database host: {host}")
    print(f"Target database name: {database}")
    print("This deletes local application data. It does not call WooCommerce.")
    if not args.yes and input("Type RESET LOCAL to continue: ").strip() != "RESET LOCAL":
        print("Cancelled.")
        return 1
    reset_database(settings.database_url)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_ROOT, check=True)
    print("Local database reset and migrations completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
