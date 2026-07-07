from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import DashboardActivityItem, DashboardResponse, DashboardWarningGroup
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(limit: int = 25, db: Session = Depends(get_db)) -> DashboardResponse:
    return build_dashboard(db, activity_limit=limit)


@router.get("/summary", response_model=DashboardResponse)
def dashboard_summary(limit: int = 25, db: Session = Depends(get_db)) -> DashboardResponse:
    return build_dashboard(db, activity_limit=limit)


@router.get("/activity", response_model=list[DashboardActivityItem])
def dashboard_activity(limit: int = 25, db: Session = Depends(get_db)) -> list[DashboardActivityItem]:
    return build_dashboard(db, activity_limit=limit).activity


@router.get("/warnings", response_model=list[DashboardWarningGroup])
def dashboard_warnings(db: Session = Depends(get_db)) -> list[DashboardWarningGroup]:
    return build_dashboard(db, activity_limit=1).warnings
