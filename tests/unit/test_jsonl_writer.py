"""Unit tests for JsonlWriter — no sockets, just tmp_path file I/O."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from home_weather_hub import tempest_listener as tl
from home_weather_hub.tempest_listener import JsonlWriter

pytestmark = pytest.mark.unit


def test_writes_record_to_dated_file(tmp_path: Path) -> None:
    writer = JsonlWriter(tmp_path)
    try:
        writer.write({"hello": "world"})
        writer.flush()
    finally:
        writer.close()

    today = datetime.now(UTC).date().isoformat()
    target = tmp_path / f"tempest-{today}.jsonl"
    assert target.exists()
    line = target.read_text().strip()
    assert json.loads(line) == {"hello": "world"}


def test_creates_data_dir_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "does" / "not" / "exist"
    writer = JsonlWriter(nested)
    try:
        writer.write({"x": 1})
    finally:
        writer.close()
    assert nested.is_dir()
    assert any(nested.glob("tempest-*.jsonl"))


def test_appends_multiple_records_one_per_line(tmp_path: Path) -> None:
    writer = JsonlWriter(tmp_path)
    try:
        for i in range(5):
            writer.write({"i": i})
    finally:
        writer.close()

    today = datetime.now(UTC).date().isoformat()
    lines = (tmp_path / f"tempest-{today}.jsonl").read_text().splitlines()
    assert len(lines) == 5
    assert [json.loads(line)["i"] for line in lines] == [0, 1, 2, 3, 4]


def test_rotates_on_date_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Rotation: stamp a record on day 1, advance the clock, stamp another, expect two files."""

    class FrozenDateTime:
        current = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(tl, "datetime", FrozenDateTime)

    writer = JsonlWriter(tmp_path)
    try:
        writer.write({"day": 1})
        FrozenDateTime.current = datetime(2026, 5, 3, 0, 0, 1, tzinfo=UTC)
        writer.write({"day": 2})
    finally:
        writer.close()

    files = sorted(p.name for p in tmp_path.glob("tempest-*.jsonl"))
    assert files == ["tempest-2026-05-02.jsonl", "tempest-2026-05-03.jsonl"]
    day1 = json.loads((tmp_path / "tempest-2026-05-02.jsonl").read_text().strip())
    day2 = json.loads((tmp_path / "tempest-2026-05-03.jsonl").read_text().strip())
    assert day1 == {"day": 1}
    assert day2 == {"day": 2}


def test_close_is_idempotent(tmp_path: Path) -> None:
    writer = JsonlWriter(tmp_path)
    writer.write({"a": 1})
    writer.close()
    writer.close()  # second close must not raise


def test_flush_before_any_write_is_safe(tmp_path: Path) -> None:
    writer = JsonlWriter(tmp_path)
    writer.flush()  # no file open yet — must not raise
    writer.close()
