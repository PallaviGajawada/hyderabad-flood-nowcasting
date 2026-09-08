"""Minimal FastAPI application for the Hyderabad flood prototype."""

from __future__ import annotations

import os
import json

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException

from .config import (
    DATA_VALIDATION_REPORT,
    DRAINAGE_ASSUMPTIONS_PATH,
    DRAINAGE_CAPACITY_INDEX_RASTER,
    DRAINAGE_INTERACTION_RASTER,
    DRAINAGE_METADATA,
    DRAINAGE_REMOVED_VOLUME_RASTER,
    DISPLAY_DEPTH_CM,
    FLOOD_DEPTH_ASSUMPTIONS_PATH,
    FLOOD_DEPTH_METADATA,
    FLOOD_RISK_CLASS_RASTER,
    PREPROCESSING_REPORT,
    RAW_EQUIVALENT_DEPTH_CM,
    RAW_EQUIVALENT_DEPTH_MM,
    REMAINING_SURFACE_WATER_VOLUME_RASTER,
    ROAD_FLOOD_RISK_GEOJSON,
    ROADS_GEOJSON,
    ROADS_GRAPHML,
    ROADS_METADATA,
    RUNOFF_COEFFICIENTS_PATH,
    RUNOFF_DEPTH_RASTER,
    RUNOFF_METADATA,
    RUNOFF_VOLUME_RASTER,
    FLOW_ACCUMULATION_RASTER,
    FLOW_DIRECTION_RASTER,
    NALA_INTERACTION_RASTER,
    SURFACE_WATER_DEPTH_CM,
    SURFACE_WATER_DEPTH_MM,
    SURFACE_WATER_METADATA,
    SURFACE_WATER_VOLUME,
    SURFACE_WATER_ASSUMPTIONS_PATH,
)
from .preprocessing.data_validator import validate_all_datasets
from .models.forecast_model import forecast_status, forecast_summary
from .routing.safe_route import calculate_safe_route

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


def surface_water_status() -> dict[str, object]:
    output_paths = {
        "surface_water_depth_mm": str(SURFACE_WATER_DEPTH_MM),
        "surface_water_depth_cm": str(SURFACE_WATER_DEPTH_CM),
        "surface_water_volume_m3": str(SURFACE_WATER_VOLUME),
        "flow_direction": str(FLOW_DIRECTION_RASTER),
        "flow_accumulation": str(FLOW_ACCUMULATION_RASTER),
        "nala_interaction": str(NALA_INTERACTION_RASTER),
        "metadata": str(SURFACE_WATER_METADATA),
    }
    if not SURFACE_WATER_METADATA.exists():
        return {
            "status": "not_run",
            "model_status": "not_ready",
            "ready": False,
            "output_availability": output_paths,
            "dem_information": {},
            "runoff_scenario": None,
            "terrain_routing_method": None,
            "drainage_assumption_status": (
                "available" if SURFACE_WATER_ASSUMPTIONS_PATH.exists() else "missing"
            ),
            "warnings": ["Run the surface-water model before requesting its summary."],
            "limitations": [],
        }
    report = json.loads(SURFACE_WATER_METADATA.read_text(encoding="utf-8"))
    files_ready = all(
        path.exists()
        for path in (
            SURFACE_WATER_DEPTH_MM,
            SURFACE_WATER_DEPTH_CM,
            SURFACE_WATER_VOLUME,
            FLOW_DIRECTION_RASTER,
            FLOW_ACCUMULATION_RASTER,
            NALA_INTERACTION_RASTER,
            SURFACE_WATER_METADATA,
        )
    )
    ready = report.get("status") == "ready" and files_ready
    return {
        "status": "ready" if ready else report.get("status", "not_ready"),
        "model_status": "ready" if ready else "not_ready",
        "ready": ready,
        "output_availability": report.get("output_availability", output_paths),
        "dem_information": {
            "source": report.get("dem_source"),
            "crs": report.get("crs"),
            "raster_dimensions": report.get("raster_dimensions"),
            "raster_resolution_m": report.get("raster_resolution_m"),
            "nodata_handling": report.get("nodata_handling"),
        },
        "runoff_scenario": {
            "timestamp": report.get("rainfall_timestamp"),
            "description": report.get("rainfall_scenario"),
            "source": report.get("runoff_source"),
        },
        "terrain_routing_method": report.get("terrain_routing_method"),
        "drainage_assumption_status": (
            "prototype_assumption"
            if report.get("drainage_assumptions", {}).get("status")
            == "prototype_assumption"
            else "unknown"
        ),
        "warnings": report.get("warnings", []),
        "limitations": report.get("limitations", []),
    }


def surface_water_summary() -> dict[str, object]:
    status = surface_water_status()
    if status.get("model_status") != "ready":
        raise HTTPException(
            status_code=404,
            detail="Surface-water model has not successfully run; summary statistics are unavailable.",
        )
    report = json.loads(SURFACE_WATER_METADATA.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        "rainfall_timestamp": report.get("rainfall_timestamp"),
        "rainfall_scenario": report.get("rainfall_scenario"),
        **report["statistics"],
    }


def drainage_status() -> dict[str, object]:
    output_paths = {
        "drainage_interaction": str(DRAINAGE_INTERACTION_RASTER),
        "drainage_capacity_index": str(DRAINAGE_CAPACITY_INDEX_RASTER),
        "metadata": str(DRAINAGE_METADATA),
        "assumptions": str(DRAINAGE_ASSUMPTIONS_PATH),
    }
    if not DRAINAGE_METADATA.exists():
        return {
            "status": "not_run",
            "model_status": "not_ready",
            "ready": False,
            "output_availability": output_paths,
            "assumption_status": (
                "available" if DRAINAGE_ASSUMPTIONS_PATH.exists() else "missing"
            ),
            "warnings": ["Run the drainage model before requesting its summary."],
            "limitations": [],
        }
    report = json.loads(DRAINAGE_METADATA.read_text(encoding="utf-8"))
    files_ready = all(
        path.exists()
        for path in (
            DRAINAGE_INTERACTION_RASTER,
            DRAINAGE_CAPACITY_INDEX_RASTER,
            DRAINAGE_METADATA,
        )
    )
    ready = report.get("status") == "ready" and files_ready
    return {
        "status": "ready" if ready else report.get("status", "not_ready"),
        "model_status": "ready" if ready else "not_ready",
        "ready": ready,
        "output_availability": report.get("output_availability", output_paths),
        "assumption_status": (
            "prototype_assumption"
            if report.get("source") == "prototype_assumption"
            else "unknown"
        ),
        "crs": report.get("crs"),
        "raster_dimensions": report.get("raster_dimensions"),
        "raster_resolution_m": report.get("raster_resolution_m"),
        "statistics": report.get("statistics", {}),
        "warnings": report.get("warnings", []),
        "limitations": report.get("limitations", []),
    }


def drainage_summary() -> dict[str, object]:
    status = drainage_status()
    if status.get("model_status") != "ready":
        raise HTTPException(
            status_code=404,
            detail="Drainage model has not successfully run; summary statistics are unavailable.",
        )
    report = json.loads(DRAINAGE_METADATA.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        **report["statistics"],
        "warnings": report.get("warnings", []),
        "limitations": report.get("limitations", []),
    }


def flood_depth_status() -> dict[str, object]:
    output_paths = {
        "raw_equivalent_depth_mm": str(RAW_EQUIVALENT_DEPTH_MM),
        "raw_equivalent_depth_cm": str(RAW_EQUIVALENT_DEPTH_CM),
        "display_depth_cm": str(DISPLAY_DEPTH_CM),
        "flood_risk_class": str(FLOOD_RISK_CLASS_RASTER),
        "drainage_removed_volume_m3": str(DRAINAGE_REMOVED_VOLUME_RASTER),
        "remaining_surface_water_volume_m3": str(REMAINING_SURFACE_WATER_VOLUME_RASTER),
        "road_flood_risk": str(ROAD_FLOOD_RISK_GEOJSON),
        "metadata": str(FLOOD_DEPTH_METADATA),
        "assumptions": str(FLOOD_DEPTH_ASSUMPTIONS_PATH),
    }
    if not FLOOD_DEPTH_METADATA.exists():
        return {
            "status": "not_run",
            "model_status": "not_ready",
            "ready": False,
            "output_availability": output_paths,
            "assumption_status": (
                "available" if FLOOD_DEPTH_ASSUMPTIONS_PATH.exists() else "missing"
            ),
            "warnings": ["Run the flood-depth model before requesting its summary."],
            "limitations": [],
        }
    report = json.loads(FLOOD_DEPTH_METADATA.read_text(encoding="utf-8"))
    files_ready = all(
        path.exists()
        for path in (
            RAW_EQUIVALENT_DEPTH_MM,
            RAW_EQUIVALENT_DEPTH_CM,
            DISPLAY_DEPTH_CM,
            FLOOD_RISK_CLASS_RASTER,
            DRAINAGE_REMOVED_VOLUME_RASTER,
            REMAINING_SURFACE_WATER_VOLUME_RASTER,
            ROAD_FLOOD_RISK_GEOJSON,
            FLOOD_DEPTH_METADATA,
        )
    )
    ready = report.get("status") == "ready" and files_ready
    return {
        "status": "ready" if ready else report.get("status", "not_ready"),
        "model_status": "ready" if ready else "not_ready",
        "ready": ready,
        "output_availability": report.get("output_availability", output_paths),
        "assumption_status": (
            "prototype_assumption"
            if report.get("source") == "prototype_assumption"
            else "unknown"
        ),
        "grid": report.get("grid", {}),
        "statistics": report.get("statistics", {}),
        "warnings": report.get("warnings", []),
        "limitations": report.get("limitations", []),
    }


def flood_depth_summary() -> dict[str, object]:
    status = flood_depth_status()
    if status.get("model_status") != "ready":
        raise HTTPException(
            status_code=404,
            detail="Flood-depth model has not successfully run; summary statistics are unavailable.",
        )
    report = json.loads(FLOOD_DEPTH_METADATA.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        **report["statistics"],
        "road_flood_risk": report.get("road_flood_risk", {}),
        "warnings": report.get("warnings", []),
        "limitations": report.get("limitations", []),
    }


def road_flood_risk() -> dict[str, object]:
    status = flood_depth_status()
    if status.get("model_status") != "ready":
        raise HTTPException(
            status_code=404,
            detail="Flood-depth model has not successfully run; road flood-risk data are unavailable.",
        )
    report = json.loads(FLOOD_DEPTH_METADATA.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        "output": str(ROAD_FLOOD_RISK_GEOJSON),
        **report.get("road_flood_risk", {}),
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

    @router.get("/forecast-status")
    def get_forecast_status() -> dict[str, object]:
        return forecast_status()

    @router.get("/forecast-summary")
    def get_forecast_summary() -> dict[str, object]:
        try:
            return forecast_summary()
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/forecast")
    def get_forecast() -> dict[str, object]:
        return forecast_summary()

    @router.get("/flood-depth")
    def get_flood_depth() -> dict[str, str]:
        return model_placeholder()

    @router.get("/safe-route")
    def get_safe_route(
        source_lat: float,
        source_lon: float,
        destination_lat: float,
        destination_lon: float,
        forecast_minutes: int = 0,
    ) -> dict[str, object]:
        try:
            return calculate_safe_route(
                source_lat=source_lat,
                source_lon=source_lon,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
                forecast_minutes=forecast_minutes,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

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

    @router.get("/surface-water-status")
    def get_surface_water_status() -> dict[str, object]:
        return surface_water_status()

    @router.get("/surface-water-summary")
    def get_surface_water_summary() -> dict[str, object]:
        return surface_water_summary()

    @router.get("/drainage-status")
    def get_drainage_status() -> dict[str, object]:
        return drainage_status()

    @router.get("/drainage-summary")
    def get_drainage_summary() -> dict[str, object]:
        return drainage_summary()

    @router.get("/flood-depth-status")
    def get_flood_depth_status() -> dict[str, object]:
        return flood_depth_status()

    @router.get("/flood-depth-summary")
    def get_flood_depth_summary() -> dict[str, object]:
        return flood_depth_summary()

    @router.get("/road-flood-risk")
    def get_road_flood_risk() -> dict[str, object]:
        return road_flood_risk()


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