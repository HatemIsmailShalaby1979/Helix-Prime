"""Sports-academy capability pack (v1).

Reuses the governed Helix Codex core. Starts read-only with synthetic data and
never activates live connectors or external writes, and never auto-improves.
Built for the first design partner (private sports academy, one location).
"""
from __future__ import annotations

from .ontology import (  # noqa: F401
    Athlete, Family, Coach, Program, Session, CheckIn,
    FacilitySlot, FeePayment, EnrollmentRecord,
)
from .contracts import AcademyConnector, build_academy_connectors  # noqa: F401
from .fixtures import build_synthetic_academy  # noqa: F401
from .adapters.attendance_adapter import (  # noqa: F401
    compute_attendance, daily_adherence_report, record_attendance_outcome,
)

DATA_MODE = "simulated_realistic"

__all__ = [
    "Athlete", "Family", "Coach", "Program", "Session", "CheckIn",
    "FacilitySlot", "FeePayment", "EnrollmentRecord",
    "AcademyConnector", "build_academy_connectors",
    "build_synthetic_academy",
    "compute_attendance", "daily_adherence_report", "record_attendance_outcome",
    "DATA_MODE",
]
