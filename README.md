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
| Test pyramid (unit / integration / e2e) | ✅ 13 tests, all passing |
| Lint + format (`ruff`) | ✅ Configured |
| Zigbee/MQTT subscriber for indoor sensors | ⏳ Not started |
| Dashboard web app | ⏳ Not started |
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
