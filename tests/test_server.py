"""
Dashboard server tests. Skipped automatically if FastAPI is not installed.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from locksight.server.app import app  # noqa: E402


def test_dashboard_page_is_served():
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "LockSight" in res.text


def test_cytoscape_is_served_locally():
    with TestClient(app) as client:
        res = client.get("/static/vendor/cytoscape.min.js")
        assert res.status_code == 200


def test_options():
    with TestClient(app) as client:
        opts = client.get("/api/options").json()
        assert "bank" in opts["scenarios"]
        assert "weighted" in opts["policies"]


def test_invalid_scenario_rejected():
    with TestClient(app) as client:
        res = client.post("/api/run", json={"scenario": "nope"})
        assert res.status_code == 400


def test_run_streams_events_over_websocket():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            res = client.post("/api/run", json={"scenario": "pool",
                                                "detection": "on_block"})
            assert res.status_code == 200

            types, aborts = [], 0
            for _ in range(2000):              # safety bound, never hangs
                msg = ws.receive_json()
                types.append(msg["type"])
                if msg["type"] == "event":
                    assert "graph" in msg      # every event carries a snapshot
                    if msg["event"]["type"] == "abort":
                        aborts += 1
                if msg["type"] in ("run_complete", "run_error"):
                    break

            assert types[0] == "run_start"
            assert types[-1] == "run_complete"
            assert msg["result"]["completed"] == msg["result"]["tasks"]
            assert aborts == msg["result"]["aborts"]
