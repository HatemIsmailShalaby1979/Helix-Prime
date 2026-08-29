"""Data classifications for restaurant data (Prompt 11, item 7).

Maps fields to the canonical classification vocabulary used by the security core
(public / internal / client_confidential / personnel_sensitive / financial /
regulated_high_risk). The pack collects only the minimum necessary data.
"""
from __future__ import annotations

# Field -> classification. Personnel-sensitive and financial fields are flagged so
# the pack can exclude them from operational recommendations unless explicitly consented.
DATA_CLASSIFICATIONS = {
    "shift_schedule": "client_confidential",
    "employee_name": "personnel_sensitive",
    "employee_role": "client_confidential",
    "inventory_levels": "client_confidential",
    "supplier_lead_time": "internal",
    "complaint_text": "client_confidential",
    "complaint_severity": "client_confidential",
    "daily_covers": "internal",
    "daily_revenue": "financial",
}


def classify(field: str) -> str:
    return DATA_CLASSIFICATIONS.get(field, "client_confidential")
