"""
Server-sent events — the only async module in the repository.

Everything else in Helix is synchronous by design: 445 sync tests cover the
control plane, and async-ifying ``Engine`` would invalidate every one of them
for no functional gain. Async is needed exactly where a connection stays open
longer than a request, and that is only here.

Design
------
One :class:`asyncio.Queue` per ``correlation_id``. A synchronous worker (the
engine call, run in a thread) publishes to the queue through
:func:`publish_sync`, which is thread-safe; the SSE endpoint awaits it. No
shared mutable state beyond the subscription map, which is guarded by the event
loop's single-threaded execution.

Multi-user presence uses the same bus keyed by ``tenant_id`` — enough for a
self-hosted box, and far cheaper than standing up a broker.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

_MAX_QUEUE_DEPTH = 200


class EventBus:
    """Fan-out bus for one process. Replaceable by a broker later; nothing else changes."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, set[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _bind_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        return self._loop

    def subscribe(self, key: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_DEPTH)
        self._subscribers.setdefault(key, set()).add(queue)
        return queue

    def unsubscribe(self, key: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(key)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(key, None)

    def publish(self, key: str, event: str, data: Dict[str, Any]) -> None:
        """Publish from within the event loop."""
        for queue in list(self._subscribers.get(key, ())):
            if queue.full():
                # Slow consumer: drop the oldest rather than block the producer.
                # A live view that lags is better than a workflow that stalls.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - race
                    pass
            queue.put_nowait({"event": event, "data": data})

    def publish_sync(self, key: str, event: str, data: Dict[str, Any]) -> None:
        """
        Publish from a worker thread.

        ``Queue.put_nowait`` is not thread-safe with respect to the loop's
        internal waiters, so the payload is handed back to the loop.
        """
        loop = self._loop or self._bind_loop()
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self.publish, key, event, data)

    def subscriber_count(self, key: str) -> int:
        return len(self._subscribers.get(key, ()))


_BUS = EventBus()


def get_bus() -> EventBus:
    return _BUS


def encode(event: str, data: Dict[str, Any]) -> str:
    """Format one SSE frame."""
    payload = json.dumps(data, default=str, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
