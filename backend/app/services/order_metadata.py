from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.order_metadata import OrderNote, OrderTag, OrderTagAssignment
from app.models.orders import Order
from app.schemas.orders import (
    OrderNoteCreate,
    OrderNoteListResponse,
    OrderNoteRead,
    OrderTagCreate,
    OrderTagListResponse,
    OrderTagRead,
    OrderTagsRead,
    OrderTagsUpdate,
)
from app.services.stock_mutation_guard import begin_stock_mutation, complete_stock_mutation


class OrderMetadataNotFound(ValueError):
    pass


def note_to_read(note: OrderNote) -> OrderNoteRead:
    return OrderNoteRead(
        id=note.id,
        order_id=note.order_id,
        note=note.note,
        note_type=note.note_type,
        created_by=note.created_by,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def tag_to_read(tag: OrderTag) -> OrderTagRead:
    return OrderTagRead(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        created_by=tag.created_by,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
    )


def order_metadata_fields(order: Order) -> dict:
    notes = sorted(order.notes, key=lambda row: (row.created_at, row.id), reverse=True)
    assignments = sorted(order.tag_assignments, key=lambda row: (row.position, row.tag_id))
    tags = [tag_to_read(assignment.tag) for assignment in assignments]
    highlighted = assignments[0] if assignments and assignments[0].position == 0 else None
    return {
        "tags": tags,
        "highlight_tag_id": highlighted.tag_id if highlighted else None,
        "highlight_color": highlighted.tag.color if highlighted else None,
        "note_count": len(notes),
        "latest_note": note_to_read(notes[0]) if notes else None,
    }


def list_order_notes(db: Session, order_id: int) -> OrderNoteListResponse:
    require_order(db, order_id)
    notes = list(
        db.scalars(
            select(OrderNote)
            .where(OrderNote.order_id == order_id)
            .order_by(OrderNote.created_at.desc(), OrderNote.id.desc())
        ).all()
    )
    return OrderNoteListResponse(notes=[note_to_read(note) for note in notes], total=len(notes))


def create_order_note(
    db: Session,
    order_id: int,
    payload: OrderNoteCreate,
    *,
    actor: str,
) -> OrderNoteRead:
    mutation_payload = {
        "order_id": order_id,
        "note": payload.note,
        "actor": actor,
        "idempotency_key": payload.idempotency_key,
    }
    mutation, replay = begin_stock_mutation(
        db,
        "create_order_note",
        payload.idempotency_key,
        mutation_payload,
    )
    if replay is not None:
        return OrderNoteRead.model_validate(replay)
    require_order(db, order_id, lock=True)
    note = add_order_note(db, order_id, payload.note, note_type="manual", created_by=actor)
    db.flush()
    response = note_to_read(note)
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def add_order_note(
    db: Session,
    order_id: int,
    note: str,
    *,
    note_type: str,
    created_by: str,
) -> OrderNote:
    row = OrderNote(
        order_id=order_id,
        note=note,
        note_type=note_type,
        created_by=created_by,
    )
    db.add(row)
    return row


def list_order_tags(db: Session) -> OrderTagListResponse:
    tags = list(db.scalars(select(OrderTag).order_by(OrderTag.name.asc(), OrderTag.id.asc())).all())
    return OrderTagListResponse(tags=[tag_to_read(tag) for tag in tags], total=len(tags))


def create_order_tag(db: Session, payload: OrderTagCreate, *, actor: str) -> OrderTagRead:
    tag = OrderTag(
        name=payload.name,
        normalized_name=normalize_tag_name(payload.name),
        color=payload.color,
        created_by=actor,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag_to_read(tag)


def replace_order_tags(
    db: Session,
    order_id: int,
    payload: OrderTagsUpdate,
    *,
    actor: str,
) -> OrderTagsRead:
    require_order(db, order_id, lock=True)
    tags_by_id = {
        tag.id: tag
        for tag in db.scalars(select(OrderTag).where(OrderTag.id.in_(payload.tag_ids))).all()
    } if payload.tag_ids else {}
    missing_ids = [tag_id for tag_id in payload.tag_ids if tag_id not in tags_by_id]
    if missing_ids:
        raise OrderMetadataNotFound(f"Order tag {missing_ids[0]} was not found.")

    ordered_ids = list(payload.tag_ids)
    if payload.highlight_tag_id is not None:
        ordered_ids.remove(payload.highlight_tag_id)
        ordered_ids.insert(0, payload.highlight_tag_id)

    db.execute(delete(OrderTagAssignment).where(OrderTagAssignment.order_id == order_id))
    now = datetime.now(timezone.utc)
    first_position = 0 if payload.highlight_tag_id is not None else 1
    for position, tag_id in enumerate(ordered_ids, start=first_position):
        db.add(
            OrderTagAssignment(
                order_id=order_id,
                tag_id=tag_id,
                position=position,
                assigned_by=actor,
                created_at=now,
            )
        )
    db.commit()
    tags = [tag_to_read(tags_by_id[tag_id]) for tag_id in ordered_ids]
    return OrderTagsRead(
        tags=tags,
        highlight_tag_id=payload.highlight_tag_id,
        highlight_color=(tags_by_id[payload.highlight_tag_id].color if payload.highlight_tag_id else None),
    )


def require_order(db: Session, order_id: int, *, lock: bool = False) -> Order:
    statement = select(Order).where(Order.id == order_id, Order.is_historical_snapshot.is_(False))
    if lock:
        statement = statement.with_for_update()
    order = db.scalars(statement).one_or_none()
    if order is None:
        raise OrderMetadataNotFound("Order not found.")
    return order


def metadata_load_options():
    return (
        selectinload(Order.notes),
        selectinload(Order.tag_assignments).selectinload(OrderTagAssignment.tag),
    )


def normalize_tag_name(value: str) -> str:
    return " ".join(value.split()).casefold()
