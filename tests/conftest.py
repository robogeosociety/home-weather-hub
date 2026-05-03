"""Shared pytest fixtures."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture
def free_udp_port() -> int:
    """Reserve and release a UDP port; return the port number for the test to bind.

    There is a small TOCTOU window between close() and the test's bind(), but
    on a single CI runner it has not been a real source of flakes. Revisit
    (e.g. handing the bound socket to the test) if integration tests start
    failing intermittently with EADDRINUSE.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
