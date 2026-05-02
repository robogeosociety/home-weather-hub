"""SQLite schema and connection helper for the weather hub aggregate store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id   TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    label       TEXT,
    location    TEXT,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    ts          INTEGER NOT NULL,
    sensor_id   TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL,
    PRIMARY KEY (sensor_id, metric, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_obs_metric_ts ON observations(metric, ts);

CREATE TABLE IF NOT EXISTS daily_aggregates (
    day         TEXT    NOT NULL,
    sensor_id   TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    min_value   REAL    NOT NULL,
    max_value   REAL    NOT NULL,
    sum_value   REAL    NOT NULL,
    count       INTEGER NOT NULL,
    min_ts      INTEGER NOT NULL,
    max_ts      INTEGER NOT NULL,
    PRIMARY KEY (day, sensor_id, metric)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS monthly_aggregates (
    year_month  TEXT    NOT NULL,
    sensor_id   TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    min_value   REAL    NOT NULL,
    max_value   REAL    NOT NULL,
    sum_value   REAL    NOT NULL,
    count       INTEGER NOT NULL,
    min_ts      INTEGER NOT NULL,
    max_ts      INTEGER NOT NULL,
    PRIMARY KEY (year_month, sensor_id, metric)
) WITHOUT ROWID;

-- One row per evt_strike packet. Tempest reports distance from the station
-- (no bearing) and a unitless energy estimate. There is no spatial location;
-- placing strikes on a map requires the station's known lat/lon.
CREATE TABLE IF NOT EXISTS lightning_strikes (
    ts          INTEGER NOT NULL,
    sensor_id   TEXT    NOT NULL,
    distance_km REAL    NOT NULL,
    energy      INTEGER NOT NULL,
    PRIMARY KEY (sensor_id, ts)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_strikes_ts ON lightning_strikes(ts);
"""


def open_db(path: Path | str) -> sqlite3.Connection:
    """Open (or create) the weather DB with WAL + sane defaults and ensure schema."""
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn
