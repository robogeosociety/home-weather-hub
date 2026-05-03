"""Live STDOUT monitor for the Tempest weather station.

Bind UDP 50222, decode each broadcast, and print one human-readable line per
packet. Exit on Escape, q, or Ctrl+C.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import socket
import sys
import termios
import tty
from datetime import datetime

from home_weather_hub.tempest_decode import format_oneline

DEFAULT_PORT = 50222

_COLORS = {
    "obs_st": "\x1b[32m",  # green
    "rapid_wind": "\x1b[36m",  # cyan
    "hub_status": "\x1b[2m",  # dim
    "device_status": "\x1b[33m",  # yellow
    "evt_strike": "\x1b[1;31m",  # bold red
    "evt_precip": "\x1b[1;34m",  # bold blue
    "light_debug": "\x1b[2m",  # dim
}
_RESET = "\x1b[0m"


class _Monitor(asyncio.DatagramProtocol):
    def __init__(self, types: set[str] | None, use_color: bool):
        self._types = types
        self._color = use_color

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        sock = transport.get_extra_info("socket")
        addr = sock.getsockname()
        print(
            f"# listening on {addr[0]}:{addr[1]}  (Esc / q / Ctrl+C to exit)",
            flush=True,
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            print(f"[{ts}] {addr[0]:>15}  BAD  {data[:80]!r}", flush=True)
            return
        t = payload.get("type", "?") if isinstance(payload, dict) else "?"
        if self._types is not None and t not in self._types:
            return
        line = format_oneline(payload if isinstance(payload, dict) else {"raw": payload})
        prefix = f"[{ts}] {addr[0]:>15}  "
        if self._color and t in _COLORS:
            print(f"{prefix}{_COLORS[t]}{line}{_RESET}", flush=True)
        else:
            print(f"{prefix}{line}", flush=True)


async def _run(port: int, types: set[str] | None, use_color: bool) -> None:
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Monitor(types, use_color),
        local_addr=("0.0.0.0", port),
        family=socket.AF_INET,
        allow_broadcast=True,
        reuse_port=True,
    )

    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    fd: int | None = sys.stdin.fileno() if sys.stdin.isatty() else None
    old_termios = None
    if fd is not None:
        old_termios = termios.tcgetattr(fd)
        tty.setcbreak(fd)

        def _on_stdin() -> None:
            try:
                ch = sys.stdin.read(1)
            except OSError:
                return
            if ch in ("\x1b", "q", "Q"):
                stop_event.set()

        loop.add_reader(fd, _on_stdin)

    try:
        await stop_event.wait()
    finally:
        if fd is not None:
            loop.remove_reader(fd)
            if old_termios is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_termios)
        transport.close()
        print("\n# stopped", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--types",
        help="comma-separated message types to show (default: all). "
        "e.g. obs_st,rapid_wind,evt_strike",
    )
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    types = {t.strip() for t in args.types.split(",")} if args.types else None
    use_color = sys.stdout.isatty() and not args.no_color

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(args.port, types, use_color))


if __name__ == "__main__":
    main()
