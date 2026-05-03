"""Unit tests for the MQTT-side routing logic in `MessageRouter`.

These never touch a real broker; they invoke `router.handle()` directly
with synthetic topic + payload pairs and assert what landed in the JSONL
writer and the SQLite aggregator.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_weather_hub.storage import Aggregator, open_db
from home_weather_hub.zigbee_subscriber import (
    DEFAULT_BASE_TOPIC,
    JsonlWriter,
    MessageRouter,
    _StationOverride,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def writer(tmp_path: Path) -> JsonlWriter:
    return JsonlWriter(tmp_path)


@pytest.fixture
def agg() -> Aggregator:
    return Aggregator(open_db(":memory:"))


@pytest.fixture
def fixed_clock() -> float:
    # 2026-05-02 18:30:00 UTC. Matches the `last_seen` value in
    # test_last_seen_drives_observation_ts so receive-time ≠ device-time
    # tests stay deterministic.
    return float(int(datetime(2026, 5, 2, 18, 30, tzinfo=UTC).timestamp()))


def _bridge_devices_payload() -> bytes:
    return json.dumps(
        [
            {
                "type": "Coordinator",
                "ieee_address": "0x00124b0000000000",
                "friendly_name": "Coordinator",
            },
            {
                "type": "EndDevice",
                "ieee_address": "0xa4c138aabbccdd",
                "friendly_name": "living_room",
            },
        ]
    ).encode()


def _device_payload(**fields: object) -> bytes:
    return json.dumps(fields).encode()


def test_per_device_message_after_catalog_writes_jsonl_and_aggregate(
    tmp_path: Path,
    writer: JsonlWriter,
    agg: Aggregator,
    fixed_clock: float,
) -> None:
    router = MessageRouter(writer, agg, time_source=lambda: fixed_clock)
    router.handle(f"{DEFAULT_BASE_TOPIC}/bridge/devices", _bridge_devices_payload())
    router.handle(
        f"{DEFAULT_BASE_TOPIC}/living_room",
        _device_payload(temperature=22.4, humidity=45.2, battery=96, voltage=3000),
    )
    writer.flush()

    jsonl_path = next(tmp_path.glob("zigbee-*.jsonl"))
    line = jsonl_path.read_text().strip()
    record = json.loads(line)
    assert record["sensor_id"] == "snzb:0xa4c138aabbccdd"
    assert record["friendly_name"] == "living_room"
    assert record["payload"]["temperature"] == 22.4

    rows = agg._conn.execute("SELECT metric, value FROM observations ORDER BY metric").fetchall()
    by_metric = {r["metric"]: r["value"] for r in rows}
    assert by_metric == {
        "air_temp_c": 22.4,
        "battery_pct": 96.0,
        "battery_v": 3.0,
        "humidity_pct": 45.2,
    }


def test_message_before_catalog_falls_back_to_friendly_name_id(
    tmp_path: Path,
    writer: JsonlWriter,
    agg: Aggregator,
    fixed_clock: float,
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = MessageRouter(writer, agg, time_source=lambda: fixed_clock)
    with caplog.at_level("WARNING"):
        router.handle(
            f"{DEFAULT_BASE_TOPIC}/living_room",
            _device_payload(temperature=20.0),
        )
    rows = agg._conn.execute("SELECT sensor_id, metric, value FROM observations").fetchall()
    assert len(rows) == 1
    assert rows[0]["sensor_id"] == "znme:living_room"
    assert any("not yet in Z2M catalog" in m for m in caplog.messages)


def test_unknown_device_warning_only_fires_once(
    writer: JsonlWriter,
    fixed_clock: float,
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = MessageRouter(writer, None, time_source=lambda: fixed_clock)
    with caplog.at_level("WARNING"):
        for _ in range(3):
            router.handle(
                f"{DEFAULT_BASE_TOPIC}/living_room",
                _device_payload(temperature=20.0),
            )
    catalog_warnings = [m for m in caplog.messages if "not yet in Z2M catalog" in m]
    assert len(catalog_warnings) == 1


def test_bridge_topics_other_than_devices_are_ignored(
    writer: JsonlWriter,
    agg: Aggregator,
) -> None:
    router = MessageRouter(writer, agg)
    router.handle(f"{DEFAULT_BASE_TOPIC}/bridge/state", _device_payload(state="online"))
    router.handle(f"{DEFAULT_BASE_TOPIC}/bridge/info", _device_payload(version="2.0.0"))
    writer.flush()
    assert list(Path(writer._data_dir).glob("zigbee-*.jsonl")) == []
    n_obs = agg._conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert n_obs == 0


def test_subtopics_like_availability_are_ignored(
    writer: JsonlWriter,
    agg: Aggregator,
) -> None:
    router = MessageRouter(writer, agg)
    router.handle(f"{DEFAULT_BASE_TOPIC}/bridge/devices", _bridge_devices_payload())
    router.handle(
        f"{DEFAULT_BASE_TOPIC}/living_room/availability",
        _device_payload(state="online"),
    )
    n_obs = agg._conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert n_obs == 0


def test_malformed_json_does_not_raise(
    writer: JsonlWriter,
    agg: Aggregator,
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = MessageRouter(writer, agg)
    with caplog.at_level("WARNING"):
        router.handle(f"{DEFAULT_BASE_TOPIC}/living_room", b"this is not json")
    assert any("malformed JSON" in m for m in caplog.messages)
    n_obs = agg._conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert n_obs == 0


def test_station_override_drives_kind_and_location(
    writer: JsonlWriter,
    agg: Aggregator,
    fixed_clock: float,
) -> None:
    overrides = {
        "snzb:0xa4c138aabbccdd": _StationOverride(kind="snzb-02wd", location="living_room"),
    }
    router = MessageRouter(
        writer,
        agg,
        time_source=lambda: fixed_clock,
        stations_by_sensor_id=overrides,
    )
    router.handle(f"{DEFAULT_BASE_TOPIC}/bridge/devices", _bridge_devices_payload())
    router.handle(f"{DEFAULT_BASE_TOPIC}/living_room", _device_payload(temperature=21.5))

    sensor = agg._conn.execute("SELECT kind, location FROM sensors").fetchone()
    assert sensor["kind"] == "snzb-02wd"
    assert sensor["location"] == "living_room"


def test_last_seen_drives_observation_ts(
    writer: JsonlWriter,
    agg: Aggregator,
    fixed_clock: float,
) -> None:
    """When the device payload includes `last_seen`, it should be used as the
    canonical timestamp instead of wall-clock receive time. That keeps day/
    month buckets aligned with the device's view of the world."""
    router = MessageRouter(writer, agg, time_source=lambda: fixed_clock)
    router.handle(f"{DEFAULT_BASE_TOPIC}/bridge/devices", _bridge_devices_payload())
    router.handle(
        f"{DEFAULT_BASE_TOPIC}/living_room",
        _device_payload(temperature=21.5, last_seen="2026-05-02T18:30:00Z"),
    )
    ts = agg._conn.execute("SELECT ts FROM observations").fetchone()["ts"]
    assert ts == int(fixed_clock)


def test_unknown_topic_outside_base_is_ignored(
    writer: JsonlWriter,
    agg: Aggregator,
) -> None:
    router = MessageRouter(writer, agg)
    router.handle("homeassistant/sensor/foo/state", _device_payload(temperature=25.0))
    n_obs = agg._conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert n_obs == 0
