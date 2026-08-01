import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models.woocommerce import WooCommerceSyncError, WooCommerceSyncRun, WooCommerceWebhookDelivery
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
    WooCommerceAccessModeRequest,
    WooCommerceAccessModeResponse,
    WooCommerceConfigurationRequest,
    WooCommerceConfigurationResponse,
    WooCommerceProductCommitResponse,
    WooCommerceProductPreviewResponse,
    WooCommerceStatusResponse,
    WooCommerceSyncErrorRead,
    WooCommerceSyncRequest,
    WooCommerceSyncRunDetail,
    WooCommerceSyncRunListResponse,
    WooCommerceSyncRunRead,
    WooCommerceWebhookDeliveryResponse,
    WooCommerceWebhookEventListResponse,
    WooWritebackOrderStatusPreviewRequest,
    WooWritebackPreviewResponse,
    WooWritebackQueueCreateRequest,
    WooWritebackQueueListResponse,
    WooWritebackQueueRead,
    WooStockSyncRequest,
    WooStockSyncJobListResponse,
    WooStockSyncJobRead,
    WooWritebackStockPreviewRequest,
)
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.auth import authenticated_actor
from app.services.woocommerce_access import change_access_mode, effective_woocommerce_settings, latest_access_mode_change
from app.services.woocommerce_configuration import latest_woocommerce_configuration, save_woocommerce_configuration
from app.services.woocommerce_orders import commit_order_sync, commit_recent_order_sync, preview_order_sync
from app.services.woocommerce_order_reconciliation import reconciliation_health
from app.services.woocommerce_remap import commit_remap, deactivate_mapping, list_mappings, list_remap_candidates, mapping_to_read, preview_remap
from app.services.woocommerce_sync import commit_product_sync, preview_product_sync
from app.services.woocommerce_webhooks import (
    WooCommerceWebhookError,
    is_woocommerce_webhook_ping,
    list_webhook_events,
    ping_response,
    process_order_webhook,
    validate_webhook_receiver_configuration,
    webhook_is_configured,
)
from app.services.woocommerce_writeback import (
    approve_queue_item,
    cancel_queue_item,
    create_queue_item,
    get_queue_item,
    list_queue,
    preview_order_status_writeback,
    preview_stock_writeback,
    queue_to_read,
    revalidate_queue_item,
    send_queue_item,
)
from app.services.woocommerce_stock_sync_jobs import cancel_stock_sync_job, create_stock_sync_job, list_stock_sync_jobs, resume_stock_sync_job, stock_sync_job_read

router = APIRouter(prefix="/integrations/woocommerce", tags=["woocommerce"])
logger = logging.getLogger(__name__)


def create_woocommerce_client() -> WooCommerceClient:
    with SessionLocal() as db:
        return WooCommerceClient(effective_woocommerce_settings(db, get_settings()))


def initial_order_sync(settings, actor: str) -> None:
    try:
        with SessionLocal() as db:
            commit_recent_order_sync(
                db,
                WooCommerceClient(settings),
                WooCommerceOrderSyncRequest(limit=75, created_by=f"{actor}:configuration"[:120]),
                per_status_limit=25,
            )
    except Exception:
        logger.exception("Initial WooCommerce open-order sync failed after saving configuration.")


@router.post("/access-mode", response_model=WooCommerceAccessModeResponse)
def update_woocommerce_access_mode(
    payload: WooCommerceAccessModeRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> WooCommerceAccessModeResponse:
    try:
        row = change_access_mode(db, payload.access_mode, actor)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    label = "Read & write" if row.access_mode == "read_write" else "Read only"
    return WooCommerceAccessModeResponse(
        access_mode=row.access_mode,
        changed_by=row.changed_by,
        changed_at=row.created_at,
        message=f"WooCommerce access changed to {label}.",
    )


@router.post("/configuration", response_model=WooCommerceConfigurationResponse)
def configure_woocommerce(
    payload: WooCommerceConfigurationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> WooCommerceConfigurationResponse:
    try:
        settings = save_woocommerce_configuration(
            payload.base_url,
            payload.consumer_key,
            payload.consumer_secret,
            allow_host_change=payload.allow_host_change,
            db=db,
            changed_by=actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except WooCommerceClientError as error:
        raise HTTPException(status_code=400, detail=f"WooCommerce connection failed: {error.message}") from error
    background_tasks.add_task(initial_order_sync, settings, actor)
    client = WooCommerceClient(settings)
    return WooCommerceConfigurationResponse(
        connected=True,
        base_url=settings.woocommerce_base_url,
        base_url_host=client.base_url_host or "",
        consumer_key_present=True,
        consumer_secret_present=True,
        message="WooCommerce credentials were verified and saved securely in Pongo. Initial open-order sync started.",
    )


@router.get("/status", response_model=WooCommerceStatusResponse)
def woocommerce_status(request: Request, check: bool = False, db: Session = Depends(get_db)) -> WooCommerceStatusResponse:
    settings = effective_woocommerce_settings(db, get_settings())
    client = WooCommerceClient(settings)
    base_url_present = bool(settings.woocommerce_base_url)
    consumer_key_present = bool(settings.woocommerce_consumer_key)
    consumer_secret_present = bool(settings.woocommerce_consumer_secret)
    configured = base_url_present and consumer_key_present and consumer_secret_present
    scheduler_task = getattr(request.app.state, "order_reconciliation_task", None)
    base_status = woo_status_payload(settings, client, db, scheduler_running=scheduler_task is not None and not scheduler_task.done())
    if not configured:
        return WooCommerceStatusResponse(
            **base_status,
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
            error_status = {**base_status, "last_error": error.message}
            return WooCommerceStatusResponse(
                **error_status,
                configured=True,
                base_url_present=True,
                consumer_key_present=True,
                consumer_secret_present=True,
                message=f"Configured, but WooCommerce connection check failed: {error.message}",
            )
        return WooCommerceStatusResponse(**base_status, configured=True, base_url_present=True, consumer_key_present=True, consumer_secret_present=True, message="Configured and staging connection check succeeded.")
    return WooCommerceStatusResponse(**base_status, configured=True, base_url_present=True, consumer_key_present=True, consumer_secret_present=True, message="WooCommerce sync is configured.")


@router.post("/products/preview", response_model=WooCommerceProductPreviewResponse)
def preview_woocommerce_products(payload: WooCommerceSyncRequest | None = None, db: Session = Depends(get_db)) -> WooCommerceProductPreviewResponse:
    return preview_product_sync(db, create_woocommerce_client(), payload or WooCommerceSyncRequest())


@router.post("/products/commit", response_model=WooCommerceProductCommitResponse)
def commit_woocommerce_products(payload: WooCommerceSyncRequest | None = None, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooCommerceProductCommitResponse:
    request_payload = (payload or WooCommerceSyncRequest()).model_copy(update={"created_by": actor})
    sync_run, summary = commit_product_sync(db, create_woocommerce_client(), request_payload)
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
        page=summary.page,
        next_page=summary.next_page,
        has_more=summary.has_more,
        unmatched_local_count=summary.unmatched_local_count,
        unmatched_local_skus=summary.unmatched_local_skus,
        unchanged_count=summary.unchanged_count,
    )


@router.post("/orders/preview", response_model=WooCommerceOrderPreviewResponse)
def preview_woocommerce_orders(payload: WooCommerceOrderSyncRequest | None = None, db: Session = Depends(get_db)) -> WooCommerceOrderPreviewResponse:
    return preview_order_sync(db, create_woocommerce_client(), payload or WooCommerceOrderSyncRequest())


@router.post("/orders/commit", response_model=WooCommerceOrderCommitResponse)
def commit_woocommerce_orders(payload: WooCommerceOrderSyncRequest | None = None, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooCommerceOrderCommitResponse:
    request_payload = (payload or WooCommerceOrderSyncRequest()).model_copy(update={"created_by": actor})
    sync_run, summary = commit_order_sync(db, create_woocommerce_client(), request_payload)
    return order_commit_response(sync_run, summary)


@router.post("/orders/quick-sync", response_model=WooCommerceOrderCommitResponse)
def quick_sync_woocommerce_orders(payload: WooCommerceOrderSyncRequest | None = None, per_status_limit: int = 10, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooCommerceOrderCommitResponse:
    request_payload = (payload or WooCommerceOrderSyncRequest(limit=50)).model_copy(update={"created_by": actor})
    sync_run, summary = commit_recent_order_sync(db, create_woocommerce_client(), request_payload, per_status_limit=max(1, min(per_status_limit, 25)))
    return order_commit_response(sync_run, summary)


@router.post("/webhooks/orders", response_model=WooCommerceWebhookDeliveryResponse)
async def receive_woocommerce_order_webhook(request: Request, db: Session = Depends(get_db)) -> WooCommerceWebhookDeliveryResponse:
    settings = effective_woocommerce_settings(db, get_settings())
    max_body_bytes = max(1, min(int(getattr(settings, "woocommerce_webhook_max_body_bytes", 1_048_576)), 10_485_760))
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_body_bytes:
        raise HTTPException(status_code=413, detail="WooCommerce webhook body is too large.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > max_body_bytes:
            raise HTTPException(status_code=413, detail="WooCommerce webhook body is too large.")
        body.extend(chunk)
    raw_body = bytes(body)
    try:
        validate_webhook_receiver_configuration(settings)
        if is_woocommerce_webhook_ping(raw_body, request.headers):
            return ping_response(raw_body)
        return process_order_webhook(db, settings, raw_body, request.headers, request.headers.get("content-type", ""))
    except WooCommerceWebhookError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from None


@router.get("/webhooks/events", response_model=WooCommerceWebhookEventListResponse)
def woo_order_webhook_events(after_id: int = 0, limit: int = 50, initialize: bool = False, db: Session = Depends(get_db)) -> WooCommerceWebhookEventListResponse:
    return list_webhook_events(db, after_id=max(after_id, 0), limit=limit, initialize=initialize)


def order_commit_response(sync_run: WooCommerceSyncRun | None, summary: WooCommerceOrderPreviewResponse) -> WooCommerceOrderCommitResponse:
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
        auto_allocated_count=summary.auto_allocated_count,
        allocation_exception_count=summary.allocation_exception_count,
        unmatched_line_count=summary.unmatched_line_count,
        conflict_line_count=summary.conflict_line_count,
        pick_ready_count=summary.pick_ready_count,
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
    try:
        result = commit_remap(db, payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
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


@router.post("/writeback/stock/preview", response_model=WooWritebackPreviewResponse)
def writeback_stock_preview(payload: WooWritebackStockPreviewRequest, db: Session = Depends(get_db)) -> WooWritebackPreviewResponse:
    try:
        settings = effective_woocommerce_settings(db, get_settings())
        result = preview_stock_writeback(db, settings, create_woocommerce_client(), payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Local item not found")
    return result


@router.post("/writeback/stock/sync", response_model=WooStockSyncJobRead, status_code=202)
def writeback_stock_sync(payload: WooStockSyncRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooStockSyncJobRead:
    try:
        return stock_sync_job_read(create_stock_sync_job(db, payload.model_copy(update={"requested_by": actor})))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/writeback/stock/jobs", response_model=WooStockSyncJobListResponse)
def writeback_stock_jobs(limit: int = 25, db: Session = Depends(get_db)) -> WooStockSyncJobListResponse:
    return list_stock_sync_jobs(db, max(1, min(limit, 100)))


@router.get("/writeback/stock/jobs/{job_id}", response_model=WooStockSyncJobRead)
def writeback_stock_job(job_id: int, db: Session = Depends(get_db)) -> WooStockSyncJobRead:
    from app.models.woocommerce import WooStockSyncJob

    job = db.get(WooStockSyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Stock sync job not found")
    return stock_sync_job_read(job)


@router.post("/writeback/stock/jobs/{job_id}/resume", response_model=WooStockSyncJobRead)
def writeback_stock_job_resume(job_id: int, db: Session = Depends(get_db)) -> WooStockSyncJobRead:
    try:
        job = resume_stock_sync_job(db, job_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Stock sync job not found")
    return stock_sync_job_read(job)


@router.post("/writeback/stock/jobs/{job_id}/cancel", response_model=WooStockSyncJobRead)
def writeback_stock_job_cancel(job_id: int, db: Session = Depends(get_db)) -> WooStockSyncJobRead:
    try:
        job = cancel_stock_sync_job(db, job_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if job is None:
        raise HTTPException(status_code=404, detail="Stock sync job not found")
    return stock_sync_job_read(job)


@router.post("/writeback/order-status/preview", response_model=WooWritebackPreviewResponse)
def writeback_order_status_preview(payload: WooWritebackOrderStatusPreviewRequest, db: Session = Depends(get_db)) -> WooWritebackPreviewResponse:
    settings = effective_woocommerce_settings(db, get_settings())
    result = preview_order_status_writeback(db, settings, create_woocommerce_client(), payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Local order not found")
    return result


@router.post("/writeback/queue", response_model=WooWritebackQueueRead)
def writeback_queue_create(payload: WooWritebackQueueCreateRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooWritebackQueueRead:
    try:
        row = create_queue_item(db, effective_woocommerce_settings(db, get_settings()), payload.model_copy(update={"requested_by": actor}))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return queue_to_read(row)


@router.get("/writeback/queue", response_model=WooWritebackQueueListResponse)
def writeback_queue_list(status: str | None = None, db: Session = Depends(get_db)) -> WooWritebackQueueListResponse:
    return list_queue(db, status=status)


@router.get("/writeback/status", response_model=WooCommerceStatusResponse)
def writeback_status(db: Session = Depends(get_db)) -> WooCommerceStatusResponse:
    return woocommerce_status(check=False, db=db)


@router.get("/writeback/logs", response_model=WooWritebackQueueListResponse)
def writeback_logs(db: Session = Depends(get_db)) -> WooWritebackQueueListResponse:
    rows = []
    for status in ["sent", "failed", "cancelled"]:
        rows.extend(list_queue(db, status=status).queue)
    rows.sort(key=lambda row: row.updated_at or row.created_at, reverse=True)
    return WooWritebackQueueListResponse(queue=rows, total=len(rows))


@router.get("/writeback/queue/{queue_id}", response_model=WooWritebackQueueRead)
def writeback_queue_detail(queue_id: int, db: Session = Depends(get_db)) -> WooWritebackQueueRead:
    row = get_queue_item(db, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="WooCommerce writeback queue item not found")
    return queue_to_read(row)


@router.post("/writeback/queue/{queue_id}/approve", response_model=WooWritebackQueueRead)
def writeback_queue_approve(queue_id: int, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooWritebackQueueRead:
    try:
        row = approve_queue_item(db, queue_id, approved_by=actor)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if row is None:
        raise HTTPException(status_code=404, detail="WooCommerce writeback queue item not found")
    return queue_to_read(row)


@router.post("/writeback/queue/{queue_id}/send", response_model=WooWritebackQueueRead)
def writeback_queue_send(queue_id: int, db: Session = Depends(get_db)) -> WooWritebackQueueRead:
    settings = effective_woocommerce_settings(db, get_settings())
    row = send_queue_item(db, create_woocommerce_client(), settings, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="WooCommerce writeback queue item not found")
    return queue_to_read(row)


@router.post("/writeback/queue/{queue_id}/revalidate", response_model=WooWritebackQueueRead)
def writeback_queue_revalidate(queue_id: int, db: Session = Depends(get_db)) -> WooWritebackQueueRead:
    try:
        settings = effective_woocommerce_settings(db, get_settings())
        row = revalidate_queue_item(db, create_woocommerce_client(), settings, queue_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if row is None:
        raise HTTPException(status_code=404, detail="WooCommerce writeback queue item not found")
    return queue_to_read(row)


@router.post("/writeback/queue/{queue_id}/cancel", response_model=WooWritebackQueueRead)
def writeback_queue_cancel(queue_id: int, db: Session = Depends(get_db)) -> WooWritebackQueueRead:
    row = cancel_queue_item(db, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="WooCommerce writeback queue item not found")
    return queue_to_read(row)


@router.post("/writeback/{queue_id}/approve", response_model=WooWritebackQueueRead)
def writeback_queue_approve_legacy(queue_id: int, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> WooWritebackQueueRead:
    return writeback_queue_approve(queue_id, db=db, actor=actor)


@router.post("/writeback/{queue_id}/send", response_model=WooWritebackQueueRead)
def writeback_queue_send_legacy(queue_id: int, db: Session = Depends(get_db)) -> WooWritebackQueueRead:
    return writeback_queue_send(queue_id, db=db)


@router.post("/writeback/{queue_id}/cancel", response_model=WooWritebackQueueRead)
def writeback_queue_cancel_legacy(queue_id: int, db: Session = Depends(get_db)) -> WooWritebackQueueRead:
    return writeback_queue_cancel(queue_id, db=db)


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


def woo_status_payload(settings, client: WooCommerceClient, db: Session, *, scheduler_running: bool = False) -> dict:
    host = client.base_url_host
    allowed_host = getattr(settings, "woocommerce_allowed_host", "")
    access_change = latest_access_mode_change(db)
    saved_configuration = latest_woocommerce_configuration(db)
    last_product_sync = latest_sync(db, "products")
    last_order_sync = latest_sync(db, "orders")
    latest_error = db.scalars(select(WooCommerceSyncError).order_by(WooCommerceSyncError.created_at.desc(), WooCommerceSyncError.id.desc())).first()
    latest_webhook = db.scalars(select(WooCommerceWebhookDelivery).order_by(WooCommerceWebhookDelivery.received_at.desc(), WooCommerceWebhookDelivery.id.desc())).first()
    return {
        "base_url": settings.woocommerce_base_url or None,
        "base_url_host": host,
        "environment": getattr(settings, "woocommerce_environment", "development"),
        "access_mode": "read_only" if getattr(settings, "woocommerce_read_only", True) else "read_write",
        "access_mode_updated_by": access_change.changed_by if access_change else None,
        "access_mode_updated_at": access_change.created_at if access_change else None,
        "configuration_source": "pongo_database" if saved_configuration else "backend_environment",
        "configuration_updated_by": saved_configuration.updated_by if saved_configuration else None,
        "configuration_updated_at": saved_configuration.updated_at if saved_configuration else None,
        "read_enabled": getattr(settings, "woocommerce_read_enabled", True),
        "read_only": getattr(settings, "woocommerce_read_only", True),
        "writeback_enabled": getattr(settings, "woocommerce_writeback_enabled", False),
        "dry_run": getattr(settings, "woocommerce_writeback_dry_run", True),
        "staging_live_test_mode": getattr(settings, "woocommerce_staging_live_test_mode", False),
        "stock_write_allowed": getattr(settings, "woocommerce_allow_stock_write", False),
        "production_stock_authority": getattr(settings, "woocommerce_production_stock_authority", "disabled"),
        "order_status_write_allowed": getattr(settings, "woocommerce_allow_order_status_write", False),
        "product_metadata_write_allowed": getattr(settings, "woocommerce_allow_product_metadata_write", False),
        "customer_write_allowed": getattr(settings, "woocommerce_allow_customer_write", False),
        "coupon_write_allowed": getattr(settings, "woocommerce_allow_coupon_write", False),
        "refund_write_allowed": getattr(settings, "woocommerce_allow_refund_write", False),
        "delete_allowed": getattr(settings, "woocommerce_allow_delete", False),
        "allowed_host": allowed_host or None,
        "host_allowed": bool(host and allowed_host and host.lower() == allowed_host.lower()),
        "webhook_enabled": getattr(settings, "woocommerce_webhook_enabled", False),
        "webhook_configured": webhook_is_configured(settings),
        "webhook_secret_present": bool(getattr(settings, "woocommerce_webhook_secret", "")),
        "last_webhook_delivery": {
            "id": latest_webhook.id,
            "topic": latest_webhook.topic,
            "status": latest_webhook.processing_status,
            "woo_order_id": latest_webhook.woo_order_id,
            "created_order": latest_webhook.created_order,
            "received_at": latest_webhook.received_at.isoformat(),
        } if latest_webhook else None,
        "last_product_sync": sync_run_to_read(last_product_sync).model_dump(mode="json") if last_product_sync else None,
        "last_order_sync": sync_run_to_read(last_order_sync).model_dump(mode="json") if last_order_sync else None,
        "order_reconciliation": reconciliation_health(db, settings, running=scheduler_running),
        "last_error": latest_error.error_message if latest_error else None,
    }


def latest_sync(db: Session, sync_type: str) -> WooCommerceSyncRun | None:
    return db.scalars(select(WooCommerceSyncRun).where(WooCommerceSyncRun.sync_type == sync_type).order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())).first()
