"""Minimal FastAPI application for the Hyderabad flood prototype."""

from __future__ import annotations

import os
import json

import uvicorn
from fastapi import APIRouter, FastAPI

from .config import (
    DATA_VALIDATION_REPORT,
    PREPROCESSING_REPORT,
    ROADS_GEOJSON,
    ROADS_GRAPHML,
    ROADS_METADATA,
)
from .preprocessing.data_validator import validate_all_datasets

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


def preprocessing_status() -> dict[str, object]:
    if not PREPROCESSING_REPORT.exists():
        return {
            "status": "not_run",
            "generated_at": None,
            "datasets": [],
            "available_processed_datasets": [],
            "feature_counts": {},
            "raster_information": {},
            "rainfall_information": {},
            "warnings": ["Run the GIS preprocessing pipeline to create the report."],
            "errors": [],
        }
    return json.loads(PREPROCESSING_REPORT.read_text(encoding="utf-8"))


def roads_status() -> dict[str, object]:
    output_paths = {
        "geojson": str(ROADS_GEOJSON),
        "graphml": str(ROADS_GRAPHML),
        "metadata": str(ROADS_METADATA),
    }
    if not ROADS_METADATA.exists():
        return {
            "status": "not_ready",
            "ready": False,
            "number_nodes": 0,
            "number_edges": 0,
            "output_paths": output_paths,
            "overpass_errors": [],
        }
    report = json.loads(ROADS_METADATA.read_text(encoding="utf-8"))
    files_ready = all(
        path.exists() for path in (ROADS_GEOJSON, ROADS_GRAPHML, ROADS_METADATA)
    )
    ready = report.get("status") == "ready" and files_ready
    return {
        **report,
        "status": "ready" if ready else report.get("status", "not_ready"),
        "ready": ready,
        "output_paths": output_paths,
    }


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

    @router.get("/data-status")
    def get_data_status() -> dict[str, object]:
        return validate_all_datasets(report_path=DATA_VALIDATION_REPORT)

    @router.get("/preprocessing-status")
    def get_preprocessing_status() -> dict[str, object]:
        return preprocessing_status()

    @router.get("/roads-status")
    def get_roads_status() -> dict[str, object]:
        return roads_status()


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