"""Incremental min/max/mean aggregator over (sensor, metric, ts, value) records."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

# NOTE on min_ts/max_ts tie-break: the CASE expressions use strict `<` / `>`,
# so when a new observation ties the existing extreme the *first* occurrence's
# timestamp is preserved. That gives the dashboard a stable "first time today
# we saw the high/low" answer instead of jittering to the most recent tie.
_UPSERT_DAILY = """
INSERT INTO daily_aggregates
    (day, sensor_id, metric, min_value, max_value, sum_value, count, min_ts, max_ts)
VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
ON CONFLICT(day, sensor_id, metric) DO UPDATE SET
    min_value = MIN(min_value, excluded.min_value),
    max_value = MAX(max_value, excluded.max_value),
    sum_value = sum_value + excluded.sum_value,
    count     = count + 1,
    min_ts    = CASE WHEN excluded.min_value < min_value THEN excluded.min_ts ELSE min_ts END,
    max_ts    = CASE WHEN excluded.max_value > max_value THEN excluded.max_ts ELSE max_ts END
"""

_UPSERT_MONTHLY = """
INSERT INTO monthly_aggregates
    (year_month, sensor_id, metric, min_value, max_value, sum_value, count, min_ts, max_ts)
VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
ON CONFLICT(year_month, sensor_id, metric) DO UPDATE SET
    min_value = MIN(min_value, excluded.min_value),
    max_value = MAX(max_value, excluded.max_value),
    sum_value = sum_value + excluded.sum_value,
    count     = count + 1,
    min_ts    = CASE WHEN excluded.min_value < min_value THEN excluded.min_ts ELSE min_ts END,
    max_ts    = CASE WHEN excluded.max_value > max_value THEN excluded.max_ts ELSE max_ts END
"""

_UPSERT_SENSOR = """
INSERT INTO sensors (sensor_id, kind, label, location, first_seen, last_seen)
VALUES (?, ?, NULL, ?, ?, ?)
ON CONFLICT(sensor_id) DO UPDATE SET
    last_seen = MAX(last_seen, excluded.last_seen),
    kind      = excluded.kind,
    location  = COALESCE(sensors.location, excluded.location)
"""


def _day_bucket(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def _month_bucket(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")


class Aggregator:
    """Wraps a sqlite3 connection; one record() per (sensor, metric, ts, value)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def record(
        self,
        sensor_id: str,
        kind: str,
        location: str | None,
        metric: str,
        value: float,
        ts: int,
    ) -> None:
        self.record_many([(sensor_id, kind, location, metric, value, ts)])

    def record_many(
        self,
        rows: Iterable[tuple[str, str, str | None, str, float, int]],
    ) -> None:
        rows = list(rows)
        if not rows:
            return
        conn = self._conn
        conn.execute("BEGIN")
        try:
            # Per-sensor min/max ts in the batch. The one sensor upsert per
            # (sensor, batch) seeds first_seen with the earliest accepted ts
            # and bumps last_seen to the latest — so a catch-up batch after a
            # reconnect doesn't accidentally rewrite first_seen forward or
            # leave last_seen behind.
            sensor_span: dict[str, tuple[str, str | None, int, int]] = {}
            for sensor_id, kind, location, metric, value, ts in rows:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO observations (ts, sensor_id, metric, value) "
                    "VALUES (?, ?, ?, ?)",
                    (ts, sensor_id, metric, value),
                )
                if cur.rowcount == 0:
                    # Duplicate (sensor, metric, ts) — skip the rollups to avoid
                    # double-counting in min/max/sum/count.
                    continue
                day = _day_bucket(ts)
                month = _month_bucket(ts)
                conn.execute(
                    _UPSERT_DAILY,
                    (day, sensor_id, metric, value, value, value, ts, ts),
                )
                conn.execute(
                    _UPSERT_MONTHLY,
                    (month, sensor_id, metric, value, value, value, ts, ts),
                )
                prev = sensor_span.get(sensor_id)
                if prev is None:
                    sensor_span[sensor_id] = (kind, location, ts, ts)
                else:
                    sensor_span[sensor_id] = (
                        kind,
                        location,
                        min(prev[2], ts),
                        max(prev[3], ts),
                    )
            for sensor_id, (kind, location, first_ts, last_ts) in sensor_span.items():
                conn.execute(_UPSERT_SENSOR, (sensor_id, kind, location, first_ts, last_ts))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def record_strike(
        self,
        sensor_id: str,
        kind: str,
        location: str | None,
        ts: int,
        distance_km: float,
        energy: int,
    ) -> None:
        """Persist a single lightning strike. Idempotent on (sensor_id, ts)."""
        conn = self._conn
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO lightning_strikes "
                "(ts, sensor_id, distance_km, energy) VALUES (?, ?, ?, ?)",
                (ts, sensor_id, distance_km, energy),
            )
            conn.execute(_UPSERT_SENSOR, (sensor_id, kind, location, ts, ts))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def upsert_station_metadata(
        self,
        sensor_id: str,
        kind: str,
        label: str | None = None,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        ts: int | None = None,
    ) -> None:
        """Seed or update a sensor's static metadata (label, location, lat/lng).

        Per-packet writes via record()/record_strike() never overwrite these
        fields — they only bump last_seen and refuse to clobber an existing
        location. Use this from listener startup after loading station config.
        """
        conn = self._conn
        seed_ts = ts if ts is not None else int(datetime.now(UTC).timestamp())
        conn.execute(
            """
            INSERT INTO sensors
                (sensor_id, kind, label, location, latitude, longitude,
                 first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sensor_id) DO UPDATE SET
                kind      = excluded.kind,
                label     = COALESCE(excluded.label, sensors.label),
                location  = COALESCE(excluded.location, sensors.location),
                latitude  = COALESCE(excluded.latitude, sensors.latitude),
                longitude = COALESCE(excluded.longitude, sensors.longitude)
            """,
            (sensor_id, kind, label, location, latitude, longitude, seed_ts, seed_ts),
        )

    def close(self) -> None:
        self._conn.close()
