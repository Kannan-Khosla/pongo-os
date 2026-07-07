from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports_placeholder() -> dict[str, str]:
    return {"module": "reports", "status": "placeholder"}
