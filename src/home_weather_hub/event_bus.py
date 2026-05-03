"""In-process pub/sub for decoded Tempest events.

The UDP listener decodes packets and publishes them here; the FastAPI WebSocket
endpoint subscribes and forwards them to connected dashboard clients. Keeping
this in-process (one container, one event loop) means the listener and the
dashboard API don't both need to bind UDP 50222 with `SO_REUSEPORT`.

Each subscriber gets its own bounded queue. Slow subscribers drop the oldest
message before getting a new one — a stalled WebSocket can't back-pressure the
UDP listener.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from home_weather_hub.tempest_decode import DecodedEvent

log = logging.getLogger(__name__)

DEFAULT_SUBSCRIBER_QUEUE_SIZE = 64


class EventBus:
    def __init__(self, subscriber_queue_size: int = DEFAULT_SUBSCRIBER_QUEUE_SIZE):
        self._subscribers: set[asyncio.Queue[DecodedEvent]] = set()
        self._queue_size = subscriber_queue_size

    def publish(self, event: DecodedEvent) -> None:
        """Fan out to every subscriber. Drops oldest on overflow, never blocks."""
        for q in self._subscribers:
            if q.full():
                # The slow subscriber is at fault, not us — drop its oldest message.
                with contextlib.suppress(asyncio.QueueEmpty):  # race-only
                    q.get_nowait()
                log.debug("dropped oldest event for slow subscriber (qsize=%d)", q.qsize())
            q.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[DecodedEvent]]:
        """Async context manager that registers a queue and unregisters on exit."""
        q: asyncio.Queue[DecodedEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(q)
        try:
            yield q
        finally:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


_default_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-wide default bus, creating it on first call."""
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_event_bus_for_tests() -> None:
    """Drop the singleton so tests get a clean instance."""
    global _default_bus
    _default_bus = None
