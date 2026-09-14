"""The attendance surface: the punch clock screen and the punches API.

GET routes render the attendance page, the record list, and the weekly
summary; the single mutating route is the punch toggle, which reads the
account's current state and opens or closes accordingly. Every punch writes
one governed node through AttendanceService, with the timestamp decided by
the server. The mutating route answers an HTMX fragment under HX-Request so
the button label and the running total update in place.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from helix_codex_app.db import close, connect
from helix_codex_app.modules.attendance.repository import _fmt, _parse
from helix_codex_app.modules.attendance.service import AttendanceService
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.templating import render

attendance_router = APIRouter(
    prefix="/app",
    dependencies=[
        Depends(current_account),
        Depends(require_permission("attendance.punch")),
    ],
)


@attendance_router.get("/attendance", response_model=None)
def attendance_screen(request: Request) -> HTMLResponse:
    """The punch clock page: state, running total, and the week so far."""
    account = _account(request)
    conn = _conn(request)
    try:
        context = _page_context(conn, account)
    finally:
        close(conn)
    return render(request, "attendance.html", context)


@attendance_router.post(
    "/api/attendance/punch",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def punch_route(request: Request) -> JSONResponse | HTMLResponse:
    """Open or close the account's punch, server-deciding the timestamp."""
    account = _account(request)
    conn = _conn(request)
    hx_fragment = None
    try:
        raw = await _payload(request)
        service = AttendanceService(conn)
        action = str(raw.get("action", "")).strip()
        if action not in ("in", "out"):
            action = "out" if service.current_status(account) else "in"
        if action == "in":
            punch = service.punch_in(
                account,
                source=str(raw.get("source", "")).strip() or None,
                device_id=str(raw.get("device_id", "")).strip() or None,
            )
        else:
            punch = service.punch_out(account)
        if request.headers.get("hx-request") == "true":
            context = _punch_context(conn, account)
            hx_fragment = render(request, "partials/punch.html", context)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(punch.to_dict(), status_code=201)


@attendance_router.get("/api/attendance/records", response_model=None)
def records_route(request: Request) -> JSONResponse:
    """Punch records visible to the account inside [from, to)."""
    account = _account(request)
    conn = _conn(request)
    try:
        from_at, to_at = _records_range(request)
        service = AttendanceService(conn)
        records = [record.to_dict() for record in service.list_records(account, from_at, to_at)]
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse({"records": records, "from": from_at, "to": to_at})


@attendance_router.get("/api/attendance/summary", response_model=None)
def summary_route(request: Request) -> JSONResponse:
    """Worked minutes per day plus a total, for the account's visible scope."""
    account = _account(request)
    conn = _conn(request)
    try:
        from_at, to_at = _summary_range(request)
        service = AttendanceService(conn)
        summary = service.summary(account, from_at, to_at)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse(summary)


def _page_context(conn: Any, account: Account) -> dict[str, Any]:
    service = AttendanceService(conn)
    from_at, to_at = _summary_range_defaults()
    weekly = service.summary(account, from_at, to_at)
    records_from, records_to = _records_range_defaults()
    today = service.list_records(account, records_from, records_to)
    return {
        "active_nav": "attendance",
        "account": account,
        "punch": _punch_from_service(service, account),
        "today_minutes": service.today_minutes(account),
        "weekly": weekly,
        "today_records": [record.to_dict() for record in today],
        "week_from": from_at,
        "week_to": to_at,
    }


def _punch_context(conn: Any, account: Account) -> dict[str, Any]:
    service = AttendanceService(conn)
    return {
        "active_nav": "attendance",
        "account": account,
        "punch": _punch_from_service(service, account),
        "today_minutes": service.today_minutes(account),
    }


def _punch_from_service(service: AttendanceService, account: Account) -> dict[str, Any]:
    open_punch = service.current_status(account)
    if open_punch is None:
        return {"open": False, "action": "in", "label": "Punch in", "punched_at": None}
    return {
        "open": True,
        "action": "out",
        "label": "Punch out",
        "punched_at": open_punch.punched_at,
    }


def _records_range(request: Request) -> tuple[str, str]:
    from_at = request.query_params.get("from")
    to_at = request.query_params.get("to")
    if not from_at and not to_at:
        return _records_range_defaults()
    if not from_at or not to_at:
        raise ValueError("from and to must be provided together")
    _parse(from_at)
    _parse(to_at)
    if _parse(to_at) <= _parse(from_at):
        raise ValueError("the window must end after it starts")
    return from_at, to_at


def _summary_range(request: Request) -> tuple[str, str]:
    from_at = request.query_params.get("from")
    to_at = request.query_params.get("to")
    if not from_at and not to_at:
        return _summary_range_defaults()
    if not from_at or not to_at:
        raise ValueError("from and to must be provided together")
    _parse(from_at)
    _parse(to_at)
    if _parse(to_at) <= _parse(from_at):
        raise ValueError("the window must end after it starts")
    return from_at, to_at


def _records_range_defaults() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return _fmt(start), _fmt(start + timedelta(days=1))


def _summary_range_defaults() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    monday = start - timedelta(days=start.weekday())
    return _fmt(monday), _fmt(now)


async def _payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    result: dict[str, Any] = {}
    for key, value in form.multi_items():
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(str(value))
            else:
                result[key] = [existing, str(value)]
        else:
            result[key] = str(value)
    return result


def _account(request: Request) -> Account:
    return request.state.account


def _conn(request: Request):
    return connect(db_path=request.app.state.settings.db_path)
