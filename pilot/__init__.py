"""Helix Codex controlled design-partner pilot package (Prompt 10).

Read-only-first orchestration of the verified connector, customer-success,
governed-memory, and command-center building blocks. Does not activate live
connectors, cloud services, or external writes, and never auto-improves.
"""
from __future__ import annotations

from .config import PilotConfig
from .consent import ConsentRecord, validate_consent
from .evidence_pack import build_evidence_pack
from .exceptions import PilotError
from .phases import CLOSED, READ_ONLY, SUPERVISED, ConnectorPermissions, ReadOnlyPeriod
from .run import DEFAULT_AS_OF, PilotRuntime
from .scope import (
    HISTORICAL_CONSENTED,
    LIVE_CUSTOMER,
    SIMULATED_REALISTIC,
    PilotScope,
    default_scope,
)

__all__ = [
    "PilotConfig",
    "ConsentRecord",
    "validate_consent",
    "PilotError",
    "PilotRuntime",
    "DEFAULT_AS_OF",
    "PilotScope",
    "default_scope",
    "HISTORICAL_CONSENTED",
    "SIMULATED_REALISTIC",
    "LIVE_CUSTOMER",
    "READ_ONLY",
    "SUPERVISED",
    "CLOSED",
    "ReadOnlyPeriod",
    "ConnectorPermissions",
    "build_evidence_pack",
]
