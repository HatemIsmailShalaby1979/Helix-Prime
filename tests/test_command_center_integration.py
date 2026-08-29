"""Integration tests for the governed Codex Command Center (Prompt 6).

Covers every required verification scenario against the PURE builder in
``cockpit.command_center_integration`` (no Streamlit needed):

* full synthetic customer-success walkthrough
* connector failure state
* stale data state
* contradictory data state
* missing data state
* approval required
* self-approval denied
* cross-role approval
* outcome recorded
* tenant isolation
* no simulated data presented as live
* governance checker + release gates (reproduced in-session)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# `cockpit/` is added to sys.path so its modules (command_center_integration,
# codex_command_center) import as top-level modules, matching the repo convention.
sys.path.insert(0, str(ROOT / "cockpit"))
# repo root so `memory.governed_memory` imports as a package
sys.path.insert(0, str(ROOT))

import types  # noqa: E402

from connectors.contracts import ConnectorContext, ConnectorStatus  # noqa: E402
from connectors.fakes import FakeConnector  # noqa: E402
from connectors.registry import ConnectorRegistry  # noqa: E402
from customer_success.fixtures import (  # noqa: E402
    at_risk_account,
    contradictory_account,
    healthy_account,
    unknown_account,
)
from memory.governed_memory import GovernedMemory  # noqa: E402

from command_center_integration import (  # noqa: E402
    assemble_command_center,
    evaluate_approval,
    reset_demo,
)

TENANT = "tenant-1"
CLIENT = "Demo Account"
ACTOR = "local-operator"
CORR = "corr-prompt6"
AS_OF = "2026-08-29T12:00:00Z"


def _ctx(data_mode="simulated_realistic", tenant=TENANT):
    return ConnectorContext(tenant, "org-1", CLIENT, actor=ACTOR,
                            correlation_id=CORR, data_mode=data_mode)


def _view(**kw):
    kw.setdefault("tenant_id", TENANT)
    kw.setdefault("client_id", CLIENT)
    kw.setdefault("actor", ACTOR)
    kw.setdefault("role_id", "customer_success_gm")
    kw.setdefault("requested_data_mode", "simulated_realistic")
    kw.setdefault("correlation_id", CORR)
    kw.setdefault("memory", GovernedMemory())
    return assemble_command_center(**kw)


def _add_outcome(memory, diagnosis, decision, actor=ACTOR, role_id="customer_success_gm",
                 correlation_id=CORR, data_mode="simulated_realistic"):
    return memory.add(
        kind="outcome",
        nature="verified_outcome" if diagnosis.health_state != "contradictory" else "model_inference",
        tenant_id=diagnosis.tenant_id,
        client_id=diagnosis.client_id,
        actor=actor,
        role_id=role_id,
        source="customer_success_wedge",
        classification="client_confidential",
        timestamp=AS_OF,
        correlation_id=correlation_id,
        confidence=diagnosis.confidence,
        evidence_refs=[e.ref for e in diagnosis.evidence],
        data_mode=data_mode,
        provenance={"correlation_id": correlation_id, "data_mode": data_mode,
                    "basis": diagnosis.provenance.basis, "sources": list(diagnosis.provenance.sources)},
        body={"decision": decision, "diagnosis_ref": diagnosis.fingerprint()},
    )


# 1. full synthetic customer-success walkthrough ---------------------------------
def test_full_synthetic_walkthrough():
    v = _view(bundle=healthy_account(_ctx()))
    # governance metadata preserved on the view
    assert v.meta.tenant_id == TENANT and v.meta.client_id == CLIENT
    assert v.meta.role_id == "customer_success_gm"
    assert v.meta.classification == "client_confidential"
    assert v.meta.correlation_id == CORR and v.meta.effective_data_mode == "simulated_realistic"
    # 3 connectors
    assert {c.provider.lower() for c in v.connector_status} == {"salesforce", "zendesk", "clay"}
    # diagnosis carries all required fields
    d = v.diagnosis
    assert d.health_state == "healthy"
    assert d.evidence and d.confidence > 0
    assert d.recommended_action and d.responsible_role and d.expected_outcome
    assert d.provenance.correlation_id == CORR
    # approval preview present
    assert v.approval_preview is not None
    # evidence + outcome timelines present (outcome may be empty initially)
    assert len(v.evidence_timeline) >= 1
    for e in v.evidence_timeline:
        assert e.data_mode and e.governance.correlation_id == CORR
    assert v.audit_status in {"in_memory_not_persisted", "verified", "broken"}
    assert isinstance(v.state_flags, dict)


# 2. connector failure state -----------------------------------------------------
def test_connector_failure_state():
    ctx = _ctx()
    reg = ConnectorRegistry(mode="fake")
    connectors = {p: reg.get_connector(p, ctx) for p in ("salesforce", "zendesk", "clay")}
    connectors["zendesk"] = FakeConnector("zendesk", "Zendesk", status=ConnectorStatus.DISCONNECTED)
    v = _view(connectors=connectors)
    statuses = {c.provider.lower(): c.status for c in v.connector_status}
    assert statuses["zendesk"] == "disconnected"
    assert v.state_flags["unavailable"] is True
    assert any("unavailable" in a.lower() for a in v.state_flags["alerts"])


# 3. stale data state ------------------------------------------------------------
def test_stale_data_state():
    ctx = _ctx()
    bundle = at_risk_account(ctx, stale=True)
    v = _view(bundle=bundle)
    assert v.state_flags["stale"] is True
    assert any("stale" in a.lower() for a in v.state_flags["alerts"])
    assert v.diagnosis.confidence < 1.0
    assert any(rf.factor == "stale_data" for rf in v.diagnosis.risk_factors)


# 4. contradictory data state ---------------------------------------------------
def test_contradictory_data_state():
    ctx = _ctx()
    bundle = contradictory_account(ctx)
    v = _view(bundle=bundle)
    assert v.diagnosis.health_state == "contradictory"
    assert v.state_flags["contradictory"] is True
    # contradictory sources require approval
    assert v.diagnosis.approval_requirement is True
    assert v.approval_preview.required is True


# 5. missing data state ---------------------------------------------------------
def test_missing_data_state():
    ctx = _ctx()
    bundle = unknown_account(ctx)
    v = _view(bundle=bundle)  # must not raise
    assert v.diagnosis.health_state == "unknown"
    assert v.state_flags["unknown"] is True
    # evidence may be sparse; view still complete and safe
    assert v.meta.tenant_id == TENANT


# 6. approval required ----------------------------------------------------------
def test_approval_required_flag():
    ctx = _ctx()
    v = _view(bundle=contradictory_account(ctx))
    assert v.approval_preview.required is True
    assert v.approval_preview.role == v.diagnosis.responsible_role


# 7. self-approval denied -------------------------------------------------------
def test_self_approval_denied():
    v = _view(bundle=contradictory_account(_ctx()), role_id="customer_success_gm")
    dec = evaluate_approval(v, approver_actor=ACTOR, approver_role_id="customer_success_gm")
    assert dec.decision == "denied"
    assert "self-approval" in dec.reason.lower()


# 8. cross-role approval --------------------------------------------------------
def test_cross_role_approval():
    # operator is ICT GM; the required approver role is customer_success_gm -> cross-role
    v = _view(bundle=contradictory_account(_ctx()), role_id="ict_gm")
    dec = evaluate_approval(v, approver_actor="approver-bob", approver_role_id="customer_success_gm")
    assert dec.decision == "allowed"
    # same-role approval is denied
    dec2 = evaluate_approval(v, approver_actor="approver-bob", approver_role_id="ict_gm")
    assert dec2.decision == "denied"
    assert "same-role" in dec2.reason.lower()


# 9. outcome recorded -----------------------------------------------------------
def test_outcome_recorded():
    mem = GovernedMemory()
    v1 = _view(memory=mem, bundle=healthy_account(_ctx()))
    rec = _add_outcome(mem, v1.diagnosis, "accepted")
    assert rec.body["decision"] == "accepted"
    # rebuild view; outcome appears in the timeline
    v2 = _view(memory=mem, bundle=healthy_account(_ctx()))
    assert any(o.decision == "accepted" and o.outcome_id == rec.record_id for o in v2.outcome_timeline)
    assert rec.correlation_id == CORR


# 10. tenant isolation ----------------------------------------------------------
def test_tenant_isolation():
    mem = GovernedMemory()
    v1 = _view(tenant_id="tenant-1", memory=mem, bundle=healthy_account(_ctx()))
    _add_outcome(mem, v1.diagnosis, "accepted")
    v1b = _view(tenant_id="tenant-1", memory=mem, bundle=healthy_account(_ctx()))
    assert any(o.decision == "accepted" for o in v1b.outcome_timeline)
    # tenant-2 must NOT see tenant-1's outcomes
    v2 = _view(tenant_id="tenant-2", memory=mem, bundle=healthy_account(_ctx(tenant="tenant-2")))
    assert v2.diagnosis.tenant_id == "tenant-2"
    assert all(o.governance.tenant_id == "tenant-2" for o in v2.outcome_timeline)
    assert not any(o.decision == "accepted" for o in v2.outcome_timeline)


# 11. no simulated data presented as live --------------------------------------
def test_no_simulated_presented_as_live():
    v = _view(requested_data_mode="live_external")
    assert v.meta.requested_data_mode == "live_external"
    assert v.meta.effective_data_mode != "live_external"
    assert v.meta.effective_data_mode == "simulated_realistic"
    assert v.meta.live_warning is True
    assert all(e.data_mode != "live_external" for e in v.evidence_timeline)
    assert v.diagnosis.provenance.data_mode != "live_external"


# reset control -----------------------------------------------------------------
def test_reset_demo_clears_outcomes():
    mem = GovernedMemory()
    v = _view(memory=mem, bundle=healthy_account(_ctx()))
    _add_outcome(mem, v.diagnosis, "accepted")
    assert any(o.decision == "accepted" for o in _view(memory=mem, bundle=healthy_account(_ctx())).outcome_timeline)
    reset_demo(mem)
    assert not any(o.decision == "accepted" for o in _view(memory=mem, bundle=healthy_account(_ctx())).outcome_timeline)


# audit status reflects recorded chain ------------------------------------------
def test_audit_status_verified(tmp_path):
    db = str(tmp_path / "governed_memory.jsonl")
    mem = GovernedMemory(path=db)
    v = _view(memory=mem, bundle=healthy_account(_ctx()))
    _add_outcome(mem, v.diagnosis, "accepted")
    v2 = _view(memory=mem, bundle=healthy_account(_ctx()))
    assert v2.audit_status == "verified"


# 12. governance checker --------------------------------------------------------
def test_governance_checker_passes():
    out = subprocess.run(
        [sys.executable, "-m", "GOVERNANCE.governance_check", "check"],
        cwd=".", capture_output=True, text=True,
    )
    assert "governance=PASS" in out.stdout, out.stdout + out.stderr


# 13. release gates: controlled_pilot ready, production NOT_READY ---------------
def test_release_gates():
    from release.gate import run_gate

    pilot = run_gate(profile="controlled_pilot")
    assert pilot["classification"] == "CONTROLLED_PILOT_READY"
    prod = run_gate(profile="production")
    assert prod["classification"] == "NOT_READY"
