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
| Typed Tempest decoder (Pydantic v2 models) | ✅ Implemented — `src/home_weather_hub/tempest_decode.py` |
| `tempest-listener` and `tempest-monitor` CLIs | ✅ Implemented |
| In-process event bus (UDP → WebSocket fan-out) | ✅ Implemented — `src/home_weather_hub/event_bus.py` |
| JSONL store (snapshot / history / strikes / layout) | ✅ Implemented — `src/home_weather_hub/store.py` |
| FastAPI dashboard API + WebSocket (`dashboard-api` CLI) | ✅ Implemented — `src/home_weather_hub/dashboard_api.py` |
| React dashboard (vintage Weather Channel UI) | ✅ Implemented — `web/` (Vite + React 19 + TS, port 5189) |
| Test pyramid (unit / integration / e2e) | ✅ 63 tests, all passing |
| Lint + format (`ruff`) | ✅ Configured |
| Zigbee/MQTT subscriber for indoor sensors | ⏳ Not started |
| `?tv=1` Local-on-the-8s scene cycle (Phase 2) | ⏳ Placeholder only |
| Containerized deployment to Mac Mini M1 | ⏳ Not started |
| Webcam backdrop (stretch) | ⏳ Not started |

**Known field issue (2026-05-02):** the Tempest hub at `192.168.4.20` is healthy and broadcasting `hub_status` every ~10s, but the outdoor device itself isn't transmitting (`obs_st`/`rapid_wind`/`device_status` absent). Likely battery or sub-GHz radio link — needs checking in the WeatherFlow app before useful sample data can be collected.

## Quick start

```sh
uv sync                              # install runtime + dev deps
uv run tempest-listener              # bind 0.0.0.0:50222, write ./data/tempest-<UTC-date>.jsonl
uv run tempest-listener --port 50222 --data-dir ./data --log-level INFO
```

Stop with `Ctrl-C`; SIGINT/SIGTERM trigger a clean drain + close. Captured packets land in `./data/*.jsonl` (gitignored), one record per line, each wrapped as `{received_at, src_addr, payload}`.

## Dashboard

Two processes during dev — backend on `:8770`, Vite frontend on `:5189` (proxies `/api` and `/ws` to the backend):

```sh
# terminal 1 — combined UDP listener + REST/WS API
uv run dashboard-api                           # binds UDP 50222 + HTTP :8770
uv run dashboard-api --no-udp                  # API only (run when listener is in another process)

# terminal 2 — frontend
cd web && npm install && npm run dev           # http://localhost:5189
```

URL flags:
- `?darkmode=true|false` — overrides the persisted theme (vintage cobalt vs. parchment-and-ink)
- `?tv=1` — kiosk mode, ignores saved layout (Phase 2 fully replaces with a Local-on-the-8s scene cycle)

Set the station coordinates via env vars so the lightning map centers correctly:

```sh
export STATION_LAT=47.6062
export STATION_LNG=-122.3321
export STATION_NAME="Tempest Station"
```

Tap the **LAYOUT** button in the toolbar to enter WYSIWYG edit mode — drag/resize widgets on the cyan grid, swap between `NUM` and `GRAPH` per widget, pick `current/min/max/mean` per metric. Changes persist server-side to `data/layout.json` (so the iPad and TV share the same layout).

Dev-only: in edit mode, the **TEST STRIKE** button injects a synthetic lightning strike so the strike map is demoable before a real storm.

Production build (single-process, served by the same uvicorn that serves the API):

```sh
cd web && npm run build && cd ..
uv run dashboard-api --static-dir web/dist     # serves the SPA at /
```

## Tests

The UDP collector has a full testing pyramid, with each level filterable by pytest marker:

| Marker | Tests | What it covers | Speed |
|---|---|---|---|
| `unit` | 10 | `JsonlWriter` (rotation, flush, idempotent close, dir creation) and `TempestProtocol.datagram_received` (envelope, malformed-packet handling, recovery). No sockets. | <0.1s |
| `integration` | 2 | Real `asyncio` UDP endpoint on a free loopback port + real `JsonlWriter` writing to `tmp_path`. Sends datagrams via `socket.sendto` and asserts the file contents. | <0.3s |
| `e2e` | 1 | Spawns `python -m home_weather_hub.tempest_listener` as a subprocess, sends a datagram, sends SIGINT, and asserts a clean exit, the `"shutting down"` log line, and a valid JSONL file. | ~1s |

Run them:

```sh
uv run pytest                # everything (13 tests, ~0.5s total)
uv run pytest -m unit        # fast feedback loop while editing the listener
uv run pytest -m integration # exercises the real asyncio + socket path
uv run pytest -m e2e         # exercises the CLI end-to-end
```

## Lint & format

```sh
uv run ruff check .          # lint
uv run ruff check --fix .    # lint + autofix
uv run ruff format .         # format
```
