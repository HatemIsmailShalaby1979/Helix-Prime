"""Small-restaurant capability pack (Prompt 11).

Reuses the governed Helix Codex core. Starts read-only with synthetic data and never
activates live connectors or external writes, and never auto-improves.
"""
from __future__ import annotations

from contracts.vocabulary import CONNECTOR_SIMULATED_REALISTIC

from .classifications import DATA_CLASSIFICATIONS  # noqa: F401
from .contracts import RestaurantConnector, build_restaurant_connectors  # noqa: F401
from .fixtures import build_synthetic_restaurant  # noqa: F401
from .metrics import compute_restaurant_metrics  # noqa: F401
from .ontology import (  # noqa: F401
    Complaint,
    DailySummary,
    Employee,
    InventoryItem,
    Shift,
    Supplier,
)
from .policies import POLICIES, authority_for  # noqa: F401
from .register import REGISTRY, get_capability, register_capability  # noqa: F401
from .roles import (  # noqa: F401
    AUTHORITY_BOUNDARIES,
    RESPONSIBILITIES,
    ROLES,
    required_approver_role,
)
from .runtime import RestaurantCapabilityPack  # noqa: F401
from .workflows import (  # noqa: F401
    WORKFLOW_CATEGORIES,
    RestaurantDiagnosis,
    RiskFinding,
    run_all_workflows,
)

DATA_MODE = CONNECTOR_SIMULATED_REALISTIC

__all__ = [
    "Employee",
    "Shift",
    "InventoryItem",
    "Supplier",
    "Complaint",
    "DailySummary",
    "ROLES",
    "RESPONSIBILITIES",
    "AUTHORITY_BOUNDARIES",
    "required_approver_role",
    "RestaurantConnector",
    "build_restaurant_connectors",
    "RestaurantDiagnosis",
    "RiskFinding",
    "run_all_workflows",
    "WORKFLOW_CATEGORIES",
    "POLICIES",
    "authority_for",
    "DATA_CLASSIFICATIONS",
    "compute_restaurant_metrics",
    "build_synthetic_restaurant",
    "RestaurantCapabilityPack",
    "REGISTRY",
    "register_capability",
    "get_capability",
    "DATA_MODE",
]
