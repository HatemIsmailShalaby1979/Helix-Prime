"""Attendance adapter (v1) — check-in/check-out tracking via the RTA engine.

Maps academy Session/CheckIn records onto the RTA schedule-vs-actual contract
(`agent_id` = athlete, `scheduled_hours` = expected session hours,
`actual_hours` = hours actually attended) and invokes the reused
``engines.rta.adapter.adapt`` so every computation carries engine evidence,
provenance, and the sample-data boundary.

Nothing here executes a write. Outcomes are recorded in governed memory by the
caller via :func:`record_attendance_outcome` when a runtime is provided.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from connectors.contracts import ConnectorContext

from ..ontology import CheckIn, Session

DATA_MODE = "simulated_realistic"


def _hours(start: str, end: str) -> float:
    fmt = "%H:%M"
    s = datetime.strptime(start, fmt)
    e = datetime.strptime(end, fmt)
    return round((e - s).total_seconds() / 3600.0, 2)


def _attended_hours(session: Session, checkin: CheckIn) -> float:
    if checkin.check_out_at is None:
        end = session.end
    else:
        end = checkin.check_out_at[11:16]
    return _hours(session.start, end)


def compute_attendance(
    sessions: Sequence[Session],
    checkins: Sequence[CheckIn],
) -> Dict[str, Any]:
    """Pure attendance computation from sessions + check-ins.

    Returns per-session and per-athlete attendance rates plus the overall
    rate — deterministic, no I/O, no engine dependency. Used directly by
    tests, KPI computations, and as the fallback when the RTA engine is
    unavailable (fail-closed: the engine is evidence, this is arithmetic).
    """
    by_session: Dict[str, Dict[str, Any]] = {}
    for s in sessions:
        roster = set(s.roster)
        present = {c.athlete_id for c in checkins if c.session_id == s.session_id}
        by_session[s.session_id] = {
            "date": s.date,
            "program_id": s.program_id,
            "coach_id": s.coach_id,
            "roster_size": len(roster),
            "present": len(present & roster),
            "absent": len(roster - present),
            "attendance_rate": (len(present & roster) / len(roster)) if roster else 0.0,
        }

    per_athlete: Dict[str, Dict[str, int]] = {}
    for s in sessions:
        for athlete_id in s.roster:
            slot = per_athlete.setdefault(athlete_id, {"expected": 0, "attended": 0})
            slot["expected"] += 1
            if any(c.athlete_id == athlete_id and c.session_id == s.session_id for c in checkins):
                slot["attended"] += 1

    total_expected = sum(v["expected"] for v in per_athlete.values())
    total_attended = sum(v["attended"] for v in per_athlete.values())
    overall = (total_attended / total_expected) if total_expected else 0.0

    return {
        "overall_attendance_rate": round(overall, 4),
        "total_expected": total_expected,
        "total_attended": total_attended,
        "by_session": by_session,
        "by_athlete": {
            aid: {
                "expected": v["expected"],
                "attended": v["attended"],
                "attendance_rate": round(v["attended"] / v["expected"], 4)
                if v["expected"]
                else 0.0,
            }
            for aid, v in per_athlete.items()
        },
    }


def build_rta_payloads(
    sessions: Sequence[Session],
    checkins: Sequence[CheckIn],
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the schedule/actual DataFrames payload for the RTA engine.

    One row per (athlete, session). `agent_id` carries the athlete id so RTA's
    per-agent adherence becomes per-athlete adherence. `hour` collapses to 0
    (a single slot per session) because academy sessions are not hourly.
    """
    import pandas as pd

    rows_schedule = []
    rows_actual = []
    checkin_index = {(c.athlete_id, c.session_id): c for c in checkins}
    for s in sessions:
        if date is not None and s.date != date:
            continue
        scheduled_hours = _hours(s.start, s.end)
        for athlete_id in s.roster:
            rows_schedule.append(
                {
                    "agent_id": athlete_id,
                    "date": s.date,
                    "hour": 0,
                    "scheduled_hours": scheduled_hours,
                }
            )
            c = checkin_index.get((athlete_id, s.session_id))
            if c is not None:
                rows_actual.append(
                    {
                        "agent_id": athlete_id,
                        "date": s.date,
                        "hour": 0,
                        "actual_hours": _attended_hours(s, c),
                    }
                )
    return {
        "schedule": pd.DataFrame(rows_schedule),
        "actual": pd.DataFrame(rows_actual),
    }


def rta_attendance_adherence(
    sessions: Sequence[Session],
    checkins: Sequence[CheckIn],
    *,
    tenant_id: str,
    client_id: str,
    correlation_id: str,
    actor: str = "academy-operator",
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke the reused RTA engine adapter on academy attendance data.

    Runs in sample mode (`is_sample=True`) — pack data is synthetic by
    construction. The engine call is made under the academy owner's mapped GM
    role ``ops_gm`` because the RTA engine enforces that ownership; pack-local
    attendance governance (coach/head-coach) applies at the approval layer.
    Returns the engine's metrics dict (overall_adherence,
    agent_adherence = per-athlete adherence, date_adherence, ...).
    """
    from engines.rta.adapter import adapt as rta_adapt

    payloads = build_rta_payloads(sessions, checkins, date=date)
    if payloads["schedule"].empty:
        return {
            "overall_adherence": 0.0,
            "agent_adherence": {},
            "date_adherence": {},
            "empty": True,
        }
    result = rta_adapt(
        input_payload={
            "schedule": payloads["schedule"],
            "actual": payloads["actual"],
            "is_sample": True,
        },
        tenant_id=tenant_id,
        client_id=client_id,
        correlation_id=correlation_id,
        causation_id=None,
        actor=actor,
        owning_role_id="ops_gm",
        is_sample=True,
    )
    if result.error is not None:
        return {"engine_error": dict(result.error), "overall_adherence": None}
    return dict(result.metrics)


def daily_adherence_report(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    as_of: str,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """One-day attendance + adherence report for the owner/coach dashboards.

    Reads through the governed connector (tenant-scoped), computes pure
    attendance, and augments with RTA engine adherence for the same day.
    """
    conn = connectors["academy_ops"]
    sessions = conn.list_sessions(ctx)
    checkins = conn.list_checkins(ctx)
    day_sessions = [s for s in sessions if date is None or s.date == date] or list(sessions)
    report_date = date or (day_sessions[0].date if day_sessions else as_of[:10])
    day_session_ids = {s.session_id for s in day_sessions}
    day_checkins = [c for c in checkins if c.session_id in day_session_ids]

    attendance = compute_attendance(day_sessions, day_checkins)
    adherence = rta_attendance_adherence(
        day_sessions,
        day_checkins,
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        correlation_id=ctx.correlation_id or f"attendance-{report_date}",
    )
    return {
        "date": report_date,
        "attendance": attendance,
        "rta_adherence": adherence,
        "sessions_reported": len(day_sessions),
        "evidence_ref": f"attendance-report-{report_date}",
    }


def record_attendance_outcome(
    mem,
    ctx: ConnectorContext,
    report: Dict[str, Any],
    as_of: str,
    actor: str = "academy-operator",
    role_id: str = "coach",
) -> str:
    """Record a daily attendance report as a governed-memory outcome.

    Nature is ``simulated_event`` — synthetic data may never be recorded as a
    verified outcome (constitution: simulated, historical, and live data
    remain visibly distinct).
    """
    rec = mem.add(
        kind="outcome",
        nature="simulated_event",
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        actor=actor,
        role_id=role_id,
        source="academy_attendance",
        classification="client_confidential",
        timestamp=as_of,
        correlation_id=ctx.correlation_id or f"attendance-{report.get('date')}",
        confidence=1.0,
        evidence_refs=[report.get("evidence_ref", "attendance-report")],
        data_mode=DATA_MODE,
        provenance={
            "correlation_id": ctx.correlation_id or f"attendance-{report.get('date')}",
            "data_mode": DATA_MODE,
            "basis": "daily_attendance_report",
            "sources": [report.get("evidence_ref", "attendance-report")],
        },
        body={
            "action": "daily_attendance_report",
            "date": report.get("date"),
            "overall_attendance_rate": report.get("attendance", {}).get("overall_attendance_rate"),
            "sessions_reported": report.get("sessions_reported"),
            "overall_adherence": report.get("rta_adherence", {}).get("overall_adherence"),
        },
    )
    return rec.record_id


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
