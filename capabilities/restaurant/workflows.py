"""Core restaurant workflows (Prompt 11, items 3 & 9).

Each workflow is a pure, deterministic function over synthetic connector data. It
returns a :class:`RestaurantDiagnosis` (risk findings + recommended actions) with the
evidence refs that support it. The runtime records each diagnosis and its recommended
actions in governed memory; nothing here executes a write.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from connectors.contracts import ConnectorContext

from .ontology import Shift, InventoryItem, Supplier, Complaint, DailySummary

WORKFLOW_CATEGORIES = (
    "staffing_risk",
    "shift_coverage",
    "inventory_risk",
    "complaint_escalation",
    "supplier_delay",
    "daily_summary",
)


@dataclass
class RiskFinding:
    category: str
    severity: str  # low | medium | high
    detail: str
    evidence_ref: str


@dataclass
class RestaurantDiagnosis:
    category: str
    health_state: str  # ok | at_risk | critical
    confidence: float
    findings: Tuple[RiskFinding, ...]
    recommended_actions: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]


def _understaffed(shifts: Sequence[Shift]) -> list:
    out = []
    for s in shifts:
        gap = s.required_headcount - len(s.assigned)
        if gap > 0:
            out.append((s, gap))
    return out


def staffing_risk(shifts: Sequence[Shift], as_of: str) -> RestaurantDiagnosis:
    gaps = _understaffed(shifts)
    findings = [
        RiskFinding("staffing_risk", "high" if g >= 2 else "medium",
                    f"{s.shift_id} short by {g} (has {len(s.assigned)}/{s.required_headcount})",
                    s.source.record_id)
        for s, g in gaps
    ]
    actions = tuple(
        f"Approve overtime/notify shift manager to fill {s.shift_id} (need +{g})"
        for s, g in gaps
    )
    state = "critical" if any(g >= 2 for _, g in gaps) else ("at_risk" if gaps else "ok")
    return RestaurantDiagnosis(
        "staffing_risk", state, 0.8 if gaps else 1.0, tuple(findings), actions,
        tuple(f.evidence_ref for f in findings),
    )


def shift_coverage(shifts: Sequence[Shift], as_of: str) -> RestaurantDiagnosis:
    gaps = _understaffed(shifts)
    findings = [
        RiskFinding("shift_coverage", "medium", f"{s.shift_id} uncovered roles", s.source.record_id)
        for s, _ in gaps
    ]
    actions = tuple(
        f"Cross-train staff to cover {s.shift_id} (recommend adding flex capacity)"
        for s, _ in gaps
    )
    state = "at_risk" if gaps else "ok"
    return RestaurantDiagnosis(
        "shift_coverage", state, 0.75 if gaps else 1.0, tuple(findings), actions,
        tuple(f.evidence_ref for f in findings),
    )


def inventory_risk(inventory: Sequence[InventoryItem], as_of: str) -> RestaurantDiagnosis:
    low = [i for i in inventory if i.on_hand < i.par_level]
    findings = [
        RiskFinding("inventory_risk", "high" if i.par_level - i.on_hand >= i.par_level * 0.5 else "medium",
                    f"{i.name} at {i.on_hand}{i.unit} below par {i.par_level}{i.unit}",
                    i.source.record_id)
        for i in low
    ]
    actions = tuple(f"Reorder {i.name} from {i.supplier_id} (par {i.par_level}{i.unit})" for i in low)
    state = "critical" if any(i.par_level - i.on_hand >= i.par_level * 0.5 for i in low) else ("at_risk" if low else "ok")
    return RestaurantDiagnosis(
        "inventory_risk", state, 0.85 if low else 1.0, tuple(findings), actions,
        tuple(f.evidence_ref for f in findings),
    )


def complaint_escalation(complaints: Sequence[Complaint], as_of: str) -> RestaurantDiagnosis:
    breaches = [c for c in complaints if c.severity == "high" and c.status == "open" and c.sla_due_at <= as_of]
    findings = [
        RiskFinding("complaint_escalation", "high",
                    f"{c.complaint_id} high-severity, SLA due {c.sla_due_at}, still {c.status}",
                    c.source.record_id)
        for c in breaches
    ]
    actions = tuple(
        f"Escalate {c.complaint_id} to restaurant owner with corrective offer" for c in breaches
    )
    state = "critical" if breaches else "ok"
    return RestaurantDiagnosis(
        "complaint_escalation", state, 0.9 if breaches else 1.0, tuple(findings), actions,
        tuple(f.evidence_ref for f in findings),
    )


def supplier_delay(suppliers: Sequence[Supplier], inventory: Sequence[InventoryItem], as_of: str) -> RestaurantDiagnosis:
    risky = [s for s in suppliers if s.reliability < 0.8 or s.lead_time_days >= 4]
    findings = [
        RiskFinding("supplier_delay", "high" if s.reliability < 0.8 else "medium",
                    f"{s.name} reliability {s.reliability} lead {s.lead_time_days}d",
                    s.source.record_id)
        for s in risky
    ]
    actions = tuple(
        f"Confirm expedited delivery with {s.name} or pre-position alternate supplier" for s in risky
    )
    state = "at_risk" if risky else "ok"
    return RestaurantDiagnosis(
        "supplier_delay", state, 0.8 if risky else 1.0, tuple(findings), actions,
        tuple(f.evidence_ref for f in findings),
    )


def daily_summary(summary: Sequence[DailySummary], as_of: str) -> RestaurantDiagnosis:
    if not summary:
        return RestaurantDiagnosis("daily_summary", "unknown", 0.0, (), (), ())
    s = summary[0]
    unfilled = s.shifts_required - s.shifts_filled
    findings = []
    if unfilled > 0:
        findings.append(RiskFinding("daily_summary", "medium",
                                    f"{unfilled} shift roles unfilled ({s.shifts_filled}/{s.shifts_required})",
                                    s.source.record_id))
    if s.complaints_open > 0:
        findings.append(RiskFinding("daily_summary", "medium",
                                    f"{s.complaints_open} open complaints", s.source.record_id))
    actions = tuple(
        f"Review daily operating summary: {f.detail}" for f in findings
    )
    state = "at_risk" if findings else "ok"
    return RestaurantDiagnosis(
        "daily_summary", state, 0.9 if findings else 1.0, tuple(findings), actions,
        tuple(f.evidence_ref for f in findings),
    )


def run_all_workflows(
    shifts: Sequence[Shift], inventory: Sequence[InventoryItem],
    suppliers: Sequence[Supplier], complaints: Sequence[Complaint],
    summary: Sequence[DailySummary], ctx: ConnectorContext, as_of: str,
) -> list[RestaurantDiagnosis]:
    return [
        staffing_risk(shifts, as_of),
        shift_coverage(shifts, as_of),
        inventory_risk(inventory, as_of),
        complaint_escalation(complaints, as_of),
        supplier_delay(suppliers, inventory, as_of),
        daily_summary(summary, as_of),
    ]
