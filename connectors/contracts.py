"""Provider-neutral, read-first connector contracts.

Connectors are deliberately small and deterministic. Vendor adapters may use
HTTP later, but the control plane only consumes these normalized records.
"""
from __future__ import annotations

import datetime as _datetime
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

SCHEMA_VERSION = "1.0"


def _now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _version(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ConnectorStatus(str, Enum):
    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"
    AUTHENTICATED = "authenticated"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    REVOKED = "revoked"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class RateLimitPolicy:
    """Deterministic rate-limit behavior. Window is tracked by absolute call
    count on the connector instance (no wall-clock dependency in tests)."""
    max_requests_per_window: int = 1000
    window_seconds: int = 60
    on_exceed: str = "fail_closed"  # "fail_closed" | "throttle"


@dataclass(frozen=True)
class RetryPolicy:
    """Deterministic retry behavior. backoff_seconds is informational; the
    connector never sleeps in tests — retries are countable and immediate."""
    max_attempts: int = 3
    backoff_seconds: float = 0.0
    retry_on: tuple[str, ...] = ("transient", "rate_limited")


@dataclass(frozen=True)
class ConnectorCapability:
    connector_id: str
    provider: str
    capability_id: str
    version: str = SCHEMA_VERSION
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    risk_class: str = "client_confidential"
    writes_require_approval: bool = True
    data_classification: str = "client_confidential"
    rate_limit: RateLimitPolicy = field(default_factory=RateLimitPolicy)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    approval_required: bool = True


@dataclass(frozen=True)
class ConnectorContext:
    tenant_id: str
    organization_id: str
    client_id: str
    actor: str = "codex"
    correlation_id: str = ""
    data_mode: str = "simulated_realistic"
    data_classification: str = "client_confidential"

    def __post_init__(self) -> None:
        for name in ("tenant_id", "organization_id", "client_id", "actor"):
            if not getattr(self, name).strip():
                raise ValueError(f"ConnectorContext.{name}: must be non-empty")
        if self.data_mode not in {"historical_anonymized", "historical_consented", "simulated_realistic", "live_external"}:
            raise ValueError(f"ConnectorContext.data_mode: unsupported {self.data_mode!r}")


@dataclass(frozen=True)
class SourceRef:
    provider: str
    record_id: str
    observed_at: str
    input_version: str
    data_mode: str


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    lifecycle_stage: str
    owner: str | None
    source: SourceRef
    tenant_id: str
    client_id: str
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SupportTicket:
    ticket_id: str
    account_id: str
    subject: str
    status: str
    priority: str
    sla_breached: bool
    created_at: str
    source: SourceRef
    tenant_id: str
    client_id: str


@dataclass(frozen=True)
class CustomerSignal:
    signal_id: str
    account_id: str
    signal_type: str
    value: float
    observed_at: str
    source: SourceRef
    tenant_id: str
    client_id: str


@dataclass(frozen=True)
class EnrichmentResult:
    account_id: str
    fields: Mapping[str, Any]
    confidence: float
    source: SourceRef
    tenant_id: str
    client_id: str

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("EnrichmentResult.confidence: must be between 0 and 1")


class Connector(Protocol):
    connector_id: str
    provider: str

    def status(self) -> ConnectorStatus: ...
    def capabilities(self) -> Sequence[ConnectorCapability]: ...
    def health_check(self) -> Mapping[str, Any]: ...
    def list_accounts(self, context: ConnectorContext) -> Sequence[Account]: ...
    def list_tickets(self, context: ConnectorContext, account_id: str) -> Sequence[SupportTicket]: ...
    def enrich_account(self, context: ConnectorContext, account: Account) -> EnrichmentResult: ...


@dataclass(frozen=True)
class Provenance:
    """Record-level provenance for every connector result. Captures where the
    data came from, under which tenant/client/correlation scope, and in which
    data mode (so simulated data is never mistaken for live external data)."""
    provider: str
    connector_id: str
    fetched_at: str
    record_count: int
    data_mode: str
    correlation_id: str
    source_refs: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class FailureDetail:
    """Typed failure envelope. `retryable` tells the retry policy whether the
    failure is safe to retry."""
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True)
class ConnectorResult:
    """Uniform envelope returned by every read path.

    status: "ok" | "rate_limited" | "error" | "unavailable" | "refused"
    """
    status: str
    data: Any = None
    error: FailureDetail | None = None
    provenance: Provenance | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class WriteRequest:
    capability_id: str
    payload: Mapping[str, Any]
    approval_id: str | None = None
    actor: str = "codex"


@dataclass(frozen=True)
class ConnectorWriteResult:
    """Uniform envelope returned by every write path.

    In the read-only first version, `executed` is always False. Writes require
    an explicit, cross-role approval AND an activated live adapter.
    """
    executed: bool
    approval_required: bool
    reason: str
    provenance: Provenance | None = None
    correlation_id: str = ""
