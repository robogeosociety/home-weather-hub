"""Integration tests for the FastAPI dashboard API.

Uses FastAPI's TestClient (which spins up the app in-process) and the WS
support in `httpx`/`starlette.testclient`. UDP binding is disabled so tests
don't need a free port or root.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from home_weather_hub.dashboard_api import create_app
from home_weather_hub.event_bus import EventBus
from home_weather_hub.tempest_decode import DecodedRapidWind

pytestmark = pytest.mark.integration


def _envelope(payload: dict) -> dict:
    return {
        "received_at": datetime.now(UTC).isoformat(),
        "src_addr": "192.168.4.20",
        "payload": payload,
    }


def _seed_obs_st(data_dir: Path) -> None:
    today = datetime.now(UTC).date()
    path = data_dir / f"tempest-{today.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    obs = [
        1700000000,
        1.0,
        3.2,
        5.0,
        90.0,
        3,
        1015.4,
        21.5,
        58.0,
        12000.0,
        4.2,
        450.0,
        0.5,
        1,
        0.0,
        0,
        2.78,
        1,
    ]
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_envelope({"type": "obs_st", "obs": [obs]})) + "\n")


def test_health_reports_config(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=EventBus())
    with TestClient(app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["data_dir"] == str(tmp_path)
        assert body["subscribers"] == 0


def test_snapshot_returns_latest_decoded_obs_st(tmp_path: Path) -> None:
    _seed_obs_st(tmp_path)
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=EventBus())
    with TestClient(app) as client:
        r = client.get("/api/snapshot")
        assert r.status_code == 200
        body = r.json()
        assert body["events"]["obs_st"]["air_temp_c"] == 21.5
        assert body["metrics"]["outdoor.air_temp_c"] == 21.5
        # Computed-field round-trip through the API.
        assert body["events"]["obs_st"]["air_temp_f"] == pytest.approx(70.7, abs=0.05)


def test_history_unknown_metric_returns_404(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=EventBus())
    with TestClient(app) as client:
        r = client.get("/api/history", params={"metric": "outdoor.nonexistent"})
        assert r.status_code == 404


def test_layout_round_trips_through_api(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=EventBus())
    with TestClient(app) as client:
        assert client.get("/api/layout").json() == {}
        r = client.put("/api/layout", json={"mac": [{"i": "temp", "x": 0, "y": 0, "w": 4, "h": 3}]})
        assert r.status_code == 200
        roundtrip = client.get("/api/layout").json()
        assert roundtrip == {"mac": [{"i": "temp", "x": 0, "y": 0, "w": 4, "h": 3}]}


def test_station_config_returns_metric_registry(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=EventBus())
    with TestClient(app) as client:
        body = client.get("/api/station").json()
        assert "outdoor.air_temp_f" in body["metric_keys"]
        assert "outdoor.wind_avg_mph" in body["metric_keys"]


def test_websocket_emits_initial_snapshot_then_live_events(tmp_path: Path) -> None:
    _seed_obs_st(tmp_path)
    bus = EventBus()
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=bus)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        initial = json.loads(ws.receive_text())
        assert initial["type"] == "snapshot"
        assert initial["data"]["metrics"]["outdoor.air_temp_c"] == 21.5
        # Now publish a live event and read it through the socket.
        bus.publish(
            DecodedRapidWind(time_epoch=1700000300, wind_speed_mps=4.5, wind_direction_deg=180)
        )
        live = json.loads(ws.receive_text())
        assert live["type"] == "event"
        assert live["data"]["wind_direction_deg"] == 180


def test_synthetic_strike_endpoint_publishes_to_bus(tmp_path: Path) -> None:
    bus = EventBus()
    app = create_app(data_dir=tmp_path, bind_udp=False, event_bus=bus)
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.receive_text()  # discard initial snapshot
        r = client.post("/api/_dev/strike", params={"distance_km": 7.5})
        assert r.status_code == 200
        assert r.json()["distance_km"] == 7.5
        event = json.loads(ws.receive_text())
        assert event["type"] == "event"
        assert event["data"]["type"] == "evt_strike"
        assert event["data"]["distance_km"] == 7.5
