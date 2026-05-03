"""Decode Tempest UDP payloads into typed Pydantic models.

The listener writes raw JSONL; this module is the single source of truth for
turning those payloads into named fields. Both the CLI monitor and the
dashboard API import from here, so the wire format has one schema.

The Tempest UDP API is array-positional (`obs`, `ob`, `evt`); positions and
units are derived from observed traffic and the WeatherFlow public docs.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

# ---- unit conversions (also used by the API for synthesized fields) ---------


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def mps_to_mph(mps: float) -> float:
    return mps * 2.23694


def mm_to_in(mm: float) -> float:
    return mm / 25.4


def km_to_mi(km: float) -> float:
    return km * 0.621371


def format_uptime(seconds: int) -> str:
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


# ---- models -----------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class DecodedObsSt(_Base):
    """Station observation. Cadence ~60s.

    Field positions reflect the WeatherFlow Tempest UDP API obs_st spec.
    """

    type: Literal["obs_st"] = "obs_st"
    time_epoch: int | None = None
    wind_lull_mps: float | None = None
    wind_avg_mps: float | None = None
    wind_gust_mps: float | None = None
    wind_direction_deg: float | None = None
    wind_sample_interval_sec: int | None = None
    pressure_mb: float | None = None
    air_temp_c: float | None = None
    relative_humidity_pct: float | None = None
    illuminance_lux: float | None = None
    uv_index: float | None = None
    solar_radiation_w_m2: float | None = None
    rain_accumulated_mm: float | None = None
    precipitation_type: int | None = None
    lightning_strike_avg_distance_km: float | None = None
    lightning_strike_count: int | None = None
    battery_voltage: float | None = None
    report_interval_minutes: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def air_temp_f(self) -> float | None:
        return c_to_f(self.air_temp_c) if self.air_temp_c is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wind_avg_mph(self) -> float | None:
        return mps_to_mph(self.wind_avg_mps) if self.wind_avg_mps is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wind_gust_mph(self) -> float | None:
        return mps_to_mph(self.wind_gust_mps) if self.wind_gust_mps is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rain_accumulated_in(self) -> float | None:
        return mm_to_in(self.rain_accumulated_mm) if self.rain_accumulated_mm is not None else None

    def format_oneline(self) -> str:
        if self.air_temp_c is None or self.wind_avg_mps is None:
            return "obs_st (incomplete observation)"
        return (
            "obs_st  "
            f"temp={c_to_f(self.air_temp_c):.1f}°F ({self.air_temp_c:.1f}°C)  "
            f"rh={self.relative_humidity_pct:.0f}%  "
            f"wind={mps_to_mph(self.wind_avg_mps):.1f} mph "
            f"@{self.wind_direction_deg:.0f}°  "
            f"gust={mps_to_mph(self.wind_gust_mps):.1f} mph  "
            f"press={self.pressure_mb:.1f} mb  "
            f"rain={mm_to_in(self.rain_accumulated_mm):.3f} in/min  "
            f"lux={self.illuminance_lux:.0f}  "
            f"uv={self.uv_index:.1f}  "
            f"bat={self.battery_voltage:.2f}V"
        )


class DecodedRapidWind(_Base):
    """Wind sample. Cadence ~3s."""

    type: Literal["rapid_wind"] = "rapid_wind"
    time_epoch: int | None = None
    wind_speed_mps: float | None = None
    wind_direction_deg: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wind_speed_mph(self) -> float | None:
        return mps_to_mph(self.wind_speed_mps) if self.wind_speed_mps is not None else None

    def format_oneline(self) -> str:
        if self.wind_speed_mps is None or self.wind_direction_deg is None:
            return "rapid_wind (incomplete sample)"
        return (
            f"rapid_wind  {mps_to_mph(self.wind_speed_mps):.1f} mph @{self.wind_direction_deg:.0f}°"
        )


class DecodedEvtStrike(_Base):
    """Lightning strike event. Bearing is unknown — distance only."""

    type: Literal["evt_strike"] = "evt_strike"
    time_epoch: int | None = None
    distance_km: float | None = None
    energy: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def distance_mi(self) -> float | None:
        return km_to_mi(self.distance_km) if self.distance_km is not None else None

    def format_oneline(self) -> str:
        return f"evt_strike  distance={self.distance_km} km  energy={self.energy}"


class DecodedEvtPrecip(_Base):
    """Precipitation start event."""

    type: Literal["evt_precip"] = "evt_precip"
    time_epoch: int | None = None

    def format_oneline(self) -> str:
        return "evt_precip  rain detected"


class DecodedHubStatus(_Base):
    type: Literal["hub_status"] = "hub_status"
    serial_number: str | None = None
    firmware_revision: str | None = None
    uptime: int | None = None
    rssi: int | None = None
    seq: int | None = None
    timestamp: int | None = None

    def format_oneline(self) -> str:
        return (
            "hub_status     "
            f"uptime={format_uptime(self.uptime or 0)}  "
            f"rssi={self.rssi if self.rssi is not None else '?'} dBm  "
            f"seq={self.seq if self.seq is not None else '?'}"
        )


class DecodedDeviceStatus(_Base):
    type: Literal["device_status"] = "device_status"
    serial_number: str | None = None
    hub_sn: str | None = None
    timestamp: int | None = None
    uptime: int | None = None
    voltage: float | None = None
    firmware_revision: int | str | None = None
    rssi: int | None = None
    hub_rssi: int | None = None
    sensor_status: int | None = None
    debug: int | None = None

    def format_oneline(self) -> str:
        v_str = f"{self.voltage:.2f}V" if isinstance(self.voltage, int | float) else "?"
        return (
            "device_status  "
            f"uptime={format_uptime(self.uptime or 0)}  "
            f"bat={v_str}  "
            f"rssi={self.rssi if self.rssi is not None else '?'} dBm  "
            f"hub_rssi={self.hub_rssi if self.hub_rssi is not None else '?'} dBm  "
            f"sensor_status={self.sensor_status if self.sensor_status is not None else '?'}"
        )


DecodedEvent = Annotated[
    DecodedObsSt
    | DecodedRapidWind
    | DecodedEvtStrike
    | DecodedEvtPrecip
    | DecodedHubStatus
    | DecodedDeviceStatus,
    Field(discriminator="type"),
]


# ---- decoder ----------------------------------------------------------------


def _decode_obs_st(payload: dict) -> DecodedObsSt | None:
    obs_lists = payload.get("obs") or []
    if not obs_lists:
        return None
    obs = obs_lists[0] if isinstance(obs_lists[0], list) else None
    if obs is None or len(obs) < 18:
        return None
    return DecodedObsSt(
        time_epoch=obs[0],
        wind_lull_mps=obs[1],
        wind_avg_mps=obs[2],
        wind_gust_mps=obs[3],
        wind_direction_deg=obs[4],
        wind_sample_interval_sec=obs[5],
        pressure_mb=obs[6],
        air_temp_c=obs[7],
        relative_humidity_pct=obs[8],
        illuminance_lux=obs[9],
        uv_index=obs[10],
        solar_radiation_w_m2=obs[11],
        rain_accumulated_mm=obs[12],
        precipitation_type=obs[13],
        lightning_strike_avg_distance_km=obs[14],
        lightning_strike_count=obs[15],
        battery_voltage=obs[16],
        report_interval_minutes=obs[17],
    )


def _decode_rapid_wind(payload: dict) -> DecodedRapidWind | None:
    ob = payload.get("ob") or []
    if len(ob) < 3:
        return None
    return DecodedRapidWind(
        time_epoch=ob[0],
        wind_speed_mps=ob[1],
        wind_direction_deg=ob[2],
    )


def _decode_evt_strike(payload: dict) -> DecodedEvtStrike | None:
    evt = payload.get("evt") or []
    if len(evt) < 3:
        return None
    return DecodedEvtStrike(time_epoch=evt[0], distance_km=evt[1], energy=evt[2])


def _decode_evt_precip(payload: dict) -> DecodedEvtPrecip | None:
    evt = payload.get("evt") or []
    return DecodedEvtPrecip(time_epoch=evt[0] if evt else None)


def _decode_hub_status(payload: dict) -> DecodedHubStatus:
    return DecodedHubStatus(
        serial_number=payload.get("serial_number"),
        firmware_revision=payload.get("firmware_revision"),
        uptime=payload.get("uptime"),
        rssi=payload.get("rssi"),
        seq=payload.get("seq"),
        timestamp=payload.get("timestamp"),
    )


def _decode_device_status(payload: dict) -> DecodedDeviceStatus:
    return DecodedDeviceStatus(
        serial_number=payload.get("serial_number"),
        hub_sn=payload.get("hub_sn"),
        timestamp=payload.get("timestamp"),
        uptime=payload.get("uptime"),
        voltage=payload.get("voltage"),
        firmware_revision=payload.get("firmware_revision"),
        rssi=payload.get("rssi"),
        hub_rssi=payload.get("hub_rssi"),
        sensor_status=payload.get("sensor_status"),
        debug=payload.get("debug"),
    )


_DECODERS = {
    "obs_st": _decode_obs_st,
    "rapid_wind": _decode_rapid_wind,
    "evt_strike": _decode_evt_strike,
    "evt_precip": _decode_evt_precip,
    "hub_status": _decode_hub_status,
    "device_status": _decode_device_status,
}


def decode(payload: dict) -> DecodedEvent | None:
    """Return a typed model for a recognized Tempest payload, else None.

    Returns None for unknown `type` fields and for malformed messages of a known
    type (e.g. obs_st with truncated observation array). Callers should treat
    None as "skip this packet" — never crash.
    """
    if not isinstance(payload, dict):
        return None
    t = payload.get("type")
    decoder = _DECODERS.get(t) if isinstance(t, str) else None
    if decoder is None:
        return None
    try:
        return decoder(payload)
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def format_oneline(payload: dict) -> str:
    """One-line human summary used by the CLI monitor.

    Falls back to a truncated raw-JSON dump for unknown or malformed payloads
    so the operator still sees something on every datagram.
    """
    decoded = decode(payload)
    if decoded is not None:
        return decoded.format_oneline()
    if not isinstance(payload, dict):
        return f"?  {json.dumps(payload, separators=(',', ':'))[:200]}"
    t = payload.get("type", "?")
    return f"{t}  {json.dumps(payload, separators=(',', ':'))[:200]}"
