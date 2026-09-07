"""ESA WorldCover clipping and observed-class cataloguing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping

from ..config import DATASETS, PREPROCESSED_ROOT, WEB_CRS
from .spatial import boundary_geometry, read_boundary

WORLD_COVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def process_landcover(
    *,
    input_path: Path = DATASETS.landcover,
    output_dir: Path = PREPROCESSED_ROOT / "landcover",
) -> dict[str, Any]:
    """Clip WorldCover to GHMC and catalog only classes actually observed."""

    boundary = read_boundary(target_crs=WEB_CRS)
    with rasterio.open(input_path) as source:
        clipped, transform = mask(
            source,
            [mapping(boundary_geometry(boundary))],
            crop=True,
            nodata=source.nodata,
        )
        profile = source.profile.copy()
        profile.update(
            height=clipped.shape[1],
            width=clipped.shape[2],
            transform=transform,
            compress="deflate",
        )
        values = clipped[0]
        nodata = source.nodata
        observed = np.unique(values)
        observed = [
            int(value)
            for value in observed
            if nodata is None or value != nodata
        ]
        unknown = [code for code in observed if code not in WORLD_COVER_CLASSES]
        source_crs = str(source.crs)
        source_shape = (source.height, source.width)

    output_dir.mkdir(parents=True, exist_ok=True)
    landcover_path = output_dir / "landcover_ghmc.tif"
    classes_path = output_dir / "worldcover_classes.json"
    with rasterio.open(landcover_path, "w", **profile) as destination:
        destination.write(clipped)
    class_lookup = {
        str(code): {
            "label": WORLD_COVER_CLASSES[code],
            "observed_in_ghmc": True,
        }
        for code in observed
        if code in WORLD_COVER_CLASSES
    }
    classes_path.write_text(
        json.dumps(
            {
                "source": "ESA WorldCover class legend",
                "source_dataset": str(input_path),
                "observed_class_codes": observed,
                "classes": class_lookup,
                "hydraulic_parameters_assigned": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "dataset_key": "hyderabad_landcover",
        "input_dataset": str(input_path),
        "output_dataset": [str(landcover_path), str(classes_path)],
        "feature_count_before": None,
        "feature_count_after": None,
        "crs_before": source_crs,
        "crs_after": source_crs,
        "geometry_types": [],
        "bounding_box": [float(value) for value in boundary.total_bounds],
        "invalid_geometry_count": 0,
        "empty_geometry_count": 0,
        "clipping_performed": True,
        "raster_information": {
            "source_dimensions": {"width": source_shape[1], "height": source_shape[0]},
            "output_dimensions": {"width": int(clipped.shape[2]), "height": int(clipped.shape[1])},
            "pixel_size": {"x": abs(float(transform.a)), "y": abs(float(transform.e))},
            "observed_class_codes": observed,
        },
        "warnings": [
            f"Observed source class codes without a configured label: {unknown}"
            if unknown
            else "No unrecognized WorldCover class codes observed."
        ],
        "errors": [],
    }