#!/usr/bin/env python3
"""UDP-to-InfluxDB bridge for the Tempest hub.

Binds 0.0.0.0:50222, decodes obs_st / evt_strike / rapid_wind packets,
and writes line protocol to the tempest_archive bucket. Stdlib only —
no external dependencies, so it can run via the system python3 without uv.

Run:
    INFLUX_URL=http://localhost:8086 \\
    INFLUX_ORG=home INFLUX_BUCKET=tempest_archive \\
    INFLUX_TOKEN=$INFLUX_TEMPEST_TOKEN \\
    python3 tempest_to_influx.py
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import socket
import sys
import urllib.error
import urllib.request

# obs_st field decoder (matches src/home_weather_hub/decoders/tempest.py)
OBS_ST_METRICS: tuple[tuple[int, str], ...] = (
    (1, "wind_lull_mps"),
    (2, "wind_avg_mps"),
    (3, "wind_gust_mps"),
    (4, "wind_dir_deg"),
    (6, "pressure_mb"),
    (7, "air_temp_c"),
    (8, "humidity_pct"),
    (9, "illuminance_lux"),
    (10, "uv_index"),
    (11, "solar_w_m2"),
    (12, "rain_mm"),
    (13, "lightning_avg_km"),
    (15, "lightning_count"),
    (16, "battery_v"),
)

log = logging.getLogger("tempest_to_influx")


def _esc_tag(s: str) -> str:
    return s.replace(",", r"\,").replace(" ", r"\ ").replace("=", r"\=")


def _field_kv(name: str, val: float) -> str:
    # InfluxDB line protocol — floats need no suffix; ints would need 'i'.
    return f"{name}={val}"


def decode_obs_st(payload: dict) -> list[str]:
    """Return a list of line-protocol records for an obs_st packet."""
    if payload.get("type") != "obs_st":
        return []
    serial = payload.get("serial_number")
    hub = payload.get("hub_sn") or ""
    obs_lists = payload.get("obs")
    if not isinstance(serial, str) or not isinstance(obs_lists, list):
        return []
    sensor = f"tempest:{serial}"
    tags = f"sensor_id={_esc_tag(sensor)}"
    if hub:
        tags += f",hub={_esc_tag(hub)}"
    lines: list[str] = []
    for obs in obs_lists:
        if not isinstance(obs, list) or not obs:
            continue
        ts = obs[0]
        if not isinstance(ts, (int, float)):
            continue
        fields: list[str] = []
        for idx, name in OBS_ST_METRICS:
            if idx >= len(obs):
                continue
            v = obs[idx]
            if v is None or not isinstance(v, (int, float)):
                continue
            fields.append(_field_kv(name, float(v)))
        if not fields:
            continue
        lines.append(f"weather,{tags} {','.join(fields)} {int(ts)}")
    return lines


def decode_evt_strike(payload: dict) -> list[str]:
    if payload.get("type") != "evt_strike":
        return []
    serial = payload.get("serial_number")
    evt = payload.get("evt")
    if not isinstance(serial, str) or not isinstance(evt, list) or len(evt) < 3:
        return []
    ts, distance, energy = evt[0], evt[1], evt[2]
    if not all(isinstance(x, (int, float)) for x in (ts, distance, energy)):
        return []
    tags = f"sensor_id={_esc_tag(f'tempest:{serial}')}"
    return [
        f"lightning_strike,{tags} distance_km={float(distance)},energy={int(energy)}i {int(ts)}"
    ]


def decode_rapid_wind(payload: dict) -> list[str]:
    if payload.get("type") != "rapid_wind":
        return []
    serial = payload.get("serial_number")
    ob = payload.get("ob")
    if not isinstance(serial, str) or not isinstance(ob, list) or len(ob) < 3:
        return []
    ts, speed, direction = ob[0], ob[1], ob[2]
    if not all(isinstance(x, (int, float)) for x in (ts, speed, direction)):
        return []
    tags = f"sensor_id={_esc_tag(f'tempest:{serial}')}"
    return [
        f"wind_rapid,{tags} wind_avg_mps={float(speed)},wind_dir_deg={float(direction)} {int(ts)}"
    ]


DECODERS = (decode_obs_st, decode_evt_strike, decode_rapid_wind)


def write_lines(url: str, org: str, bucket: str, token: str, lines: list[str]) -> None:
    body = "\n".join(lines).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/api/v2/write?org={org}&bucket={bucket}&precision=s",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 204):
                log.warning("influx write returned %s", resp.status)
    except urllib.error.HTTPError as e:
        log.error("influx HTTPError %s: %s", e.code, e.read().decode("utf-8", "replace"))
    except OSError as e:
        log.error("influx write failed: %s", e)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    url = os.environ.get("INFLUX_URL", "http://localhost:8086")
    org = os.environ["INFLUX_ORG"]
    bucket = os.environ["INFLUX_BUCKET"]
    token = os.environ["INFLUX_TOKEN"]
    port = int(os.environ.get("UDP_PORT", "50222"))

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    with contextlib.suppress(OSError):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("0.0.0.0", port))

    stop = False

    def _sig(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    log.info("listening on UDP 0.0.0.0:%s → %s/%s", port, url, bucket)
    counts: dict[str, int] = {}
    s.settimeout(1.0)
    while not stop:
        try:
            data, addr = s.recvfrom(65535)
        except TimeoutError:
            continue
        try:
            payload = json.loads(data)
        except Exception as e:
            log.warning("undecodable from %s: %s (%d bytes)", addr, e, len(data))
            continue
        ptype = payload.get("type", "?")
        counts[ptype] = counts.get(ptype, 0) + 1
        lines: list[str] = []
        for dec in DECODERS:
            lines.extend(dec(payload))
        if lines:
            write_lines(url, org, bucket, token, lines)
        if counts.get(ptype, 0) in (1, 5, 25, 100) or counts.get(ptype, 0) % 50 == 0:
            log.info("counts: %s", counts)

    log.info("shutting down. final counts: %s", counts)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
