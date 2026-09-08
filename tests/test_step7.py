"""Focused regression tests for the deterministic Step 7 framework."""

from __future__ import annotations

import hashlib

import networkx as nx
import numpy as np
import rasterio

from backend.config import (
    DISPLAY_DEPTH_CM,
    FORECAST_OUTPUT_ROOT,
    FLOOD_RISK_CLASS_RASTER,
    ROADS_GRAPHML,
)
from backend.main import app, forecast_status, forecast_summary
from backend.models.forecast_model import forecast_factor, load_forecast_assumptions, run_forecast
from backend.routing.safe_route import (
    _load_base_graph,
    _safe_graph,
    calculate_safe_route,
)


def test_all_forecast_horizons_are_generated() -> None:
    status = forecast_status()
    assert status["status"] == "ready"
    assert status["forecast_horizons_minutes"] == [0, 30, 60, 90, 120, 150, 180]

    summary = forecast_summary()
    assert len(summary["horizons"]) == 7
    for minutes in status["forecast_horizons_minutes"]:
        horizon = FORECAST_OUTPUT_ROOT / f"tplus_{minutes:03d}"
        assert (horizon / "flood_depth_cm.tif").exists()
        assert (horizon / "flood_risk_class.tif").exists()
        assert (horizon / "forecast_summary.json").exists()


def test_forecast_rasters_preserve_step6_grid_and_finite_values() -> None:
    with rasterio.open(DISPLAY_DEPTH_CM) as baseline:
        baseline_array = baseline.read(1)
        baseline_valid = baseline_array != baseline.nodata
        for minutes in [0, 30, 60, 90, 120, 150, 180]:
            with rasterio.open(
                FORECAST_OUTPUT_ROOT / f"tplus_{minutes:03d}" / "flood_depth_cm.tif"
            ) as forecast:
                assert forecast.crs == baseline.crs
                assert forecast.transform == baseline.transform
                assert (forecast.height, forecast.width) == (baseline.height, baseline.width)
                values = forecast.read(1)
                assert np.isfinite(values[baseline_valid]).all()


def test_forecast_generation_is_deterministic() -> None:
    target = FORECAST_OUTPUT_ROOT / "tplus_060" / "flood_depth_cm.tif"
    with rasterio.open(target) as raster:
        first_hash = hashlib.sha256(raster.read(1).tobytes()).hexdigest()
    run_forecast()
    with rasterio.open(target) as raster:
        second_hash = hashlib.sha256(raster.read(1).tobytes()).hexdigest()
    assert first_hash == second_hash
    assumptions = load_forecast_assumptions()
    assert forecast_factor(60, assumptions) == forecast_factor(60, assumptions)


def test_routing_loads_graph_and_penalizes_flooded_edges() -> None:
    graph = _load_base_graph()
    assert graph.number_of_nodes() >= 138_000
    assert graph.number_of_edges() > 0
    safe_graph = _safe_graph(60)
    flooded = [
        edge
        for _, _, edge in safe_graph.edges(data=True)
        if edge["forecast_risk_class"] >= 2
    ]
    clear = [
        edge
        for _, _, edge in safe_graph.edges(data=True)
        if edge["forecast_risk_class"] == 0
    ]
    assert flooded and clear
    assert max(edge["routing_cost"] / edge["travel_time_min"] for edge in flooded) > 1
    assert all(
        edge["forecast_depth_cm"] <= 30
        for _, _, edge in safe_graph.edges(data=True)
    )


def test_safe_route_returns_comparison_fields_for_known_hyderabad_points() -> None:
    graph = nx.read_graphml(ROADS_GRAPHML)
    source = list(graph.nodes(data=True))[50_000][1]
    destination = list(graph.nodes(data=True))[90_000][1]
    result = calculate_safe_route(
        source_lat=float(source["y"]),
        source_lon=float(source["x"]),
        destination_lat=float(destination["y"]),
        destination_lon=float(destination["x"]),
        forecast_minutes=60,
    )
    assert result["status"] == "ready"
    assert result["route"]
    assert result["normal_route"]["node_sequence"]
    assert result["flood_safe_route"]["node_sequence"]
    assert {"distance_m", "estimated_time_min", "max_flood_depth_cm", "mean_flood_depth_cm", "max_risk_class", "safety"} <= result["normal_route"].keys()
    assert {"distance_m", "estimated_time_min", "max_flood_depth_cm", "mean_flood_depth_cm", "max_risk_class", "safety"} <= result["flood_safe_route"].keys()


def test_step7_api_paths_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/api/forecast-status",
        "/api/forecast-summary",
        "/api/safe-route",
    }.issubset(paths)