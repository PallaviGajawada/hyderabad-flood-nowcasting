"""Prototype drainage-removal, equivalent-depth, risk, and road-risk model."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry import shape

from ..config import (
    DRAINAGE_CAPACITY_INDEX_RASTER,
    DRAINAGE_REMOVED_VOLUME_RASTER,
    DRAINAGE_ASSUMPTIONS_PATH,
    DRAINAGE_INTERACTION_RASTER,
    DRAINAGE_METADATA,
    DISPLAY_DEPTH_CM,
    FLOOD_DEPTH_ASSUMPTIONS_PATH,
    FLOOD_DEPTH_METADATA,
    FLOOD_DEPTH_OUTPUT_ROOT,
    FLOOD_RISK_CLASS_RASTER,
    PROCESSED_DEM_RASTER,
    PROCESSED_WATERBODIES_VECTOR,
    RAW_EQUIVALENT_DEPTH_CM,
    RAW_EQUIVALENT_DEPTH_MM,
    ROAD_FLOOD_RISK_GEOJSON,
    ROADS_GEOJSON,
    REMAINING_SURFACE_WATER_VOLUME_RASTER,
    SURFACE_WATER_VOLUME,
)
from .drainage_model import load_drainage_assumptions

FLOOD_DEPTH_NODATA = -9999.0
RISK_NODATA = -9999


def load_flood_depth_assumptions(
    path: Path = FLOOD_DEPTH_ASSUMPTIONS_PATH,
) -> dict[str, Any]:
    assumptions = json.loads(path.read_text(encoding="utf-8"))
    if assumptions.get("status") != "prototype_assumption":
        raise ValueError("Flood-depth assumptions must be marked prototype_assumption.")
    if assumptions.get("source") != "prototype_assumption":
        raise ValueError("Flood-depth assumptions must identify their prototype source.")
    required = (
        "display_depth_cap_cm",
        "low_threshold_cm",
        "moderate_threshold_cm",
        "high_threshold_cm",
        "severe_threshold_cm",
        "risk_class_encoding",
        "road_sample_points",
    )
    if any(key not in assumptions for key in required):
        raise ValueError("Flood-depth assumptions are incomplete.")
    thresholds = [
        float(assumptions["low_threshold_cm"]),
        float(assumptions["moderate_threshold_cm"]),
        float(assumptions["high_threshold_cm"]),
        float(assumptions["severe_threshold_cm"]),
    ]
    if thresholds != sorted(thresholds):
        raise ValueError("Flood-depth thresholds must be nondecreasing.")
    if float(assumptions["display_depth_cap_cm"]) <= 0:
        raise ValueError("display_depth_cap_cm must be positive.")
    if int(assumptions["road_sample_points"]) < 2:
        raise ValueError("road_sample_points must be at least 2.")
    return assumptions


def classify_risk(
    depth_cm: np.ndarray,
    *,
    low_threshold_cm: float,
    moderate_threshold_cm: float,
    high_threshold_cm: float,
    severe_threshold_cm: float,
) -> np.ndarray:
    risk = np.zeros(depth_cm.shape, dtype=np.int16)
    positive = depth_cm > 0
    risk[positive & (depth_cm < low_threshold_cm)] = 1
    risk[
        (depth_cm >= low_threshold_cm) & (depth_cm < moderate_threshold_cm)
    ] = 2
    risk[
        (depth_cm >= moderate_threshold_cm) & (depth_cm < high_threshold_cm)
    ] = 3
    risk[depth_cm >= severe_threshold_cm] = 4
    return risk


def calculate_drainage_removal(
    surface_water_volume_m3: np.ndarray,
    capacity_index: np.ndarray,
    *,
    enabled: bool,
    removal_fraction: float,
    effectiveness: float,
    maximum_removal_m3_per_cell: float,
    valid_mask: np.ndarray,
) -> np.ndarray:
    removed = np.zeros(surface_water_volume_m3.shape, dtype=np.float64)
    if not enabled:
        return removed
    candidate = (
        surface_water_volume_m3
        * np.clip(capacity_index, 0.0, 1.0)
        * float(removal_fraction)
        * float(effectiveness)
    )
    removed[valid_mask] = np.minimum(
        np.maximum(candidate[valid_mask], 0.0),
        float(maximum_removal_m3_per_cell),
    )
    return removed


def _read_water_body_mask(
    *,
    target_crs: Any,
    output_shape: tuple[int, int],
    transform: Any,
) -> np.ndarray:
    frame = gpd.read_file(PROCESSED_WATERBODIES_VECTOR)
    if frame.crs is None:
        raise ValueError("Processed water-body GeoJSON has no CRS.")
    frame["geometry"] = frame.geometry.map(
        lambda value: shape(value) if isinstance(value, dict) else value
    )
    frame = frame.to_crs(target_crs)
    shapes = (
        (geometry, 1)
        for geometry in frame.geometry
        if geometry is not None and not geometry.is_empty
    )
    return rasterize(
        shapes,
        out_shape=output_shape,
        transform=transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)


def _write_raster(
    path: Path,
    reference: rasterio.DatasetReader,
    array: np.ndarray,
    *,
    dtype: str,
    nodata: float | int,
) -> None:
    profile = reference.profile.copy()
    profile.update(
        count=1,
        dtype=dtype,
        nodata=nodata,
        compress="deflate",
        predictor=2 if dtype == "float32" else 1,
        BIGTIFF="IF_SAFER",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(array.astype(dtype), 1)


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return json.dumps(value.tolist())
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value))
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def aggregate_road_flood_risk(
    *,
    depth_raster: Path = DISPLAY_DEPTH_CM,
    risk_raster: Path = FLOOD_RISK_CLASS_RASTER,
    output_path: Path = ROAD_FLOOD_RISK_GEOJSON,
    sample_points: int = 5,
) -> dict[str, Any]:
    """Sample the existing processed OSM road edges without downloading roads."""

    roads = gpd.read_file(ROADS_GEOJSON)
    if roads.crs is None:
        raise ValueError("Processed road GeoJSON has no CRS.")
    with (
        rasterio.open(depth_raster) as depth,
        rasterio.open(risk_raster) as risk,
    ):
        transformer = Transformer.from_crs(
            roads.crs, depth.crs, always_xy=True
        )
        max_depths: list[float] = []
        mean_depths: list[float] = []
        affected_percentages: list[float] = []
        max_risks: list[int] = []
        for geometry in roads.geometry:
            if geometry is None or geometry.is_empty:
                max_depths.append(0.0)
                mean_depths.append(0.0)
                affected_percentages.append(0.0)
                max_risks.append(0)
                continue
            points = [
                geometry.interpolate(index / (sample_points - 1), normalized=True)
                for index in range(sample_points)
            ]
            xs, ys = transformer.transform(
                [point.x for point in points], [point.y for point in points]
            )
            coordinates = list(zip(xs, ys))
            depth_values = np.asarray(
                [value[0] for value in depth.sample(coordinates)],
                dtype=np.float32,
            )
            risk_values = np.asarray(
                [value[0] for value in risk.sample(coordinates)],
                dtype=np.int16,
            )
            valid_depth = depth_values != depth.nodata
            valid_risk = risk_values != risk.nodata
            if not valid_depth.any():
                max_depths.append(0.0)
                mean_depths.append(0.0)
                affected_percentages.append(0.0)
            else:
                observed = depth_values[valid_depth]
                max_depths.append(float(observed.max()))
                mean_depths.append(float(observed.mean()))
                affected_percentages.append(float(np.mean(observed > 0) * 100))
            max_risks.append(
                int(risk_values[valid_risk].max()) if valid_risk.any() else 0
            )
    result = roads.copy()
    result["prototype_max_depth_cm"] = max_depths
    result["prototype_mean_depth_cm"] = mean_depths
    result["prototype_affected_percent"] = affected_percentages
    result["prototype_max_risk_class"] = max_risks
    for column in result.columns:
        if column != result.geometry.name:
            result[column] = result[column].map(_json_safe)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(output_path, driver="GeoJSON")
    affected = np.asarray(affected_percentages) > 0
    return {
        "status": "ready",
        "source": str(ROADS_GEOJSON),
        "output": str(output_path),
        "sample_points_per_road_edge": sample_points,
        "road_edge_count": int(len(result)),
        "road_edges_with_positive_display_depth": int(affected.sum()),
        "road_edge_affected_percent_mean": float(
            np.mean(affected_percentages)
        )
        if affected_percentages
        else 0.0,
        "maximum_prototype_road_depth_cm": float(max(max_depths))
        if max_depths
        else 0.0,
        "maximum_road_risk_class": int(max(max_risks)) if max_risks else 0,
        "risk_class_counts": {
            str(value): int(np.sum(np.asarray(max_risks) == value))
            for value in range(5)
        },
        "warnings": [
            "Road values are sampled from prototype display depth and risk rasters.",
            "They are not measured street flood depths or safe-route recommendations.",
        ],
    }


def run_flood_depth_model(
    *,
    drainage_assumptions_path: Path = DRAINAGE_ASSUMPTIONS_PATH,
    flood_depth_assumptions_path: Path = FLOOD_DEPTH_ASSUMPTIONS_PATH,
    metadata_path: Path = FLOOD_DEPTH_METADATA,
) -> dict[str, Any]:
    drainage_assumptions = load_drainage_assumptions(drainage_assumptions_path)
    flood_assumptions = load_flood_depth_assumptions(flood_depth_assumptions_path)
    required_outputs = (
        DRAINAGE_INTERACTION_RASTER,
        DRAINAGE_CAPACITY_INDEX_RASTER,
        DRAINAGE_METADATA,
    )
    if not all(path.exists() for path in required_outputs):
        raise ValueError("Run the drainage model successfully before flood depth.")
    with (
        rasterio.open(PROCESSED_DEM_RASTER) as dem,
        rasterio.open(SURFACE_WATER_VOLUME) as surface_water,
        rasterio.open(DRAINAGE_INTERACTION_RASTER) as interaction,
        rasterio.open(DRAINAGE_CAPACITY_INDEX_RASTER) as capacity,
    ):
        grids = (surface_water, interaction, capacity)
        for grid in grids:
            if (
                grid.crs != dem.crs
                or grid.transform != dem.transform
                or grid.width != dem.width
                or grid.height != dem.height
            ):
                raise ValueError("Flood-depth input grids are not aligned with DEM.")
        surface_volume = surface_water.read(1).astype(np.float64)
        interaction_values = interaction.read(1)
        capacity_values = capacity.read(1).astype(np.float32)
        dem_values = dem.read(1)
        valid = (
            (surface_volume != surface_water.nodata)
            & (interaction_values != interaction.nodata)
            & (capacity_values != capacity.nodata)
            & (dem.nodata is None or dem_values != dem.nodata)
        )
        water_body_mask = _read_water_body_mask(
            target_crs=dem.crs,
            output_shape=(dem.height, dem.width),
            transform=dem.transform,
        ) & valid
        removal_valid = valid & ~water_body_mask
        removed = calculate_drainage_removal(
            surface_volume,
            capacity_values,
            enabled=bool(drainage_assumptions["removal_enabled"]),
            removal_fraction=float(
                drainage_assumptions["surface_volume_removal_fraction"]
            ),
            effectiveness=float(
                drainage_assumptions["prototype_drainage_effectiveness"]
            ),
            maximum_removal_m3_per_cell=float(
                drainage_assumptions["maximum_prototype_removal_m3_per_cell"]
            ),
            valid_mask=removal_valid,
        )
        remaining = np.zeros(surface_volume.shape, dtype=np.float64)
        remaining[valid] = np.maximum(surface_volume[valid] - removed[valid], 0)
        cell_area_m2 = abs(float(dem.transform.a * dem.transform.e))
        raw_mm = np.zeros(surface_volume.shape, dtype=np.float64)
        raw_mm[valid] = remaining[valid] / cell_area_m2 * 1000
        raw_cm = raw_mm / 10
        display_cm = np.minimum(raw_cm, float(flood_assumptions["display_depth_cap_cm"]))
        risk = classify_risk(
            display_cm,
            low_threshold_cm=float(flood_assumptions["low_threshold_cm"]),
            moderate_threshold_cm=float(flood_assumptions["moderate_threshold_cm"]),
            high_threshold_cm=float(flood_assumptions["high_threshold_cm"]),
            severe_threshold_cm=float(flood_assumptions["severe_threshold_cm"]),
        )
        raw_mm_output = np.full(raw_mm.shape, FLOOD_DEPTH_NODATA, dtype=np.float32)
        raw_cm_output = np.full(raw_cm.shape, FLOOD_DEPTH_NODATA, dtype=np.float32)
        display_output = np.full(display_cm.shape, FLOOD_DEPTH_NODATA, dtype=np.float32)
        removed_output = np.full(removed.shape, FLOOD_DEPTH_NODATA, dtype=np.float32)
        remaining_output = np.full(remaining.shape, FLOOD_DEPTH_NODATA, dtype=np.float32)
        risk_output = np.full(risk.shape, RISK_NODATA, dtype=np.int16)
        for output, values in (
            (raw_mm_output, raw_mm),
            (raw_cm_output, raw_cm),
            (display_output, display_cm),
            (removed_output, removed),
            (remaining_output, remaining),
        ):
            output[valid] = values[valid]
        risk_output[valid] = risk[valid]
        _write_raster(
            RAW_EQUIVALENT_DEPTH_MM, dem, raw_mm_output, dtype="float32", nodata=FLOOD_DEPTH_NODATA
        )
        _write_raster(
            RAW_EQUIVALENT_DEPTH_CM, dem, raw_cm_output, dtype="float32", nodata=FLOOD_DEPTH_NODATA
        )
        _write_raster(
            DISPLAY_DEPTH_CM, dem, display_output, dtype="float32", nodata=FLOOD_DEPTH_NODATA
        )
        _write_raster(
            DRAINAGE_REMOVED_VOLUME_RASTER, dem, removed_output, dtype="float32", nodata=FLOOD_DEPTH_NODATA
        )
        _write_raster(
            REMAINING_SURFACE_WATER_VOLUME_RASTER,
            dem,
            remaining_output,
            dtype="float32",
            nodata=FLOOD_DEPTH_NODATA,
        )
        _write_raster(
            FLOOD_RISK_CLASS_RASTER, dem, risk_output, dtype="int16", nodata=RISK_NODATA
        )
        valid_raw = raw_cm[valid]
        valid_display = display_cm[valid]
        valid_risk = risk[valid]
        input_total = float(surface_volume[valid].sum())
        removed_total = float(removed[valid].sum())
        remaining_total = float(remaining[valid].sum())
        conservation_error = input_total - removed_total - remaining_total
        grid_info = {
            "crs": str(dem.crs),
            "raster_dimensions": {"height": dem.height, "width": dem.width},
            "raster_resolution_m": [float(value) for value in dem.res],
            "cell_area_m2": cell_area_m2,
        }
    road_summary = aggregate_road_flood_risk(
        sample_points=int(flood_assumptions["road_sample_points"])
    )
    threshold_counts = {
        "above_1_cm": int(np.sum(valid_raw >= 1)),
        "above_5_cm": int(np.sum(valid_raw >= 5)),
        "above_10_cm": int(np.sum(valid_raw >= 10)),
        "above_20_cm": int(np.sum(valid_raw >= 20)),
        "above_50_cm": int(np.sum(valid_raw >= 50)),
    }
    metadata = {
        "status": "ready",
        "source": "prototype_assumption",
        "model_description": "prototype drainage interaction and equivalent flood-depth screening",
        "surface_water_source": str(SURFACE_WATER_VOLUME),
        "drainage_interaction_source": str(DRAINAGE_INTERACTION_RASTER),
        "drainage_capacity_source": str(DRAINAGE_CAPACITY_INDEX_RASTER),
        "water_body_source": str(PROCESSED_WATERBODIES_VECTOR),
        "grid": grid_info,
        "drainage_assumptions": drainage_assumptions,
        "flood_depth_assumptions": flood_assumptions,
        "equations": {
            "drainage_removed_volume_m3": "min(surface_water_volume_m3 * capacity_index * surface_volume_removal_fraction * prototype_drainage_effectiveness, maximum_prototype_removal_m3_per_cell)",
            "remaining_surface_water_volume_m3": "surface_water_volume_m3 - drainage_removed_volume_m3",
            "raw_equivalent_depth_cm": "remaining_surface_water_volume_m3 / cell_area_m2 * 100",
            "display_depth_cm": "min(raw_equivalent_depth_cm, display_depth_cap_cm)",
        },
        "statistics": {
            "valid_cell_count": int(valid.sum()),
            "raw_maximum_depth_cm": float(valid_raw.max()) if valid_raw.size else None,
            "raw_mean_depth_cm": float(valid_raw.mean()) if valid_raw.size else None,
            "raw_maximum_depth_mm": float(valid_raw.max() * 10) if valid_raw.size else None,
            "display_maximum_depth_cm": float(valid_display.max())
            if valid_display.size
            else None,
            "display_mean_depth_cm": float(valid_display.mean())
            if valid_display.size
            else None,
            "threshold_cell_counts": threshold_counts,
            "risk_class_counts": {
                str(value): int(np.sum(valid_risk == value)) for value in range(5)
            },
            "input_surface_water_volume_m3": input_total,
            "prototype_drainage_removed_volume_m3": removed_total,
            "remaining_surface_water_volume_m3": remaining_total,
            "volume_conservation_error_m3": conservation_error,
            "volume_conservation_check": abs(conservation_error) < 1e-3,
            "water_body_cell_count": int(water_body_mask.sum()),
            "drainage_influence_cell_count": int(np.sum(interaction_values > 0)),
        },
        "road_flood_risk": road_summary,
        "output_availability": {
            "raw_equivalent_depth_mm": str(RAW_EQUIVALENT_DEPTH_MM),
            "raw_equivalent_depth_cm": str(RAW_EQUIVALENT_DEPTH_CM),
            "display_depth_cm": str(DISPLAY_DEPTH_CM),
            "flood_risk_class": str(FLOOD_RISK_CLASS_RASTER),
            "drainage_removed_volume_m3": str(DRAINAGE_REMOVED_VOLUME_RASTER),
            "remaining_surface_water_volume_m3": str(REMAINING_SURFACE_WATER_VOLUME_RASTER),
            "road_flood_risk": str(ROAD_FLOOD_RISK_GEOJSON),
            "metadata": str(metadata_path),
        },
        "warnings": [
            "This is a research/prototype screening model and is not an engineering hydraulic simulation or operational flood warning system.",
            "Equivalent depths are not measured street-level flood depths.",
            "The display cap is a visualization/screening decision, not physical inundation capping.",
            "Risk thresholds are prototype screening thresholds and are not official emergency thresholds.",
            "Mapped nalas are used as a spatial proxy; missing hydraulic attributes are represented by explicitly labeled prototype assumptions.",
        ],
        "limitations": [
            "No pipe diameter, channel depth, invert, Manning roughness, measured flow, pump operation, manhole level, blockage, or real-time sewer condition is represented.",
            "Surface-water input is a static historical/scenario raster and not a time-stepped forecast.",
            "Road statistics are sampled edge summaries and are not safe-route recommendations.",
        ],
        "processing_timestamp": datetime.now(UTC).isoformat(),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata