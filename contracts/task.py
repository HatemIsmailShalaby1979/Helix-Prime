"""
Typed agent contracts for Helix Prime Codex C1.

Implements validated models for:
  CorrelationContext, TaskRequest, TaskResult, Recommendation, Action, Approval, EvidenceRef, AgentError

Design goals (C1 additive, local-first, no network/secrets):
- Explicit types, deterministic validation, clear error messages (no silent fallback)
- Every model carries schema_version, stable IDs, tenant/client, actor/role, timestamps
- Confidence only where applicable (Recommendation/TaskResult), validated 0.0-1.0
- Approval/ownership boundaries checked (no self-approval when SOD flag, approver != actor)
- Adapter retains call_agent(...) text as fallback; structured path is primary (see contracts/adapter.py)

No dependency on organization catalog (avoid circular import); role-id format validated as non-empty string.
"""
from __future__ import annotations

import dataclasses
import datetime
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"

# ── helpers ────────────────────────────────────────────────────────────────

def _require_non_empty_str(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be non-empty string, got {value!r}")
    return value.strip()


def _require_optional_str(value: Any, field_path: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_path}: must be string or null, got {type(value).__name__}")
    # allow empty? but normalize
    return value.strip()


def _validate_iso_timestamp(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    # accept both "2026-08-27T18:00:00Z" and "2026-08-27T18:00:00+00:00" and with microseconds
    try:
        cand = s.replace("Z", "+00:00") if s.endswith("Z") else s
        datetime.datetime.fromisoformat(cand)
    except Exception as e:
        raise ValueError(f"{field_path}: must be ISO8601 timestamp, got {s!r}: {e}") from e
    return s


def _validate_confidence(value: Any, field_path: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field_path}: confidence must be number 0.0-1.0, got {type(value).__name__}")
    f = float(value)
    if not (0.0 <= f <= 1.0):
        raise ValueError(f"{field_path}: confidence must be 0.0-1.0, got {f}")
    return f


def _require_dict(value: Any, field_path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_path}: must be mapping/dict, got {type(value).__name__}")
    return value


def _new_id(prefix: str = "") -> str:
    # stable sortable id: prefix + uuid4 hex 12
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex


def _validate_schema_version(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if not re.match(r"^\d+\.\d+$", s):
        raise ValueError(f"{field_path}: must be semver-like '1.0', got {s!r}")
    return s


# ── EvidenceRef ────────────────────────────────────────────────────────────

@dataclass
class EvidenceRef:
    """
    Reference to evidence supporting a decision/action.

    Required for human-supervised autonomy per Codex principle:
    every action is attributable with evidence reference.
    """
    evidence_id: str
    type: str  # e.g., log, engine_output, file, metric, approval, audit
    uri: str
    timestamp: str
    schema_version: str = SCHEMA_VERSION
    hash: Optional[str] = None
    actor: Optional[str] = None

    def __post_init__(self) -> None:
        self.evidence_id = _require_non_empty_str(self.evidence_id, "EvidenceRef.evidence_id")
        self.type = _require_non_empty_str(self.type, "EvidenceRef.type")
        self.uri = _require_non_empty_str(self.uri, "EvidenceRef.uri")
        self.timestamp = _validate_iso_timestamp(self.timestamp, "EvidenceRef.timestamp")
        self.schema_version = _validate_schema_version(self.schema_version, "EvidenceRef.schema_version")
        if self.hash is not None:
            self.hash = _require_non_empty_str(self.hash, "EvidenceRef.hash")
        if self.actor is not None:
            self.actor = _require_non_empty_str(self.actor, "EvidenceRef.actor")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "type": self.type,
            "uri": self.uri,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }
        if self.hash is not None:
            d["hash"] = self.hash
        if self.actor is not None:
            d["actor"] = self.actor
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRef":
        if not isinstance(data, dict):
            raise ValueError(f"EvidenceRef.from_dict: expected dict, got {type(data).__name__}")
        return cls(
            evidence_id=data.get("evidence_id", ""),
            type=data.get("type", ""),
            uri=data.get("uri", ""),
            timestamp=data.get("timestamp", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            hash=data.get("hash"),
            actor=data.get("actor"),
        )


# ── AgentError ─────────────────────────────────────────────────────────────

ALLOWED_ERROR_CODES = {
    "invalid_input",
    "missing_correlation",
    "unauthorized",
    "not_found",
    "policy_denied",
    "refused",
    "timeout",
    "engine_error",
    "approval_denied",
    "conflict",
    "dependency_unavailable",
}


@dataclass
class AgentError:
    error_id: str
    correlation_id: str
    code: str
    message: str
    timestamp: str
    schema_version: str = SCHEMA_VERSION
    retryable: bool = False
    evidence_ref: Optional[EvidenceRef] = None

    def __post_init__(self) -> None:
        self.error_id = _require_non_empty_str(self.error_id, "AgentError.error_id")
        self.correlation_id = _require_non_empty_str(self.correlation_id, "AgentError.correlation_id")
        self.code = _require_non_empty_str(self.code, "AgentError.code").lower()
        if self.code not in ALLOWED_ERROR_CODES:
            raise ValueError(
                f"AgentError.code: must be one of {sorted(ALLOWED_ERROR_CODES)}, got {self.code!r}"
            )
        self.message = _require_non_empty_str(self.message, "AgentError.message")
        self.timestamp = _validate_iso_timestamp(self.timestamp, "AgentError.timestamp")
        self.schema_version = _validate_schema_version(self.schema_version, "AgentError.schema_version")
        if not isinstance(self.retryable, bool):
            raise ValueError(f"AgentError.retryable: must be bool, got {type(self.retryable).__name__}")
        if self.evidence_ref is not None and not isinstance(self.evidence_ref, EvidenceRef):
            raise ValueError(f"AgentError.evidence_ref: must be EvidenceRef or null, got {type(self.evidence_ref).__name__}")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "error_id": self.error_id,
            "correlation_id": self.correlation_id,
            "code": self.code,
            "message": self.message,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "retryable": self.retryable,
        }
        if self.evidence_ref is not None:
            d["evidence_ref"] = self.evidence_ref.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentError":
        if not isinstance(data, dict):
            raise ValueError(f"AgentError.from_dict: expected dict, got {type(data).__name__}")
        ev = data.get("evidence_ref")
        return cls(
            error_id=data.get("error_id", ""),
            correlation_id=data.get("correlation_id", ""),
            code=data.get("code", ""),
            message=data.get("message", ""),
            timestamp=data.get("timestamp", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            retryable=bool(data.get("retryable", False)),
            evidence_ref=EvidenceRef.from_dict(ev) if isinstance(ev, dict) else None,
        )


# ── CorrelationContext ─────────────────────────────────────────────────────

@dataclass
class CorrelationContext:
    """
    Durable correlation for request tracing, idempotency, and tenant/client isolation.

    Required per Codex: every action is attributable with correlation ID and idempotency key.
    """
    correlation_id: str
    idempotency_key: str
    tenant_id: Optional[str]
    client_id: Optional[str]
    created_at: str
    schema_version: str = SCHEMA_VERSION
    trace_parent: Optional[str] = None

    def __post_init__(self) -> None:
        self.correlation_id = _require_non_empty_str(self.correlation_id, "CorrelationContext.correlation_id")
        self.idempotency_key = _require_non_empty_str(self.idempotency_key, "CorrelationContext.idempotency_key")
        # at least one of tenant_id or client_id should be present per spec; allow both, but require at least one non-empty
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "CorrelationContext.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "CorrelationContext.client_id")
        if not self.tenant_id and not self.client_id:
            raise ValueError("CorrelationContext: at least one of tenant_id or client_id must be non-empty")
        self.created_at = _validate_iso_timestamp(self.created_at, "CorrelationContext.created_at")
        self.schema_version = _validate_schema_version(self.schema_version, "CorrelationContext.schema_version")
        if self.trace_parent is not None:
            self.trace_parent = _require_non_empty_str(self.trace_parent, "CorrelationContext.trace_parent")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.trace_parent is not None:
            d["trace_parent"] = self.trace_parent
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorrelationContext":
        if not isinstance(data, dict):
            raise ValueError(f"CorrelationContext.from_dict: expected dict, got {type(data).__name__}")
        return cls(
            correlation_id=data.get("correlation_id", ""),
            idempotency_key=data.get("idempotency_key", ""),
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            created_at=data.get("created_at", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            trace_parent=data.get("trace_parent"),
        )

    @classmethod
    def new(
        cls,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> "CorrelationContext":
        cid = correlation_id or uuid.uuid4().hex
        ik = idempotency_key or uuid.uuid4().hex
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        return cls(
            correlation_id=cid,
            idempotency_key=ik,
            tenant_id=tenant_id,
            client_id=client_id,
            created_at=now,
        )


# ── Approval ───────────────────────────────────────────────────────────────

ALLOWED_APPROVAL_DECISIONS = {"approved", "denied"}


@dataclass
class Approval:
    approval_id: str
    correlation_id: str
    subject_id: str  # request_id or action_id being approved
    approver_actor: str
    approver_role_id: str
    decision: str
    reason: str
    timestamp: str
    schema_version: str = SCHEMA_VERSION
    evidence_ref: Optional[EvidenceRef] = None

    def __post_init__(self) -> None:
        self.approval_id = _require_non_empty_str(self.approval_id, "Approval.approval_id")
        self.correlation_id = _require_non_empty_str(self.correlation_id, "Approval.correlation_id")
        self.subject_id = _require_non_empty_str(self.subject_id, "Approval.subject_id")
        self.approver_actor = _require_non_empty_str(self.approver_actor, "Approval.approver_actor")
        self.approver_role_id = _require_non_empty_str(self.approver_role_id, "Approval.approver_role_id")
        self.decision = _require_non_empty_str(self.decision, "Approval.decision").lower()
        if self.decision not in ALLOWED_APPROVAL_DECISIONS:
            raise ValueError(
                f"Approval.decision: must be one of {sorted(ALLOWED_APPROVAL_DECISIONS)}, got {self.decision!r}"
            )
        self.reason = _require_non_empty_str(self.reason, "Approval.reason")
        self.timestamp = _validate_iso_timestamp(self.timestamp, "Approval.timestamp")
        self.schema_version = _validate_schema_version(self.schema_version, "Approval.schema_version")
        if self.evidence_ref is not None and not isinstance(self.evidence_ref, EvidenceRef):
            raise ValueError(f"Approval.evidence_ref: must be EvidenceRef or null, got {type(self.evidence_ref).__name__}")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "approval_id": self.approval_id,
            "correlation_id": self.correlation_id,
            "subject_id": self.subject_id,
            "approver_actor": self.approver_actor,
            "approver_role_id": self.approver_role_id,
            "decision": self.decision,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }
        if self.evidence_ref is not None:
            d["evidence_ref"] = self.evidence_ref.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Approval":
        if not isinstance(data, dict):
            raise ValueError(f"Approval.from_dict: expected dict, got {type(data).__name__}")
        ev = data.get("evidence_ref")
        return cls(
            approval_id=data.get("approval_id", ""),
            correlation_id=data.get("correlation_id", ""),
            subject_id=data.get("subject_id", ""),
            approver_actor=data.get("approver_actor", ""),
            approver_role_id=data.get("approver_role_id", ""),
            decision=data.get("decision", ""),
            reason=data.get("reason", ""),
            timestamp=data.get("timestamp", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            evidence_ref=EvidenceRef.from_dict(ev) if isinstance(ev, dict) else None,
        )


# ── Action ─────────────────────────────────────────────────────────────────

ALLOWED_ACTION_STATUSES = {"proposed", "approved", "denied", "executing", "succeeded", "failed", "compensated", "closed"}


@dataclass
class Action:
    action_id: str
    correlation: CorrelationContext
    tenant_id: Optional[str]
    client_id: Optional[str]
    actor: str
    owning_role_id: str
    capability: str
    payload: Dict[str, Any]
    requires_approval: bool
    status: str
    created_at: str
    schema_version: str = SCHEMA_VERSION
    approval: Optional[Approval] = None
    executed_at: Optional[str] = None
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    idempotency_key: Optional[str] = None

    def __post_init__(self) -> None:
        self.action_id = _require_non_empty_str(self.action_id, "Action.action_id")
        if not isinstance(self.correlation, CorrelationContext):
            raise ValueError(f"Action.correlation: must be CorrelationContext, got {type(self.correlation).__name__}")
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "Action.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "Action.client_id")
        if not self.tenant_id and not self.client_id and not self.correlation.tenant_id and not self.correlation.client_id:
            raise ValueError("Action: at least one of tenant_id/client_id (or correlation tenant/client) must be present")
        self.actor = _require_non_empty_str(self.actor, "Action.actor")
        self.owning_role_id = _require_non_empty_str(self.owning_role_id, "Action.owning_role_id")
        self.capability = _require_non_empty_str(self.capability, "Action.capability")
        self.payload = _require_dict(self.payload, "Action.payload")
        if not isinstance(self.requires_approval, bool):
            raise ValueError(f"Action.requires_approval: must be bool, got {type(self.requires_approval).__name__}")
        self.status = _require_non_empty_str(self.status, "Action.status").lower()
        if self.status not in ALLOWED_ACTION_STATUSES:
            raise ValueError(f"Action.status: must be one of {sorted(ALLOWED_ACTION_STATUSES)}, got {self.status!r}")
        self.created_at = _validate_iso_timestamp(self.created_at, "Action.created_at")
        self.schema_version = _validate_schema_version(self.schema_version, "Action.schema_version")
        if self.approval is not None and not isinstance(self.approval, Approval):
            raise ValueError(f"Action.approval: must be Approval or null, got {type(self.approval).__name__}")
        if self.executed_at is not None:
            self.executed_at = _validate_iso_timestamp(self.executed_at, "Action.executed_at")
        if not isinstance(self.evidence_refs, list):
            raise ValueError(f"Action.evidence_refs: must be list, got {type(self.evidence_refs).__name__}")
        for i, ev in enumerate(self.evidence_refs):
            if not isinstance(ev, EvidenceRef):
                raise ValueError(f"Action.evidence_refs[{i}]: must be EvidenceRef, got {type(ev).__name__}")
        if self.idempotency_key is not None:
            self.idempotency_key = _require_non_empty_str(self.idempotency_key, "Action.idempotency_key")
        else:
            # default to correlation's key if not provided
            self.idempotency_key = self.correlation.idempotency_key

        # ownership boundary: if requires_approval and approval present, approver must differ from actor when SOD would apply.
        # C1 enforces: approver_actor != actor (no self-approval) when requires_approval True.
        if self.requires_approval and self.approval is not None:
            if self.approval.approver_actor == self.actor:
                raise ValueError(
                    f"Action: approver_actor {self.approval.approver_actor!r} cannot be same as actor {self.actor!r} (self-approval forbidden)"
                )
            if self.approval.approver_role_id == self.owning_role_id:
                # flag but allow if explicitly documented; for C1 we forbid same-role approval when requires_approval
                # This enforces SOD: cannot approve own actions.
                raise ValueError(
                    f"Action: approver_role_id {self.approval.approver_role_id!r} cannot be same as owning_role_id {self.owning_role_id!r} (SOD violation)"
                )
            if self.approval.correlation_id != self.correlation.correlation_id:
                raise ValueError(
                    f"Action: approval correlation_id {self.approval.correlation_id!r} must match action correlation {self.correlation.correlation_id!r}"
                )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "action_id": self.action_id,
            "correlation": self.correlation.to_dict(),
            "actor": self.actor,
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "payload": self.payload,
            "requires_approval": self.requires_approval,
            "status": self.status,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "idempotency_key": self.idempotency_key,
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.approval is not None:
            d["approval"] = self.approval.to_dict()
        if self.executed_at is not None:
            d["executed_at"] = self.executed_at
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Action":
        if not isinstance(data, dict):
            raise ValueError(f"Action.from_dict: expected dict, got {type(data).__name__}")
        corr = data.get("correlation", {})
        return cls(
            action_id=data.get("action_id", ""),
            correlation=CorrelationContext.from_dict(corr) if isinstance(corr, dict) else corr,  # type: ignore
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            actor=data.get("actor", ""),
            owning_role_id=data.get("owning_role_id", ""),
            capability=data.get("capability", ""),
            payload=data.get("payload", {}),
            requires_approval=bool(data.get("requires_approval", False)),
            status=data.get("status", ""),
            created_at=data.get("created_at", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            approval=Approval.from_dict(data["approval"]) if isinstance(data.get("approval"), dict) else None,
            executed_at=data.get("executed_at"),
            evidence_refs=[EvidenceRef.from_dict(e) for e in data.get("evidence_refs", []) if isinstance(e, dict)],
            idempotency_key=data.get("idempotency_key"),
        )


# ── Recommendation ─────────────────────────────────────────────────────────

@dataclass
class Recommendation:
    recommendation_id: str
    correlation: CorrelationContext
    owning_role_id: str
    capability: str
    confidence: float
    rationale: str
    requires_approval: bool
    created_at: str
    schema_version: str = SCHEMA_VERSION
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    proposed_action: Optional[Action] = None
    evidence_refs: List[EvidenceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recommendation_id = _require_non_empty_str(self.recommendation_id, "Recommendation.recommendation_id")
        if not isinstance(self.correlation, CorrelationContext):
            raise ValueError(f"Recommendation.correlation: must be CorrelationContext, got {type(self.correlation).__name__}")
        self.owning_role_id = _require_non_empty_str(self.owning_role_id, "Recommendation.owning_role_id")
        self.capability = _require_non_empty_str(self.capability, "Recommendation.capability")
        self.confidence = _validate_confidence(self.confidence, "Recommendation.confidence")
        self.rationale = _require_non_empty_str(self.rationale, "Recommendation.rationale")
        if not isinstance(self.requires_approval, bool):
            raise ValueError(f"Recommendation.requires_approval: must be bool, got {type(self.requires_approval).__name__}")
        self.created_at = _validate_iso_timestamp(self.created_at, "Recommendation.created_at")
        self.schema_version = _validate_schema_version(self.schema_version, "Recommendation.schema_version")
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "Recommendation.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "Recommendation.client_id")
        if self.proposed_action is not None and not isinstance(self.proposed_action, Action):
            raise ValueError(f"Recommendation.proposed_action: must be Action or null, got {type(self.proposed_action).__name__}")
        if not isinstance(self.evidence_refs, list):
            raise ValueError(f"Recommendation.evidence_refs: must be list, got {type(self.evidence_refs).__name__}")
        for i, ev in enumerate(self.evidence_refs):
            if not isinstance(ev, EvidenceRef):
                raise ValueError(f"Recommendation.evidence_refs[{i}]: must be EvidenceRef, got {type(ev).__name__}")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "recommendation_id": self.recommendation_id,
            "correlation": self.correlation.to_dict(),
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "requires_approval": self.requires_approval,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.proposed_action is not None:
            d["proposed_action"] = self.proposed_action.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Recommendation":
        if not isinstance(data, dict):
            raise ValueError(f"Recommendation.from_dict: expected dict, got {type(data).__name__}")
        corr = data.get("correlation", {})
        return cls(
            recommendation_id=data.get("recommendation_id", ""),
            correlation=CorrelationContext.from_dict(corr) if isinstance(corr, dict) else corr,  # type: ignore
            owning_role_id=data.get("owning_role_id", ""),
            capability=data.get("capability", ""),
            confidence=data.get("confidence", 0),
            rationale=data.get("rationale", ""),
            requires_approval=bool(data.get("requires_approval", False)),
            created_at=data.get("created_at", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            proposed_action=Action.from_dict(data["proposed_action"]) if isinstance(data.get("proposed_action"), dict) else None,
            evidence_refs=[EvidenceRef.from_dict(e) for e in data.get("evidence_refs", []) if isinstance(e, dict)],
        )


# ── TaskRequest ────────────────────────────────────────────────────────────

ALLOWED_TASK_REQUEST_STATUSES = {"proposed", "validated", "awaiting_approval", "executing"}


@dataclass
class TaskRequest:
    """
    Canonical request for agent work. One source of truth per Codex principle.
    """
    request_id: str
    correlation: CorrelationContext
    requesting_actor: str
    owning_role_id: str
    capability: str
    input_payload: Dict[str, Any]
    requires_approval: bool
    status: str
    created_at: str
    schema_version: str = SCHEMA_VERSION
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    approval_limit_tier: Optional[str] = None
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    idempotency_key: Optional[str] = None
    timeout_seconds: Optional[int] = None

    def __post_init__(self) -> None:
        self.request_id = _require_non_empty_str(self.request_id, "TaskRequest.request_id")
        if not isinstance(self.correlation, CorrelationContext):
            raise ValueError(f"TaskRequest.correlation: must be CorrelationContext, got {type(self.correlation).__name__}")
        self.requesting_actor = _require_non_empty_str(self.requesting_actor, "TaskRequest.requesting_actor")
        self.owning_role_id = _require_non_empty_str(self.owning_role_id, "TaskRequest.owning_role_id")
        self.capability = _require_non_empty_str(self.capability, "TaskRequest.capability")
        self.input_payload = _require_dict(self.input_payload, "TaskRequest.input_payload")
        if not isinstance(self.requires_approval, bool):
            raise ValueError(f"TaskRequest.requires_approval: must be bool, got {type(self.requires_approval).__name__}")
        self.status = _require_non_empty_str(self.status, "TaskRequest.status").lower()
        if self.status not in ALLOWED_TASK_REQUEST_STATUSES:
            raise ValueError(
                f"TaskRequest.status: must be one of {sorted(ALLOWED_TASK_REQUEST_STATUSES)}, got {self.status!r}"
            )
        self.created_at = _validate_iso_timestamp(self.created_at, "TaskRequest.created_at")
        self.schema_version = _validate_schema_version(self.schema_version, "TaskRequest.schema_version")
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "TaskRequest.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "TaskRequest.client_id")
        if not self.tenant_id and not self.client_id and not self.correlation.tenant_id and not self.correlation.client_id:
            raise ValueError("TaskRequest: at least one of tenant_id/client_id (or correlation tenant/client) must be present")
        if self.approval_limit_tier is not None:
            self.approval_limit_tier = _require_non_empty_str(self.approval_limit_tier, "TaskRequest.approval_limit_tier")
        if not isinstance(self.evidence_refs, list):
            raise ValueError(f"TaskRequest.evidence_refs: must be list, got {type(self.evidence_refs).__name__}")
        for i, ev in enumerate(self.evidence_refs):
            if not isinstance(ev, EvidenceRef):
                raise ValueError(f"TaskRequest.evidence_refs[{i}]: must be EvidenceRef, got {type(ev).__name__}")
        if self.idempotency_key is not None:
            self.idempotency_key = _require_non_empty_str(self.idempotency_key, "TaskRequest.idempotency_key")
        else:
            self.idempotency_key = self.correlation.idempotency_key
        if self.timeout_seconds is not None:
            if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
                raise ValueError(f"TaskRequest.timeout_seconds: must be positive int, got {self.timeout_seconds!r}")
        # correlation/idempotency consistency
        if self.idempotency_key != self.correlation.idempotency_key:
            # Allow explicit override but log via validation; for C1 require equality to avoid divergence
            raise ValueError(
                f"TaskRequest.idempotency_key {self.idempotency_key!r} must match correlation.idempotency_key {self.correlation.idempotency_key!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "request_id": self.request_id,
            "correlation": self.correlation.to_dict(),
            "requesting_actor": self.requesting_actor,
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "input_payload": self.input_payload,
            "requires_approval": self.requires_approval,
            "status": self.status,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "idempotency_key": self.idempotency_key,
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.approval_limit_tier is not None:
            d["approval_limit_tier"] = self.approval_limit_tier
        if self.timeout_seconds is not None:
            d["timeout_seconds"] = self.timeout_seconds
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRequest":
        if not isinstance(data, dict):
            raise ValueError(f"TaskRequest.from_dict: expected dict, got {type(data).__name__}")
        corr = data.get("correlation", {})
        return cls(
            request_id=data.get("request_id", ""),
            correlation=CorrelationContext.from_dict(corr) if isinstance(corr, dict) else corr,  # type: ignore
            requesting_actor=data.get("requesting_actor", ""),
            owning_role_id=data.get("owning_role_id", ""),
            capability=data.get("capability", ""),
            input_payload=data.get("input_payload", {}),
            requires_approval=bool(data.get("requires_approval", False)),
            status=data.get("status", ""),
            created_at=data.get("created_at", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            approval_limit_tier=data.get("approval_limit_tier"),
            evidence_refs=[EvidenceRef.from_dict(e) for e in data.get("evidence_refs", []) if isinstance(e, dict)],
            idempotency_key=data.get("idempotency_key"),
            timeout_seconds=data.get("timeout_seconds"),
        )


# ── TaskResult ─────────────────────────────────────────────────────────────

ALLOWED_TASK_RESULT_STATUSES = {
    "succeeded",
    "failed",
    "refused",
    "timed_out",
    "pending_approval",
    "awaiting_approval",
    "compensated",
    "closed",
}


@dataclass
class TaskResult:
    result_id: str
    request_id: str
    correlation: CorrelationContext
    owning_role_id: str
    capability: str
    status: str
    created_at: str
    schema_version: str = SCHEMA_VERSION
    output_payload: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    error: Optional[AgentError] = None
    recommendation: Optional[Recommendation] = None
    action: Optional[Action] = None
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        self.result_id = _require_non_empty_str(self.result_id, "TaskResult.result_id")
        self.request_id = _require_non_empty_str(self.request_id, "TaskResult.request_id")
        if not isinstance(self.correlation, CorrelationContext):
            raise ValueError(f"TaskResult.correlation: must be CorrelationContext, got {type(self.correlation).__name__}")
        self.owning_role_id = _require_non_empty_str(self.owning_role_id, "TaskResult.owning_role_id")
        self.capability = _require_non_empty_str(self.capability, "TaskResult.capability")
        self.status = _require_non_empty_str(self.status, "TaskResult.status").lower()
        if self.status not in ALLOWED_TASK_RESULT_STATUSES:
            raise ValueError(
                f"TaskResult.status: must be one of {sorted(ALLOWED_TASK_RESULT_STATUSES)}, got {self.status!r}"
            )
        self.created_at = _validate_iso_timestamp(self.created_at, "TaskResult.created_at")
        self.schema_version = _validate_schema_version(self.schema_version, "TaskResult.schema_version")
        if self.output_payload is not None:
            self.output_payload = _require_dict(self.output_payload, "TaskResult.output_payload")
        if self.confidence is not None:
            self.confidence = _validate_confidence(self.confidence, "TaskResult.confidence")
        if not isinstance(self.evidence_refs, list):
            raise ValueError(f"TaskResult.evidence_refs: must be list, got {type(self.evidence_refs).__name__}")
        for i, ev in enumerate(self.evidence_refs):
            if not isinstance(ev, EvidenceRef):
                raise ValueError(f"TaskResult.evidence_refs[{i}]: must be EvidenceRef, got {type(ev).__name__}")
        if self.error is not None and not isinstance(self.error, AgentError):
            raise ValueError(f"TaskResult.error: must be AgentError or null, got {type(self.error).__name__}")
        if self.recommendation is not None and not isinstance(self.recommendation, Recommendation):
            raise ValueError(f"TaskResult.recommendation: must be Recommendation or null, got {type(self.recommendation).__name__}")
        if self.action is not None and not isinstance(self.action, Action):
            raise ValueError(f"TaskResult.action: must be Action or null, got {type(self.action).__name__}")
        if self.completed_at is not None:
            self.completed_at = _validate_iso_timestamp(self.completed_at, "TaskResult.completed_at")

        # status consistency
        if self.status == "refused" and self.error is None:
            raise ValueError("TaskResult: status 'refused' requires error with code 'refused' or 'policy_denied'")
        if self.status == "timed_out" and (self.error is None or self.error.code != "timeout"):
            raise ValueError("TaskResult: status 'timed_out' requires error.code == 'timeout'")
        if self.status == "failed" and self.error is None:
            raise ValueError("TaskResult: status 'failed' requires error")
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("TaskResult: status 'succeeded' cannot have error")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "result_id": self.result_id,
            "request_id": self.request_id,
            "correlation": self.correlation.to_dict(),
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "status": self.status,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
        }
        if self.output_payload is not None:
            d["output_payload"] = self.output_payload
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.error is not None:
            d["error"] = self.error.to_dict()
        if self.recommendation is not None:
            d["recommendation"] = self.recommendation.to_dict()
        if self.action is not None:
            d["action"] = self.action.to_dict()
        if self.completed_at is not None:
            d["completed_at"] = self.completed_at
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        if not isinstance(data, dict):
            raise ValueError(f"TaskResult.from_dict: expected dict, got {type(data).__name__}")
        corr = data.get("correlation", {})
        return cls(
            result_id=data.get("result_id", ""),
            request_id=data.get("request_id", ""),
            correlation=CorrelationContext.from_dict(corr) if isinstance(corr, dict) else corr,  # type: ignore
            owning_role_id=data.get("owning_role_id", ""),
            capability=data.get("capability", ""),
            status=data.get("status", ""),
            created_at=data.get("created_at", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            output_payload=data.get("output_payload"),
            confidence=data.get("confidence"),
            evidence_refs=[EvidenceRef.from_dict(e) for e in data.get("evidence_refs", []) if isinstance(e, dict)],
            error=AgentError.from_dict(data["error"]) if isinstance(data.get("error"), dict) else None,
            recommendation=Recommendation.from_dict(data["recommendation"]) if isinstance(data.get("recommendation"), dict) else None,
            action=Action.from_dict(data["action"]) if isinstance(data.get("action"), dict) else None,
            completed_at=data.get("completed_at"),
        )
