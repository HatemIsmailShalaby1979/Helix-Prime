"""The read-only audit-trail view: it surfaces the record, and it invents nothing.

The screen exists to answer one question — "what did the core already record for
this correlation id?" — so the tests are about the ways a screen like this misleads:

1. IT MUST SHOW THE RECORD, NOT A READING OF IT. The gate decision, the timestamps
   and the actor handoff have to be the core's own fields, so they are asserted
   against a run the suite actually made rather than against a fixture written here.
2. IT MUST NOT WIDEN THE BOUNDARY. The trail is per-tenant. Another tenant's
   correlation id has to come back as not-found, not as someone else's run.
3. IT MUST NOT BE REACHABLE WITHOUT `ops.view`, like the rest of the ops surface.
4. IT MUST DISTINGUISH "no such run" FROM "nothing recorded", because those are
   different answers and an empty table cannot say which one it is.

One test here is not about the view at all: it pins the reader defect this work
surfaced, where `AuditTrail.list_records` is `ORDER BY rowid ASC LIMIT n` so a
"most recent" reader built on its tail returns the OLDEST rows.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

TestClient = pytest.importorskip("fastapi.testclient").TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration import engine_bridge
from helix_codex_app.security.accounts import (
    DEMO_CLIENT_ID,
    DEMO_DOMAIN_NAME,
    DEMO_TENANT_ID,
    AccountRepository,
    ensure_demo_account,
)
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

SUBMIT_PATH = "/app/api/ops/demo/wfm"
GOOD = {"arrival_rate": 12.5, "average_handling_time": 6.0, "service_level_target": 0.8}

# The lifecycle the core records for one governed demo run, in order. Pinned exactly
# rather than by containment: a trail view that quietly stopped showing one of these
# would still "contain" the rest.
EXPECTED_EVENTS = (
    "workflow_created",
    "workflow_validated",
    "workflow_executing",
    "handler_succeeded",
    "workflow_succeeded",
    "workflow_closed",
)
# The core's own `decision` field per audit row for the same run.
EXPECTED_DECISIONS = ("allowed", "allowed", "allowed", "succeeded", "succeeded")


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    repo.create_domain(DEMO_DOMAIN_NAME, tenant_id=DEMO_TENANT_ID, client_id=DEMO_CLIENT_ID)
    demo = ensure_demo_account(repo, password_hash=hash_password("x"))
    other = repo.create_domain("other.test", tenant_id="tenant-b", client_id="client-b")
    manager = repo.create_account(
        other.domain_id, "boss", role_id="manager", password_hash=hash_password("x")
    )
    employee = repo.create_account(
        other.domain_id, "staffer", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    yield SimpleNamespace(
        conn=conn,
        demo=demo,
        manager=manager,
        employee=employee,
        settings=settings,
        store=SessionStore(conn, settings),
        tmp_path=tmp_path,
        audit_db_path=str(tmp_path / "audit.db"),
    )
    db.close(conn)


@pytest.fixture()
def client(ctx, monkeypatch):
    monkeypatch.setenv("HELIX_DB_PATH", str(ctx.tmp_path / "workflow.db"))
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", ctx.audit_db_path)
    monkeypatch.setenv("HELIX_LOG_PATH", str(ctx.tmp_path / "logs.jsonl"))
    from server.config import get_settings

    get_settings.cache_clear()
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client
    get_settings.cache_clear()


def _session(ctx, account) -> tuple[dict, dict]:
    token, _issued = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _seed(trail, event_type: str):
    """One linked audit record, so the chain stays valid while seeding."""
    from security.audit import AuditRecord

    return AuditRecord.new(
        event_type=event_type,
        actor="seeder",
        actor_type="agent",
        decision="allowed",
        previous_hash=trail.last_hash(),
    )


def _run(ctx, client) -> dict:
    """Make one real governed run and return its report."""
    cookies, headers = _session(ctx, ctx.demo)
    response = client.post(SUBMIT_PATH, cookies=cookies, headers=headers, json=GOOD)
    assert response.status_code == 201
    return response.json()


def test_the_trail_shows_the_core_s_own_record(ctx, client):
    report = _run(ctx, client)
    cookies, _headers = _session(ctx, ctx.demo)

    payload = client.get(f"/app/api/ops/audit/{report['correlation_id']}", cookies=cookies).json()

    assert payload["found"] is True
    assert payload["correlation_id"] == report["correlation_id"]
    assert payload["workflow"]["workflow_id"] == report["workflow_id"]
    assert payload["execution"]["executed"] is True
    assert payload["execution"]["succeeded"] is True
    assert payload["execution"]["state"] == report["state"]
    assert [event["event_type"] for event in payload["events"]] == list(EXPECTED_EVENTS)
    assert tuple(row["decision"] for row in payload["audit"]) == EXPECTED_DECISIONS
    assert payload["chain"]["linked"] is True


def test_the_screen_renders_the_trail_for_a_human(ctx, client):
    report = _run(ctx, client)
    cookies, _headers = _session(ctx, ctx.demo)

    page = client.get(f"/app/ops/audit/{report['correlation_id']}", cookies=cookies)

    assert page.status_code == 200
    assert report["correlation_id"] in page.text
    assert report["workflow_id"] in page.text
    assert "workflow_created" in page.text
    assert "handler_succeeded" in page.text
    assert "allowed" in page.text


def test_the_demo_result_links_to_the_trail(ctx, client):
    """The view has to be reachable from where a reader holds the id."""
    cookies, headers = _session(ctx, ctx.demo)
    page = client.post(
        SUBMIT_PATH,
        cookies=cookies,
        headers={**headers, "hx-request": "true"},
        json=GOOD,
    )

    assert page.status_code == 200
    assert 'href="/app/ops/audit/' in page.text


def test_the_trail_needs_a_session(ctx, client):
    assert client.get("/app/ops/audit/anything").status_code == 401


def test_the_trail_needs_ops_view(ctx, client):
    cookies, _headers = _session(ctx, ctx.employee)

    assert client.get("/app/ops/audit/anything", cookies=cookies).status_code == 403


def test_another_tenants_correlation_id_is_not_found(ctx, client):
    """The trail is per-tenant, and a foreign id must not resolve."""
    report = _run(ctx, client)
    cookies, _headers = _session(ctx, ctx.manager)

    payload = client.get(f"/app/api/ops/audit/{report['correlation_id']}", cookies=cookies).json()

    assert payload["found"] is False
    assert payload["audit"] == []
    assert payload["workflow"] is None


def test_an_unknown_correlation_id_is_reported_not_raised(ctx, client):
    """'No such run' is an answer, and it must read differently from an empty table."""
    cookies, _headers = _session(ctx, ctx.demo)

    page = client.get("/app/ops/audit/00000000000000000000000000000000", cookies=cookies)

    assert page.status_code == 200
    assert "Nothing recorded" in page.text


def test_recent_audit_entries_returns_the_newest_rows_not_the_oldest(ctx, client):
    """The reader defect this view surfaced, pinned so it cannot come back.

    `AuditTrail.list_records` is `ORDER BY rowid ASC LIMIT n`, so asking it for N rows
    returns the OLDEST N and the "tail" of that window is ancient. Measured
    2026-09-27 on the live `security/audit.db`: the reader returned rows from
    2026-08-28 while the newest row was 2026-09-27. The trail is seeded past the old
    scan window here, so an implementation that reads the tail of the oldest N fails.
    """
    _run(ctx, client)

    from security.audit import AuditTrail

    trail = AuditTrail(db_path=ctx.audit_db_path)
    try:
        for _ in range(engine_bridge.AUDIT_SCAN_LIMIT + 100):
            trail.append(_seed(trail, "sentinel_old"))
        trail.append(_seed(trail, "sentinel_new"))
    finally:
        trail.close()

    rows = engine_bridge.recent_audit_entries(limit=5)

    assert [row["event_type"] for row in rows] == ["sentinel_old"] * 4 + ["sentinel_new"]
