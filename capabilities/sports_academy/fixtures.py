"""Synthetic sports-academy fixtures for the read-only pilot (v1).

Clearly synthetic, deterministic data for one location. Used only for
demonstration; no live customer data and no network access.

Seeded patterns (deterministic, used by tests downstream):
- ~40 athletes across 2 programs, ~85% overall attendance (seeded RNG 42).
- Athletes ath-risk-1 and ath-risk-2 have deliberately declining attendance
  (miss the last 4 scheduled sessions) — they must surface as churn-risk flags
  in the athlete-profile adapter tests (S3).
- Facility ~65% booked (13 of 20 slots booked).
- 3 manual fee records (2 paid, 1 outstanding).
"""
from __future__ import annotations

import random

from connectors.contracts import SourceRef

from .ontology import (
    Athlete, Coach, CheckIn, EnrollmentRecord, Family, FeePayment,
    FacilitySlot, Program, Session,
)

DATA_MODE = "simulated_realistic"

_SESSION_DATES = (
    "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
    "2026-09-05", "2026-09-06", "2026-09-07",
)

_ATTENDANCE_SEED = 42


def _src(provider: str, record_id: str, as_of: str) -> SourceRef:
    return SourceRef(provider, record_id, as_of, "v1-synthetic", DATA_MODE)


def build_synthetic_academy(tenant_id: str, client_id: str, as_of: str) -> dict:
    families = [
        Family(f"fam-{i:02d}", f"Parent {i:02d}", f"+1-555-01{i:02d}",
               f"parent{i:02d}@example.com", tenant_id, client_id,
               _src("CRM", f"fam-{i:02d}", as_of))
        for i in range(1, 21)
    ]

    coaches = [
        Coach(f"coach-{i}", name, tenant_id, client_id,
              _src("HR", f"coach-{i}", as_of))
        for i, name in enumerate(
            ("Coach Ahmed", "Coach Sara", "Coach Yusuf", "Coach Lena",
             "Coach Marco", "Coach Priya"), start=1)
    ]

    programs = [
        Program("prog-u12", "U12 Football", 200.0, tenant_id, client_id,
                _src("Programs", "prog-u12", as_of)),
        Program("prog-u15", "U15 Basketball", 220.0, tenant_id, client_id,
                _src("Programs", "prog-u15", as_of)),
    ]

    athlete_names = [f"Athlete {i:02d}" for i in range(1, 41)]
    athletes = []
    for i, name in enumerate(athlete_names, start=1):
        program_id = "prog-u12" if i <= 20 else "prog-u15"
        athlete_id = f"ath-{i:02d}"
        status = "active"
        if i == 39:
            status = "inquiry"
        elif i == 40:
            status = "trial"
        athletes.append(Athlete(
            athlete_id, name, f"2014-{((i % 12) + 1):02d}-{((i % 28) + 1):02d}",
            program_id, f"fam-{((i + 1) // 2):02d}", status,
            tenant_id, client_id, _src("CRM", athlete_id, as_of),
        ))

    sessions = []
    checkins = []
    facility_slots = []
    session_seq = 0
    rng = random.Random(_ATTENDANCE_SEED)
    for day_idx, date in enumerate(_SESSION_DATES):
        for prog_idx, program_id in enumerate(("prog-u12", "prog-u15")):
            coach = coaches[(day_idx + prog_idx) % len(coaches)]
            slot_id = f"slot-{date}-{prog_idx + 1}"
            surface = "field-a" if prog_idx == 0 else "court-1"
            start, end = ("16:00", "17:30") if prog_idx == 0 else ("18:00", "19:30")
            session_seq += 1
            session_id = f"ses-{session_seq:03d}"
            roster = tuple(a.athlete_id for a in athletes
                            if a.program_id == program_id and a.enrollment_status == "active")
            facility_slots.append(FacilitySlot(
                slot_id, date, start, end, surface, session_id,
                tenant_id, client_id, _src("Facility", slot_id, as_of),
            ))
            sessions.append(Session(
                session_id, date, start, end, program_id, coach.coach_id,
                slot_id, roster, tenant_id, client_id,
                _src("Scheduling", session_id, as_of),
            ))
            for athlete_id in roster:
                # ~85% attendance via a seeded RNG (hash() is randomized
                # across processes and cannot be used); ath-risk-1/ath-risk-2
                # miss the last 4 days to seed churn-risk detection
                attends = (rng.random() < 0.85) if athlete_id not in ("ath-01", "ath-02") else (day_idx < 3)
                if not attends:
                    continue
                checkin_seq = len(checkins) + 1
                checkins.append(CheckIn(
                    f"chk-{checkin_seq:04d}", athlete_id, session_id,
                    f"{date}T{start}:00Z", f"{date}T{end}:00Z",
                    tenant_id, client_id,
                    _src("Attendance", f"chk-{checkin_seq:04d}", as_of),
                ))
    # 20 facility slots total; add 7 unbooked ones so utilization = 13/20 = 65%
    unbooked_dates = _SESSION_DATES[:7]
    for i, date in enumerate(unbooked_dates):
        slot_id = f"slot-{date}-free-{i + 1}"
        facility_slots.append(FacilitySlot(
            slot_id, date, "10:00", "11:30", "field-b", None,
            tenant_id, client_id, _src("Facility", slot_id, as_of),
        ))

    fee_payments = [
        FeePayment("pay-001", "ath-01", "fam-01", "prog-u12", 200.0, "USD",
                   "2026-09-01", "2026-09-01T10:00:00Z", "cash",
                   tenant_id, client_id, _src("Billing", "pay-001", as_of)),
        FeePayment("pay-002", "ath-02", "fam-01", "prog-u12", 200.0, "USD",
                   "2026-09-01", "2026-09-02T09:00:00Z", "bank transfer",
                   tenant_id, client_id, _src("Billing", "pay-002", as_of)),
        FeePayment("pay-003", "ath-03", "fam-02", "prog-u12", 200.0, "USD",
                   "2026-09-01", None, "outstanding reminder sent",
                   tenant_id, client_id, _src("Billing", "pay-003", as_of)),
    ]

    enrollment_records = [
        EnrollmentRecord("enr-001", "ath-39", "inquiry", "2026-08-28T09:00:00Z",
                         "parent called, wants Saturday trial", tenant_id, client_id,
                         _src("CRM", "enr-001", as_of)),
        EnrollmentRecord("enr-002", "ath-40", "trial", "2026-08-30T09:00:00Z",
                         "trial booked for 2026-09-05", tenant_id, client_id,
                         _src("CRM", "enr-002", as_of)),
    ]

    return {
        "families": families,
        "coaches": coaches,
        "programs": programs,
        "athletes": athletes,
        "sessions": sessions,
        "checkins": checkins,
        "facility_slots": facility_slots,
        "fee_payments": fee_payments,
        "enrollment_records": enrollment_records,
    }
