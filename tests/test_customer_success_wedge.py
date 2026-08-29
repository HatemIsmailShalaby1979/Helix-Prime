"""Customer-success wedge verification (Prompt 5).

Covers: fixtures (healthy/at-risk/unknown/contradictory), missing data, stale
data, conflicting source data, recommendation rejection, outcome recording,
determinism, provenance, visible data-mode labelling, and approval preview.
"""
from __future__ import annotations

import types

from connectors.contracts import ConnectorContext
from customer_success import wedge
from customer_success.fixtures import (
    at_risk_account,
    contradictory_account,
    healthy_account,
    unknown_account,
)
from customer_success.wedge import (
    AccountContextBundle,
    OutcomeMemory,
    build_approval_preview,
    diagnose,
    record_outcome,
    run_wedge,
)


def _ctx(tenant="tenant-1", client="client-1", corr="corr-cs"):
    return ConnectorContext(tenant, "org-1", client, correlation_id=corr)


# ── fixtures map to expected health states ──────────────────────────────────

def test_healthy_fixture():
    diag, _ = run_wedge(healthy_account(_ctx()), OutcomeMemory())
    assert diag.health_state == "healthy"
    assert diag.confidence >= 0.7
    assert not any(r.severity in ("high", "critical") for r in diag.risk_factors)
    assert diag.recommended_action  # non-empty


def test_at_risk_fixture():
    diag, _ = run_wedge(at_risk_account(_ctx()), OutcomeMemory())
    assert diag.health_state == "at_risk"
    assert any(r.factor.startswith("sla_breach") for r in diag.risk_factors)


def test_unknown_fixture():
    diag, _ = run_wedge(unknown_account(_ctx()), OutcomeMemory())
    assert diag.health_state == "unknown"
    assert any(r.factor == "insufficient_data" for r in diag.risk_factors)
    assert diag.confidence <= 0.4


def test_contradictory_fixture():
    diag, _ = run_wedge(contradictory_account(_ctx()), OutcomeMemory())
    assert diag.health_state == "contradictory"
    assert any(r.factor == "conflicting_source_data" for r in diag.risk_factors)
    assert diag.confidence <= 0.2
    # contradictory diagnoses never auto-execute; approval is required
    assert diag.approval_requirement is True


# ── missing data ────────────────────────────────────────────────────────────

def test_missing_account_context():
    bundle = AccountContextBundle(
        context=_ctx(), account=None, tickets=(), enrichment=None, signals=(),
        data_mode="simulated_realistic", as_of="2026-08-29T12:00:00Z",
    )
    diag = diagnose(bundle)
    assert diag.health_state == "unknown"
    assert any(r.factor == "missing_account_context" for r in diag.risk_factors)
    assert diag.account_id == "unknown"


def test_unknown_fixture_is_missing_data_safe():
    # Account present but no tickets/enrichment/signals -> insufficient, not crash
    diag, _ = run_wedge(unknown_account(_ctx()), OutcomeMemory())
    assert diag.health_state == "unknown"


# ── stale data ──────────────────────────────────────────────────────────────

def test_stale_data_reduces_confidence_and_flags_risk():
    fresh = diagnose(at_risk_account(_ctx(), stale=False))
    stale = diagnose(at_risk_account(_ctx(), stale=True))
    assert any(r.factor == "stale_data" for r in stale.risk_factors)
    assert stale.confidence < fresh.confidence


# ── conflicting source data ─────────────────────────────────────────────────

def test_conflicting_source_data_detected():
    diag = diagnose(contradictory_account(_ctx()))
    conflict = next(r for r in diag.risk_factors if r.factor == "conflicting_source_data")
    assert conflict.severity == "critical"
    assert diag.health_state == "contradictory"


# ── recommendation rejection ────────────────────────────────────────────────

def test_recommendation_rejection_recorded_and_diagnosis_unchanged():
    mem = OutcomeMemory()
    bundle = at_risk_account(_ctx())
    diag, _ = run_wedge(bundle, mem)
    fingerprint_before = diag.fingerprint()
    rejected = record_outcome(
        mem, diag, "rejected", actor="alice", role_id="customer_success_gm",
        rationale="Deferred pending QBR",
    )
    assert rejected.decision == "rejected"
    assert mem.for_account(diag.account_id) == (rejected,)
    # Rejecting must NOT mutate the diagnosis
    diag2 = diagnose(bundle)
    assert diag2.fingerprint() == fingerprint_before


# ── outcome recording ───────────────────────────────────────────────────────

def test_outcome_recording():
    mem = OutcomeMemory()
    diag, _ = run_wedge(healthy_account(_ctx()), mem)
    # run_wedge itself must NOT record anything
    assert mem.all() == ()
    accepted = record_outcome(mem, diag, "accepted", actor="alice", role_id="customer_success_gm")
    assert accepted in mem.all()
    assert accepted.diagnosis_ref == diag.fingerprint()
    assert mem.for_account(diag.account_id) == (accepted,)


def test_outcome_recording_with_audit_trail(tmp_path):
    mem = OutcomeMemory(audit_db_path=str(tmp_path / "audit.db"))
    diag, _ = run_wedge(at_risk_account(_ctx()), mem)
    rec = record_outcome(mem, diag, "accepted", actor="alice", role_id="customer_success_gm")
    assert rec in mem.all()
    from security.audit import AuditTrail
    ok, msg = AuditTrail(db_path=str(tmp_path / "audit.db")).verify_chain()
    assert ok, msg


# ── determinism ─────────────────────────────────────────────────────────────

def test_diagnosis_is_deterministic():
    bundle = at_risk_account(_ctx())
    d1 = diagnose(bundle)
    d2 = diagnose(bundle)
    assert d1.fingerprint() == d2.fingerprint()
    assert (d1.health_state, d1.score, d1.confidence) == (d2.health_state, d2.score, d2.confidence)
    assert [e.ref for e in d1.evidence] == [e.ref for e in d2.evidence]


# ── provenance + visible data-mode labelling ───────────────────────────────

def test_provenance_carries_correlation_and_sources():
    ctx = _ctx(corr="corr-prov-cs")
    diag, _ = run_wedge(healthy_account(ctx), OutcomeMemory())
    assert diag.provenance.correlation_id == "corr-prov-cs"
    assert diag.provenance.data_mode == "simulated_realistic"
    assert set(diag.provenance.sources) >= {"Salesforce", "Zendesk", "Clay", "OperationalTelemetry"}


def test_historical_and_simulated_labelled_distinctly():
    ctx = _ctx()
    sim = diagnose(healthy_account(ctx, data_mode="simulated_realistic"))
    hist = diagnose(healthy_account(ctx, data_mode="historical_consented"))
    assert sim.data_mode == "simulated_realistic"
    assert hist.data_mode == "historical_consented"
    assert sim.provenance.data_mode == "simulated_realistic"
    assert hist.provenance.data_mode == "historical_consented"
    # same underlying shape -> same health call, but provenance marks the mode
    assert sim.health_state == hist.health_state


# ── approval preview ─────────────────────────────────────────────────────────

def test_approval_preview_reflects_requirement():
    contra = build_approval_preview(diagnose(contradictory_account(_ctx())))
    assert contra.required is True
    assert contra.role == "customer_success_gm"
    assert contra.policy == "cross_role_approval_required"

    healthy = build_approval_preview(diagnose(healthy_account(_ctx())))
    assert healthy.required is False
    assert healthy.policy == "no_approval_required"


def test_approval_preview_for_committal_action():
    ctx = _ctx()
    bundle = healthy_account(ctx)
    diag = diagnose(bundle)
    # Simulate a committal next-best-action (e.g. issuing a concession)
    committal = types.SimpleNamespace(
        account_id=diag.account_id, tenant_id=diag.tenant_id, client_id=diag.client_id,
        health_state=diag.health_state, score=diag.score, confidence=diag.confidence,
        risk_factors=diag.risk_factors, evidence=diag.evidence,
        recommended_action="Issue a goodwill concession to retain the account",
        recommended_actions=diag.recommended_actions,
        responsible_role="sales_gm", approval_requirement=False,
        expected_outcome=diag.expected_outcome, data_mode=diag.data_mode,
        provenance=diag.provenance,
    )
    preview = build_approval_preview(committal)
    assert preview.required is True
    assert preview.role == "sales_gm"
