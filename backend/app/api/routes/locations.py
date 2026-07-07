from fastapi import APIRouter

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("")
def list_locations_placeholder() -> dict[str, str]:
    return {"module": "locations", "status": "placeholder"}
