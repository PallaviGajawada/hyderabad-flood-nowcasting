"""Focused regression checks for the demo-ready web GIS layer service."""

from __future__ import annotations

from backend.main import app
from backend.map_layers import get_map_layers


def test_map_layers_are_lightweight_and_horizon_specific() -> None:
    result = get_map_layers(60)
    assert result["status"] == "ready"
    assert result["forecast_minutes"] == 60
    assert result["limits"]["roads_returned"] <= 3_000
    assert result["limits"]["flood_grid"] == "80x60"
    assert len(result["layers"]["roads"]["features"]) <= 3_000
    assert len(result["layers"]["road_risk"]["features"]) <= 3_000
    assert result["layers"]["flood"]["features"]
    assert all(
        feature["properties"]["horizon_minutes"] == 60
        for feature in result["layers"]["flood"]["features"][:10]
    )


def test_step8_map_endpoint_is_in_openapi_contract() -> None:
    assert "/api/map-layers" in app.openapi()["paths"]