"""CLI for inspecting aggregated sensor stats from the weather DB."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from home_weather_hub.storage.schema import open_db

DEFAULT_DB_PATH = Path("./data/weather.db")


def _print_table(rows: list[sqlite3.Row], headers: list[str]) -> None:
    if not rows:
        print("(no rows)")
        return
    widths = [len(h) for h in headers]
    body = []
    for r in rows:
        cells = [str(r[h]) if r[h] is not None else "" for h in headers]
        for i, c in enumerate(cells):
            widths[i] = max(widths[i], len(c))
        body.append(cells)
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    print(line)
    print("  ".join("-" * w for w in widths))
    for cells in body:
        print("  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)))


def _query_monthly(
    conn: sqlite3.Connection,
    year_month: str,
    metric: str | None,
    sensor: str | None,
) -> list[sqlite3.Row]:
    sql = (
        "SELECT sensor_id, metric, min_value AS min, max_value AS max, "
        "ROUND(sum_value * 1.0 / count, 3) AS mean, count, "
        "datetime(min_ts, 'unixepoch') AS min_at, "
        "datetime(max_ts, 'unixepoch') AS max_at "
        "FROM monthly_aggregates WHERE year_month = ?"
    )
    args: list[str] = [year_month]
    if metric:
        sql += " AND metric = ?"
        args.append(metric)
    if sensor:
        sql += " AND sensor_id = ?"
        args.append(sensor)
    sql += " ORDER BY sensor_id, metric"
    return list(conn.execute(sql, args))


def _query_strikes(
    conn: sqlite3.Connection,
    last_days: int | None,
    sensor: str | None,
) -> list[sqlite3.Row]:
    sql = (
        "SELECT datetime(ts, 'unixepoch') AS at, sensor_id, distance_km, energy "
        "FROM lightning_strikes WHERE 1=1"
    )
    args: list = []
    if last_days is not None:
        cutoff = int((datetime.now(UTC) - timedelta(days=last_days)).timestamp())
        sql += " AND ts >= ?"
        args.append(cutoff)
    if sensor:
        sql += " AND sensor_id = ?"
        args.append(sensor)
    sql += " ORDER BY ts DESC LIMIT 500"
    return list(conn.execute(sql, args))


def _query_daily(
    conn: sqlite3.Connection,
    last_days: int,
    metric: str | None,
    sensor: str | None,
) -> list[sqlite3.Row]:
    cutoff = (datetime.now(UTC) - timedelta(days=last_days)).strftime("%Y-%m-%d")
    sql = (
        "SELECT day, sensor_id, metric, min_value AS min, max_value AS max, "
        "ROUND(sum_value * 1.0 / count, 3) AS mean, count "
        "FROM daily_aggregates WHERE day >= ?"
    )
    args: list[str] = [cutoff]
    if metric:
        sql += " AND metric = ?"
        args.append(metric)
    if sensor:
        sql += " AND sensor_id = ?"
        args.append(sensor)
    sql += " ORDER BY day, sensor_id, metric"
    return list(conn.execute(sql, args))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--month",
        help="YYYY-MM bucket (default: current UTC month). Ignored if --last-days is set.",
    )
    parser.add_argument(
        "--last-days",
        type=int,
        help="Show daily rollups for the last N days instead of the monthly summary.",
    )
    parser.add_argument("--metric", help="Filter to a single metric (e.g. air_temp_c).")
    parser.add_argument("--sensor", help="Filter to a single sensor_id.")
    parser.add_argument(
        "--strikes",
        action="store_true",
        help="Show individual lightning strikes instead of metric aggregates.",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        raise SystemExit(f"db not found: {args.db_path}")

    conn = open_db(args.db_path)
    try:
        if args.strikes:
            rows = _query_strikes(conn, args.last_days, args.sensor)
            print(
                "# lightning strikes" + (f" (last {args.last_days} days)" if args.last_days else "")
            )
            _print_table(rows, ["at", "sensor_id", "distance_km", "energy"])
        elif args.last_days is not None:
            rows = _query_daily(conn, args.last_days, args.metric, args.sensor)
            _print_table(
                rows,
                ["day", "sensor_id", "metric", "min", "max", "mean", "count"],
            )
        else:
            year_month = args.month or datetime.now(UTC).strftime("%Y-%m")
            rows = _query_monthly(conn, year_month, args.metric, args.sensor)
            print(f"# month: {year_month}")
            _print_table(
                rows,
                [
                    "sensor_id",
                    "metric",
                    "min",
                    "max",
                    "mean",
                    "count",
                    "min_at",
                    "max_at",
                ],
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
