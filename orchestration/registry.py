"""
Orchestration registry — C1a compatibility wrapper.

Re-exports organization/capability_registry for orchestrator use.
Preserves legacy name-only resolution via compatibility adapter.
"""
from __future__ import annotations

from organization.capability_registry import (
    CapabilityRegistry,
    build_registry_from_catalog,
    get_agent_for_capability,
    get_capabilities_for_role,
    get_default_registry,
    get_engine_for_capability,
    is_capability_owned_by_role,
    is_tool_allowed,
    discover,
    route_task_request,
)

__all__ = [
    "CapabilityRegistry",
    "build_registry_from_catalog",
    "get_agent_for_capability",
    "get_capabilities_for_role",
    "get_default_registry",
    "get_engine_for_capability",
    "is_capability_owned_by_role",
    "is_tool_allowed",
    "discover",
    "route_task_request",
]
