"""DEM clipping and terrain-derivative preprocessing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.mask import mask
from rasterio.transform import array_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import mapping

from ..config import DATASETS, MODEL_CRS, PREPROCESSED_ROOT, WEB_CRS
from .spatial import boundary_geometry, read_boundary


def _write_raster(path: Path, values: np.ndarray, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(values, 1)


def process_dem(
    *,
    input_path: Path = DATASETS.dem,
    output_dir: Path = PREPROCESSED_ROOT / "dem",
) -> dict[str, Any]:
    """Clip the DEM and calculate slope in a projected working CRS."""

    boundary_web = read_boundary(target_crs=WEB_CRS)
    boundary_shape_web = boundary_geometry(boundary_web)
    with rasterio.open(input_path) as source:
        source_boundary = boundary_web.to_crs(source.crs)
        clipped, clipped_transform = mask(
            source,
            [mapping(boundary_geometry(source_boundary))],
            crop=True,
            nodata=source.nodata,
        )
        clipped_values = clipped[0]
        source_nodata = source.nodata if source.nodata is not None else -9999.0
        source_bounds = array_bounds(
            clipped_values.shape[0],
            clipped_values.shape[1],
            clipped_transform,
        )
        dst_transform, dst_width, dst_height = calculate_default_transform(
            source.crs,
            MODEL_CRS,
            clipped_values.shape[1],
            clipped_values.shape[0],
            *source_bounds,
        )
        dem_nodata = -9999.0
        elevation = np.full((dst_height, dst_width), dem_nodata, dtype=np.float32)
        reproject(
            source=clipped_values,
            destination=elevation,
            src_transform=clipped_transform,
            src_crs=source.crs,
            src_nodata=source_nodata,
            dst_transform=dst_transform,
            dst_crs=MODEL_CRS,
            dst_nodata=dem_nodata,
            resampling=Resampling.bilinear,
        )

    target_boundary = boundary_web.to_crs(MODEL_CRS)
    inside = geometry_mask(
        [mapping(boundary_geometry(target_boundary))],
        out_shape=elevation.shape,
        transform=dst_transform,
        invert=True,
    )
    elevation[~inside] = dem_nodata
    valid = (elevation != dem_nodata) & np.isfinite(elevation)
    safe_elevation = np.where(valid, elevation, np.nan)
    pixel_x = abs(float(dst_transform.a))
    pixel_y = abs(float(dst_transform.e))
    gradient_y, gradient_x = np.gradient(safe_elevation, pixel_y, pixel_x)
    slope_degrees = np.degrees(np.arctan(np.sqrt(gradient_x**2 + gradient_y**2)))
    slope_percent = np.tan(np.radians(slope_degrees)) * 100.0
    slope_degrees = np.where(np.isfinite(slope_degrees) & inside, slope_degrees, -9999.0).astype(np.float32)
    slope_percent = np.where(np.isfinite(slope_percent) & inside, slope_percent, -9999.0).astype(np.float32)

    profile = {
        "driver": "GTiff",
        "height": dst_height,
        "width": dst_width,
        "count": 1,
        "dtype": "float32",
        "crs": MODEL_CRS,
        "transform": dst_transform,
        "nodata": dem_nodata,
        "compress": "deflate",
    }
    dem_path = output_dir / "dem_ghmc.tif"
    slope_path = output_dir / "slope_ghmc.tif"
    slope_percent_path = output_dir / "slope_percent_ghmc.tif"
    _write_raster(dem_path, elevation, profile)
    _write_raster(slope_path, slope_degrees, profile)
    _write_raster(slope_percent_path, slope_percent, profile)

    return {
        "dataset_key": "hyderabad_dem",
        "input_dataset": str(input_path),
        "output_dataset": [str(dem_path), str(slope_path), str(slope_percent_path)],
        "feature_count_before": None,
        "feature_count_after": None,
        "crs_before": str(source.crs),
        "crs_after": MODEL_CRS,
        "geometry_types": [],
        "bounding_box": [float(value) for value in target_boundary.total_bounds],
        "invalid_geometry_count": 0,
        "empty_geometry_count": 0,
        "clipping_performed": True,
        "raster_information": {
            "width": dst_width,
            "height": dst_height,
            "pixel_size": {"x": pixel_x, "y": pixel_y},
            "valid_elevation_pixels": int(valid.sum()),
            "elevation_min": float(np.nanmin(safe_elevation)),
            "elevation_max": float(np.nanmax(safe_elevation)),
            "slope_units": "degrees",
            "slope_percent_output": str(slope_percent_path),
        },
        "reprojection": {
            "from": str(source.crs),
            "to": MODEL_CRS,
            "reason": "Projected metres are required for slope and future distance/area calculations.",
        },
        "warnings": [
            "Slope is a terrain derivative only; no hydraulic parameters were assigned."
        ],
        "errors": [],
    }