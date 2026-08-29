"""Policies and authority boundaries (Prompt 11, item 4).

Reuses the role/authority model from :mod:`roles` and lists the standing policies
the pack enforces. Approvals are manual and gated by separation of duties; the
read-only first version never executes a committal write.
"""
from __future__ import annotations

from .roles import AUTHORITY_BOUNDARIES, required_approver_role

POLICIES = (
    "All connectors are read-only; writes require an explicit cross-role approval and an activated live adapter (not present in the pilot).",
    "Every committal recommendation requires a manual approval record with an owner and an approval state (draft/approved/denied/rolled_back).",
    "Self-approval and same-role approval are denied (separation of duties).",
    "The first real pilot begins in a read-only period; committal approvals are blocked until it is explicitly exited.",
    "Only minimum necessary data is collected; personnel-sensitive and financial fields are excluded from operational recommendations unless consented.",
    "Synthetic data is clearly marked (data_mode=simulated_realistic) and is never presented as live customer data.",
    "Every outcome is recorded in governed memory with provenance, correlation ID, data mode, and approval state.",
)


def authority_for(category: str) -> dict:
    return AUTHORITY_BOUNDARIES.get(category, {"owner_role": "restaurant_gm", "approver_role": "restaurant_gm"})


__all__ = ["POLICIES", "AUTHORITY_BOUNDARIES", "required_approver_role", "authority_for"]
