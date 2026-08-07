import csv
from datetime import date
from io import BytesIO, StringIO

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.inventory import InventoryItem, InventoryItemLocation, StockAdjustment, StockAdjustmentLine, StockMovement
from app.models.orders import OrderItem
from app.models.receipts import Receipt, ReceiptItem
from app.schemas.reports import FulfillmentReportRow, FulfillmentSummaryResponse, ReceivedInventoryReportRow, ReceivedInventorySummaryResponse, SkuOrdersReportRow, SkuOrdersSummaryResponse
from app.services.fulfillment_report import (
    FULFILLMENT_REPORT_CSV_COLUMNS,
    FulfillmentReportFilters,
    build_fulfillment_summary,
    fulfillment_report_row_to_csv,
    get_fulfillment_report_rows,
)
from app.services.received_inventory_report import (
    RECEIVED_INVENTORY_CSV_COLUMNS,
    ReceivedInventoryFilters,
    build_received_inventory_summary,
    get_received_inventory_rows,
    received_inventory_row_to_csv,
)
from app.services.sku_orders_report import SkuOrdersFilters, build_sku_orders_summary, export_sku_orders_csv, get_sku_order_rows
from app.services.reporting import (
    ReportArtifactUnavailableError,
    ReportIntegrityError,
    create_report_run,
    email_report,
    get_report_run,
    google_access_token,
    google_sheets_status,
    list_report_catalog,
    publish_report_to_google_sheets,
    report_artifact_bytes,
    report_run_to_dict,
)
from app.services.google_reports_configuration import (
    exchange_google_oauth_code,
    effective_google_reports_settings,
    google_oauth_authorization_url,
    google_reports_configuration_status,
    save_google_reports_configuration,
    save_google_reports_oauth_client,
    save_google_reports_refresh_token,
    verify_google_oauth_state,
)
from app.services.report_jobs import (
    enqueue_report_job,
    get_report_job,
    latest_completed_report_run,
    report_job_to_dict,
)
from app.services.auth import authenticated_actor

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportRunCreate(BaseModel):
    filters: dict[str, object] = Field(default_factory=dict)
    generated_by: str | None = Field(default="reporting-ui", max_length=120)


class GoogleSheetShareRequest(BaseModel):
    share_with: list[EmailStr] = Field(default_factory=list, max_length=50)


class GoogleSheetsConfigurationRequest(BaseModel):
    client_id: str | None = Field(default=None, max_length=500)
    client_secret: str | None = Field(default=None, max_length=1000)
    refresh_token: str | None = Field(default=None, max_length=4000)
    folder_id: str | None = Field(default=None, max_length=255)


class GoogleSheetsOAuthStartRequest(BaseModel):
    client_id: str | None = Field(default=None, max_length=500)
    client_secret: str | None = Field(default=None, max_length=1000)
    folder_id: str | None = Field(default=None, max_length=255)


class EmailReportRequest(BaseModel):
    recipients: list[EmailStr] = Field(min_length=1, max_length=50)
    formats: list[str] = Field(default_factory=lambda: ["pdf", "csv"], max_length=2)
    subject: str | None = Field(default=None, max_length=240)
    message: str | None = Field(default=None, max_length=4000)
    google_sheet_url: str | None = Field(default=None, max_length=1000)


@router.get("")
def list_reports(db: Session = Depends(get_db)) -> dict[str, object]:
    return list_report_catalog(effective_google_reports_settings(db, get_settings()))


@router.get("/sharing/status")
def report_sharing_status(db: Session = Depends(get_db)) -> dict[str, object]:
    settings = get_settings()
    return {
        "google_sheets": google_sheets_status(effective_google_reports_settings(db, settings)),
        "email": {"configured": bool(settings.smtp_host and settings.smtp_from_email)},
    }


@router.get("/google-sheets/configuration")
def read_google_sheets_configuration(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    return {
        **google_reports_configuration_status(db, get_settings()),
        "oauth_redirect_uri": str(request.url_for("google_sheets_oauth_callback")),
    }


@router.post("/google-sheets/configuration")
def configure_google_sheets(
    payload: GoogleSheetsConfigurationRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict[str, object]:
    try:
        status = save_google_reports_configuration(
            db,
            get_settings(),
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            refresh_token=payload.refresh_token,
            folder_id=payload.folder_id,
            changed_by=actor,
            verifier=google_access_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Google rejected these credentials. Check the OAuth client and refresh token, then try again.") from exc
    return {**status, "message": "Google Sheets is connected and saved securely in Pongo."}


@router.post("/google-sheets/oauth/start")
def start_google_sheets_oauth(
    request: Request,
    payload: GoogleSheetsOAuthStartRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict[str, str]:
    settings = get_settings()
    redirect_uri = str(request.url_for("google_sheets_oauth_callback"))
    try:
        save_google_reports_oauth_client(
            db,
            settings,
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            folder_id=payload.folder_id,
            changed_by=actor,
        )
        current = effective_google_reports_settings(db, settings)
        authorization_url = google_oauth_authorization_url(current, actor=actor, redirect_uri=redirect_uri)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"authorization_url": authorization_url, "redirect_uri": redirect_uri}


@router.get("/google-sheets/oauth/callback", name="google_sheets_oauth_callback")
def google_sheets_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> RedirectResponse:
    settings = get_settings()
    redirect_uri = str(request.url_for("google_sheets_oauth_callback"))
    try:
        if not state:
            raise ValueError("Google did not return a verifiable connection request.")
        verify_google_oauth_state(settings, state=state, actor=actor, redirect_uri=redirect_uri)
        if error:
            return RedirectResponse(url="/#/settings/google-sheets?google=denied", status_code=303)
        if not code:
            raise ValueError("Google did not return an authorization code.")
        current = effective_google_reports_settings(db, settings)
        refresh_token = exchange_google_oauth_code(current, code=code, redirect_uri=redirect_uri)
        save_google_reports_refresh_token(db, settings, refresh_token=refresh_token, changed_by=actor)
    except (ValueError, httpx.HTTPError):
        db.rollback()
        return RedirectResponse(url="/#/settings/google-sheets?google=failed", status_code=303)
    return RedirectResponse(url="/#/settings/google-sheets?google=connected", status_code=303)


@router.post("/runs/{report_key}")
def run_report(report_key: str, payload: ReportRunCreate, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict[str, object]:
    try:
        return create_report_run(db, report_key, payload.filters, actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs/{report_key}", status_code=202)
def enqueue_report(
    report_key: str,
    payload: ReportRunCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict[str, object]:
    try:
        job, deduplicated = enqueue_report_job(db, report_key, payload.filters, actor)
        return report_job_to_dict(job, deduplicated=deduplicated)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/jobs/latest/{report_key}")
def latest_report(
    report_key: str,
    payload: ReportRunCreate,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        run = latest_completed_report_run(db, report_key, payload.filters)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Report not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ReportIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="No completed report run matches these filters.")
    return report_run_to_dict(run)


@router.get("/jobs/{job_id}")
def read_report_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    job = get_report_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Report job not found.")
    return report_job_to_dict(job)


@router.get("/runs/{run_id}")
def read_report_run(run_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    run = require_report_run(db, run_id)
    return report_run_to_dict(run)


@router.get("/runs/{run_id}/csv")
def download_report_csv(run_id: str, db: Session = Depends(get_db)) -> Response:
    run = require_report_run(db, run_id)
    csv_artifact = require_report_artifact(run, "csv")
    return StreamingResponse(
        BytesIO(csv_artifact),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="pongo-{run.report_key}-{run.id}.csv"',
            "Content-Length": str(len(csv_artifact)),
            "X-Report-Data-SHA256": run.data_hash,
            "X-Artifact-SHA256": run.csv_artifact_hash,
        },
    )


@router.get("/runs/{run_id}/pdf")
def download_report_pdf(run_id: str, db: Session = Depends(get_db)) -> Response:
    run = require_report_run(db, run_id)
    pdf_artifact = require_report_artifact(run, "pdf")
    return StreamingResponse(
        BytesIO(pdf_artifact),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="pongo-{run.report_key}-{run.id}.pdf"',
            "Content-Length": str(len(pdf_artifact)),
            "X-Report-Data-SHA256": run.data_hash,
            "X-Artifact-SHA256": run.pdf_artifact_hash,
        },
    )


@router.post("/runs/{run_id}/google-sheets")
def open_report_in_google_sheets(
    run_id: str,
    payload: GoogleSheetShareRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = require_report_run(db, run_id)
    try:
        return publish_report_to_google_sheets(
            db,
            run,
            effective_google_reports_settings(db, get_settings()),
            [str(recipient) for recipient in payload.share_with],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Google Sheets rejected the report request. Check the backend Google connection and scopes.") from exc


@router.post("/runs/{run_id}/email")
def share_report_by_email(
    run_id: str,
    payload: EmailReportRequest,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    run = require_report_run(db, run_id)
    try:
        return email_report(
            db,
            run,
            get_settings(),
            [str(recipient) for recipient in payload.recipients],
            payload.formats,
            payload.subject,
            payload.message,
            payload.google_sheet_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail="The configured mail server could not send this report.") from exc


def require_report_run(db: Session, run_id: str):
    try:
        run = get_report_run(db, run_id)
    except ReportIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Report run not found.")
    return run


def require_report_artifact(run, artifact_format: str) -> bytes:
    try:
        return report_artifact_bytes(run, artifact_format)
    except ReportArtifactUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReportIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/received-inventory", response_model=list[ReceivedInventoryReportRow])
def received_inventory_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    receipt_number: str | None = None,
    reference_number: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> list[ReceivedInventoryReportRow]:
    return get_received_inventory_rows(db, build_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, receipt_number, reference_number, created_by))


@router.get("/received-inventory/summary", response_model=ReceivedInventorySummaryResponse)
def received_inventory_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    receipt_number: str | None = None,
    reference_number: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    filters = build_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, receipt_number, reference_number, created_by)
    rows = get_received_inventory_rows(db, filters)
    return build_received_inventory_summary(rows, filters)


@router.get("/received-inventory/export")
def export_received_inventory_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    receipt_number: str | None = None,
    reference_number: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    filters = build_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, receipt_number, reference_number, created_by)
    rows = get_received_inventory_rows(db, filters)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RECEIVED_INVENTORY_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(received_inventory_row_to_csv(row))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-received-inventory-report.csv"'},
    )


@router.get("/fulfillments", response_model=list[FulfillmentReportRow])
def fulfillment_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    fulfillment_number: str | None = None,
    woo_order_number: str | None = None,
    woo_order_id: int | None = None,
    customer_email: str | None = None,
    local_status: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> list[FulfillmentReportRow]:
    return get_fulfillment_report_rows(db, build_fulfillment_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, fulfillment_number, woo_order_number, woo_order_id, customer_email, local_status, created_by))


@router.get("/fulfillments/summary", response_model=FulfillmentSummaryResponse)
def fulfillment_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    fulfillment_number: str | None = None,
    woo_order_number: str | None = None,
    woo_order_id: int | None = None,
    customer_email: str | None = None,
    local_status: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    filters = build_fulfillment_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, fulfillment_number, woo_order_number, woo_order_id, customer_email, local_status, created_by)
    rows = get_fulfillment_report_rows(db, filters)
    return build_fulfillment_summary(rows, filters)


@router.get("/fulfillments/export")
def export_fulfillment_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    fulfillment_number: str | None = None,
    woo_order_number: str | None = None,
    woo_order_id: int | None = None,
    customer_email: str | None = None,
    local_status: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    filters = build_fulfillment_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, fulfillment_number, woo_order_number, woo_order_id, customer_email, local_status, created_by)
    rows = get_fulfillment_report_rows(db, filters)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FULFILLMENT_REPORT_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(fulfillment_report_row_to_csv(row))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-fulfillment-report.csv"'},
    )


@router.get("/sku-orders", response_model=list[SkuOrdersReportRow])
def sku_orders_report(
    start_date: date | None = None,
    end_date: date | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    order_status: str | None = None,
    woo_status: str | None = None,
    include_unmatched: bool = True,
    group_by: str = "sku",
    limit: int | None = None,
    offset: int | None = None,
    db: Session = Depends(get_db),
) -> list[SkuOrdersReportRow]:
    return get_sku_order_rows(db, build_sku_order_filters(start_date, end_date, sku, brand, category, order_status, woo_status, include_unmatched, group_by, limit, offset))


@router.get("/sku-orders/summary", response_model=SkuOrdersSummaryResponse)
def sku_orders_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    order_status: str | None = None,
    woo_status: str | None = None,
    include_unmatched: bool = True,
    group_by: str = "sku",
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rows = get_sku_order_rows(db, build_sku_order_filters(start_date, end_date, sku, brand, category, order_status, woo_status, include_unmatched, group_by, None, None))
    return build_sku_orders_summary(rows)


@router.get("/sku-orders/export")
def export_sku_orders_report(
    start_date: date | None = None,
    end_date: date | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    order_status: str | None = None,
    woo_status: str | None = None,
    include_unmatched: bool = True,
    group_by: str = "sku",
    db: Session = Depends(get_db),
) -> Response:
    rows = get_sku_order_rows(db, build_sku_order_filters(start_date, end_date, sku, brand, category, order_status, woo_status, include_unmatched, group_by, None, None))
    return Response(content=export_sku_orders_csv(rows), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="pongo-sku-orders-report.csv"'})


@router.get("/inventory-valuation")
def inventory_valuation_report(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    return inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, limit, offset)


@router.get("/inventory-valuation/summary")
def inventory_valuation_summary(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, None, 0)
    return {
        **inventory_valuation_count_metadata(db, warehouse, inventory_location, sku, barcode, brand, category, rows),
        **summarize_inventory_rows(rows),
    }


@router.get("/inventory-valuation/export")
def inventory_valuation_export(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> Response:
    rows = inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, None, 0)
    return csv_response("pongo-inventory-valuation-report.csv", rows)


@router.get("/low-stock")
def low_stock_report(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    return [row for row in inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, limit, offset) if row["under_par"] or row["sellable"] < 0]


@router.get("/low-stock/summary")
def low_stock_summary(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = low_stock_report(warehouse, inventory_location, sku, barcode, brand, category, None, 0, db)
    return {"total_rows": len(rows), "under_par_count": sum(1 for row in rows if row["under_par"]), "negative_sellable_count": sum(1 for row in rows if row["sellable"] < 0), "suggested_order_qty": sum(row.get("suggested_order_qty", 0) for row in rows)}


@router.get("/low-stock/export")
def low_stock_export(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-low-stock-report.csv", low_stock_report(warehouse, inventory_location, sku, barcode, brand, category, None, 0, db))


@router.get("/stock-movement-ledger")
def stock_movement_ledger_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, movement_type: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    rows = movement_ledger_rows(db, start_date, end_date, sku, barcode, warehouse, inventory_location, movement_type)
    return rows[offset : offset + limit] if limit else rows[offset:]


@router.get("/stock-movement-ledger/summary")
def stock_movement_ledger_summary(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, movement_type: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = movement_ledger_rows(db, start_date, end_date, sku, barcode, warehouse, inventory_location, movement_type)
    return {"total_rows": len(rows), "total_quantity_change": sum(row["quantity_change"] for row in rows), "movement_types": sorted({row["movement_type"] for row in rows})}


@router.get("/stock-movement-ledger/export")
def stock_movement_ledger_export(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, movement_type: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-stock-movement-ledger-report.csv", movement_ledger_rows(db, start_date, end_date, sku, barcode, warehouse, inventory_location, movement_type))


@router.get("/item-activity")
def item_activity_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, movement_type: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    return stock_movement_ledger_report(start_date, end_date, sku, barcode, None, None, movement_type, limit, offset, db)


@router.get("/item-activity/summary")
def item_activity_summary(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, movement_type: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = movement_ledger_rows(db, start_date, end_date, sku, barcode, None, None, movement_type)
    return {"total_rows": len(rows), "stock_increase": sum(row["quantity_change"] for row in rows if row["quantity_change"] > 0), "stock_decrease": sum(row["quantity_change"] for row in rows if row["quantity_change"] < 0)}


@router.get("/item-activity/export")
def item_activity_export(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, movement_type: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-item-activity-report.csv", movement_ledger_rows(db, start_date, end_date, sku, barcode, None, None, movement_type))


@router.get("/location-utilization")
def location_utilization_report(warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    rows = inventory_valuation_rows(db, warehouse, inventory_location, None, None, None, None, None, 0)
    grouped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["warehouse"], row["inventory_location"], row.get("location_code"), row.get("location_name"))
        group = grouped.setdefault(key, {"warehouse": row["warehouse"], "inventory_location": row["inventory_location"], "location_code": row.get("location_code"), "location_name": row.get("location_name"), "sku_count": 0, "total_units": 0, "allocated_units": 0, "sellable_units": 0, "inventory_value": 0, "under_par_skus": 0})
        group["sku_count"] += 1
        group["total_units"] += row["in_stock"]
        group["allocated_units"] += row["allocated"]
        group["sellable_units"] += row["sellable"]
        group["inventory_value"] += row["inventory_value"] or 0
        group["under_par_skus"] += 1 if row["under_par"] else 0
    return list(grouped.values())


@router.get("/location-utilization/summary")
def location_utilization_summary(warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = location_utilization_report(warehouse, inventory_location, db)
    return {"locations_count": len(rows), "total_skus": sum(row["sku_count"] for row in rows), "total_units": sum(row["total_units"] for row in rows), "inventory_value": sum(row["inventory_value"] for row in rows)}


@router.get("/location-utilization/export")
def location_utilization_export(warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-location-utilization-report.csv", location_utilization_report(warehouse, inventory_location, db))


@router.get("/margin-by-sku")
def margin_by_sku_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(OrderItem, InventoryItem).join(InventoryItem, OrderItem.inventory_item_id == InventoryItem.id, isouter=True)
    if sku:
        statement = statement.where(OrderItem.sku == sku)
    rows = {}
    for order_item, item in db.execute(statement).all():
        if start_date and order_item.created_at.date() < start_date:
            continue
        if end_date and order_item.created_at.date() > end_date:
            continue
        if brand and (item.brand if item else order_item.brand) != brand:
            continue
        if category and (item.category if item else None) != category:
            continue
        key = order_item.sku or (item.sku if item else f"line-{order_item.id}")
        unit_cost = order_item.unit_cost or (item.unit_cost if item else 0) or 0
        revenue = order_item.line_total or order_item.total_price or 0
        quantity = order_item.quantity_ordered or order_item.ordered_qty or 0
        row = rows.setdefault(key, {"sku": key, "description": order_item.description or (item.description if item else None), "brand": item.brand if item else order_item.brand, "quantity_ordered": 0, "quantity_fulfilled": 0, "revenue": 0, "estimated_cost": 0, "estimated_margin": 0, "estimated_margin_percent": 0, "order_count": 0, "first_order_date": order_item.created_at, "last_order_date": order_item.created_at})
        row["quantity_ordered"] += float(quantity)
        row["quantity_fulfilled"] += float(order_item.quantity_fulfilled or order_item.fulfilled_qty or 0)
        row["revenue"] += float(revenue)
        row["estimated_cost"] += float(quantity * unit_cost)
        row["order_count"] += 1
        row["first_order_date"] = min(row["first_order_date"], order_item.created_at)
        row["last_order_date"] = max(row["last_order_date"], order_item.created_at)
    for row in rows.values():
        row["estimated_margin"] = row["revenue"] - row["estimated_cost"]
        row["estimated_margin_percent"] = (row["estimated_margin"] / row["revenue"] * 100) if row["revenue"] else 0
    return list(rows.values())


@router.get("/margin-by-sku/summary")
def margin_by_sku_summary(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = margin_by_sku_report(start_date, end_date, sku, brand, category, db)
    return {"total_skus": len(rows), "revenue": sum(row["revenue"] for row in rows), "estimated_cost": sum(row["estimated_cost"] for row in rows), "estimated_margin": sum(row["estimated_margin"] for row in rows)}


@router.get("/margin-by-sku/export")
def margin_by_sku_export(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-margin-by-sku-report.csv", margin_by_sku_report(start_date, end_date, sku, brand, category, db))


@router.get("/receiving-cost")
def receiving_cost_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(ReceiptItem, Receipt).join(Receipt, ReceiptItem.receipt_id == Receipt.id)
    rows = []
    for line, receipt in db.execute(statement).all():
        if start_date and line.created_at.date() < start_date:
            continue
        if end_date and line.created_at.date() > end_date:
            continue
        if sku and line.sku != sku:
            continue
        if warehouse and line.warehouse != warehouse:
            continue
        if inventory_location and line.inventory_location_name != inventory_location:
            continue
        rows.append({"receipt_number": receipt.receipt_number, "received_date": str(line.received_date or receipt.received_date or ""), "sku": line.sku, "description": line.description, "warehouse": line.warehouse, "inventory_location": line.inventory_location_name, "quantity": float(line.quantity_received or line.quantity or 0), "unit_cost": float(line.unit_cost or 0), "total_cost": float(line.unit_cost_total or 0), "brand": line.brand, "category": line.category})
    return rows


@router.get("/receiving-cost/summary")
def receiving_cost_summary(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = receiving_cost_report(start_date, end_date, sku, warehouse, inventory_location, db)
    return {"total_rows": len(rows), "total_quantity": sum(row["quantity"] for row in rows), "total_cost": sum(row["total_cost"] for row in rows)}


@router.get("/receiving-cost/export")
def receiving_cost_export(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-receiving-cost-report.csv", receiving_cost_report(start_date, end_date, sku, warehouse, inventory_location, db))


@router.get("/adjustments")
def adjustments_report(adjustment_type: str | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(StockAdjustmentLine, StockAdjustment).join(StockAdjustment, StockAdjustmentLine.adjustment_id == StockAdjustment.id)
    rows = []
    for line, adjustment in db.execute(statement).all():
        if adjustment_type and adjustment.adjustment_type != adjustment_type:
            continue
        if sku and line.sku != sku:
            continue
        if warehouse and line.warehouse != warehouse:
            continue
        if inventory_location and line.inventory_location != inventory_location:
            continue
        value_impact = (line.quantity_change or 0) * (line.unit_cost or 0)
        rows.append({"adjustment_number": adjustment.adjustment_number, "date": line.created_at, "adjustment_type": adjustment.adjustment_type, "reason": adjustment.reason, "sku": line.sku, "description": line.description, "warehouse": line.warehouse, "inventory_location": line.inventory_location, "old_qty": float(line.old_quantity or 0), "new_qty": float(line.new_quantity or 0), "quantity_change": float(line.quantity_change or 0), "unit_cost": float(line.unit_cost or 0), "estimated_value_impact": float(value_impact)})
    return rows


@router.get("/adjustments/summary")
def adjustments_summary(adjustment_type: str | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = adjustments_report(adjustment_type, sku, warehouse, inventory_location, db)
    return {"total_rows": len(rows), "total_quantity_change": sum(row["quantity_change"] for row in rows), "estimated_value_impact": sum(row["estimated_value_impact"] for row in rows)}


@router.get("/adjustments/export")
def adjustments_export(adjustment_type: str | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-adjustments-report.csv", adjustments_report(adjustment_type, sku, warehouse, inventory_location, db))


def inventory_valuation_rows(db: Session, warehouse: str | None, inventory_location: str | None, sku: str | None, barcode: str | None, brand: str | None, category: str | None, limit: int | None, offset: int) -> list[dict]:
    statement = select(InventoryItemLocation, InventoryItem).join(InventoryItem, InventoryItemLocation.inventory_item_id == InventoryItem.id).where(usable_item_location_predicate())
    if warehouse:
        statement = statement.where(InventoryItemLocation.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(InventoryItemLocation.inventory_location == inventory_location)
    if sku:
        statement = statement.where(InventoryItem.sku == sku)
    if barcode:
        statement = statement.where(InventoryItem.barcode == barcode)
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if category:
        statement = statement.where(InventoryItem.category == category)
    statement = statement.order_by(InventoryItem.sku.asc().nullslast(), InventoryItemLocation.warehouse.asc().nullslast(), InventoryItemLocation.inventory_location.asc().nullslast())
    if offset:
        statement = statement.offset(offset)
    if limit:
        statement = statement.limit(limit)
    rows = []
    for location, item in db.execute(statement).all():
        unit_cost = float(item.unit_cost) if item.unit_cost is not None else None
        sales_price = float(item.sales_price) if item.sales_price is not None else None
        in_stock = float(location.in_stock or 0)
        allocated = float(location.allocated or 0)
        sellable = float(location.sellable or (location.in_stock or 0) - (location.allocated or 0))
        par_level = float(location.par_level if location.par_level is not None else item.par_level or 0)
        rows.append({"sku": item.sku, "barcode": item.barcode, "description": item.woo_name or item.description, "brand": item.brand, "category": item.category, "warehouse": location.warehouse, "inventory_location": location.inventory_location, "location_code": location.location_code, "location_name": location.location_name, "in_stock": in_stock, "allocated": allocated, "sellable": sellable, "unit_cost": unit_cost, "inventory_value": in_stock * unit_cost if unit_cost is not None else None, "sales_price": sales_price, "retail_value": in_stock * sales_price if sales_price is not None else None, "margin_estimate": sales_price - unit_cost if sales_price is not None and unit_cost is not None else None, "par_level": par_level, "under_par": bool(location.under_par), "reorder_enabled": bool(item.reorder), "default_econ_order": float(item.default_econ_order or 0), "suggested_order_qty": max(0, par_level - in_stock)})
    return rows


def summarize_inventory_rows(rows: list[dict]) -> dict:
    inventory_values = [row["inventory_value"] for row in rows if row["inventory_value"] is not None]
    retail_values = [row["retail_value"] for row in rows if row["retail_value"] is not None]
    return {"total_skus": len({sku for row in rows if (sku := normalize_sku(row.get("sku")))}), "total_units": sum(row["in_stock"] for row in rows), "total_inventory_value": sum(inventory_values) if inventory_values else None, "total_retail_value": sum(retail_values) if retail_values else None, "locations_count": len({(row["warehouse"], row["inventory_location"]) for row in rows}), "under_par_count": sum(1 for row in rows if row["under_par"])}


def normalize_sku(value: object) -> str | None:
    normalized = str(value or "").strip().casefold()
    return normalized or None


def usable_item_location_predicate():
    return and_(
        InventoryItemLocation.active.is_(True),
        func.trim(func.coalesce(InventoryItemLocation.warehouse, "")) != "",
        func.trim(func.coalesce(InventoryItemLocation.inventory_location, "")) != "",
    )


def inventory_valuation_count_metadata(
    db: Session,
    warehouse: str | None,
    inventory_location: str | None,
    sku: str | None,
    barcode: str | None,
    brand: str | None,
    category: str | None,
    rows: list[dict],
) -> dict:
    statement = select(InventoryItem)
    if sku:
        statement = statement.where(InventoryItem.sku == sku)
    if barcode:
        statement = statement.where(InventoryItem.barcode == barcode)
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if category:
        statement = statement.where(InventoryItem.category == category)
    items = list(db.scalars(statement).all())
    item_ids = {item.id for item in items}
    all_location_item_ids: set[int] = set()
    reported_item_ids: set[int] = set()
    if item_ids:
        all_location_item_ids = set(db.scalars(select(InventoryItemLocation.inventory_item_id).where(InventoryItemLocation.inventory_item_id.in_(item_ids), usable_item_location_predicate())).all())
        location_statement = select(InventoryItemLocation.inventory_item_id).where(InventoryItemLocation.inventory_item_id.in_(item_ids), usable_item_location_predicate())
        if warehouse:
            location_statement = location_statement.where(InventoryItemLocation.warehouse == warehouse)
        if inventory_location:
            location_statement = location_statement.where(InventoryItemLocation.inventory_location == inventory_location)
        reported_item_ids = set(db.scalars(location_statement).all())
    reported_skus = {sku for row in rows if (sku := normalize_sku(row.get("sku")))}
    valued_skus = {sku for item in items if item.id in reported_item_ids and item.unit_cost is not None and (sku := normalize_sku(item.sku))}
    catalog_skus = [sku for item in items if (sku := normalize_sku(item.sku))]
    missing_location_count = len(item_ids - all_location_item_ids)
    location_filter_exclusion_count = len((item_ids & all_location_item_ids) - reported_item_ids)
    missing_cost_count = sum(1 for item in items if item.unit_cost is None)
    reported_missing_cost_count = sum(1 for item in items if item.id in reported_item_ids and item.unit_cost is None)
    missing_sku_count = sum(1 for item in items if normalize_sku(item.sku) is None)
    duplicate_sku_record_count = len(catalog_skus) - len(set(catalog_skus))
    exclusion_summary = []
    if missing_location_count:
        exclusion_summary.append({"reason": "missing_location", "label": "Location missing", "count": missing_location_count, "message": f"{missing_location_count} inventory record(s) are excluded because they have no active location row with both warehouse and location populated."})
    if location_filter_exclusion_count:
        exclusion_summary.append({"reason": "location_filter", "label": "Outside selected location", "count": location_filter_exclusion_count, "message": f"{location_filter_exclusion_count} inventory record(s) are excluded because their location rows do not match the selected warehouse or location."})
    if missing_cost_count:
        exclusion_summary.append({"reason": "missing_cost", "label": "Cost missing", "count": missing_cost_count, "message": f"{missing_cost_count} inventory record(s) cannot be counted as valued SKUs because unit cost is unavailable; {reported_missing_cost_count} appear in the current report."})
    if missing_sku_count:
        exclusion_summary.append({"reason": "missing_sku", "label": "SKU missing", "count": missing_sku_count, "message": f"{missing_sku_count} inventory record(s) are omitted from SKU counts because SKU is blank."})
    if duplicate_sku_record_count:
        exclusion_summary.append({"reason": "duplicate_sku", "label": "Duplicate SKU records", "count": duplicate_sku_record_count, "message": f"{duplicate_sku_record_count} inventory record(s) share an existing SKU and are collapsed in unique SKU counts."})
    return {
        "inventory_record_count": len(items),
        "unique_sku_count": len(set(catalog_skus)),
        "reported_sku_count": len(reported_skus),
        "valued_sku_count": len(valued_skus),
        "missing_sku_count": missing_sku_count,
        "duplicate_sku_record_count": duplicate_sku_record_count,
        "missing_location_count": missing_location_count,
        "missing_cost_count": missing_cost_count,
        "reported_missing_cost_count": reported_missing_cost_count,
        "excluded_record_count": len(item_ids - reported_item_ids),
        "location_filter_exclusion_count": location_filter_exclusion_count,
        "exclusion_summary": exclusion_summary,
    }


def movement_ledger_rows(db: Session, start_date: date | None, end_date: date | None, sku: str | None, barcode: str | None, warehouse: str | None, inventory_location: str | None, movement_type: str | None) -> list[dict]:
    statement = select(StockMovement).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    if sku:
        statement = statement.where(StockMovement.sku == sku)
    if barcode:
        statement = statement.where(StockMovement.barcode == barcode)
    if warehouse:
        statement = statement.where(StockMovement.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(StockMovement.inventory_location_name == inventory_location)
    rows = []
    for movement in db.scalars(statement).all():
        value = movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type)
        if movement_type and value != movement_type:
            continue
        if start_date and movement.created_at.date() < start_date:
            continue
        if end_date and movement.created_at.date() > end_date:
            continue
        rows.append({"date": movement.created_at, "movement_type": value, "reference_number": movement.reference_number, "sku": movement.sku, "barcode": movement.barcode, "description": movement.inventory_item.description if movement.inventory_item else None, "warehouse": movement.warehouse, "inventory_location": movement.inventory_location_name, "from_location": movement.from_inventory_location, "to_location": movement.to_inventory_location, "quantity_change": float(movement.quantity_change or 0), "old_location_stock": float(movement.old_location_stock or movement.old_stock or 0), "new_location_stock": float(movement.new_location_stock or movement.new_stock or 0), "reason": movement.reason, "notes": movement.notes})
    return rows


def csv_response(filename: str, rows: list[dict]) -> Response:
    buffer = StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def build_filters(
    date_from: date | None,
    date_to: date | None,
    warehouse: str | None,
    inventory_location: str | None,
    sku: str | None,
    barcode: str | None,
    category: str | None,
    brand: str | None,
    receipt_number: str | None,
    reference_number: str | None,
    created_by: str | None,
) -> ReceivedInventoryFilters:
    return ReceivedInventoryFilters(
        date_from=date_from,
        date_to=date_to,
        warehouse=warehouse,
        inventory_location=inventory_location,
        sku=sku,
        barcode=barcode,
        category=category,
        brand=brand,
        receipt_number=receipt_number,
        reference_number=reference_number,
        created_by=created_by,
    )


def build_fulfillment_filters(
    date_from: date | None,
    date_to: date | None,
    warehouse: str | None,
    inventory_location: str | None,
    sku: str | None,
    barcode: str | None,
    category: str | None,
    brand: str | None,
    fulfillment_number: str | None,
    woo_order_number: str | None,
    woo_order_id: int | None,
    customer_email: str | None,
    local_status: str | None,
    created_by: str | None,
) -> FulfillmentReportFilters:
    return FulfillmentReportFilters(
        date_from=date_from,
        date_to=date_to,
        warehouse=warehouse,
        inventory_location=inventory_location,
        sku=sku,
        barcode=barcode,
        category=category,
        brand=brand,
        fulfillment_number=fulfillment_number,
        woo_order_number=woo_order_number,
        woo_order_id=woo_order_id,
        customer_email=customer_email,
        local_status=local_status,
        created_by=created_by,
    )


def build_sku_order_filters(
    start_date: date | None,
    end_date: date | None,
    sku: str | None,
    brand: str | None,
    category: str | None,
    order_status: str | None,
    woo_status: str | None,
    include_unmatched: bool,
    group_by: str,
    limit: int | None,
    offset: int | None,
) -> SkuOrdersFilters:
    safe_group_by = group_by if group_by in {"sku", "brand", "category", "location"} else "sku"
    return SkuOrdersFilters(
        start_date=start_date,
        end_date=end_date,
        sku=sku,
        brand=brand,
        category=category,
        order_status=order_status,
        woo_status=woo_status,
        include_unmatched=include_unmatched,
        group_by=safe_group_by,
        limit=limit,
        offset=offset,
    )
