from fastapi import APIRouter

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
def list_items_placeholder() -> dict[str, str]:
    return {"module": "items", "status": "placeholder"}
