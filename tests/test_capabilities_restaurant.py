"""Tests for the restaurant capability pack (Prompt 11).

Covers capability-pack registration, tenant isolation, synthetic restaurant walkthrough,
evidence + provenance, approval gating, memory recording, failure handling, no external
writes, no production claim, metacognitive proposals, governance checks, release gates,
and a joint demonstration that the SAME governed core supports both call-centre and
restaurant workflows.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from capabilities.restaurant import (  # noqa: E402
    RestaurantCapabilityPack, build_synthetic_restaurant, get_capability, DATA_MODE,
    RestaurantConnector,
)
from capabilities.restaurant.runtime import DEFAULT_AS_OF  # noqa: E402
from connectors.contracts import ConnectorContext  # noqa: E402
from memory.governed_memory import GovernedMemory  # noqa: E402
from pilot.consent import ConsentRecord  # noqa: E402

TS = "2026-08-29T12:00:00Z"


def _valid_consent(tenant_id="r1", client_id="rc1"):
    return ConsentRecord(
        consent_id="rc-consent-1", tenant_id=tenant_id, client_id=client_id, customer_id="cust-r1",
        status="granted", granted_at="2026-01-01T00:00:00Z", expires_at="2027-01-01T00:00:00Z",
        data_modes_permitted=("historical_consented", "simulated_realistic"), recorded_by="csm",
        signature="sig",
    )


def _pack():
    return RestaurantCapabilityPack(GovernedMemory())


def _fixtures():
    return {(("r1", "rc1")): build_synthetic_restaurant("r1", "rc1", TS),
            (("r2", "rc2")): build_synthetic_restaurant("r2", "rc2", TS)}


# 1. capability-pack registration --------------------------------------------
def test_capability_pack_registration():
    meta = get_capability("restaurant_operations")
    assert meta is not None
    for key in ("ontology", "roles", "workflows", "policies", "metrics",
                "connector_contracts", "data_classifications", "approval_requirements",
                "failure_modes", "fixtures", "reused_core"):
        assert key in meta, key
    assert meta["read_only_start"] is True
    assert meta["production_readiness"] == "NOT_ESTABLISHED"


# 2. tenant isolation ---------------------------------------------------------
def test_tenant_isolation():
    rt = _pack()
    rt.dry_run([("r1", "rc1"), ("r2", "rc2")], _fixtures())
    assert rt.tenant_isolation_ok("r1", "r2") is True
    t1 = rt.mem.retrieve(tenant_id="r1", include_deleted=False)
    assert all(r.tenant_id == "r1" for r in t1)
    assert all(r.tenant_id != "r2" for r in t1)


# 3. synthetic restaurant walkthrough -----------------------------------------
def test_synthetic_restaurant_walkthrough():
    rt = _pack()
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent())
    # 6 workflow diagnoses recorded
    diags = rt.mem.retrieve(tenant_id="r1", kinds=["customer_context"], include_deleted=False)
    cats = {d.body["workflow_category"] for d in diags}
    assert {"staffing_risk", "inventory_risk", "complaint_escalation"} <= cats
    # recommendations + approval drafts created for risky categories
    recs = rt.mem.retrieve(tenant_id="r1", kinds=["recommendation"], include_deleted=False)
    apps = rt.mem.retrieve(tenant_id="r1", kinds=["approval"], include_deleted=False)
    assert recs and apps
    # no live customer data mode anywhere
    assert all(r.data_mode != "live_customer" for r in rt.mem._records)
    # metrics computed and deterministic
    m = rt.build_evidence_pack(TS)["metrics"]
    assert "escalation_accuracy" in m and "recommendation_acceptance_rate" in m


# 4. evidence + provenance ----------------------------------------------------
def test_evidence_and_provenance():
    rt = _pack()
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent())
    pack = rt.build_evidence_pack(TS)
    assert pack["audit_chain_intact"] is True
    assert pack["audit_status"] in ("verified", "in_memory_not_persisted")
    for r in rt.mem._records:
        assert r.provenance.get("correlation_id"), r.kind
        assert r.provenance.get("data_mode") == DATA_MODE, r.kind
        assert r.data_mode == DATA_MODE
    # every recommendation carries evidence refs
    recs = rt.mem.retrieve(tenant_id="r1", kinds=["recommendation"], include_deleted=False)
    assert all(r.evidence_refs for r in recs)


# 5. approval gating ----------------------------------------------------------
def test_approval_gating():
    rt = _pack()
    consent = _valid_consent()
    rt.prepare_first_real_pilot("2026-08-01T00:00:00Z", "2026-09-01T00:00:00Z", consent, TS)
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=consent)
    draft = rt.mem.retrieve(tenant_id="r1", kinds=["approval"], include_deleted=False)[0]
    rid = draft.body["recommendation_id"]
    owner = draft.body["owner"]
    owner_role = draft.body["owner_role"]
    # blocked during read-only period
    blocked = False
    try:
        rt.approve_action(draft.record_id, "approver-1", "restaurant_gm", owner, owner_role, as_of=TS)
    except Exception:
        blocked = True
    assert blocked
    # exit read-only, then gating by role + SOD
    rt.exit_read_only_period(TS, "approver-1", "restaurant_gm")
    # wrong approver role -> denied
    wrong = False
    try:
        rt.approve_action(draft.record_id, "approver-1", "shift_manager", owner, owner_role, as_of=TS)
    except Exception:
        wrong = True
    assert wrong
    # self/same-role approval denied
    sod = False
    try:
        rt.approve_action(draft.record_id, owner, owner_role, owner, owner_role, as_of=TS)
    except Exception:
        sod = True
    assert sod
    # valid cross-role approval
    rt.approve_action(draft.record_id, "approver-1", "restaurant_gm", owner, owner_role, as_of=TS)
    latest = [a for a in rt.mem._records if a.kind == "approval" and a.body.get("recommendation_id") == rid]
    latest.sort(key=lambda r: r.record_id)
    assert latest[-1].body["approval_state"] == "approved"


# 6. memory recording ---------------------------------------------------------
def test_memory_recording():
    rt = _pack()
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent())
    kinds = {r.kind for r in rt.mem.retrieve(tenant_id="r1", include_deleted=False)}
    assert {"customer_context", "recommendation", "approval"} <= kinds
    # an outcome (baseline) record exists at pilot scope
    assert any(r.kind == "outcome" for r in rt.mem._records)


# 7. failure handling ---------------------------------------------------------
def test_failure_handling():
    rt = _pack()
    from capabilities.restaurant.contracts import RestaurantConnector

    class BrokenConnector(RestaurantConnector):
        def list_shifts(self, ctx):
            raise RuntimeError("restaurant ops down")

        def list_inventory(self, ctx):
            raise RuntimeError("restaurant ops down")

        def list_suppliers(self, ctx):
            raise RuntimeError("restaurant ops down")

        def list_complaints(self, ctx):
            raise RuntimeError("restaurant ops down")

        def list_daily_summary(self, ctx):
            raise RuntimeError("restaurant ops down")

    rt._build_connectors = lambda ctx, fixtures: {"restaurant_ops": BrokenConnector("restaurant_ops", "RestaurantOps", fixtures)}
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent())
    fails = [r for r in rt.mem._records if r.kind == "workflow_history" and r.body.get("action") == "connector_failure"]
    assert fails
    # connector write path still disabled
    ctx = ConnectorContext("r1", "org-1", "rc1", actor="x", correlation_id="c", data_mode=DATA_MODE)
    conn = RestaurantConnector("restaurant_ops", "RestaurantOps", {})
    assert conn.request_write(ctx, "reorder", {}, None).executed is False


# 8. no external writes -------------------------------------------------------
def test_no_external_writes():
    rt = _pack()
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent())
    rt.generate_metacognitive_proposal(TS, "corr-meta")
    # no live customer records
    assert all(r.data_mode != "live_customer" for r in rt.mem._records)
    # any policy record is a proposal, never applied
    policies = [r for r in rt.mem._records if r.kind == "policy"]
    assert policies
    assert all(p.body.get("applied") is False for p in policies)
    # live not activated in config
    assert rt.config.live_activated is False


# 9. no production claim ------------------------------------------------------
def test_no_production_claim():
    rt = _pack()
    assert rt.final_status()["production_readiness"] == "NOT_ESTABLISHED"
    assert "not validated for every business" in rt.final_status()["note"].lower()


# metacognitive proposals (reuse) ---------------------------------------------
def test_metacognitive_proposal_reuse():
    rt = _pack()
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent())
    report = rt.generate_metacognitive_proposal(TS, "corr-meta")
    assert report["approval_state"] in ("evaluated", "evaluated_failed", "draft")
    # proposal recorded as governed evidence, not deployed
    pol = [r for r in rt.mem._records if r.kind == "policy" and r.body.get("proposal_id") == report["proposal_id"]]
    assert pol and pol[0].body.get("applied") is False


# connector permissions reuse -------------------------------------------------
def test_connector_read_only_contract():
    ctx = ConnectorContext("r1", "org-1", "rc1", actor="x", correlation_id="c", data_mode=DATA_MODE)
    conn = RestaurantConnector("restaurant_ops", "RestaurantOps", build_synthetic_restaurant("r1", "rc1", TS))
    res = conn.list_shifts_result(ctx)
    assert res.status == "ok"
    assert res.provenance.data_mode == DATA_MODE
    assert res.provenance.correlation_id == "c"
    assert conn.request_write(ctx, "notify_staff", {}, None).executed is False


# 10. governance checks -------------------------------------------------------
def test_governance_checks():
    out = subprocess.run([sys.executable, "-m", "GOVERNANCE.governance_check", "check"],
                         cwd=str(ROOT), capture_output=True, text=True)
    assert "governance=PASS" in out.stdout, out.stdout + out.stderr


# 11. release gates -----------------------------------------------------------
def test_release_gates():
    from release.gate import run_gate
    assert run_gate("controlled_pilot")["classification"] == "CONTROLLED_PILOT_READY"
    assert run_gate("production")["classification"] == "NOT_READY"


# 12. same governed core supports call-centre AND restaurant ------------------
def test_same_core_supports_call_centre_and_restaurant():
    from pilot import PilotRuntime, PilotConfig
    mem = GovernedMemory()
    # call-centre pilot (verified core) on one tenant
    cc = PilotRuntime(PilotConfig.from_dict({}), mem)
    cc.dry_run([("cc-1", "cc-c1")], consent=_valid_consent("cc-1", "cc-c1"))
    # restaurant pack (same governed core) on another tenant, same memory
    rt = RestaurantCapabilityPack(mem)
    rt.dry_run([("r1", "rc1")], _fixtures(), consent=_valid_consent("r1", "rc1"))
    # both tenants present and isolated
    assert cc.tenant_isolation_ok("cc-1", "r1") is True
    assert all(r.tenant_id == "cc-1" for r in mem.retrieve(tenant_id="cc-1", include_deleted=True))
    assert all(r.tenant_id == "r1" for r in mem.retrieve(tenant_id="r1", include_deleted=True))
    # audit chain intact across both packs
    ok, _ = mem.verify_chain()
    assert ok
