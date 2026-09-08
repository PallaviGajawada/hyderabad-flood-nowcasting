"""Deterministic D8-style prototype surface-water routing and accumulation."""

from __future__ import annotations

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape

from ..config import (
    FLOW_ACCUMULATION_RASTER,
    FLOW_DIRECTION_RASTER,
    NALA_INTERACTION_RASTER,
    PROCESSED_DEM_RASTER,
    PROCESSED_NALAS_VECTOR,
    PROCESSED_WATERBODIES_VECTOR,
    RUNOFF_DEPTH_RASTER,
    RUNOFF_METADATA,
    RUNOFF_VOLUME_RASTER,
    SURFACE_WATER_ASSUMPTIONS_PATH,
    SURFACE_WATER_DEPTH_CM,
    SURFACE_WATER_DEPTH_MM,
    SURFACE_WATER_METADATA,
    SURFACE_WATER_OUTPUT_ROOT,
    SURFACE_WATER_VOLUME,
)
from ..preprocessing.spatial import read_vector

SURFACE_WATER_NODATA = -9999.0
FLOW_DIRECTION_NODATA = -9999
NALA_NODATA = -9999

# ESRI-style D8 bit codes: N, NE, E, SE, S, SW, W, NW.
D8_NEIGHBORS = (
    (1, -1, 0),
    (2, -1, 1),
    (4, 0, 1),
    (8, 1, 1),
    (16, 1, 0),
    (32, 1, -1),
    (64, 0, -1),
    (128, -1, -1),
)


def _load_assumptions(path: Path = SURFACE_WATER_ASSUMPTIONS_PATH) -> dict[str, Any]:
    assumptions = json.loads(path.read_text(encoding="utf-8"))
    if assumptions.get("status") != "prototype_assumption":
        raise ValueError("Surface-water assumptions must be marked prototype_assumption.")
    required = (
        "routing_fraction",
        "drainage_capture_fraction",
        "drainage_effectiveness",
        "maximum_prototype_drainage_removal_m3_per_cell",
    )
    if any(key not in assumptions for key in required):
        raise ValueError("Surface-water assumptions are incomplete.")
    if not 0 <= float(assumptions["routing_fraction"]) <= 1:
        raise ValueError("routing_fraction must be between 0 and 1.")
    if not 0 <= float(assumptions["drainage_capture_fraction"]) <= 1:
        raise ValueError("drainage_capture_fraction must be between 0 and 1.")
    if not 0 <= float(assumptions["drainage_effectiveness"]) <= 1:
        raise ValueError("drainage_effectiveness must be between 0 and 1.")
    return assumptions


def cell_area_m2_from_transform(transform: Any) -> float:
    """Return the projected cell area for the DEM reference grid."""

    return abs(float(transform.a * transform.e))


def _assert_aligned(reference: rasterio.DatasetReader, runoff: rasterio.DatasetReader) -> None:
    checks = {
        "crs": reference.crs == runoff.crs,
        "width": reference.width == runoff.width,
        "height": reference.height == runoff.height,
        "transform": reference.transform == runoff.transform,
        "resolution": reference.res == runoff.res,
        "bounds": reference.bounds == runoff.bounds,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"Runoff and DEM grids are not aligned: {', '.join(failed)}.")


def _rasterize_lines(
    path: Path,
    *,
    crs: Any,
    shape: tuple[int, int],
    transform: Any,
) -> np.ndarray:
    frame = _read_processed_vector(path)
    frame["geometry"] = frame.geometry.map(
        lambda geometry: shape(geometry)
        if isinstance(geometry, dict)
        else geometry
    )
    if frame.crs is None:
        raise ValueError(f"Vector source has no CRS: {path}")
    frame = frame.to_crs(crs)
    shapes = (
        (geometry, 1)
        for geometry in frame.geometry
        if geometry is not None and not geometry.is_empty
    )
    return rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    )


def _rasterize_water_bodies(
    path: Path,
    *,
    crs: Any,
    shape: tuple[int, int],
    transform: Any,
) -> np.ndarray:
    frame = _read_processed_vector(path)
    frame["geometry"] = frame.geometry.map(
        lambda geometry: shape(geometry)
        if isinstance(geometry, dict)
        else geometry
    )
    if frame.crs is None:
        raise ValueError(f"Vector source has no CRS: {path}")
    frame = frame.to_crs(crs)
    shapes = (
        (geometry, 1)
        for geometry in frame.geometry
        if geometry is not None and not geometry.is_empty
    )
    return rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    )


def _read_processed_vector(path: Path) -> gpd.GeoDataFrame:
    """Read generated GeoJSON with OGR before falling back to ArcGIS parsing."""

    try:
        return gpd.read_file(path)
    except Exception:
        frame, _ = read_vector(path)
        return frame


def derive_flow_direction(
    elevation: np.ndarray,
    valid_mask: np.ndarray,
    *,
    water_body_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Choose the steepest strictly lower valid D8 neighbor deterministically."""

    direction = np.zeros(elevation.shape, dtype=np.int16)
    best_drop = np.zeros(elevation.shape, dtype=np.float32)
    water = water_body_mask if water_body_mask is not None else np.zeros_like(valid_mask)
    source_valid = valid_mask & ~water
    rows, cols = elevation.shape
    for code, row_delta, col_delta in D8_NEIGHBORS:
        source_rows = slice(max(0, -row_delta), min(rows, rows - row_delta))
        source_cols = slice(max(0, -col_delta), min(cols, cols - col_delta))
        target_rows = slice(max(0, row_delta), min(rows, rows + row_delta))
        target_cols = slice(max(0, col_delta), min(cols, cols + col_delta))
        source_elevation = elevation[source_rows, source_cols]
        target_elevation = elevation[target_rows, target_cols]
        candidate = (
            source_valid[source_rows, source_cols]
            & valid_mask[target_rows, target_cols]
            & (target_elevation < source_elevation)
        )
        drop = source_elevation - target_elevation
        better = candidate & (drop > best_drop[source_rows, source_cols])
        direction_view = direction[source_rows, source_cols]
        drop_view = best_drop[source_rows, source_cols]
        direction_view[better] = code
        drop_view[better] = drop[better]
    return direction


def accumulate_surface_water(
    runoff_volume: np.ndarray,
    flow_direction: np.ndarray,
    valid_mask: np.ndarray,
    nala_mask: np.ndarray,
    water_body_mask: np.ndarray,
    *,
    routing_fraction: float,
    drainage_capture_fraction: float,
    drainage_effectiveness: float,
    maximum_drainage_removal_m3_per_cell: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Route volume once through an acyclic D8 graph and track conservation."""

    height, width = runoff_volume.shape
    cell_count = height * width
    accumulated = np.where(valid_mask, runoff_volume, 0).astype(np.float64).ravel()
    input_total = float(accumulated.sum())
    retained = np.zeros(cell_count, dtype=np.float64)
    removed = np.zeros(cell_count, dtype=np.float64)
    indegree = np.zeros(cell_count, dtype=np.int32)
    flat_valid = valid_mask.ravel()
    flat_direction = flow_direction.ravel()
    row_indices, col_indices = np.indices((height, width))
    flat_rows = row_indices.ravel()
    flat_cols = col_indices.ravel()
    target_for_cell = np.full(cell_count, -1, dtype=np.int64)
    direction_offsets = {code: (dr, dc) for code, dr, dc in D8_NEIGHBORS}
    for code, (row_delta, col_delta) in direction_offsets.items():
        selected = flat_valid & (flat_direction == code)
        target_rows = flat_rows[selected] + row_delta
        target_cols = flat_cols[selected] + col_delta
        targets = target_rows * width + target_cols
        source_indices = np.flatnonzero(selected)
        target_for_cell[source_indices] = targets
        np.add.at(indegree, targets, 1)

    queue = deque(np.flatnonzero(flat_valid & (indegree == 0)).tolist())
    processed = 0
    while queue:
        source = queue.popleft()
        processed += 1
        incoming = accumulated[source]
        if nala_mask.ravel()[source] and not water_body_mask.ravel()[source]:
            removal = min(
                incoming
                * drainage_capture_fraction
                * drainage_effectiveness,
                maximum_drainage_removal_m3_per_cell,
            )
            removed[source] = removal
        post_drainage = max(0.0, incoming - removed[source])
        if water_body_mask.ravel()[source]:
            retained[source] = post_drainage
            continue
        outgoing = post_drainage * routing_fraction
        retained[source] = post_drainage - outgoing
        target = target_for_cell[source]
        if target >= 0:
            accumulated[target] += outgoing
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
        else:
            retained[source] += outgoing

    if processed != int(valid_mask.sum()):
        raise ValueError(
            f"D8 flow graph could not be fully ordered: processed {processed} of {int(valid_mask.sum())} valid cells."
        )
    conservation_error = float(
        input_total
        - retained[flat_valid].sum()
        - removed[flat_valid].sum()
    )
    return (
        accumulated.reshape((height, width)),
        retained.reshape((height, width)),
        removed.reshape((height, width)),
        conservation_error,
    )


def _write_raster(path: Path, profile: dict[str, Any], array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(array, 1)


def _profile(reference: rasterio.DatasetReader, *, dtype: str, nodata: float | int) -> dict[str, Any]:
    profile = reference.profile.copy()
    profile.update(
        count=1,
        dtype=dtype,
        nodata=nodata,
        compress="deflate",
        predictor=2 if dtype != "int16" else 1,
        BIGTIFF="IF_SAFER",
    )
    return profile


def run_surface_water_model(
    *,
    assumptions_path: Path = SURFACE_WATER_ASSUMPTIONS_PATH,
    metadata_path: Path = SURFACE_WATER_METADATA,
) -> dict[str, Any]:
    assumptions = _load_assumptions(assumptions_path)
    runoff_metadata = json.loads(RUNOFF_METADATA.read_text(encoding="utf-8"))
    if runoff_metadata.get("status") != "ready":
        raise ValueError("Runoff model metadata is not ready.")

    with (
        rasterio.open(PROCESSED_DEM_RASTER) as dem,
        rasterio.open(RUNOFF_DEPTH_RASTER) as runoff_depth,
        rasterio.open(RUNOFF_VOLUME_RASTER) as runoff_volume,
    ):
        _assert_aligned(dem, runoff_volume)
        _assert_aligned(dem, runoff_depth)
        elevation = dem.read(1).astype(np.float32)
        runoff_depth_values = runoff_depth.read(1).astype(np.float32)
        runoff_volume_values = runoff_volume.read(1).astype(np.float64)
        dem_valid = np.ones(elevation.shape, dtype=bool)
        if dem.nodata is not None:
            dem_valid &= elevation != dem.nodata
        runoff_valid = runoff_volume_values != runoff_volume.nodata
        valid_mask = dem_valid & runoff_valid
        water_body_mask = _rasterize_water_bodies(
            PROCESSED_WATERBODIES_VECTOR,
            crs=dem.crs,
            shape=elevation.shape,
            transform=dem.transform,
        ).astype(bool) & valid_mask
        nala_mask = _rasterize_lines(
            PROCESSED_NALAS_VECTOR,
            crs=dem.crs,
            shape=elevation.shape,
            transform=dem.transform,
        ).astype(bool) & valid_mask
        flow_direction = derive_flow_direction(
            elevation,
            valid_mask,
            water_body_mask=water_body_mask,
        )
        (
            flow_accumulation,
            retained_volume,
            removed_volume,
            conservation_error,
        ) = accumulate_surface_water(
            runoff_volume_values,
            flow_direction,
            valid_mask,
            nala_mask,
            water_body_mask,
            routing_fraction=float(assumptions["routing_fraction"]),
            drainage_capture_fraction=float(assumptions["drainage_capture_fraction"]),
            drainage_effectiveness=float(assumptions["drainage_effectiveness"]),
            maximum_drainage_removal_m3_per_cell=float(
                assumptions["maximum_prototype_drainage_removal_m3_per_cell"]
            ),
        )
        cell_area_m2 = cell_area_m2_from_transform(dem.transform)
        accumulated_depth_mm = np.zeros(elevation.shape, dtype=np.float64)
        accumulated_depth_mm[valid_mask] = retained_volume[valid_mask] / cell_area_m2 * 1000
        depth_mm = np.full(elevation.shape, SURFACE_WATER_NODATA, dtype=np.float32)
        depth_cm = np.full(elevation.shape, SURFACE_WATER_NODATA, dtype=np.float32)
        volume_m3 = np.full(elevation.shape, SURFACE_WATER_NODATA, dtype=np.float32)
        accumulation_output = np.full(elevation.shape, SURFACE_WATER_NODATA, dtype=np.float32)
        direction_output = np.full(elevation.shape, FLOW_DIRECTION_NODATA, dtype=np.int16)
        nala_output = np.full(elevation.shape, NALA_NODATA, dtype=np.int16)
        depth_mm[valid_mask] = accumulated_depth_mm[valid_mask]
        depth_cm[valid_mask] = accumulated_depth_mm[valid_mask] / 10
        volume_m3[valid_mask] = retained_volume[valid_mask]
        accumulation_output[valid_mask] = flow_accumulation[valid_mask]
        direction_output[valid_mask] = flow_direction[valid_mask]
        nala_output[valid_mask] = nala_mask[valid_mask].astype(np.int16)
        reference_profile = dem.profile.copy()
        reference_shape = [int(dem.height), int(dem.width)]
        reference_crs = str(dem.crs)
        reference_resolution = [float(value) for value in dem.res]
        reference_transform = dem.transform

    _write_raster(
        SURFACE_WATER_DEPTH_MM,
        _profile_from_reference(reference_profile, dtype="float32", nodata=SURFACE_WATER_NODATA),
        depth_mm,
    )
    _write_raster(
        SURFACE_WATER_DEPTH_CM,
        _profile_from_reference(reference_profile, dtype="float32", nodata=SURFACE_WATER_NODATA),
        depth_cm,
    )
    _write_raster(
        SURFACE_WATER_VOLUME,
        _profile_from_reference(reference_profile, dtype="float32", nodata=SURFACE_WATER_NODATA),
        volume_m3,
    )
    _write_raster(
        FLOW_ACCUMULATION_RASTER,
        _profile_from_reference(reference_profile, dtype="float32", nodata=SURFACE_WATER_NODATA),
        accumulation_output,
    )
    _write_raster(
        FLOW_DIRECTION_RASTER,
        _profile_from_reference(reference_profile, dtype="int16", nodata=FLOW_DIRECTION_NODATA),
        direction_output,
    )
    _write_raster(
        NALA_INTERACTION_RASTER,
        _profile_from_reference(reference_profile, dtype="int16", nodata=NALA_NODATA),
        nala_output,
    )

    valid_depth = depth_mm[valid_mask]
    valid_volume = volume_m3[valid_mask]
    threshold_counts = {
        "above_1_cm": int(np.sum(valid_depth >= 10)),
        "above_5_cm": int(np.sum(valid_depth >= 50)),
        "above_10_cm": int(np.sum(valid_depth >= 100)),
        "above_20_cm": int(np.sum(valid_depth >= 200)),
        "above_50_cm": int(np.sum(valid_depth >= 500)),
    }
    input_total = float(runoff_volume_values[valid_mask].sum())
    removed_total = float(removed_volume[valid_mask].sum())
    output_total = float(valid_volume.sum())
    metadata = {
        "status": "ready",
        "model_description": "prototype terrain-based surface-water accumulation",
        "rainfall_scenario": runoff_metadata.get("rainfall_scenario"),
        "rainfall_timestamp": runoff_metadata.get("rainfall_timestamp"),
        "runoff_source": str(RUNOFF_VOLUME_RASTER),
        "dem_source": str(PROCESSED_DEM_RASTER),
        "nala_source": "outputs/preprocessed/drainage/ghmc_nalas.geojson",
        "water_body_source": "outputs/preprocessed/waterbodies/hyderabad_tanks.geojson",
        "terrain_routing_method": "deterministic D8-style steepest strictly-lower-neighbor routing",
        "d8_direction_codes": {
            "1": "north",
            "2": "northeast",
            "4": "east",
            "8": "southeast",
            "16": "south",
            "32": "southwest",
            "64": "west",
            "128": "northwest",
            "0": "sink/no lower neighbor",
        },
        "drainage_assumptions": assumptions,
        "water_body_treatment": assumptions["water_body_treatment"],
        "crs": reference_crs,
        "raster_dimensions": {"height": reference_shape[0], "width": reference_shape[1]},
        "raster_resolution_m": reference_resolution,
        "cell_area_m2": cell_area_m2,
        "nodata_handling": {
            "output_nodata": SURFACE_WATER_NODATA,
            "flow_direction_nodata": FLOW_DIRECTION_NODATA,
            "nala_interaction_nodata": NALA_NODATA,
            "description": "DEM/runoff nodata cells remain nodata and are excluded from routing.",
        },
        "processing_timestamp": datetime.now(UTC).isoformat(),
        "statistics": {
            "valid_cell_count": int(valid_mask.sum()),
            "maximum_surface_water_depth_mm": float(valid_depth.max()) if valid_depth.size else None,
            "maximum_surface_water_depth_cm": float(valid_depth.max() / 10) if valid_depth.size else None,
            "mean_surface_water_depth_mm": float(valid_depth.mean()) if valid_depth.size else None,
            "total_surface_water_volume_m3": output_total,
            "threshold_cell_counts": threshold_counts,
            "nala_interaction_cell_count": int(nala_mask.sum()),
            "water_body_cell_count": int(water_body_mask.sum()),
            "input_runoff_volume_m3": input_total,
            "prototype_drainage_removed_volume_m3": removed_total,
            "volume_conservation_error_m3": conservation_error,
            "volume_conservation_check": abs(conservation_error) < 1e-3,
        },
        "output_availability": {
            "surface_water_depth_mm": str(SURFACE_WATER_DEPTH_MM),
            "surface_water_depth_cm": str(SURFACE_WATER_DEPTH_CM),
            "surface_water_volume_m3": str(SURFACE_WATER_VOLUME),
            "flow_direction": str(FLOW_DIRECTION_RASTER),
            "flow_accumulation": str(FLOW_ACCUMULATION_RASTER),
            "nala_interaction": str(NALA_INTERACTION_RASTER),
            "metadata": str(metadata_path),
        },
        "warnings": [
            "This is a terrain-based screening/prototype model, not a full 2D shallow-water hydrodynamic solver.",
            "Depth is equivalent accumulated surface-water depth, not observed or measured flood depth.",
            "Drainage removal uses configurable prototype assumptions and is not a measured GHMC/HMWSSB capacity.",
            "No safe routing, hydraulic pipe flow, backflow, tank operating rule, or final 0-3 hour forecast is implemented.",
            "Current rainfall remains the IMD historical/scenario input, not radar nowcasting.",
        ],
        "limitations": [
            "D8 routing uses only the steepest strictly lower neighbor; flats and pits become sinks.",
            "The model does not represent momentum, storage-area relationships, infiltration dynamics, or time stepping.",
            "Tanks are represented as retention sinks without measured levels, spillways, or capacities.",
        ],
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def _profile_from_reference(
    reference_profile: dict[str, Any],
    *,
    dtype: str,
    nodata: float | int,
) -> dict[str, Any]:
    profile = reference_profile.copy()
    profile.update(
        count=1,
        dtype=dtype,
        nodata=nodata,
        compress="deflate",
        predictor=2 if dtype == "float32" else 1,
        BIGTIFF="IF_SAFER",
    )
    return profile