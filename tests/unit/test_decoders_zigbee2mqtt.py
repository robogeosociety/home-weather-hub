"""Unit tests for the Zigbee2MQTT decoder."""

from __future__ import annotations

import pytest

from home_weather_hub.decoders.zigbee2mqtt import decode_bridge_devices, decode_payload

pytestmark = pytest.mark.unit


def test_snzb_02wd_payload_maps_all_known_fields() -> None:
    payload = {
        "battery": 96,
        "humidity": 45.2,
        "linkquality": 78,
        "temperature": 22.4,
        "voltage": 3000,
    }
    decoded = dict(decode_payload(payload))
    assert decoded["air_temp_c"] == pytest.approx(22.4)
    assert decoded["humidity_pct"] == pytest.approx(45.2)
    assert decoded["battery_pct"] == pytest.approx(96.0)
    assert decoded["battery_v"] == pytest.approx(3.0)  # 3000 mV → 3.0 V
    assert decoded["link_quality"] == pytest.approx(78.0)


def test_partial_payload_only_emits_present_fields() -> None:
    decoded = dict(decode_payload({"temperature": 19.1, "linkquality": 200}))
    assert decoded == {"air_temp_c": 19.1, "link_quality": 200.0}


def test_null_and_non_numeric_fields_are_dropped() -> None:
    decoded = dict(
        decode_payload(
            {
                "temperature": None,
                "humidity": "n/a",
                "battery": True,  # bool is not a real number for our purposes
                "voltage": 2950,
            }
        )
    )
    assert decoded == {"battery_v": pytest.approx(2.95)}


def test_keep_alive_only_returns_empty_list() -> None:
    assert decode_payload({"last_seen": "2026-05-02T18:30:00Z"}) == []


def test_non_dict_payload_returns_empty_list() -> None:
    assert decode_payload("not a dict") == []  # type: ignore[arg-type]
    assert decode_payload(None) == []  # type: ignore[arg-type]
    assert decode_payload([1, 2, 3]) == []  # type: ignore[arg-type]


def test_decode_bridge_devices_skips_coordinator_and_returns_friendly_to_ieee() -> None:
    payload = [
        {
            "type": "Coordinator",
            "ieee_address": "0x00124b0000000000",
            "friendly_name": "Coordinator",
        },
        {
            "type": "EndDevice",
            "ieee_address": "0xa4c138aabbccdd",
            "friendly_name": "living_room",
            "definition": {"model": "SNZB-02"},
        },
        {
            "type": "EndDevice",
            "ieee_address": "0xa4c138eeff0011",
            "friendly_name": "bedroom",
        },
    ]
    assert decode_bridge_devices(payload) == {
        "living_room": "0xa4c138aabbccdd",
        "bedroom": "0xa4c138eeff0011",
    }


def test_decode_bridge_devices_drops_entries_missing_required_fields() -> None:
    payload = [
        {"type": "EndDevice", "friendly_name": "no_ieee"},
        {"type": "EndDevice", "ieee_address": "0xabc"},  # no friendly_name
        {"type": "EndDevice", "ieee_address": "0xdef", "friendly_name": "ok"},
    ]
    assert decode_bridge_devices(payload) == {"ok": "0xdef"}


def test_decode_bridge_devices_handles_non_list_input() -> None:
    assert decode_bridge_devices(None) == {}
    assert decode_bridge_devices("not a list") == {}
    assert decode_bridge_devices({"foo": "bar"}) == {}
