"""Calendar and events tests (P4.1).

Service-level tests prove the calendar invariants: one governed node per
event write, visibility limited to the creator and invited attendees,
[from, to) range semantics, soft cancellation that hides the event from
listings while keeping its rows and nodes, the steward gate on update and
cancel, exactly-one event_invite notification per new attendee, and daily
and weekly recurrence expansion on read. HTTP tests drive the mounted
calendar router through TestClient for the screens, the JSON contract, the
HTMX fragment path, CSRF, and cross-tenant isolation.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.modules.calendar.service import CalendarService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

FROM = "2026-09-01T00:00:00+00:00"
TO = "2026-10-01T00:00:00+00:00"


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    owner = repo.create_account(
        domain_a.domain_id, "owner", role_id="owner", password_hash=hash_password("x")
    )
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    omar = repo.create_account(
        domain_a.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    layla = repo.create_account(
        domain_a.domain_id, "layla", role_id="employee", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id, "ghada", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    service = CalendarService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        owner=owner,
        amira=amira,
        omar=omar,
        layla=layla,
        ghada=ghada,
        settings=settings,
        store=store,
        service=service,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _login(ctx, account) -> tuple[dict, dict]:
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _node_count(conn, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM nodes WHERE kind = ?", (kind,)).fetchone()[0]


def _notification_count(conn, kind: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM notifications WHERE kind = ?", (kind,)).fetchone()[0]


def _latest_node(conn, kind: str) -> dict:
    row = conn.execute(
        "SELECT body FROM nodes WHERE kind = ? ORDER BY rowid DESC LIMIT 1", (kind,)
    ).fetchone()
    return json.loads(row["body"])


def _event_args(**overrides):
    args = {
        "title": "Intake meeting",
        "starts_at": "2026-09-01T09:00:00+00:00",
        "ends_at": "2026-09-01T10:00:00+00:00",
    }
    args.update(overrides)
    return args


# --- service-level tests ---


def test_create_event_writes_one_node(ctx):
    before = _node_count(ctx.conn, "event")
    event = ctx.service.create_event(ctx.amira, **_event_args())
    assert event.title == "Intake meeting"
    assert event.status == "confirmed"
    assert event.creator_account_id == ctx.amira.account_id
    assert event.attendees == ()
    assert _node_count(ctx.conn, "event") == before + 1


def test_creator_sees_own_event_without_attendees(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    got = ctx.service.get_event(ctx.amira, event.event_id)
    assert got.event_id == event.event_id


def test_non_attendee_same_tenant_cannot_view(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    with pytest.raises(Exception) as exc:
        ctx.service.get_event(ctx.layla, event.event_id)
    assert exc.value.__class__.__name__ == "NotFoundError"


def test_attendee_can_view(ctx):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    got = ctx.service.get_event(ctx.omar, event.event_id)
    assert got.event_id == event.event_id
    assert got.attendees[0].account_id == ctx.omar.account_id
    assert got.attendees[0].response == "pending"


def test_foreign_tenant_event_invisible(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    with pytest.raises(Exception) as exc:
        ctx.service.get_event(ctx.ghada, event.event_id)
    assert exc.value.__class__.__name__ == "NotFoundError"


def test_foreign_tenant_list_is_empty(ctx):
    ctx.service.create_event(ctx.amira, **_event_args())
    events = ctx.service.list_events(ctx.ghada, FROM, TO)
    assert events == []


def test_range_is_inclusive_of_start_exclusive_of_end(ctx):
    inside = ctx.service.create_event(ctx.amira, **_event_args())
    at_end = ctx.service.create_event(
        ctx.amira,
        **_event_args(
            title="At the end",
            starts_at="2026-10-01T00:00:00+00:00",
            ends_at="2026-10-01T01:00:00+00:00",
        ),
    )
    events = ctx.service.list_events(ctx.amira, FROM, TO)
    titles = [e.title for e in events]
    assert inside.title in titles
    assert at_end.title not in titles


def test_cancelled_event_excluded_from_range(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    ctx.service.cancel_event(ctx.amira, event.event_id)
    assert ctx.service.list_events(ctx.amira, FROM, TO) == []


def test_rsvp_updates_attendee_row(ctx):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    updated = ctx.service.respond(ctx.omar, event.event_id, "yes")
    assert updated.attendees[0].response == "yes"


def test_rsvp_by_non_attendee_not_found(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    with pytest.raises(Exception) as exc:
        ctx.service.respond(ctx.layla, event.event_id, "yes")
    assert exc.value.__class__.__name__ == "NotFoundError"


def test_rsvp_invalid_response_rejected(ctx):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    with pytest.raises(ValueError, match="response"):
        ctx.service.respond(ctx.omar, event.event_id, "maybe!")


def test_rsvp_writes_event_response_node(ctx):
    before = _node_count(ctx.conn, "event_response")
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    ctx.service.respond(ctx.omar, event.event_id, "maybe")
    assert _node_count(ctx.conn, "event_response") == before + 1


def test_cancel_keeps_row_and_records_cancelled_node(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    cancelled = ctx.service.cancel_event(ctx.amira, event.event_id)
    assert cancelled.status == "cancelled"
    row = ctx.conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_id = ?", (event.event_id,)
    ).fetchone()[0]
    assert row == 1
    node = _latest_node(ctx.conn, "event")
    assert node["status"] == "cancelled"
    assert node["event_id"] == event.event_id


def test_cancel_by_non_steward_denied(ctx):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    with pytest.raises(PermissionDenied):
        ctx.service.cancel_event(ctx.omar, event.event_id)


def test_update_by_non_steward_denied(ctx):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    with pytest.raises(PermissionDenied):
        ctx.service.update_event(ctx.omar, event.event_id, title="Hijack")


def test_manager_can_act_when_visible(ctx):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.owner.account_id,))
    )
    updated = ctx.service.update_event(ctx.owner, event.event_id, title="Rescheduled")
    assert updated.title == "Rescheduled"


def test_update_changes_fields_and_records_node(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    updated = ctx.service.update_event(
        ctx.amira,
        event.event_id,
        title="Renamed",
        location="Room B",
        starts_at="2026-09-02T11:00:00+00:00",
        ends_at="2026-09-02T12:00:00+00:00",
    )
    assert updated.title == "Renamed"
    assert updated.location == "Room B"
    assert updated.starts_at == "2026-09-02T11:00:00+00:00"
    node = _latest_node(ctx.conn, "event")
    assert node["changed"]["title"] == "Renamed"
    assert node["changed"]["location"] == "Room B"


def test_add_attendee_notifies_once_and_not_on_repeat(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    ctx.service.update_event(ctx.amira, event.event_id, attendee_account_ids=(ctx.omar.account_id,))
    assert _notification_count(ctx.conn, "event_invite") == 1
    ctx.service.update_event(ctx.amira, event.event_id, attendee_account_ids=(ctx.omar.account_id,))
    assert _notification_count(ctx.conn, "event_invite") == 1


def test_self_attendee_never_notifies(ctx):
    ctx.service.create_event(ctx.amira, **_event_args(attendee_account_ids=(ctx.amira.account_id,)))
    assert _notification_count(ctx.conn, "event_invite") == 0


def test_daily_recurrence_expands(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args(recurrence_rule="daily"))
    events = ctx.service.list_events(ctx.amira, FROM, TO)
    assert len(events) == 30
    assert all(e.event_id == event.event_id for e in events)
    assert events[0].starts_at == "2026-09-01T09:00:00+00:00"
    assert events[1].starts_at == "2026-09-02T09:00:00+00:00"
    assert events[1].ends_at == "2026-09-02T10:00:00+00:00"


def test_weekly_recurrence_expands(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args(recurrence_rule="weekly"))
    events = ctx.service.list_events(ctx.amira, FROM, TO)
    assert len(events) == 5
    assert {e.starts_at for e in events} == {
        f"2026-09-{day:02d}T09:00:00+00:00" for day in (1, 8, 15, 22, 29)
    }


def test_single_event_does_not_expand(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    events = ctx.service.list_events(ctx.amira, FROM, TO)
    assert len(events) == 1
    assert events[0].event_id == event.event_id


def test_invalid_recurrence_rejected(ctx):
    with pytest.raises(ValueError, match="recurrence_rule"):
        ctx.service.create_event(ctx.amira, **_event_args(recurrence_rule="monthly"))


def test_blank_title_rejected(ctx):
    with pytest.raises(ValueError, match="title"):
        ctx.service.create_event(ctx.amira, **_event_args(title="   "))


def test_end_at_or_before_start_rejected(ctx):
    with pytest.raises(ValueError, match="after it starts"):
        ctx.service.create_event(
            ctx.amira,
            **_event_args(
                starts_at="2026-09-01T10:00:00+00:00",
                ends_at="2026-09-01T10:00:00+00:00",
            ),
        )


def test_unknown_attendee_rejected(ctx):
    with pytest.raises(ValueError, match="unknown attendee"):
        ctx.service.create_event(
            ctx.amira, **_event_args(attendee_account_ids=(ctx.ghada.account_id,))
        )


def test_all_day_flag_round_trip(ctx):
    event = ctx.service.create_event(ctx.amira, **_event_args(all_day=True))
    assert event.all_day is True
    assert ctx.service.get_event(ctx.amira, event.event_id).all_day is True


# --- HTTP tests ---


def test_calendar_screen_renders(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    response = client.get("/app/calendar", cookies=cookies)
    assert response.status_code == 200
    assert "Calendar" in response.text
    assert "calendar-view" in response.text
    assert "Create event" in response.text


def test_calendar_screen_requires_auth(ctx, client):
    response = client.get("/app/calendar")
    assert response.status_code == 401


def test_calendar_screen_shows_events(ctx, client):
    ctx.service.create_event(ctx.amira, **_event_args())
    cookies, headers = _login(ctx, ctx.amira)
    response = client.get("/app/calendar", cookies=cookies)
    assert response.status_code == 200
    assert "Intake meeting" in response.text


def test_create_event_api_writes_and_audits(ctx, client):
    before = _node_count(ctx.conn, "event")
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/events",
        json=_event_args(attendee_account_ids=[ctx.omar.account_id]),
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Intake meeting"
    assert payload["status"] == "confirmed"
    assert _node_count(ctx.conn, "event") == before + 1
    assert _notification_count(ctx.conn, "event_invite") == 1


def test_create_event_api_requires_csrf(ctx, client):
    cookies, _ = _login(ctx, ctx.amira)
    response = client.post("/app/api/events", json=_event_args(), cookies=cookies)
    assert response.status_code == 403


def test_create_event_api_rejects_bad_payload(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/events",
        json=_event_args(title=""),
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 400


def test_list_events_api_returns_range(ctx, client):
    ctx.service.create_event(ctx.amira, **_event_args())
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/api/events", params={"from": FROM, "to": TO}, cookies=cookies)
    assert response.status_code == 200
    payload = response.json()
    assert payload["from"] == FROM
    assert payload["to"] == TO
    assert [e["title"] for e in payload["events"]] == ["Intake meeting"]


def test_list_events_api_requires_both_range_edges(ctx, client):
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/api/events", params={"from": FROM}, cookies=cookies)
    assert response.status_code == 400


def test_respond_route_updates_row(ctx, client):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    cookies, headers = _login(ctx, ctx.omar)
    response = client.post(
        f"/app/api/events/{event.event_id}/respond",
        data={"response": "yes"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["attendees"][0]["response"] == "yes"


def test_respond_route_invalid_response_is_400(ctx, client):
    event = ctx.service.create_event(
        ctx.amira, **_event_args(attendee_account_ids=(ctx.omar.account_id,))
    )
    cookies, headers = _login(ctx, ctx.omar)
    response = client.post(
        f"/app/api/events/{event.event_id}/respond",
        data={"response": ""},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 400


def test_respond_route_by_non_attendee_is_404(ctx, client):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    cookies, headers = _login(ctx, ctx.layla)
    response = client.post(
        f"/app/api/events/{event.event_id}/respond",
        data={"response": "yes"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_cancel_via_put_hides_event_from_range(ctx, client):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    cookies, headers = _login(ctx, ctx.amira)
    put = client.put(
        f"/app/api/events/{event.event_id}",
        data={"status": "cancelled"},
        cookies=cookies,
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json()["status"] == "cancelled"
    listed = client.get("/app/api/events", params={"from": FROM, "to": TO}, cookies=cookies)
    assert listed.json()["events"] == []
    assert _node_count(ctx.conn, "event") == 2


def test_foreign_tenant_event_is_404(ctx, client):
    event = ctx.service.create_event(ctx.amira, **_event_args())
    cookies, headers = _login(ctx, ctx.ghada)
    response = client.put(
        f"/app/api/events/{event.event_id}",
        data={"status": "cancelled"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 404


def test_create_event_htmx_fragment(ctx, client):
    cookies, headers = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/events",
        data=_event_args(),
        cookies=cookies,
        headers={**headers, "hx-request": "true"},
    )
    assert response.status_code == 200
    assert "calendar-view" in response.text
    assert "Intake meeting" in response.text
