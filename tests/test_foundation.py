"""Small smoke tests for the initial backend contract."""

from backend.main import app, system_status


def test_system_status_contract() -> None:
    assert system_status() == {
        "system": "Hyderabad Urban Flood Nowcasting System",
        "status": "initial prototype",
        "forecast_horizon_hours": 3,
    }


def test_expected_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/",
        "/health",
        "/forecast",
        "/flood-depth",
        "/safe-route",
        "/data-status",
    }.issubset(paths)
    assert {
        "/api/",
        "/api/health",
        "/api/forecast",
        "/api/data-status",
        "/api/preprocessing-status",
        "/api/roads-status",
        "/api/runoff-status",
        "/api/runoff-summary",
        "/api/surface-water-status",
        "/api/surface-water-summary",
    }.issubset(paths)