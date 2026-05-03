"""FastAPI dashboard API + WebSocket.

Combined process: starts the Tempest UDP listener AND serves HTTP/WS in one
asyncio loop. The listener publishes decoded events to the in-memory
:mod:`home_weather_hub.event_bus`; this module's ``/ws`` endpoint subscribes
to that bus and forwards events to connected dashboard clients.

Single-process design avoids two services contending for UDP 50222 with
``SO_REUSEPORT`` and ships as one OrbStack container.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import random
import socket
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from home_weather_hub.event_bus import EventBus, get_event_bus
from home_weather_hub.store import METRICS, JsonlStore
from home_weather_hub.tempest_decode import DecodedEvtStrike
from home_weather_hub.tempest_listener import (
    DEFAULT_DEDUPE_WINDOW_SEC,
    DEFAULT_FLUSH_INTERVAL_SEC,
    JsonlWriter,
    TempestProtocol,
    _flush_loop,
)

log = logging.getLogger("dashboard_api")

DEFAULT_HTTP_PORT = 8770  # 8000 is commonly held by OrbStack on this Mac
DEFAULT_UDP_PORT = 50222
DEFAULT_DATA_DIR = Path("./data")


# ---- response models ------------------------------------------------------


class HealthResponse(BaseModel):
    ok: bool = True
    udp_port: int
    data_dir: str
    subscribers: int
    started_at: str


class SnapshotResponse(BaseModel):
    events: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Most recent decoded value per event type (obs_st, rapid_wind, ...)",
    )
    metrics: dict[str, float | None] = Field(
        default_factory=dict,
        description="Flat metric registry → latest scalar value (or null)",
    )


class HistoryPoint(BaseModel):
    t: int
    v: float


class HistoryResponse(BaseModel):
    metric: str
    points: list[HistoryPoint]


class StrikeResponse(BaseModel):
    t: int
    distance_km: float
    energy: float


class StrikesResponse(BaseModel):
    strikes: list[StrikeResponse]


class LayoutPayload(BaseModel):
    layouts: dict[str, Any]


class StationConfig(BaseModel):
    lat: float | None
    lng: float | None
    name: str | None
    metric_keys: list[str]


# ---- app factory ----------------------------------------------------------


def _started_at_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_app(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    udp_port: int = DEFAULT_UDP_PORT,
    bind_udp: bool = True,
    static_dir: Path | None = None,
    cors_origins: list[str] | None = None,
    event_bus: EventBus | None = None,
) -> FastAPI:
    bus = event_bus or get_event_bus()
    store = JsonlStore(data_dir)
    started = _started_at_iso()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        listener_transport = None
        flush_task: asyncio.Task | None = None
        if bind_udp:
            writer = JsonlWriter(data_dir)
            loop = asyncio.get_running_loop()
            try:
                listener_transport, _ = await loop.create_datagram_endpoint(
                    lambda: TempestProtocol(
                        writer,
                        dedupe_window_sec=DEFAULT_DEDUPE_WINDOW_SEC,
                        event_bus=bus,
                    ),
                    local_addr=("0.0.0.0", udp_port),
                    family=socket.AF_INET,
                    allow_broadcast=True,
                    reuse_port=True,
                )
                flush_task = asyncio.create_task(_flush_loop(writer, DEFAULT_FLUSH_INTERVAL_SEC))
                log.info("UDP listener bound on 0.0.0.0:%d", udp_port)
            except OSError as e:
                log.warning(
                    "could not bind UDP %d (%s); API still serving cached data", udp_port, e
                )
        try:
            yield
        finally:
            if flush_task is not None:
                flush_task.cancel()
                with contextlib.suppress(BaseException):
                    await flush_task
            if listener_transport is not None:
                listener_transport.close()

    app = FastAPI(title="home-weather-hub dashboard", version="0.1.0", lifespan=lifespan)

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ---- API ----

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            udp_port=udp_port,
            data_dir=str(data_dir),
            subscribers=bus.subscriber_count,
            started_at=started,
        )

    @app.get("/api/station", response_model=StationConfig)
    async def station() -> StationConfig:
        lat = os.environ.get("STATION_LAT")
        lng = os.environ.get("STATION_LNG")
        return StationConfig(
            lat=float(lat) if lat else None,
            lng=float(lng) if lng else None,
            name=os.environ.get("STATION_NAME") or "Tempest Station",
            metric_keys=list(METRICS.keys()),
        )

    @app.get("/api/snapshot", response_model=SnapshotResponse)
    async def snapshot() -> SnapshotResponse:
        snap = store.latest_snapshot()
        return SnapshotResponse(events=snap["events"], metrics=snap["metrics"])

    @app.get("/api/history", response_model=HistoryResponse)
    async def history(
        metric: str,
        since: Annotated[datetime | None, Query()] = None,
        until: Annotated[datetime | None, Query()] = None,
    ) -> HistoryResponse:
        if metric not in METRICS:
            raise HTTPException(status_code=404, detail=f"unknown metric: {metric}")
        until_dt = until or datetime.now(UTC)
        since_dt = since or until_dt - timedelta(hours=24)
        points = store.history(metric, since_dt, until_dt)
        return HistoryResponse(
            metric=metric,
            points=[HistoryPoint(t=p.t, v=p.v) for p in points],
        )

    @app.get("/api/strikes", response_model=StrikesResponse)
    async def strikes(
        since: Annotated[datetime | None, Query()] = None,
    ) -> StrikesResponse:
        since_dt = since or datetime.now(UTC) - timedelta(hours=6)
        items = store.recent_strikes(since_dt)
        return StrikesResponse(
            strikes=[
                StrikeResponse(t=s.t, distance_km=s.distance_km, energy=s.energy) for s in items
            ]
        )

    @app.get("/api/layout")
    async def get_layout() -> JSONResponse:
        return JSONResponse(store.read_layout() or {})

    @app.put("/api/layout")
    async def put_layout(payload: dict) -> JSONResponse:
        store.write_layout(payload)
        return JSONResponse({"ok": True})

    @app.post("/api/_dev/strike")
    async def synthetic_strike(distance_km: float | None = None) -> JSONResponse:
        """Dev-only: inject a fake strike event so the map is demoable without a storm."""
        d = distance_km if distance_km is not None else round(random.uniform(0.5, 30.0), 2)
        evt = DecodedEvtStrike(time_epoch=int(time.time()), distance_km=d, energy=4096)
        bus.publish(evt)
        return JSONResponse({"ok": True, "distance_km": d})

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            async with bus.subscribe() as queue:
                # Send an initial snapshot so the client can paint immediately.
                await websocket.send_text(
                    json.dumps({"type": "snapshot", "data": store.latest_snapshot()})
                )
                while True:
                    event = await queue.get()
                    await websocket.send_text(
                        json.dumps({"type": "event", "data": event.model_dump(mode="json")})
                    )
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("websocket loop crashed")
            with contextlib.suppress(Exception):
                await websocket.close(code=1011)

    # ---- static frontend (prod only) ----

    if static_dir is not None and static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    else:

        @app.get("/")
        async def root_dev_hint(request: Request) -> JSONResponse:
            return JSONResponse(
                {
                    "ok": True,
                    "msg": "API only. In dev, open the Vite server at http://localhost:5189.",
                    "endpoints": [
                        "/api/health",
                        "/api/snapshot",
                        "/api/history?metric=outdoor.air_temp_f",
                        "/api/strikes",
                        "/api/layout",
                        "/api/station",
                        "/ws",
                    ],
                }
            )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_HTTP_PORT, help="HTTP port")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--no-udp",
        action="store_true",
        help="Skip binding UDP — useful when the listener runs in another process.",
    )
    parser.add_argument(
        "--static-dir",
        type=Path,
        default=Path("web/dist"),
        help="Built frontend dir (served at /). Skipped if it doesn't exist.",
    )
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--cors-origin",
        action="append",
        default=["http://localhost:5189", "http://127.0.0.1:5189"],
        help="Origin(s) allowed by CORS (Vite dev server by default).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import uvicorn

    app = create_app(
        data_dir=args.data_dir,
        udp_port=args.udp_port,
        bind_udp=not args.no_udp,
        static_dir=args.static_dir,
        cors_origins=args.cors_origin,
    )
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level=args.log_level.lower())


if __name__ == "__main__":
    main()
