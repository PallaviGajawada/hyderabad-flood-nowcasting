"""Integration coverage for the real-data GIS preprocessing stages."""

import pytest

from backend.preprocessing.preprocessing_pipeline import run_preprocessing_pipeline


@pytest.fixture(scope="module")
def preprocessing_report(tmp_path_factory):
    report_path = tmp_path_factory.mktemp("preprocessing") / "report.json"
    return run_preprocessing_pipeline(report_path=report_path)


@pytest.mark.parametrize(
    "dataset_key",
    [
        "hyderabad_dem",
        "hyderabad_landcover",
        "imd_rainfall_2024",
        "ghmc_nalas",
        "hyderabad_stream_network",
        "hyderabad_tanks",
    ],
)
def test_real_dataset_preprocessing_stage_is_reported(preprocessing_report, dataset_key):
    stages = {item["dataset_key"]: item for item in preprocessing_report["datasets"]}

    assert preprocessing_report["status"] == "completed_with_warnings"
    assert dataset_key in stages
    assert stages[dataset_key]["errors"] == []
    assert stages[dataset_key]["output_dataset"]


def test_preprocessing_report_keeps_missing_inputs_explicit(preprocessing_report):
    assert preprocessing_report["inputs_not_processed"]["roads"].endswith(
        "hyderabad_roads.gpkg"
    )
    assert preprocessing_report["inputs_not_processed"]["historical_floods"].endswith(
        "hyderabad_flooding_locations.kml"
    )
    assert any("roads" in warning.lower() for warning in preprocessing_report["warnings"])
    assert any(
        "historical flood" in warning.lower()
        for warning in preprocessing_report["warnings"]
    )