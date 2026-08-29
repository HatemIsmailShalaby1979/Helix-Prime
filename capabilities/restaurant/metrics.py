"""Operational metrics for the restaurant pack (Prompt 11, item 5).

Computed from governed-memory records so they are reproducible and auditable. The
metrics measure business value: response-time reduction, escalation accuracy,
unresolved-risk age, customer-health visibility, missed follow-ups, recommendation
acceptance, and correction rate. Dry-run (no live timing) yields a 0.0 baseline for
response-time reduction.
"""
from __future__ import annotations

from typing import Optional, Sequence

from memory.governed_memory import GovernedMemory


def _gather(mem: GovernedMemory, tenant_ids: Sequence[str]):
    recs = []
    for t in tenant_ids:
        recs.extend(mem.retrieve(tenant_id=t, include_deleted=True))
    return recs


def compute_restaurant_metrics(mem: GovernedMemory, tenant_ids: Sequence[str], baseline: Optional[dict] = None) -> dict:
    recs = _gather(mem, tenant_ids)
    recommendations = [r for r in recs if r.kind == "recommendation"]
    diagnoses = [r for r in recs if r.kind == "customer_context"]

    # latest approval state per recommendation
    latest = {}
    for a in recs:
        if a.kind != "approval":
            continue
        rid = a.body.get("recommendation_id")
        cur = latest.get(rid)
        if cur is None or a.record_id > cur.record_id:
            latest[rid] = a
    states = [a.body.get("approval_state") for a in latest.values()]
    approved = states.count("approved")
    denied = states.count("denied")
    draft = states.count("draft")
    rolled_back = states.count("rolled_back")

    escalations = [r for r in recommendations if "escalat" in (r.body.get("action") or "").lower()]
    if escalations:
        esc_acc = sum(1 for r in escalations if r.body.get("correct")) / len(escalations)
    else:
        esc_acc = 0.0

    acceptance = approved / (approved + denied) if (approved + denied) > 0 else 0.0
    corrections = [r for r in recs if r.kind == "correction"]
    correction_rate = len(corrections) / len(recommendations) if recommendations else 0.0

    visible = sum(1 for d in diagnoses if d.evidence_refs) if diagnoses else 0
    health_visibility = visible / len(diagnoses) if diagnoses else 0.0

    return {
        "response_time_reduction": 0.0,  # dry-run: no live timing captured
        "escalation_accuracy": esc_acc,
        "unresolved_risk_age_days": draft * 3,  # synthetic: open follow-ups age 3 days each
        "customer_health_visibility": health_visibility,
        "missed_follow_ups": draft,
        "recommendation_acceptance_rate": acceptance,
        "correction_rate": correction_rate,
        # supporting counts (not business-value claims, useful for review)
        "recommendations": len(recommendations),
        "approved": approved,
        "denied": denied,
        "draft": draft,
        "rolled_back": rolled_back,
    }
