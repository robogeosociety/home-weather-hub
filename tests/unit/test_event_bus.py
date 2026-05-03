"""Unit tests for the in-process event bus."""

from __future__ import annotations

import asyncio

import pytest

from home_weather_hub.event_bus import EventBus
from home_weather_hub.tempest_decode import DecodedEvtStrike, DecodedHubStatus

pytestmark = pytest.mark.unit


async def test_publish_fans_out_to_every_subscriber() -> None:
    bus = EventBus()
    async with bus.subscribe() as q1, bus.subscribe() as q2:
        bus.publish(DecodedHubStatus(serial_number="HB-1"))
        e1 = await asyncio.wait_for(q1.get(), timeout=0.1)
        e2 = await asyncio.wait_for(q2.get(), timeout=0.1)
        assert e1.serial_number == "HB-1"
        assert e2.serial_number == "HB-1"


async def test_publish_with_no_subscribers_is_noop() -> None:
    bus = EventBus()
    bus.publish(DecodedHubStatus())  # must not raise


async def test_subscriber_unregisters_on_context_exit() -> None:
    bus = EventBus()
    async with bus.subscribe():
        assert bus.subscriber_count == 1
    assert bus.subscriber_count == 0


async def test_full_queue_drops_oldest_message_to_protect_publisher() -> None:
    """Slow subscribers must never back-pressure the UDP listener."""
    bus = EventBus(subscriber_queue_size=2)
    async with bus.subscribe() as q:
        bus.publish(DecodedEvtStrike(distance_km=1))
        bus.publish(DecodedEvtStrike(distance_km=2))
        bus.publish(DecodedEvtStrike(distance_km=3))  # forces drop of #1
        first = await q.get()
        second = await q.get()
        assert (first.distance_km, second.distance_km) == (2, 3)
        assert q.empty()


async def test_subscriber_unregistered_even_if_body_raises() -> None:
    bus = EventBus()
    with pytest.raises(RuntimeError):
        async with bus.subscribe():
            assert bus.subscriber_count == 1
            raise RuntimeError("boom")
    assert bus.subscriber_count == 0
