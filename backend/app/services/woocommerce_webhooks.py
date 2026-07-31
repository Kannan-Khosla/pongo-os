from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.orders import Order
from app.models.woocommerce import WooCommerceOrderEvent, WooCommerceWebhookDelivery
from app.schemas.woocommerce import (
    WooCommerceWebhookDeliveryResponse,
    WooCommerceWebhookEventListResponse,
    WooCommerceWebhookEventRead,
)
from app.services.woocommerce_orders import (
    RETIRED_WOO_LINE_STATUS,
    acquire_order_import_transaction_lock,
    commit_remote_order_records,
)

PING_PATTERN = re.compile(rb"webhook_id=([1-9][0-9]{0,19})")
SUPPORTED_ORDER_TOPICS = {"order.created", "order.updated"}
TERMINAL_DELIVERY_STATUSES = {"processed", "processed_with_errors", "ignored"}


class WooCommerceWebhookError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def webhook_source_host(settings: Any) -> str:
    allowed_host = str(getattr(settings, "woocommerce_allowed_host", "") or "").strip()
    return normalize_host(allowed_host) if allowed_host else ""


def webhook_secret(settings: Any) -> str:
    return str(getattr(settings, "woocommerce_webhook_secret", "") or "")


def webhook_is_configured(settings: Any) -> bool:
    secret = webhook_secret(settings)
    return bool(
        getattr(settings, "woocommerce_webhook_enabled", False)
        and len(secret.encode("utf-8")) >= 32
        and webhook_source_host(settings)
    )


def validate_webhook_receiver_configuration(settings: Any) -> None:
    if not getattr(settings, "woocommerce_webhook_enabled", False):
        raise WooCommerceWebhookError(503, "WooCommerce webhook receiver is disabled.")
    if len(webhook_secret(settings).encode("utf-8")) < 32:
        raise WooCommerceWebhookError(503, "WooCommerce webhook receiver is not fully configured.")
    if not webhook_source_host(settings):
        raise WooCommerceWebhookError(503, "WooCommerce webhook source host is not configured.")


def is_woocommerce_webhook_ping(raw_body: bytes, headers: Mapping[str, str]) -> bool:
    if headers.get("x-wc-webhook-signature"):
        return False
    return PING_PATTERN.fullmatch(raw_body) is not None


def ping_response(raw_body: bytes) -> WooCommerceWebhookDeliveryResponse:
    match = PING_PATTERN.fullmatch(raw_body)
    webhook_id = match.group(1).decode("ascii") if match else None
    return WooCommerceWebhookDeliveryResponse(
        status="ready",
        message=f"WooCommerce webhook {webhook_id or ''} ping received; no order data was changed.".replace("  ", " "),
    )


def process_order_webhook(
    db: Session,
    settings: Any,
    raw_body: bytes,
    headers: Mapping[str, str],
    content_type: str,
) -> WooCommerceWebhookDeliveryResponse:
    validate_webhook_receiver_configuration(settings)
    validate_content_type(content_type)
    validate_signature(raw_body, headers.get("x-wc-webhook-signature", ""), webhook_secret(settings))

    topic = required_header(headers, "x-wc-webhook-topic", 120)
    resource = required_header(headers, "x-wc-webhook-resource", 80)
    event = required_header(headers, "x-wc-webhook-event", 80)
    webhook_id = required_header(headers, "x-wc-webhook-id", 80)
    delivery_id = required_header(headers, "x-wc-webhook-delivery-id", 191)
    source = required_header(headers, "x-wc-webhook-source", 500)
    validate_header_relationships(topic, resource, event, webhook_id)
    source_host = validate_source_host(source, webhook_source_host(settings))
    payload = decode_json_object(raw_body)
    payload_sha256 = hashlib.sha256(raw_body).hexdigest()

    if topic not in SUPPORTED_ORDER_TOPICS:
        existing = find_delivery(db, webhook_id, delivery_id, payload_sha256)
        if existing and existing.processing_status in TERMINAL_DELIVERY_STATUSES:
            existing.attempt_count += 1
            db.commit()
            return delivery_response(db, existing, duplicate=True)
        delivery = existing or WooCommerceWebhookDelivery(
            webhook_id=webhook_id,
            delivery_id=delivery_id,
            payload_sha256=payload_sha256,
            topic=topic,
            resource=resource,
            event=event,
            source_host=source_host,
            woo_order_id=positive_int_or_none(payload.get("id")),
        )
        if existing:
            delivery.attempt_count += 1
        delivery.processing_status = "ignored"
        delivery.error_message = "Only order.created and order.updated are enabled."
        delivery.processed_at = datetime.now(timezone.utc)
        db.add(delivery)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            duplicate = find_delivery(db, webhook_id, delivery_id, payload_sha256)
            if duplicate is None:
                raise
            return delivery_response(db, duplicate, duplicate=True)
        db.refresh(delivery)
        return delivery_response(db, delivery)

    woo_order_id = validate_order_payload(payload)
    acquire_order_import_transaction_lock(db)
    existing = find_delivery(db, webhook_id, delivery_id, payload_sha256, for_update=True)
    if existing and existing.processing_status in TERMINAL_DELIVERY_STATUSES:
        existing.attempt_count += 1
        db.commit()
        return delivery_response(db, existing, duplicate=True)
    existing_order = db.scalars(select(Order).where(Order.woo_order_id == woo_order_id)).one_or_none()
    if existing_order is not None and webhook_payload_is_stale(existing_order, payload):
        delivery = existing or WooCommerceWebhookDelivery(
            webhook_id=webhook_id,
            delivery_id=delivery_id,
            payload_sha256=payload_sha256,
            topic=topic,
            resource=resource,
            event=event,
            source_host=source_host,
            woo_order_id=woo_order_id,
        )
        if existing:
            delivery.attempt_count += 1
        delivery.local_order_id = existing_order.id
        delivery.processing_status = "ignored"
        delivery.error_message = f"Stale {topic} payload was ignored because newer local WooCommerce data already exists."
        delivery.processed_at = datetime.now(timezone.utc)
        db.add(delivery)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            duplicate = find_delivery(db, webhook_id, delivery_id, payload_sha256)
            if duplicate is None:
                raise
            return delivery_response(db, duplicate, duplicate=True)
        db.refresh(delivery)
        return delivery_response(db, delivery)

    delivery = existing or WooCommerceWebhookDelivery(
        webhook_id=webhook_id,
        delivery_id=delivery_id,
        payload_sha256=payload_sha256,
        topic=topic,
        resource=resource,
        event=event,
        source_host=source_host,
        woo_order_id=woo_order_id,
    )
    if existing:
        delivery.attempt_count += 1
        delivery.processing_status = "received"
        delivery.error_message = None
    db.add(delivery)

    try:
        db.flush()
        sync_run, summary = commit_remote_order_records(
            db,
            [payload],
            [str(payload["status"])],
            "woocommerce-webhook",
            commit=False,
        )
        local_order = db.scalars(
            select(Order).where(Order.woo_order_id == woo_order_id).options(selectinload(Order.items))
        ).one_or_none()
        expected_line_ids = [int(line["id"]) for line in payload["line_items"]]
        actual_line_ids = [
            line.woo_order_item_id
            for line in local_order.items
            if line.status != RETIRED_WOO_LINE_STATUS
        ] if local_order else []
        if local_order is None or len(actual_line_ids) != len(expected_line_ids) or set(actual_line_ids) != set(expected_line_ids):
            raise RuntimeError("Verified WooCommerce order payload was not imported completely.")
        delivery.local_order_id = local_order.id if local_order else None
        delivery.sync_run_id = sync_run.id
        delivery.created_order = summary.create_count > 0
        delivery.processing_status = "processed_with_errors" if summary.error_count or summary.conflict_count else "processed"
        delivery.error_message = " ".join((summary.errors or summary.warnings)[:3])[:1000] or None
        delivery.processed_at = datetime.now(timezone.utc)
        db.add(
            WooCommerceOrderEvent(
                webhook_delivery_id=delivery.id,
                local_order_id=local_order.id,
                woo_order_id=woo_order_id,
                event_type=topic.replace(".", "_"),
            )
        )
        db.flush()
        db.commit()
        db.refresh(delivery)
        return delivery_response(db, delivery)
    except IntegrityError:
        db.rollback()
        duplicate = find_delivery(db, webhook_id, delivery_id, payload_sha256)
        if duplicate and duplicate.processing_status in TERMINAL_DELIVERY_STATUSES:
            return delivery_response(db, duplicate, duplicate=True)
        raise WooCommerceWebhookError(503, "WooCommerce webhook import could not be committed.") from None
    except WooCommerceWebhookError:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        record_failed_delivery(
            db,
            webhook_id=webhook_id,
            delivery_id=delivery_id,
            payload_sha256=payload_sha256,
            topic=topic,
            resource=resource,
            event=event,
            source_host=source_host,
            woo_order_id=woo_order_id,
            error_message=str(error),
        )
        raise WooCommerceWebhookError(503, "WooCommerce webhook order import failed.") from None


def list_webhook_events(db: Session, after_id: int = 0, limit: int = 50, initialize: bool = False) -> WooCommerceWebhookEventListResponse:
    # The staff cursor remains new-order-only; update events stay in the durable
    # audit table without being presented as new-order notifications.
    acquire_order_import_transaction_lock(db)
    latest_event_id = int(
        db.scalar(
            select(func.coalesce(func.max(WooCommerceOrderEvent.id), 0)).where(
                WooCommerceOrderEvent.event_type == "order_created"
            )
        )
        or 0
    )
    if initialize:
        return WooCommerceWebhookEventListResponse(
            events=[],
            latest_event_id=latest_event_id,
            next_after_id=latest_event_id,
            has_more=False,
        )
    page_size = max(1, min(limit, 100))
    statement = (
        select(WooCommerceOrderEvent, WooCommerceWebhookDelivery, Order)
        .join(WooCommerceWebhookDelivery, WooCommerceWebhookDelivery.id == WooCommerceOrderEvent.webhook_delivery_id)
        .join(Order, Order.id == WooCommerceOrderEvent.local_order_id)
        .where(
            WooCommerceOrderEvent.id > max(after_id, 0),
            WooCommerceOrderEvent.event_type == "order_created",
        )
        .order_by(WooCommerceOrderEvent.id.asc())
        .limit(page_size + 1)
    )
    rows = db.execute(statement).all()
    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    events = []
    for order_event, delivery, order in visible_rows:
        events.append(
            WooCommerceWebhookEventRead(
                id=order_event.id,
                topic=delivery.topic,
                event_type=order_event.event_type,
                woo_order_id=delivery.woo_order_id,
                local_order_id=delivery.local_order_id,
                woo_order_number=order.woo_order_number if order else None,
                woo_status=order.woo_status if order else None,
                local_status=order.local_status if order else None,
                customer_name=order.customer_name if order else None,
                currency=order.currency if order else None,
                total=float(order.total) if order and order.total is not None else None,
                created_order=delivery.created_order,
                received_at=delivery.received_at,
            )
        )
    if has_more and visible_rows:
        next_after_id = visible_rows[-1][0].id
    else:
        next_after_id = max(after_id, latest_event_id)
    return WooCommerceWebhookEventListResponse(
        events=events,
        latest_event_id=max(after_id, latest_event_id),
        next_after_id=next_after_id,
        has_more=has_more,
    )


def validate_content_type(content_type: str) -> None:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise WooCommerceWebhookError(415, "WooCommerce webhook deliveries must use application/json.")


def validate_signature(raw_body: bytes, supplied_signature: str, secret: str) -> None:
    if not supplied_signature or len(supplied_signature) > 512:
        raise WooCommerceWebhookError(401, "WooCommerce webhook signature is missing or invalid.")
    expected = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("ascii")
    if not hmac.compare_digest(expected, supplied_signature.strip()):
        raise WooCommerceWebhookError(401, "WooCommerce webhook signature is missing or invalid.")


def required_header(headers: Mapping[str, str], name: str, max_length: int) -> str:
    value = str(headers.get(name, "") or "").strip()
    if not value or len(value) > max_length:
        raise WooCommerceWebhookError(400, f"Required WooCommerce webhook header {name} is missing or invalid.")
    return value


def validate_header_relationships(topic: str, resource: str, event: str, webhook_id: str) -> None:
    if not webhook_id.isdigit() or int(webhook_id) <= 0:
        raise WooCommerceWebhookError(400, "WooCommerce webhook ID is invalid.")
    topic_parts = topic.split(".", 1)
    if len(topic_parts) != 2 or topic_parts[0] != resource or topic_parts[1] != event:
        raise WooCommerceWebhookError(400, "WooCommerce webhook topic, resource, and event headers do not match.")


def validate_source_host(source: str, expected_host: str) -> str:
    parsed_source = urlparse(source)
    source_host = normalize_host(parsed_source.hostname or "")
    if parsed_source.scheme not in {"http", "https"} or not source_host or source_host != normalize_host(expected_host):
        raise WooCommerceWebhookError(403, "WooCommerce webhook source host is not allowed.")
    return source_host


def decode_json_object(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise WooCommerceWebhookError(400, "WooCommerce webhook body is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise WooCommerceWebhookError(422, "WooCommerce webhook body must be a JSON object.")
    return payload


def validate_order_payload(payload: dict[str, Any]) -> int:
    woo_order_id = positive_int_or_none(payload.get("id"))
    if woo_order_id is None:
        raise WooCommerceWebhookError(422, "WooCommerce order payload has an invalid order ID.")
    if not isinstance(payload.get("status"), str) or not str(payload["status"]).strip():
        raise WooCommerceWebhookError(422, "WooCommerce order payload has an invalid status.")
    if not isinstance(payload.get("line_items"), list):
        raise WooCommerceWebhookError(422, "WooCommerce order payload has invalid line items.")
    if any(not isinstance(line, dict) or positive_int_or_none(line.get("id")) is None for line in payload["line_items"]):
        raise WooCommerceWebhookError(422, "WooCommerce order payload contains an invalid line item ID.")
    return woo_order_id


def positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_host(value: str) -> str:
    return value.strip().rstrip(".").lower()


def parse_webhook_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text_value = str(value)
        if text_value.endswith("Z"):
            text_value = text_value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def webhook_payload_is_stale(existing_order: Order, payload: dict[str, Any]) -> bool:
    existing_modified = existing_order.date_modified
    if existing_modified is None:
        return False
    if existing_modified.tzinfo is None:
        existing_modified = existing_modified.replace(tzinfo=timezone.utc)
    else:
        existing_modified = existing_modified.astimezone(timezone.utc)
    incoming_modified = parse_webhook_datetime(payload.get("date_modified_gmt") or payload.get("date_modified"))
    return incoming_modified is None or incoming_modified <= existing_modified


def find_delivery(db: Session, webhook_id: str, delivery_id: str, payload_sha256: str, *, for_update: bool = False) -> WooCommerceWebhookDelivery | None:
    statement = select(WooCommerceWebhookDelivery).where(
        WooCommerceWebhookDelivery.webhook_id == webhook_id,
        WooCommerceWebhookDelivery.delivery_id == delivery_id,
        WooCommerceWebhookDelivery.payload_sha256 == payload_sha256,
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalars(statement).one_or_none()


def delivery_response(db: Session, delivery: WooCommerceWebhookDelivery, duplicate: bool = False) -> WooCommerceWebhookDeliveryResponse:
    status = "duplicate" if duplicate else delivery.processing_status
    if duplicate:
        message = "WooCommerce webhook delivery was already processed."
    elif delivery.processing_status == "ignored":
        message = delivery.error_message or "WooCommerce webhook delivery was authenticated but ignored."
    else:
        message = "WooCommerce order webhook was imported into Pongo OS."
    order_event_id = db.scalar(
        select(WooCommerceOrderEvent.id).where(WooCommerceOrderEvent.webhook_delivery_id == delivery.id)
    ) if delivery.id is not None else None
    return WooCommerceWebhookDeliveryResponse(
        status=status,
        duplicate=duplicate,
        delivery_id=delivery.delivery_id,
        event_id=order_event_id,
        woo_order_id=delivery.woo_order_id,
        local_order_id=delivery.local_order_id,
        sync_run_id=delivery.sync_run_id,
        created_order=delivery.created_order,
        message=message,
    )


def record_failed_delivery(db: Session, **values: Any) -> None:
    safe_error = str(values.pop("error_message", "Webhook import failed."))[:1000]
    delivery = find_delivery(db, values["webhook_id"], values["delivery_id"], values["payload_sha256"], for_update=True)
    if delivery is not None and delivery.processing_status in TERMINAL_DELIVERY_STATUSES:
        db.rollback()
        return
    if delivery is None:
        delivery = WooCommerceWebhookDelivery(**values)
    else:
        delivery.attempt_count += 1
    delivery.processing_status = "failed"
    delivery.error_message = safe_error
    delivery.processed_at = datetime.now(timezone.utc)
    db.add(delivery)
    try:
        db.commit()
    except Exception:
        db.rollback()
