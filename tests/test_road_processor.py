"""Tests for OSMnx road preprocessing and the road status API."""

import json
from pathlib import Path

import networkx as nx
from shapely.geometry import LineString

from backend import main
from backend.preprocessing import road_processor


def _fake_drive_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=78.30, y=17.40)
    graph.add_node(2, x=78.31, y=17.41)
    graph.add_edge(
        1,
        2,
        key=0,
        geometry=LineString([(78.30, 17.40), (78.31, 17.41)]),
        name="Test Road",
        highway="residential",
        oneway=False,
    )
    return graph


def test_process_roads_writes_requested_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        road_processor.ox,
        "graph_from_polygon",
        lambda *args, **kwargs: _fake_drive_graph(),
    )

    metadata = road_processor.process_roads(
        geojson_path=tmp_path / "hyderabad_roads.geojson",
        graphml_path=tmp_path / "hyderabad_drive.graphml",
        metadata_path=tmp_path / "road_network_metadata.json",
    )

    assert metadata["status"] == "ready"
    assert metadata["network_type"] == "drive"
    assert metadata["number_nodes"] == 2
    assert metadata["number_edges"] == 1
    assert metadata["important_osm_tags_preserved"]
    assert (tmp_path / "hyderabad_roads.geojson").exists()
    assert (tmp_path / "hyderabad_drive.graphml").exists()
    assert (tmp_path / "road_network_metadata.json").exists()


def test_roads_status_reports_ready_outputs(tmp_path, monkeypatch):
    output_paths = {
        "geojson": tmp_path / "roads.geojson",
        "graphml": tmp_path / "roads.graphml",
        "metadata": tmp_path / "metadata.json",
    }
    for path in output_paths.values():
        path.write_text("output", encoding="utf-8")
    output_paths["metadata"].write_text(
        json.dumps(
            {
                "status": "ready",
                "number_nodes": 2,
                "number_edges": 1,
                "output_paths": {key: str(path) for key, path in output_paths.items()},
                "overpass_errors": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "ROADS_GEOJSON", output_paths["geojson"])
    monkeypatch.setattr(main, "ROADS_GRAPHML", output_paths["graphml"])
    monkeypatch.setattr(main, "ROADS_METADATA", output_paths["metadata"])

    result = main.roads_status()

    assert result["ready"] is True
    assert result["status"] == "ready"
    assert result["number_nodes"] == 2
    assert result["number_edges"] == 1