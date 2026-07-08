import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ui import UISavedView

router = APIRouter(prefix="/ui", tags=["ui"])


def saved_view_to_dict(row: UISavedView) -> dict:
    return {
        "id": row.id,
        "view_key": row.view_key,
        "name": row.name,
        "page": row.page,
        "filters": json.loads(row.filters_json or "{}"),
        "columns": json.loads(row.columns_json or "[]"),
        "sort": json.loads(row.sort_json or "null"),
        "is_default": row.is_default,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/saved-views")
def list_saved_views(page: str | None = None, db: Session = Depends(get_db)) -> dict:
    statement = select(UISavedView).order_by(UISavedView.is_default.desc(), UISavedView.name.asc())
    if page:
        statement = statement.where(UISavedView.page == page)
    rows = list(db.scalars(statement).all())
    return {"views": [saved_view_to_dict(row) for row in rows], "total": len(rows)}


@router.post("/saved-views", status_code=201)
def create_saved_view(payload: dict, db: Session = Depends(get_db)) -> dict:
    row = UISavedView(
        view_key=payload.get("view_key") or f"{payload.get('page') or 'items'}:{payload.get('name') or 'view'}",
        name=payload.get("name") or "Saved view",
        page=payload.get("page") or "items",
        filters_json=json.dumps(payload.get("filters") or payload.get("filters_json") or {}),
        columns_json=json.dumps(payload.get("columns") or payload.get("columns_json") or []),
        sort_json=json.dumps(payload.get("sort") if "sort" in payload else payload.get("sort_json")),
        is_default=bool(payload.get("is_default")),
        created_by=payload.get("created_by"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return saved_view_to_dict(row)


@router.patch("/saved-views/{view_id}")
def update_saved_view(view_id: int, payload: dict, db: Session = Depends(get_db)) -> dict:
    row = db.get(UISavedView, view_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    for field in ["view_key", "name", "page", "is_default", "created_by"]:
        if field in payload:
            setattr(row, field, payload[field])
    if "filters" in payload:
        row.filters_json = json.dumps(payload["filters"])
    if "columns" in payload:
        row.columns_json = json.dumps(payload["columns"])
    if "sort" in payload:
        row.sort_json = json.dumps(payload["sort"])
    db.commit()
    db.refresh(row)
    return saved_view_to_dict(row)


@router.delete("/saved-views/{view_id}")
def delete_saved_view(view_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(UISavedView, view_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Saved view not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": view_id}
