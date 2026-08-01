import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import allocations, auth, business_dashboard, cycle_counts, dashboard, fulfillments, health, import_jobs, insights, inventory, items, locations, orders, picks, receipts, reports, routes, scanner, stock_movements, ui, woocommerce
from app.core.config import get_settings
from app.services.woocommerce_order_reconciliation import reconciliation_should_start, run_order_reconciliation_scheduler
from app.services.woocommerce_stock_sync_jobs import run_stock_sync_job_scheduler, stock_sync_scheduler_should_start
from app.services.auth import require_authenticated_user

logger = logging.getLogger("pongo.http")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    stop_event = asyncio.Event()
    task = None
    stock_sync_task = None
    if reconciliation_should_start(settings):
        task = asyncio.create_task(run_order_reconciliation_scheduler(settings, stop_event))
    if stock_sync_scheduler_should_start(settings):
        stock_sync_task = asyncio.create_task(run_stock_sync_job_scheduler(settings, stop_event))
    app.state.order_reconciliation_task = task
    app.state.stock_sync_task = stock_sync_task
    try:
        yield
    finally:
        if task is not None:
            stop_event.set()
            await task
        if stock_sync_task is not None:
            stop_event.set()
            await stock_sync_task
        app.state.order_reconciliation_task = None
        app.state.stock_sync_task = None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pongo Inventory OS API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(json.dumps({"event": "http_request", "request_id": request_id, "method": request.method, "path": request.url.path, "status": 500}))
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(json.dumps({"event": "http_request", "request_id": request_id, "method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": round((perf_counter() - started) * 1000, 2)}))
        return response

    protected = [Depends(require_authenticated_user)]
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api", dependencies=protected)
    app.include_router(business_dashboard.router, prefix="/api", dependencies=protected)
    app.include_router(insights.router, prefix="/api", dependencies=protected)
    app.include_router(items.router, prefix="/api", dependencies=protected)
    app.include_router(allocations.router, prefix="/api", dependencies=protected)
    app.include_router(picks.router, prefix="/api", dependencies=protected)
    app.include_router(fulfillments.router, prefix="/api", dependencies=protected)
    app.include_router(woocommerce.router, prefix="/api", dependencies=protected)
    app.include_router(inventory.router, prefix="/api", dependencies=protected)
    app.include_router(import_jobs.router, prefix="/api", dependencies=protected)
    app.include_router(locations.router, prefix="/api", dependencies=protected)
    app.include_router(cycle_counts.router, prefix="/api", dependencies=protected)
    app.include_router(receipts.router, prefix="/api", dependencies=protected)
    app.include_router(stock_movements.router, prefix="/api", dependencies=protected)
    app.include_router(orders.router, prefix="/api", dependencies=protected)
    app.include_router(reports.router, prefix="/api", dependencies=protected)
    app.include_router(routes.router, prefix="/api", dependencies=protected)
    app.include_router(scanner.router, prefix="/api", dependencies=protected)
    app.include_router(ui.router, prefix="/api", dependencies=protected)
    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
