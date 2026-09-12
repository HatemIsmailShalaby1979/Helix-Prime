"""Sports-academy capability-pack registration (v1).

A capability pack is registered once with metadata describing its ontology,
roles, workflows, policies, metrics, connector contracts, data
classifications, approval requirements, failure modes, and fixtures. The
registry is the single place the rest of the system discovers what a pack
provides. Mirrors capabilities/restaurant/register.py.
"""
from __future__ import annotations

from .roles import ROLES, RESPONSIBILITIES, AUTHORITY_BOUNDARIES, MAPS_TO_AGENT
from .workflows import WORKFLOW_CATEGORIES
from .classifications import DATA_CLASSIFICATIONS

REGISTRY: dict = {}


def get_academy_metadata() -> dict:
    return {
        "name": "sports_academy_operations",
        "domain": "sports_academy",
        "version": "1.0.0",
        "read_only_start": True,
        "synthetic_data_only": True,
        "production_readiness": "NOT_ESTABLISHED",
        "ontology": [
            "Athlete",
            "Family",
            "Coach",
            "Program",
            "Session",
            "CheckIn",
            "FacilitySlot",
            "FeePayment",
            "EnrollmentRecord",
        ],
        "roles": list(ROLES),
        "responsibilities": dict(RESPONSIBILITIES),
        "workflows": list(WORKFLOW_CATEGORIES),
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "maps_to_agent": dict(MAPS_TO_AGENT),
        "metrics": [
            "attendance_rate",
            "churn_rate",
            "facility_utilization",
            "mrr",
            "active_athletes",
            "session_adherence",
            "athlete_attendance_rate",
            "session_delivery_ontime",
            "parent_satisfaction",
        ],
        "connector_contracts": {
            "provider": "AcademyOps",
            "base": "connectors.base.BaseConnector",
            "reads": [
                "athletes",
                "families",
                "coaches",
                "programs",
                "sessions",
                "checkins",
                "facility_slots",
                "fee_payments",
                "enrollment_records",
            ],
            "writes": [],
            "write_executed_by_default": False,
        },
        "data_classifications": dict(DATA_CLASSIFICATIONS),
        "approval_requirements": "manual approval with owner + SOD; committal actions blocked during read-only period",
        "failure_modes": [
            "connector_unavailable",
            "scope_mismatch",
            "missing_data",
            "stale_data",
            "conflicting_recommendation",
            "approval_denied",
        ],
        "fixtures": "build_synthetic_academy(tenant_id, client_id, as_of)",
        "reused_core": [
            "security.identity",
            "memory.governed_memory",
            "connectors.base",
            "control_plane.workflow",
            "pilot.approval",
            "pilot.phases",
            "pilot.consent",
            "metacognition.improvement",
            "engines.rta.adapter",
            "engines.cx.adapter",
            "GOVERNANCE.governance_check",
        ],
    }


def register_capability(name: str, metadata: dict) -> dict:
    REGISTRY[name] = metadata
    return metadata


def get_capability(name: str):
    return REGISTRY.get(name)


# Auto-register on import so discovery works without extra wiring.
register_capability("sports_academy_operations", get_academy_metadata())
