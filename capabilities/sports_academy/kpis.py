"""Academy KPI computation (v1) — derived from pack data and governed memory.

Every KPI declared in declarations/{academy,coach}_kpis.yaml has a compute
function here; drift between the YAML declarations and this module is enforced
by tests. Targets come from the YAML (single source) and are embedded in the
output so dashboards render value + target + direction together.
Pattern: capabilities/restaurant/metrics.py — deterministic, reproducible,
computed from records, no I/O, no live timing claims.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, Optional, Sequence

import yaml

from .ontology import Athlete, CheckIn, Coach, FeePayment, Session

_DECLARATIONS = pathlib.Path(__file__).parent / "declarations"


def load_kpi_definitions(which: str) -> Dict[str, Any]:
    """Load canonical KPI declarations (academy | coach) from YAML."""
    path = _DECLARATIONS / f"{which}_kpis.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {kpi["id"]: kpi for kpi in data["kpis"]}


ACADEMY_KPI_TARGETS: Dict[str, float] = {
    kpi_id: kpi["target"] for kpi_id, kpi in load_kpi_definitions("academy").items()
}
COACH_KPI_TARGETS: Dict[str, float] = {
    kpi_id: kpi["target"] for kpi_id, kpi in load_kpi_definitions("coach").items()
}


def attendance_rate(athletes: Sequence[Athlete],
                    sessions: Sequence[Session],
                    checkins: Sequence[CheckIn]) -> float:
    if not sessions:
        return 0.0
    expected = sum(len(s.roster) for s in sessions)
    if not expected:
        return 0.0
    attended = len({(c.athlete_id, c.session_id) for c in checkins
                    if c.session_id in {s.session_id for s in sessions}})
    return round(attended / expected, 4)


def churn_rate(athletes: Sequence[Athlete]) -> float:
    if not athletes:
        return 0.0
    churned = sum(1 for a in athletes if a.enrollment_status in ("churned",))
    inactive = sum(1 for a in athletes if a.enrollment_status == "inquiry")
    return round((churned + inactive) / len(athletes), 4) if athletes else 0.0


def facility_utilization(facility_slots: Sequence[Any]) -> float:
    if not facility_slots:
        return 0.0
    booked = sum(1 for s in facility_slots if s.booked_by_session_id is not None)
    return round(booked / len(facility_slots), 4)


def monthly_recurring_revenue(athletes: Sequence[Athlete],
                              programs: Sequence[Any]) -> float:
    """Sum of monthly program fees for active athletes (design-point MRR)."""
    fee_by_program = {p.program_id: p.monthly_fee for p in programs}
    total = sum(fee_by_program.get(a.program_id, 0.0)
                for a in athletes if a.enrollment_status == "active")
    return round(total, 2)


def active_athletes(athletes: Sequence[Athlete]) -> int:
    return sum(1 for a in athletes if a.enrollment_status == "active")


def compute_academy_metrics(*, athletes: Sequence[Athlete],
                           sessions: Sequence[Session],
                           checkins: Sequence[CheckIn],
                           facility_slots: Sequence[Any],
                           programs: Sequence[Any],
                           fee_payments: Optional[Sequence[FeePayment]] = None) -> Dict[str, Any]:
    """The 5 owner-dashboard numbers + targets, from pack data."""
    return {
        "attendance_rate": _with_target(
            attendance_rate(athletes, sessions, checkins), "attendance_rate",
            ACADEMY_KPI_TARGETS, direction="higher_is_better"),
        "churn_rate": _with_target(
            churn_rate(athletes), "churn_rate",
            ACADEMY_KPI_TARGETS, direction="lower_is_better"),
        "facility_utilization": _with_target(
            facility_utilization(facility_slots), "facility_utilization",
            ACADEMY_KPI_TARGETS, direction="higher_is_better"),
        "mrr": _with_target(
            monthly_recurring_revenue(athletes, programs), "mrr",
            ACADEMY_KPI_TARGETS, direction="higher_is_better"),
        "active_athletes": _with_target(
            active_athletes(athletes), "active_athletes",
            ACADEMY_KPI_TARGETS, direction="higher_is_better"),
    }


def coach_sessions_map(sessions: Sequence[Session]) -> Dict[str, Sequence[Session]]:
    out: Dict[str, list] = {}
    for s in sessions:
        out.setdefault(s.coach_id, []).append(s)
    return out


def _coach_athlete_attendance(sessions: Sequence[Session],
                              checkins: Sequence[CheckIn]) -> float:
    if not sessions:
        return 0.0
    attended = len({(c.athlete_id, c.session_id) for c in checkins
                    if c.session_id in {s.session_id for s in sessions}})
    expected = sum(len(s.roster) for s in sessions)
    return round(attended / expected, 4) if expected else 0.0


def compute_coach_metrics(coach: Coach,
                          sessions: Sequence[Session],
                          checkins: Sequence[CheckIn]) -> Dict[str, Any]:
    """The 4 coach KPIs for one coach, from pack data.

    session_delivery_ontime: in the synthetic read-only pilot every scheduled
    session is considered delivered on time unless no athlete checked in at all
    (a proxy for a cancelled session); a live adapter will use real coach
    check-ins.
    """
    coach_sessions = [s for s in sessions if s.coach_id == coach.coach_id]
    delivered = sum(
        1 for s in coach_sessions
        if any(c.session_id == s.session_id for c in checkins)
    )
    session_adherence = round(delivered / len(coach_sessions), 4) if coach_sessions else 0.0
    ontime = session_adherence  # pilot proxy: delivered == on time (see docstring)
    return {
        "coach_id": coach.coach_id,
        "coach_name": coach.name,
        "sessions_scheduled": len(coach_sessions),
        "sessions_delivered": delivered,
        "session_adherence": _with_target(
            session_adherence, "session_adherence",
            COACH_KPI_TARGETS, direction="higher_is_better"),
        "athlete_attendance_rate": _with_target(
            _coach_athlete_attendance(coach_sessions, checkins),
            "athlete_attendance_rate",
            COACH_KPI_TARGETS, direction="higher_is_better"),
        "session_delivery_ontime": _with_target(
            ontime, "session_delivery_ontime",
            COACH_KPI_TARGETS, direction="higher_is_better"),
        "parent_satisfaction": _with_target(
            None, "parent_satisfaction",
            COACH_KPI_TARGETS, direction="higher_is_better"),
    }


def compute_all_coach_metrics(coaches: Sequence[Coach],
                              sessions: Sequence[Session],
                              checkins: Sequence[CheckIn]) -> Dict[str, Dict[str, Any]]:
    return {c.coach_id: compute_coach_metrics(c, sessions, checkins)
            for c in coaches}


def _with_target(value: Optional[float], kpi_id: str,
                 targets: Dict[str, float], *, direction: str) -> Dict[str, Any]:
    target = targets.get(kpi_id)
    return {
        "value": value,
        "target": target,
        "direction": direction,
        "met": (value is not None and target is not None and (
            value >= target if direction == "higher_is_better" else value <= target
        )),
    }
