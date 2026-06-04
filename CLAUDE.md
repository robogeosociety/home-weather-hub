# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Live local-network climate dashboard for Tommy's home. Three data planes feed one web app:

- **Outside weather** — [Tempest](https://shop.tempest.earth/products/tempest) station broadcasts UDP packets on the LAN. Listener must bind to the broadcast port and decode Tempest's JSON message types (e.g. `obs_st`, `rapid_wind`, `evt_strike`).
- **Inside climate** — Zigbee sensors publish to a local MQTT broker. Subscriber consumes those topics.
- **Dashboard** — Containerized web app served from a Mac Mini M1 on the local network. Stretch: live webcam co-sited with the Tempest as the dashboard background.

The deployment target (Mac Mini M1, LAN-only, Apple Silicon container runtime) shapes most architectural choices — keep images `linux/arm64`-compatible and prefer OrbStack-friendly compose setups over anything that assumes cloud infra.

## Stack

- **Python 3.12+** managed by **`uv`** for the ingest side (UDP listener, MQTT subscriber, eventually the dashboard backend). Single src-layout package: `src/home_weather_hub/`.
- The dashboard frontend is not yet built; if/when added it will likely be Vite (the gitignore is already Vite-flavored).
- Captured raw data lands in `./data/*.jsonl` (gitignored), one packet per line, daily-rotated. Decoded `obs_st` values also flow into a SQLite store at `./data/weather.db` (see below).

## Storage architecture

Two parallel sinks. JSONL is the immutable audit/replay corpus; SQLite is the query surface for the dashboard.

- **JSONL** (`data/tempest-YYYY-MM-DD.jsonl`) — raw packets wrapped in `{received_at, src_addr, payload}`. Captures everything (`obs_st`, `rapid_wind`, `hub_status`, `device_status`, events). Replayable.
- **SQLite WAL** (`data/weather.db`) — four tables, all keyed on a sensor-agnostic `(sensor_id, metric)` schema so future Zigbee/MQTT data drops in without migrations:
  - `sensors` — catalog (`tempest:<serial>`, `snzb:<ieee>`); kind, label, location, latitude, longitude, first/last seen. Lat/lng comes from the host-local `config/stations.toml` (gitignored), seeded once at listener startup. Per-packet writes use `COALESCE` so they never overwrite seeded metadata.
  - `observations` — one row per `(sensor_id, metric, ts)`. Currently only `obs_st` decoded fields (14 metrics: wind lull/avg/gust/dir, pressure, air_temp_c, humidity_pct, illuminance_lux, uv_index, solar_w_m2, rain_mm, lightning_avg_km, lightning_count, battery_v).
  - `daily_aggregates` and `monthly_aggregates` — `(min_value, max_value, sum_value, count, min_ts, max_ts)` per `(bucket, sensor, metric)`. Updated incrementally via `INSERT...ON CONFLICT DO UPDATE` on every `obs_st` packet, inside a single transaction. Mean is `sum_value / count`.
  - `lightning_strikes` — one row per `evt_strike` packet (`ts, sensor_id, distance_km, energy`), idempotent on `(sensor_id, ts)`. Tempest reports distance from the station and a unitless energy estimate only — **no bearing**, so individual strikes can't be placed on a map; the dashboard reads the `strikes_with_location` view (joins to `sensors.latitude/longitude`) to render each strike as a circle of radius `distance_km` around the station. The `obs_st.lightning_count` / `lightning_avg_km` minute aggregates also still flow into the rollup tables.

The aggregator skips rollup updates when `INSERT OR IGNORE` on `observations` reports `rowcount == 0`, so duplicate-keyed records don't double-count. `rapid_wind` and `evt_precip` packets stay JSONL-only. Disable the SQLite sink with `--no-db` for replay or capture-only runs.

Inspect via `uv run tempest-stats [--month YYYY-MM | --last-days N] [--metric ...] [--sensor ...]` or directly with `sqlite3 data/weather.db`.

## Tempest UDP listener

`src/home_weather_hub/tempest_listener.py` — `asyncio.DatagramProtocol` bound to `0.0.0.0:50222` with `SO_REUSEADDR`/`SO_REUSEPORT`/`SO_BROADCAST`. Each datagram is JSON-decoded, wrapped with `{received_at, src_addr, payload}`, and appended to `data/tempest-<UTC-date>.jsonl`. Malformed packets log a WARNING with hex preview and are dropped, not crashed-on. SIGINT/SIGTERM trigger a clean drain + close.

Run it:

```sh
uv sync                              # first time only
uv run tempest-listener              # writes JSONL + ./data/weather.db
uv run tempest-listener --no-db      # skip the aggregate DB
uv run tempest-listener --port 50222 --data-dir ./data --db-path ./data/weather.db
```

The Tempest hub on Tommy's LAN is at **192.168.4.20** (`HB-00208576`). The hub broadcasts `hub_status` every ~10s regardless of device state. If `obs_st` (60s) and `rapid_wind` (3s) are absent, **the Tempest device itself isn't transmitting** — check the WeatherFlow app for battery/radio link before assuming a listener bug.

Smoke test without the listener (handy when debugging the network path):

```sh
nc -ul 50222              # macOS BSD nc; prints raw JSON if anything is broadcasting
sudo tcpdump -i en0 -nn -A 'udp port 50222'
```

## Workspace conventions (inherited from `~/dev/CLAUDE.md`)

These apply to every project under `~/dev` and are easy to forget when scaffolding:

- **Dev servers** — Use the global `/dev` skill to start servers (it detects the stack and registers a GitHub Deployment). Use `/tailscale-serve <port>` to expose a port over the tailnet.
- **Vite port registry** — If a Vite config is added, pick the next free port from `~/.claude/vite-ports.json` (range 5180–5199), record it there, and set both `server.port` and `server.strictPort: true`. Never kill a process on a port you didn't start.
- **Long-running services vs Nomad** — The dashboard web server, MQTT subscriber, and UDP listener are services → run them as **OrbStack containers** on the Mac Mini, not Nomad jobs. Nomad in this workspace is reserved for scheduled production jobs with lifecycle hooks (see `~/dev/NOMAD.md`).
## Pull requests — the "newspaper" framework

PR descriptions follow the **newspaper / information-pyramid** format: one self-contained
front page (kicker → headline → dek → masthead → why → what → mermaid flow → screens →
verification → risk) that reads top-to-bottom on an iPad-mini portrait display (1–2 pages;
up to 4 for very complex *code* changes). Rebuild from the **full** diff, never append.
Full rules: <https://github.com/tommyroar/.github/blob/main/PR_FRAMEWORK.md>. CI validates
the body via the `pr-newspaper` workflow (the reusable gate in `tommyroar/pr-newspaper`).
