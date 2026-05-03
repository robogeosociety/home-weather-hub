"""Unit tests for the Tempest payload decoder."""

from __future__ import annotations

import pytest

from home_weather_hub.tempest_decode import (
    DecodedDeviceStatus,
    DecodedEvtPrecip,
    DecodedEvtStrike,
    DecodedHubStatus,
    DecodedObsSt,
    DecodedRapidWind,
    c_to_f,
    decode,
    format_oneline,
    format_uptime,
    km_to_mi,
    mm_to_in,
    mps_to_mph,
)

pytestmark = pytest.mark.unit


# ---- conversion helpers ----------------------------------------------------


def test_c_to_f_freezing_and_boiling() -> None:
    assert c_to_f(0) == 32
    assert c_to_f(100) == 212


def test_mps_to_mph_zero_and_known_value() -> None:
    assert mps_to_mph(0) == 0
    assert mps_to_mph(10) == pytest.approx(22.3694, rel=1e-4)


def test_mm_to_in() -> None:
    assert mm_to_in(25.4) == pytest.approx(1.0)


def test_km_to_mi() -> None:
    assert km_to_mi(1.609344) == pytest.approx(1.0, rel=1e-4)


def test_format_uptime_minutes_hours_days() -> None:
    assert format_uptime(45) == "0m"
    assert format_uptime(120) == "2m"
    assert format_uptime(3600 + 120) == "1h2m"
    assert format_uptime(86400 + 3600 * 5) == "1d5h"


# ---- obs_st ----------------------------------------------------------------


def _full_obs_st(**overrides: float) -> dict:
    """Build a syntactically-complete obs_st payload using realistic values."""
    obs = [
        1700000000,  # 0 time_epoch
        1.5,  # 1 wind_lull_mps
        3.2,  # 2 wind_avg_mps
        5.7,  # 3 wind_gust_mps
        180.0,  # 4 wind_direction_deg
        3,  # 5 wind_sample_interval_sec
        1015.4,  # 6 pressure_mb
        21.5,  # 7 air_temp_c (≈70.7°F)
        58.0,  # 8 relative_humidity_pct
        12000.0,  # 9 illuminance_lux
        4.2,  # 10 uv_index
        450.0,  # 11 solar_radiation_w_m2
        0.5,  # 12 rain_accumulated_mm
        1,  # 13 precipitation_type (rain)
        0.0,  # 14 lightning_strike_avg_distance_km
        0,  # 15 lightning_strike_count
        2.78,  # 16 battery_voltage
        1,  # 17 report_interval_minutes
    ]
    return {
        "serial_number": "ST-1",
        "type": "obs_st",
        "hub_sn": "HB-1",
        "obs": [obs],
        "firmware_revision": 165,
    }


def test_obs_st_decodes_named_fields() -> None:
    decoded = decode(_full_obs_st())
    assert isinstance(decoded, DecodedObsSt)
    assert decoded.air_temp_c == 21.5
    assert decoded.air_temp_f == pytest.approx(70.7, abs=0.05)
    assert decoded.wind_avg_mps == 3.2
    assert decoded.wind_avg_mph == pytest.approx(7.158, rel=1e-3)
    assert decoded.relative_humidity_pct == 58
    assert decoded.pressure_mb == 1015.4
    assert decoded.battery_voltage == 2.78
    assert decoded.precipitation_type == 1


def test_obs_st_truncated_obs_returns_none() -> None:
    payload = _full_obs_st()
    payload["obs"][0] = payload["obs"][0][:10]  # too short
    assert decode(payload) is None


def test_obs_st_missing_obs_returns_none() -> None:
    assert decode({"type": "obs_st"}) is None
    assert decode({"type": "obs_st", "obs": []}) is None


def test_obs_st_serializes_computed_fields() -> None:
    decoded = decode(_full_obs_st())
    assert decoded is not None
    dumped = decoded.model_dump()
    # Computed fields must be in the JSON dump so the frontend gets °F without
    # doing math on every render.
    assert "air_temp_f" in dumped
    assert "wind_avg_mph" in dumped
    assert "wind_gust_mph" in dumped
    assert "rain_accumulated_in" in dumped


def test_obs_st_oneline_matches_legacy_monitor_format() -> None:
    decoded = decode(_full_obs_st())
    assert decoded is not None
    line = decoded.format_oneline()
    # The legacy monitor produced this exact prefix; preserve it byte-for-byte
    # so existing operator workflows aren't disrupted.
    assert line.startswith("obs_st  temp=70.7°F (21.5°C)  rh=58%  wind=7.2 mph @180°")


# ---- rapid_wind ------------------------------------------------------------


def test_rapid_wind_decodes() -> None:
    decoded = decode({"type": "rapid_wind", "ob": [1700000000, 4.5, 270]})
    assert isinstance(decoded, DecodedRapidWind)
    assert decoded.wind_speed_mps == 4.5
    assert decoded.wind_direction_deg == 270
    assert decoded.wind_speed_mph == pytest.approx(10.066, rel=1e-3)


def test_rapid_wind_short_ob_returns_none() -> None:
    assert decode({"type": "rapid_wind", "ob": [1700000000, 4.5]}) is None
    assert decode({"type": "rapid_wind", "ob": []}) is None


# ---- evt_strike + evt_precip ----------------------------------------------


def test_evt_strike_decodes() -> None:
    decoded = decode({"type": "evt_strike", "evt": [1700000000, 12.5, 4096]})
    assert isinstance(decoded, DecodedEvtStrike)
    assert decoded.distance_km == 12.5
    assert decoded.energy == 4096
    assert decoded.distance_mi == pytest.approx(7.767, rel=1e-3)


def test_evt_strike_short_returns_none() -> None:
    assert decode({"type": "evt_strike", "evt": [1700000000]}) is None


def test_evt_precip_decodes_even_without_evt_array() -> None:
    decoded = decode({"type": "evt_precip"})
    assert isinstance(decoded, DecodedEvtPrecip)
    assert decoded.format_oneline() == "evt_precip  rain detected"


# ---- hub_status + device_status -------------------------------------------


def test_hub_status_decodes_known_fields() -> None:
    decoded = decode(
        {
            "type": "hub_status",
            "serial_number": "HB-00208576",
            "uptime": 90061,
            "rssi": -55,
            "seq": 1234,
            "firmware_revision": "194",
            "extra_unknown_field": "ignored",
        }
    )
    assert isinstance(decoded, DecodedHubStatus)
    assert decoded.serial_number == "HB-00208576"
    assert decoded.uptime == 90061
    assert "1d1h" in decoded.format_oneline()


def test_device_status_decodes_known_fields() -> None:
    decoded = decode(
        {
            "type": "device_status",
            "serial_number": "ST-00000512",
            "hub_sn": "HB-00208576",
            "uptime": 7200,
            "voltage": 2.78,
            "rssi": -68,
            "hub_rssi": -54,
            "sensor_status": 0,
        }
    )
    assert isinstance(decoded, DecodedDeviceStatus)
    line = decoded.format_oneline()
    assert "bat=2.78V" in line
    assert "uptime=2h" in line


# ---- decode dispatch --------------------------------------------------------


def test_decode_returns_none_for_unknown_type() -> None:
    assert decode({"type": "lightning_unicorn"}) is None


def test_decode_returns_none_for_non_dict() -> None:
    assert decode([1, 2, 3]) is None  # type: ignore[arg-type]
    assert decode(None) is None  # type: ignore[arg-type]


def test_decode_returns_none_for_missing_type() -> None:
    assert decode({"obs": [[]]}) is None


def test_decode_swallows_internal_errors() -> None:
    """A surprise field type (e.g. a string where a number is expected) must not crash."""
    payload = {"type": "rapid_wind", "ob": [1700000000, "not-a-number", "north"]}
    # Pydantic validation may raise or coerce; the decoder must absorb either path.
    result = decode(payload)
    # Either coerced or None — both are acceptable, just must not raise.
    assert result is None or isinstance(result, DecodedRapidWind)


# ---- format_oneline ---------------------------------------------------------


def test_format_oneline_unknown_type_falls_back_to_raw() -> None:
    line = format_oneline({"type": "mystery", "x": 1})
    assert line.startswith("mystery  ")
    assert '"x":1' in line


def test_format_oneline_non_dict_falls_back() -> None:
    line = format_oneline([1, 2, 3])  # type: ignore[arg-type]
    assert line.startswith("?  ")
