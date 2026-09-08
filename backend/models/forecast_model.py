"""Deterministic Step 7 forecast scenarios derived from the Step 6 baseline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from ..config import (
    DISPLAY_DEPTH_CM,
    FLOOD_DEPTH_ASSUMPTIONS_PATH,
    FLOOD_RISK_CLASS_RASTER,
    FORECAST_ASSUMPTIONS_PATH,
    FORECAST_METADATA,
    FORECAST_OUTPUT_ROOT,
)
from .flood_depth_model import classify_risk, load_flood_depth_assumptions


def load_forecast_assumptions(
    path: Path = FORECAST_ASSUMPTIONS_PATH,
) -> dict[str, Any]:
    assumptions = json.loads(path.read_text(encoding="utf-8"))
    if assumptions.get("status") != "prototype_assumption":
        raise ValueError("Forecast assumptions must be marked prototype_assumption.")
    horizons = assumptions.get("forecast_horizons_minutes")
    if horizons != [0, 30, 60, 90, 120, 150, 180]:
        raise ValueError("Forecast horizons must contain the seven Step 7 horizons.")
    for key in (
        "rainfall_persistence_factor_per_30_min",
        "surface_water_persistence_factor_per_30_min",
        "drainage_recession_factor_per_30_min",
    ):
        value = float(assumptions[key])
        if not 0 < value <= 1:
            raise ValueError(f"{key} must be greater than 0 and at most 1.")
    return assumptions


def _safe_statistics(
    depth: np.ndarray,
    risk: np.ndarray,
    *,
    depth_nodata: float,
    risk_nodata: int,
) -> dict[str, Any]:
    valid = (depth != depth_nodata) & np.isfinite(depth)
    valid_depth = depth[valid]
    valid_risk = risk[valid & (risk != risk_nodata)]
    risk_classes, risk_counts = np.unique(valid_risk, return_counts=True)
    return {
        "valid_cell_count": int(valid_depth.size),
        "maximum_depth_cm": float(valid_depth.max()) if valid_depth.size else None,
        "mean_depth_cm": float(valid_depth.mean()) if valid_depth.size else None,
        "affected_cell_count": int(np.count_nonzero(valid_depth > 0)),
        "risk_class_counts": {
            str(int(key)): int(value) for key, value in zip(risk_classes, risk_counts)
        },
    }


def forecast_factor(minutes: int, assumptions: dict[str, Any]) -> float:
    """Return the transparent combined persistence/decay factor."""
    steps = minutes / 30
    return float(
        float(assumptions["rainfall_persistence_factor_per_30_min"]) ** steps
        * float(assumptions["surface_water_persistence_factor_per_30_min"]) ** steps
        * float(assumptions["drainage_recession_factor_per_30_min"]) ** steps
    )


def run_forecast(
    *,
    assumptions_path: Path = FORECAST_ASSUMPTIONS_PATH,
    baseline_path: Path = DISPLAY_DEPTH_CM,
    risk_baseline_path: Path = FLOOD_RISK_CLASS_RASTER,
    metadata_path: Path = FORECAST_METADATA,
) -> dict[str, Any]:
    """Generate all forecast rasters and metadata without changing Step 6 outputs."""
    assumptions = load_forecast_assumptions(assumptions_path)
    flood_assumptions = load_flood_depth_assumptions(FLOOD_DEPTH_ASSUMPTIONS_PATH)
    if not baseline_path.exists() or not risk_baseline_path.exists():
        raise FileNotFoundError("Step 6 flood-depth rasters are required for forecasting.")

    with rasterio.open(baseline_path) as baseline:
        baseline_array = baseline.read(1).astype(np.float32)
        baseline_profile = baseline.profile.copy()
        baseline_nodata = float(baseline.nodata if baseline.nodata is not None else -9999)
        baseline_transform = baseline.transform
        baseline_crs = str(baseline.crs)
        baseline_shape = [baseline.height, baseline.width]
    with rasterio.open(risk_baseline_path) as risk_source:
        risk_nodata = int(risk_source.nodata if risk_source.nodata is not None else -9999)

    valid_baseline = (baseline_array != baseline_nodata) & np.isfinite(baseline_array)
    baseline_array = np.where(valid_baseline, np.maximum(baseline_array, 0), baseline_nodata)
    metadata: dict[str, Any] = {
        "status": "ready",
        "source": "deterministic_step6_persistence_decay",
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline": str(baseline_path),
        "grid": {
            "crs": baseline_crs,
            "height": baseline_shape[0],
            "width": baseline_shape[1],
            "transform": list(baseline_transform)[:6],
            "nodata": baseline_nodata,
        },
        "rainfall": {
            "provider": assumptions["rainfall_provider"],
            "description": "Historical 2024 IMD daily gridded rainfall; not real-time radar.",
            "scenario": "Persistence/decay projection of the Step 6 baseline.",
        },
        "assumptions": assumptions,
        "horizons": [],
        "warnings": [
            "Forecasts are deterministic scenario projections, not real-time radar nowcasts.",
            "Depths are prototype accumulated surface-water equivalents, not observed street depths.",
            "Hydraulic measurements and validated drainage-network parameters are not available.",
        ],
    }

    for minutes in assumptions["forecast_horizons_minutes"]:
        factor = forecast_factor(int(minutes), assumptions)
        depth = np.where(
            valid_baseline,
            np.clip(baseline_array * factor, 0, float(flood_assumptions["display_depth_cap_cm"])),
            baseline_nodata,
        ).astype(np.float32)
        risk = np.full(depth.shape, risk_nodata, dtype=np.int16)
        risk_valid = valid_baseline
        risk[risk_valid] = classify_risk(
            depth[risk_valid],
            low_threshold_cm=float(flood_assumptions["low_threshold_cm"]),
            moderate_threshold_cm=float(flood_assumptions["moderate_threshold_cm"]),
            high_threshold_cm=float(flood_assumptions["high_threshold_cm"]),
            severe_threshold_cm=float(flood_assumptions["severe_threshold_cm"]),
        )

        horizon_dir = FORECAST_OUTPUT_ROOT / f"tplus_{int(minutes):03d}"
        horizon_dir.mkdir(parents=True, exist_ok=True)
        depth_path = horizon_dir / "flood_depth_cm.tif"
        risk_path = horizon_dir / "flood_risk_class.tif"
        depth_profile = baseline_profile.copy()
        depth_profile.update(
            count=1, dtype="float32", nodata=baseline_nodata, compress="deflate", predictor=2
        )
        risk_profile = baseline_profile.copy()
        risk_profile.update(
            count=1, dtype="int16", nodata=risk_nodata, compress="deflate", predictor=1
        )
        with rasterio.open(depth_path, "w", **depth_profile) as output:
            output.write(depth, 1)
        with rasterio.open(risk_path, "w", **risk_profile) as output:
            output.write(risk, 1)

        summary = {
            "status": "ready",
            "horizon_minutes": int(minutes),
            "horizon_label": f"T+{int(minutes)}",
            "rainfall_scenario": metadata["rainfall"]["scenario"],
            "persistence_decay_factor": factor,
            "flood_depth_raster": str(depth_path),
            "flood_risk_raster": str(risk_path),
            "statistics": _safe_statistics(
                depth, risk, depth_nodata=baseline_nodata, risk_nodata=risk_nodata
            ),
        }
        (horizon_dir / "forecast_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        metadata["horizons"].append(summary)

    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def forecast_status() -> dict[str, Any]:
    assumptions = load_forecast_assumptions()
    ready = FORECAST_METADATA.exists() and all(
        (FORECAST_OUTPUT_ROOT / f"tplus_{minutes:03d}" / "flood_depth_cm.tif").exists()
        and (FORECAST_OUTPUT_ROOT / f"tplus_{minutes:03d}" / "flood_risk_class.tif").exists()
        for minutes in assumptions["forecast_horizons_minutes"]
    )
    if not ready:
        return {
            "status": "not_ready",
            "model_status": "not_ready",
            "forecast_horizons_minutes": assumptions["forecast_horizons_minutes"],
            "rainfall_provider": assumptions["rainfall_provider"],
            "message": "Run the deterministic forecast generator after Step 6 outputs are available.",
            "warnings": ["Forecast output rasters are not complete."],
        }
    metadata = json.loads(FORECAST_METADATA.read_text(encoding="utf-8"))
    return {
        "status": "ready",
        "model_status": "ready",
        "generated_at": metadata.get("generated_at"),
        "forecast_horizons_minutes": metadata["assumptions"]["forecast_horizons_minutes"],
        "rainfall_provider": metadata["rainfall"]["provider"],
        "rainfall_description": metadata["rainfall"]["description"],
        "scenario": metadata["rainfall"]["scenario"],
        "assumptions": metadata["assumptions"],
        "warnings": metadata["warnings"],
    }


def forecast_summary() -> dict[str, Any]:
    if not FORECAST_METADATA.exists():
        raise FileNotFoundError("Forecast metadata is not available.")
    metadata = json.loads(FORECAST_METADATA.read_text(encoding="utf-8"))
    return {
        "status": metadata["status"],
        "generated_at": metadata["generated_at"],
        "rainfall": metadata["rainfall"],
        "assumptions": metadata["assumptions"],
        "horizons": metadata["horizons"],
        "warnings": metadata["warnings"],
    }