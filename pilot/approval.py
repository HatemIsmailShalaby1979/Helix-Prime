"""Manual approval records in governed memory (Prompt 10).

Every committal action produces a `recommendation` record (with evidence) and an
`approval` record in `draft` state. Approving/denying/rolling-back appends a new
versioned `approval` record (never mutates the original ledger line), enforcing
separation of duties and a full audit trail.
"""
from __future__ import annotations

from typing import Optional

from memory.governed_memory import GovernedMemory


def create_recommendation(
    mem: GovernedMemory, *, tenant_id, client_id, actor, role_id, correlation_id,
    timestamp, action, evidence, diagnosis_ref, correct, data_mode,
    classification: str = "client_confidential",
):
    return mem.add(
        kind="recommendation", nature="model_inference", tenant_id=tenant_id, client_id=client_id,
        actor=actor, role_id=role_id, source="pilot_recommendation", classification=classification,
        timestamp=timestamp, correlation_id=correlation_id, confidence=0.7,
        evidence_refs=list(evidence), data_mode=data_mode,
        provenance={"correlation_id": correlation_id, "data_mode": data_mode,
                    "basis": "pilot_recommendation", "sources": list(evidence)},
        body={"action": action, "diagnosis_ref": diagnosis_ref, "correct": bool(correct)},
    )


def create_approval_draft(
    mem: GovernedMemory, *, tenant_id, client_id, owner, role_id, correlation_id,
    timestamp, action, recommendation_id, evidence, data_mode,
):
    return mem.add(
        kind="approval", nature="user_claim", tenant_id=tenant_id, client_id=client_id,
        actor=owner, role_id=role_id, source="pilot_approval", classification="client_confidential",
        timestamp=timestamp, correlation_id=correlation_id, confidence=1.0,
        evidence_refs=list(evidence), data_mode=data_mode,
        provenance={"correlation_id": correlation_id, "data_mode": data_mode,
                    "basis": "approval_request", "sources": [recommendation_id]},
        body={"action": action, "recommendation_id": recommendation_id,
              "approval_state": "draft", "owner": owner, "owner_role": role_id},
    )


def transition_approval(
    mem: GovernedMemory, prev, new_state: str, actor, role_id, correlation_id, timestamp, reason: str = "",
):
    return mem.add(
        kind="approval", nature="user_claim", tenant_id=prev.tenant_id, client_id=prev.client_id,
        actor=actor, role_id=role_id, source="pilot_approval_transition", classification="client_confidential",
        timestamp=timestamp, correlation_id=correlation_id, confidence=1.0,
        evidence_refs=list(prev.evidence_refs), data_mode=prev.data_mode,
        provenance={"correlation_id": correlation_id, "data_mode": prev.data_mode,
                    "basis": "approval_transition", "sources": [prev.record_id]},
        body={**prev.body, "approval_state": new_state, "transition_reason": reason,
              "transition_by": actor},
        supersedes=prev.record_id,
    )


def evaluate_approval_decision(prev, decision: str, approver_actor, approver_role,
                              requester_actor, requester_role) -> tuple[bool, str]:
    """Separation of duties for the manual approval process."""
    if decision == "denied":
        return True, "denied"
    if approver_actor == requester_actor:
        return False, "self-approval denied (separation of duties)"
    if approver_role == requester_role:
        return False, "same-role approval denied (separation of duties)"
    return True, "allowed"
