"""Pilot configuration: read-only-first, minimum-data, tenant isolation (Prompt 10)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from .exceptions import PilotError
from .scope import HISTORICAL_CONSENTED, SIMULATED_REALISTIC, LIVE_CUSTOMER


@dataclass
class PilotConfig:
    read_only_connectors: bool = True
    tenant_isolation_enabled: bool = True
    minimum_data: bool = True
    live_activated: bool = False
    permitted_data_modes: Tuple[str, ...] = (HISTORICAL_CONSENTED, SIMULATED_REALISTIC)
    retention_days: int = 90

    @classmethod
    def from_dict(cls, d: dict) -> "PilotConfig":
        d = dict(d or {})
        return cls(
            read_only_connectors=d.get("read_only_connectors", True),
            tenant_isolation_enabled=d.get("tenant_isolation_enabled", True),
            minimum_data=d.get("minimum_data", True),
            live_activated=d.get("live_activated", False),
            permitted_data_modes=tuple(d.get("permitted_data_modes", (HISTORICAL_CONSENTED, SIMULATED_REALISTIC))),
            retention_days=d.get("retention_days", 90),
        )

    def validate(self) -> "PilotConfig":
        if self.live_activated:
            raise PilotError("live customer data activation is not permitted in the pilot package")
        if LIVE_CUSTOMER in self.permitted_data_modes:
            raise PilotError("live customer data mode is not permitted in the pilot package")
        if not self.read_only_connectors:
            raise PilotError("pilot requires read-only connectors")
        if not self.tenant_isolation_enabled:
            raise PilotError("pilot requires tenant isolation")
        if not self.minimum_data:
            raise PilotError("pilot requires minimum-data policy")
        return self
