"""Tests for deterministic terrain-based surface-water routing."""

import numpy as np
import rasterio

from backend import main
from backend.models.surface_water_model import (
    accumulate_surface_water,
    cell_area_m2_from_transform,
    derive_flow_direction,
    run_surface_water_model,
)


def test_d8_flow_direction_is_deterministic():
    elevation = np.array(
        [
            [3.0, 2.0, 1.0],
            [4.0, 3.0, 2.0],
            [5.0, 4.0, 3.0],
        ],
        dtype=np.float32,
    )

    direction = derive_flow_direction(elevation, np.ones_like(elevation, dtype=bool))

    assert direction[0, 0] == 4
    assert direction[0, 2] == 0
    assert direction[2, 2] == 1


def test_flow_accumulation_conserves_volume_without_drainage():
    elevation = np.array([[3.0, 2.0, 1.0]], dtype=np.float32)
    valid = np.ones_like(elevation, dtype=bool)
    direction = derive_flow_direction(elevation, valid)
    incoming = np.array([[1.0, 2.0, 3.0]], dtype=np.float64)

    accumulation, retained, removed, error = accumulate_surface_water(
        incoming,
        direction,
        valid,
        np.zeros_like(valid),
        np.zeros_like(valid),
        routing_fraction=1.0,
        drainage_capture_fraction=0.0,
        drainage_effectiveness=0.0,
        maximum_drainage_removal_m3_per_cell=0.0,
    )

    assert accumulation[0, 2] == 6.0
    assert retained.sum() == incoming.sum()
    assert removed.sum() == 0.0
    assert abs(error) < 1e-9


def test_water_body_is_a_retention_sink():
    elevation = np.array([[3.0, 2.0, 1.0]], dtype=np.float32)
    valid = np.ones_like(elevation, dtype=bool)
    water = np.array([[False, False, True]])
    direction = derive_flow_direction(elevation, valid, water_body_mask=water)

    _, retained, _, error = accumulate_surface_water(
        np.array([[1.0, 2.0, 0.0]], dtype=np.float64),
        direction,
        valid,
        np.zeros_like(valid),
        water,
        routing_fraction=1.0,
        drainage_capture_fraction=0.0,
        drainage_effectiveness=0.0,
        maximum_drainage_removal_m3_per_cell=0.0,
    )

    assert direction[0, 2] == 0
    assert retained[0, 2] == 3.0
    assert abs(error) < 1e-9


def test_real_surface_water_outputs_alignment_and_nodata():
    result = run_surface_water_model()
    assert result["status"] == "ready"
    assert result["statistics"]["volume_conservation_check"] is True
    assert result["statistics"]["nala_interaction_cell_count"] > 0
    assert result["statistics"]["water_body_cell_count"] > 0
    assert result["statistics"]["prototype_drainage_removed_volume_m3"] > 0
    assert result["statistics"]["threshold_cell_counts"]["above_1_cm"] > 0

    with rasterio.open("outputs/preprocessed/dem/dem_ghmc.tif") as dem, rasterio.open(
        result["output_availability"]["surface_water_depth_mm"]
    ) as depth, rasterio.open(
        result["output_availability"]["flow_direction"]
    ) as direction:
        assert depth.crs == dem.crs
        assert depth.transform == dem.transform
        assert (depth.width, depth.height) == (dem.width, dem.height)
        assert direction.dtypes[0] == "int16"
        assert np.any(depth.read(1) == depth.nodata)
        assert np.any(direction.read(1) == direction.nodata)


def test_cell_area_and_api_summary_are_real():
    with rasterio.open("outputs/preprocessed/dem/dem_ghmc.tif") as dem:
        area = cell_area_m2_from_transform(dem.transform)
    assert area > 0

    status = main.surface_water_status()
    summary = main.surface_water_summary()
    assert status["ready"] is True
    assert status["drainage_assumption_status"] == "prototype_assumption"
    assert summary["volume_conservation_check"] is True
    assert summary["valid_cell_count"] > 0