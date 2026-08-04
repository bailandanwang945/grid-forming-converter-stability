from fastapi.testclient import TestClient

from backend.api.app import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_damping_changes_reference_stability() -> None:
    unstable = client.post("/api/analysis/run", json={"damping": 0.05, "scr": 3.0})
    stable = client.post("/api/analysis/run", json={"damping": 0.5, "scr": 3.0})
    assert unstable.json()["summary"]["closed_loop_reference"] == "unstable"
    assert stable.json()["summary"]["closed_loop_reference"] == "stable"
    assert unstable.json()["summary"]["uncovered_points"] > 0
