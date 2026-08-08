from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# These PostgreSQL expression/partial indexes are created explicitly by
# migration 20260805_0032. SQLAlchemy metadata cannot faithfully represent
# their reflected expressions, so autogenerate must leave them migration-owned.
MIGRATION_MANAGED_INDEXES = {
    "ix_orders_reporting_date",
    "ix_orders_reporting_customer_date",
}


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    if type_ == "index" and name in MIGRATION_MANAGED_INDEXES:
        return False
    return True


def get_url() -> str:
    url = get_settings().database_url
    return f"postgresql+psycopg://{url.split('://', 1)[1]}" if url.startswith(("postgres://", "postgresql://")) else url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
