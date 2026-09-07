"""Validation helpers for the configured Hyderabad source datasets.

Validation is read-only: source files are opened and inspected in memory, but
never reprojected on disk, rewritten, or used to invent missing values.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr
from pyproj import CRS
from rasterio.warp import transform_bounds
from shapely.geometry import LineString, MultiLineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union

from ..config import DATASETS

DATASET_SPECS: dict[str, tuple[str, Path]] = {
    "ghmc_nalas": ("vector", DATASETS.drainage_nalas),
    "ghmc_inundation_areas": ("vector", DATASETS.inundation_areas),
    "hyderabad_tanks": ("vector", DATASETS.tanks),
    "hyderabad_stream_network": ("vector", DATASETS.stream_network),
    "hyderabad_roads": ("vector", DATASETS.roads),
    "hyderabad_dem": ("raster", DATASETS.dem),
    "hyderabad_landcover": ("raster", DATASETS.landcover),
    "imd_rainfall_2024": ("netcdf", DATASETS.imd_rainfall),
    "historical_floods": ("vector", DATASETS.historical_floods),
    "ghmc_boundary": ("vector", DATASETS.ghmc_boundary),
}
_REPORT_CACHE: tuple[tuple[Any, ...], dict[str, Any]] | None = None


def _result(dataset_key: str, dataset_type: str, path: Path) -> dict[str, Any]:
    return {
        "dataset_key": dataset_key,
        "path": str(path),
        "dataset_type": dataset_type,
        "exists": path.exists(),
        "readable": False,
        "validation_status": "missing" if not path.exists() else "unreadable",
        "details": {},
        "errors": [] if path.exists() else ["File does not exist."],
        "warnings": [],
    }


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _boundary_gdf() -> gpd.GeoDataFrame | None:
    """Read the GHMC boundary for in-memory extent checks only."""

    path = DATASETS.ghmc_boundary
    if not path.exists():
        return None
    try:
        boundary, _ = _read_vector_source(path)
        if boundary.empty or boundary.geometry.dropna().empty:
            return None
        return boundary
    except Exception:
        return None


def _boundary_geometry(boundary: gpd.GeoDataFrame) -> Any:
    geometries = boundary.geometry.dropna()
    if hasattr(geometries, "union_all"):
        return geometries.union_all()
    return unary_union(geometries.tolist())


def _esri_crs(spatial_reference: dict[str, Any] | None) -> str | None:
    if not spatial_reference:
        return None
    wkid = spatial_reference.get("latestWkid") or spatial_reference.get("wkid")
    if wkid:
        return f"EPSG:{wkid}"
    wkt = spatial_reference.get("wkt")
    return str(wkt) if wkt else None


def _esri_geometry_to_shape(geometry: dict[str, Any] | None) -> Any:
    if not geometry:
        return None
    if "x" in geometry and "y" in geometry:
        return Point(float(geometry["x"]), float(geometry["y"]))
    if "points" in geometry:
        return MultiPoint(
            [(float(x), float(y)) for x, y in geometry["points"]]
        )
    if "paths" in geometry:
        lines = [
            LineString([(float(x), float(y)) for x, y in path])
            for path in geometry["paths"]
            if len(path) >= 2
        ]
        if not lines:
            return None
        return lines[0] if len(lines) == 1 else MultiLineString(lines)
    if "rings" in geometry:
        polygons = [
            Polygon([(float(x), float(y)) for x, y in ring])
            for ring in geometry["rings"]
            if len(ring) >= 4
        ]
        polygons = [polygon for polygon in polygons if not polygon.is_empty]
        if not polygons:
            return None
        return polygons[0] if len(polygons) == 1 else unary_union(polygons)
    return None


def _read_vector_source(path: Path) -> tuple[gpd.GeoDataFrame, str]:
    """Read GeoJSON or ArcGIS FeatureSet JSON into an in-memory GeoDataFrame."""

    if path.suffix.lower() in {".json", ".txt", ".geojson"}:
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict) and "features" in payload:
                rows: list[dict[str, Any]] = []
                for feature in payload.get("features", []):
                    attributes = dict(feature.get("attributes") or feature.get("properties") or {})
                    attributes["geometry"] = (
                        _esri_geometry_to_shape(feature.get("geometry"))
                        if "geometryType" in payload or "spatialReference" in payload
                        else feature.get("geometry")
                    )
                    rows.append(attributes)
                crs = _esri_crs(payload.get("spatialReference"))
                frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)
                frame.attrs["source_geometry_type"] = payload.get("geometryType")
                return (
                    frame,
                    "ArcGIS FeatureSet JSON"
                    if payload.get("geometryType") or payload.get("spatialReference")
                    else "GeoJSON",
                )
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    return gpd.read_file(path), "OGR-readable vector"


def _vector_overlap(
    frame: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame | None,
) -> bool | None:
    if boundary is None or frame.empty or frame.geometry.dropna().empty:
        return None
    if frame.crs is None or boundary.crs is None:
        return None
    try:
        comparable = frame
        if CRS.from_user_input(frame.crs) != CRS.from_user_input(boundary.crs):
            comparable = frame.to_crs(boundary.crs)
        extent = box(*comparable.geometry.total_bounds)
        return bool(extent.intersects(_boundary_geometry(boundary)))
    except Exception:
        return None


def _raster_overlap(
    bounds: tuple[float, float, float, float],
    raster_crs: Any,
    boundary: gpd.GeoDataFrame | None,
) -> bool | None:
    if boundary is None or raster_crs is None or boundary.crs is None:
        return None
    try:
        boundary_crs = CRS.from_user_input(boundary.crs)
        raster_bounds = bounds
        if CRS.from_user_input(raster_crs) != boundary_crs:
            raster_bounds = transform_bounds(
                raster_crs,
                boundary_crs,
                *bounds,
                densify_pts=21,
            )
        return bool(box(*raster_bounds).intersects(_boundary_geometry(boundary)))
    except Exception:
        return None


def validate_vector(
    path: Path,
    *,
    dataset_key: str | None = None,
    boundary: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Validate a vector dataset without changing its source file."""

    key = dataset_key or path.stem
    result = _result(key, "vector", path)
    if not path.exists():
        return result
    try:
        frame, source_format = _read_vector_source(path)
        geometry = frame.geometry
        missing_values = {
            str(column): int(count)
            for column, count in frame.isna().sum().items()
            if int(count) > 0
        }
        invalid_count = int((~geometry.is_valid & geometry.notna()).sum())
        empty_count = int((geometry.is_empty & geometry.notna()).sum())
        result["readable"] = True
        result["validation_status"] = "valid" if invalid_count == 0 else "invalid"
        result["details"] = {
            "feature_count": int(len(frame)),
            "source_format": source_format,
            "source_geometry_type": (
                frame.attrs.get("source_geometry_type")
                if frame.attrs.get("source_geometry_type")
                else None
            ),
            "geometry_types": sorted(
                str(value)
                for value in geometry.dropna().geom_type.unique()
            ),
            "crs": str(frame.crs) if frame.crs is not None else None,
            "bounding_box": [
                _as_float(value) for value in frame.total_bounds
            ]
            if not frame.empty
            else None,
            "important_fields": [
                str(column) for column in frame.columns if column != frame.geometry.name
            ],
            "invalid_geometry_count": invalid_count,
            "empty_geometry_count": empty_count,
            "missing_values": missing_values,
            "overlaps_ghmc_boundary": _vector_overlap(frame, boundary),
        }
        if frame.crs is None:
            result["warnings"].append("CRS is missing.")
        if result["details"]["overlaps_ghmc_boundary"] is None and boundary is not None:
            result["warnings"].append(
                "Extent overlap could not be evaluated because CRS or geometry is missing."
            )
    except Exception as exc:
        result["errors"] = [f"{type(exc).__name__}: {exc}"]
    return result


def validate_raster(
    path: Path,
    *,
    dataset_key: str | None = None,
    boundary: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Validate raster metadata and value range without modifying the raster."""

    key = dataset_key or path.stem
    result = _result(key, "raster", path)
    if not path.exists():
        return result
    try:
        with rasterio.open(path) as raster:
            minimum: float | None = None
            maximum: float | None = None
            missing_values: dict[str, int] = {}
            valid_values: dict[str, int] = {}
            for band_number in range(1, raster.count + 1):
                band_min: float | None = None
                band_max: float | None = None
                missing_count = 0
                valid_count = 0
                for _, window in raster.block_windows(band_number):
                    values = raster.read(band_number, window=window, masked=True)
                    valid = values.compressed()
                    missing_count += int(values.size - valid.size)
                    valid_count += int(valid.size)
                    if valid.size == 0:
                        continue
                    block_min = _as_float(valid.min())
                    block_max = _as_float(valid.max())
                    if block_min is not None:
                        band_min = block_min if band_min is None else min(band_min, block_min)
                    if block_max is not None:
                        band_max = block_max if band_max is None else max(band_max, block_max)
                missing_values[f"band_{band_number}"] = missing_count
                valid_values[f"band_{band_number}"] = valid_count
                if band_min is not None:
                    minimum = band_min if minimum is None else min(minimum, band_min)
                if band_max is not None:
                    maximum = band_max if maximum is None else max(maximum, band_max)

            bounds = tuple(float(value) for value in raster.bounds)
            result["readable"] = True
            result["validation_status"] = "valid"
            result["details"] = {
                "width": int(raster.width),
                "height": int(raster.height),
                "band_count": int(raster.count),
                "crs": str(raster.crs) if raster.crs is not None else None,
                "pixel_size": {
                    "x": abs(float(raster.transform.a)),
                    "y": abs(float(raster.transform.e)),
                },
                "bounds": list(bounds),
                "min_value": minimum,
                "max_value": maximum,
                "nodata_value": _as_float(raster.nodata),
                "missing_values": missing_values,
                "valid_value_count": valid_values,
                "overlaps_ghmc_boundary": _raster_overlap(
                    bounds,
                    raster.crs,
                    boundary,
                ),
            }
            if raster.crs is None:
                result["warnings"].append("CRS is missing.")
    except Exception as exc:
        result["errors"] = [f"{type(exc).__name__}: {exc}"]
    return result


def _coordinate_name(dataset: xr.Dataset, names: tuple[str, ...]) -> str | None:
    lowered = {name.lower(): name for name in dataset.variables}
    for name in names:
        if name in lowered:
            return lowered[name]
    return None


def _coordinate_extent(dataset: xr.Dataset, name: str | None) -> tuple[float, float] | None:
    if name is None:
        return None
    values = np.asarray(dataset[name].values, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    return float(finite.min()), float(finite.max())


def validate_netcdf(
    path: Path,
    *,
    dataset_key: str | None = None,
) -> dict[str, Any]:
    """Validate NetCDF dimensions, variables, coordinates, and rainfall metadata."""

    key = dataset_key or path.stem
    result = _result(key, "netcdf", path)
    if not path.exists():
        return result
    try:
        with xr.open_dataset(path, decode_times=False) as dataset:
            dimensions = {str(name): int(size) for name, size in dataset.sizes.items()}
            variables = [str(name) for name in dataset.data_vars]
            coordinate_names = [str(name) for name in dataset.coords]
            rainfall_variables = [
                name
                for name in variables
                if any(token in name.lower() for token in ("rain", "precip", "prcp"))
            ]
            rainfall_variable = rainfall_variables[0] if rainfall_variables else None
            time_name = _coordinate_name(
                dataset,
                ("time", "valid_time", "datetime", "date"),
            )
            latitude_name = _coordinate_name(dataset, ("lat", "latitude", "y"))
            longitude_name = _coordinate_name(dataset, ("lon", "longitude", "x"))
            latitude_extent = _coordinate_extent(dataset, latitude_name)
            longitude_extent = _coordinate_extent(dataset, longitude_name)
            units = (
                str(dataset[rainfall_variable].attrs.get("units"))
                if rainfall_variable is not None
                and dataset[rainfall_variable].attrs.get("units") is not None
                else None
            )
            result["readable"] = True
            result["validation_status"] = "valid"
            result["details"] = {
                "dimensions": dimensions,
                "variables": variables,
                "coordinate_names": coordinate_names,
                "time_dimension": {
                    "name": time_name,
                    "size": dimensions.get(time_name) if time_name else None,
                },
                "rainfall_variable": rainfall_variable,
                "rainfall_variables": rainfall_variables,
                "units": units,
                "spatial_extent": {
                    "latitude": latitude_extent,
                    "longitude": longitude_extent,
                },
            }
            if rainfall_variable is None:
                result["warnings"].append(
                    "No rainfall-like data variable was identified by name."
                )
    except Exception as exc:
        result["errors"] = [f"{type(exc).__name__}: {exc}"]
    return result


def _dataset_signature() -> tuple[Any, ...]:
    signature: list[Any] = []
    for dataset_key, (dataset_type, path) in DATASET_SPECS.items():
        try:
            stat = path.stat()
            signature.append(
                (
                    dataset_key,
                    dataset_type,
                    str(path),
                    True,
                    stat.st_mtime_ns,
                    stat.st_size,
                )
            )
        except FileNotFoundError:
            signature.append((dataset_key, dataset_type, str(path), False, None, None))
    return tuple(signature)


def validate_all_datasets(
    *,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Validate every configured dataset and optionally write a JSON report."""

    global _REPORT_CACHE
    signature = _dataset_signature()
    cache_key = (str(report_path) if report_path is not None else "", *signature)
    if _REPORT_CACHE is not None and _REPORT_CACHE[0] == cache_key:
        return _REPORT_CACHE[1]

    boundary = _boundary_gdf()
    datasets: dict[str, dict[str, Any]] = {}
    for dataset_key, (dataset_type, path) in DATASET_SPECS.items():
        if dataset_type == "vector":
            datasets[dataset_key] = validate_vector(
                path,
                dataset_key=dataset_key,
                boundary=boundary,
            )
        elif dataset_type == "raster":
            datasets[dataset_key] = validate_raster(
                path,
                dataset_key=dataset_key,
                boundary=boundary,
            )
        else:
            datasets[dataset_key] = validate_netcdf(
                path,
                dataset_key=dataset_key,
            )

    statuses = [item["validation_status"] for item in datasets.values()]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "datasets": datasets,
        "summary": {
            "total": len(datasets),
            "found": sum(bool(item["exists"]) for item in datasets.values()),
            "readable": sum(bool(item["readable"]) for item in datasets.values()),
            "valid": statuses.count("valid"),
            "missing": statuses.count("missing"),
            "unreadable": statuses.count("unreadable"),
            "invalid": statuses.count("invalid"),
        },
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, default=_json_default) + "\n",
            encoding="utf-8",
        )
    _REPORT_CACHE = (cache_key, report)
    return report