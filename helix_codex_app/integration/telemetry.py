"""App-to-core telemetry seam.

The only app module besides the bridges that may import parent
observability internals. Sign-in outcomes and HTTP request counts are
recorded into the shared process registry with a fixed label vocabulary,
so the app surface is observable through the same exposition without any
caller-controlled label text ever reaching it.
"""
from __future__ import annotations

from observability.metrics import REGISTRY

_AUTH_EVENTS = ("login_success", "login_failure", "login_throttled", "login_locked")


def record_auth_event(event: str) -> None:
    """Count one sign-in outcome in the shared registry."""
    if event not in _AUTH_EVENTS:
        raise ValueError(
            f"telemetry: unknown auth event {event!r} (expected one of {list(_AUTH_EVENTS)})"
        )
    REGISTRY.record_auth_event(event)


def record_http_request(*, route: str, status: str, method: str, duration: float) -> None:
    """Count one app request and observe its latency in the shared registry."""
    REGISTRY.http_requests.inc(route=route, status=status, method=method)
    REGISTRY.http_duration.observe(duration, route=route)
