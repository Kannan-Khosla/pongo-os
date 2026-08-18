from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, event, func, inspect
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base


METRIC_SOURCE_TABLES = {
    "allocation_lines",
    "allocations",
    "fulfillment_lines",
    "fulfillments",
    "inventory_item_locations",
    "inventory_items",
    "order_items",
    "orders",
    "pick_lines",
    "picks",
    "receipt_items",
    "receipts",
    "stock_movements",
    "woo_subscription_line_snapshots",
}

# Sync bookkeeping changes do not alter any dashboard calculation. Ignoring
# them keeps a two-minute no-op Woo sync from invalidating every warm cache.
METRIC_IGNORED_COLUMNS = {
    "date_modified",
    "last_synced_at",
    "sync_error",
    "sync_status",
    "updated_at",
    "woo_last_synced_at",
    "woo_sync_error",
    "woo_sync_status",
    "workflow_notes",
}


class MetricVersion(Base):
    __tablename__ = "metric_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MetricCache(Base):
    __tablename__ = "metric_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    refresh_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_metric_cache_namespace_version", "namespace", "source_version"),)


def metric_version_insert(session: Session):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql_insert(MetricVersion)
    if dialect == "sqlite":
        return sqlite_insert(MetricVersion)
    raise RuntimeError(f"Metric versioning does not support the {dialect!r} database dialect.")


def ensure_metric_version(session: Session) -> None:
    session.execute(
        metric_version_insert(session)
        .values(id=1, version=0)
        .on_conflict_do_nothing(index_elements=[MetricVersion.id])
    )


def bump_metric_version(session: Session) -> None:
    session.execute(
        metric_version_insert(session)
        .values(id=1, version=1)
        .on_conflict_do_update(
            index_elements=[MetricVersion.id],
            set_={"version": MetricVersion.version + 1, "updated_at": func.now()},
        )
    )


@event.listens_for(Session, "before_flush")
def invalidate_metrics_for_orm_changes(session: Session, _flush_context, _instances) -> None:
    if any(
        getattr(value, "__tablename__", None) in METRIC_SOURCE_TABLES
        for value in session.new.union(session.deleted)
    ) or any(metric_columns_changed(value) for value in session.dirty):
        bump_metric_version(session)


def metric_columns_changed(value: object) -> bool:
    if getattr(value, "__tablename__", None) not in METRIC_SOURCE_TABLES:
        return False
    state = inspect(value)
    return any(
        attribute.key not in METRIC_IGNORED_COLUMNS and state.attrs[attribute.key].history.has_changes()
        for attribute in state.mapper.column_attrs
    )
