"""Notification screens, the JSON API, and the live badge SSE stream.

Every route runs behind current_account.  The SSE stream is keyed by
account_id — one queue per user, all open tabs share the same badge.
The initial frame carries the unread count so the badge is correct before
any subsequent publish arrives.  Mutating routes carry require_csrf.
The stream lives under /app/api/notifications/stream so the service
worker's existing stream exclusion applies (see sw.js).
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from helix_codex_app.db import close, connect
from helix_codex_app.integration.sse_bridge import encode, subscribe, unsubscribe
from helix_codex_app.modules.notifications.schemas import NotificationOut
from helix_codex_app.modules.notifications.service import NotificationService
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf
from helix_codex_app.templating import render

notifications_router = APIRouter(prefix="/app", dependencies=[Depends(current_account)])

_HEARTBEAT_SECONDS = 15


# -- screens -------------------------------------------------------------------


@notifications_router.get("/notifications", response_model=None)
def notifications_screen(request: Request) -> HTMLResponse:
    """The notification list page."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = NotificationService(conn)
        notifications = service.list_for(account)
        unread = service.unread_count(account)
    finally:
        close(conn)
    return render(
        request,
        "notifications.html",
        {
            "active_nav": "notifications",
            "account": account,
            "notifications": [NotificationOut.from_notification(n) for n in notifications],
            "unread": unread,
        },
    )


# -- JSON API ------------------------------------------------------------------


@notifications_router.get("/api/notifications", response_model=None)
def list_notifications(request: Request) -> JSONResponse:
    """Every notification for the caller, newest first."""
    account = _account(request)
    conn = _conn(request)
    try:
        notifications = NotificationService(conn).list_for(account)
    finally:
        close(conn)
    return JSONResponse(
        [NotificationOut.from_notification(n).model_dump(mode="json") for n in notifications]
    )


@notifications_router.post(
    "/api/notifications/read-all",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
def mark_all_read_route(request: Request) -> JSONResponse:
    """Stamp every unread notification for the caller read."""
    account = _account(request)
    conn = _conn(request)
    try:
        NotificationService(conn).mark_all_read(account)
    finally:
        close(conn)
    return JSONResponse({"ok": True})


@notifications_router.post(
    "/api/notifications/{notification_id}/read",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
def mark_read_route(request: Request, notification_id: str) -> JSONResponse:
    """Stamp one notification read.  Idempotent — a second call is a no-op."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = NotificationService(conn)
        notification = service.repo.get(notification_id, account.account_id)
        if notification is None:
            return JSONResponse(
                {"error": "no such notification"},
                status_code=404,
            )
        service.mark_read(account, notification_id)
    finally:
        close(conn)
    return JSONResponse({"ok": True})


# -- SSE stream ----------------------------------------------------------------


@notifications_router.get("/api/notifications/stream")
async def notification_stream(request: Request) -> StreamingResponse:
    """The live badge stream for one account.  Non-membership checks do not
    apply here — every authenticated identity streams on their own account."""
    account = _account(request)
    conn = _conn(request)
    try:
        unread = NotificationService(conn).unread_count(account)
    finally:
        close(conn)
    return StreamingResponse(
        notification_event_stream(request, account.account_id, unread),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def notification_event_stream(request: Any, account_id: str, initial_unread: int):
    """Yield SSE frames for the account's badge until disconnect.

    Split out from the route so tests can drive it directly — a test
    client cannot stream an infinite response.
    """
    queue = subscribe(account_id)
    try:
        yield encode("unread_count", {"unread": initial_unread})
        while True:
            if await request.is_disconnected():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield encode(frame["event"], frame["data"])
    finally:
        unsubscribe(account_id, queue)


def _account(request: Request) -> Account:
    return request.state.account


def _conn(request: Request):
    return connect(db_path=request.app.state.settings.db_path)
