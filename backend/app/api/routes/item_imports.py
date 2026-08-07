from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.auth import authenticated_actor
from app.services.item_import_workflow import (
    SCHEMA_VERSION,
    cancel_preview,
    commit_preview,
    create_mapping_profile,
    create_preview,
    delete_mapping_profile,
    get_preview,
    list_mapping_profiles,
    mapping_profile_dict,
    preview_detail,
    preview_row_dict,
    preview_rows_page,
    revalidate_preview,
    schema_document,
    template_csv,
    update_mapping,
    update_mapping_profile,
    update_preview_row,
)

router = APIRouter(prefix="/items/import", tags=["item-imports"])


class MappingUpdate(BaseModel):
    mapping: dict[str, str | None]
    allow_blank_clears: bool = False
    mapping_profile_id: int | None = None


class PreviewRowUpdate(BaseModel):
    values: dict[str, Any] | None = None
    excluded: bool | None = None


class CommitRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)


class MappingProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    outcome: str
    source_headers: list[str]
    mapping: dict[str, str | None]


class MappingProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    mapping: dict[str, str | None] | None = None


@router.get("/schema")
def get_import_schema(response: Response) -> dict[str, Any]:
    response.headers["X-Import-Schema-Version"] = SCHEMA_VERSION
    return schema_document()


@router.get("/templates/{outcome}")
def download_template(outcome: str, include_existing: bool = Query(False), db: Session = Depends(get_db)) -> Response:
    content = template_csv(outcome, db, include_existing=include_existing)
    suffix = "-existing" if include_existing and outcome == "update_items" else ""
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="pongo-{outcome.replace("_", "-")}{suffix}.csv"',
            "X-Import-Schema-Version": SCHEMA_VERSION,
        },
    )


@router.get("/profiles")
def get_mapping_profiles(outcome: str | None = Query(None), db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> list[dict[str, Any]]:
    return list_mapping_profiles(db, actor, outcome=outcome)


@router.post("/profiles", status_code=201)
def post_mapping_profile(payload: MappingProfileCreate, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    profile = create_mapping_profile(db, actor, name=payload.name, outcome=payload.outcome, source_headers=payload.source_headers, mapping=payload.mapping)
    return mapping_profile_dict(profile)


@router.patch("/profiles/{profile_id}")
def patch_mapping_profile(profile_id: int, payload: MappingProfileUpdate, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    profile = update_mapping_profile(db, actor, profile_id, payload.model_dump(exclude_none=True))
    return mapping_profile_dict(profile)


@router.delete("/profiles/{profile_id}", status_code=204)
def remove_mapping_profile(profile_id: int, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> Response:
    delete_mapping_profile(db, actor, profile_id)
    return Response(status_code=204)


@router.post("/previews", status_code=201)
async def post_preview(
    outcome: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict[str, Any]:
    preview = await create_preview(file, outcome, db, actor=actor)
    return preview_detail(preview, db)


@router.get("/previews/{preview_id}")
def get_preview_detail(preview_id: str, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    return preview_detail(get_preview(db, preview_id, actor), db)


@router.get("/previews/{preview_id}/rows")
def get_preview_rows(
    preview_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    state: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict[str, Any]:
    return preview_rows_page(get_preview(db, preview_id, actor), db, page=page, page_size=page_size, state=state, search=search)


@router.patch("/previews/{preview_id}/mapping")
def patch_preview_mapping(preview_id: str, payload: MappingUpdate, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    preview = update_mapping(get_preview(db, preview_id, actor), db, payload.mapping, allow_blank_clears=payload.allow_blank_clears, mapping_profile_id=payload.mapping_profile_id)
    return preview_detail(preview, db)


@router.patch("/previews/{preview_id}/rows/{row_number}")
def patch_preview_row(preview_id: str, row_number: int, payload: PreviewRowUpdate, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    row = update_preview_row(get_preview(db, preview_id, actor), row_number, db, values=payload.values, excluded=payload.excluded)
    return preview_row_dict(row)


@router.post("/previews/{preview_id}/revalidate")
def post_revalidate(preview_id: str, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    preview = get_preview(db, preview_id, actor)
    revalidate_preview(preview, db)
    db.commit()
    db.refresh(preview)
    return preview_detail(preview, db)


@router.post("/previews/{preview_id}/commit")
def post_commit(preview_id: str, payload: CommitRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    return commit_preview(get_preview(db, preview_id, actor), db, actor=actor, idempotency_key=payload.idempotency_key)


@router.post("/previews/{preview_id}/cancel")
def post_cancel(preview_id: str, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, Any]:
    preview = cancel_preview(get_preview(db, preview_id, actor), db)
    return preview_detail(preview, db)
