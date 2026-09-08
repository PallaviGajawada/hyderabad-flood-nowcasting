"""Cached, transparent flood-aware routing over the Hyderabad OSM graph."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np

from ..config import (
    FORECAST_ASSUMPTIONS_PATH,
    ROAD_FLOOD_RISK_GEOJSON,
    ROADS_GRAPHML,
    ROUTING_ASSUMPTIONS_PATH,
)
from ..models.forecast_model import forecast_factor, load_forecast_assumptions


def load_routing_assumptions(
    path: Path = ROUTING_ASSUMPTIONS_PATH,
) -> dict[str, Any]:
    assumptions = json.loads(path.read_text(encoding="utf-8"))
    if assumptions.get("status") != "prototype_assumption":
        raise ValueError("Routing assumptions must be marked prototype_assumption.")
    if float(assumptions["safe_depth_cm"]) >= float(assumptions["caution_depth_cm"]):
        raise ValueError("Routing depth thresholds must be increasing.")
    return assumptions


def _osmid_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


@lru_cache(maxsize=1)
def _load_risk_by_osmid() -> dict[str, tuple[float, float, int]]:
    """Load the large road artifact once and retain only routing attributes."""
    if not ROAD_FLOOD_RISK_GEOJSON.exists():
        raise FileNotFoundError("Road flood-risk GeoJSON is not available.")
    frame = gpd.read_file(ROAD_FLOOD_RISK_GEOJSON)
    risk_by_osmid: dict[str, tuple[float, float, int]] = {}
    for row in frame.itertuples(index=False):
        properties = row._asdict()
        osmids = _osmid_values(properties.get("osmid"))
        values = (
            float(properties.get("prototype_max_depth_cm") or 0),
            float(properties.get("prototype_mean_depth_cm") or 0),
            int(properties.get("prototype_max_risk_class") or 0),
        )
        for osmid in osmids:
            previous = risk_by_osmid.get(osmid)
            if previous is None or (values[0], values[2]) > (previous[0], previous[2]):
                risk_by_osmid[osmid] = values
    return risk_by_osmid


@lru_cache(maxsize=1)
def _load_graph() -> nx.MultiDiGraph:
    if not ROADS_GRAPHML.exists():
        raise FileNotFoundError("Hyderabad drive graph is not available.")
    graph = nx.read_graphml(ROADS_GRAPHML)
    if not isinstance(graph, nx.MultiDiGraph):
        graph = nx.MultiDiGraph(graph)
    return graph


@lru_cache(maxsize=1)
def _load_base_graph() -> nx.DiGraph:
    """Collapse parallel OSM edges to the shortest normal edge for routing."""
    source = _load_graph()
    risk_by_osmid = _load_risk_by_osmid()
    base = nx.DiGraph()
    for node, data in source.nodes(data=True):
        base.add_node(node, x=float(data["x"]), y=float(data["y"]))
    for u, v, data in source.edges(data=True):
        length = max(float(data.get("length", 1.0)), 0.1)
        depth, mean_depth, risk_class = _risk_for_edge(data, risk_by_osmid)
        candidate = {
            **data,
            "length": length,
            "flood_depth_cm": depth,
            "flood_mean_depth_cm": mean_depth,
            "flood_risk_class": risk_class,
            "travel_time_min": _travel_time_minutes(data, length),
        }
        if not base.has_edge(u, v) or candidate["length"] < base[u][v]["length"]:
            base.add_edge(u, v, **candidate)
    return base


def _risk_for_edge(
    data: dict[str, Any], risk_by_osmid: dict[str, tuple[float, float, int]]
) -> tuple[float, float, int]:
    values = [risk_by_osmid[key] for key in _osmid_values(data.get("osmid")) if key in risk_by_osmid]
    if not values:
        return 0.0, 0.0, 0
    return max(value[0] for value in values), max(value[1] for value in values), max(value[2] for value in values)


def _travel_time_minutes(data: dict[str, Any], length_m: float) -> float:
    speed = data.get("maxspeed")
    numeric = None
    if isinstance(speed, (int, float)):
        numeric = float(speed)
    elif speed:
        try:
            numeric = float(str(speed).split(";")[0].split()[0])
        except (ValueError, IndexError):
            numeric = None
    speed_kmh = numeric if numeric and numeric > 0 else 30.0
    return length_m / (speed_kmh * 1000 / 60)


def _nearest_node(latitude: float, longitude: float) -> str:
    graph = _load_base_graph()
    best_node = None
    best_distance = float("inf")
    latitude_scale = 111_000
    longitude_scale = latitude_scale * math.cos(math.radians(latitude))
    for node, data in graph.nodes(data=True):
        distance = ((float(data["y"]) - latitude) * latitude_scale) ** 2 + (
            (float(data["x"]) - longitude) * longitude_scale
        ) ** 2
        if distance < best_distance:
            best_distance = distance
            best_node = node
    if best_node is None:
        raise ValueError("Road graph contains no nodes.")
    return str(best_node)


def _scaled_edge(edge: dict[str, Any], forecast_minutes: int) -> dict[str, Any]:
    factor = forecast_factor(
        forecast_minutes, load_forecast_assumptions()
    )
    depth = float(edge["flood_depth_cm"]) * factor
    risk = 0
    if depth > 0:
        if depth <= 5:
            risk = 1
        elif depth <= 15:
            risk = 2
        elif depth <= 30:
            risk = 3
        else:
            risk = 4
    return {**edge, "forecast_depth_cm": depth, "forecast_risk_class": risk}


@lru_cache(maxsize=8)
def _safe_graph(forecast_minutes: int) -> nx.DiGraph:
    assumptions = load_routing_assumptions()
    graph = nx.DiGraph()
    for node, data in _load_base_graph().nodes(data=True):
        graph.add_node(node, **data)
    max_depth = float(assumptions["maximum_allowed_depth_cm"])
    risk_penalties = {str(key): float(value) for key, value in assumptions["risk_class_penalties"].items()}
    caution_depth = float(assumptions["caution_depth_cm"])
    caution_penalty = float(assumptions["caution_penalty_per_cm"])
    for u, v, edge in _load_base_graph().edges(data=True):
        scaled = _scaled_edge(edge, forecast_minutes)
        depth = scaled["forecast_depth_cm"]
        if depth > max_depth:
            continue
        penalty = risk_penalties.get(str(scaled["forecast_risk_class"]), 1.0)
        if depth > caution_depth:
            penalty *= 1 + (depth - caution_depth) * caution_penalty
        graph.add_edge(
            u,
            v,
            **scaled,
            routing_cost=float(edge["travel_time_min"]) * penalty,
        )
    return graph


def _route_metrics(graph: nx.DiGraph, path: list[str], forecast_minutes: int) -> dict[str, Any]:
    edges = [graph[u][v] for u, v in zip(path, path[1:])]
    scaled_edges = [_scaled_edge(edge, forecast_minutes) for edge in edges]
    depths = [edge["forecast_depth_cm"] for edge in scaled_edges] or [0.0]
    risks = [edge["forecast_risk_class"] for edge in scaled_edges] or [0]
    distance = float(sum(float(edge["length"]) for edge in edges))
    time = float(sum(float(edge["travel_time_min"]) for edge in edges))
    max_depth = max(depths)
    if max_depth <= 5:
        safety = "SAFE"
    elif max_depth <= 15:
        safety = "CAUTION"
    else:
        safety = "DANGEROUS"
    return {
        "node_sequence": [str(node) for node in path],
        "route": [
            {"lat": float(graph.nodes[node]["y"]), "lon": float(graph.nodes[node]["x"])}
            for node in path
        ],
        "distance_m": distance,
        "estimated_time_min": time,
        "max_flood_depth_cm": float(max_depth),
        "mean_flood_depth_cm": float(np.mean(depths)),
        "max_risk_class": int(max(risks)),
        "safety": safety,
    }


def calculate_safe_route(
    *,
    source_lat: float,
    source_lon: float,
    destination_lat: float,
    destination_lon: float,
    forecast_minutes: int,
) -> dict[str, Any]:
    if forecast_minutes not in load_forecast_assumptions()["forecast_horizons_minutes"]:
        raise ValueError("forecast_minutes must be one of 0, 30, 60, 90, 120, 150, or 180.")
    base = _load_base_graph()
    safe = _safe_graph(forecast_minutes)
    source_node = _nearest_node(source_lat, source_lon)
    destination_node = _nearest_node(destination_lat, destination_lon)
    try:
        normal_path = nx.shortest_path(base, source_node, destination_node, weight="length")
    except nx.NetworkXNoPath as error:
        raise ValueError("No normal route connects the requested points.") from error
    try:
        safe_path = nx.shortest_path(safe, source_node, destination_node, weight="routing_cost")
    except nx.NetworkXNoPath as error:
        raise ValueError("No flood-aware route connects the requested points.") from error

    normal_metrics = _route_metrics(base, normal_path, forecast_minutes)
    safe_metrics = _route_metrics(safe, safe_path, forecast_minutes)
    return {
        "status": "ready",
        "source": {"lat": source_lat, "lon": source_lon, "node": source_node},
        "destination": {
            "lat": destination_lat,
            "lon": destination_lon,
            "node": destination_node,
        },
        "forecast_minutes": forecast_minutes,
        "route": safe_metrics["route"],
        "distance_m": safe_metrics["distance_m"],
        "estimated_time_min": safe_metrics["estimated_time_min"],
        "max_flood_depth_cm": safe_metrics["max_flood_depth_cm"],
        "mean_flood_depth_cm": safe_metrics["mean_flood_depth_cm"],
        "max_risk_class": safe_metrics["max_risk_class"],
        "safety": safe_metrics["safety"],
        "flood_avoided": safe_metrics["distance_m"] != normal_metrics["distance_m"]
        or safe_metrics["max_flood_depth_cm"] < normal_metrics["max_flood_depth_cm"],
        "normal_route": normal_metrics,
        "flood_safe_route": safe_metrics,
        "assumptions": load_routing_assumptions(),
        "warnings": [
            "Routes use OSM road geometry and prototype sampled flood-risk penalties.",
            "This is not emergency navigation or a guarantee that a road is passable.",
        ],
    }