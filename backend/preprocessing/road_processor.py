"""Download and preprocess the real GHMC drive network from OpenStreetMap."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import osmnx as ox

from ..config import (
    ROADS_GEOJSON,
    ROADS_GRAPHML,
    ROADS_METADATA,
    WEB_CRS,
)
from .spatial import boundary_geometry, read_boundary

IMPORTANT_OSM_TAGS = [
    "name",
    "highway",
    "oneway",
    "maxspeed",
    "lanes",
    "access",
    "bridge",
    "tunnel",
]


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _ensure_output_attributes(edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    result = edges.copy()
    for tag in IMPORTANT_OSM_TAGS:
        if tag not in result.columns:
            result[tag] = None
    return result


def _write_roads_geojson(edges: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = _ensure_output_attributes(edges)
    if output.crs != WEB_CRS:
        output = output.to_crs(WEB_CRS)
    output.to_file(path, driver="GeoJSON", index=False)


def _remove_non_graphml_attributes(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Keep the source graph intact while making a serializable GraphML copy."""

    serializable = graph.copy()
    for _, attributes in serializable.nodes(data=True):
        for key, value in list(attributes.items()):
            if value is None:
                del attributes[key]
    for _, _, _, attributes in serializable.edges(keys=True, data=True):
        for key, value in list(attributes.items()):
            if value is None:
                del attributes[key]
    return serializable


def _write_metadata(metadata: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata, indent=2, default=_json_safe) + "\n",
        encoding="utf-8",
    )


def _boundary_query_area(boundary) -> list[float]:
    min_x, min_y, max_x, max_y = boundary.bounds
    return [float(min_x), float(min_y), float(max_x), float(max_y)]


def process_roads(
    *,
    geojson_path: Path = ROADS_GEOJSON,
    graphml_path: Path = ROADS_GRAPHML,
    metadata_path: Path = ROADS_METADATA,
) -> dict[str, Any]:
    """Query, clean, and export the GHMC drivable road network.

    OSMnx handles Overpass request subdivision when the polygon exceeds its
    configured maximum query area. The boundary itself is always the query
    geometry; no Hyderabad-wide fallback query is used.
    """

    retrieval_timestamp = datetime.now(UTC).isoformat()
    boundary = read_boundary(target_crs=WEB_CRS)
    polygon = boundary_geometry(boundary)
    metadata: dict[str, Any] = {
        "source": "OpenStreetMap",
        "retrieval_method": "OSMnx/Overpass",
        "retrieval_timestamp": retrieval_timestamp,
        "crs": WEB_CRS,
        "bounding_box": _boundary_query_area(polygon),
        "network_type": "drive",
        "important_osm_tags_preserved": IMPORTANT_OSM_TAGS,
        "query_boundary": "supplied GHMC boundary",
        "simplified": True,
        "overpass_errors": [],
        "status": "not_ready",
        "output_paths": {
            "geojson": str(geojson_path),
            "graphml": str(graphml_path),
            "metadata": str(metadata_path),
        },
    }

    try:
        ox.settings.use_cache = True
        ox.settings.requests_timeout = 180
        graph = ox.graph_from_polygon(
            polygon,
            network_type="drive",
            simplify=True,
            retain_all=False,
            truncate_by_edge=False,
        )
        graph.remove_nodes_from(list(nx.isolates(graph)))
        nodes, edges = ox.graph_to_gdfs(
            graph,
            nodes=True,
            edges=True,
            fill_edge_geometry=True,
        )
        if nodes.crs is None:
            nodes = nodes.set_crs(WEB_CRS)
        if edges.crs is None:
            edges = edges.set_crs(WEB_CRS)
        edges = _ensure_output_attributes(edges)
        _write_roads_geojson(edges, geojson_path)
        graphml_graph = _remove_non_graphml_attributes(graph)
        graphml_path.parent.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(graphml_graph, filepath=graphml_path)

        metadata.update(
            {
                "status": "ready",
                "number_nodes": int(graph.number_of_nodes()),
                "number_edges": int(graph.number_of_edges()),
                "geometry_types": sorted(
                    str(value) for value in edges.geometry.dropna().geom_type.unique()
                ),
                "output_feature_count": int(len(edges)),
                "overpass_errors": [],
            }
        )
    except Exception as exc:
        metadata.update(
            {
                "status": "error",
                "number_nodes": 0,
                "number_edges": 0,
                "overpass_errors": [f"{type(exc).__name__}: {exc}"],
            }
        )
        _write_metadata(metadata, metadata_path)
        raise

    _write_metadata(metadata, metadata_path)
    return metadata