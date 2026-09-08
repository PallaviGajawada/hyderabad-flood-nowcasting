"""Configuration and dataset locations for the nowcasting prototype."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(
    os.environ.get(
        "HYDERABAD_FLOOD_DATA",
        str(PROJECT_ROOT / "data"),
    )
).expanduser()
OUTPUTS_ROOT = PROJECT_ROOT / "outputs"
DATA_VALIDATION_REPORT = OUTPUTS_ROOT / "data_validation_report.json"
PREPROCESSED_ROOT = OUTPUTS_ROOT / "preprocessed"
PREPROCESSING_REPORT = PREPROCESSED_ROOT / "preprocessing_report.json"
PROCESSED_DEM_RASTER = PREPROCESSED_ROOT / "dem" / "dem_ghmc.tif"
PROCESSED_LANDCOVER_RASTER = PREPROCESSED_ROOT / "landcover" / "landcover_ghmc.tif"
PROCESSED_RAINFALL_NETCDF = PREPROCESSED_ROOT / "rainfall" / "imd_rainfall_ghmc.nc"
ROADS_PREPROCESSED_ROOT = PREPROCESSED_ROOT / "roads"
ROADS_GEOJSON = ROADS_PREPROCESSED_ROOT / "hyderabad_roads.geojson"
ROADS_GRAPHML = ROADS_PREPROCESSED_ROOT / "hyderabad_drive.graphml"
ROADS_METADATA = ROADS_PREPROCESSED_ROOT / "road_network_metadata.json"
RUNOFF_COEFFICIENTS_PATH = PROJECT_ROOT / "backend" / "runoff_coefficients.json"
MODEL_OUTPUT_ROOT = OUTPUTS_ROOT / "model"
RUNOFF_OUTPUT_ROOT = MODEL_OUTPUT_ROOT / "runoff"
RUNOFF_DEPTH_RASTER = RUNOFF_OUTPUT_ROOT / "runoff_depth_mm.tif"
RUNOFF_VOLUME_RASTER = RUNOFF_OUTPUT_ROOT / "runoff_volume_m3.tif"
RUNOFF_METADATA = RUNOFF_OUTPUT_ROOT / "runoff_metadata.json"
WEB_CRS = "EPSG:4326"
MODEL_CRS = "EPSG:32644"


@dataclass(frozen=True)
class DatasetPaths:
    """Expected source data locations for later preprocessing stages."""

    drainage_nalas: Path = DATA_ROOT / "drainage" / "ghmc_nalas" / "ghmc_nalas.json"
    inundation_areas: Path = (
        DATA_ROOT / "flood" / "ghmc_inundation" / "ghmc_inundation_areas.json"
    )
    tanks: Path = DATA_ROOT / "drainage" / "tanks" / "hyderabad_tanks.json"
    stream_network: Path = (
        DATA_ROOT / "drainage" / "streams" / "hyderabad_stream_network.json"
    )
    roads: Path = DATA_ROOT / "roads" / "osm" / "hyderabad_roads.gpkg"
    dem: Path = DATA_ROOT / "terrain" / "dem" / "hyderabad_dem_30m.tif"
    landcover: Path = (
        DATA_ROOT
        / "landcover"
        / "esaworldcover"
        / "hyderabad_landcover_10m.tif"
    )
    imd_rainfall: Path = (
        DATA_ROOT / "rainfall" / "imd_gauge" / "imd_rainfall_2024.nc"
    )
    historical_floods: Path = (
        DATA_ROOT
        / "flood"
        / "historical_floods"
        / "hyderabad_flooding_locations.kml"
    )
    ghmc_boundary: Path = (
        DATA_ROOT / "boundaries" / "ghmc" / "ghmc_boundary.json"
    )


DATASETS = DatasetPaths()