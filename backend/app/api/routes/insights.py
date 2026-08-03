from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.insights import InsightResponse
from app.services.insights import EXPORT_COLUMNS, build_insight, export_insight_csv

router = APIRouter(prefix="/insights", tags=["insights"])


def insight_params(
    start_date: str | None = None,
    end_date: str | None = None,
    compare_start_date: str | None = None,
    compare_end_date: str | None = None,
    granularity: Literal["day", "week"] = "day",
    brand: str | None = None,
    category: str | None = None,
    sku: str | None = None,
    customer_email: str | None = None,
    city: str | None = None,
    postal_code: str | None = None,
    payment_method: str | None = None,
    order_status: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return {
        "start_date": start_date,
        "end_date": end_date,
        "compare_start_date": compare_start_date,
        "compare_end_date": compare_end_date,
        "granularity": granularity,
        "brand": brand,
        "category": category,
        "sku": sku,
        "customer_email": customer_email,
        "city": city,
        "postal_code": postal_code,
        "payment_method": payment_method,
        "order_status": order_status,
        "limit": limit,
        "offset": offset,
    }


def route_for(dashboard: str):
    def handler(params: dict[str, Any] = Depends(insight_params), db: Session = Depends(get_db)) -> InsightResponse:
        return build_insight(db, dashboard, params)

    return handler


router.add_api_route("/overview", route_for("overview"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/orders-revenue", route_for("orders-revenue"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/customer-metrics", route_for("customer-metrics"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/customer-segmentation", route_for("customer-segmentation"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/product-sku", route_for("product-sku"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/subscriptions", route_for("subscriptions"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/subscription-products", route_for("subscription-products"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/inventory-forecasting", route_for("inventory-forecasting"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/coupons", route_for("coupons"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/payment-health", route_for("payment-health"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/geography", route_for("geography"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/product-affinity", route_for("product-affinity"), methods=["GET"], response_model=InsightResponse)
router.add_api_route("/reorder-forecast", route_for("reorder-forecast"), methods=["GET"], response_model=InsightResponse)


@router.get("/{dashboard}/export")
def export_dashboard(dashboard: str, params: dict[str, Any] = Depends(insight_params), db: Session = Depends(get_db)) -> Response:
    if dashboard not in EXPORT_COLUMNS:
        return Response("Export not available for this dashboard.\n", status_code=404, media_type="text/plain")
    csv_body = export_insight_csv(db, dashboard, params)
    return Response(csv_body, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="pongo-insights-{dashboard}.csv"'})
