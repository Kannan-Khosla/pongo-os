from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.receipts import Receipt, ReceiptItem
from app.schemas.receipts import BulkReceiptCommitRequest, BulkReceiptRequest, DirectReceiptCommitRequest, DirectReceiptCommitResponse, DirectReceiptPreviewResponse, DirectReceiptRequest, InvoiceReceiptCommitRequest, InvoiceReceiptReversalRequest, ReceiptDetail, ReceiptListResponse
from app.services.bulk_receiving import commit_bulk_receipt, export_receipt_csv, preview_bulk_receipt
from app.services.auth import authenticated_actor
from app.services.receiving import build_direct_receipt_preview, commit_direct_receipt, receipt_to_detail, receipt_to_read
from app.services.invoice_receiving import commit_invoice_receipt, invoice_reversal_preview, preview_invoice_pdf, revert_invoice_receipt
from app.services.pdf_exports import pdf_content_disposition, tabular_pdf_bytes
from app.services.stock_mutation_guard import IdempotencyConflict

router = APIRouter(prefix="/receipts", tags=["receipts"])
MAX_INVOICE_PDF_BYTES = 10 * 1024 * 1024


async def read_invoice_upload(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.casefold().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload a PDF invoice.")
    document = await file.read(MAX_INVOICE_PDF_BYTES + 1)
    if len(document) > MAX_INVOICE_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Invoice PDFs must be 10 MB or smaller.")
    if not document.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")
    return document


@router.post("/direct/preview", response_model=DirectReceiptPreviewResponse)
def preview_direct_receipt(payload: DirectReceiptRequest, db: Session = Depends(get_db)) -> DirectReceiptPreviewResponse:
    return build_direct_receipt_preview(payload, db)


@router.post("/direct/commit", response_model=DirectReceiptCommitResponse)
def commit_direct_receipt_endpoint(payload: DirectReceiptCommitRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> DirectReceiptCommitResponse:
    try:
        receipt, movement_count, total_quantity, total_value, warnings = commit_direct_receipt(payload.model_copy(update={"created_by": actor}), db)
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DirectReceiptCommitResponse(
        receipt_id=receipt.id,
        receipt_number=receipt.receipt_number,
        status=receipt.status or "posted",
        total_lines=len(receipt.items),
        total_quantity_received=float(total_quantity),
        total_inventory_value=float(total_value),
        created_movements=movement_count,
        warnings=warnings,
    )


@router.post("/bulk/preview")
def preview_bulk_receipt_endpoint(payload: BulkReceiptRequest, db: Session = Depends(get_db)) -> dict:
    return preview_bulk_receipt(payload.model_dump(), db)


@router.post("/bulk/commit")
def commit_bulk_receipt_endpoint(payload: BulkReceiptCommitRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    try:
        return commit_bulk_receipt({**payload.model_dump(), "created_by": actor}, db)
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/invoice/preview")
async def preview_invoice_receipt_endpoint(
    file: UploadFile = File(...),
    warehouse: str = Form("Main Warehouse"),
    inventory_location: str = Form(...),
    db: Session = Depends(get_db),
) -> dict:
    return preview_invoice_pdf(await read_invoice_upload(file), db, warehouse=warehouse, inventory_location=inventory_location)


@router.post("/invoice/commit")
async def commit_invoice_receipt_endpoint(
    payload: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict:
    try:
        validated = InvoiceReceiptCommitRequest.model_validate_json(payload)
        return commit_invoice_receipt(validated, await read_invoice_upload(file), db, actor)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/invoice/{receipt_id}/reversal/preview")
def preview_invoice_reversal_endpoint(receipt_id: int, db: Session = Depends(get_db)) -> dict:
    return invoice_reversal_preview(receipt_id, db)


@router.post("/invoice/{receipt_id}/reversal/commit")
def commit_invoice_reversal_endpoint(
    receipt_id: int,
    payload: InvoiceReceiptReversalRequest,
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict:
    try:
        return revert_invoice_receipt(receipt_id, payload, db, actor)
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=ReceiptListResponse)
def list_receipts(
    receipt_type: str | None = None,
    status: str | None = None,
    warehouse: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    reference_number: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ReceiptListResponse:
    statement = select(Receipt)
    if receipt_type:
        statement = statement.where(Receipt.receipt_type == receipt_type)
    if status:
        statement = statement.where(Receipt.status == status)
    if warehouse:
        statement = statement.where(Receipt.warehouse == warehouse)
    if date_from:
        statement = statement.where(Receipt.received_date >= date_from)
    if date_to:
        statement = statement.where(Receipt.received_date <= date_to)
    if reference_number:
        statement = statement.where(Receipt.reference_number == reference_number)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    total_pages = (total + page_size - 1) // page_size
    effective_page = min(page, max(total_pages, 1))
    receipts = list(
        db.scalars(
            statement
            .options(selectinload(Receipt.items))
            .order_by(Receipt.created_at.desc(), Receipt.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return ReceiptListResponse(
        receipts=[receipt_to_read(receipt) for receipt in receipts],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(receipts),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/{receipt_id}", response_model=ReceiptDetail)
def get_receipt(receipt_id: int, db: Session = Depends(get_db)) -> ReceiptDetail:
    receipt = db.scalars(
        select(Receipt)
        .where(Receipt.id == receipt_id)
        .options(selectinload(Receipt.items).selectinload(ReceiptItem.inventory_item), selectinload(Receipt.items).selectinload(ReceiptItem.inventory_location))
    ).one_or_none()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt_to_detail(receipt)


@router.get("/{receipt_id}/detail", response_model=ReceiptDetail)
def get_receipt_detail(receipt_id: int, db: Session = Depends(get_db)) -> ReceiptDetail:
    return get_receipt(receipt_id, db)


@router.get("/{receipt_id}/pdf")
def receipt_pdf(receipt_id: int, preview: bool = False, db: Session = Depends(get_db)) -> Response:
    receipt = db.scalars(
        select(Receipt)
        .where(Receipt.id == receipt_id)
        .options(selectinload(Receipt.items).selectinload(ReceiptItem.inventory_item), selectinload(Receipt.items).selectinload(ReceiptItem.inventory_location))
    ).one_or_none()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    filename = f"pongo-{receipt.receipt_number}-receipt.pdf"
    return Response(
        content=tabular_pdf_bytes(export_receipt_csv(receipt), f"Receipt {receipt.receipt_number}"),
        media_type="application/pdf",
        headers={"Content-Disposition": pdf_content_disposition(filename, preview)},
    )


@router.get("/{receipt_id}/export")
def export_receipt(receipt_id: int, db: Session = Depends(get_db)) -> Response:
    receipt = db.scalars(
        select(Receipt)
        .where(Receipt.id == receipt_id)
        .options(selectinload(Receipt.items).selectinload(ReceiptItem.inventory_item), selectinload(Receipt.items).selectinload(ReceiptItem.inventory_location))
    ).one_or_none()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return Response(
        content=export_receipt_csv(receipt),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="pongo-{receipt.receipt_number}-receipt.csv"'},
    )
