"""Read-side store for the dashboard API.

Today: scans the daily JSONL files the listener writes. Tomorrow: swap the impl
for DuckDB (`read_json_auto('data/tempest-*.jsonl')`) without touching any
callsite. The interface IS the architecture; the backing store is an
implementation detail.

Metric keys are dotted paths into a `DecodedObsSt` field, e.g. `air_temp_c`,
`wind_avg_mph`, `relative_humidity_pct`, `pressure_mb`. The metric registry is
the contract between widgets and the store.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from home_weather_hub.tempest_decode import (
    DecodedEvtStrike,
    DecodedObsSt,
    DecodedRapidWind,
    decode,
)

log = logging.getLogger(__name__)


# Metric registry. Each entry maps a stable dotted key to (event_type, attribute).
# Widgets reference these keys; the store resolves them.
METRICS: dict[str, tuple[str, str]] = {
    "outdoor.air_temp_c": ("obs_st", "air_temp_c"),
    "outdoor.air_temp_f": ("obs_st", "air_temp_f"),
    "outdoor.relative_humidity_pct": ("obs_st", "relative_humidity_pct"),
    "outdoor.pressure_mb": ("obs_st", "pressure_mb"),
    "outdoor.wind_avg_mph": ("obs_st", "wind_avg_mph"),
    "outdoor.wind_gust_mph": ("obs_st", "wind_gust_mph"),
    "outdoor.wind_direction_deg": ("obs_st", "wind_direction_deg"),
    "outdoor.uv_index": ("obs_st", "uv_index"),
    "outdoor.illuminance_lux": ("obs_st", "illuminance_lux"),
    "outdoor.solar_radiation_w_m2": ("obs_st", "solar_radiation_w_m2"),
    "outdoor.rain_accumulated_in": ("obs_st", "rain_accumulated_in"),
    "outdoor.battery_voltage": ("obs_st", "battery_voltage"),
    # rapid_wind cadence (3s) — preferred for live wind widgets
    "outdoor.rapid_wind_speed_mph": ("rapid_wind", "wind_speed_mph"),
    "outdoor.rapid_wind_direction_deg": ("rapid_wind", "wind_direction_deg"),
}


@dataclass(frozen=True)
class Point:
    t: int  # unix epoch seconds
    v: float


@dataclass(frozen=True)
class StrikePoint:
    t: int
    distance_km: float
    energy: float


# ---- helpers ---------------------------------------------------------------


def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                log.debug("skipping malformed JSONL line in %s", path)


def _dates_in_range(since: datetime, until: datetime) -> list[date]:
    """Inclusive list of UTC dates spanned by [since, until]."""
    d = since.astimezone(UTC).date()
    end = until.astimezone(UTC).date()
    out: list[date] = []
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


# ---- store -----------------------------------------------------------------


class JsonlStore:
    def __init__(self, data_dir: Path):
        self._data_dir = data_dir

    # ---- file discovery ----

    def _path_for(self, d: date) -> Path:
        return self._data_dir / f"tempest-{d.isoformat()}.jsonl"

    def _files_in_range(self, since: datetime, until: datetime) -> list[Path]:
        return [self._path_for(d) for d in _dates_in_range(since, until)]

    def _all_files(self) -> list[Path]:
        if not self._data_dir.exists():
            return []
        return sorted(self._data_dir.glob("tempest-*.jsonl"))

    # ---- snapshot / history ----

    def latest_snapshot(self) -> dict[str, Any]:
        """Most recent decoded value of each known event type, plus metric values.

        Walks the most recent JSONL files in reverse until each event type is
        seen at least once. Returns a dict shaped for the API response.
        """
        seen_types: dict[str, dict] = {}
        wanted = {"obs_st", "rapid_wind", "evt_strike", "hub_status", "device_status"}
        for path in reversed(self._all_files()):
            for record in reversed(list(_iter_jsonl(path))):
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                t = payload.get("type")
                if t in wanted and t not in seen_types:
                    decoded = decode(payload)
                    if decoded is not None:
                        seen_types[t] = decoded.model_dump(mode="json") | {
                            "received_at": record.get("received_at")
                        }
                        if seen_types.keys() >= wanted:
                            break
            if seen_types.keys() >= wanted:
                break
        # Build a flat metric map for the dashboard's BigReadout widgets.
        metrics: dict[str, float | None] = {}
        for key, (event_type, attr) in METRICS.items():
            event = seen_types.get(event_type)
            metrics[key] = event.get(attr) if event else None
        return {"events": seen_types, "metrics": metrics}

    def history(self, metric: str, since: datetime, until: datetime) -> list[Point]:
        spec = METRICS.get(metric)
        if spec is None:
            return []
        event_type, attr = spec
        out: list[Point] = []
        for path in self._files_in_range(since, until):
            for record in _iter_jsonl(path):
                payload = record.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != event_type:
                    continue
                decoded = decode(payload)
                if decoded is None:
                    continue
                value = getattr(decoded, attr, None)
                if value is None:
                    continue
                t = getattr(decoded, "time_epoch", None)
                if t is None:
                    # Fall back to the receipt timestamp for hub/device/etc.
                    received_at = record.get("received_at")
                    if isinstance(received_at, str):
                        try:
                            t = int(datetime.fromisoformat(received_at).timestamp())
                        except ValueError:
                            continue
                    else:
                        continue
                out.append(Point(t=int(t), v=float(value)))
        out.sort(key=lambda p: p.t)
        return out

    def recent_strikes(self, since: datetime) -> list[StrikePoint]:
        until = datetime.now(UTC)
        out: list[StrikePoint] = []
        for path in self._files_in_range(since, until):
            for record in _iter_jsonl(path):
                payload = record.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "evt_strike":
                    continue
                decoded = decode(payload)
                if not isinstance(decoded, DecodedEvtStrike):
                    continue
                if decoded.time_epoch is None or decoded.distance_km is None:
                    continue
                if decoded.time_epoch < int(since.timestamp()):
                    continue
                out.append(
                    StrikePoint(
                        t=int(decoded.time_epoch),
                        distance_km=float(decoded.distance_km),
                        energy=float(decoded.energy or 0.0),
                    )
                )
        out.sort(key=lambda s: s.t)
        return out

    # ---- layout persistence ----

    def _layout_path(self) -> Path:
        return self._data_dir / "layout.json"

    def read_layout(self) -> dict[str, Any] | None:
        path = self._layout_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("layout.json malformed; ignoring")
            return None

    def write_layout(self, layout: dict[str, Any]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # Atomic-ish: write to a temp file then rename.
        path = self._layout_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(layout, indent=2), encoding="utf-8")
        tmp.replace(path)


# Re-exports for callers that want the model types alongside the store.
__all__ = [
    "METRICS",
    "DecodedObsSt",
    "DecodedRapidWind",
    "JsonlStore",
    "Point",
    "StrikePoint",
]
