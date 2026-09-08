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
PROCESSED_SLOPE_PERCENT_RASTER = PREPROCESSED_ROOT / "dem" / "slope_percent_ghmc.tif"
PROCESSED_LANDCOVER_RASTER = PREPROCESSED_ROOT / "landcover" / "landcover_ghmc.tif"
PROCESSED_RAINFALL_NETCDF = PREPROCESSED_ROOT / "rainfall" / "imd_rainfall_ghmc.nc"
PROCESSED_NALAS_VECTOR = PREPROCESSED_ROOT / "drainage" / "ghmc_nalas.geojson"
PROCESSED_WATERBODIES_VECTOR = PREPROCESSED_ROOT / "waterbodies" / "hyderabad_tanks.geojson"
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
SURFACE_WATER_ASSUMPTIONS_PATH = PROJECT_ROOT / "backend" / "surface_water_assumptions.json"
SURFACE_WATER_OUTPUT_ROOT = MODEL_OUTPUT_ROOT / "surface_water"
SURFACE_WATER_DEPTH_MM = SURFACE_WATER_OUTPUT_ROOT / "surface_water_depth_mm.tif"
SURFACE_WATER_DEPTH_CM = SURFACE_WATER_OUTPUT_ROOT / "surface_water_depth_cm.tif"
SURFACE_WATER_VOLUME = SURFACE_WATER_OUTPUT_ROOT / "surface_water_volume_m3.tif"
FLOW_DIRECTION_RASTER = SURFACE_WATER_OUTPUT_ROOT / "flow_direction.tif"
FLOW_ACCUMULATION_RASTER = SURFACE_WATER_OUTPUT_ROOT / "flow_accumulation.tif"
NALA_INTERACTION_RASTER = SURFACE_WATER_OUTPUT_ROOT / "nala_interaction.tif"
SURFACE_WATER_METADATA = SURFACE_WATER_OUTPUT_ROOT / "surface_water_metadata.json"
DRAINAGE_ASSUMPTIONS_PATH = PROJECT_ROOT / "backend" / "drainage_assumptions.json"
DRAINAGE_OUTPUT_ROOT = MODEL_OUTPUT_ROOT / "drainage"
DRAINAGE_INTERACTION_RASTER = DRAINAGE_OUTPUT_ROOT / "drainage_interaction.tif"
DRAINAGE_CAPACITY_INDEX_RASTER = DRAINAGE_OUTPUT_ROOT / "drainage_capacity_index.tif"
DRAINAGE_METADATA = DRAINAGE_OUTPUT_ROOT / "drainage_metadata.json"
FLOOD_DEPTH_ASSUMPTIONS_PATH = PROJECT_ROOT / "backend" / "flood_depth_assumptions.json"
FLOOD_DEPTH_OUTPUT_ROOT = MODEL_OUTPUT_ROOT / "flood_depth"
RAW_EQUIVALENT_DEPTH_MM = FLOOD_DEPTH_OUTPUT_ROOT / "raw_equivalent_depth_mm.tif"
RAW_EQUIVALENT_DEPTH_CM = FLOOD_DEPTH_OUTPUT_ROOT / "raw_equivalent_depth_cm.tif"
DISPLAY_DEPTH_CM = FLOOD_DEPTH_OUTPUT_ROOT / "display_depth_cm.tif"
FLOOD_RISK_CLASS_RASTER = FLOOD_DEPTH_OUTPUT_ROOT / "flood_risk_class.tif"
DRAINAGE_REMOVED_VOLUME_RASTER = FLOOD_DEPTH_OUTPUT_ROOT / "drainage_removed_volume_m3.tif"
REMAINING_SURFACE_WATER_VOLUME_RASTER = (
    FLOOD_DEPTH_OUTPUT_ROOT / "remaining_surface_water_volume_m3.tif"
)
FLOOD_DEPTH_METADATA = FLOOD_DEPTH_OUTPUT_ROOT / "flood_depth_metadata.json"
ROAD_FLOOD_RISK_GEOJSON = FLOOD_DEPTH_OUTPUT_ROOT / "road_flood_risk.geojson"
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