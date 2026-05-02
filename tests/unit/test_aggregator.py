"""Unit tests for the SQLite-backed Aggregator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from home_weather_hub.storage import Aggregator, open_db

pytestmark = pytest.mark.unit


def _epoch(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp())


@pytest.fixture
def agg() -> Aggregator:
    return Aggregator(open_db(":memory:"))


def test_first_record_creates_row_with_min_eq_max_eq_value(agg: Aggregator) -> None:
    ts = _epoch(2026, 5, 2)
    agg.record("tempest:ST-1", "tempest", "outside", "air_temp_c", 18.5, ts)
    row = agg._conn.execute(
        "SELECT min_value, max_value, sum_value, count, min_ts, max_ts FROM monthly_aggregates"
    ).fetchone()
    assert row["min_value"] == 18.5
    assert row["max_value"] == 18.5
    assert row["sum_value"] == 18.5
    assert row["count"] == 1
    assert row["min_ts"] == ts
    assert row["max_ts"] == ts


def test_subsequent_records_update_min_max_sum_count(agg: Aggregator) -> None:
    base_ts = _epoch(2026, 5, 2, 10)
    for i, v in enumerate([18.0, 22.0, 15.0, 19.5]):
        agg.record("tempest:ST-1", "tempest", "outside", "air_temp_c", v, base_ts + i * 60)
    row = agg._conn.execute(
        "SELECT min_value, max_value, sum_value, count, "
        "ROUND(sum_value/count, 4) AS mean FROM monthly_aggregates"
    ).fetchone()
    assert row["min_value"] == 15.0
    assert row["max_value"] == 22.0
    assert row["sum_value"] == pytest.approx(74.5)
    assert row["count"] == 4
    assert row["mean"] == pytest.approx(18.625)


def test_min_max_ts_track_when_extremes_were_set(agg: Aggregator) -> None:
    ts1 = _epoch(2026, 5, 2, 10)
    ts2 = _epoch(2026, 5, 2, 14)
    ts3 = _epoch(2026, 5, 2, 18)
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, ts1)
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 25.0, ts2)  # new max
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 12.0, ts3)  # new min
    row = agg._conn.execute("SELECT min_ts, max_ts FROM monthly_aggregates").fetchone()
    assert row["min_ts"] == ts3
    assert row["max_ts"] == ts2


def test_day_boundary_creates_distinct_daily_rows_same_monthly(agg: Aggregator) -> None:
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, _epoch(2026, 5, 2))
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 22.0, _epoch(2026, 5, 3))
    daily = agg._conn.execute("SELECT day, count FROM daily_aggregates ORDER BY day").fetchall()
    assert [r["day"] for r in daily] == ["2026-05-02", "2026-05-03"]
    assert all(r["count"] == 1 for r in daily)
    monthly = agg._conn.execute("SELECT count FROM monthly_aggregates").fetchall()
    assert len(monthly) == 1 and monthly[0]["count"] == 2


def test_month_boundary_creates_distinct_monthly_rows(agg: Aggregator) -> None:
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, _epoch(2026, 4, 30, 23))
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 22.0, _epoch(2026, 5, 1, 1))
    rows = agg._conn.execute(
        "SELECT year_month, count FROM monthly_aggregates ORDER BY year_month"
    ).fetchall()
    assert [r["year_month"] for r in rows] == ["2026-04", "2026-05"]
    assert all(r["count"] == 1 for r in rows)


def test_distinct_sensors_do_not_collide_on_same_metric(agg: Aggregator) -> None:
    ts = _epoch(2026, 5, 2)
    agg.record("tempest:ST-1", "tempest", "outside", "air_temp_c", 18.0, ts)
    agg.record("snzb:0xa1", "snzb-02wd", "living_room", "air_temp_c", 22.5, ts)
    rows = agg._conn.execute(
        "SELECT sensor_id, max_value FROM monthly_aggregates ORDER BY sensor_id"
    ).fetchall()
    assert {r["sensor_id"]: r["max_value"] for r in rows} == {
        "snzb:0xa1": 22.5,
        "tempest:ST-1": 18.0,
    }
    sensor_kinds = {
        r["sensor_id"]: r["kind"] for r in agg._conn.execute("SELECT sensor_id, kind FROM sensors")
    }
    assert sensor_kinds == {"tempest:ST-1": "tempest", "snzb:0xa1": "snzb-02wd"}


def test_record_many_runs_in_single_transaction(agg: Aggregator) -> None:
    ts = _epoch(2026, 5, 2)
    rows = [
        ("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, ts),
        ("tempest:ST-1", "tempest", None, "humidity_pct", 60.0, ts),
        ("tempest:ST-1", "tempest", None, "wind_avg_mps", 3.2, ts),
    ]
    agg.record_many(rows)
    n_obs = agg._conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert n_obs == 3
    assert agg._conn.execute("SELECT COUNT(*) AS n FROM monthly_aggregates").fetchone()["n"] == 3
    # Sensor row written exactly once per record_many even with three metrics.
    n_sensors = agg._conn.execute("SELECT COUNT(*) AS n FROM sensors").fetchone()["n"]
    assert n_sensors == 1


def test_duplicate_observations_are_idempotent(agg: Aggregator) -> None:
    """Replaying the same (sensor, metric, ts) must not double-count in either
    the observations table or the rollups."""
    ts = _epoch(2026, 5, 2)
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, ts)
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, ts)
    n_obs = agg._conn.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"]
    assert n_obs == 1
    row = agg._conn.execute("SELECT count, sum_value FROM monthly_aggregates").fetchone()
    assert row["count"] == 1
    assert row["sum_value"] == 18.0


def test_record_strike_persists_individual_strike(agg: Aggregator) -> None:
    ts = _epoch(2026, 5, 2, 14, 30)
    agg.record_strike("tempest:ST-1", "tempest", "outside", ts, 12.5, 4567)
    row = agg._conn.execute(
        "SELECT ts, sensor_id, distance_km, energy FROM lightning_strikes"
    ).fetchone()
    assert row["ts"] == ts
    assert row["sensor_id"] == "tempest:ST-1"
    assert row["distance_km"] == 12.5
    assert row["energy"] == 4567
    sensor = agg._conn.execute("SELECT kind, location FROM sensors").fetchone()
    assert sensor["kind"] == "tempest"
    assert sensor["location"] == "outside"


def test_record_strike_is_idempotent_on_sensor_ts(agg: Aggregator) -> None:
    ts = _epoch(2026, 5, 2, 14, 30)
    agg.record_strike("tempest:ST-1", "tempest", None, ts, 12.5, 4567)
    agg.record_strike("tempest:ST-1", "tempest", None, ts, 12.5, 4567)
    n = agg._conn.execute("SELECT COUNT(*) AS n FROM lightning_strikes").fetchone()["n"]
    assert n == 1


def test_two_strikes_at_different_ts_both_persist(agg: Aggregator) -> None:
    base = _epoch(2026, 5, 2, 14, 30)
    agg.record_strike("tempest:ST-1", "tempest", None, base, 8.0, 1000)
    agg.record_strike("tempest:ST-1", "tempest", None, base + 5, 9.5, 2000)
    rows = agg._conn.execute(
        "SELECT distance_km, energy FROM lightning_strikes ORDER BY ts"
    ).fetchall()
    assert [(r["distance_km"], r["energy"]) for r in rows] == [(8.0, 1000), (9.5, 2000)]


def test_upsert_station_metadata_seeds_lat_lng(agg: Aggregator) -> None:
    agg.upsert_station_metadata(
        sensor_id="tempest:ST-1",
        kind="tempest",
        label="Backyard",
        location="outside",
        latitude=47.6062,
        longitude=-122.3321,
    )
    row = agg._conn.execute("SELECT label, location, latitude, longitude FROM sensors").fetchone()
    assert row["label"] == "Backyard"
    assert row["location"] == "outside"
    assert row["latitude"] == pytest.approx(47.6062)
    assert row["longitude"] == pytest.approx(-122.3321)


def test_record_does_not_clobber_seeded_metadata(agg: Aggregator) -> None:
    seed_ts = _epoch(2026, 5, 1)
    agg.upsert_station_metadata(
        sensor_id="tempest:ST-1",
        kind="tempest",
        label="Backyard",
        location="outside",
        latitude=47.6062,
        longitude=-122.3321,
        ts=seed_ts,
    )
    ts = _epoch(2026, 5, 2)
    # Per-packet record passes None for label/lat/lng — must not wipe seeded values.
    agg.record("tempest:ST-1", "tempest", None, "air_temp_c", 18.0, ts)
    row = agg._conn.execute(
        "SELECT label, location, latitude, longitude, first_seen, last_seen FROM sensors"
    ).fetchone()
    assert row["label"] == "Backyard"
    assert row["location"] == "outside"
    assert row["latitude"] == pytest.approx(47.6062)
    assert row["longitude"] == pytest.approx(-122.3321)
    assert row["first_seen"] == seed_ts
    assert row["last_seen"] == ts  # bumped to packet time


def test_strikes_with_location_view_joins_to_sensors(agg: Aggregator) -> None:
    agg.upsert_station_metadata(
        sensor_id="tempest:ST-1",
        kind="tempest",
        location="outside",
        latitude=47.6062,
        longitude=-122.3321,
    )
    ts = _epoch(2026, 5, 2, 14, 30)
    agg.record_strike("tempest:ST-1", "tempest", None, ts, 12.0, 4567)
    row = agg._conn.execute(
        "SELECT distance_km, station_latitude, station_longitude, station_location "
        "FROM strikes_with_location"
    ).fetchone()
    assert row["distance_km"] == 12.0
    assert row["station_latitude"] == pytest.approx(47.6062)
    assert row["station_longitude"] == pytest.approx(-122.3321)
    assert row["station_location"] == "outside"


def test_upsert_station_metadata_is_partial_update(agg: Aggregator) -> None:
    """Calling twice with different fields merges — None in the second call doesn't
    null out fields that were set in the first."""
    agg.upsert_station_metadata(
        sensor_id="tempest:ST-1", kind="tempest", latitude=47.0, longitude=-122.0
    )
    agg.upsert_station_metadata(sensor_id="tempest:ST-1", kind="tempest", label="Backyard")
    row = agg._conn.execute("SELECT label, latitude, longitude FROM sensors").fetchone()
    assert row["label"] == "Backyard"
    assert row["latitude"] == 47.0
    assert row["longitude"] == -122.0


def test_mean_derivable_from_sum_and_count(agg: Aggregator) -> None:
    base = _epoch(2026, 5, 2, 10)
    for i, v in enumerate([10.0, 20.0, 30.0]):
        agg.record("tempest:ST-1", "tempest", None, "uv_index", v, base + i * 60)
    mean = agg._conn.execute(
        "SELECT sum_value * 1.0 / count AS mean FROM monthly_aggregates"
    ).fetchone()["mean"]
    assert mean == pytest.approx(20.0)
