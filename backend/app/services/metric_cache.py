from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from threading import Lock
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.performance import MetricCache, MetricVersion, bump_metric_version, ensure_metric_version


# The local lock covers SQLite/tests. PostgreSQL's transaction lock coordinates
# the separate web and worker processes without another service.
_build_lock = Lock()


def cached_metric_payload(
    db: Session,
    namespace: str,
    params: dict[str, Any],
    builder: Callable[[], dict[str, Any]],
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    cache_key = metric_cache_key(namespace, params)
    version = current_metric_version(db)
    cached = db.get(MetricCache, cache_key)
    if cached is not None and cached.source_version == version:
        return cached.payload
    if cached is not None and not force_refresh:
        cached.refresh_requested_at = datetime.now(timezone.utc)
        db.commit()
        return cached.payload

    with _build_lock:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": signed_lock_key(cache_key)},
            )
        version = current_metric_version(db)
        cached = db.get(MetricCache, cache_key, populate_existing=True)
        if cached is not None and cached.source_version == version:
            return cached.payload
        if cached is not None and not force_refresh:
            cached.refresh_requested_at = datetime.now(timezone.utc)
            db.commit()
            return cached.payload
        payload = builder()
        if cached is None:
            cached = MetricCache(
                cache_key=cache_key,
                namespace=namespace,
                params=params,
                source_version=version,
                payload=payload,
            )
            db.add(cached)
        else:
            cached.params = params
            cached.source_version = version
            cached.payload = payload
            cached.generated_at = datetime.now(timezone.utc)
            cached.refresh_requested_at = None
        db.commit()
        return payload


def current_metric_version(db: Session) -> int:
    version = db.scalar(select(MetricVersion.version).where(MetricVersion.id == 1))
    if version is not None:
        return int(version)
    ensure_metric_version(db)
    version = db.scalar(select(MetricVersion.version).where(MetricVersion.id == 1))
    if version is None:
        raise RuntimeError("Unable to initialize the metric cache version.")
    return int(version)


def invalidate_metrics(db: Session) -> None:
    bump_metric_version(db)


def metric_cache_key(namespace: str, params: dict[str, Any]) -> str:
    canonical = json.dumps({"namespace": namespace, "params": params}, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(canonical.encode()).hexdigest()


def signed_lock_key(cache_key: str) -> int:
    value = int(cache_key[:16], 16)
    return value - (1 << 64) if value >= (1 << 63) else value
