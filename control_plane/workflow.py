"""
Workflow/task execution model and typed state machine for Helix Prime Codex C2.

States: proposed, validated, awaiting_approval, approved, executing, succeeded, failed, compensated, cancelled, dead_letter, closed
Invalid transitions fail deterministically (ValueError).
"""
from __future__ import annotations

import dataclasses
import datetime
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from contracts.task import CorrelationContext, EvidenceRef, AgentError, Approval

SCHEMA_VERSION = "1.0"


class WorkflowState:
    PROPOSED = "proposed"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    COMPENSATED = "compensated"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"
    CLOSED = "closed"

    ALL = {
        PROPOSED,
        VALIDATED,
        AWAITING_APPROVAL,
        APPROVED,
        EXECUTING,
        SUCCEEDED,
        FAILED,
        COMPENSATED,
        CANCELLED,
        DEAD_LETTER,
        CLOSED,
    }


# Valid transitions map: from_state -> set of allowed to_states
VALID_TRANSITIONS: Dict[str, set] = {
    WorkflowState.PROPOSED: {
        WorkflowState.VALIDATED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
        WorkflowState.DEAD_LETTER,
    },
    WorkflowState.VALIDATED: {
        WorkflowState.AWAITING_APPROVAL,
        WorkflowState.EXECUTING,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
        WorkflowState.DEAD_LETTER,
    },
    WorkflowState.AWAITING_APPROVAL: {
        WorkflowState.APPROVED,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
        WorkflowState.DEAD_LETTER,
    },
    WorkflowState.APPROVED: {
        WorkflowState.EXECUTING,
        WorkflowState.FAILED,
        WorkflowState.CANCELLED,
        WorkflowState.DEAD_LETTER,
    },
    WorkflowState.EXECUTING: {
        WorkflowState.SUCCEEDED,
        WorkflowState.FAILED,
        WorkflowState.COMPENSATED,
        WorkflowState.CANCELLED,
        WorkflowState.DEAD_LETTER,
    },
    WorkflowState.SUCCEEDED: {WorkflowState.CLOSED},
    WorkflowState.FAILED: {
        WorkflowState.COMPENSATED,
        WorkflowState.DEAD_LETTER,
        WorkflowState.CLOSED,
        WorkflowState.CANCELLED,
    },
    WorkflowState.COMPENSATED: {WorkflowState.CLOSED, WorkflowState.DEAD_LETTER},
    WorkflowState.CANCELLED: {WorkflowState.CLOSED, WorkflowState.DEAD_LETTER},
    WorkflowState.DEAD_LETTER: {WorkflowState.CLOSED, WorkflowState.COMPENSATED},
    WorkflowState.CLOSED: set(),
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    if from_state not in WorkflowState.ALL or to_state not in WorkflowState.ALL:
        return False
    return to_state in VALID_TRANSITIONS.get(from_state, set())


def _require_non_empty_str(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be non-empty string, got {value!r}")
    return value.strip()


def _validate_iso(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    try:
        cand = s.replace("Z", "+00:00") if s.endswith("Z") else s
        datetime.datetime.fromisoformat(cand)
    except Exception as e:
        raise ValueError(f"{field_path}: must be ISO8601, got {s!r}: {e}") from e
    return s


def _validate_schema_version(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if not re.match(r"^\d+\.\d+$", s):
        raise ValueError(f"{field_path}: must be semver '1.0', got {s!r}")
    return s


@dataclass
class Workflow:
    workflow_id: str
    correlation: CorrelationContext
    tenant_id: Optional[str]
    client_id: Optional[str]
    requesting_actor: str
    owning_role_id: str
    capability: str
    state: str
    input_payload: Dict[str, Any]
    created_at: str
    updated_at: str
    schema_version: str = SCHEMA_VERSION
    output_payload: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3
    deadline: Optional[str] = None  # ISO timestamp
    idempotency_key: str = ""
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    error: Optional[AgentError] = None
    approval: Optional[Approval] = None
    requires_approval: bool = False
    task_id: Optional[str] = None

    def __post_init__(self) -> None:
        self.workflow_id = _require_non_empty_str(self.workflow_id, "Workflow.workflow_id")
        if not isinstance(self.correlation, CorrelationContext):
            raise ValueError(f"Workflow.correlation: must be CorrelationContext, got {type(self.correlation).__name__}")
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "Workflow.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "Workflow.client_id")
        if not self.tenant_id and not self.client_id and not self.correlation.tenant_id and not self.correlation.client_id:
            raise ValueError("Workflow: at least one of tenant_id/client_id or correlation tenant/client must be present")
        self.requesting_actor = _require_non_empty_str(self.requesting_actor, "Workflow.requesting_actor")
        self.owning_role_id = _require_non_empty_str(self.owning_role_id, "Workflow.owning_role_id")
        self.capability = _require_non_empty_str(self.capability, "Workflow.capability")
        if self.state not in WorkflowState.ALL:
            raise ValueError(f"Workflow.state: must be one of {sorted(WorkflowState.ALL)}, got {self.state!r}")
        if not isinstance(self.input_payload, dict):
            raise ValueError(f"Workflow.input_payload: must be dict, got {type(self.input_payload).__name__}")
        if self.output_payload is not None and not isinstance(self.output_payload, dict):
            raise ValueError(f"Workflow.output_payload: must be dict or None, got {type(self.output_payload).__name__}")
        self.created_at = _validate_iso(self.created_at, "Workflow.created_at")
        self.updated_at = _validate_iso(self.updated_at, "Workflow.updated_at")
        self.schema_version = _validate_schema_version(self.schema_version, "Workflow.schema_version")
        if not isinstance(self.retry_count, int) or self.retry_count < 0:
            raise ValueError(f"Workflow.retry_count: must be int >=0, got {self.retry_count!r}")
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError(f"Workflow.max_retries: must be int >=0, got {self.max_retries!r}")
        if self.deadline is not None:
            self.deadline = _validate_iso(self.deadline, "Workflow.deadline")
        self.idempotency_key = _require_non_empty_str(self.idempotency_key, "Workflow.idempotency_key")
        if not isinstance(self.evidence_refs, list):
            raise ValueError(f"Workflow.evidence_refs: must be list, got {type(self.evidence_refs).__name__}")
        for i, ev in enumerate(self.evidence_refs):
            if not isinstance(ev, EvidenceRef):
                raise ValueError(f"Workflow.evidence_refs[{i}]: must be EvidenceRef, got {type(ev).__name__}")
        if self.error is not None and not isinstance(self.error, AgentError):
            raise ValueError(f"Workflow.error: must be AgentError or None, got {type(self.error).__name__}")
        if self.approval is not None and not isinstance(self.approval, Approval):
            raise ValueError(f"Workflow.approval: must be Approval or None, got {type(self.approval).__name__}")
        if not isinstance(self.requires_approval, bool):
            raise ValueError(f"Workflow.requires_approval: must be bool, got {type(self.requires_approval).__name__}")
        if self.task_id is not None:
            self.task_id = _require_non_empty_str(self.task_id, "Workflow.task_id")

    def can_transition(self, to_state: str) -> bool:
        return is_valid_transition(self.state, to_state)

    def transition(self, to_state: str, actor: str, timestamp: Optional[str] = None) -> None:
        """Mutate state if valid, else raise ValueError."""
        to_state = _require_non_empty_str(to_state, "transition.to_state").lower()
        if to_state not in WorkflowState.ALL:
            raise ValueError(f"transition: unknown state {to_state!r}")
        if not is_valid_transition(self.state, to_state):
            raise ValueError(f"invalid transition {self.state!r} -> {to_state!r}")
        self.state = to_state
        self.updated_at = _validate_iso(
            timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "Workflow.updated_at",
        )
        # actor is for event, not stored here; caller should create event

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "correlation": self.correlation.to_dict(),
            "requesting_actor": self.requesting_actor,
            "owning_role_id": self.owning_role_id,
            "capability": self.capability,
            "state": self.state,
            "input_payload": self.input_payload,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "idempotency_key": self.idempotency_key,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "requires_approval": self.requires_approval,
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.output_payload is not None:
            d["output_payload"] = self.output_payload
        if self.deadline is not None:
            d["deadline"] = self.deadline
        if self.error is not None:
            d["error"] = self.error.to_dict()
        if self.approval is not None:
            d["approval"] = self.approval.to_dict()
        if self.task_id is not None:
            d["task_id"] = self.task_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Workflow":
        if not isinstance(data, dict):
            raise ValueError(f"Workflow.from_dict: expected dict, got {type(data).__name__}")
        corr = data.get("correlation", {})
        return cls(
            workflow_id=data.get("workflow_id", ""),
            correlation=CorrelationContext.from_dict(corr) if isinstance(corr, dict) else corr,  # type: ignore
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            requesting_actor=data.get("requesting_actor", ""),
            owning_role_id=data.get("owning_role_id", ""),
            capability=data.get("capability", ""),
            state=data.get("state", WorkflowState.PROPOSED),
            input_payload=data.get("input_payload", {}),
            output_payload=data.get("output_payload"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 3)),
            deadline=data.get("deadline"),
            idempotency_key=data.get("idempotency_key", ""),
            evidence_refs=[EvidenceRef.from_dict(e) for e in data.get("evidence_refs", []) if isinstance(e, dict)],
            error=AgentError.from_dict(data["error"]) if isinstance(data.get("error"), dict) else None,
            approval=Approval.from_dict(data["approval"]) if isinstance(data.get("approval"), dict) else None,
            requires_approval=bool(data.get("requires_approval", False)),
            task_id=data.get("task_id"),
        )

    @classmethod
    def new(
        cls,
        correlation: CorrelationContext,
        requesting_actor: str,
        owning_role_id: str,
        capability: str,
        input_payload: Optional[Dict[str, Any]] = None,
        requires_approval: bool = False,
        max_retries: int = 3,
        deadline: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> "Workflow":
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        wid = f"wf_{uuid.uuid4().hex[:12]}"
        tid = f"task_{uuid.uuid4().hex[:12]}"
        return cls(
            workflow_id=wid,
            correlation=correlation,
            tenant_id=tenant_id or correlation.tenant_id,
            client_id=client_id or correlation.client_id,
            requesting_actor=requesting_actor,
            owning_role_id=owning_role_id,
            capability=capability,
            state=WorkflowState.PROPOSED,
            input_payload=input_payload or {},
            created_at=now,
            updated_at=now,
            max_retries=max_retries,
            deadline=deadline,
            idempotency_key=correlation.idempotency_key,
            requires_approval=requires_approval,
            task_id=tid,
        )
