"""Unit tests for TempestProtocol — call datagram_received directly with a fake writer."""

from __future__ import annotations

import json
import logging

import pytest

from home_weather_hub.tempest_listener import TempestProtocol

pytestmark = pytest.mark.unit


class RecordingWriter:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.flushed = False
        self.closed = False

    def write(self, record: dict) -> None:
        self.records.append(record)

    def flush(self) -> None:
        self.flushed = True

    def close(self) -> None:
        self.closed = True


def test_well_formed_packet_is_wrapped_and_written() -> None:
    writer = RecordingWriter()
    proto = TempestProtocol(writer)  # type: ignore[arg-type]
    payload = {"type": "hub_status", "serial_number": "HB-1"}
    proto.datagram_received(json.dumps(payload).encode(), ("192.168.4.20", 50222))

    assert len(writer.records) == 1
    rec = writer.records[0]
    assert rec["payload"] == payload
    assert rec["src_addr"] == "192.168.4.20"
    assert isinstance(rec["received_at"], str)
    assert rec["received_at"].endswith("+00:00")  # UTC


def test_malformed_json_logs_warning_and_drops(caplog: pytest.LogCaptureFixture) -> None:
    writer = RecordingWriter()
    proto = TempestProtocol(writer)  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING, logger="tempest_listener"):
        proto.datagram_received(b"not json {{", ("127.0.0.1", 50222))

    assert writer.records == []
    assert any("dropping malformed packet" in r.message for r in caplog.records)
    assert any("hex:" in r.message for r in caplog.records)


def test_protocol_keeps_running_after_malformed_packet() -> None:
    writer = RecordingWriter()
    proto = TempestProtocol(writer)  # type: ignore[arg-type]
    proto.datagram_received(b"\xff\xfe garbage", ("127.0.0.1", 50222))
    proto.datagram_received(b'{"type":"obs_st","obs":[[1]]}', ("192.168.4.20", 50222))
    assert len(writer.records) == 1
    assert writer.records[0]["payload"]["type"] == "obs_st"


def test_record_envelope_keys() -> None:
    writer = RecordingWriter()
    proto = TempestProtocol(writer)  # type: ignore[arg-type]
    proto.datagram_received(b'{"type":"x"}', ("10.0.0.1", 50222))
    assert set(writer.records[0].keys()) == {"received_at", "src_addr", "payload"}
