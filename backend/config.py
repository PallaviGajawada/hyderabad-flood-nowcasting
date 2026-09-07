"""Configuration and dataset locations for the nowcasting prototype.

The paths are intentionally descriptive only. The first foundation does not
read or synthesize any of these datasets.
"""

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


@dataclass(frozen=True)
class DatasetPaths:
    """Expected source data locations for later preprocessing stages."""

    drainage_nalas: Path = DATA_ROOT / "drainage" / "ghmc_nalas" / "ghmc_nalas.json"
    inundation_areas: Path = (
        DATA_ROOT / "flood" / "ghmc_inundation" / "ghmc_inundation_areas.txt"
    )
    tanks: Path = DATA_ROOT / "drainage" / "tanks" / "hyderabad_tanks.txt"
    stream_network: Path = (
        DATA_ROOT / "drainage" / "streams" / "hyderabad_stream_network.txt"
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
        DATA_ROOT / "boundaries" / "ghmc" / "ghmc_boundary.geojson"
    )


DATASETS = DatasetPaths()