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
| Zigbee/MQTT subscriber for indoor sensors (SNZB-02WD) | ✅ Implemented — `src/home_weather_hub/zigbee_subscriber.py` + `docker-compose.yml` (Mosquitto + Z2M) |
| Dashboard web app | ⏳ Not started |
| Containerized deployment to Mac Mini M1 | ⏳ Not started |
| Webcam backdrop (stretch) | ⏳ Not started |

**Known field issue (2026-05-02):** the Tempest hub at `192.168.4.20` is healthy and broadcasting `hub_status` every ~10s, but the outdoor device itself isn't transmitting (`obs_st`/`rapid_wind`/`device_status` absent). Likely battery or sub-GHz radio link — needs checking in the WeatherFlow app before useful sample data can be collected.

## Quick start

```sh
uv sync                                                 # install runtime + dev deps
ZIGBEE_ADAPTER_PATH=/dev/cu.usbserial-220 \
    scripts/install-native.sh                           # one-shot setup of all services
```

The installer is idempotent and brings up every collector as a managed service:

| Service | Managed by |
|---|---|
| `mosquitto` (MQTT broker on 1883/9001) | `brew services` |
| `com.zigbee2mqtt` (native Node, frontend on 127.0.0.1:8088) | launchd agent |
| `com.home-weather-hub.zigbee-subscriber` (indoor ingest) | launchd agent |
| `com.home-weather-hub.tempest-listener` (outdoor UDP ingest) | launchd agent |

For ad-hoc work the listeners can also run by hand:

```sh
uv run tempest-listener              # bind 0.0.0.0:50222, write JSONL + SQLite to ./data/
uv run tempest-listener --no-db      # JSONL only
uv run zigbee-subscriber             # ingests from the local broker
```

Stop with `Ctrl-C`; SIGINT/SIGTERM trigger a clean drain + close. Each `obs_st` packet is JSONL-appended **and** decoded into the SQLite aggregate store; raw packets land in `./data/*.jsonl` (gitignored), one record per line as `{received_at, src_addr, payload}`.

## Indoor climate (Zigbee → MQTT → SQLite)

Indoor sensors (Sonoff SNZB-02WD and friends) talk Zigbee to a **Sonoff ZBDongle-E** (Silicon Labs CP210x; vid:pid `10c4:ea60`). The dongle is bridged to MQTT by **Zigbee2MQTT** (native Node, not containerised — Docker on macOS can't pass through host `/dev/cu.*` ttys). The Python `zigbee-subscriber` consumes those MQTT topics and lands data in the same JSONL + SQLite sinks the Tempest path uses.

Three pieces, all managed as services on macOS:

| Service | What | Managed by |
|---|---|---|
| `mosquitto` | MQTT broker on `:1883` (TCP) + `:9001` (WebSocket) | `brew services` |
| `com.zigbee2mqtt` | native Z2M with frontend on `127.0.0.1:8088` | launchd agent |
| `com.home-weather-hub.zigbee-subscriber` | the Python subscriber | launchd agent |

### One-shot install

```sh
# Plug the ZBDongle-E in first
ZIGBEE_ADAPTER_PATH=/dev/cu.usbserial-220 scripts/install-zigbee-native.sh
```

The installer is idempotent — it `brew install`s `node@24` + `mosquitto`, clones+builds Zigbee2MQTT to `~/zigbee2mqtt`, drops a starter `configuration.yaml`, templates the launchd plists in `scripts/launchd/` with the local `$HOME` / repo path, and bootstraps both agents. Re-running is safe; it'll only redo the steps that aren't already in the desired state.

### Operational commands

```sh
brew services list                                            # mosquitto status
launchctl list | grep -E 'zigbee|home-weather'                # agent status (- pid label)
tail -f ~/zigbee2mqtt/data/launchd.log                        # Z2M log
tail -f data/zigbee-subscriber.launchd.log                    # subscriber log
launchctl bootout gui/$UID ~/Library/LaunchAgents/com.zigbee2mqtt.plist               # stop Z2M
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.zigbee2mqtt.plist             # start Z2M
```

### Pairing a new sensor

Open `http://127.0.0.1:8088` (or expose it over the tailnet with `tailscale serve --bg --https=8088 http://127.0.0.1:8088`), toggle "Permit join" on, factory-reset the device. Or skip the UI entirely and use the Z2M MQTT API:

```sh
mosquitto_pub -t zigbee2mqtt/bridge/request/permit_join -m '{"value":true,"time":254}'
mosquitto_pub -t zigbee2mqtt/bridge/request/device/rename \
  -m '{"from":"0xa4c138aabbccdd","to":"indoors"}'
```

JSONL files rotate daily as `data/zigbee-YYYY-MM-DD.jsonl` (envelope: `{received_at, topic, friendly_name, sensor_id, payload}`); decoded numeric fields land in `observations` and the daily/monthly rollups keyed by `sensor_id = snzb:<ieee_address>`. Renaming a device does **not** change the sensor_id, so historical data survives renames.

Field mapping (Z2M payload → schema metric):

| Z2M field | Metric | Notes |
|---|---|---|
| `temperature` | `air_temp_c` | shares an axis with the Tempest reading |
| `humidity` | `humidity_pct` | |
| `battery` | `battery_pct` | |
| `voltage` | `battery_v` | converted from mV |
| `linkquality` | `link_quality` | 0–255 |

### Running the subscriber by hand

The launchd agent is the supported path, but for ad-hoc work:

```sh
uv run zigbee-subscriber                              # default 127.0.0.1:1883
uv run zigbee-subscriber --broker-host 192.168.4.10   # remote broker
uv run zigbee-subscriber --no-db                      # JSONL only
```

## Aggregate storage

`data/weather.db` (SQLite, WAL mode) holds everything the dashboard will query. Schema:

| Table | Grain | Purpose |
|---|---|---|
| `sensors` | one row per device | sensor catalog (`tempest:<serial>`, `snzb:<ieee>`, …) — first/last seen, location |
| `observations` | one row per `(sensor, metric, ts)` | per-sample raw decoded values (Tempest `obs_st` fields) |
| `daily_aggregates` | `(day, sensor, metric)` | min/max/sum/count + min_ts/max_ts; updated incrementally |
| `monthly_aggregates` | `(year_month, sensor, metric)` | same shape, monthly bucket |
| `lightning_strikes` | one row per `evt_strike` packet | per-strike `distance_km` (from station — Tempest reports no bearing) and unitless `energy` |
| `strikes_with_location` (view) | per strike, joined to sensor lat/lng | what the dashboard reads to render strikes as a circle around the station |

Mean = `sum_value / count`. The aggregator uses `INSERT OR IGNORE` on observations so duplicate `(sensor, metric, ts)` records don't double-count in the rollups. Strikes are idempotent on `(sensor_id, ts)`. Future MQTT/Zigbee data drops into the same tables — no schema changes.

### Station config (lat/lng)

Per-host station metadata lives in `config/stations.toml` (gitignored — copy from `config/stations.example.toml`). The listener reads it at startup and seeds the `sensors` table; per-packet writes use `COALESCE` so they never clobber the seeded label/location/lat/lng.

```toml
# config/stations.toml
[[stations]]
sensor_id = "tempest:ST-00027770"
kind      = "tempest"
label     = "Backyard Tempest"
location  = "outside"
latitude  = 47.6062
longitude = -122.3321
```

The Tempest itself reports strike distance only (no bearing), so the station's known coordinates are the only spatial anchor — they let the dashboard render a strike as `(station_lat, station_lng) ± distance_km`. Pass `--stations <path>` to the listener to override.

Inspect with the bundled CLI or plain `sqlite3`:

```sh
uv run tempest-stats                                    # current month, all metrics
uv run tempest-stats --month 2026-04                    # specific month
uv run tempest-stats --metric air_temp_c                # one metric
uv run tempest-stats --last-days 30 --metric air_temp_c # daily series
uv run tempest-stats --strikes                          # all individual strikes (newest first)
uv run tempest-stats --strikes --last-days 7            # strikes in the last week
sqlite3 data/weather.db "SELECT * FROM monthly_aggregates LIMIT 10"
```

## Tests

The UDP collector has a full testing pyramid, with each level filterable by pytest marker:

| Marker | Tests | What it covers | Speed |
|---|---|---|---|
| `unit` | 65 | Tempest path (`JsonlWriter`, `TempestProtocol.datagram_received`, `decode_obs_st`, `Aggregator`) + Zigbee path (`decode_payload`, `decode_bridge_devices`, `MessageRouter` topic routing / catalog fallback / station overrides / `last_seen` handling). No sockets. | <0.3s |
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
