"""Preprocessing for GHMC nalas and the supplied stream network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import DATASETS, PREPROCESSED_ROOT, WEB_CRS
from .spatial import (
    add_projected_length,
    bounds,
    clean_geometries,
    clip_to_boundary,
    geometry_types,
    read_boundary,
    read_vector,
    serialized_crs,
    write_geojson,
)


def _process_line_layer(
    *,
    dataset_key: str,
    input_path: Path,
    output_path: Path,
    boundary,
) -> dict[str, Any]:
    frame, source_format = read_vector(input_path)
    source_crs = serialized_crs(frame)
    feature_count_before = len(frame)
    cleaned, clean_stats = clean_geometries(frame)
    clipped = clip_to_boundary(cleaned, boundary=boundary, output_crs=WEB_CRS)
    clipped = add_projected_length(clipped)
    write_geojson(clipped, output_path)
    warnings: list[str] = []
    if len(clipped) < len(cleaned):
        warnings.append(
            f"{len(cleaned) - len(clipped)} features were outside the GHMC boundary or had no intersection."
        )
    return {
        "dataset_key": dataset_key,
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
        "length_field": "length_m_calc",
        "warnings": warnings,
        "errors": [],
    }


def process_drainage(
    *,
    output_dir: Path = PREPROCESSED_ROOT / "drainage",
) -> dict[str, Any]:
    """Clean, clip, and export the two available drainage line layers."""

    boundary = read_boundary(target_crs=WEB_CRS)
    return {
        "datasets": [
            _process_line_layer(
                dataset_key="ghmc_nalas",
                input_path=DATASETS.drainage_nalas,
                output_path=output_dir / "ghmc_nalas.geojson",
                boundary=boundary,
            ),
            _process_line_layer(
                dataset_key="hyderabad_stream_network",
                input_path=DATASETS.stream_network,
                output_path=output_dir / "streams.geojson",
                boundary=boundary,
            ),
        ],
        "warnings": [],
        "errors": [],
    }