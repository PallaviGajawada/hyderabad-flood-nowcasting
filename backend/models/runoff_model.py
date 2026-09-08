"""Transparent rainfall-to-runoff prototype on the processed DEM grid."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import xarray as xr
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject

from ..config import (
    PROCESSED_DEM_RASTER,
    PROCESSED_LANDCOVER_RASTER,
    RUNOFF_COEFFICIENTS_PATH,
    RUNOFF_DEPTH_RASTER,
    RUNOFF_METADATA,
    RUNOFF_OUTPUT_ROOT,
    RUNOFF_VOLUME_RASTER,
)
from .rainfall_interface import IMDRainfallProvider

RUNOFF_NODATA = -9999.0


def _read_coefficients(path: Path = RUNOFF_COEFFICIENTS_PATH) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "prototype_assumption":
        raise ValueError("Runoff coefficient configuration must be marked prototype_assumption.")
    classes = payload.get("classes", {})
    parsed: dict[int, dict[str, Any]] = {}
    for raw_code, details in classes.items():
        coefficient = details.get("runoff_coefficient")
        if not isinstance(coefficient, (int, float)) or not 0 <= coefficient <= 1:
            raise ValueError(f"Invalid runoff coefficient for WorldCover class {raw_code}.")
        parsed[int(raw_code)] = details
    return parsed


def coefficient_for_class(
    class_code: int,
    coefficients: dict[int, dict[str, Any]] | None = None,
) -> float:
    """Return a configured coefficient; unknown classes fail explicitly."""

    values = coefficients if coefficients is not None else _read_coefficients()
    try:
        return float(values[int(class_code)]["runoff_coefficient"])
    except KeyError as exc:
        raise KeyError(f"No runoff coefficient configured for WorldCover class {class_code}.") from exc


def runoff_depth_mm(
    rainfall_mm: np.ndarray,
    coefficient: float | np.ndarray,
) -> np.ndarray:
    """Apply the prototype equation without changing units."""

    return np.asarray(rainfall_mm, dtype=np.float32) * np.float32(coefficient)


def runoff_volume_m3(
    runoff_depth: np.ndarray,
    cell_area_m2: float | np.ndarray,
) -> np.ndarray:
    """Convert millimetre depth to cubic metres."""

    return np.asarray(runoff_depth, dtype=np.float32) / np.float32(1000.0) * np.asarray(
        cell_area_m2,
        dtype=np.float32,
    )


def _coordinate_resolution(values: np.ndarray, fallback: float = 0.25) -> float:
    if len(values) > 1:
        return float(np.median(np.abs(np.diff(values))))
    return fallback


def _rainfall_source_grid(
    rainfall: xr.DataArray,
    *,
    nodata: float = np.nan,
) -> tuple[np.ndarray, Affine, str, list[float]]:
    latitude_name = next(name for name in rainfall.coords if name.lower() in {"lat", "latitude", "y"})
    longitude_name = next(name for name in rainfall.coords if name.lower() in {"lon", "longitude", "x"})
    latitudes = np.asarray(rainfall[latitude_name].values, dtype=float)
    longitudes = np.asarray(rainfall[longitude_name].values, dtype=float)
    lat_resolution = _coordinate_resolution(latitudes)
    lon_resolution = _coordinate_resolution(longitudes)
    array = np.asarray(rainfall.values, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError(f"Expected one rainfall timestamp with 2D spatial data, received shape {array.shape}.")
    if latitudes[0] < latitudes[-1]:
        array = np.flipud(array)
        north = float(latitudes[-1]) + lat_resolution / 2
    else:
        north = float(latitudes[0]) + lat_resolution / 2
    west = float(longitudes.min()) - lon_resolution / 2
    transform = Affine.translation(west, north) @ Affine.scale(
        lon_resolution,
        -lat_resolution,
    )
    source_crs = "EPSG:4326"
    array = np.where(np.isfinite(array), array, nodata).astype(np.float32)
    return array, transform, source_crs, [lat_resolution, lon_resolution]


def _resample_to_reference(
    source: np.ndarray,
    *,
    source_transform: Affine,
    source_crs: str,
    source_nodata: float,
    reference: rasterio.DatasetReader,
    destination_nodata: float,
) -> np.ndarray:
    destination = np.full(
        (reference.height, reference.width),
        destination_nodata,
        dtype=np.float32,
    )
    reproject(
        source=source,
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        src_nodata=source_nodata,
        dst_transform=reference.transform,
        dst_crs=reference.crs,
        dst_nodata=destination_nodata,
        resampling=Resampling.nearest,
    )
    return destination


def _write_raster(path: Path, profile: dict[str, Any], values: np.ndarray) -> None:
    profile = profile.copy()
    profile.update(
        count=1,
        dtype="float32",
        nodata=RUNOFF_NODATA,
        compress="deflate",
        predictor=2,
        BIGTIFF="IF_SAFER",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(values.astype(np.float32), 1)


def _choose_peak_timestamp(provider: IMDRainfallProvider) -> np.datetime64:
    dataset = provider.load_dataset()
    rainfall = dataset["rainfall_mm"]
    spatial_dims = [dimension for dimension in rainfall.dims if dimension != "TIME"]
    means = rainfall.mean(dim=spatial_dims, skipna=True).values
    return np.datetime64(dataset["TIME"].values[int(np.nanargmax(means))])


def run_runoff_model(
    *,
    timestamp: str | np.datetime64 | None = None,
    rainfall_provider: IMDRainfallProvider | None = None,
    coefficient_path: Path = RUNOFF_COEFFICIENTS_PATH,
    depth_path: Path = RUNOFF_DEPTH_RASTER,
    volume_path: Path = RUNOFF_VOLUME_RASTER,
    metadata_path: Path = RUNOFF_METADATA,
) -> dict[str, Any]:
    """Run the rainfall-to-runoff prototype for one available rainfall scenario."""

    provider = rainfall_provider or IMDRainfallProvider()
    coefficients = _read_coefficients(coefficient_path)
    chosen_timestamp = (
        np.datetime64(timestamp) if timestamp is not None else _choose_peak_timestamp(provider)
    )
    rainfall = provider.get_rainfall(timestamp=chosen_timestamp)
    rainfall_array, rainfall_transform, rainfall_crs, rainfall_resolution = _rainfall_source_grid(rainfall)

    with rasterio.open(PROCESSED_DEM_RASTER) as reference:
        with rasterio.open(PROCESSED_LANDCOVER_RASTER) as landcover:
            landcover_values = _resample_to_reference(
                landcover.read(1).astype(np.float32),
                source_transform=landcover.transform,
                source_crs=str(landcover.crs),
                source_nodata=float(landcover.nodata or 0),
                reference=reference,
                destination_nodata=0,
            )
        rainfall_values = _resample_to_reference(
            rainfall_array,
            source_transform=rainfall_transform,
            source_crs=rainfall_crs,
            source_nodata=np.nan,
            reference=reference,
            destination_nodata=np.nan,
        )
        if str(reference.crs) != "EPSG:32644":
            raise ValueError(f"Expected processed DEM CRS EPSG:32644, received {reference.crs}.")
        reference_profile = reference.profile.copy()
        reference_values = reference.read(1)
        reference_valid = (
            np.ones(reference_values.shape, dtype=bool)
            if reference.nodata is None
            else reference_values != reference.nodata
        )
        reference_height, reference_width = reference.height, reference.width
        reference_transform = reference.transform
        reference_crs = str(reference.crs)
        reference_resolution = [float(value) for value in reference.res]

    coefficient_values = np.full(landcover_values.shape, np.nan, dtype=np.float32)
    water_mask = np.zeros(landcover_values.shape, dtype=bool)
    known_landcover = np.zeros(landcover_values.shape, dtype=bool)
    for class_code, details in coefficients.items():
        mask = landcover_values == class_code
        coefficient_values[mask] = float(details["runoff_coefficient"])
        known_landcover[mask] = True
        if details["land_cover_behavior"] == "water":
            water_mask[mask] = True

    valid_mask = np.isfinite(rainfall_values) & known_landcover & reference_valid
    depth_values = np.full(landcover_values.shape, RUNOFF_NODATA, dtype=np.float32)
    depth_values[valid_mask] = runoff_depth_mm(
        rainfall_values[valid_mask],
        coefficient_values[valid_mask],
    )
    depth_values[water_mask & valid_mask] = 0.0
    cell_area_m2 = abs(float(reference_transform.a * reference_transform.e))
    volume_values = np.full(landcover_values.shape, RUNOFF_NODATA, dtype=np.float32)
    volume_values[valid_mask] = runoff_volume_m3(depth_values[valid_mask], cell_area_m2)
    _write_raster(depth_path, reference_profile, depth_values)
    _write_raster(volume_path, reference_profile, volume_values)

    valid_depth = depth_values[depth_values != RUNOFF_NODATA]
    valid_volume = volume_values[volume_values != RUNOFF_NODATA]
    coefficient_classes_observed = sorted(
        int(value) for value in np.unique(landcover_values[np.isfinite(coefficient_values)])
    )
    metadata = {
        "status": "ready",
        "rainfall_source": provider.source_name,
        "rainfall_provider": provider.__class__.__name__,
        "rainfall_timestamp": str(chosen_timestamp),
        "rainfall_scenario": "maximum spatial-mean rainfall in the processed IMD period",
        "rainfall_available_start": str(provider.available_time_range()[0]),
        "rainfall_available_end": str(provider.available_time_range()[1]),
        "rainfall_units": rainfall.attrs.get("units", "mm"),
        "rainfall_source_resolution_degrees": rainfall_resolution,
        "landcover_source": str(PROCESSED_LANDCOVER_RASTER),
        "dem_reference": str(PROCESSED_DEM_RASTER),
        "coefficient_configuration": str(coefficient_path),
        "coefficient_configuration_status": "prototype_assumption",
        "coefficient_classes_observed": coefficient_classes_observed,
        "runoff_equation": "runoff_depth_mm = rainfall_depth_mm × runoff_coefficient",
        "volume_equation": "runoff_volume_m3 = runoff_depth_mm / 1000 × cell_area_m2",
        "prototype_assumptions": [
            "All configured runoff coefficients are transparent prototype assumptions, not supplied GHMC measurements.",
            "Nearest-neighbor resampling was used from the 0.25-degree IMD grid to the processed DEM grid.",
            "Nearest-neighbor resampling was used from the processed ESA WorldCover grid to the processed DEM grid.",
            "The output grid follows the processed DEM in EPSG:32644 at approximately 30 m resolution.",
            "WorldCover water classes are handled separately with zero direct runoff in this screening calculation.",
        ],
        "crs": reference_crs,
        "raster_dimensions": {"height": reference_height, "width": reference_width},
        "raster_resolution_m": reference_resolution,
        "raster_transform": [float(value) for value in reference_transform],
        "nodata": {
            "output": RUNOFF_NODATA,
            "landcover_source": 0,
            "rainfall_outside_source_coverage": "NaN",
            "handling": "Cells without rainfall coverage, nodata land cover, or an unconfigured class remain nodata.",
        },
        "cell_area_m2": cell_area_m2,
        "statistics": {
            "minimum_runoff_depth_mm": float(np.min(valid_depth)) if valid_depth.size else None,
            "maximum_runoff_depth_mm": float(np.max(valid_depth)) if valid_depth.size else None,
            "mean_runoff_depth_mm": float(np.mean(valid_depth)) if valid_depth.size else None,
            "total_runoff_volume_m3": float(np.sum(valid_volume)) if valid_volume.size else None,
            "valid_cell_count": int(valid_depth.size),
        },
        "output_availability": {
            "runoff_depth_mm": str(depth_path),
            "runoff_volume_m3": str(volume_path),
            "metadata": str(metadata_path),
        },
        "processing_timestamp": datetime.now(UTC).isoformat(),
        "warnings": [
            "This is a transparent rainfall-to-runoff screening prototype, not an engineering-grade hydraulic model.",
            "The IMD input is historical/scenario rainfall, not a Doppler Weather Radar nowcast.",
            "The processed rainfall grid does not cover the full southern extent of the GHMC DEM; those cells remain nodata.",
            "This stage does not simulate drainage capacity, pipe flow, backflow, flood routing, or street-level flood depth.",
        ],
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, default=str) + "\n", encoding="utf-8")
    return metadata