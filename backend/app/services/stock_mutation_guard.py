from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.stock_mutations import StockMutationRequest


class IdempotencyConflict(ValueError):
    pass


def begin_stock_mutation(
    db: Session,
    operation: str,
    idempotency_key: str | None,
    payload: BaseModel | dict[str, Any],
) -> tuple[StockMutationRequest | None, dict | None]:
    key = (idempotency_key or "").strip()
    if not key:
        raise IdempotencyConflict("A nonblank idempotency key is required for stock-changing requests.")
    if len(key) > 120:
        raise IdempotencyConflict("Idempotency key must be 120 characters or fewer.")

    request_hash = mutation_request_hash(payload)
    existing = db.scalars(
        select(StockMutationRequest)
        .where(
            StockMutationRequest.operation == operation,
            StockMutationRequest.idempotency_key == key,
        )
        .with_for_update()
    ).one_or_none()
    if existing is not None:
        return validate_existing_mutation(existing, request_hash)

    request = StockMutationRequest(
        operation=operation,
        idempotency_key=key,
        request_hash=request_hash,
        status="pending",
    )
    try:
        db.add(request)
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalars(
            select(StockMutationRequest).where(
                StockMutationRequest.operation == operation,
                StockMutationRequest.idempotency_key == key,
            )
        ).one()
        return validate_existing_mutation(existing, request_hash)
    return request, None


def complete_stock_mutation(request: StockMutationRequest | None, response_payload: BaseModel | dict[str, Any]) -> None:
    if request is None:
        return
    request.status = "completed"
    request.response_payload = jsonable_encoder(response_payload)


def mutation_request_hash(payload: BaseModel | dict[str, Any]) -> str:
    data = payload.model_dump(mode="json", by_alias=False) if isinstance(payload, BaseModel) else dict(payload)
    data.pop("idempotency_key", None)
    encoded = json.dumps(jsonable_encoder(data), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def validate_existing_mutation(
    request: StockMutationRequest,
    request_hash: str,
) -> tuple[StockMutationRequest, dict | None]:
    if request.request_hash != request_hash:
        raise IdempotencyConflict("Idempotency key was already used with a different request.")
    if request.status != "completed" or request.response_payload is None:
        raise IdempotencyConflict("An operation with this idempotency key is still in progress.")
    return request, request.response_payload
