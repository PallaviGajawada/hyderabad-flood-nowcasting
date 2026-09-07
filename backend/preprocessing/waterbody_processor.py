"""Preprocessing for the supplied Hyderabad tanks and water bodies."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import DATASETS, PREPROCESSED_ROOT, WEB_CRS
from .spatial import (
    bounds,
    clean_geometries,
    clip_to_boundary,
    geometry_types,
    read_boundary,
    read_vector,
    serialized_crs,
    write_geojson,
)


def process_waterbodies(
    *,
    input_path: Path = DATASETS.tanks,
    output_path: Path = PREPROCESSED_ROOT / "waterbodies" / "hyderabad_tanks.geojson",
) -> dict[str, Any]:
    """Clean and clip tank polygons without adding storage assumptions."""

    boundary = read_boundary(target_crs=WEB_CRS)
    frame, source_format = read_vector(input_path)
    source_crs = serialized_crs(frame)
    feature_count_before = len(frame)
    cleaned, clean_stats = clean_geometries(frame)
    clipped = clip_to_boundary(cleaned, boundary=boundary, output_crs=WEB_CRS)
    write_geojson(clipped, output_path)
    warnings: list[str] = []
    if len(clipped) < len(cleaned):
        warnings.append(
            f"{len(cleaned) - len(clipped)} water-body features were outside the GHMC boundary or had no intersection."
        )
    warnings.append(
        "Storage capacity, water level, and hydraulic parameters were not assigned."
    )
    return {
        "dataset_key": "hyderabad_tanks",
        "input_dataset": str(input_path),
        "output_dataset": str(output_path),
        "source_format": source_format,
        "feature_count_before": feature_count_before,
        "feature_count_after": len(clipped),
        "crs_before": source_crs,
        "crs_after": WEB_CRS,
        "geometry_types": geometry_types(clipped),
        "bounding_box": bounds(clipped),
        "invalid_geometry_count": clean_stats["invalid_geometry_count_before"],
        "empty_geometry_count": clean_stats["empty_geometry_count_before"],
        "duplicate_geometry_count": clean_stats["duplicate_geometry_count"],
        "clipping_performed": True,
        "important_fields_preserved": [
            str(column) for column in clipped.columns if column != clipped.geometry.name
        ],
        "warnings": warnings,
        "errors": [],
    }