"""Roles, responsibilities, and authority boundaries (Prompt 11)."""
from __future__ import annotations

# Roles present at a small restaurant location.
ROLES = (
    "restaurant_owner",
    "restaurant_gm",
    "shift_manager",
    "assistant_manager",
    "kitchen_lead",
    "staff",
)

RESPONSIBILITIES = {
    "restaurant_owner": "Final accountability for the location; approves high-risk committal actions.",
    "restaurant_gm": "Day-to-day operations; owns operational workflows and approves escalations.",
    "shift_manager": "Runs a shift; owns staffing and shift-coverage recommendations.",
    "assistant_manager": "Supports the shift manager; owns inventory and supplier recommendations.",
    "kitchen_lead": "Owns kitchen inventory and food-quality complaints.",
    "staff": "Executes assigned tasks; holds no approval authority.",
}

# Authority boundaries: which role OWNS a workflow category, and which role must
# APPROVE any committal action it produces (separation of duties).
AUTHORITY_BOUNDARIES = {
    "staffing_risk": {"owner_role": "shift_manager", "approver_role": "restaurant_gm"},
    "shift_coverage": {"owner_role": "shift_manager", "approver_role": "restaurant_gm"},
    "inventory_risk": {"owner_role": "assistant_manager", "approver_role": "restaurant_gm"},
    "supplier_delay": {"owner_role": "assistant_manager", "approver_role": "restaurant_gm"},
    "complaint_escalation": {"owner_role": "restaurant_gm", "approver_role": "restaurant_owner"},
    "daily_summary": {"owner_role": "restaurant_gm", "approver_role": "restaurant_owner"},
}


def required_approver_role(category: str) -> str:
    return AUTHORITY_BOUNDARIES.get(category, {}).get("approver_role", "restaurant_gm")
