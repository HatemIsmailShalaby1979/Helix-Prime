"""
Emergency-stop (kill switch) tests — H1.5 / G18.

A platform whose value proposition is provable restraint must be able to halt
itself. These tests pin the five required behaviours plus the fail-closed
rule: engaged halts deny committal actions and are audited; reads (and
cancellation, the safe direction) keep working; release restores committal;
tenant-scoped halts do not touch other tenants; the halt engagement itself is
auditable; an unreadable flag is treated as engaged.
"""
from __future__ import annotations

import secrets

import pytest

from contracts.task import Approval, CorrelationContext, TaskRequest
from control_plane.engine import Engine
from control_plane.kill_switch import KillSwitch, KillSwitchEngaged
from control_plane.store import Store
from control_plane.workflow import WorkflowState
from security.audit import AuditTrail

FIXED_TS = "2026-08-27T18:00:00Z"


def _corr(cid, tenant="helix-prime"):
    return CorrelationContext(
        correlation_id=cid,
        idempotency_key=f"idem_{cid}",
        tenant_id=tenant,
        client_id="Account Alpha",
        created_at=FIXED_TS,
    )


def _request(cid, tenant="helix-prime", requires_approval=False):
    return TaskRequest(
        request_id=f"req_{cid}",
        correlation=_corr(cid, tenant),
        requesting_actor="suby",
        owning_role_id="ops_gm",
        capability="ops_execution",
        input_payload={},
        requires_approval=requires_approval,
        status="proposed",
        created_at=FIXED_TS,
        client_id="Account Alpha",
    )


def _engine(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(
        store=store,
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    engine.register_handler("ops_execution", lambda wf: {"ok": True})
    return engine


def _audit_event_types(audit_db_path):
    trail = AuditTrail(db_path=audit_db_path)
    try:
        return [(r.event_type, r.decision, r.actor) for r in trail.list_records(limit=200)]
    finally:
        trail.close()


def test_engaged_submit_denied_and_audited(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.kill_switch.engage("incident drill", "operator")
        with pytest.raises(KillSwitchEngaged):
            engine.submit(_request("deny1"))
        events = _audit_event_types(str(tmp_path / "audit.db"))
        assert ("kill_switch_engaged", "engaged", "operator") in events
        assert ("kill_switch_denied", "denied", "suby") in events
        assert engine.store.list_workflows(limit=10) == []
    finally:
        engine.close()


def test_engaged_read_only_actions_still_allowed(tmp_path):
    engine = _engine(tmp_path)
    try:
        wf = engine.submit(_request("ro1"))
        assert wf.state == WorkflowState.EXECUTING
        engine.kill_switch.engage("freeze", "operator")
        fetched = engine.store.get_workflow(wf.workflow_id)
        assert fetched is not None and fetched.workflow_id == wf.workflow_id
        assert len(engine.store.list_workflows(limit=10)) == 1
        assert len(engine.store.get_events(wf.workflow_id)) >= 1
        with pytest.raises(KillSwitchEngaged):
            engine.execute(wf.workflow_id)
    finally:
        engine.close()


def test_release_allows_committal_again(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.kill_switch.engage("brief stop", "operator")
        with pytest.raises(KillSwitchEngaged):
            engine.submit(_request("rel1"))
        released = engine.kill_switch.release("operator")
        assert released["engaged"] is False
        wf = engine.submit(_request("rel2"))
        assert wf.state == WorkflowState.EXECUTING
    finally:
        engine.close()


def test_tenant_scoped_halt_does_not_affect_other_tenants(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.kill_switch.engage("tenant incident", "operator", tenant_id="tenant-a")
        assert engine.kill_switch.is_engaged() is False
        assert engine.kill_switch.is_engaged(tenant_id="tenant-a") is True
        assert engine.kill_switch.is_engaged(tenant_id="tenant-b") is False
        with pytest.raises(KillSwitchEngaged):
            engine.submit(_request("ta1", tenant="tenant-a"))
        wf_b = engine.submit(_request("tb1", tenant="tenant-b"))
        assert wf_b.state == WorkflowState.EXECUTING
    finally:
        engine.close()


def test_halt_engagement_itself_is_auditable(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.kill_switch.engage("audit me", "operator", tenant_id="tenant-a")
        engine.kill_switch.release("operator", tenant_id="tenant-a")
        events = _audit_event_types(str(tmp_path / "audit.db"))
        assert ("kill_switch_engaged", "engaged", "operator") in events
        assert ("kill_switch_released", "released", "operator") in events
        verifier = AuditTrail(db_path=str(tmp_path / "audit.db"))
        try:
            ok, detail = verifier.verify_chain()
            assert ok is True, detail
        finally:
            verifier.close()
    finally:
        engine.close()


def test_unreadable_flag_fails_closed(tmp_path):
    engine = _engine(tmp_path)
    try:
        broken = KillSwitch(db_path=str(tmp_path))
        assert broken.is_engaged() is True
        engine.kill_switch = broken
        with pytest.raises(KillSwitchEngaged):
            engine.submit(_request("fc1"))
    finally:
        engine.close()


def test_approve_and_execute_denied_while_engaged(tmp_path):
    engine = _engine(tmp_path)
    try:
        wf = engine.submit(_request("ap1", requires_approval=True))
        assert wf.state == WorkflowState.AWAITING_APPROVAL
        engine.kill_switch.engage("freeze approvals", "operator")
        approval = Approval(
            approval_id="apr_ks",
            correlation_id=wf.correlation.correlation_id,
            subject_id=wf.workflow_id,
            approver_actor="sami",
            approver_role_id="sami",
            decision="approved",
            reason="ok",
            timestamp=FIXED_TS,
        )
        with pytest.raises(KillSwitchEngaged):
            engine.approve(wf.workflow_id, approval)
        with pytest.raises(KillSwitchEngaged):
            engine.execute(wf.workflow_id)
        with pytest.raises(KillSwitchEngaged):
            other = engine.submit(_request("ap2"))
            engine.execute(other.workflow_id)
    finally:
        engine.close()


def test_cancel_still_allowed_while_engaged(tmp_path):
    engine = _engine(tmp_path)
    try:
        wf = engine.submit(_request("cx1"))
        engine.kill_switch.engage("freeze", "operator")
        cancelled = engine.cancel(wf.workflow_id, "operator")
        assert cancelled.state == WorkflowState.CLOSED
    finally:
        engine.close()


# ── CLI ────────────────────────────────────────────────────────────────────


def test_cli_engage_release_status_roundtrip(tmp_path, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("kill_switch_cli", "scripts/kill_switch.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    db = str(tmp_path / "ks.db")
    audit = str(tmp_path / "audit.db")
    assert (
        cli.main(
            [
                "--db-path",
                db,
                "--audit-db-path",
                audit,
                "engage",
                "--reason",
                "cli drill",
                "--actor",
                "cli-op",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "engaged" in out
    assert cli.main(["status", "--tenant", "other", "--db-path", db, "--audit-db-path", audit]) == 0
    assert '"engaged": true' in capsys.readouterr().out
    assert (
        cli.main(["--db-path", db, "--audit-db-path", audit, "release", "--actor", "cli-op"]) == 0
    )
    assert cli.main(["--db-path", db, "--audit-db-path", audit, "status"]) == 0
    assert '"engaged": false' in capsys.readouterr().out
    assert KillSwitch(db_path=db).is_engaged() is False


# ── HTTP surface ───────────────────────────────────────────────────────────


fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

TOKEN = secrets.token_urlsafe(24)
WRONG = secrets.token_urlsafe(24)


@pytest.fixture(autouse=True)
def _token_env(monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "sami")


@pytest.fixture()
def client(tmp_path):
    from server.app import create_app
    from server.config import Settings

    settings = Settings(
        profile="local",
        db_path=str(tmp_path / "workflow.db"),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def _submit_body():
    return {
        "tenant_id": "helix-prime",
        "client_id": "Account Alpha",
        "capability": "wfm_forecast",
        "requesting_actor": "suby",
        "owning_role_id": "ops_gm",
        "input_payload": {"arrival_rate": 10},
        "requires_approval": False,
    }


def test_halt_route_requires_auth(client):
    assert client.post("/api/halt/engage", json={"reason": "x"}).status_code == 401
    assert client.get("/api/halt/status").status_code == 401


def test_halt_engage_requires_privileged_role(client, monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "ops_gm")
    resp = client.post("/api/halt/engage", json={"reason": "x"}, headers=_auth())
    assert resp.status_code == 403


def test_halt_engage_release_lifecycle(client):
    resp = client.post("/api/halt/engage", json={"reason": "http drill"}, headers=_auth())
    assert resp.status_code == 200
    assert resp.json()["engaged"] is True
    status = client.get("/api/halt/status", headers=_auth())
    assert status.status_code == 200
    assert status.json()["engaged"] is True
    blocked = client.post("/api/workflows", json=_submit_body(), headers=_auth())
    assert blocked.status_code == 503
    assert blocked.json()["error"]["code"] == "halt_engaged"
    released = client.post("/api/halt/release", json={}, headers=_auth())
    assert released.status_code == 200
    assert released.json()["engaged"] is False
    ok = client.post("/api/workflows", json=_submit_body(), headers=_auth())
    assert ok.status_code in (200, 202)
