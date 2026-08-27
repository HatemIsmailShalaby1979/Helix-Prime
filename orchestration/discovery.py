"""
Capability-based discovery for Helix Prime Codex C1a.

Provides deterministic, fail-closed routing by capability, with legacy
name-based compatibility preserved via adapter.

Usage:
    from orchestration.discovery import discover_agent, discover_engine, route_by_capability
    from contracts.task import TaskRequest

    owner = discover_agent("wfm_forecast")  # -> "ops_gm"
    engine = discover_engine("erlang_c")    # -> "WFM Forecasting"
    owner = route_by_capability(request)    # -> TaskRequest.capability owner

Legacy fallback: if capability is unknown, caller should handle ValueError as
review queue, not silent execution. Name-based orchestrator._resolve_agents
remains for keyword routing until C2 replaces it.
"""
from __future__ import annotations

from typing import Any

from organization.capability_registry import (
    get_agent_for_capability as discover_agent,
    get_engine_for_capability as discover_engine,
    discover,
    route_task_request,
    is_tool_allowed,
    get_capabilities_for_role,
)


def route_by_capability(request: Any) -> str:
    """Deterministic routing for TaskRequest by its capability field."""
    return route_task_request(request)


__all__ = [
    "discover_agent",
    "discover_engine",
    "discover",
    "route_by_capability",
    "is_tool_allowed",
    "get_capabilities_for_role",
]
