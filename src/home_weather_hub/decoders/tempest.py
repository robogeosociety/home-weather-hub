"""Decode Tempest UDP payloads into normalized (metric, value) pairs."""

from __future__ import annotations

# (obs[] index, metric name). Index 0 is the epoch timestamp; index 14 is the
# precipitation type enum (not aggregable as a scalar). See WeatherFlow UDP API:
# https://weatherflow.github.io/Tempest/api/udp.html
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


def decode_obs_st(payload: dict) -> tuple[str, int, list[tuple[str, float]]] | None:
    """Decode an `obs_st` Tempest packet.

    Returns `(sensor_id, ts, [(metric, value), ...])` or `None` if the payload
    is not an obs_st packet, the obs array is missing/empty, or the timestamp
    is unusable. Null sub-sensor slots are skipped silently.
    """
    if payload.get("type") != "obs_st":
        return None
    serial = payload.get("serial_number")
    if not isinstance(serial, str) or not serial:
        return None
    obs_lists = payload.get("obs")
    if not isinstance(obs_lists, list) or not obs_lists:
        return None
    obs = obs_lists[0]
    if not isinstance(obs, list) or not obs:
        return None
    ts = obs[0]
    if not isinstance(ts, int | float):
        return None
    ts_int = int(ts)
    metrics: list[tuple[str, float]] = []
    for idx, name in OBS_ST_METRICS:
        if idx >= len(obs):
            continue
        val = obs[idx]
        if val is None or not isinstance(val, int | float):
            continue
        metrics.append((name, float(val)))
    return f"tempest:{serial}", ts_int, metrics


def decode_evt_strike(payload: dict) -> tuple[str, int, float, int] | None:
    """Decode an `evt_strike` Tempest packet.

    Returns `(sensor_id, ts, distance_km, energy)` or `None` if the payload
    isn't an evt_strike or the `evt` array is the wrong shape. Note that the
    Tempest reports distance from the station and a unitless energy estimate
    only — there is no bearing, so individual strikes cannot be placed on a
    map without combining with the station's known location.
    """
    if payload.get("type") != "evt_strike":
        return None
    serial = payload.get("serial_number")
    if not isinstance(serial, str) or not serial:
        return None
    evt = payload.get("evt")
    if not isinstance(evt, list) or len(evt) < 3:
        return None
    ts, distance, energy = evt[0], evt[1], evt[2]
    if not isinstance(ts, int | float):
        return None
    if not isinstance(distance, int | float):
        return None
    if not isinstance(energy, int | float):
        return None
    return f"tempest:{serial}", int(ts), float(distance), int(energy)
