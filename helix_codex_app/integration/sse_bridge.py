"""The parent SSE EventBus, exposed through the integration seam.

Chat and the future notification centre stream over the parent's one
process-wide EventBus, keyed by conversation_id here and account_id there.
The import belongs in this file and nowhere else under helix_codex_app: the
seam rule says integration/ is the only package that may touch parent
internals. There is exactly one bus per process; a broker becomes necessary
only when the app grows past one process, and that is a documented later
problem (see repomap.md), not something to build today.
"""
from __future__ import annotations

import asyncio
from typing import Any

from server.sse import encode as _encode
from server.sse import get_bus

__all__ = [
    "encode",
    "publish",
    "publish_sync",
    "subscribe",
    "subscriber_count",
    "unsubscribe",
]


def subscribe(key: str) -> asyncio.Queue:
    """Open a queue on the bus key. The caller owns the queue and must
    unsubscribe it when the connection closes."""
    return get_bus().subscribe(key)


def unsubscribe(key: str, queue: asyncio.Queue) -> None:
    """Remove one queue from a key. Safe to call twice."""
    get_bus().unsubscribe(key, queue)


def publish(key: str, event: str, data: dict[str, Any]) -> None:
    """Publish a frame from inside the event loop."""
    get_bus().publish(key, event, data)


def publish_sync(key: str, event: str, data: dict[str, Any]) -> None:
    """Publish a frame from a worker thread."""
    get_bus().publish_sync(key, event, data)


def subscriber_count(key: str) -> int:
    """How many queues are listening on a key today."""
    return get_bus().subscriber_count(key)


def encode(event: str, data: dict[str, Any]) -> str:
    """Format one SSE frame."""
    return _encode(event, data)
