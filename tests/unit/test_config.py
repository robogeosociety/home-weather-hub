"""Unit tests for the stations.toml loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from home_weather_hub.config import StationConfig, load_stations

pytestmark = pytest.mark.unit


def test_load_stations_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_stations(tmp_path / "nope.toml") == []


def test_load_stations_parses_full_entry(tmp_path: Path) -> None:
    p = tmp_path / "stations.toml"
    p.write_text(
        """
        [[stations]]
        sensor_id = "tempest:ST-1"
        kind = "tempest"
        label = "Backyard"
        location = "outside"
        latitude = 47.6062
        longitude = -122.3321
        """
    )
    [s] = load_stations(p)
    assert s == StationConfig(
        sensor_id="tempest:ST-1",
        kind="tempest",
        label="Backyard",
        location="outside",
        latitude=47.6062,
        longitude=-122.3321,
    )


def test_load_stations_allows_optional_fields(tmp_path: Path) -> None:
    p = tmp_path / "stations.toml"
    p.write_text(
        """
        [[stations]]
        sensor_id = "snzb:0xa1"
        kind = "snzb-02wd"
        """
    )
    [s] = load_stations(p)
    assert s.label is None
    assert s.location is None
    assert s.latitude is None
    assert s.longitude is None


def test_load_stations_raises_on_missing_required_key(tmp_path: Path) -> None:
    p = tmp_path / "stations.toml"
    p.write_text(
        """
        [[stations]]
        sensor_id = "tempest:ST-1"
        """
    )
    with pytest.raises(ValueError, match="kind"):
        load_stations(p)


def test_load_stations_handles_multiple_stations(tmp_path: Path) -> None:
    p = tmp_path / "stations.toml"
    p.write_text(
        """
        [[stations]]
        sensor_id = "tempest:ST-1"
        kind = "tempest"
        latitude = 47.0

        [[stations]]
        sensor_id = "snzb:0xa1"
        kind = "snzb-02wd"
        location = "living_room"
        """
    )
    stations = load_stations(p)
    assert [s.sensor_id for s in stations] == ["tempest:ST-1", "snzb:0xa1"]
    assert stations[0].latitude == 47.0
    assert stations[1].location == "living_room"
