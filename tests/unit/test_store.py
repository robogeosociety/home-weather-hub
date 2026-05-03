"""Unit tests for the JSONL store."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from home_weather_hub.store import JsonlStore

pytestmark = pytest.mark.unit


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _envelope(payload: dict, when: datetime | None = None) -> dict:
    when = when or datetime.now(UTC)
    return {
        "received_at": when.isoformat(),
        "src_addr": "192.168.4.20",
        "payload": payload,
    }


def _obs_st(time_epoch: int, temp_c: float = 20.0, wind_mps: float = 2.0) -> dict:
    return {
        "type": "obs_st",
        "obs": [
            [
                time_epoch,
                1.0,
                wind_mps,
                wind_mps + 1,
                90.0,
                3,
                1013.25,
                temp_c,
                50.0,
                1000.0,
                2.0,
                200.0,
                0.0,
                0,
                0.0,
                0,
                2.78,
                1,
            ]
        ],
    }


# ---- snapshot --------------------------------------------------------------


def test_latest_snapshot_returns_empty_when_no_data(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path)
    snap = store.latest_snapshot()
    assert snap["events"] == {}
    assert snap["metrics"]["outdoor.air_temp_c"] is None


def test_latest_snapshot_picks_most_recent_obs_st(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    path = tmp_path / f"tempest-{today.isoformat()}.jsonl"
    _write_jsonl(
        path,
        [
            _envelope(_obs_st(1700000000, temp_c=10.0)),
            _envelope(_obs_st(1700000060, temp_c=15.0)),
            _envelope(_obs_st(1700000120, temp_c=22.5)),
        ],
    )
    snap = JsonlStore(tmp_path).latest_snapshot()
    assert snap["events"]["obs_st"]["air_temp_c"] == 22.5
    assert snap["metrics"]["outdoor.air_temp_c"] == 22.5
    assert snap["metrics"]["outdoor.air_temp_f"] == pytest.approx(72.5, abs=0.05)


def test_latest_snapshot_skips_malformed_lines(tmp_path: Path) -> None:
    today = datetime.now(UTC).date()
    path = tmp_path / f"tempest-{today.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("not-json\n")
        fh.write(json.dumps(_envelope(_obs_st(1700000000, temp_c=11.1))) + "\n")
        fh.write("\n")  # blank
    snap = JsonlStore(tmp_path).latest_snapshot()
    assert snap["events"]["obs_st"]["air_temp_c"] == 11.1


# ---- history ---------------------------------------------------------------


def test_history_returns_sorted_points_for_metric(tmp_path: Path) -> None:
    # Pick an epoch and derive the file date from it so file-discovery and
    # since/until lookups agree.
    base = 1700000000  # 2023-11-14 22:13:20 UTC
    file_date = datetime.fromtimestamp(base, tz=UTC).date()
    path = tmp_path / f"tempest-{file_date.isoformat()}.jsonl"
    _write_jsonl(
        path,
        [
            _envelope(_obs_st(base + 120, temp_c=15.0)),
            _envelope(_obs_st(base, temp_c=10.0)),
            _envelope(_obs_st(base + 60, temp_c=12.5)),
        ],
    )
    points = JsonlStore(tmp_path).history(
        "outdoor.air_temp_c",
        since=datetime.fromtimestamp(base - 1, tz=UTC),
        until=datetime.fromtimestamp(base + 200, tz=UTC),
    )
    assert [p.t for p in points] == [base, base + 60, base + 120]
    assert [p.v for p in points] == [10.0, 12.5, 15.0]


def test_history_unknown_metric_returns_empty(tmp_path: Path) -> None:
    assert (
        JsonlStore(tmp_path).history(
            "outdoor.nonexistent",
            since=datetime.now(UTC) - timedelta(days=1),
            until=datetime.now(UTC),
        )
        == []
    )


# ---- strikes ---------------------------------------------------------------


def test_recent_strikes_filters_by_since_and_sorts(tmp_path: Path) -> None:
    # `recent_strikes` walks files from `since` up to *now*, so we must use a
    # recent epoch — otherwise the date range never includes the file we wrote.
    now = datetime.now(UTC)
    base = int(now.timestamp())
    file_date = now.date()
    path = tmp_path / f"tempest-{file_date.isoformat()}.jsonl"
    _write_jsonl(
        path,
        [
            _envelope({"type": "evt_strike", "evt": [base - 10, 5.0, 4096]}),
            _envelope({"type": "evt_strike", "evt": [base - 200, 12.0, 2048]}),  # too old
            _envelope({"type": "evt_strike", "evt": [base - 5, 2.5, 8192]}),
        ],
    )
    strikes = JsonlStore(tmp_path).recent_strikes(
        since=datetime.fromtimestamp(base - 60, tz=UTC),
    )
    assert [s.t for s in strikes] == [base - 10, base - 5]
    assert [s.distance_km for s in strikes] == [5.0, 2.5]


# ---- layout ---------------------------------------------------------------


def test_layout_round_trip(tmp_path: Path) -> None:
    store = JsonlStore(tmp_path)
    assert store.read_layout() is None
    store.write_layout({"mac": [{"i": "temp", "x": 0, "y": 0, "w": 4, "h": 3}]})
    assert store.read_layout() == {"mac": [{"i": "temp", "x": 0, "y": 0, "w": 4, "h": 3}]}


def test_layout_write_is_atomic(tmp_path: Path) -> None:
    """A second write must replace the first cleanly, no partial files left behind."""
    store = JsonlStore(tmp_path)
    store.write_layout({"v": 1})
    store.write_layout({"v": 2})
    assert store.read_layout() == {"v": 2}
    assert not (tmp_path / "layout.json.tmp").exists()


def test_layout_malformed_returns_none(tmp_path: Path) -> None:
    (tmp_path / "layout.json").write_text("{not json")
    assert JsonlStore(tmp_path).read_layout() is None
