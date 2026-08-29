"""Pilot evidence pack assembly (Prompt 10)."""
from __future__ import annotations

from typing import Any

from .metrics import compute_pilot_metrics
from .scope import LIVE_CUSTOMER


def build_evidence_pack(runtime: Any, as_of: str) -> dict:
    mem = runtime.mem
    tenant_ids = runtime.tenant_ids
    metrics = compute_pilot_metrics(mem, tenant_ids, runtime.baseline_metrics)

    all_recs = mem._records
    mode_counts: dict = {}
    for r in all_recs:
        mode_counts[r.data_mode] = mode_counts.get(r.data_mode, 0) + 1

    latest = {}
    for a in all_recs:
        if a.kind != "approval":
            continue
        rid = a.body.get("recommendation_id")
        cur = latest.get(rid)
        if cur is None or a.record_id > cur.record_id:
            latest[rid] = a
    states = [a.body.get("approval_state") for a in latest.values()]

    incidents = [
        {"action": r.body.get("action"), "target": r.body.get("target"),
         "reason": r.body.get("reason")}
        for r in all_recs
        if r.kind == "workflow_history" and r.body.get("action") in ("connector_failure", "rollback", "incident")
    ]

    ok, _ = mem.verify_chain()
    scope = runtime.scope
    rop = runtime.read_only_period
    return {
        "pilot_mode": {
            "phase": runtime.phase,
            "read_only_period": (
                {"starts_at": rop.starts_at, "ends_at": rop.ends_at} if rop else None
            ),
            "connector_permissions": {
                "read_allowed": runtime.connector_permissions.read_allowed,
                "write_allowed": runtime.connector_permissions.write_allowed,
            },
        },
        "pilot_id": "helix-codex-design-partner-pilot",
        "generated_at": as_of,
        "scope": {
            "name": scope.name,
            "objectives": list(scope.objectives),
            "data_classification_default": scope.data_classification.default,
            "minimum_data_enabled": scope.minimum_data.enabled,
            "tenant_isolation_enabled": scope.tenant_isolation.enabled,
            "read_only_connectors": scope.read_only_connectors.writes_enabled is False,
            "retention_days": scope.retention.retention_days,
        },
        "consent": (runtime.consent.__dict__ if runtime.consent else None),
        "config": {
            "read_only_connectors": runtime.config.read_only_connectors,
            "tenant_isolation_enabled": runtime.config.tenant_isolation_enabled,
            "minimum_data": runtime.config.minimum_data,
            "live_activated": runtime.config.live_activated,
            "permitted_data_modes": list(runtime.config.permitted_data_modes),
        },
        "data_mode_breakdown": mode_counts,
        "live_customer_records": mode_counts.get(LIVE_CUSTOMER, 0),
        "metrics": metrics,
        "baseline_metrics": runtime.baseline_metrics,
        "approval_summary": {
            "total": len(latest),
            "approved": states.count("approved"),
            "denied": states.count("denied"),
            "draft": states.count("draft"),
            "rolled_back": states.count("rolled_back"),
        },
        "incidents": incidents,
        "audit_status": mem.audit_status(),
        "audit_chain_intact": ok,
        "review_checklist": [item.__dict__ for item in scope.review_checklist],
        "final_status": runtime.final_status(),
    }
