"""Integration tests — real asyncio UDP endpoint, real socket sends, real file writes."""

from __future__ import annotations

import asyncio
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_weather_hub.tempest_listener import JsonlWriter, TempestProtocol

pytestmark = pytest.mark.integration


async def _bring_up_listener(port: int, data_dir: Path):
    writer = JsonlWriter(data_dir)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: TempestProtocol(writer),
        local_addr=("127.0.0.1", port),
        family=socket.AF_INET,
        allow_broadcast=True,
    )
    return transport, writer


def _send_udp(payload: bytes, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload, ("127.0.0.1", port))
    finally:
        sock.close()


async def test_listener_writes_received_packet_to_jsonl(free_udp_port: int, tmp_path: Path) -> None:
    transport, writer = await _bring_up_listener(free_udp_port, tmp_path)
    try:
        _send_udp(b'{"type":"hub_status","serial_number":"HB-INT"}', free_udp_port)
        today = datetime.now(UTC).date().isoformat()
        target = tmp_path / f"tempest-{today}.jsonl"
        # Datagram delivery on loopback is fast; flush each tick and check.
        for _ in range(50):
            await asyncio.sleep(0.01)
            writer.flush()
            if target.exists() and target.stat().st_size > 0:
                break
        else:
            pytest.fail("packet never landed in JSONL within ~500ms")
    finally:
        transport.close()
        writer.close()

    line = target.read_text().splitlines()[-1]
    record = json.loads(line)
    assert record["payload"] == {"type": "hub_status", "serial_number": "HB-INT"}
    assert record["src_addr"] == "127.0.0.1"


async def test_listener_survives_mix_of_good_and_bad_packets(
    free_udp_port: int, tmp_path: Path
) -> None:
    transport, writer = await _bring_up_listener(free_udp_port, tmp_path)
    try:
        _send_udp(b"not json", free_udp_port)
        _send_udp(b'{"type":"obs_st","obs":[[1,2,3]]}', free_udp_port)
        _send_udp(b"\x00\x01\x02 garbage", free_udp_port)
        _send_udp(b'{"type":"rapid_wind","ob":[1,2,3]}', free_udp_port)

        target = tmp_path / f"tempest-{datetime.now(UTC).date().isoformat()}.jsonl"
        for _ in range(50):
            await asyncio.sleep(0.01)
            writer.flush()
            if target.exists() and len(target.read_text().splitlines()) >= 2:
                break
        else:
            pytest.fail("expected 2 valid records to land within ~500ms")
    finally:
        transport.close()
        writer.close()

    types = [json.loads(line)["payload"]["type"] for line in target.read_text().splitlines()]
    assert types == ["obs_st", "rapid_wind"]
