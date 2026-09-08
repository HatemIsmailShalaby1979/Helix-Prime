"""Connector write governance policy.

This module implements the governance gate for connector writes. It maps
capabilities to risk tiers and enforces the approval workflow.
"""
from __future__ import annotations

from typing import Any, Mapping


# Risk tier mapping by capability type
RISK_TIERS: dict[str, int] = {
    "read": 1,
    "write_local": 2,
    "write_external": 3,
    "write_critical": 4,
    "write_financial": 5,
}


def get_risk_tier(capability_id: str) -> int:
    """Get the risk tier for a capability.

    Args:
        capability_id: The capability identifier.

    Returns:
        Risk tier (1-5), defaulting to 3 if unknown.
    """
    for prefix, tier in RISK_TIERS.items():
        if capability_id.startswith(prefix):
            return tier
    return 3


def evaluate_write_gate(
    capability_id: str,
    data_mode: str,
    provider_activated: bool,
) -> dict[str, Any]:
    """Evaluate whether a write is permitted.

    Args:
        capability_id: The capability being written.
        data_mode: Current data mode (simulated_realistic, live_external, etc.)
        provider_activated: Whether the provider is activated for live writes.

    Returns:
        Dict with keys:
            - permitted: bool
            - reason: str
            - approval_required: bool
            - risk_tier: int
    """
    risk_tier = get_risk_tier(capability_id)

    # Block writes in sample/simulated mode
    if data_mode in ("simulated_realistic", "historical_anonymized", "historical_consented"):
        return {
            "permitted": False,
            "reason": "write_blocked_by_data_mode",
            "approval_required": False,
            "risk_tier": risk_tier,
        }

    # Block unactivated providers
    if not provider_activated:
        return {
            "permitted": False,
            "reason": "provider_not_activated",
            "approval_required": True,
            "risk_tier": risk_tier,
        }

    # High-risk writes always require approval
    if risk_tier >= 4:
        return {
            "permitted": True,
            "reason": "approval_required_for_risk_tier",
            "approval_required": True,
            "risk_tier": risk_tier,
        }

    # Low-risk writes may be auto-approved
    return {
        "permitted": True,
        "reason": "auto_approved",
        "approval_required": False,
        "risk_tier": risk_tier,
    }
