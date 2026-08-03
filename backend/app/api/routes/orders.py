from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.orders import OrderItem
from app.schemas.orders import BulkOrderActionRequest, BulkOrderActionResponse, BulkUnpickRequest, CompletedOrderListResponse, OpenOrderDetail, OpenOrderListResponse, OrderCompletionRequest, OrderCompletionResponse, OrderWorkflowPreviewResponse
from app.services.allocations import allocation_to_read, list_allocations
from app.services.auth import authenticated_actor
from app.services.completed_orders import CompletedOrderFilters, export_completed_orders_csv, list_completed_orders
from app.services.fulfillments import fulfillment_to_read, list_fulfillments
from app.services.order_workflow import auto_allocate_order_if_possible, complete_order_without_stock_reduction, complete_picked_order, determine_order_workflow_flags, evaluate_order_allocation
from app.services.picks import list_picks, pick_to_read, unpick_orders
from app.services.stock_mutation_guard import IdempotencyConflict
from app.services.woocommerce_orders import export_open_orders_csv, get_open_order_detail, list_open_orders
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_writeback import sync_completed_order_status, sync_inventory_stock

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/open", response_model=OpenOrderListResponse)
def list_open_order_queue(
    search: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    return list_open_orders(db, search=search, availability_status=availability_status, matched_status=matched_status)


@router.get("/allocate", response_model=OpenOrderListResponse)
def list_allocation_exceptions(
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    include_allocated: bool = False,
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    view = "open" if include_allocated else "allocate"
    return list_open_orders(db, search=search, woo_status=woo_status, availability_status=availability_status, matched_status=matched_status, workflow_view=view)


@router.get("/pick", response_model=OpenOrderListResponse)
def list_pickable_orders(
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    return list_open_orders(db, search=search, woo_status=woo_status, availability_status=availability_status, matched_status=matched_status, workflow_view="pick")


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
    db: Session = Depends(get_db),
) -> CompletedOrderListResponse:
    return list_completed_orders(db, CompletedOrderFilters(local_status=local_status, date_from=date_from, date_to=date_to, customer_email=customer_email, woo_order_number=woo_order_number, sku=sku, barcode=barcode, search=search))


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
def list_order_history(db: Session = Depends(get_db)) -> dict:
    allocations = list_allocations(db)
    picks = list_picks(db)
    fulfillments = list_fulfillments(db)
    return {
        "allocations": [allocation_to_read(row) for row in allocations],
        "picks": [pick_to_read(row) for row in picks],
        "fulfillments": [fulfillment_to_read(row) for row in fulfillments],
        "total": len(allocations) + len(picks) + len(fulfillments),
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
        completion_mode = payload.completion_mode
        if completion_mode == "complete":
            detail = get_open_order_detail(db, order_id)
            if detail is None:
                raise HTTPException(status_code=404, detail="Order not found")
            completion_mode = "complete_picked" if detail.pick_status == "picked" else "complete_without_picking"
        if completion_mode == "complete_picked":
            result = complete_picked_order(db, order_id, created_by=actor)
        elif completion_mode == "complete_without_picking":
            result = complete_order_without_stock_reduction(db, order_id, payload.reason or "Completed from Open Orders.", created_by=actor)
        else:
            raise ValueError("Invalid completion mode.")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    settings = effective_woocommerce_settings(db, get_settings())
    woo_client = WooCommerceClient(settings)
    stock_sync = sync_completed_picked_stock(db, settings, woo_client, order_id, actor) if completion_mode == "complete_picked" else None
    writeback = None
    writeback_error = None
    try:
        writeback = sync_completed_order_status(db, settings, woo_client, order_id, actor)
    except ValueError as error:
        writeback_error = str(error)
    return OrderCompletionResponse(
        **result,
        queue_woo_status_update=True,
        woo_sync_status=writeback.status if writeback else "failed",
        woo_writeback_queue_id=writeback.id if writeback else None,
        woo_sync_error=(writeback.error_message if writeback else writeback_error) or stock_sync_error(stock_sync),
    )


def sync_completed_picked_stock(db: Session, settings, woo_client: WooCommerceClient, order_id: int, requested_by: str):
    item_ids = {item_id for item_id in db.scalars(select(OrderItem.inventory_item_id).where(OrderItem.order_id == order_id)).all() if item_id}
    return sync_inventory_stock(db, settings, woo_client, item_ids=item_ids, requested_by=requested_by)


def stock_sync_error(sync) -> str | None:
    if sync and sync.failed_count:
        return f"{sync.failed_count} completed-order stock update(s) failed to reach WooCommerce. Review the writeback queue."
    if sync and sync.dry_run_count:
        return "WooCommerce stock writeback ran in dry-run mode; remote stock was not changed."
    return None


@router.get("/{order_id}", response_model=OpenOrderDetail)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OpenOrderDetail:
    order = get_open_order_detail(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
