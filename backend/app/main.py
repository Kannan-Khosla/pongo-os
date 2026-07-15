from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import allocations, business_dashboard, cycle_counts, dashboard, fulfillments, health, import_jobs, insights, inventory, items, locations, orders, picks, receipts, reports, routes, scanner, stock_movements, ui, woocommerce
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pongo Inventory OS API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(business_dashboard.router, prefix="/api")
    app.include_router(insights.router, prefix="/api")
    app.include_router(items.router, prefix="/api")
    app.include_router(allocations.router, prefix="/api")
    app.include_router(picks.router, prefix="/api")
    app.include_router(fulfillments.router, prefix="/api")
    app.include_router(woocommerce.router, prefix="/api")
    app.include_router(inventory.router, prefix="/api")
    app.include_router(import_jobs.router, prefix="/api")
    app.include_router(locations.router, prefix="/api")
    app.include_router(cycle_counts.router, prefix="/api")
    app.include_router(receipts.router, prefix="/api")
    app.include_router(stock_movements.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(routes.router, prefix="/api")
    app.include_router(scanner.router, prefix="/api")
    app.include_router(ui.router, prefix="/api")
    return app


app = create_app()
