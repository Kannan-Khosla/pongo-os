from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, items, locations, orders, receipts, reports, routes
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
    app.include_router(items.router, prefix="/api")
    app.include_router(locations.router, prefix="/api")
    app.include_router(receipts.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(routes.router, prefix="/api")
    return app


app = create_app()
