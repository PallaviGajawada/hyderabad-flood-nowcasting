"""Tests for the transparent rainfall-to-runoff prototype."""

import json

import numpy as np
import rasterio

from backend import main
from backend.models.rainfall_interface import IMDRainfallProvider
from backend.models.runoff_model import (
    coefficient_for_class,
    runoff_depth_mm,
    runoff_volume_m3,
    run_runoff_model,
)


def test_rainfall_provider_reads_timestamp_and_preserves_units():
    provider = IMDRainfallProvider()

    rainfall = provider.get_rainfall(timestamp="2024-08-20")

    assert provider.source_name == "IMD historical rainfall"
    assert rainfall.attrs["units"] == "mm"
    assert rainfall.attrs["provider"] == provider.source_name
    assert rainfall.ndim == 2


def test_coefficient_lookup_and_water_class_are_configured():
    assert 0 < coefficient_for_class(50) <= 1
    assert coefficient_for_class(80) == 0


def test_runoff_equation_and_volume_conversion():
    depth = runoff_depth_mm(np.array([10.0, 20.0]), np.array([0.5, 0.25]))
    volume = runoff_volume_m3(depth, 100.0)

    np.testing.assert_allclose(depth, [5.0, 5.0])
    np.testing.assert_allclose(volume, [0.5, 0.5])


def test_real_runoff_outputs_are_aligned_and_keep_nodata():
    metadata = run_runoff_model(timestamp="2024-08-20")

    assert metadata["status"] == "ready"
    assert metadata["raster_dimensions"] == {"height": 1018, "width": 1333}
    assert metadata["rainfall_source_resolution_degrees"] == [0.25, 0.25]
    assert metadata["statistics"]["valid_cell_count"] > 0
    assert metadata["statistics"]["total_runoff_volume_m3"] > 0

    with rasterio.open(metadata["output_availability"]["runoff_depth_mm"]) as depth, rasterio.open(
        metadata["output_availability"]["runoff_volume_m3"]
    ) as volume:
        assert depth.crs == volume.crs
        assert depth.transform == volume.transform
        assert (depth.width, depth.height) == (volume.width, volume.height)
        assert depth.nodata == -9999.0
        assert volume.nodata == -9999.0
        values = depth.read(1)
        assert np.any(values == depth.nodata)
        assert np.any(values >= 0)


def test_water_body_class_is_zero_runoff_assumption():
    assert runoff_depth_mm(np.array([40.0]), coefficient_for_class(80))[0] == 0


def test_runoff_api_status_and_summary(tmp_path, monkeypatch):
    depth_path = tmp_path / "runoff_depth_mm.tif"
    volume_path = tmp_path / "runoff_volume_m3.tif"
    metadata_path = tmp_path / "runoff_metadata.json"
    coefficient_path = tmp_path / "runoff_coefficients.json"
    for path in (depth_path, volume_path, coefficient_path):
        path.write_text("output", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "rainfall_provider": "IMDRainfallProvider",
                "rainfall_timestamp": "2024-08-20T00:00:00",
                "rainfall_scenario": "test",
                "coefficient_configuration_status": "prototype_assumption",
                "crs": "EPSG:32644",
                "raster_dimensions": {"height": 2, "width": 3},
                "raster_resolution_m": [30.0, 30.0],
                "warnings": [],
                "prototype_assumptions": [],
                "output_availability": {
                    "runoff_depth_mm": str(depth_path),
                    "runoff_volume_m3": str(volume_path),
                    "metadata": str(metadata_path),
                },
                "statistics": {
                    "minimum_runoff_depth_mm": 0.0,
                    "maximum_runoff_depth_mm": 10.0,
                    "mean_runoff_depth_mm": 5.0,
                    "total_runoff_volume_m3": 20.0,
                    "valid_cell_count": 6,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "RUNOFF_DEPTH_RASTER", depth_path)
    monkeypatch.setattr(main, "RUNOFF_VOLUME_RASTER", volume_path)
    monkeypatch.setattr(main, "RUNOFF_METADATA", metadata_path)
    monkeypatch.setattr(main, "RUNOFF_COEFFICIENTS_PATH", coefficient_path)

    status = main.runoff_status()
    summary = main.runoff_summary()

    assert status["model_status"] == "ready"
    assert status["raster_dimensions"] == {"height": 2, "width": 3}
    assert summary["total_runoff_volume_m3"] == 20.0
    assert summary["valid_cell_count"] == 6