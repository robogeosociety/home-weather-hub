# home-weather-hub

Deployed dashboards · [grafana-local](https://github.com/tommyroar/home-weather-hub/deployments/grafana-local) · [grafana-tailnet](https://github.com/tommyroar/home-weather-hub/deployments/grafana-tailnet) · [influxdb-local](https://github.com/tommyroar/home-weather-hub/deployments/influxdb-local) · [influxdb-tailnet](https://github.com/tommyroar/home-weather-hub/deployments/influxdb-tailnet)

Live home-climate observability for Tommy's house. Outdoor weather (Tempest UDP) and indoor Zigbee climate flow into a self-hosted **InfluxDB** on a Mac Mini, are visualized in **Grafana**, and are reachable from the LAN and over **Tailscale**.

## Goal

Replace the original "build it from scratch" approach with **Home Assistant on a Raspberry Pi + InfluxDB + Grafana on the Mac Mini**:

- HA (running on a dedicated Pi running HAOS) is the universal capture layer for both outdoor weather and indoor Zigbee climate.
- The Mac Mini hosts the time-series store, the dashboards, and the network exposure.
- The custom Python listener and SQLite aggregator that started this repo are kept as a stopgap and as the canonical decoder reference, but they are no longer the data path of record.

## Current state

| Component | Status | Runs in | Notes |
|---|---|---|---|
| InfluxDB 2.7 (data store) | ✅ Live | OrbStack container, `/Volumes/dev/influxdb/` | Buckets: `tempest_archive`, `home_assistant`, `zigbee_archive`. Infinite retention. |
| Grafana 11.3 (dashboards) | ✅ Live | OrbStack container, `/Volumes/dev/grafana/` | Provisioned datasources + 7-panel `Tempest — Basic` dashboard (uid `tempest-basic`). |
| Tempest UDP → InfluxDB bridge | ✅ Live (stopgap) | Python via LaunchAgent, `~/.local/share/tempest-bridge/` | Mirrors what HA will do once it's up. Retire when HA takes over. |
| Daily InfluxDB backup | ✅ Live | LaunchAgent, 03:30 daily | 30-day retention to `/Volumes/dev/influxdb/backups/` |
| Tailscale exposure | ✅ Live | tailscale-serve, ports 3000 + 8086 | HTTPS terminated on the tailnet edge |
| Playwright validation | ✅ 5/5 pass | `infra/grafana/playwright/` | API + datasource + provisioning + data presence + browser render |
| Home Assistant on Raspberry Pi | ⏳ Flashing HAOS | (Pi) | WeatherFlow + Zigbee2MQTT integrations; pushes to `home_assistant` |
| Zigbee indoor sensor (SNZB-02WD) | ⚠️ Offline since 2026-05-17 | Will reattach via HA on Pi | Battery suspected; HA's Z2M add-on will own it |
| Webcam backdrop (stretch) | ⏳ Idea only | TBD | Lovelace picture-elements card or Grafana background |

Live data right now: Tempest `ST-00204728` writing one `obs_st` per 60s plus `rapid_wind` every 3s into `tempest_archive`. Battery ~2.63V — bottom third of healthy range, watch it.

## Access

| URL | Purpose |
|---|---|
| http://tommys-mac-mini.local:3001/d/tempest-basic | Grafana dashboard, LAN |
| https://tommys-mac-mini.tail59a169.ts.net:3000/d/tempest-basic | Grafana dashboard, Tailscale |
| http://tommys-mac-mini.local:8086/ | InfluxDB UI, LAN |
| https://tommys-mac-mini.tail59a169.ts.net:8086/ | InfluxDB UI, Tailscale |
| https://github.com/tommyroar/home-weather-hub/deployments | All four as clickable GitHub deployments |

Credentials live in three chmod-600 `.env` files on the host (`/Volumes/dev/influxdb/.env`, `/Volumes/dev/grafana/.env`, `~/.local/share/tempest-bridge/.env`). They're gitignored. See [`infra/README.md`](infra/README.md) for layout, `.env.example` files, and reproducible setup from a clean machine.

## Repo layout

```
home-weather-hub/
├── src/home_weather_hub/   # Original Python: Tempest decoder, listener,
│                           # SQLite aggregator, CLIs. The decoder still
│                           # drives the running bridge.
├── tests/                  # pytest suite for the Python module
├── infra/                  # Snapshot of the OrbStack + LaunchAgent +
│                           # Playwright config running on tommys-mac-mini
└── pyproject.toml          # uv-managed Python project
```

## Migration plan

1. **Now** — Mac Mini hosts InfluxDB + Grafana; Python bridge fills `tempest_archive`. HAOS being flashed onto the Pi.
2. **Next** — HA on the Pi listens for the same Tempest UDP broadcasts; HA's InfluxDB integration pushes entity states to `home_assistant`. Optionally route Zigbee entities to `zigbee_archive` via include filters in HA.
3. **Then** — Decommission the Mac-side Python bridge (`launchctl bootout` + remove `~/.local/share/tempest-bridge/`). Add a third Grafana datasource for `zigbee_archive`, grow dashboards.
4. **Stretch** — Webcam co-sited with the Tempest, rendered as a Lovelace card backdrop in HA or embedded in Grafana.

## Working with the Python module

The Tempest decoder (`src/home_weather_hub/decoders/tempest.py`) is the canonical reference for `obs_st` and `evt_strike` payload shapes — the live bridge in `infra/tempest-bridge/tempest_to_influx.py` mirrors its logic. The SQLite aggregator under `src/home_weather_hub/storage/` is no longer the data path of record; observations flow into InfluxDB now. The CLIs (`tempest-listener`, `tempest-stats`, `tempest-monitor`) still build and run but are not part of the current pipeline.

```sh
uv sync                       # install runtime + dev deps
uv run pytest                 # 54 tests, ~1s total
uv run ruff check .           # lint
uv run ruff format .          # format
```

### Tests

| Marker | Tests | Speed | What it covers |
|---|---|---|---|
| `unit` | 47 | <0.2s | `JsonlWriter`, `TempestProtocol.datagram_received` (envelope, dedupe), decoders, `Aggregator` math + idempotency, config loader |
| `integration` | 6 | <0.5s | Real asyncio UDP endpoint, real `JsonlWriter`, end-to-end through the SQLite aggregator (with and without DB sink) |
| `e2e` | 1 | ~1s | `python -m home_weather_hub.tempest_listener` subprocess + SIGINT clean shutdown |

```sh
uv run pytest -m unit         # fast feedback while editing the decoder
uv run pytest -m integration  # real socket + sqlite path
uv run pytest -m e2e          # CLI end-to-end
```
