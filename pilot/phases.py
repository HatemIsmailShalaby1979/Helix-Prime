"""Pilot phase + permission controls for the first real design-partner pilot.

The first real pilot MUST begin in a read-only period: it previews and records
recommendations but is not permitted to approve/commit any committal action until
the period is explicitly exited (an audited, human decision). Connector
permissions are read-only by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .exceptions import PilotError

READ_ONLY = "read_only"
SUPERVISED = "supervised"
CLOSED = "closed"


@dataclass(frozen=True)
class ReadOnlyPeriod:
    starts_at: str
    ends_at: str
    note: str = ("Initial pilot phase is read-only: previews/recommendations only, "
                 "no committal approvals until explicitly exited.")

    def is_active(self, as_of: str) -> bool:
        return self.starts_at <= as_of <= self.ends_at

    def enforce(self, as_of: str) -> None:
        if self.is_active(as_of):
            raise PilotError("read-only period active: committal approvals are not permitted yet")


@dataclass(frozen=True)
class ConnectorPermissions:
    providers: Tuple[str, ...] = ("zendesk", "salesforce", "clay")
    read_allowed: bool = True
    write_allowed: bool = False
    note: str = "Connectors are permitted read-only; all write capabilities are denied in the pilot."

    def validate(self) -> "ConnectorPermissions":
        if self.write_allowed:
            raise PilotError("connector write permissions are not permitted in the pilot")
        return self
