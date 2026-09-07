"""Historical IMD rainfall extraction into a standardized GHMC NetCDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import xarray as xr

from ..config import DATASETS, PREPROCESSED_ROOT, WEB_CRS
from .spatial import bounds, read_boundary


def _coordinate_slice(values: Any, lower: float, upper: float) -> slice:
    first = float(values[0])
    last = float(values[-1])
    return slice(lower, upper) if first <= last else slice(upper, lower)


def process_rainfall(
    *,
    input_path: Path = DATASETS.imd_rainfall,
    output_dir: Path = PREPROCESSED_ROOT / "rainfall",
) -> dict[str, Any]:
    """Extract the GHMC bounding region and rename rainfall to rainfall_mm."""

    boundary = read_boundary(target_crs=WEB_CRS)
    boundary_bounds = bounds(boundary)
    if boundary_bounds is None:
        raise ValueError("GHMC boundary has no usable extent.")
    min_lon, min_lat, max_lon, max_lat = boundary_bounds
    with xr.open_dataset(input_path) as source:
        variables = list(source.data_vars)
        rainfall_variables = [
            name
            for name in variables
            if any(token in name.lower() for token in ("rain", "precip", "prcp"))
        ]
        if not rainfall_variables:
            raise ValueError("No rainfall-like variable found in the IMD NetCDF.")
        rainfall_name = rainfall_variables[0]
        units = source[rainfall_name].attrs.get("units")
        if str(units).lower() != "mm":
            raise ValueError(f"Expected millimetre rainfall, received units={units!r}.")
        latitude_name = next(
            (name for name in source.coords if name.lower() in {"lat", "latitude", "y"}),
            None,
        )
        longitude_name = next(
            (name for name in source.coords if name.lower() in {"lon", "longitude", "x"}),
            None,
        )
        time_name = next(
            (name for name in source.coords if name.lower() in {"time", "valid_time", "datetime", "date"}),
            None,
        )
        if not latitude_name or not longitude_name or not time_name:
            raise ValueError("IMD NetCDF is missing latitude, longitude, or time coordinates.")
        selected = source.sel(
            {
                latitude_name: _coordinate_slice(source[latitude_name].values, min_lat, max_lat),
                longitude_name: _coordinate_slice(source[longitude_name].values, min_lon, max_lon),
            }
        )[[rainfall_name]].rename({rainfall_name: "rainfall_mm"}).load()
        selected["rainfall_mm"].attrs.update(
            {
                "units": "mm",
                "source_variable": rainfall_name,
                "source_dataset": str(input_path),
                "description": "Historical IMD rainfall; not radar nowcast data.",
            }
        )
        selected.attrs.update(
            {
                "source_provider": "IMD",
                "source_type": "historical",
                "analysis_extent": "GHMC bounding box",
            }
        )
        dimensions = {str(name): int(size) for name, size in selected.sizes.items()}
        coordinate_names = list(selected.coords)
        spatial_extent = {
            "latitude": [
                float(selected[latitude_name].min()),
                float(selected[latitude_name].max()),
            ],
            "longitude": [
                float(selected[longitude_name].min()),
                float(selected[longitude_name].max()),
            ],
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "imd_rainfall_ghmc.nc"
    selected.to_netcdf(output_path)
    return {
        "dataset_key": "imd_rainfall_2024",
        "input_dataset": str(input_path),
        "output_dataset": str(output_path),
        "feature_count_before": None,
        "feature_count_after": None,
        "crs_before": None,
        "crs_after": None,
        "geometry_types": [],
        "bounding_box": boundary_bounds,
        "invalid_geometry_count": 0,
        "empty_geometry_count": 0,
        "clipping_performed": True,
        "rainfall_information": {
            "variable": "rainfall_mm",
            "source_variable": rainfall_name,
            "units": "mm",
            "dimensions": dimensions,
            "coordinates": coordinate_names,
            "time_dimension": time_name,
            "spatial_extent": spatial_extent,
            "source_type": "historical IMD rainfall, not radar nowcast",
        },
        "warnings": [
            "The extracted IMD series is historical rainfall and must not be treated as radar nowcast data."
        ],
        "errors": [],
    }