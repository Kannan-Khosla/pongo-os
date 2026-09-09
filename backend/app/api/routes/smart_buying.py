from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from app.schemas.smart_buying import SmartBuyingExportRequest
from app.services.pdf_exports import pdf_content_disposition, tabular_pdf_bytes
from app.services.smart_buying import export_purchase_draft, load_smart_buying_snapshot


router = APIRouter(prefix="/smart-buying", tags=["smart-buying"])


@router.get("/snapshot")
def smart_buying_snapshot() -> dict:
    return load_smart_buying_snapshot()


@router.post("/export/{format}")
def export_smart_buying_draft(format: Literal["csv", "pdf"], payload: SmartBuyingExportRequest) -> Response:
    csv_text = export_purchase_draft(payload)
    content = csv_text if format == "csv" else tabular_pdf_bytes(
        csv_text, f"Smart Buying / {payload.po_number} / Planning draft - not sent"
    )
    return Response(
        content=content,
        media_type="text/csv" if format == "csv" else "application/pdf",
        headers={
            "Content-Disposition": pdf_content_disposition(f"pongo-{payload.po_number}.{format}", False),
            "Cache-Control": "no-store",
            "X-Smart-Buying-Mode": "snapshot",
        },
    )
