from pathlib import Path

import pytest

from scripts.reset_local_db import validate_reset_target


def test_local_database_reset_guard_allows_local_postgres_and_backend_sqlite():
    host, database = validate_reset_target("development", "postgresql://postgres:postgres@localhost:5432/pongo_test")
    sqlite_path = Path(__file__).resolve().parents[1] / "reset-test.db"
    sqlite_host, sqlite_database = validate_reset_target("test", f"sqlite:///{sqlite_path}")

    assert (host, database) == ("localhost", "pongo_test")
    assert sqlite_host == "local-file"
    assert sqlite_database.endswith("reset-test.db")


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_database_reset_guard_blocks_nonlocal_environments(environment):
    with pytest.raises(ValueError, match="APP_ENV"):
        validate_reset_target(environment, "postgresql://postgres:postgres@localhost:5432/pongo")


def test_database_reset_guard_blocks_remote_database_host():
    with pytest.raises(ValueError, match="non-local host"):
        validate_reset_target("development", "postgresql://user:password@db.example.com:5432/pongo")


def test_database_reset_guard_blocks_heroku():
    with pytest.raises(ValueError, match="Heroku"):
        validate_reset_target("development", "postgresql://postgres:postgres@localhost:5432/pongo", dyno="web.1")
