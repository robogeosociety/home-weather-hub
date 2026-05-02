"""Unit tests for the Tempest obs_st decoder."""

from __future__ import annotations

import pytest

from home_weather_hub.decoders.tempest import OBS_ST_METRICS, decode_obs_st

pytestmark = pytest.mark.unit


def _full_obs(epoch: int = 1_700_000_000) -> list:
    """An obs_st obs[] array filled with distinct floats so each metric is identifiable."""
    return [
        epoch,  # 0  epoch
        0.5,  # 1  wind_lull
        2.0,  # 2  wind_avg
        4.5,  # 3  wind_gust
        180.0,  # 4  wind_dir
        3,  # 5  wind interval (not stored)
        1015.2,  # 6  pressure
        18.7,  # 7  air_temp
        62.0,  # 8  humidity
        12345,  # 9  illuminance
        3.4,  # 10 uv
        450,  # 11 solar
        0.05,  # 12 rain
        7.2,  # 13 lightning_avg_km
        0,  # 14 precip type (not stored)
        2,  # 15 lightning_count
        2.78,  # 16 battery_v
        60,  # 17 report interval (not stored)
    ]


def test_decode_obs_st_full_payload() -> None:
    payload = {
        "type": "obs_st",
        "serial_number": "ST-00027770",
        "obs": [_full_obs(1_700_000_000)],
    }
    result = decode_obs_st(payload)
    assert result is not None
    sensor_id, ts, metrics = result
    assert sensor_id == "tempest:ST-00027770"
    assert ts == 1_700_000_000
    by_name = dict(metrics)
    assert by_name["wind_lull_mps"] == 0.5
    assert by_name["wind_avg_mps"] == 2.0
    assert by_name["wind_gust_mps"] == 4.5
    assert by_name["wind_dir_deg"] == 180.0
    assert by_name["pressure_mb"] == 1015.2
    assert by_name["air_temp_c"] == 18.7
    assert by_name["humidity_pct"] == 62.0
    assert by_name["illuminance_lux"] == 12345.0
    assert by_name["uv_index"] == 3.4
    assert by_name["solar_w_m2"] == 450.0
    assert by_name["rain_mm"] == 0.05
    assert by_name["lightning_avg_km"] == 7.2
    assert by_name["lightning_count"] == 2.0
    assert by_name["battery_v"] == 2.78
    assert len(metrics) == len(OBS_ST_METRICS)


def test_decode_obs_st_skips_null_subsensor_slots() -> None:
    obs = _full_obs()
    obs[10] = None  # uv unavailable
    obs[12] = None  # rain unavailable
    payload = {"type": "obs_st", "serial_number": "ST-1", "obs": [obs]}
    result = decode_obs_st(payload)
    assert result is not None
    names = {m for m, _ in result[2]}
    assert "uv_index" not in names
    assert "rain_mm" not in names
    assert "air_temp_c" in names


def test_decode_non_obs_st_returns_none() -> None:
    assert decode_obs_st({"type": "hub_status", "uptime": 12}) is None
    assert decode_obs_st({"type": "rapid_wind", "ob": [1, 2.0, 90]}) is None


def test_decode_handles_malformed_payload_without_crashing() -> None:
    assert decode_obs_st({"type": "obs_st"}) is None  # no obs
    assert decode_obs_st({"type": "obs_st", "serial_number": "ST-1", "obs": []}) is None
    assert decode_obs_st({"type": "obs_st", "serial_number": "ST-1", "obs": [[]]}) is None
    assert decode_obs_st({"type": "obs_st", "serial_number": "ST-1", "obs": [[None, 1.0]]}) is None
    assert decode_obs_st({"type": "obs_st", "obs": [[1, 2]]}) is None  # no serial


def test_decode_truncated_obs_array_only_yields_present_metrics() -> None:
    # obs only has the first 5 entries -> only wind metrics should be returned.
    short = [1_700_000_000, 1.0, 2.0, 3.0, 90.0]
    payload = {"type": "obs_st", "serial_number": "ST-2", "obs": [short]}
    result = decode_obs_st(payload)
    assert result is not None
    names = [m for m, _ in result[2]]
    assert names == ["wind_lull_mps", "wind_avg_mps", "wind_gust_mps", "wind_dir_deg"]
