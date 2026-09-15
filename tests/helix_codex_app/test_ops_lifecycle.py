"""The operations lifecycle, end to end (P6.5).

Submit, approve, refuse, close — one workflow of each, through the real app and
the real governed engine, with the correlation id checked after every step. The
close step is driven through the shared engine provider the app itself uses,
because the app deliberately exposes no execute route: execution is the core's
job once a second person has approved.

The states below were observed against the real engine, not read off a diagram:
submit lands at awaiting_approval, approval releases the gate straight to
executing, execution closes the workflow, and a refusal sends it to dead_letter.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore

CAPABILITY = "wfm_forecast"


def _baseline_payload() -> dict:
    """The WFM engine's canonical sample payload.

    Execution needs a payload the handler can actually run. An empty one fails
    the handler and the workflow goes to dead_letter, which is correct engine
    behaviour but not the path this test is proving.
    """
    from engines.contracts import ENGINE_BASELINE_PAYLOADS

    return dict(ENGINE_BASELINE_PAYLOADS["wfm"])


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("academy.test", tenant_id="tenant-a", client_id="client-a")
    manager = repo.create_account(
        domain.domain_id, "layla", role_id="manager", password_hash=hash_password("x")
    )
    owner = repo.create_account(
        domain.domain_id, "own", role_id="owner", password_hash=hash_password("x")
    )
    employee = repo.create_account(
        domain.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        manager=manager,
        owner=owner,
        employee=employee,
        settings=settings,
        store=store,
        tmp_path=tmp_path,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx, monkeypatch):
    monkeypatch.setenv("HELIX_DB_PATH", str(ctx.tmp_path / "workflow.db"))
    monkeypatch.setenv("HELIX_AUDIT_DB_PATH", str(ctx.tmp_path / "audit.db"))
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


def _submit(client, ctx, account, *, payload: dict | None = None) -> dict:
    cookies, headers = _session(ctx, account)
    response = client.post(
        "/app/api/ops/workflows",
        json={"capability": CAPABILITY, "input_payload": payload or {}},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _decide(client, ctx, account, workflow_id: str, *, decision: str, reason: str) -> dict:
    cookies, headers = _session(ctx, account)
    response = client.post(
        f"/app/api/ops/workflows/{workflow_id}/approve",
        json={"decision": decision, "reason": reason},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_submit_approve_and_close_keeps_the_correlation_id_throughout(client, ctx):
    from server.deps import get_provider

    submitted = _submit(client, ctx, ctx.manager, payload=_baseline_payload())
    correlation = submitted["correlation_id"]
    assert submitted["state"] == "awaiting_approval"

    approved = _decide(
        client, ctx, ctx.owner, submitted["workflow_id"], decision="approve", reason="evidence holds"
    )
    assert approved["state"] == "executing"
    assert approved["correlation_id"] == correlation

    engine = get_provider().engine
    executed = engine.execute(submitted["workflow_id"])
    assert executed.state == "closed"
    assert executed.correlation.correlation_id == correlation

    cookies, _ = _session(ctx, ctx.owner)
    fetched = client.get(
        f"/app/api/ops/workflows/{submitted['workflow_id']}", cookies=cookies
    ).json()
    assert fetched["state"] == "closed"
    assert fetched["correlation_id"] == correlation


def test_a_refusal_stops_the_workflow_and_keeps_the_correlation_id(client, ctx):
    submitted = _submit(client, ctx, ctx.manager)
    correlation = submitted["correlation_id"]

    refused = _decide(
        client, ctx, ctx.owner, submitted["workflow_id"], decision="reject", reason="not this quarter"
    )
    assert refused["state"] == "dead_letter"
    assert refused["correlation_id"] == correlation

    cookies, _ = _session(ctx, ctx.owner)
    fetched = client.get(
        f"/app/api/ops/workflows/{submitted['workflow_id']}", cookies=cookies
    ).json()
    assert fetched["state"] == "dead_letter"
    assert fetched["correlation_id"] == correlation


def test_a_refused_workflow_cannot_be_executed_afterwards(client, ctx):
    """A denial is a stop, not a pause: the gate will not re-open the workflow."""
    from server.deps import get_provider

    submitted = _submit(client, ctx, ctx.manager)
    _decide(
        client, ctx, ctx.owner, submitted["workflow_id"], decision="reject", reason="no"
    )
    engine = get_provider().engine
    with pytest.raises(ValueError):
        engine.execute(submitted["workflow_id"])


def test_the_submitter_cannot_close_their_own_request(client, ctx):
    """Separation of duties holds at every step, not just at the gate."""
    submitted = _submit(client, ctx, ctx.manager)
    cookies, headers = _session(ctx, ctx.manager)
    response = client.post(
        f"/app/api/ops/workflows/{submitted['workflow_id']}/approve",
        json={"decision": "approve"},
        cookies=cookies,
        headers=headers,
    )
    assert response.status_code >= 400
    cookies, _ = _session(ctx, ctx.manager)
    still = client.get(
        f"/app/api/ops/workflows/{submitted['workflow_id']}", cookies=cookies
    ).json()
    assert still["state"] == "awaiting_approval"


def test_each_workflow_gets_its_own_correlation_id(client, ctx):
    first = _submit(client, ctx, ctx.manager)
    second = _submit(client, ctx, ctx.manager)
    assert first["correlation_id"] != second["correlation_id"]


def test_the_lifecycle_leaves_an_audit_row_for_the_correlation_id(client, ctx):
    """The correlation id is the thread to the audit trail, so it must be there."""
    from helix_codex_app.integration import engine_bridge

    submitted = _submit(client, ctx, ctx.manager)
    _decide(
        client, ctx, ctx.owner, submitted["workflow_id"], decision="approve", reason="auditable"
    )
    rows = [
        row
        for row in engine_bridge.recent_audit_entries(limit=500)
        if row.get("correlation_id") == submitted["correlation_id"]
    ]
    assert rows, "no audit row carries the workflow's correlation id"
