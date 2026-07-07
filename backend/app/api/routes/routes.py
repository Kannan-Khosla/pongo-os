from fastapi import APIRouter

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("")
def list_routes_placeholder() -> dict[str, str]:
    return {"module": "routes", "status": "placeholder"}
