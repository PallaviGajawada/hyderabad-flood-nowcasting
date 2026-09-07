"""Reproducible orchestration for the available GIS preprocessing stages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import (
    DATASETS,
    MODEL_CRS,
    PREPROCESSED_ROOT,
    PREPROCESSING_REPORT,
    WEB_CRS,
)
from .dem_processor import process_dem
from .drainage_processor import process_drainage
from .landcover_processor import process_landcover
from .rainfall_processor import process_rainfall
from .waterbody_processor import process_waterbodies


def _flatten(result: dict[str, Any]) -> list[dict[str, Any]]:
    if "datasets" in result:
        return list(result["datasets"])
    return [result]


def _write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")


def run_preprocessing_pipeline(
    *,
    report_path: Path = PREPROCESSING_REPORT,
) -> dict[str, Any]:
    """Run every preprocessing stage supported by the available inputs."""

    stage_results: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = [
        "Road processing was not run because the Hyderabad roads GeoPackage is missing.",
        "Historical flood processing was not run because the flood-location KML is missing.",
        "No hydraulic parameters, flood simulation, or safe-route model were created.",
    ]
    stages = (
        ("dem", process_dem),
        ("landcover", process_landcover),
        ("rainfall", process_rainfall),
        ("drainage", process_drainage),
        ("waterbodies", process_waterbodies),
    )
    for stage_name, processor in stages:
        try:
            stage_results.extend(_flatten(processor()))
        except Exception as exc:
            errors.append(f"{stage_name}: {type(exc).__name__}: {exc}")

    available_outputs = sorted(
        str(path)
        for path in PREPROCESSED_ROOT.rglob("*")
        if path.is_file() and path != report_path
    )
    feature_counts = {
        item["dataset_key"]: {
            "before": item.get("feature_count_before"),
            "after": item.get("feature_count_after"),
        }
        for item in stage_results
        if item.get("feature_count_before") is not None
    }
    raster_information = {
        item["dataset_key"]: item["raster_information"]
        for item in stage_results
        if item.get("raster_information")
    }
    rainfall_information = next(
        (
            item["rainfall_information"]
            for item in stage_results
            if item.get("rainfall_information")
        ),
        {},
    )
    for item in stage_results:
        warnings.extend(item.get("warnings", []))
        errors.extend(item.get("errors", []))
    report = {
        "status": "failed" if errors else "completed_with_warnings",
        "generated_at": datetime.now(UTC).isoformat(),
        "spatial_reference_strategy": {
            "web_interchange_crs": WEB_CRS,
            "projected_model_crs": MODEL_CRS,
            "reason": "EPSG:4326 is retained for web/interchange GeoJSON; EPSG:32644 is used for metres-based terrain and length calculations.",
        },
        "datasets": stage_results,
        "available_processed_datasets": available_outputs,
        "feature_counts": feature_counts,
        "raster_information": raster_information,
        "rainfall_information": rainfall_information,
        "warnings": warnings,
        "errors": errors,
        "inputs_not_processed": {
            "roads": str(DATASETS.roads),
            "historical_floods": str(DATASETS.historical_floods),
        },
    }
    _write_report(report, report_path)
    if errors:
        raise RuntimeError(
            f"GIS preprocessing failed for {len(errors)} stage(s); see {report_path}."
        )
    return report