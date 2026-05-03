"""Decode Zigbee2MQTT JSON payloads into normalized (metric, value) pairs.

Z2M publishes per-device messages on `zigbee2mqtt/<friendly_name>` with a
JSON body whose keys depend on the device's exposed clusters. For a Sonoff
SNZB-02 / SNZB-02WD temp+humidity sensor a typical payload looks like::

    {
        "battery": 96,         # %
        "humidity": 45.2,      # %
        "linkquality": 78,     # 0..255
        "temperature": 22.4,   # °C
        "voltage": 3000        # mV
    }

We map those onto the same metric names the Tempest decoder uses where
possible (`air_temp_c`, `humidity_pct`, `battery_v`) so the dashboard can
plot indoor and outdoor temperature on the same axis without re-keying.
"""

from __future__ import annotations

from collections.abc import Callable

_Converter = Callable[[float], float]

# Z2M payload key -> (metric name, unit-converter). Only numeric, scalar,
# directly-aggregable fields are mapped. Non-numeric fields (action, state,
# update_available, ...) are intentionally skipped.
_FIELD_MAP: tuple[tuple[str, str, _Converter], ...] = (
    ("temperature", "air_temp_c", float),
    ("humidity", "humidity_pct", float),
    ("battery", "battery_pct", float),
    # Z2M reports voltage in mV; the existing schema uses volts.
    ("voltage", "battery_v", lambda v: float(v) / 1000.0),
    ("linkquality", "link_quality", float),
    ("pressure", "pressure_mb", float),
    ("illuminance_lux", "illuminance_lux", float),
)


def decode_payload(payload: dict) -> list[tuple[str, float]]:
    """Decode a single Z2M device message into [(metric, value), ...].

    Returns an empty list if no recognised fields are present (e.g. a
    keep-alive that only carries `last_seen`). Silently skips fields that
    aren't numbers — Z2M occasionally emits `null` or string enums for
    device-specific keys we don't care about.
    """
    if not isinstance(payload, dict):
        return []
    out: list[tuple[str, float]] = []
    for src_key, metric, convert in _FIELD_MAP:
        if src_key not in payload:
            continue
        raw = payload[src_key]
        if raw is None or isinstance(raw, bool) or not isinstance(raw, int | float):
            continue
        out.append((metric, convert(raw)))
    return out


def decode_bridge_devices(payload: object) -> dict[str, str]:
    """Build a friendly_name -> ieee_address map from `bridge/devices`.

    Z2M publishes the full device catalogue as a retained message on
    `zigbee2mqtt/bridge/devices` whenever it changes. We use it to resolve
    the per-device topic (which uses `friendly_name`) back to a stable
    `snzb:<ieee>` sensor_id.

    Skips the Coordinator entry and any device missing an ieee_address.
    """
    if not isinstance(payload, list):
        return {}
    out: dict[str, str] = {}
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "Coordinator":
            continue
        ieee = entry.get("ieee_address")
        name = entry.get("friendly_name")
        if not isinstance(ieee, str) or not ieee:
            continue
        if not isinstance(name, str) or not name:
            continue
        out[name] = ieee
    return out
