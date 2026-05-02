# home-weather-hub
Monitor outside and inside climate and host a live dashboard on the local network

## Objective
- Monitor my [Tempest](https://shop.tempest.earth/products/tempest) outside weather station updates over UDP
- Monitor my internal climate using a zigbee network over mqtt
- Host a containerized web application on my Mac Mini M1 that displays a live dashboard of my inside and outside climate
- (Stretch goal) incorporate a live webcam as the background for the webapp co-sited with the Tempest

## Status

| Area | Status |
|---|---|
| Tempest UDP listener (`asyncio.DatagramProtocol`) | ✅ Implemented — `src/home_weather_hub/tempest_listener.py` |
| Daily-rotated JSONL writer with malformed-packet handling | ✅ Implemented |
| `tempest-listener` CLI (`uv run tempest-listener`) | ✅ Implemented |
| SQLite observation + monthly/daily aggregate store | ✅ Implemented — `src/home_weather_hub/storage/` |
| `tempest-stats` CLI (`uv run tempest-stats`) | ✅ Implemented |
| Test pyramid (unit / integration / e2e) | ✅ 35 tests, all passing |
| Lint + format (`ruff`) | ✅ Configured |
| Zigbee/MQTT subscriber for indoor sensors (SNZB-02WD) | ⏳ Not started — schema is sensor-agnostic and ready |
| Dashboard web app | ⏳ Not started |
| Containerized deployment to Mac Mini M1 | ⏳ Not started |
| Webcam backdrop (stretch) | ⏳ Not started |

**Known field issue (2026-05-02):** the Tempest hub at `192.168.4.20` is healthy and broadcasting `hub_status` every ~10s, but the outdoor device itself isn't transmitting (`obs_st`/`rapid_wind`/`device_status` absent). Likely battery or sub-GHz radio link — needs checking in the WeatherFlow app before useful sample data can be collected.

## Quick start

```sh
uv sync                              # install runtime + dev deps
uv run tempest-listener              # bind 0.0.0.0:50222, write JSONL + SQLite to ./data/
uv run tempest-listener --port 50222 --data-dir ./data --db-path ./data/weather.db
uv run tempest-listener --no-db      # JSONL only (skip the aggregate DB)
```

Stop with `Ctrl-C`; SIGINT/SIGTERM trigger a clean drain + close. Each `obs_st` packet is JSONL-appended **and** decoded into the SQLite aggregate store; raw packets land in `./data/*.jsonl` (gitignored), one record per line as `{received_at, src_addr, payload}`.

## Aggregate storage

`data/weather.db` (SQLite, WAL mode) holds everything the dashboard will query. Schema:

| Table | Grain | Purpose |
|---|---|---|
| `sensors` | one row per device | sensor catalog (`tempest:<serial>`, `snzb:<ieee>`, …) — first/last seen, location |
| `observations` | one row per `(sensor, metric, ts)` | per-sample raw decoded values (Tempest `obs_st` fields) |
| `daily_aggregates` | `(day, sensor, metric)` | min/max/sum/count + min_ts/max_ts; updated incrementally |
| `monthly_aggregates` | `(year_month, sensor, metric)` | same shape, monthly bucket |

Mean = `sum_value / count`. The aggregator uses `INSERT OR IGNORE` on observations so duplicate `(sensor, metric, ts)` records don't double-count in the rollups. Future MQTT/Zigbee data drops into the same tables — no schema changes.

Inspect with the bundled CLI or plain `sqlite3`:

```sh
uv run tempest-stats                                    # current month, all metrics
uv run tempest-stats --month 2026-04                    # specific month
uv run tempest-stats --metric air_temp_c                # one metric
uv run tempest-stats --last-days 30 --metric air_temp_c # daily series
sqlite3 data/weather.db "SELECT * FROM monthly_aggregates LIMIT 10"
```

## Tests

The UDP collector has a full testing pyramid, with each level filterable by pytest marker:

| Marker | Tests | What it covers | Speed |
|---|---|---|---|
| `unit` | 29 | `JsonlWriter`, `TempestProtocol.datagram_received` (envelope, malformed-packet handling, dedupe), `decode_obs_st` (metric mapping, null slots, malformed payloads), and `Aggregator` (min/max/sum/count math, day & month boundaries, sensor isolation, idempotent dupes). No sockets. | <0.2s |
| `integration` | 5 | Real `asyncio` UDP endpoint on a free loopback port + real `JsonlWriter` writing to `tmp_path`, plus end-to-end through the SQLite aggregator. Sends datagrams via `socket.sendto` and asserts both file and DB contents. | <0.5s |
| `e2e` | 1 | Spawns `python -m home_weather_hub.tempest_listener` as a subprocess, sends a datagram, sends SIGINT, and asserts a clean exit, the `"shutting down"` log line, and a valid JSONL file. | ~1s |

Run them:

```sh
uv run pytest                # everything (35 tests, ~0.8s total)
uv run pytest -m unit        # fast feedback loop while editing the listener
uv run pytest -m integration # exercises the real asyncio + socket + sqlite path
uv run pytest -m e2e         # exercises the CLI end-to-end
```

## Lint & format

```sh
uv run ruff check .          # lint
uv run ruff check --fix .    # lint + autofix
uv run ruff format .         # format
```
