"""
SSE stream for one workflow run.

The engine call itself is synchronous and is run in a worker thread; only this
endpoint is async. That keeps 445 sync tests intact while still giving the UI a
live view.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from server import deps
from server.errors import NotFound
from server.features.workflows.repository import WorkflowRepository
from server.sse import encode, get_bus

router = APIRouter(tags=["stream"])

_HEARTBEAT_SECONDS = 15


async def event_stream(request: Request, correlation_id: str):
    """
    Yield SSE frames for one correlation until the client goes away.

    Split out from the route so it can be driven directly in tests: an
    ASGI test client cannot stream an infinite response to completion.
    """
    bus = get_bus()
    queue = bus.subscribe(correlation_id)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                # Comment frame keeps proxies from closing an idle stream.
                yield ": keep-alive\n\n"
                continue
            yield encode(frame["event"], frame["data"])
    finally:
        bus.unsubscribe(correlation_id, queue)


@router.get("/api/stream/{correlation_id}")
async def stream(request: Request, correlation_id: str) -> StreamingResponse:
    return StreamingResponse(
        event_stream(request, correlation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/stream/{correlation_id}/workflow")
def workflow_for_correlation(correlation_id: str) -> dict:
    """Convenience lookup so the console can render a stream without a second call."""
    repo = WorkflowRepository(deps.get_engine())
    for workflow in repo.list_recent(limit=200):
        if workflow.correlation.correlation_id == correlation_id:
            return repo.to_response(workflow)
    raise NotFound(f"no workflow for correlation {correlation_id!r}")
