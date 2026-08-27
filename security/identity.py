"""
Identity and authorization — local-first seam for Helix Prime Codex C3.

Supports actor identity with type, tenant/client scope, role, capability, tool, action, approval authority.
No external IdP; deterministic, deny-by-default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class ActorType:
    HUMAN = "human"
    AGENT = "agent"
    SERVICE = "service"

    ALL = {HUMAN, AGENT, SERVICE}


@dataclass
class Identity:
    actor: str  # e.g., "sami", "compliance_user", "system"
    actor_type: str  # human/agent/service
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    role_id: Optional[str] = None  # e.g., "ops_gm", "sami"
    # For service identities, role may be None but capability still checked

    def __post_init__(self) -> None:
        if not isinstance(self.actor, str) or not self.actor.strip():
            raise ValueError(f"Identity.actor: must be non-empty string, got {self.actor!r}")
        self.actor = self.actor.strip()
        if self.actor_type not in ActorType.ALL:
            raise ValueError(f"Identity.actor_type: must be one of {sorted(ActorType.ALL)}, got {self.actor_type!r}")
        if self.tenant_id is not None:
            if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
                raise ValueError(f"Identity.tenant_id: must be non-empty string or None, got {self.tenant_id!r}")
            self.tenant_id = self.tenant_id.strip()
        if self.client_id is not None:
            if not isinstance(self.client_id, str) or not self.client_id.strip():
                raise ValueError(f"Identity.client_id: must be non-empty string, got {self.client_id!r}")
            self.client_id = self.client_id.strip()
        if self.role_id is not None:
            if not isinstance(self.role_id, str) or not self.role_id.strip():
                raise ValueError(f"Identity.role_id: must be non-empty string or None, got {self.role_id!r}")
            self.role_id = self.role_id.strip()

    def to_dict(self) -> dict:
        d = {"actor": self.actor, "actor_type": self.actor_type}
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.role_id is not None:
            d["role_id"] = self.role_id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Identity":
        return cls(
            actor=data.get("actor", ""),
            actor_type=data.get("actor_type", ""),
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            role_id=data.get("role_id"),
        )

    def scope_key(self) -> str:
        """Tenant/client scope for isolation checks."""
        return f"{self.tenant_id or '*'}:{self.client_id or '*'}"
