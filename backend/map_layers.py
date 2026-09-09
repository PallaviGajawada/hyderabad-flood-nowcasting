"""Cached, lightweight GeoJSON layers for the Step 8 demonstration map."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from shapely.geometry import box, mapping
from shapely.ops import transform as transform_geometry

from .config import (
    FORECAST_OUTPUT_ROOT,
    PROCESSED_NALAS_VECTOR,
    PROCESSED_WATERBODIES_VECTOR,
    ROAD_FLOOD_RISK_GEOJSON,
    ROADS_GEOJSON,
    WEB_CRS,
)
from .models.forecast_model import forecast_factor, load_forecast_assumptions
from .preprocessing.spatial import boundary_geometry, read_boundary

MAX_ROAD_FEATURES = 3_000
FLOOD_GRID_ROWS = 60
FLOOD_GRID_COLUMNS = 80


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _feature(geometry: Any, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": mapping(geometry),
        "properties": _json_value(properties),
    }


def _collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def _frame_features(
    frame: gpd.GeoDataFrame,
    *,
    properties: list[str],
    simplify_tolerance: float,
    limit: int | None = None,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    selected = frame.head(limit) if limit is not None else frame
    for _, row in selected.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue
        geometry = geometry.simplify(simplify_tolerance, preserve_topology=True)
        if geometry.is_empty:
            continue
        values = {
            key: row[key]
            for key in properties
            if key in row.index and key != "geometry"
        }
        features.append(_feature(geometry, values))
    return _collection(features)


@lru_cache(maxsize=1)
def _static_layers() -> dict[str, dict[str, Any]]:
    boundary = read_boundary(target_crs=WEB_CRS)
    boundary_shape = boundary_geometry(boundary)
    layers: dict[str, dict[str, Any]] = {
        "boundary": _collection([_feature(boundary_shape, {"name": "GHMC boundary"})]),
    }

    nalas = gpd.read_file(PROCESSED_NALAS_VECTOR)
    if nalas.crs is not None and str(nalas.crs) != WEB_CRS:
        nalas = nalas.to_crs(WEB_CRS)
    layers["nalas"] = _frame_features(
        nalas,
        properties=["Nala_ID", "Nala_Name", "ZONE_NAME", "length_m_calc"],
        simplify_tolerance=0.00006,
    )

    waterbodies = gpd.read_file(PROCESSED_WATERBODIES_VECTOR)
    if waterbodies.crs is not None and str(waterbodies.crs) != WEB_CRS:
        waterbodies = waterbodies.to_crs(WEB_CRS)
    layers["waterbodies"] = _frame_features(
        waterbodies,
        properties=["Descr_2", "Descr_3", "LU_Code", "Shape_Area"],
        simplify_tolerance=0.00015,
    )

    roads = gpd.read_file(ROADS_GEOJSON, rows=MAX_ROAD_FEATURES)
    if roads.crs is not None and str(roads.crs) != WEB_CRS:
        roads = roads.to_crs(WEB_CRS)
    layers["roads"] = _frame_features(
        roads,
        properties=["osmid", "highway", "name", "ref", "length"],
        simplify_tolerance=0.00003,
        limit=MAX_ROAD_FEATURES,
    )

    risk = gpd.read_file(ROAD_FLOOD_RISK_GEOJSON, rows=MAX_ROAD_FEATURES)
    if risk.crs is not None and str(risk.crs) != WEB_CRS:
        risk = risk.to_crs(WEB_CRS)
    layers["road_risk"] = _frame_features(
        risk,
        properties=[
            "osmid",
            "highway",
            "name",
            "ref",
            "prototype_max_depth_cm",
            "prototype_mean_depth_cm",
            "prototype_affected_percent",
            "prototype_max_risk_class",
        ],
        simplify_tolerance=0.00003,
        limit=MAX_ROAD_FEATURES,
    )
    return layers


def _flood_layer(forecast_minutes: int) -> dict[str, Any]:
    raster_path = (
        FORECAST_OUTPUT_ROOT
        / f"tplus_{forecast_minutes:03d}"
        / "flood_depth_cm.tif"
    )
    risk_path = (
        FORECAST_OUTPUT_ROOT
        / f"tplus_{forecast_minutes:03d}"
        / "flood_risk_class.tif"
    )
    with rasterio.open(raster_path) as depth_source, rasterio.open(risk_path) as risk_source:
        rows = min(FLOOD_GRID_ROWS, depth_source.height)
        columns = min(FLOOD_GRID_COLUMNS, depth_source.width)
        depth = depth_source.read(
            1,
            out_shape=(rows, columns),
            resampling=Resampling.average,
        )
        risk = risk_source.read(
            1,
            out_shape=(rows, columns),
            resampling=Resampling.nearest,
        )
        transform = from_bounds(
            *depth_source.bounds,
            columns,
            rows,
        )
        source_to_web = Transformer.from_crs(
            depth_source.crs,
            WEB_CRS,
            always_xy=True,
        ).transform
        cell_width = (depth_source.bounds.right - depth_source.bounds.left) / columns
        cell_height = (depth_source.bounds.top - depth_source.bounds.bottom) / rows
        features: list[dict[str, Any]] = []
        for row in range(rows):
            for column in range(columns):
                value = float(depth[row, column])
                if not np.isfinite(value) or value <= 0:
                    continue
                x0, y0 = transform * (column, row)
                x1, y1 = x0 + cell_width, y0 - cell_height
                geometry = transform_geometry(
                    source_to_web,
                    box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
                )
                features.append(
                    _feature(
                        geometry,
                        {
                            "depth_cm": round(value, 2),
                            "risk_class": int(max(0, risk[row, column])),
                            "horizon_minutes": forecast_minutes,
                        },
                    )
                )
    return _collection(features)


@lru_cache(maxsize=8)
def get_map_layers(forecast_minutes: int) -> dict[str, Any]:
    """Return cached, simplified layers safe for browser rendering."""
    static = _static_layers()
    scaled_roads = json.loads(json.dumps(static["road_risk"]))
    factor = forecast_factor(forecast_minutes, load_forecast_assumptions())
    for feature in scaled_roads["features"]:
        properties = feature.get("properties", {})
        depth = float(properties.get("prototype_max_depth_cm") or 0) * factor
        properties["forecast_max_depth_cm"] = round(depth, 2)
        properties["forecast_mean_depth_cm"] = round(
            float(properties.get("prototype_mean_depth_cm") or 0) * factor,
            2,
        )
        properties["forecast_risk_class"] = (
            0 if depth <= 0 else 1 if depth <= 5 else 2 if depth <= 15 else 3 if depth <= 30 else 4
        )
        properties["forecast_minutes"] = forecast_minutes
    return {
        "status": "ready",
        "forecast_minutes": forecast_minutes,
        "layers": {
            **static,
            "road_risk": scaled_roads,
            "flood": _flood_layer(forecast_minutes),
        },
        "limits": {
            "roads_returned": MAX_ROAD_FEATURES,
            "flood_grid": f"{FLOOD_GRID_COLUMNS}x{FLOOD_GRID_ROWS}",
            "note": "Web visualization layers are simplified; original scientific outputs are unchanged.",
        },
    }