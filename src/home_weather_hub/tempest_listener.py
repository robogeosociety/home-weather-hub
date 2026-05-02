"""Listen for Tempest weather station UDP broadcasts and append to daily JSONL files."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import socket
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

DEFAULT_PORT = 50222
DEFAULT_FLUSH_INTERVAL_SEC = 5.0
DEFAULT_DEDUPE_WINDOW_SEC = 2.0

log = logging.getLogger("tempest_listener")


class JsonlWriter:
    """Append-only JSONL writer that rotates by UTC date."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: date | None = None
        self._fh = None

    def _path_for(self, d: date) -> Path:
        return self._data_dir / f"tempest-{d.isoformat()}.jsonl"

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


class TempestProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        writer: JsonlWriter,
        dedupe_window_sec: float = DEFAULT_DEDUPE_WINDOW_SEC,
        time_source: Callable[[], float] = time.monotonic,
    ):
        self._writer = writer
        self._packet_count = 0
        self._dropped_dups = 0
        self._dedupe_window = dedupe_window_sec
        self._time = time_source
        # Maps raw datagram bytes -> expiry time (monotonic seconds).
        self._recent: dict[bytes, float] = {}

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        sock = transport.get_extra_info("socket")
        log.info("listening on %s", sock.getsockname())

    def _is_duplicate(self, data: bytes) -> bool:
        # Hosts with multiple interfaces on the same broadcast domain receive each
        # broadcast once per receiving interface; drop bytewise-identical replays
        # that arrive within the dedupe window.
        if self._dedupe_window <= 0:
            return False
        now = self._time()
        if self._recent:
            expired = [k for k, exp in self._recent.items() if exp <= now]
            for k in expired:
                del self._recent[k]
        if data in self._recent:
            return True
        self._recent[data] = now + self._dedupe_window
        return False

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._is_duplicate(data):
            self._dropped_dups += 1
            if self._dropped_dups % 100 == 1:
                log.info("dropped %d duplicate packet(s) so far", self._dropped_dups)
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            preview = data[:80].hex()
            log.warning("dropping malformed packet from %s: %s (hex: %s)", addr[0], e, preview)
            return
        record = {
            "received_at": datetime.now(UTC).isoformat(),
            "src_addr": addr[0],
            "payload": payload,
        }
        self._writer.write(record)
        self._packet_count += 1
        if self._packet_count % 100 == 1:
            log.info(
                "packet #%d type=%s from %s",
                self._packet_count,
                payload.get("type", "?") if isinstance(payload, dict) else "?",
                addr[0],
            )


async def _flush_loop(writer: JsonlWriter, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        writer.flush()


async def _run(port: int, data_dir: Path, flush_interval: float, dedupe_window: float) -> None:
    writer = JsonlWriter(data_dir)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: TempestProtocol(writer, dedupe_window_sec=dedupe_window),
        local_addr=("0.0.0.0", port),
        family=socket.AF_INET,
        allow_broadcast=True,
        reuse_port=True,
    )
    flush_task = asyncio.create_task(_flush_loop(writer, flush_interval))
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        await stop_event.wait()
    finally:
        log.info("shutting down")
        flush_task.cancel()
        transport.close()
        writer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data-dir", type=Path, default=Path("./data"))
    parser.add_argument("--flush-interval", type=float, default=DEFAULT_FLUSH_INTERVAL_SEC)
    parser.add_argument(
        "--dedupe-window",
        type=float,
        default=DEFAULT_DEDUPE_WINDOW_SEC,
        help="Drop bytewise-identical packets seen within this many seconds. Set to 0 to disable.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run(args.port, args.data_dir, args.flush_interval, args.dedupe_window))


if __name__ == "__main__":
    main()
