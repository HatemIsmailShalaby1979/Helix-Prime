"""Helix Codex controlled design-partner pilot package (Prompt 10).

Read-only-first orchestration of the verified connector, customer-success,
governed-memory, and command-center building blocks. Does not activate live
connectors, cloud services, or external writes, and never auto-improves.
"""
from __future__ import annotations

from .config import PilotConfig
from .consent import ConsentRecord, validate_consent
from .exceptions import PilotError
from .phases import (READ_ONLY, SUPERVISED, CLOSED, ReadOnlyPeriod, ConnectorPermissions)
from .run import PilotRuntime, DEFAULT_AS_OF
from .scope import (
    PilotScope, default_scope,
    HISTORICAL_CONSENTED, SIMULATED_REALISTIC, LIVE_CUSTOMER,
)
from .evidence_pack import build_evidence_pack

__all__ = [
    "PilotConfig", "ConsentRecord", "validate_consent", "PilotError",
    "PilotRuntime", "DEFAULT_AS_OF", "PilotScope", "default_scope",
    "HISTORICAL_CONSENTED", "SIMULATED_REALISTIC", "LIVE_CUSTOMER",
    "READ_ONLY", "SUPERVISED", "CLOSED", "ReadOnlyPeriod", "ConnectorPermissions",
    "build_evidence_pack",
]
