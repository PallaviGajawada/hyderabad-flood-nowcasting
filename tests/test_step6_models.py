"""Tests for the Step 6 drainage and flood-depth screening outputs."""

import json

import geopandas as gpd
import numpy as np
import pytest
import rasterio

from backend import main
from backend.config import (
    DRAINAGE_CAPACITY_INDEX_RASTER,
    DRAINAGE_INTERACTION_RASTER,
    DRAINAGE_METADATA,
    DISPLAY_DEPTH_CM,
    FLOOD_DEPTH_METADATA,
    FLOOD_RISK_CLASS_RASTER,
    RAW_EQUIVALENT_DEPTH_CM,
    REMAINING_SURFACE_WATER_VOLUME_RASTER,
    ROAD_FLOOD_RISK_GEOJSON,
)
from backend.models.flood_depth_model import classify_risk


def test_drainage_rasters_are_aligned_and_interaction_is_detected():
    with (
        rasterio.open("outputs/preprocessed/dem/dem_ghmc.tif") as dem,
        rasterio.open(DRAINAGE_INTERACTION_RASTER) as interaction,
        rasterio.open(DRAINAGE_CAPACITY_INDEX_RASTER) as capacity,
    ):
        assert interaction.crs == dem.crs
        assert interaction.transform == dem.transform
        assert (interaction.width, interaction.height) == (dem.width, dem.height)
        assert capacity.transform == dem.transform
        interaction_values = interaction.read(1)
        capacity_values = capacity.read(1)
        assert np.sum(interaction_values == 1) > 0
        assert np.sum(interaction_values == 2) > 0
        assert np.nanmax(capacity_values[capacity_values != capacity.nodata]) > 0


def test_drainage_capacity_and_flood_volume_conservation():
    drainage = json.loads(DRAINAGE_METADATA.read_text(encoding="utf-8"))
    flood = json.loads(FLOOD_DEPTH_METADATA.read_text(encoding="utf-8"))
    assert drainage["source"] == "prototype_assumption"
    assert flood["source"] == "prototype_assumption"
    stats = flood["statistics"]
    assert stats["prototype_drainage_removed_volume_m3"] > 0
    assert stats["remaining_surface_water_volume_m3"] < stats[
        "input_surface_water_volume_m3"
    ]
    assert abs(stats["volume_conservation_error_m3"]) < 1e-3
    assert stats["volume_conservation_check"] is True


def test_flood_depth_is_remaining_volume_divided_by_cell_area_and_is_capped():
    metadata = json.loads(FLOOD_DEPTH_METADATA.read_text(encoding="utf-8"))
    cell_area = metadata["grid"]["cell_area_m2"]
    with (
        rasterio.open(REMAINING_SURFACE_WATER_VOLUME_RASTER) as volume,
        rasterio.open(RAW_EQUIVALENT_DEPTH_CM) as raw_depth,
        rasterio.open(DISPLAY_DEPTH_CM) as display_depth,
    ):
        volume_values = volume.read(1)
        raw_values = raw_depth.read(1)
        display_values = display_depth.read(1)
        valid = volume_values != volume.nodata
        sample = np.flatnonzero(valid)[0]
        row, col = np.unravel_index(sample, volume_values.shape)
        assert raw_values[row, col] == pytest.approx(
            volume_values[row, col] / cell_area * 100,
            rel=1e-5,
        )
        assert np.nanmax(display_values[display_values != display_depth.nodata]) == 30.0
        assert np.nanmax(raw_values[raw_values != raw_depth.nodata]) > 30.0


def test_risk_classification_and_raster_nodata():
    risk = classify_risk(
        np.array([[0.0, 2.0, 5.0, 15.0, 30.0]]),
        low_threshold_cm=5,
        moderate_threshold_cm=15,
        high_threshold_cm=30,
        severe_threshold_cm=30,
    )
    assert risk.tolist() == [[0, 1, 2, 3, 4]]
    with rasterio.open(FLOOD_RISK_CLASS_RASTER) as raster:
        values = raster.read(1)
        assert raster.nodata in values
        assert np.any(values == 4)


def test_road_flood_risk_aggregation_output():
    roads = gpd.read_file(ROAD_FLOOD_RISK_GEOJSON, rows=10)
    required = {
        "prototype_max_depth_cm",
        "prototype_mean_depth_cm",
        "prototype_affected_percent",
        "prototype_max_risk_class",
    }
    assert required.issubset(roads.columns)
    assert len(roads) == 10
    metadata = json.loads(FLOOD_DEPTH_METADATA.read_text(encoding="utf-8"))
    assert metadata["road_flood_risk"]["road_edge_count"] > 0


def test_step6_api_status_and_summary():
    assert main.drainage_status()["ready"] is True
    assert main.drainage_summary()["status"] == "ready"
    assert main.flood_depth_status()["ready"] is True
    summary = main.flood_depth_summary()
    assert summary["volume_conservation_check"] is True
    road = main.road_flood_risk()
    assert road["status"] == "ready"
    assert road["road_edge_count"] > 0


def test_step6_status_has_no_fabricated_fallback_before_execution(monkeypatch, tmp_path):
    missing_drainage = tmp_path / "missing-drainage.json"
    missing_flood = tmp_path / "missing-flood.json"
    monkeypatch.setattr(main, "DRAINAGE_METADATA", missing_drainage)
    monkeypatch.setattr(main, "FLOOD_DEPTH_METADATA", missing_flood)

    drainage_status = main.drainage_status()
    flood_status = main.flood_depth_status()
    assert drainage_status["ready"] is False
    assert drainage_status["status"] == "not_run"
    assert drainage_status["statistics"] if "statistics" in drainage_status else True
    assert flood_status["ready"] is False
    assert flood_status["status"] == "not_run"
    with pytest.raises(Exception):
        main.flood_depth_summary()