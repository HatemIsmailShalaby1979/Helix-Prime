"""Pilot success-metric computation from governed memory (Prompt 10).

All metrics are derived deterministically from the governed-memory records the
pilot writes, so they are fully reproducible from the audit ledger.
"""
from __future__ import annotations

from typing import Iterable, Optional

from memory.governed_memory import GovernedMemory

RISK_STATES = ("at_risk", "critical")
NON_VISIBLE = ("unknown", "contradictory")
MINUTES_PER_APPROVED = 15.0


def _latest_approvals(mem: GovernedMemory, tenant_ids: Iterable[str]) -> dict:
    approvals = []
    for t in tenant_ids:
        approvals.extend(mem.retrieve(tenant_id=t, kinds=["approval"], include_deleted=False))
    latest = {}
    for a in approvals:
        rid = a.body.get("recommendation_id")
        cur = latest.get(rid)
        if cur is None or a.record_id > cur.record_id:
            latest[rid] = a
    return latest


def compute_pilot_metrics(mem: GovernedMemory, tenant_ids: Iterable[str], baseline: Optional[dict] = None) -> dict:
    tenant_ids = list(tenant_ids)
    recs = []
    for t in tenant_ids:
        recs.extend(mem.retrieve(tenant_id=t, include_deleted=False))
    recommendations = [r for r in recs if r.kind == "recommendation"]
    diagnoses = [r for r in recs if r.kind == "customer_context"]
    corrections = [r for r in recs if r.kind == "correction"]
    latest = _latest_approvals(mem, tenant_ids)
    states = [a.body.get("approval_state") for a in latest.values()]

    total_rec = len(recommendations)
    approved = states.count("approved")
    missed = total_rec - approved

    escalations = [r for r in recommendations if "escalat" in r.body.get("action", "").lower()]
    esc_correct = sum(1 for r in escalations if r.body.get("correct"))
    esc_acc = (esc_correct / len(escalations)) if escalations else 1.0

    visible = sum(1 for d in diagnoses if d.body.get("health_state") not in NON_VISIBLE)
    vis_rate = (visible / len(diagnoses)) if diagnoses else 0.0

    open_risk = sum(d.body.get("open_risk_count", 0) for d in diagnoses)
    unresolved_age = open_risk * 3  # synthetic days/risk factor

    correction_rate = (len(corrections) / len(recs)) if recs else 0.0
    acc_rate = (approved / total_rec) if total_rec else 0.0
    base_rt = (baseline or {}).get("response_time", 0.0)
    # Dry-run does not execute actions, so realized == baseline (honest 0.0 reduction).
    reduction = round(max(0.0, float(base_rt) - float(base_rt)), 2)
    operator_time_saved = approved * MINUTES_PER_APPROVED

    return {
        "response_time_reduction": reduction,
        "escalation_accuracy": round(esc_acc, 3),
        "unresolved_risk_age": unresolved_age,
        "customer_health_visibility": round(vis_rate, 3),
        "missed_follow_ups": missed,
        "recommendation_acceptance_rate": round(acc_rate, 3),
        "correction_rate": round(correction_rate, 3),
        "operator_time_saved_min": operator_time_saved,
    }
