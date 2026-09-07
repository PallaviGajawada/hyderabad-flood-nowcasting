"""Minimal FastAPI application for the Hyderabad flood prototype."""

from __future__ import annotations

import os

import uvicorn
from fastapi import APIRouter, FastAPI

from .config import DATASETS

SYSTEM_NAME = "Hyderabad Urban Flood Nowcasting System"
MODEL_NOT_IMPLEMENTED = "Model not implemented yet."

app = FastAPI(
    title=SYSTEM_NAME,
    description=(
        "Initial API foundation for a 0–3 hour urban flood nowcasting "
        "prototype. Model outputs are not implemented."
    ),
    version="0.1.0",
)


def system_status() -> dict[str, object]:
    return {
        "system": SYSTEM_NAME,
        "status": "initial prototype",
        "forecast_horizon_hours": 3,
    }


def health_status() -> dict[str, str]:
    return {"status": "ok"}


def model_placeholder() -> dict[str, str]:
    return {"status": "not_implemented", "message": MODEL_NOT_IMPLEMENTED}


def register_routes(router: APIRouter) -> None:
    @router.get("/")
    def get_system_status() -> dict[str, object]:
        return system_status()

    @router.get("/health")
    def get_health() -> dict[str, str]:
        return health_status()

    @router.get("/healthz")
    def get_healthz() -> dict[str, str]:
        return health_status()

    @router.get("/forecast")
    def get_forecast() -> dict[str, str]:
        return model_placeholder()

    @router.get("/flood-depth")
    def get_flood_depth() -> dict[str, str]:
        return model_placeholder()

    @router.get("/safe-route")
    def get_safe_route() -> dict[str, str]:
        return model_placeholder()


# The unprefixed routes make the Python app easy to run directly. The /api
# router matches the workspace's proxied API service path.
register_routes(app.router)
api_router = APIRouter(prefix="/api")
register_routes(api_router)
app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )