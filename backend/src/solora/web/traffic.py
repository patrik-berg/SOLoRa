"""Local-only observation delivery. No radio operations or packet injection API."""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from solora.application.system_settings import SystemSettingsService
from solora.application.traffic import TrafficBuffer
from solora.domain.protocol import PROTOCOL_VERSION
from solora.version import APP_VERSION
from solora.web.routes import SystemRepositoryDependency

router = APIRouter(prefix="/api/traffic", tags=["diagnostics"])


async def events(buffer: TrafficBuffer, request: Request) -> AsyncGenerator[str]:
    """Bounded deltas with a fresh snapshot on every EventSource reconnect."""
    cursor = -1
    ticks = 0
    while not await request.is_disconnected():
        snapshot = buffer.snapshot(max(cursor, 0))
        revision = snapshot["revision"]
        if revision != cursor:
            yield f"event: traffic\ndata: {json.dumps(snapshot)}\n\n"
            cursor = revision
        elif ticks % 15 == 0:
            yield ": local stream keepalive\n\n"
        ticks += 1
        await asyncio.sleep(1)  # local SSE cadence only; no radio poll or retry


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    return StreamingResponse(
        events(request.app.state.traffic, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("")
def snapshot(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.traffic.snapshot(), headers={"Cache-Control": "no-store"})


@router.delete("")
def clear(request: Request) -> JSONResponse:
    request.app.state.traffic.clear()
    return snapshot(request)


@router.get("/export")
def export(request: Request, repository: SystemRepositoryDependency) -> JSONResponse:
    identity = SystemSettingsService(repository).get_identity()
    timestamp = datetime.now(UTC)
    return JSONResponse(
        {
            "format": "SOLoRa Traffic Log",
            "application_version": APP_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "export_timestamp": timestamp.isoformat(),
            "system_name": identity.system_name,
            "system_role": identity.system_role,
            **request.app.state.traffic.snapshot(),
        },
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": (
                f'attachment; filename="solora-traffic-{timestamp:%Y-%m-%dT%H%M%SZ}.json"'
            ),
        },
    )
