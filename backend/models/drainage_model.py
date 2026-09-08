"""Prototype drainage-network interaction and capacity-index model."""

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
    DRAINAGE_ASSUMPTIONS_PATH,
    DRAINAGE_CAPACITY_INDEX_RASTER,
    DRAINAGE_INTERACTION_RASTER,
    DRAINAGE_METADATA,
    DRAINAGE_OUTPUT_ROOT,
    PREPROCESSED_ROOT,
    PROCESSED_DEM_RASTER,
    PROCESSED_NALAS_VECTOR,
    PROCESSED_SLOPE_PERCENT_RASTER,
)

DRAINAGE_NODATA = -9999
CAPACITY_NODATA = -9999.0


def load_drainage_assumptions(path: Path = DRAINAGE_ASSUMPTIONS_PATH) -> dict[str, Any]:
    assumptions = json.loads(path.read_text(encoding="utf-8"))
    if assumptions.get("status") != "prototype_assumption":
        raise ValueError("Drainage assumptions must be marked prototype_assumption.")
    if assumptions.get("source") != "prototype_assumption":
        raise ValueError("Drainage assumptions must identify their prototype source.")
    required = (
        "drainage_influence_radius_m",
        "prototype_drainage_effectiveness",
        "surface_volume_removal_fraction",
        "maximum_prototype_removal_m3_per_cell",
        "slope_reference_percent",
        "slope_weight",
        "proximity_weight",
        "removal_enabled",
    )
    if any(key not in assumptions for key in required):
        raise ValueError("Drainage assumptions are incomplete.")
    if float(assumptions["drainage_influence_radius_m"]) <= 0:
        raise ValueError("drainage_influence_radius_m must be positive.")
    for key in (
        "prototype_drainage_effectiveness",
        "surface_volume_removal_fraction",
        "slope_weight",
        "proximity_weight",
    ):
        if not 0 <= float(assumptions[key]) <= 1:
            raise ValueError(f"{key} must be between 0 and 1.")
    if abs(
        float(assumptions["slope_weight"])
        + float(assumptions["proximity_weight"])
        - 1
    ) > 1e-6:
        raise ValueError("slope_weight and proximity_weight must sum to 1.")
    return assumptions


def _read_lines(path: Path, target_crs: Any) -> gpd.GeoDataFrame:
    try:
        frame = gpd.read_file(path)
    except Exception as exc:
        raise ValueError(f"Could not read processed nala GeoJSON: {path}") from exc
    if frame.crs is None:
        raise ValueError(f"Processed nala GeoJSON has no CRS: {path}")
    frame["geometry"] = frame.geometry.map(
        lambda value: shape(value) if isinstance(value, dict) else value
    )
    return frame.to_crs(target_crs)


def rasterize_nala_network(
    *,
    path: Path = PROCESSED_NALAS_VECTOR,
    target_crs: Any,
    output_shape: tuple[int, int],
    transform: Any,
) -> np.ndarray:
    frame = _read_lines(path, target_crs)
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
    )


def _expand_frontier(frontier: np.ndarray) -> np.ndarray:
    expanded = np.zeros_like(frontier, dtype=bool)
    expanded[1:, :] |= frontier[:-1, :]
    expanded[:-1, :] |= frontier[1:, :]
    expanded[:, 1:] |= frontier[:, :-1]
    expanded[:, :-1] |= frontier[:, 1:]
    expanded[1:, 1:] |= frontier[:-1, :-1]
    expanded[:-1, :-1] |= frontier[1:, 1:]
    expanded[1:, :-1] |= frontier[:-1, 1:]
    expanded[:-1, 1:] |= frontier[1:, :-1]
    return expanded


def compute_nala_influence(
    nala_mask: np.ndarray,
    *,
    radius_cells: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return interaction codes and approximate grid distance to mapped nalas."""

    distance = np.full(nala_mask.shape, np.inf, dtype=np.float32)
    distance[nala_mask] = 0
    frontier = nala_mask.copy()
    for step in range(1, radius_cells + 1):
        expanded = _expand_frontier(frontier)
        new_cells = expanded & ~np.isfinite(distance)
        distance[new_cells] = step
        frontier = new_cells
        if not frontier.any():
            break
    interaction = np.zeros(nala_mask.shape, dtype=np.uint8)
    interaction[nala_mask] = 1
    interaction[(~nala_mask) & np.isfinite(distance)] = 2
    return interaction, distance


def calculate_capacity_index(
    interaction: np.ndarray,
    distance_cells: np.ndarray,
    slope_percent: np.ndarray,
    *,
    radius_cells: int,
    slope_reference_percent: float,
    slope_weight: float,
    proximity_weight: float,
    effectiveness: float,
) -> np.ndarray:
    proximity = np.zeros(interaction.shape, dtype=np.float32)
    influenced = np.isfinite(distance_cells)
    proximity[influenced] = np.clip(
        1.0 - distance_cells[influenced] / max(1, radius_cells),
        0.0,
        1.0,
    )
    slope_factor = np.clip(
        np.nan_to_num(slope_percent, nan=0.0, posinf=0.0, neginf=0.0)
        / max(0.001, slope_reference_percent),
        0.0,
        1.0,
    )
    slope_factor = 0.5 + 0.5 * slope_factor
    capacity = (
        proximity_weight * proximity + slope_weight * slope_factor
    ) * float(effectiveness)
    return np.where(influenced, np.clip(capacity, 0.0, 1.0), 0.0).astype(np.float32)


def _write_raster(path: Path, reference: rasterio.DatasetReader, array: np.ndarray, *, dtype: str, nodata: float | int) -> None:
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


def run_drainage_model(
    *,
    assumptions_path: Path = DRAINAGE_ASSUMPTIONS_PATH,
    metadata_path: Path = DRAINAGE_METADATA,
) -> dict[str, Any]:
    assumptions = load_drainage_assumptions(assumptions_path)
    with (
        rasterio.open(PROCESSED_DEM_RASTER) as dem,
        rasterio.open(PROCESSED_SLOPE_PERCENT_RASTER) as slope,
    ):
        if (
            dem.crs != slope.crs
            or dem.transform != slope.transform
            or dem.width != slope.width
            or dem.height != slope.height
        ):
            raise ValueError("DEM and slope grids are not aligned.")
        elevation_valid = (
            np.ones((dem.height, dem.width), dtype=bool)
            if dem.nodata is None
            else dem.read(1) != dem.nodata
        )
        slope_values = slope.read(1).astype(np.float32)
        slope_valid = (
            np.ones_like(elevation_valid)
            if slope.nodata is None
            else slope_values != slope.nodata
        )
        # Slope nodata must not erase otherwise valid DEM/runoff cells from
        # the Step 6 volume balance. Outside mapped nala influence, the slope
        # value does not affect the capacity index; use a neutral zero slope.
        slope_values = np.where(slope_valid, slope_values, 0.0)
        valid = elevation_valid
        nala_mask = rasterize_nala_network(
            target_crs=dem.crs,
            output_shape=(dem.height, dem.width),
            transform=dem.transform,
        ).astype(bool) & valid
        radius_cells = max(
            1,
            int(np.ceil(float(assumptions["drainage_influence_radius_m"]) / dem.res[0])),
        )
        interaction, distance_cells = compute_nala_influence(
            nala_mask,
            radius_cells=radius_cells,
        )
        capacity = calculate_capacity_index(
            interaction,
            distance_cells,
            slope_values,
            radius_cells=radius_cells,
            slope_reference_percent=float(assumptions["slope_reference_percent"]),
            slope_weight=float(assumptions["slope_weight"]),
            proximity_weight=float(assumptions["proximity_weight"]),
            effectiveness=float(assumptions["prototype_drainage_effectiveness"]),
        )
        interaction_output = np.full(interaction.shape, DRAINAGE_NODATA, dtype=np.int16)
        capacity_output = np.full(capacity.shape, CAPACITY_NODATA, dtype=np.float32)
        interaction_output[valid] = interaction[valid]
        capacity_output[valid] = capacity[valid]
        _write_raster(
            DRAINAGE_INTERACTION_RASTER,
            dem,
            interaction_output,
            dtype="int16",
            nodata=DRAINAGE_NODATA,
        )
        _write_raster(
            DRAINAGE_CAPACITY_INDEX_RASTER,
            dem,
            capacity_output,
            dtype="float32",
            nodata=CAPACITY_NODATA,
        )
        metadata = {
            "status": "ready",
            "model_description": "prototype mapped-nala drainage interaction and capacity index",
            "source": "prototype_assumption",
            "nala_source": str(PROCESSED_NALAS_VECTOR),
            "dem_source": str(PROCESSED_DEM_RASTER),
            "slope_source": str(PROCESSED_SLOPE_PERCENT_RASTER),
            "crs": str(dem.crs),
            "raster_dimensions": {"height": dem.height, "width": dem.width},
            "raster_resolution_m": [float(value) for value in dem.res],
            "assumptions": assumptions,
            "interaction_encoding": {
                "0": "no mapped nala influence",
                "1": "mapped nala intersects cell",
                "2": "within prototype nala influence radius",
                "-9999": "nodata",
            },
            "statistics": {
                "valid_cell_count": int(valid.sum()),
                "mapped_nala_intersection_cell_count": int(nala_mask.sum()),
                "drainage_influence_cell_count": int(
                    np.sum((interaction > 0) & valid)
                ),
                "maximum_capacity_index": float(capacity[valid].max())
                if valid.any()
                else None,
                "mean_influence_capacity_index": float(capacity[valid].mean())
                if valid.any()
                else None,
            },
            "output_availability": {
                "drainage_interaction": str(DRAINAGE_INTERACTION_RASTER),
                "drainage_capacity_index": str(DRAINAGE_CAPACITY_INDEX_RASTER),
                "metadata": str(metadata_path),
            },
            "warnings": [
                "The mapped nala/drainage network is a spatial proxy for drainage interaction.",
                "The capacity index is dimensionless and is not measured hydraulic capacity.",
                "Missing pipe, channel, pump, and invert attributes are not fabricated.",
            ],
            "limitations": [
                "The supplied mapped nala network may be incomplete.",
                "No pipe hydraulics, channel hydraulics, backflow, or operational drainage state is represented.",
            ],
            "processing_timestamp": datetime.now(UTC).isoformat(),
        }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata