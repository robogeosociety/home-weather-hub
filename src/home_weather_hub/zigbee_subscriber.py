"""Subscribe to Zigbee2MQTT topics and ingest device readings.

The subscriber connects to a local Mosquitto broker, listens to:

    zigbee2mqtt/bridge/devices   — retained device catalog (friendly_name → ieee)
    zigbee2mqtt/+                — per-device readings (temp/humidity/battery/...)

and routes each per-device message through the existing JSONL+SQLite sinks.
The catalog topic is what lets us key everything by stable `snzb:<ieee>`
sensor_ids even though the payload topic uses the human-friendly name.

JSONL files rotate daily as `data/zigbee-YYYY-MM-DD.jsonl` so they sit
alongside (and never collide with) the Tempest dumps.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import time
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path

import aiomqtt

from home_weather_hub.config import load_stations
from home_weather_hub.decoders.zigbee2mqtt import decode_bridge_devices, decode_payload
from home_weather_hub.storage import Aggregator, open_db

DEFAULT_BROKER_HOST = "127.0.0.1"
DEFAULT_BROKER_PORT = 1883
DEFAULT_BASE_TOPIC = "zigbee2mqtt"
DEFAULT_FLUSH_INTERVAL_SEC = 5.0
DEFAULT_DB_PATH = Path("./data/weather.db")
DEFAULT_STATIONS_PATH = Path("./config/stations.toml")
DEFAULT_DEVICE_KIND = "zigbee"

# Sensor topics we never want to treat as a device reading. `bridge/*` is the
# Z2M control-plane; the catalogue subscription handles `bridge/devices`
# explicitly.
_BRIDGE_PREFIX = "bridge"

log = logging.getLogger("zigbee_subscriber")


class _StationOverride:
    """Per-sensor metadata loaded from `stations.toml` and applied at ingest."""

    __slots__ = ("kind", "location")

    def __init__(self, kind: str, location: str | None):
        self.kind = kind
        self.location = location


class JsonlWriter:
    """Daily-rotated JSONL writer (mirrors the Tempest one — same envelope shape)."""

    def __init__(self, data_dir: Path, prefix: str = "zigbee"):
        self._data_dir = data_dir
        self._prefix = prefix
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: date | None = None
        self._fh = None

    def _path_for(self, d: date) -> Path:
        return self._data_dir / f"{self._prefix}-{d.isoformat()}.jsonl"

    def _rotate_if_needed(self, today: date) -> None:
        if today == self._current_date and self._fh is not None:
            return
        self.close()
        path = self._path_for(today)
        self._fh = path.open("a", encoding="utf-8")
        self._current_date = today
        log.info("writing to %s", path)

    def write(self, record: dict) -> None:
        self._rotate_if_needed(datetime.now(UTC).date())
        assert self._fh is not None
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None


class MessageRouter:
    """Pure routing logic, separated from aiomqtt so it can be unit-tested.

    Holds the friendly_name -> ieee_address map (refreshed from the retained
    `bridge/devices` topic) and the friendly_name -> kind/location overrides
    sourced from `stations.toml`. Per-device messages are decoded and
    forwarded to the JSONL writer + Aggregator.
    """

    def __init__(
        self,
        writer: JsonlWriter,
        aggregator: Aggregator | None,
        base_topic: str = DEFAULT_BASE_TOPIC,
        time_source: Callable[[], float] = time.time,
        stations_by_sensor_id: dict[str, _StationOverride] | None = None,
    ):
        self._writer = writer
        self._aggregator = aggregator
        self._base_topic = base_topic
        self._time = time_source
        self._friendly_to_ieee: dict[str, str] = {}
        self._known_sensors: set[str] = set()
        self._warned_unknown: set[str] = set()
        self._overrides = stations_by_sensor_id or {}
        self._packet_count = 0

    def seed_known_sensors(self, sensor_ids: Iterable[str]) -> None:
        self._known_sensors.update(sensor_ids)

    def handle(self, topic: str, raw_payload: bytes) -> None:
        """Entry point. Routes by topic, never raises on a single bad message."""
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as e:
            log.warning(
                "dropping malformed JSON on %s: %s (first 80 bytes: %s)",
                topic,
                e,
                raw_payload[:80],
            )
            return

        sub = self._strip_base_topic(topic)
        if sub is None:
            return  # not ours

        if sub == f"{_BRIDGE_PREFIX}/devices":
            self._handle_bridge_devices(payload)
            return
        if sub.startswith(f"{_BRIDGE_PREFIX}/"):
            return  # other bridge/* topics — uninteresting to us

        # Anything else under the base topic is a per-device message keyed by
        # friendly_name. Z2M may have sub-topics like `<name>/availability`
        # or `<name>/set` we should ignore.
        if "/" in sub:
            return
        self._handle_device_message(friendly_name=sub, topic=topic, payload=payload)

    def _strip_base_topic(self, topic: str) -> str | None:
        prefix = self._base_topic + "/"
        if not topic.startswith(prefix):
            return None
        return topic[len(prefix) :]

    def _handle_bridge_devices(self, payload: object) -> None:
        mapping = decode_bridge_devices(payload)
        if not mapping:
            return
        added = set(mapping.items()) - set(self._friendly_to_ieee.items())
        self._friendly_to_ieee = mapping
        if added:
            log.info(
                "Z2M device catalog refreshed: %d device(s), %d new/changed",
                len(mapping),
                len(added),
            )

    def _handle_device_message(self, friendly_name: str, topic: str, payload: object) -> None:
        ieee = self._friendly_to_ieee.get(friendly_name)
        if ieee is None:
            # Catalog hasn't arrived yet (rare — `bridge/devices` is retained
            # so it lands on connect) or this is a device Z2M doesn't know.
            # Fall back to keying by friendly_name so data isn't lost; once
            # the catalog catches up we'll switch over.
            sensor_id = f"znme:{friendly_name}"
            if friendly_name not in self._warned_unknown:
                self._warned_unknown.add(friendly_name)
                log.warning(
                    "device %r not yet in Z2M catalog; logging as %s until bridge/devices arrives",
                    friendly_name,
                    sensor_id,
                )
        else:
            sensor_id = f"snzb:{ieee}"

        record = {
            "received_at": datetime.now(UTC).isoformat(),
            "topic": topic,
            "friendly_name": friendly_name,
            "sensor_id": sensor_id,
            "payload": payload,
        }
        self._writer.write(record)
        self._packet_count += 1
        if self._packet_count % 50 == 1:
            log.info("message #%d topic=%s sensor=%s", self._packet_count, topic, sensor_id)

        if self._aggregator is None or not isinstance(payload, dict):
            return

        metrics = decode_payload(payload)
        if not metrics:
            return

        ts = self._extract_ts(payload)
        override = self._overrides.get(sensor_id)
        kind = override.kind if override else DEFAULT_DEVICE_KIND
        location = override.location if override else None
        rows = [(sensor_id, kind, location, name, value, ts) for name, value in metrics]
        try:
            self._aggregator.record_many(rows)
        except Exception:
            log.exception("aggregator failed for %s", sensor_id)

        if sensor_id not in self._known_sensors:
            # First time we've seen this sensor in this process — same
            # observability hook as the Tempest path so the operator
            # notices new devices that aren't in stations.toml.
            self._known_sensors.add(sensor_id)
            if override is None:
                log.warning(
                    "data from unconfigured sensor %s (friendly_name=%s); "
                    "add it to stations.toml to attach a label/location",
                    sensor_id,
                    friendly_name,
                )

    def _extract_ts(self, payload: dict) -> int:
        # Z2M sometimes emits `last_seen` in ISO-8601; prefer it so the
        # aggregator's day/month buckets match the device's clock rather
        # than our receive time. Fall back to wall clock when absent.
        raw = payload.get("last_seen")
        if isinstance(raw, str):
            try:
                return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
            except ValueError:
                pass
        return int(self._time())


async def _flush_loop(writer: JsonlWriter, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        writer.flush()


async def _consume(
    client: aiomqtt.Client,
    router: MessageRouter,
    base_topic: str,
) -> None:
    # Subscribe to the catalog first so the friendly_name->ieee map is
    # primed before any per-device message lands. Z2M publishes the
    # catalog as a retained message so we get it immediately on connect.
    await client.subscribe(f"{base_topic}/bridge/devices")
    await client.subscribe(f"{base_topic}/+")
    async for message in client.messages:
        router.handle(str(message.topic), bytes(message.payload))


async def _run(
    broker_host: str,
    broker_port: int,
    base_topic: str,
    data_dir: Path,
    flush_interval: float,
    db_path: Path | None,
    stations_path: Path | None,
) -> None:
    writer = JsonlWriter(data_dir)
    aggregator: Aggregator | None = None
    overrides: dict[str, _StationOverride] = {}
    known_sensors: set[str] = set()
    if db_path is not None:
        conn = open_db(db_path)
        aggregator = Aggregator(conn)
        log.info("aggregating to %s", db_path)
        if stations_path is not None:
            stations = load_stations(stations_path)
            zigbee_stations = [s for s in stations if s.sensor_id.startswith(("snzb:", "znme:"))]
            for s in zigbee_stations:
                aggregator.upsert_station_metadata(
                    sensor_id=s.sensor_id,
                    kind=s.kind,
                    label=s.label,
                    location=s.location,
                    latitude=s.latitude,
                    longitude=s.longitude,
                )
                overrides[s.sensor_id] = _StationOverride(kind=s.kind, location=s.location)
                known_sensors.add(s.sensor_id)
            if zigbee_stations:
                log.info(
                    "seeded %d Zigbee station(s) from %s: %s",
                    len(zigbee_stations),
                    stations_path,
                    ", ".join(s.sensor_id for s in zigbee_stations),
                )
            elif stations_path.exists():
                log.info("no Zigbee [[stations]] in %s", stations_path)
            else:
                log.info("no station config at %s (skipping)", stations_path)

    router = MessageRouter(
        writer=writer,
        aggregator=aggregator,
        base_topic=base_topic,
        stations_by_sensor_id=overrides,
    )
    router.seed_known_sensors(known_sensors)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    flush_task = asyncio.create_task(_flush_loop(writer, flush_interval))
    try:
        log.info("connecting to mqtt://%s:%d", broker_host, broker_port)
        async with aiomqtt.Client(hostname=broker_host, port=broker_port) as client:
            consume_task = asyncio.create_task(_consume(client, router, base_topic))
            stop_task = asyncio.create_task(stop_event.wait())
            done, _pending = await asyncio.wait(
                {consume_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            consume_task.cancel()
            stop_task.cancel()
            # Surface any exception from the consumer (e.g. broker died) so
            # the caller sees a non-zero exit, not a silent shutdown.
            for t in done:
                if t is consume_task and not t.cancelled():
                    exc = t.exception()
                    if exc is not None:
                        raise exc
    finally:
        log.info("shutting down")
        flush_task.cancel()
        writer.close()
        if aggregator is not None:
            aggregator.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-host", default=DEFAULT_BROKER_HOST)
    parser.add_argument("--broker-port", type=int, default=DEFAULT_BROKER_PORT)
    parser.add_argument(
        "--base-topic",
        default=DEFAULT_BASE_TOPIC,
        help="Z2M `mqtt.base_topic` value (default 'zigbee2mqtt').",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("./data"))
    parser.add_argument("--flush-interval", type=float, default=DEFAULT_FLUSH_INTERVAL_SEC)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite file for observation + aggregate storage. Created if missing.",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Disable the SQLite aggregator entirely (JSONL only).",
    )
    parser.add_argument(
        "--stations",
        type=Path,
        default=DEFAULT_STATIONS_PATH,
        help="TOML file describing each station's sensor_id, label, location. "
        "Loaded once at startup; missing file is OK (no seeding).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    db_path = None if args.no_db else args.db_path
    stations_path = None if db_path is None else args.stations
    asyncio.run(
        _run(
            args.broker_host,
            args.broker_port,
            args.base_topic,
            args.data_dir,
            args.flush_interval,
            db_path,
            stations_path,
        )
    )


if __name__ == "__main__":
    main()
