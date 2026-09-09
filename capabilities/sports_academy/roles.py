"""Academy roles, responsibilities, and authority boundaries (v1).

Pack-local only — these roles are NOT merged into the core role catalog
(organization/role-catalog.yaml / ORGANIZATION_CATALOG) until the capability
loader exists (blueprint §2.3). Core GM mapping is recorded as metadata for
that future merge, never enforced from here.
"""
from __future__ import annotations

# Roles present at one sports-academy location.
ROLES = (
    "academy_owner",
    "head_coach",
    "coach",
    "academy_admin",
    "parent",
)

RESPONSIBILITIES = {
    "academy_owner": "Final accountability for the academy; approves enrollments, renewals, and fee actions.",
    "head_coach": "Owns coaching delivery and coach quality; approves attendance-ops escalations.",
    "coach": "Delivers sessions; records check-in/check-out and daily attendance reports.",
    "academy_admin": "Runs front-desk operations; owns enrollment and renewal paperwork.",
    "parent": "Read-only access to their own children's schedule, attendance, and fees; holds no approval authority.",
}

# Authority boundaries: which role OWNS a workflow, and which role must
# APPROVE any committal action it produces (separation of duties).
AUTHORITY_BOUNDARIES = {
    "enrollment": {"owner_role": "academy_admin", "approver_role": "academy_owner"},
    "attendance_ops": {"owner_role": "coach", "approver_role": "head_coach"},
    "renewal": {"owner_role": "academy_admin", "approver_role": "academy_owner"},
    "facility_booking": {"owner_role": "academy_admin", "approver_role": "head_coach"},
    "fee_record": {"owner_role": "academy_admin", "approver_role": "academy_owner"},
}

# Metadata for the future capability-loader role merge (NOT enforced in v1).
MAPS_TO_AGENT = {
    "academy_owner": "sami",
    "head_coach": "ops_gm",
    "coach": "ops_gm",
    "academy_admin": "hr_personnel_gm",
    "parent": None,
}


def required_approver_role(category: str) -> str:
    return AUTHORITY_BOUNDARIES.get(category, {}).get("approver_role", "academy_owner")
