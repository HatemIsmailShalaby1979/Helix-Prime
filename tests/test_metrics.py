"""
Observability tests (H2.2, G22): /metrics endpoint, request middleware metrics,
governance-decision counters, audit-chain verification metrics, queue depth,
secret redaction in request logs, and alert-rule drift against the exposition.
"""
from __future__ import annotations

import secrets

import pytest

pytest.importorskip("fastapi")
fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from observability.metrics import REGISTRY  # noqa: E402

TOKEN = secrets.token_urlsafe(24)
WRONG = secrets.token_urlsafe(24)


@pytest.fixture(autouse=True)
def _token_env(monkeypatch):
    monkeypatch.setenv("HELIX_API_TOKEN", TOKEN)
    monkeypatch.setenv("HELIX_API_TOKEN_ROLE", "sami")
    REGISTRY.reset_for_tests()


@pytest.fixture()
def client(tmp_path, monkeypatch):
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


# ── /metrics auth boundary ──────────────────────────────────────────────────


def test_metrics_requires_auth(client):
    resp = client.get("/metrics")
    assert resp.status_code == 401


def test_metrics_rejects_wrong_token(client):
    resp = client.get("/metrics", headers={"Authorization": f"Bearer {WRONG}"})
    assert resp.status_code == 401


def test_metrics_serves_prometheus_text_with_auth(client):
    resp = client.get("/metrics", headers=_auth())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    for family in (
        "helix_http_requests_total",
        "helix_http_request_duration_seconds",
        "helix_governance_decisions_total",
        "helix_audit_chain_verifications_total",
        "helix_audit_chain_verification_failures",
        "helix_approval_queue_depth",
    ):
        assert f"# HELP {family} " in body, f"{family} missing from exposition"
        assert f"# TYPE {family} " in body


def test_metrics_counts_requests_by_route_template(client):
    client.get("/healthz")
    client.get("/healthz")
    client.get("/api/approvals", headers=_auth())
    resp = client.get("/metrics", headers=_auth())
    assert resp.status_code == 200
    assert 'helix_http_requests_total{route="/healthz",status="200",method="GET"} 2.0' in resp.text
    assert 'helix_http_requests_total{route="/api/approvals",status="200",method="GET"} 1.0' in resp.text


def test_metrics_401_is_counted(client):
    client.get("/metrics")
    resp = client.get("/metrics", headers=_auth())
    assert 'helix_http_requests_total{route="/metrics",status="401",method="GET"} 1.0' in resp.text


def test_unknown_path_counts_as_unmatched(client):
    client.get("/no/such/route")
    resp = client.get("/metrics", headers=_auth())
    assert 'helix_http_requests_total{route="unmatched",status="404",method="GET"}' in resp.text


# ── governance decision counter (via Engine._audit hook) ───────────────────


def test_governance_decisions_counter_records_outcomes(tmp_path):
    from contracts.task import CorrelationContext, TaskRequest
    from control_plane.engine import Engine
    from control_plane.store import Store
    from control_plane.workflow import WorkflowState

    with Store(db_path=str(tmp_path / "wf.db")) as store:
        engine = Engine(store=store, audit_db_path=str(tmp_path / "audit.db"))
        engine.register_handler("wfm_forecast", lambda wf: {"ok": True})
        corr = CorrelationContext.new(tenant_id="t1", client_id="c1")
        req = TaskRequest(
            request_id="req_obs_1",
            correlation=corr,
            requesting_actor="suby",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            input_payload={},
            requires_approval=True,
            status="proposed",
            created_at="2026-09-12T00:00:00Z",
            client_id="c1",
        )
        wf = engine.submit(req)
        assert wf.state == WorkflowState.AWAITING_APPROVAL
        engine.close()

    snap = REGISTRY.snapshot()[ "helix_governance_decisions_total" ]
    assert snap.get("allowed", 0.0) >= 2.0


# ── audit-chain verification metrics ───────────────────────────────────────


def test_audit_verification_failure_is_counted(tmp_path):
    import json as _json
    import sqlite3

    from security.audit import AuditRecord, AuditTrail

    REGISTRY.reset_for_tests()
    db = str(tmp_path / "audit.db")
    trail = AuditTrail(db_path=db)
    prev = None
    for _ in range(2):
        rec = AuditRecord.new(
            event_type="t", actor="a", actor_type="agent", decision="succeeded",
            previous_hash=prev,
        )
        trail.append(rec)
        prev = rec.current_hash
    trail.close()

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT audit_id, data FROM audit ORDER BY rowid LIMIT 1").fetchone()
    data = _json.loads(row[1])
    data["decision"] = "tampered"
    conn.execute(
        "UPDATE audit SET data = ? WHERE audit_id = ?",
        (_json.dumps(data), row[0]),
    )
    conn.commit()
    conn.close()

    trail2 = AuditTrail(db_path=db)
    ok, _msg = trail2.verify_chain()
    trail2.close()
    assert ok is False

    snap = REGISTRY.snapshot()
    assert snap["helix_audit_chain_verifications_total"].get("failure", 0.0) >= 1.0
    assert snap["helix_audit_chain_verification_failures"][""] >= 1.0


def test_audit_verification_success_is_counted(tmp_path):
    from security.audit import AuditRecord, AuditTrail

    REGISTRY.reset_for_tests()
    db = str(tmp_path / "audit.db")
    trail = AuditTrail(db_path=db)
    prev = None
    for _ in range(3):
        rec = AuditRecord.new(
            event_type="t", actor="a", actor_type="agent", decision="succeeded",
            previous_hash=prev,
        )
        trail.append(rec)
        prev = rec.current_hash
    ok, _ = trail.verify_chain()
    trail.close()
    assert ok is True
    assert REGISTRY.snapshot()["helix_audit_chain_verifications_total"].get("ok", 0.0) >= 1.0


# ── approval-queue depth gauge ─────────────────────────────────────────────


def test_approval_queue_depth_reflected_in_metrics(client):
    client.post(
        "/api/workflows",
        json={
            "tenant_id": "tenant-obs",
            "client_id": "client-obs",
            "capability": "wfm_forecast",
            "requesting_actor": "suby",
            "owning_role_id": "ops_gm",
            "input_payload": {
                "arrival_rate": 10,
                "average_handling_time": 300,
                "service_level_target": 0.8,
            },
            "requires_approval": True,
        },
        headers=_auth(),
    )
    resp = client.get("/metrics", headers=_auth())
    for line in resp.text.splitlines():
        if line.startswith("helix_approval_queue_depth "):
            assert float(line.split()[-1]) >= 1.0
            return
    pytest.fail("helix_approval_queue_depth not present in exposition")


# ── request-log redaction (no secrets/PII in logs) ─────────────────────────


def test_request_log_line_is_redacted(client, tmp_path):
    import json as _json
    import pathlib

    fake_password = secrets.token_urlsafe(24)
    fake_token_value = secrets.token_hex(16)
    client.get(
        f"/api/workflows?password={fake_password}&token={fake_token_value}",
        headers=_auth(),
    )
    log_path = pathlib.Path(str(tmp_path / "logs.jsonl"))
    if not log_path.exists():
        pytest.skip("log written to default observability path")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    http_lines = [_json.loads(line) for line in lines if '"http_request"' in line]
    assert http_lines, "no http_request structured log lines were written"
    entry = http_lines[-1]
    serialized = _json.dumps(entry)
    assert fake_password not in serialized, "raw password-like value leaked into request log"
    assert fake_token_value not in serialized, "raw token-like value leaked into request log"


# ── alert-rule drift: rules reference exported metrics only ────────────────


def test_alert_rules_reference_exported_metrics_only():
    import pathlib
    import re

    rules_path = pathlib.Path("infra/monitoring/alerts.yml")
    assert rules_path.exists(), "infra/monitoring/alerts.yml must exist"
    text = rules_path.read_text(encoding="utf-8")
    expressions = " ".join(
        chunk for chunk in re.findall(r"expr: >-?\s*\n((?:.*\n)+?)\s{8,}[a-z_]+:", text)
    ) + " " + " ".join(
        line.split("expr:", 1)[1]
        for line in text.splitlines()
        if "expr:" in line and "helix_" in line
    )
    used = set(re.findall(r"\bhelix_[a-z_]+\b", expressions))
    assert used, "no helix metrics referenced in alert rule expressions"
    exported = set(REGISTRY.snapshot().keys())
    exported |= {
        "helix_http_requests_total",
        "helix_http_request_duration_seconds",
        "helix_governance_decisions_total",
        "helix_audit_chain_verifications_total",
        "helix_audit_chain_verification_failures",
        "helix_approval_queue_depth",
    }
    missing = sorted(
        name
        for name in used
        if name not in exported
        and not name.endswith(("_bucket", "_sum", "_count"))
        and name.rsplit("_bucket", 1)[0] not in exported
        and name.rsplit("_sum", 1)[0] not in exported
        and name.rsplit("_count", 1)[0] not in exported
    )
    assert not missing, (
        f"alert rules reference metrics that /metrics does not export: {missing}"
    )


def test_alert_rules_yaml_is_well_formed():
    import pathlib

    import yaml

    rules_path = pathlib.Path("infra/monitoring/alerts.yml")
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and "groups" in data
    for group in data["groups"]:
        assert "name" in group and "rules" in group
        for rule in group["rules"]:
            assert "alert" in rule and "expr" in rule and "labels" in rule
            assert "severity" in rule["labels"]
