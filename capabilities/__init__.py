"""Helix Codex capability packs.

A capability pack reuses the governed core (identity, tenant isolation, governance,
connectors, workflows, approvals, evidence, memory, metrics, metacognitive proposals)
and adds a business-specific ontology + workflows. It does NOT create a separate
platform. Each pack must preserve tenant/client identity, provenance, correlation IDs,
data mode, approval state, outcome recording, and the audit trail.
"""
from __future__ import annotations

from .restaurant.register import REGISTRY, register_capability, get_capability

__all__ = ["REGISTRY", "register_capability", "get_capability"]
