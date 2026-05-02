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


def test_dedupe_drops_identical_bytes_within_window() -> None:
    """Multiple interfaces on the same broadcast domain deliver the same packet
    twice; the second copy should be dropped."""
    fake_clock = [1000.0]
    writer = RecordingWriter()
    proto = TempestProtocol(
        writer,  # type: ignore[arg-type]
        dedupe_window_sec=2.0,
        time_source=lambda: fake_clock[0],
    )
    pkt = b'{"type":"hub_status","seq":42}'
    proto.datagram_received(pkt, ("192.168.5.232", 50222))
    fake_clock[0] += 0.001  # microseconds later, second interface delivers
    proto.datagram_received(pkt, ("192.168.5.233", 50222))
    assert len(writer.records) == 1
    assert writer.records[0]["payload"] == {"type": "hub_status", "seq": 42}


def test_dedupe_allows_identical_bytes_after_window_expires() -> None:
    fake_clock = [1000.0]
    writer = RecordingWriter()
    proto = TempestProtocol(
        writer,  # type: ignore[arg-type]
        dedupe_window_sec=2.0,
        time_source=lambda: fake_clock[0],
    )
    pkt = b'{"type":"rapid_wind","ob":[1,2,3]}'
    proto.datagram_received(pkt, ("192.168.5.232", 50222))
    fake_clock[0] += 2.5  # well past the window
    proto.datagram_received(pkt, ("192.168.5.232", 50222))
    assert len(writer.records) == 2


def test_dedupe_does_not_collapse_distinct_payloads() -> None:
    """Real distinct observations differ byte-for-byte and must not be deduped."""
    fake_clock = [1000.0]
    writer = RecordingWriter()
    proto = TempestProtocol(
        writer,  # type: ignore[arg-type]
        dedupe_window_sec=2.0,
        time_source=lambda: fake_clock[0],
    )
    proto.datagram_received(b'{"type":"hub_status","seq":1}', ("192.168.5.232", 50222))
    fake_clock[0] += 0.5
    proto.datagram_received(b'{"type":"hub_status","seq":2}', ("192.168.5.232", 50222))
    fake_clock[0] += 0.5
    proto.datagram_received(b'{"type":"hub_status","seq":3}', ("192.168.5.232", 50222))
    assert len(writer.records) == 3
    assert [r["payload"]["seq"] for r in writer.records] == [1, 2, 3]


def test_dedupe_disabled_when_window_is_zero() -> None:
    writer = RecordingWriter()
    proto = TempestProtocol(writer, dedupe_window_sec=0.0)  # type: ignore[arg-type]
    pkt = b'{"type":"hub_status"}'
    proto.datagram_received(pkt, ("192.168.5.232", 50222))
    proto.datagram_received(pkt, ("192.168.5.233", 50222))
    assert len(writer.records) == 2


def test_dedupe_cache_prunes_expired_entries() -> None:
    """Cache must shed stale entries so it doesn't grow unbounded."""
    fake_clock = [1000.0]
    writer = RecordingWriter()
    proto = TempestProtocol(
        writer,  # type: ignore[arg-type]
        dedupe_window_sec=1.0,
        time_source=lambda: fake_clock[0],
    )
    for i in range(5):
        proto.datagram_received(f'{{"i":{i}}}'.encode(), ("192.168.5.232", 50222))
        fake_clock[0] += 0.1
    assert len(proto._recent) == 5  # type: ignore[attr-defined]

    fake_clock[0] += 5.0  # blow past the window for everything
    proto.datagram_received(b'{"trigger":"prune"}', ("192.168.5.232", 50222))
    # After the next insert, all 5 prior entries should have been pruned;
    # only the freshly inserted one remains.
    assert len(proto._recent) == 1  # type: ignore[attr-defined]
