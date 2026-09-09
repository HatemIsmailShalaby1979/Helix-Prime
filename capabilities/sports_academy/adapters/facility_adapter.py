"""Facility adapter (v1) — court/field booking, conflicts, utilization.

Read-only over the connector's facility slots. Overlap-conflict detection is
a pure function over slot tuples; utilization feeds the owner dashboard's
facility KPI. No booking writes exist in v1 (facility_booking committal
actions require approval through the pack runtime).
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from connectors.contracts import ConnectorContext

from ..ontology import FacilitySlot

DATA_MODE = "simulated_realistic"


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _overlaps(a: FacilitySlot, b: FacilitySlot) -> bool:
    if a.date != b.date:
        return False
    if a.surface != b.surface:
        return False
    return _minutes(a.start) < _minutes(b.end) and _minutes(b.start) < _minutes(a.end)


def detect_booking_conflicts(
    facility_slots: Sequence[FacilitySlot],
) -> List[Dict[str, Any]]:
    """Pure conflict detection: two *booked* slots overlapping on date+surface."""
    booked = [s for s in facility_slots if s.booked_by_session_id is not None]
    conflicts: List[Dict[str, Any]] = []
    for i in range(len(booked)):
        for j in range(i + 1, len(booked)):
            a, b = booked[i], booked[j]
            if _overlaps(a, b):
                conflicts.append({
                    "slot_a": a.slot_id, "slot_b": b.slot_id,
                    "date": a.date, "surface": a.surface,
                    "window": f"{a.start}–{b.end}",
                    "sessions": sorted({a.booked_by_session_id, b.booked_by_session_id}),
                })
    return conflicts


def facility_utilization(facility_slots: Sequence[FacilitySlot]) -> float:
    if not facility_slots:
        return 0.0
    booked = sum(1 for s in facility_slots if s.booked_by_session_id is not None)
    return round(booked / len(facility_slots), 4)


def facility_overview(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
) -> Dict[str, Any]:
    """Slot inventory + utilization + conflicts for the admin/owner view."""
    conn = connectors["academy_ops"]
    slots = conn.list_facility_slots(ctx)
    return {
        "data_mode": DATA_MODE,
        "total_slots": len(slots),
        "booked_slots": sum(1 for s in slots if s.booked_by_session_id is not None),
        "utilization": facility_utilization(slots),
        "conflicts": detect_booking_conflicts(slots),
        "slots": [
            {"slot_id": s.slot_id, "date": s.date, "start": s.start, "end": s.end,
             "surface": s.surface, "booked": s.booked_by_session_id is not None,
             "session_id": s.booked_by_session_id}
            for s in sorted(slots, key=lambda s: (s.date, s.surface, s.start))
        ],
    }
