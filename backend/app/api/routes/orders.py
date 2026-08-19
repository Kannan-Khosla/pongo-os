from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.orders import (
    BulkOrderActionRequest,
    BulkOrderActionResponse,
    BulkUnpickRequest,
    CompletedOrderListResponse,
    CompletedOrderPickRecoveryRequest,
    CompletedOrderPickRecoveryResponse,
    OpenOrderDetail,
    OpenOrderListResponse,
    OrderCompletionRequest,
    OrderCompletionResponse,
    OrderSubstitutionRequest,
    OrderSubstitutionResponse,
    OrderWorkflowPreviewResponse,
    WooOrderStatusActionRequest,
    WooOrderStatusActionResponse,
    WooOrderReconcileRequest,
    WooOrderReconcileResponse,
)
from app.services.allocations import allocation_to_read, list_allocations_page
from app.services.auth import authenticated_actor
from app.services.completed_orders import CompletedOrderFilters, export_completed_orders_csv, list_completed_orders
from app.services.fulfillments import fulfillment_to_read, list_fulfillments_page
from app.services.order_actions import (
    OrderActionConflict,
    change_live_woo_order_status,
    prepare_completed_order_for_picking,
    reconcile_live_woo_order,
    stock_sync_error,
    substitute_order_line,
    sync_completed_picked_stock,
)
from app.services.order_workflow import auto_allocate_order_if_possible, complete_order_without_stock_reduction, complete_picked_order, determine_order_workflow_flags, evaluate_order_allocation
from app.services.picks import list_picks_page, pick_to_read, unpick_orders
from app.services.stock_mutation_guard import IdempotencyConflict
from app.services.woocommerce_orders import export_open_orders_csv, get_open_order_detail, list_open_orders
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_writeback import sync_completed_order_status

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/open", response_model=OpenOrderListResponse)
def list_open_order_queue(
    search: str | None = None,
    order_number: str | None = None,
    customer: str | None = None,
    containing_item: str | None = None,
    warehouse: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    return list_open_orders(
        db,
        search=search,
        order_number=order_number,
        customer=customer,
        containing_item=containing_item,
        warehouse=warehouse,
        availability_status=availability_status,
        matched_status=matched_status,
        page=page,
        page_size=page_size,
    )


@router.get("/allocate", response_model=OpenOrderListResponse)
def list_allocation_exceptions(
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    include_allocated: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    view = "open" if include_allocated else "allocate"
    return list_open_orders(db, search=search, woo_status=woo_status, availability_status=availability_status, matched_status=matched_status, workflow_view=view, page=page, page_size=page_size)


@router.get("/pick", response_model=OpenOrderListResponse)
def list_pickable_orders(
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    return list_open_orders(db, search=search, woo_status=woo_status, availability_status=availability_status, matched_status=matched_status, workflow_view="pick", page=page, page_size=page_size)


@router.get("/open/export")
def export_open_order_queue(
    search: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_text = export_open_orders_csv(db, search=search, availability_status=availability_status, matched_status=matched_status)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-open-orders-export.csv"'},
    )


@router.get("/completed", response_model=CompletedOrderListResponse)
def list_completed_order_queue(
    local_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CompletedOrderListResponse:
    return list_completed_orders(
        db,
        CompletedOrderFilters(local_status=local_status, date_from=date_from, date_to=date_to, customer_email=customer_email, woo_order_number=woo_order_number, sku=sku, barcode=barcode, search=search),
        page=page,
        page_size=page_size,
    )


@router.get("/completed/export")
def export_completed_order_queue(
    local_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_text = export_completed_orders_csv(db, CompletedOrderFilters(local_status=local_status, date_from=date_from, date_to=date_to, customer_email=customer_email, woo_order_number=woo_order_number, sku=sku, barcode=barcode, search=search))
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-completed-orders-export.csv"'},
    )


@router.get("/history")
def list_order_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    allocations, allocation_total, allocation_page, allocation_total_pages = list_allocations_page(
        db,
        page=page,
        page_size=page_size,
        clamp_page=False,
    )
    picks, pick_total, pick_page, pick_total_pages = list_picks_page(
        db,
        page=page,
        page_size=page_size,
        clamp_page=False,
    )
    fulfillments, fulfillment_total, fulfillment_page, fulfillment_total_pages = list_fulfillments_page(
        db,
        page=page,
        page_size=page_size,
        clamp_page=False,
    )
    section_pagination = {
        "allocations": pagination_metadata(allocation_total, allocation_page, page_size, allocation_total_pages, len(allocations)),
        "picks": pagination_metadata(pick_total, pick_page, page_size, pick_total_pages, len(picks)),
        "fulfillments": pagination_metadata(fulfillment_total, fulfillment_page, page_size, fulfillment_total_pages, len(fulfillments)),
    }
    total_pages = max(allocation_total_pages, pick_total_pages, fulfillment_total_pages)
    return {
        "allocations": [allocation_to_read(row) for row in allocations],
        "picks": [pick_to_read(row) for row in picks],
        "fulfillments": [fulfillment_to_read(row) for row in fulfillments],
        "total": allocation_total + pick_total + fulfillment_total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "returned_count": len(allocations) + len(picks) + len(fulfillments),
        "has_previous": page > 1 and (allocation_total + pick_total + fulfillment_total) > 0,
        "has_next": page < total_pages,
        "pagination": section_pagination,
    }


def pagination_metadata(total: int, page: int, page_size: int, total_pages: int, returned_count: int) -> dict:
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "returned_count": returned_count,
        "has_previous": page > 1 and total > 0,
        "has_next": page < total_pages,
    }


@router.post("/bulk/complete", response_model=BulkOrderActionResponse)
def bulk_complete_orders(payload: BulkOrderActionRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> BulkOrderActionResponse:
    selected_ids = list(dict.fromkeys(payload.order_ids))
    results = []
    errors = []
    settings = effective_woocommerce_settings(db, get_settings())
    woo_client = WooCommerceClient(settings)
    for order_id in selected_ids:
        try:
            detail = get_open_order_detail(db, order_id)
            if detail is None:
                raise ValueError("Order not found.")
            was_picked = detail.pick_status == "picked"
            if was_picked:
                result = complete_picked_order(db, order_id, created_by=actor)
            else:
                result = complete_order_without_stock_reduction(db, order_id, payload.reason or "Bulk completed from Open Orders.", created_by=actor)
            stock_sync = sync_completed_picked_stock(db, settings, woo_client, order_id, actor) if was_picked else None
            writeback = sync_completed_order_status(db, settings, woo_client, order_id, actor)
            results.append({
                "order_id": order_id,
                "status": result["status"],
                "message": result["message"],
                "woo_sync_status": writeback.status,
                "woo_writeback_queue_id": writeback.id,
                "woo_sync_error": writeback.error_message or stock_sync_error(stock_sync),
            })
        except Exception as error:
            db.rollback()
            errors.append(f"Order {order_id}: {error}")
    succeeded_count = len(results)
    failed_count = len(selected_ids) - succeeded_count
    status = "completed" if failed_count == 0 else ("partial" if succeeded_count else "rejected")
    return BulkOrderActionResponse(
        status=status,
        requested_count=len(selected_ids),
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        results=results,
        errors=errors,
    )


@router.post("/bulk/unpick", response_model=BulkOrderActionResponse)
def bulk_unpick_orders(payload: BulkUnpickRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> BulkOrderActionResponse:
    try:
        return BulkOrderActionResponse(
            **unpick_orders(
                db,
                payload.order_ids,
                created_by=actor,
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
            )
        )
    except IdempotencyConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{order_id}/workflow")
def get_order_workflow(order_id: int, db: Session = Depends(get_db)) -> dict:
    detail = get_open_order_detail(db, order_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Order not found")
    flags = determine_order_workflow_flags(db, order_id)
    evaluation = evaluate_order_allocation(db, order_id).as_dict()
    return {"order": detail, "workflow": flags, "allocation_evaluation": evaluation}


@router.post("/{order_id}/auto-allocate/preview", response_model=OrderWorkflowPreviewResponse)
def preview_order_auto_allocation(order_id: int, db: Session = Depends(get_db)) -> OrderWorkflowPreviewResponse:
    evaluation = evaluate_order_allocation(db, order_id)
    return OrderWorkflowPreviewResponse(
        order_id=order_id,
        status="allocatable" if evaluation.can_fully_allocate else "exception",
        message=None if evaluation.can_fully_allocate else "Order cannot be fully auto-allocated.",
        warnings=evaluation.warnings,
        errors=[line["message"] for line in evaluation.unmatched_lines + evaluation.conflict_lines + evaluation.shortage_lines + evaluation.unavailable_lines],
        workflow=evaluation.as_dict(),
    )


@router.post("/{order_id}/auto-allocate/commit", response_model=OrderWorkflowPreviewResponse)
def commit_order_auto_allocation(order_id: int, db: Session = Depends(get_db)) -> OrderWorkflowPreviewResponse:
    try:
        result = auto_allocate_order_if_possible(db, order_id, source="manual-auto-allocation")
        db.commit()
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    return OrderWorkflowPreviewResponse(
        order_id=order_id,
        status=result["status"],
        message=result.get("reason"),
        warnings=[],
        errors=[] if result["status"] in {"allocated", "not_required"} else [result.get("reason") or "Auto-allocation failed."],
        workflow=result.get("evaluation"),
    )


@router.post("/{order_id}/complete/preview", response_model=OrderWorkflowPreviewResponse)
def preview_order_completion(order_id: int, payload: OrderCompletionRequest, db: Session = Depends(get_db)) -> OrderWorkflowPreviewResponse:
    detail = get_open_order_detail(db, order_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Order not found")
    flags = determine_order_workflow_flags(db, order_id)
    if payload.completion_mode not in {"complete", "complete_picked", "complete_without_picking"}:
        raise HTTPException(status_code=400, detail="Invalid completion mode.")
    completing_without_picking = payload.completion_mode == "complete_without_picking" or (payload.completion_mode == "complete" and detail.pick_status != "picked")
    warning = "This order has not been fully picked. Completing it now will not reduce unpicked stock." if completing_without_picking else "Stock already reduced during picking; completion will only close the local order."
    return OrderWorkflowPreviewResponse(order_id=order_id, status="preview", message=warning, warnings=[warning], workflow={"order": detail.model_dump(mode="json"), "flags": flags})


@router.post("/{order_id}/complete/commit", response_model=OrderCompletionResponse)
def commit_order_completion(order_id: int, payload: OrderCompletionRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> OrderCompletionResponse:
    try:
        detail = get_open_order_detail(db, order_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Order not found")
        was_recovery = detail.completion_status == "picking_recovery" or (
            detail.completed_without_picking and detail.woo_status == "completed"
        )
        recovery_completion_replay = was_recovery and detail.completion_status == "completed"
        completion_mode = payload.completion_mode
        if completion_mode == "complete":
            completion_mode = "complete_picked" if detail.pick_status == "picked" else "complete_without_picking"
        if was_recovery and completion_mode != "complete_picked":
            raise ValueError("A recovery order must be fully picked before it can be completed.")
        if recovery_completion_replay:
            result = {
                "status": "completed",
                "order_id": order_id,
                "released_quantity": 0,
                "message": "Recovery picking completion was already applied.",
            }
        elif completion_mode == "complete_picked":
            result = complete_picked_order(db, order_id, created_by=actor)
        elif completion_mode == "complete_without_picking":
            result = complete_order_without_stock_reduction(db, order_id, payload.reason or "Completed from Open Orders.", created_by=actor)
        else:
            raise ValueError("Invalid completion mode.")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = effective_woocommerce_settings(db, get_settings())
    woo_client = WooCommerceClient(settings)
    stock_sync = (
        sync_completed_picked_stock(db, settings, woo_client, order_id, actor)
        if completion_mode == "complete_picked" and not recovery_completion_replay
        else None
    )
    writeback = None
    writeback_error = None
    queue_woo_status_update = bool(payload.queue_woo_status_update and not was_recovery)
    if queue_woo_status_update:
        try:
            writeback = sync_completed_order_status(db, settings, woo_client, order_id, actor)
        except ValueError as error:
            writeback_error = str(error)
    return OrderCompletionResponse(
        **result,
        queue_woo_status_update=queue_woo_status_update,
        woo_sync_status=writeback.status if writeback else ("failed" if queue_woo_status_update else "not_requested"),
        woo_writeback_queue_id=writeback.id if writeback else None,
        woo_sync_error=(writeback.error_message if writeback else writeback_error) or stock_sync_error(stock_sync),
    )


@router.post("/woocommerce/{woo_order_id}/status", response_model=WooOrderStatusActionResponse)
def update_live_woo_order_status(
    woo_order_id: int,
    payload: WooOrderStatusActionRequest,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> WooOrderStatusActionResponse:
    assert_matching_idempotency_keys(payload.idempotency_key, idempotency_key_header)
    settings = effective_woocommerce_settings(db, get_settings())
    try:
        return change_live_woo_order_status(
            db,
            settings,
            WooCommerceClient(settings),
            woo_order_id,
            payload,
            actor=actor,
        )
    except (OrderActionConflict, IdempotencyConflict) as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except WooCommerceClientError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=error.message) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/woocommerce/{woo_order_id}/reconcile", response_model=WooOrderReconcileResponse)
def reconcile_live_woo_order_detail(
    woo_order_id: int,
    payload: WooOrderReconcileRequest,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> WooOrderReconcileResponse:
    assert_matching_idempotency_keys(payload.idempotency_key, idempotency_key_header)
    settings = effective_woocommerce_settings(db, get_settings())
    try:
        return reconcile_live_woo_order(
            db,
            WooCommerceClient(settings),
            woo_order_id,
            payload,
            actor=actor,
        )
    except (OrderActionConflict, IdempotencyConflict) as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except WooCommerceClientError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=error.message) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{order_id}/lines/{order_line_id}/substitute", response_model=OrderSubstitutionResponse)
def substitute_open_order_line(
    order_id: int,
    order_line_id: int,
    payload: OrderSubstitutionRequest,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> OrderSubstitutionResponse:
    assert_matching_idempotency_keys(payload.idempotency_key, idempotency_key_header)
    try:
        return substitute_order_line(db, order_id, order_line_id, payload, actor=actor)
    except (OrderActionConflict, IdempotencyConflict) as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{order_id}/prepare-picking", response_model=CompletedOrderPickRecoveryResponse)
def prepare_completed_order_pick_recovery(
    order_id: int,
    payload: CompletedOrderPickRecoveryRequest,
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> CompletedOrderPickRecoveryResponse:
    assert_matching_idempotency_keys(payload.idempotency_key, idempotency_key_header)
    settings = effective_woocommerce_settings(db, get_settings())
    try:
        return prepare_completed_order_for_picking(
            db,
            WooCommerceClient(settings),
            order_id,
            payload,
            actor=actor,
        )
    except (OrderActionConflict, IdempotencyConflict) as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    except WooCommerceClientError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=error.message) from error


def assert_matching_idempotency_keys(body_key: str, header_key: str | None) -> None:
    if header_key is not None and header_key.strip() != body_key.strip():
        raise HTTPException(status_code=409, detail="Body and Idempotency-Key header values must match.")


@router.get("/{order_id}", response_model=OpenOrderDetail)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OpenOrderDetail:
    order = get_open_order_detail(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
