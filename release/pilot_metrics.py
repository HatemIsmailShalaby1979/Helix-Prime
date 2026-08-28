"""
Helix Prime Codex post-C8 — controlled-pilot operational metrics.

Defines the measured pilot metrics and explicitly separates three distinct
kinds of value so they are never conflated:

  1. MEASURED synthetic dry-run values  — what a local run actually produced.
  2. PROPOSED pilot thresholds          — candidate operating thresholds for a
                                          real pilot; they are not validated
                                          targets and are NOT invented SLOs.
  3. PRODUCTION SLOs (not yet validated) — record that no production SLO is
                                          claimed until external validation.

Only measured synthetic dry-run values are asserted by tests. Proposed
thresholds and production SLOs are recorded as "proposed"/"not validated",
never treated as proof.
"""

from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Any, Dict, List, Optional

# The pilot metrics every dry-run measures.
METRIC_NAMES = [
    "workflow_completion_rate",
    "approval_denial_rate",
    "timeout_rate",
    "retry_rate",
    "dead_letter_rate",
    "audit_verification_rate",
    "data_classification_violations",
    "tenant_isolation_violations",
    "model_unavailable_count",
    "sibling_transport_failures",
    "exec_time_ms_mean",
    "exec_time_ms_p50",
    "exec_time_ms_p95",
    "exec_time_ms_p99",
]

# FAKE/NON-ENTRY: these are candidate operating thresholds a future real pilot
# might monitor. They are NOT validated targets and are explicitly not asserted
# as requirements anywhere. The pilot must gather its own evidence first.
PROPOSED_PILOT_THRESHOLDS: Dict[str, Optional[float]] = {
    "workflow_completion_rate_ge": None,   # not set: requires real-pilot evidence
    "approval_denial_rate_le": None,       # not set
    "timeout_rate_le": None,               # not set
    "retry_rate_le": None,                 # not set
    "dead_letter_rate_le": None,           # not set
    "audit_verification_rate_ge": 1.0,     # every audit chain must verify
    "data_classification_violations_le": 0.0,  # zero violations expected
    "tenant_isolation_violations_le": 0.0,     # zero violations expected
    "model_unavailable_count_le": None,    # not set
    "sibling_transport_failures_le": None, # not set
    "exec_time_p95_ms_le": None,           # not set
}

# Production SLOs are NOT validated; a pilot cannot claim them.
# Left as documented-not-set so no production SLO is ever fabricated.
PRODUCTION_SLOS_NOT_VALIDATED: Dict[str, Optional[float]] = {
    "availability_ge": None,
    "latency_p95_ms_le": None,
    "error_budget": None,
    "recovery_time_objective_seconds_le": None,
}


def pct(values: List[float], percentile: float) -> Optional[float]:
    """Simple nearest-rank percentile. Returns None on empty input."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(percentile / 100.0 * (len(s) - 1)))))
    return s[k]


def summarize(timings_ms: List[float]) -> Dict[str, Any]:
    """Summarize a list of local execution timings (ms)."""
    if not timings_ms:
        return {
            "exec_time_ms_mean": None,
            "exec_time_ms_p50": None,
            "exec_time_ms_p95": None,
            "exec_time_ms_p99": None,
            "n": 0,
        }
    return {
        "exec_time_ms_mean": round(mean(timings_ms), 3),
        "exec_time_ms_p50": round(median(timings_ms), 3),
        "exec_time_ms_p95": pct(timings_ms, 95),
        "exec_time_ms_p99": pct(timings_ms, 99),
        "n": len(timings_ms),
        "exec_time_ms_stddev": round(pstdev(timings_ms), 3),
    }


def build_summary(
    total_workflows: int,
    completed: int,
    denied_approvals: int,
    timeouts: int,
    retries: int,
    dead_letter: int,
    audit_verified: int,
    audit_total: int,
    data_classification_violations: int = 0,
    tenant_isolation_violations: int = 0,
    model_unavailable: int = 0,
    sibling_transport_failures: int = 0,
    timings_ms: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Aggregate deterministic measured metrics from a dry-run event stream.

    All rates are 0.0..1.0; counts are integers. No target thresholds are
    applied here — aggregation only. Thresholds are separate (see above).
    """
    timings_ms = timings_ms or []
    total = max(total_workflows, 1)
    timing = summarize(timings_ms)

    metrics: Dict[str, Any] = {
        "workflow_completion_rate": round(completed / total, 4),
        "approval_denial_rate": round(denied_approvals / total, 4)
        if denied_approvals
        else 0.0,
        "timeout_rate": round(timeouts / total, 4),
        "retry_rate": round(retries / total, 4),
        "dead_letter_rate": round(dead_letter / total, 4),
        "audit_verification_rate": round(audit_verified / audit_total, 4)
        if audit_total
        else 0.0,
        "data_classification_violations": data_classification_violations,
        "tenant_isolation_violations": tenant_isolation_violations,
        "model_unavailable_count": model_unavailable,
        "sibling_transport_failures": sibling_transport_failures,
        **timing,
    }

    return {
        "measured_synthetic_dry_run": metrics,
        "proposed_pilot_thresholds": dict(PROPOSED_PILOT_THRESHOLDS),
        "production_slos_not_validated": dict(PRODUCTION_SLOS_NOT_VALIDATED),
        "note": (
            "Measured values are from a synthetic dry run only. Proposed "
            "pilot thresholds are NOT validated targets and production SLOs "
            "are NOT claimed."
        ),
    }
