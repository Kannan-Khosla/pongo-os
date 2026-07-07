from fastapi import APIRouter

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.get("")
def list_receipts_placeholder() -> dict[str, str]:
    return {"module": "receipts", "status": "placeholder"}
