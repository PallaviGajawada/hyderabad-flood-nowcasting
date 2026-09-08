"""Minimal FastAPI application for the Hyderabad flood prototype."""

from __future__ import annotations

import os
import json

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException

from .config import (
    DATA_VALIDATION_REPORT,
    PREPROCESSING_REPORT,
    ROADS_GEOJSON,
    ROADS_GRAPHML,
    ROADS_METADATA,
    RUNOFF_COEFFICIENTS_PATH,
    RUNOFF_DEPTH_RASTER,
    RUNOFF_METADATA,
    RUNOFF_VOLUME_RASTER,
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


def runoff_status() -> dict[str, object]:
    output_paths = {
        "runoff_depth_mm": str(RUNOFF_DEPTH_RASTER),
        "runoff_volume_m3": str(RUNOFF_VOLUME_RASTER),
        "metadata": str(RUNOFF_METADATA),
        "coefficients": str(RUNOFF_COEFFICIENTS_PATH),
    }
    if not RUNOFF_METADATA.exists():
        return {
            "status": "not_run",
            "model_status": "not_ready",
            "rainfall_provider": None,
            "rainfall_timestamp": None,
            "rainfall_available_start": None,
            "rainfall_available_end": None,
            "output_availability": output_paths,
            "coefficient_configuration_status": (
                "available" if RUNOFF_COEFFICIENTS_PATH.exists() else "missing"
            ),
            "crs": None,
            "raster_dimensions": None,
            "raster_resolution_m": None,
            "warnings": ["Run the rainfall-to-runoff prototype before requesting output statistics."],
            "limitations": [],
        }
    report = json.loads(RUNOFF_METADATA.read_text(encoding="utf-8"))
    files_ready = all(
        path.exists()
        for path in (RUNOFF_DEPTH_RASTER, RUNOFF_VOLUME_RASTER, RUNOFF_METADATA)
    )
    ready = report.get("status") == "ready" and files_ready
    return {
        "status": "ready" if ready else report.get("status", "not_ready"),
        "model_status": "ready" if ready else "not_ready",
        "rainfall_provider": report.get("rainfall_provider"),
        "rainfall_timestamp": report.get("rainfall_timestamp"),
        "rainfall_available_start": report.get("rainfall_available_start"),
        "rainfall_available_end": report.get("rainfall_available_end"),
        "rainfall_scenario": report.get("rainfall_scenario"),
        "output_availability": {
            **report.get("output_availability", {}),
            "coefficients": str(RUNOFF_COEFFICIENTS_PATH),
        },
        "coefficient_configuration_status": report.get(
            "coefficient_configuration_status", "unknown"
        ),
        "crs": report.get("crs"),
        "raster_dimensions": report.get("raster_dimensions"),
        "raster_resolution_m": report.get("raster_resolution_m"),
        "warnings": report.get("warnings", []),
        "limitations": report.get("prototype_assumptions", []),
    }


def runoff_summary() -> dict[str, object]:
    status = runoff_status()
    if not status.get("model_status") == "ready":
        raise HTTPException(
            status_code=404,
            detail="Runoff model has not successfully run; summary statistics are unavailable.",
        )
    report = json.loads(RUNOFF_METADATA.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        **report["statistics"],
        "rainfall_provider": report["rainfall_provider"],
        "rainfall_timestamp": report["rainfall_timestamp"],
        "rainfall_scenario": report["rainfall_scenario"],
        "crs": report["crs"],
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

    @router.get("/runoff-status")
    def get_runoff_status() -> dict[str, object]:
        return runoff_status()

    @router.get("/runoff-summary")
    def get_runoff_summary() -> dict[str, object]:
        return runoff_summary()


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