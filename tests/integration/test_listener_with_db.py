"""Integration test — listener writes obs_st packets through to JSONL + SQLite."""

from __future__ import annotations

import asyncio
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_weather_hub.storage import Aggregator, open_db
from home_weather_hub.tempest_listener import JsonlWriter, TempestProtocol

pytestmark = pytest.mark.integration


def _send_udp(payload: bytes, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload, ("127.0.0.1", port))
    finally:
        sock.close()


def _make_obs_st(serial: str, ts: int, temp_c: float) -> bytes:
    """Minimal valid obs_st packet — only fills the slots we assert on."""
    obs = [
        ts,
        0.5,
        2.0,
        4.5,
        180.0,
        3,
        1015.2,
        temp_c,
        62.0,
        12345,
        3.4,
        450,
        0.05,
        7.2,
        0,
        2,
        2.78,
        60,
    ]
    return json.dumps({"type": "obs_st", "serial_number": serial, "obs": [obs]}).encode()


async def test_listener_writes_obs_st_to_db_and_jsonl(free_udp_port: int, tmp_path: Path) -> None:
    db_path = tmp_path / "weather.db"
    conn = open_db(db_path)
    aggregator = Aggregator(conn)
    writer = JsonlWriter(tmp_path)

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: TempestProtocol(writer, aggregator=aggregator, dedupe_window_sec=0.0),
        local_addr=("127.0.0.1", free_udp_port),
        family=socket.AF_INET,
        allow_broadcast=True,
    )

    try:
        ts = int(datetime(2026, 5, 2, 12, tzinfo=UTC).timestamp())
        _send_udp(_make_obs_st("ST-INT", ts, 18.5), free_udp_port)
        _send_udp(_make_obs_st("ST-INT", ts + 60, 22.0), free_udp_port)

        # Wait for both to land.
        for _ in range(80):
            await asyncio.sleep(0.01)
            writer.flush()
            n = conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
            if n >= 28:  # 14 metrics * 2 packets
                break
        else:
            pytest.fail("observations did not reach the DB within ~800ms")
    finally:
        transport.close()
        writer.close()
        aggregator.close()

    # JSONL still written.
    today = datetime.now(UTC).date().isoformat()
    jsonl_path = tmp_path / f"tempest-{today}.jsonl"
    lines = jsonl_path.read_text().splitlines()
    assert len(lines) == 2

    # Re-open db (was closed via aggregator.close())
    conn2 = open_db(db_path)
    try:
        temp_row = conn2.execute(
            "SELECT min_value, max_value, count FROM monthly_aggregates WHERE metric = 'air_temp_c'"
        ).fetchone()
        assert temp_row["min_value"] == 18.5
        assert temp_row["max_value"] == 22.0
        assert temp_row["count"] == 2

        sensor_row = conn2.execute("SELECT sensor_id, kind FROM sensors").fetchone()
        assert sensor_row["sensor_id"] == "tempest:ST-INT"
        assert sensor_row["kind"] == "tempest"

        daily_count = conn2.execute(
            "SELECT COUNT(*) AS n FROM daily_aggregates WHERE metric='air_temp_c'"
        ).fetchone()["n"]
        assert daily_count == 1  # both samples land in the same UTC day
    finally:
        conn2.close()


async def test_listener_with_no_aggregator_still_writes_jsonl(
    free_udp_port: int, tmp_path: Path
) -> None:
    """Smoke test the --no-db code path: JSONL works without an aggregator."""
    writer = JsonlWriter(tmp_path)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: TempestProtocol(writer, aggregator=None, dedupe_window_sec=0.0),
        local_addr=("127.0.0.1", free_udp_port),
        family=socket.AF_INET,
        allow_broadcast=True,
    )
    try:
        _send_udp(_make_obs_st("ST-NO-DB", 1_700_000_000, 19.0), free_udp_port)
        today = datetime.now(UTC).date().isoformat()
        target = tmp_path / f"tempest-{today}.jsonl"
        for _ in range(50):
            await asyncio.sleep(0.01)
            writer.flush()
            if target.exists() and target.stat().st_size > 0:
                break
        else:
            pytest.fail("packet never landed in JSONL")
    finally:
        transport.close()
        writer.close()

    assert not (tmp_path / "weather.db").exists()
