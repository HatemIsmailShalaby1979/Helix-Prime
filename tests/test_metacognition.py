"""Tests for the evidence-gated metacognitive improvement system (Prompt 8).

Covers: proposal generation, failed evaluation, rejection, approval (with
separation-of-duties), rollback, and the core guarantee that no unapproved
proposal ever changes runtime behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from metacognition.improvement import (
    MetacognitionEngine,
    APPROVED,
    DRAFT,
    EVALUATED,
    EVALUATED_FAILED,
    REJECTED,
    ROLLED_BACK,
    apply_proposal,
    rollback_proposal,
)

TS = "2026-08-29T12:00:00Z"
CORR = "corr-meta"


def _simulate(policy, case):
    # policy = {"value": threshold}; case = {"score": s}; success when score >= threshold
    return case.get("score", 0.0) >= policy.get("value", 1.0)


def _cases():
    return [{"score": s} for s in (0.2, 0.4, 0.6, 0.8)]


def _propose(eng, proposed_value, baseline_value=0.5, **kw):
    return eng.propose(
        kind="policy",
        target="approval_threshold",
        baseline=f"threshold={baseline_value}",
        proposed=f"threshold={proposed_value}",
        baseline_policy={"value": baseline_value},
        proposed_policy={"value": proposed_value},
        hypothesis="lower threshold improves throughput without harming quality",
        evidence=["rec-0001", "rec-0002"],
        risk_assessment="low: reversible, monitored",
        rollback_plan="restore previous threshold value",
        tenant_id=kw.get("tenant_id", "t1"),
        client_id=kw.get("client_id", "c1"),
        created_by=kw.get("created_by", "agent-1"),
        role_id=kw.get("role_id", "customer_success_gm"),
        correlation_id=CORR,
        timestamp=TS,
        min_improvement=0.0,
    )


# --- proposal generation ------------------------------------------------------
def test_proposal_generation(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    p = _propose(eng, 0.3)
    assert p.approval_state == DRAFT
    for f in ("proposal_id", "version", "baseline", "hypothesis", "evidence",
              "evaluation_results", "risk_assessment", "approval_state",
              "rollback_plan", "provenance", "tenant_id", "client_id",
              "created_by", "role_id", "correlation_id", "timestamp",
              "data_mode", "classification"):
        assert hasattr(p, f) and getattr(p, f) is not None, f
    # persists + reloads
    eng2 = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    assert eng2.get_proposal(p.proposal_id).proposed == "threshold=0.3"


# --- failed evaluation --------------------------------------------------------
def test_failed_evaluation(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    p = _propose(eng, 0.9)  # higher threshold -> worse success rate
    res = eng.evaluate(p, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    assert res.passed is False
    assert eng.get_proposal(p.proposal_id).approval_state == EVALUATED_FAILED
    dec = eng.approve(p.proposal_id, "human-1", "ict_gm")
    assert dec.decision == "denied"


# --- rejection ----------------------------------------------------------------
def test_rejection(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    p = _propose(eng, 0.3)
    eng.evaluate(p, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    eng.reject(p.proposal_id, "human-1", "not convinced")
    assert eng.get_proposal(p.proposal_id).approval_state == REJECTED
    dec = eng.approve(p.proposal_id, "human-2", "ict_gm")
    assert dec.decision == "denied"


# --- approval (with separation of duties) -------------------------------------
def test_approval(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    p = _propose(eng, 0.3)
    eng.evaluate(p, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    assert eng.get_proposal(p.proposal_id).approval_state == EVALUATED
    # self-approval denied
    self_dec = eng.approve(p.proposal_id, "agent-1", "ict_gm", requester_actor="agent-1")
    assert self_dec.decision == "denied"
    # same-role denied
    same = eng.approve(p.proposal_id, "human-2", "customer_success_gm")
    assert same.decision == "denied"
    # cross-role allowed
    ok = eng.approve(p.proposal_id, "human-1", "ict_gm")
    assert ok.decision == "allowed"
    assert eng.get_proposal(p.proposal_id).approval_state == APPROVED
    assert eng.get_proposal(p.proposal_id).reviewer == "human-1"


# --- rollback -----------------------------------------------------------------
def test_rollback(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    p = _propose(eng, 0.3)
    eng.evaluate(p, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    eng.approve(p.proposal_id, "human-1", "ict_gm")
    eng.rollback(p.proposal_id, "human-1", "reconsider")
    assert eng.get_proposal(p.proposal_id).approval_state == ROLLED_BACK


# --- NO unapproved proposal changes runtime behavior -------------------------
def test_no_unapproved_changes_runtime(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    runtime = {"approval_threshold": 0.5}

    p = _propose(eng, 0.3)
    eng.evaluate(p, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    eng.approve(p.proposal_id, "human-1", "ict_gm")
    # The engine only flipped state; runtime is untouched.
    assert runtime["approval_threshold"] == 0.5

    # Explicit, gated deployment changes runtime.
    apply_proposal(runtime, eng.get_proposal(p.proposal_id), "human-1", "ict_gm")
    assert runtime["approval_threshold"] == 0.3

    # Explicit rollback restores baseline.
    rollback_proposal(runtime, eng.get_proposal(p.proposal_id), "human-1", "ict_gm")
    assert runtime["approval_threshold"] == 0.5

    # Deploying an UNAPPROVED proposal is refused.
    p2 = _propose(eng, 0.2)
    eng.evaluate(p2, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    raised = False
    try:
        apply_proposal(runtime, eng.get_proposal(p2.proposal_id), "human-1", "ict_gm")
    except RuntimeError:
        raised = True
    assert raised
    assert runtime["approval_threshold"] == 0.5


# --- detection ----------------------------------------------------------------
def test_detect_repeated_failures(tmp_path):
    eng = MetacognitionEngine()
    recs = [
        {"kind": "outcome", "decision": "rejected", "record_id": f"o{i}", "target": "refund_flow"}
        for i in range(4)
    ] + [{"kind": "outcome", "decision": "accepted", "record_id": "ok1", "target": "refund_flow"}]
    signals = eng.detect_repeated_failures(recs, threshold=3)
    assert len(signals) == 1
    assert signals[0].count == 4 and signals[0].target == "refund_flow"


def test_detect_performance_drift(tmp_path):
    eng = MetacognitionEngine()
    drift = eng.detect_performance_drift("csat", baseline_rate=0.9, recent_rate=0.7, threshold=0.05)
    assert drift is not None and drift.delta == -0.2 or abs(drift.delta - (-0.2)) < 1e-9
    none = eng.detect_performance_drift("csat", baseline_rate=0.9, recent_rate=0.88, threshold=0.05)
    assert none is None


# --- audit chain integrity ----------------------------------------------------
def test_audit_chain_integrity(tmp_path):
    import json

    p = str(tmp_path / "prop.jsonl")
    eng = MetacognitionEngine(path=p)
    _propose(eng, 0.3)
    ok, _ = eng.verify_chain()
    assert ok is True
    # tamper with the ledger
    lines = open(p, "r", encoding="utf-8").read().splitlines()
    env = json.loads(lines[0])
    env["record"]["hypothesis"] = "tampered"
    env["hash"] = "deadbeef"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(env) + "\n")
        for ln in lines[1:]:
            fh.write(ln + "\n")
    eng2 = MetacognitionEngine(path=p)
    ok2, _ = eng2.verify_chain()
    assert ok2 is False


# --- evidence report ----------------------------------------------------------
def test_evidence_report(tmp_path):
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    p = _propose(eng, 0.3)
    eng.evaluate(p, historical_cases=_cases(), simulated_cases=_cases(), simulate=_simulate)
    eng.approve(p.proposal_id, "human-1", "ict_gm")
    rep = eng.generate_evidence_report(eng.get_proposal(p.proposal_id))
    for k in ("baseline", "hypothesis", "evidence", "evaluation_results", "risk_assessment",
              "reviewer", "approval_state", "rollback_plan", "version", "audit_chain"):
        assert k in rep, k
    assert rep["approval_state"] == APPROVED
    assert rep["audit_chain"] == "chain intact"
