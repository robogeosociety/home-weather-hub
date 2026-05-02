"""End-to-end test — spawn the tempest-listener CLI as a subprocess."""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def _wait_for(predicate, timeout: float, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_listener_cli_captures_packet_and_shuts_down_cleanly(
    free_udp_port: int, tmp_path: Path
) -> None:
    log_path = tmp_path / "listener.log"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "home_weather_hub.tempest_listener",
            "--port",
            str(free_udp_port),
            "--data-dir",
            str(tmp_path),
            "--flush-interval",
            "0.2",
        ],
        stdout=log_path.open("wb"),
        stderr=subprocess.STDOUT,
    )

    try:
        # Wait for the listener to bind before sending anything.
        if not _wait_for(lambda: "listening" in log_path.read_text(), timeout=5.0):
            pytest.fail(f"listener never logged 'listening':\n{log_path.read_text()}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(b'{"type":"obs_st","serial_number":"ST-E2E"}', ("127.0.0.1", free_udp_port))
        finally:
            sock.close()

        target = tmp_path / f"tempest-{datetime.now(UTC).date().isoformat()}.jsonl"
        if not _wait_for(lambda: target.exists() and target.stat().st_size > 0, timeout=3.0):
            pytest.fail(f"no JSONL written; log:\n{log_path.read_text()}")
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
            pytest.fail("listener did not exit within 5s of SIGINT")

    assert proc.returncode == 0, f"non-zero exit; log:\n{log_path.read_text()}"
    assert "shutting down" in log_path.read_text()

    # Every line of the JSONL is valid JSON and matches the envelope schema.
    lines = target.read_text().splitlines()
    assert lines, "expected at least one record"
    for line in lines:
        rec = json.loads(line)
        assert set(rec.keys()) == {"received_at", "src_addr", "payload"}
    assert any(json.loads(line)["payload"].get("serial_number") == "ST-E2E" for line in lines)
