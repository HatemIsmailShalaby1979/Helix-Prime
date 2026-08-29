"""Small-restaurant capability pack (Prompt 11).

Reuses the governed Helix Codex core. Starts read-only with synthetic data and never
activates live connectors or external writes, and never auto-improves.
"""
from __future__ import annotations

from .ontology import (  # noqa: F401
    Employee, Shift, InventoryItem, Supplier, Complaint, DailySummary,
)
from .roles import (  # noqa: F401
    ROLES, RESPONSIBILITIES, AUTHORITY_BOUNDARIES, required_approver_role,
)
from .contracts import RestaurantConnector, build_restaurant_connectors  # noqa: F401
from .workflows import (  # noqa: F401
    RestaurantDiagnosis, RiskFinding, run_all_workflows, WORKFLOW_CATEGORIES,
)
from .policies import POLICIES, authority_for  # noqa: F401
from .classifications import DATA_CLASSIFICATIONS  # noqa: F401
from .metrics import compute_restaurant_metrics  # noqa: F401
from .fixtures import build_synthetic_restaurant  # noqa: F401
from .runtime import RestaurantCapabilityPack  # noqa: F401
from .register import REGISTRY, register_capability, get_capability  # noqa: F401

DATA_MODE = "simulated_realistic"

__all__ = [
    "Employee", "Shift", "InventoryItem", "Supplier", "Complaint", "DailySummary",
    "ROLES", "RESPONSIBILITIES", "AUTHORITY_BOUNDARIES", "required_approver_role",
    "RestaurantConnector", "build_restaurant_connectors",
    "RestaurantDiagnosis", "RiskFinding", "run_all_workflows", "WORKFLOW_CATEGORIES",
    "POLICIES", "authority_for", "DATA_CLASSIFICATIONS", "compute_restaurant_metrics",
    "build_synthetic_restaurant", "RestaurantCapabilityPack",
    "REGISTRY", "register_capability", "get_capability", "DATA_MODE",
]
