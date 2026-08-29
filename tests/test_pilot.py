"""Tests for the controlled design-partner pilot (Prompt 10).

Covers: synthetic dry-run, consent validation, tenant isolation, connector
failure handling, approval denial, rollback, retention, evidence-pack
generation, governance checker, release gates, and the read-only / minimum-data
/ no-hidden-jobs / no-auto-self-improvement / no-production-claim invariants.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pilot import (  # noqa: E402
    PilotConfig, ConsentRecord, PilotRuntime, PilotError, build_evidence_pack,
    HISTORICAL_CONSENTED, SIMULATED_REALISTIC,
)
from pilot.scope import LIVE_CUSTOMER  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402

TS = "2026-08-29T12:00:00Z"


def _valid_consent(modes=(HISTORICAL_CONSENTED, SIMULATED_REALISTIC)):
    return ConsentRecord(
        consent_id="consent-1", tenant_id="t1", client_id="c1", customer_id="cust-1",
        status="granted", granted_at="2026-01-01T00:00:00Z", expires_at="2027-01-01T00:00:00Z",
        data_modes_permitted=modes, recorded_by="csm", signature="sig",
    )


def _runtime():
    cfg = PilotConfig.from_dict({})
    return PilotRuntime(cfg, GovernedMemory())


# --- synthetic pilot dry-run ------------------------------------------------
def test_synthetic_pilot_dry_run():
    rt = _runtime()
    rt.dry_run([("t1", "c1"), ("t2", "c2")], consent=_valid_consent())
    assert len(rt.diagnoses) == 2
    assert rt.mem.audit_status() in ("verified", "in_memory_not_persisted")

    recs = rt.mem.retrieve(tenant_id="t1", kinds=["recommendation"], include_deleted=False)
    assert recs, "recommendations should be recorded"
    # every recommendation has evidence
    assert all(r.evidence_refs for r in recs)
    # every approval draft has owner + approval_state
    apps = rt.mem.retrieve(tenant_id="t1", kinds=["approval"], include_deleted=False)
    assert apps
    for a in apps:
        assert a.body.get("owner")
        assert a.body.get("approval_state") == "draft"
    # no live customer data mode anywhere
    assert all(r.data_mode != LIVE_CUSTOMER for r in rt.mem._records)
    # connectors are read-only: request_write never executes
    from connectors.registry import ConnectorRegistry, KNOWN_PROVIDERS
    from connectors.contracts import ConnectorContext
    ctx = ConnectorContext("t1", "org-1", "c1", actor="x", correlation_id="c", data_mode="simulated_realistic")
    reg = ConnectorRegistry(mode="fake")
    res = reg.get_connector("zendesk", ctx).request_write(ctx, "send_followup", {}, None)
    assert res.executed is False


def test_every_outcome_recorded_in_governed_memory():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    kinds = {r.kind for r in rt.mem.retrieve(tenant_id="t1", include_deleted=False)}
    # diagnosis, recommendations, approval drafts, consent-validation, baseline all recorded
    assert {"customer_context", "recommendation", "approval"} <= kinds


# --- consent validation ------------------------------------------------------
def test_consent_validation():
    rt = _runtime()
    # valid passes
    rt.validate_consent(_valid_consent(), TS)
    # pending -> denied
    bad = _valid_consent()
    bad.status = "pending"
    raised = False
    try:
        rt.validate_consent(bad, TS)
    except PilotError:
        raised = True
    assert raised
    # expired -> denied
    exp = _valid_consent()
    exp.expires_at = "2020-01-01T00:00:00Z"
    raised = False
    try:
        rt.validate_consent(exp, TS)
    except PilotError:
        raised = True
    assert raised
    # live permitted -> denied
    live = _valid_consent(modes=(HISTORICAL_CONSENTED, SIMULATED_REALISTIC, LIVE_CUSTOMER))
    raised = False
    try:
        rt.validate_consent(live, TS)
    except PilotError:
        raised = True
    assert raised


# --- tenant isolation --------------------------------------------------------
def test_tenant_isolation():
    rt = _runtime()
    rt.dry_run([("t1", "c1"), ("t2", "c2")], consent=_valid_consent())
    assert rt.tenant_isolation_ok("t1", "t2") is True
    t1 = rt.mem.retrieve(tenant_id="t1", include_deleted=False)
    assert all(r.tenant_id == "t1" for r in t1)
    assert all(r.tenant_id != "t2" for r in t1)


# --- connector failure handling ----------------------------------------------
def test_connector_failure_handling():
    rt = _runtime()
    from connectors.registry import ConnectorRegistry, KNOWN_PROVIDERS
    from connectors.contracts import ConnectorContext
    ctx = ConnectorContext("t1", "org-1", "c1", actor="x", correlation_id="c", data_mode="simulated_realistic")
    connectors = {p: ConnectorRegistry(mode="fake").get_connector(p, ctx) for p in KNOWN_PROVIDERS}
    # force the Salesforce connector read to fail
    def _boom(_ctx):
        raise RuntimeError("salesforce down")
    connectors["salesforce"].list_accounts = _boom

    diagnosis, _view, _bundle, failures = rt.diagnose_account(
        "t1", "c1", TS, "pilot-operator", "customer_success_gm", "corr-x", connectors=connectors)
    # degraded gracefully: unknown diagnosis, failure recorded, no crash/outbound write
    assert diagnosis.health_state == "unknown"
    fails = rt.mem.retrieve(tenant_id="t1", kinds=["workflow_history"], include_deleted=False)
    assert any(f.body.get("action") == "connector_failure" for f in fails)
    # write path remains disabled regardless
    res = connectors["zendesk"].request_write(ctx, "send_followup", {}, None)
    assert res.executed is False


# --- approval denial ---------------------------------------------------------
def test_approval_denial():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    draft = rt.mem.retrieve(tenant_id="t1", kinds=["approval"], include_deleted=False)[0]
    rid = draft.body["recommendation_id"]
    rt.deny_action(draft.record_id, "reviewer-1", "not needed")
    # latest approval for that recommendation is now denied
    latest = [a for a in rt.mem._records if a.kind == "approval" and a.body.get("recommendation_id") == rid]
    latest.sort(key=lambda r: r.record_id)
    assert latest[-1].body["approval_state"] == "denied"


# --- rollback ----------------------------------------------------------------
def test_rollback():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    draft = rt.mem.retrieve(tenant_id="t1", kinds=["approval"], include_deleted=False)[0]
    rid = draft.body["recommendation_id"]
    owner = draft.body["owner"]
    owner_role = draft.body["owner_role"]
    rt.approve_action(draft.record_id, "approver-1", "ict_gm", owner, owner_role)
    latest = [a for a in rt.mem._records if a.kind == "approval" and a.body.get("recommendation_id") == rid]
    latest.sort(key=lambda r: r.record_id)
    assert latest[-1].body["approval_state"] == "approved"
    rt.rollback_action(draft.record_id, "approver-1", "ict_gm", "wrong call")
    latest = [a for a in rt.mem._records if a.kind == "approval" and a.body.get("recommendation_id") == rid]
    latest.sort(key=lambda r: r.record_id)
    assert latest[-1].body["approval_state"] == "rolled_back"
    incidents = [r for r in rt.mem._records if r.kind == "workflow_history" and r.body.get("action") == "rollback"]
    assert incidents


# --- retention handling ------------------------------------------------------
def test_retention_handling():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    rt.mem.add(
        kind="customer_context", nature="simulated_event", tenant_id="t1", client_id="c1",
        actor="pilot", role_id="customer_success_gm", source="test", classification="client_confidential",
        timestamp=TS, correlation_id="corr-r", confidence=1.0, evidence_refs=[], data_mode="simulated_realistic",
        retention_until="2020-01-01T00:00:00Z",
        provenance={"correlation_id": "corr-r", "data_mode": "simulated_realistic", "basis": "test", "sources": []},
        body={"health_state": "healthy", "open_risk_count": 0},
    )
    n = rt.apply_retention("2026-08-29T12:00:00Z")
    assert n >= 1
    expired = [r for r in rt.mem._records if r.retention_until == "2020-01-01T00:00:00Z"]
    assert all(r.retention_status == "expired" for r in expired)


# --- evidence-pack generation ------------------------------------------------
def test_evidence_pack_generation():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    pack = build_evidence_pack(rt, TS)
    assert pack["live_customer_records"] == 0
    assert pack["audit_chain_intact"] is True
    assert pack["final_status"]["pilot_package_ready"] is True
    assert pack["final_status"]["real_design_partner_approval_pending"] is True
    assert pack["final_status"]["production_readiness"] == "NOT_ESTABLISHED"
    assert "metrics" in pack and "approval_summary" in pack
    assert pack["consent"] is not None


# --- governance checker ------------------------------------------------------
def test_governance_checker():
    out = subprocess.run([sys.executable, "-m", "GOVERNANCE.governance_check", "check"],
                         cwd=str(ROOT), capture_output=True, text=True)
    assert "governance=PASS" in out.stdout, out.stdout + out.stderr


# --- release gates -----------------------------------------------------------
def test_release_gates():
    from release.gate import run_gate
    assert run_gate("controlled_pilot")["classification"] == "CONTROLLED_PILOT_READY"
    assert run_gate("production")["classification"] == "NOT_READY"


# --- invariants: read-only, min-data, no hidden jobs, no auto self-improvement
def test_no_automatic_self_improvement():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    # pilot never creates policy records (no behavior change) and memory does not auto-apply
    assert not any(r.kind == "policy" for r in rt.mem._records)
    assert rt.mem.auto_apply_policies is False


def test_no_hidden_background_jobs():
    before = threading.active_count()
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    after = threading.active_count()
    assert after == before  # no daemon/background threads started


def test_no_production_claim_and_minimum_data():
    rt = _runtime()
    assert rt.final_status()["production_readiness"] == "NOT_ESTABLISHED"
    assert rt.config.minimum_data is True
    assert rt.scope.minimum_data.enabled is True
    assert LIVE_CUSTOMER not in rt.config.permitted_data_modes


# --- first real pilot: read-only period + connector permissions --------------
def test_read_only_period_blocks_approval():
    rt = _runtime()
    consent = _valid_consent()
    # The first real pilot is prepared read-only.
    rt.prepare_first_real_pilot("2026-08-01T00:00:00Z", "2026-09-01T00:00:00Z", consent, TS)
    rt.dry_run([("t1", "c1")], consent=consent)
    assert rt.phase == "read_only"
    draft = rt.mem.retrieve(tenant_id="t1", kinds=["approval"], include_deleted=False)[0]
    owner = draft.body["owner"]
    owner_role = draft.body["owner_role"]
    # Approval (a committal action) is blocked during the read-only period.
    blocked = False
    try:
        rt.approve_action(draft.record_id, "approver-1", "ict_gm", owner, owner_role, as_of=TS)
    except PilotError:
        blocked = True
    assert blocked
    # Exiting the read-only period (audited) then permits approval.
    rt.exit_read_only_period(TS, "approver-1", "ict_gm")
    assert rt.phase == "supervised"
    rt.approve_action(draft.record_id, "approver-1", "ict_gm", owner, owner_role, as_of=TS)
    latest = [a for a in rt.mem._records
              if a.kind == "approval" and a.body.get("recommendation_id") == draft.body["recommendation_id"]]
    latest.sort(key=lambda r: r.record_id)
    assert latest[-1].body["approval_state"] == "approved"


def test_connector_permissions():
    from pilot.phases import ConnectorPermissions
    from connectors.registry import ConnectorRegistry, KNOWN_PROVIDERS
    from connectors.contracts import ConnectorContext

    perms = ConnectorPermissions()
    assert perms.write_allowed is False
    perms.validate()  # must not raise
    # Real (fake) connectors still reject writes regardless.
    ctx = ConnectorContext("t1", "org-1", "c1", actor="x", correlation_id="c", data_mode="simulated_realistic")
    reg = ConnectorRegistry(mode="fake")
    for p in KNOWN_PROVIDERS:
        assert reg.get_connector(p, ctx).request_write(ctx, "send_followup", {}, None).executed is False


def test_minimum_data_fields():
    rt = _runtime()
    rt.dry_run([("t1", "c1")], consent=_valid_consent())
    rec = rt.mem.retrieve(tenant_id="t1", kinds=["customer_context"], include_deleted=False)[0]
    allowed = set(rt.scope.minimum_data.collected_fields) | {
        "health_state", "open_risk_count", "recommended_actions",
    }
    for key in rec.body:
        assert key in allowed, key
    # excluded sensitive fields are never collected
    for ex in rt.scope.minimum_data.excluded_fields:
        assert ex not in rec.body
