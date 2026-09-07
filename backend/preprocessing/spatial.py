"""Shared spatial helpers for the reproducible preprocessing pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

from ..config import DATASETS, MODEL_CRS, WEB_CRS
from .data_validator import _read_vector_source


def read_vector(path: Path) -> tuple[gpd.GeoDataFrame, str]:
    """Read GeoJSON or ArcGIS FeatureSet JSON without changing the source."""

    return _read_vector_source(path)


def read_boundary(*, target_crs: str | None = None) -> gpd.GeoDataFrame:
    boundary, _ = read_vector(DATASETS.ghmc_boundary)
    if target_crs is not None and boundary.crs != target_crs:
        boundary = boundary.to_crs(target_crs)
    return boundary


def boundary_geometry(boundary: gpd.GeoDataFrame) -> Any:
    geometries = boundary.geometry.dropna()
    if hasattr(geometries, "union_all"):
        return geometries.union_all()
    return unary_union(geometries.tolist())


def clean_geometries(
    frame: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    """Repair invalid geometries in memory and remove empty/unusable rows."""

    cleaned = frame.copy()
    geometry = cleaned.geometry
    invalid_before = int((~geometry.is_valid & geometry.notna()).sum())
    empty_before = int((geometry.is_empty & geometry.notna()).sum())
    missing_before = int(geometry.isna().sum())
    if invalid_before:
        cleaned.loc[~geometry.is_valid & geometry.notna(), cleaned.geometry.name] = (
            geometry[~geometry.is_valid & geometry.notna()].map(make_valid)
        )
    geometry = cleaned.geometry
    cleaned = cleaned.loc[geometry.notna() & ~geometry.is_empty].copy()
    still_invalid = ~cleaned.geometry.is_valid
    cleaned = cleaned.loc[~still_invalid].copy()
    duplicate_keys = cleaned.geometry.map(
        lambda value: value.wkb_hex if value is not None else None
    )
    duplicate_mask = duplicate_keys.duplicated(keep="first")
    duplicate_count = int(duplicate_mask.sum())
    cleaned = cleaned.loc[~duplicate_mask].copy()
    return cleaned, {
        "invalid_geometry_count_before": invalid_before,
        "empty_geometry_count_before": empty_before + missing_before,
        "invalid_geometry_count_after": int((~cleaned.geometry.is_valid).sum()),
        "duplicate_geometry_count": duplicate_count,
    }


def clip_to_boundary(
    frame: gpd.GeoDataFrame,
    *,
    boundary: gpd.GeoDataFrame,
    output_crs: str = WEB_CRS,
) -> gpd.GeoDataFrame:
    """Clip a vector frame to the GHMC boundary and return interchange CRS."""

    source = frame.to_crs(output_crs) if frame.crs != output_crs else frame.copy()
    target_boundary = (
        boundary.to_crs(output_crs)
        if boundary.crs != output_crs
        else boundary
    )
    clip_geometry = boundary_geometry(target_boundary)
    source["geometry"] = source.geometry.intersection(clip_geometry)
    usable = source.geometry.map(
        lambda geometry: geometry is not None and not geometry.is_empty
    )
    source = source.loc[usable].copy()
    return source


def add_projected_length(
    frame: gpd.GeoDataFrame,
    *,
    field_name: str = "length_m_calc",
) -> gpd.GeoDataFrame:
    projected = frame.to_crs(MODEL_CRS)
    result = frame.copy()
    result[field_name] = projected.geometry.length.astype(float)
    return result


def write_geojson(frame: gpd.GeoDataFrame, path: Path) -> None:
    """Write a GeoJSON output, including a valid empty FeatureCollection."""

    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.to_crs(WEB_CRS) if frame.crs != WEB_CRS else frame.copy()
    if output.empty:
        path.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [],
                    "crs": {
                        "type": "name",
                        "properties": {"name": WEB_CRS},
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return
    output.to_file(path, driver="GeoJSON", index=False)


def geometry_types(frame: gpd.GeoDataFrame) -> list[str]:
    if frame.empty:
        return []
    return sorted(str(value) for value in frame.geometry.dropna().geom_type.unique())


def bounds(frame: gpd.GeoDataFrame) -> list[float] | None:
    if frame.empty:
        return None
    return [float(value) for value in frame.total_bounds]


def serialized_crs(frame: gpd.GeoDataFrame) -> str | None:
    return str(frame.crs) if frame.crs is not None else None


def geometry_mapping(frame: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    return [mapping(geometry) for geometry in frame.geometry if geometry is not None]