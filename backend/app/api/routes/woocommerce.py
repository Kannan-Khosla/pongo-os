from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.woocommerce import WooCommerceSyncRun
from app.schemas.woocommerce import (
    WooRemapCandidateListResponse,
    WooRemapCommitRequest,
    WooRemapCommitResponse,
    WooRemapDeactivateRequest,
    WooRemapMappingListResponse,
    WooRemapMappingRead,
    WooRemapPreviewRequest,
    WooRemapPreviewResponse,
    WooCommerceOrderCommitResponse,
    WooCommerceOrderPreviewResponse,
    WooCommerceOrderSyncRequest,
    WooCommerceProductCommitResponse,
    WooCommerceProductPreviewResponse,
    WooCommerceStatusResponse,
    WooCommerceSyncErrorRead,
    WooCommerceSyncRequest,
    WooCommerceSyncRunDetail,
    WooCommerceSyncRunListResponse,
    WooCommerceSyncRunRead,
)
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_orders import commit_order_sync, preview_order_sync
from app.services.woocommerce_remap import commit_remap, deactivate_mapping, list_mappings, list_remap_candidates, mapping_to_read, preview_remap
from app.services.woocommerce_sync import commit_product_sync, preview_product_sync

router = APIRouter(prefix="/integrations/woocommerce", tags=["woocommerce"])


def create_woocommerce_client() -> WooCommerceClient:
    return WooCommerceClient(get_settings())


@router.get("/status", response_model=WooCommerceStatusResponse)
def woocommerce_status(check: bool = False) -> WooCommerceStatusResponse:
    settings = get_settings()
    client = create_woocommerce_client()
    base_url_present = bool(settings.woocommerce_base_url)
    consumer_key_present = bool(settings.woocommerce_consumer_key)
    consumer_secret_present = bool(settings.woocommerce_consumer_secret)
    configured = base_url_present and consumer_key_present and consumer_secret_present
    if not configured:
        return WooCommerceStatusResponse(
            configured=False,
            base_url_present=base_url_present,
            consumer_key_present=consumer_key_present,
            consumer_secret_present=consumer_secret_present,
            message="WooCommerce credentials are not fully configured.",
        )
    if check:
        try:
            client.check_connection()
        except WooCommerceClientError as error:
            return WooCommerceStatusResponse(
                configured=True,
                base_url_present=True,
                consumer_key_present=True,
                consumer_secret_present=True,
                message=f"Configured, but read-only connection check failed: {error.message}",
            )
        return WooCommerceStatusResponse(configured=True, base_url_present=True, consumer_key_present=True, consumer_secret_present=True, message="Configured and read-only connection check succeeded.")
    return WooCommerceStatusResponse(configured=True, base_url_present=True, consumer_key_present=True, consumer_secret_present=True, message="WooCommerce sync is configured.")


@router.post("/products/preview", response_model=WooCommerceProductPreviewResponse)
def preview_woocommerce_products(payload: WooCommerceSyncRequest | None = None, db: Session = Depends(get_db)) -> WooCommerceProductPreviewResponse:
    return preview_product_sync(db, create_woocommerce_client(), payload or WooCommerceSyncRequest())


@router.post("/products/commit", response_model=WooCommerceProductCommitResponse)
def commit_woocommerce_products(payload: WooCommerceSyncRequest | None = None, db: Session = Depends(get_db)) -> WooCommerceProductCommitResponse:
    sync_run, summary = commit_product_sync(db, create_woocommerce_client(), payload or WooCommerceSyncRequest())
    return WooCommerceProductCommitResponse(
        sync_run_id=sync_run.id if sync_run else None,
        status=sync_run.status if sync_run else "not_configured",
        total_remote_records=summary.total_remote_records,
        created_count=summary.create_count,
        updated_count=summary.update_count,
        matched_count=summary.matched_count,
        skipped_count=summary.skipped_count,
        conflict_count=summary.conflict_count,
        error_count=summary.error_count,
        warnings=summary.warnings,
        errors=summary.errors,
    )


@router.post("/orders/preview", response_model=WooCommerceOrderPreviewResponse)
def preview_woocommerce_orders(payload: WooCommerceOrderSyncRequest | None = None, db: Session = Depends(get_db)) -> WooCommerceOrderPreviewResponse:
    return preview_order_sync(db, create_woocommerce_client(), payload or WooCommerceOrderSyncRequest())


@router.post("/orders/commit", response_model=WooCommerceOrderCommitResponse)
def commit_woocommerce_orders(payload: WooCommerceOrderSyncRequest | None = None, db: Session = Depends(get_db)) -> WooCommerceOrderCommitResponse:
    sync_run, summary = commit_order_sync(db, create_woocommerce_client(), payload or WooCommerceOrderSyncRequest())
    return WooCommerceOrderCommitResponse(
        sync_run_id=sync_run.id if sync_run else None,
        status=sync_run.status if sync_run else "not_configured",
        total_remote_records=summary.total_remote_records,
        created_count=summary.create_count,
        updated_count=summary.update_count,
        matched_count=summary.matched_count,
        skipped_count=summary.skipped_count,
        conflict_count=summary.conflict_count,
        error_count=summary.error_count,
        available_count=summary.available_count,
        partial_count=summary.partial_count,
        unavailable_count=summary.unavailable_count,
        unknown_count=summary.unknown_count,
        warnings=summary.warnings,
        errors=summary.errors,
    )


@router.get("/sync-runs", response_model=WooCommerceSyncRunListResponse)
def list_sync_runs(
    sync_type: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> WooCommerceSyncRunListResponse:
    statement = select(WooCommerceSyncRun).order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
    if sync_type:
        statement = statement.where(WooCommerceSyncRun.sync_type == sync_type)
    if status:
        statement = statement.where(WooCommerceSyncRun.status == status)
    if date_from:
        statement = statement.where(WooCommerceSyncRun.started_at >= date_from)
    if date_to:
        statement = statement.where(WooCommerceSyncRun.started_at <= date_to)
    runs = list(db.scalars(statement).all())
    return WooCommerceSyncRunListResponse(sync_runs=[sync_run_to_read(run) for run in runs], total=len(runs))


@router.get("/sync-runs/{sync_run_id}", response_model=WooCommerceSyncRunDetail)
def get_sync_run(sync_run_id: int, db: Session = Depends(get_db)) -> WooCommerceSyncRunDetail:
    run = db.scalars(select(WooCommerceSyncRun).where(WooCommerceSyncRun.id == sync_run_id).options(selectinload(WooCommerceSyncRun.errors))).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="WooCommerce sync run not found")
    base = sync_run_to_read(run).model_dump()
    base["errors"] = [
        WooCommerceSyncErrorRead(
            id=error.id,
            remote_order_id=error.remote_order_id,
            remote_line_item_id=error.remote_line_item_id,
            remote_product_id=error.remote_product_id,
            remote_variation_id=error.remote_variation_id,
            sku=error.sku,
            barcode=error.barcode,
            error_message=error.error_message,
            raw_payload=error.raw_payload,
            created_at=error.created_at,
        )
        for error in run.errors
    ]
    return WooCommerceSyncRunDetail.model_validate(base)


@router.get("/remap/candidates", response_model=WooRemapCandidateListResponse)
def remap_candidates(search: str | None = None, limit: int = 100, db: Session = Depends(get_db)) -> WooRemapCandidateListResponse:
    return list_remap_candidates(db, search=search, limit=limit)


@router.post("/remap/preview", response_model=WooRemapPreviewResponse)
def remap_preview(payload: WooRemapPreviewRequest, db: Session = Depends(get_db)) -> WooRemapPreviewResponse:
    result = preview_remap(db, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Local item not found")
    return result


@router.post("/remap/commit", response_model=WooRemapCommitResponse)
def remap_commit(payload: WooRemapCommitRequest, db: Session = Depends(get_db)) -> WooRemapCommitResponse:
    result = commit_remap(db, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Local item not found")
    return result


@router.get("/remap/mappings", response_model=WooRemapMappingListResponse)
def remap_mappings(
    sku: str | None = None,
    item_id: int | None = None,
    woo_product_id: int | None = None,
    mapping_source: str | None = None,
    active: bool | None = True,
    db: Session = Depends(get_db),
) -> WooRemapMappingListResponse:
    return list_mappings(db, sku=sku, item_id=item_id, woo_product_id=woo_product_id, mapping_source=mapping_source, active=active)


@router.post("/remap/deactivate", response_model=WooRemapMappingRead)
def remap_deactivate(payload: WooRemapDeactivateRequest, db: Session = Depends(get_db)) -> WooRemapMappingRead:
    mapping = deactivate_mapping(db, payload.mapping_id, payload.note)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return mapping_to_read(mapping)


def sync_run_to_read(run: WooCommerceSyncRun) -> WooCommerceSyncRunRead:
    return WooCommerceSyncRunRead(
        id=run.id,
        sync_type=run.sync_type,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_by=run.created_by,
        total_remote_records=run.total_remote_records,
        created_count=run.created_count,
        updated_count=run.updated_count,
        matched_count=run.matched_count,
        skipped_count=run.skipped_count,
        conflict_count=run.conflict_count,
        error_count=run.error_count,
        notes=run.notes,
    )
