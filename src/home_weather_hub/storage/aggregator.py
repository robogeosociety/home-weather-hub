"""Incremental min/max/mean aggregator over (sensor, metric, ts, value) records."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

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
            seen_sensors: set[str] = set()
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
                if sensor_id not in seen_sensors:
                    conn.execute(_UPSERT_SENSOR, (sensor_id, kind, location, ts, ts))
                    seen_sensors.add(sensor_id)
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

    def close(self) -> None:
        self._conn.close()
