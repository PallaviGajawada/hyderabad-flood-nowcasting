"""Focused checks for read-only dataset validation behavior."""

import json

from backend.preprocessing.data_validator import validate_all_datasets, validate_vector


def test_missing_vector_is_reported_without_a_fallback(tmp_path) -> None:
    result = validate_vector(tmp_path / "not-provided.geojson", dataset_key="missing")

    assert result["exists"] is False
    assert result["readable"] is False
    assert result["validation_status"] == "missing"
    assert result["errors"] == ["File does not exist."]


def test_validation_report_is_written_for_configured_specs(tmp_path, monkeypatch) -> None:
    import backend.preprocessing.data_validator as validator

    monkeypatch.setattr(
        validator,
        "DATASET_SPECS",
        {"missing": ("vector", tmp_path / "not-provided.geojson")},
    )
    report_path = tmp_path / "data_validation_report.json"

    report = validate_all_datasets(report_path=report_path)

    assert report["summary"]["missing"] == 1
    assert json.loads(report_path.read_text())["datasets"]["missing"]["validation_status"] == "missing"