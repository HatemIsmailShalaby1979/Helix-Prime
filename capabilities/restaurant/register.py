"""Capability-pack registry (Prompt 11, verification: registration).

A capability pack is registered once with metadata describing its ontology, roles,
workflows, policies, metrics, connector contracts, data classifications, approval
requirements, failure modes, and fixtures. The registry is the single place the
rest of the system discovers what a pack provides.
"""
from __future__ import annotations

from .roles import ROLES, RESPONSIBILITIES, AUTHORITY_BOUNDARIES
from .workflows import WORKFLOW_CATEGORIES
from .policies import POLICIES
from .classifications import DATA_CLASSIFICATIONS
from .contracts import RestaurantConnector

REGISTRY: dict = {}


def get_restaurant_metadata() -> dict:
    return {
        "name": "restaurant_operations",
        "domain": "small_restaurant",
        "read_only_start": True,
        "synthetic_data_only": True,
        "production_readiness": "NOT_ESTABLISHED",
        "ontology": ["Employee", "Shift", "InventoryItem", "Supplier", "Complaint", "DailySummary"],
        "roles": list(ROLES),
        "responsibilities": dict(RESPONSIBILITIES),
        "workflows": list(WORKFLOW_CATEGORIES),
        "policies": list(POLICIES),
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "metrics": [
            "response_time_reduction", "escalation_accuracy", "unresolved_risk_age",
            "customer_health_visibility", "missed_follow_ups", "recommendation_acceptance_rate",
            "correction_rate",
        ],
        "connector_contracts": {
            "provider": "RestaurantOps",
            "base": "connectors.base.BaseConnector",
            "reads": ["shifts", "inventory", "suppliers", "complaints", "daily_summary"],
            "writes": ["reorder", "notify_staff"],
            "write_executed_by_default": False,
        },
        "data_classifications": dict(DATA_CLASSIFICATIONS),
        "approval_requirements": "manual approval with owner + SOD; committal actions blocked during read-only period",
        "failure_modes": [
            "connector_unavailable", "scope_mismatch", "missing_data", "stale_data",
            "conflicting_recommendation", "approval_denied",
        ],
        "fixtures": "build_synthetic_restaurant(tenant_id, client_id, as_of)",
        "reused_core": [
            "security.identity", "memory.governed_memory", "connectors.base",
            "control_plane.workflow", "pilot.approval", "pilot.phases",
            "pilot.consent", "metacognition.improvement", "release.gate",
            "GOVERNANCE.governance_check",
        ],
    }


def register_capability(name: str, metadata: dict) -> dict:
    REGISTRY[name] = metadata
    return metadata


def get_capability(name: str):
    return REGISTRY.get(name)


# Auto-register on import so discovery works without extra wiring.
register_capability("restaurant_operations", get_restaurant_metadata())
