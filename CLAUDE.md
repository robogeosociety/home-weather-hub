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
- Captured raw data lands in `./data/*.jsonl` (gitignored), one packet per line, daily-rotated.

## Tempest UDP listener

`src/home_weather_hub/tempest_listener.py` — `asyncio.DatagramProtocol` bound to `0.0.0.0:50222` with `SO_REUSEADDR`/`SO_REUSEPORT`/`SO_BROADCAST`. Each datagram is JSON-decoded, wrapped with `{received_at, src_addr, payload}`, and appended to `data/tempest-<UTC-date>.jsonl`. Malformed packets log a WARNING with hex preview and are dropped, not crashed-on. SIGINT/SIGTERM trigger a clean drain + close.

Run it:

```sh
uv sync                              # first time only
uv run tempest-listener              # writes to ./data
uv run tempest-listener --port 50222 --data-dir ./data --log-level INFO
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
