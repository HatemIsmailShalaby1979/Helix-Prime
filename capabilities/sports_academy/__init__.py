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
from .adapters.athlete_profile_adapter import (  # noqa: F401
    athlete_profile, churn_risk_scores, record_churn_flags,
)
from .adapters.facility_adapter import (  # noqa: F401
    detect_booking_conflicts, facility_overview, facility_utilization,
)
from .adapters.payment_adapter import (  # noqa: F401
    fee_status_overview, monthly_recurring_revenue, outstanding_fees,
    record_manual_payment,
)
from .roles import (  # noqa: F401
    ROLES, RESPONSIBILITIES, AUTHORITY_BOUNDARIES, MAPS_TO_AGENT,
    required_approver_role,
)
from .workflows import (  # noqa: F401
    AcademyDiagnosis, RiskFinding, attendance_flow, enrollment_flow,
    renewal_flow, load_flow_declaration,
)
from .kpis import (  # noqa: F401
    compute_academy_metrics, compute_all_coach_metrics, compute_coach_metrics,
)
from .runtime import AcademyCapabilityPack  # noqa: F401
from .register import (  # noqa: F401
    REGISTRY, register_capability, get_capability, get_academy_metadata,
)

DATA_MODE = "simulated_realistic"

__all__ = [
    "Athlete", "Family", "Coach", "Program", "Session", "CheckIn",
    "FacilitySlot", "FeePayment", "EnrollmentRecord",
    "AcademyConnector", "build_academy_connectors",
    "build_synthetic_academy",
    "compute_attendance", "daily_adherence_report", "record_attendance_outcome",
    "athlete_profile", "churn_risk_scores", "record_churn_flags",
    "detect_booking_conflicts", "facility_overview", "facility_utilization",
    "fee_status_overview", "monthly_recurring_revenue", "outstanding_fees",
    "record_manual_payment",
    "ROLES", "RESPONSIBILITIES", "AUTHORITY_BOUNDARIES", "MAPS_TO_AGENT",
    "required_approver_role",
    "AcademyDiagnosis", "RiskFinding", "attendance_flow", "enrollment_flow",
    "renewal_flow", "load_flow_declaration",
    "compute_academy_metrics", "compute_all_coach_metrics", "compute_coach_metrics",
    "AcademyCapabilityPack",
    "REGISTRY", "register_capability", "get_capability", "get_academy_metadata",
    "DATA_MODE",
]
