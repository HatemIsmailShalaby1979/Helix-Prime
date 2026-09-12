"""Academy domain adapters (v1).

Each adapter maps pack-local data onto reused core engines where applicable:
- attendance → engines/rta (schedule vs actual adherence)
- athlete profiles → pack-local CRM records (+ engines/cx churn features in S3)
- facility / payments → pack-local, read-only or manual-record-only
"""
from __future__ import annotations

from .attendance_adapter import (  # noqa: F401
    compute_attendance,
    daily_adherence_report,
    record_attendance_outcome,
)
from .athlete_profile_adapter import (  # noqa: F401
    athlete_profile,
    churn_risk_scores,
    record_churn_flags,
)
from .facility_adapter import (  # noqa: F401
    detect_booking_conflicts,
    facility_overview,
    facility_utilization,
)
from .payment_adapter import (  # noqa: F401
    fee_status_overview,
    monthly_recurring_revenue,
    outstanding_fees,
    record_manual_payment,
)
