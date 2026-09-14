"""The calendar surface: the month screen, agenda, and the events API.

GET routes render the calendar page and the JSON range query; the mutating
routes write one governed node per action through CalendarService. The page
shows an agenda list on phones and a month grid on wider screens. Every
mutating route accepts a JSON body or an HTMX urlencoded form.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

import helix_codex_app.integration.engine_bridge as engine_bridge
from helix_codex_app.db import close, connect
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.modules.calendar.repository import _fmt, _parse
from helix_codex_app.modules.calendar.service import MANAGER_ROLES, CalendarService
from helix_codex_app.security.accounts import Account, AccountRepository
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.templating import render

calendar_router = APIRouter(
    prefix="/app",
    dependencies=[Depends(current_account), Depends(require_permission("calendar.use"))],
)


@calendar_router.get("/calendar", response_model=None)
def calendar_screen(request: Request) -> HTMLResponse:
    """The calendar month page with the agenda-first responsive view."""
    account = _account(request)
    conn = _conn(request)
    try:
        context = _view_context(request, conn, account)
    finally:
        close(conn)
    return render(request, "calendar.html", {"active_nav": "calendar", **context})


@calendar_router.get("/api/events", response_model=None)
def list_events_route(request: Request) -> JSONResponse:
    """Events visible to the account inside [from, to), start inclusive."""
    account = _account(request)
    conn = _conn(request)
    try:
        from_at, to_at = _range(request)
        service = CalendarService(conn)
        events = [_occurrence_dict(e) for e in service.list_events(account, from_at, to_at)]
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse({"events": events, "from": from_at, "to": to_at})


@calendar_router.post(
    "/api/events",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def create_event_route(request: Request) -> JSONResponse | HTMLResponse:
    """Create an event and record one governed node."""
    account = _account(request)
    conn = _conn(request)
    hx_fragment = None
    try:
        raw = await _payload(request)
        service = CalendarService(conn)
        attendee_ids = _attendee_ids(raw)
        event = service.create_event(
            account,
            title=str(raw.get("title", "")).strip(),
            starts_at=str(raw.get("starts_at", "")).strip(),
            ends_at=str(raw.get("ends_at", "")).strip(),
            kind=str(raw.get("kind", "event")).strip() or "event",
            all_day=_as_bool(raw.get("all_day")),
            location=str(raw.get("location", "")).strip() or None,
            room_id=str(raw.get("room_id", "")).strip() or None,
            recurrence_rule=str(raw.get("recurrence_rule", "")).strip(),
            attendee_account_ids=attendee_ids,
        )
        if request.headers.get("hx-request") == "true":
            from_at, to_at = _range(request)
            context = _view_context(request, conn, account, from_at, to_at)
            hx_fragment = render(request, "partials/calendar_view.html", context)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(_occurrence_dict(event), status_code=201)


@calendar_router.put(
    "/api/events/{event_id}",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def update_event_route(request: Request, event_id: str) -> JSONResponse | HTMLResponse:
    """Update an event, or cancel it when status is cancelled."""
    account = _account(request)
    conn = _conn(request)
    hx_fragment = None
    try:
        raw = await _payload(request)
        service = CalendarService(conn)
        status = str(raw.get("status", "")).strip()
        if status == "cancelled":
            event = service.cancel_event(account, event_id)
        else:
            attendee_ids = _attendee_ids(raw)
            event = service.update_event(
                account,
                event_id,
                title=str(raw.get("title", "")).strip() or None,
                kind=str(raw.get("kind", "")).strip() or None,
                starts_at=str(raw.get("starts_at", "")).strip() or None,
                ends_at=str(raw.get("ends_at", "")).strip() or None,
                all_day=_as_bool(raw.get("all_day")) if raw.get("all_day") is not None else None,
                location=str(raw.get("location", "")).strip() or None,
                room_id=str(raw.get("room_id", "")).strip() or None,
                recurrence_rule=str(raw.get("recurrence_rule", "")).strip() or None,
                attendee_account_ids=attendee_ids,
            )
        if request.headers.get("hx-request") == "true":
            from_at, to_at = _range(request)
            context = _view_context(request, conn, account, from_at, to_at)
            hx_fragment = render(request, "partials/calendar_view.html", context)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(_occurrence_dict(event))


@calendar_router.post(
    "/api/events/{event_id}/respond",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def respond_event_route(request: Request, event_id: str) -> JSONResponse | HTMLResponse:
    """Record an attendee's RSVP."""
    account = _account(request)
    conn = _conn(request)
    hx_fragment = None
    try:
        raw = await _payload(request)
        response = str(raw.get("response", "")).strip()
        service = CalendarService(conn)
        event = service.respond(account, event_id, response)
        if request.headers.get("hx-request") == "true":
            from_at, to_at = _range(request)
            context = _view_context(request, conn, account, from_at, to_at)
            hx_fragment = render(request, "partials/calendar_view.html", context)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    if hx_fragment is not None:
        return hx_fragment
    return JSONResponse(_occurrence_dict(event))


@calendar_router.get("/api/oncall", response_model=None)
def oncall_status_route(request: Request) -> JSONResponse:
    """The on-call state: who is covering, the account's shifts, and the WFM
    staffing coverage read through the engine bridge.

    The engine read is fail-closed: when the WFM engine cannot be reached,
    EngineUnavailableError propagates and the caller receives a 503 instead
    of a roster that might be wrong.
    """
    account = _account(request)
    conn = _conn(request)
    try:
        service = CalendarService(conn)
        coverage = service.current_oncall(account.tenant_id, datetime.now(timezone.utc).isoformat())
        next_shifts = [shift.to_dict() for shift in service.next_shifts(account)]
        now = datetime.now(timezone.utc)
        wfm = engine_bridge.wfm_coverage(
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            correlation_id="wfm-oncall",
            actor=account.account_id,
            from_at=_fmt(now),
            to_at=_fmt(now + timedelta(days=1)),
        )
        return JSONResponse(
            {
                "coverage": coverage.to_dict(),
                "next_shifts": next_shifts,
                "wfm": wfm,
            }
        )
    except PermissionDenied as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    finally:
        close(conn)


@calendar_router.post(
    "/api/oncall/shifts",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def create_shift_route(request: Request) -> JSONResponse:
    """Create an on-call shift and record one governed node. Manager only."""
    account = _account(request)
    conn = _conn(request)
    try:
        raw = await _payload(request)
        service = CalendarService(conn)
        shift = service.create_shift(
            account,
            starts_at=str(raw.get("starts_at", "")).strip(),
            ends_at=str(raw.get("ends_at", "")).strip(),
            primary_account_id=str(raw.get("primary_account_id", "")).strip(),
            backup_account_id=str(raw.get("backup_account_id", "")).strip(),
        )
        return JSONResponse(shift.to_dict(), status_code=201)
    except NotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)


def _view_context(
    request: Request,
    conn: Any,
    account: Account,
    from_at: str | None = None,
    to_at: str | None = None,
) -> dict[str, Any]:
    if from_at is None or to_at is None:
        from_at, to_at = _default_range()
    service = CalendarService(conn)
    occurrences = [_occurrence_dict(e) for e in service.list_events(account, from_at, to_at)]
    for occurrence in occurrences:
        occurrence["my_response"] = next(
            (
                attendee["response"]
                for attendee in occurrence["attendees"]
                if attendee["account_id"] == account.account_id
            ),
            "",
        )
        occurrence["cancellable"] = (
            occurrence["creator_account_id"] == account.account_id
            or account.role_id in MANAGER_ROLES
        )
    members = {
        a.account_id: a.display_name or a.username
        for a in AccountRepository(conn).list_accounts(account.domain_id)
    }
    by_date: dict[str, list[dict[str, Any]]] = {}
    for occurrence in occurrences:
        by_date.setdefault(occurrence["starts_at"][:10], []).append(occurrence)
    month_start = datetime(_parse(from_at).year, _parse(from_at).month, 1, tzinfo=timezone.utc)
    month_end = _add_months(month_start, 1)
    return {
        "account": account,
        "occurrences": occurrences,
        "members": members,
        "by_date": by_date,
        "weeks": _weeks(month_start, month_end, by_date),
        "month_label": month_start.strftime("%B %Y"),
        "from_at": from_at,
        "to_at": to_at,
    }


def _weeks(
    month_start: datetime,
    month_end: datetime,
    by_date: dict[str, list[dict[str, Any]]],
) -> list[list[dict[str, Any]]]:
    """The month's calendar grid as week rows of day cells."""
    cells: list[dict[str, Any] | None] = [None] * month_start.weekday()
    day = month_start
    while day < month_end:
        key = day.date().isoformat()
        cells.append(
            {
                "day": day.day,
                "date": key,
                "events": by_date.get(key, []),
            }
        )
        day = day + timedelta(days=1)
    while len(cells) % 7:
        cells.append(None)
    return [cells[index : index + 7] for index in range(0, len(cells), 7)]


def _default_range() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return _fmt(start), _fmt(_add_months(start, 1))


def _add_months(value: datetime, months: int) -> datetime:
    index = value.month - 1 + months
    return datetime(
        value.year + index // 12,
        index % 12 + 1,
        1,
        tzinfo=timezone.utc,
    )


def _range(request: Request) -> tuple[str, str]:
    from_at = request.query_params.get("from")
    to_at = request.query_params.get("to")
    if not from_at and not to_at:
        return _default_range()
    if not from_at or not to_at:
        raise ValueError("from and to must be provided together")
    _parse(from_at)
    _parse(to_at)
    return from_at, to_at


def _occurrence_dict(event: Any) -> dict[str, Any]:
    return event.to_dict()


def _attendee_ids(raw: dict[str, Any]) -> tuple[str, ...]:
    attendees = raw.get("attendee")
    if attendees is None:
        json_ids = raw.get("attendee_account_ids")
        if isinstance(json_ids, list):
            attendees = json_ids
    if attendees is None:
        return ()
    if not isinstance(attendees, list):
        attendees = [attendees]
    return tuple(str(account_id) for account_id in attendees if str(account_id).strip())


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "on", "yes")


async def _payload(request: Request) -> dict[str, Any]:
    """The request body as a mapping, from JSON or an HTMX urlencoded form.

    Repeated form fields (an ambiguous less common value like "attendee")
    collapse into a list instead of silently keeping only the last value.
    """
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
