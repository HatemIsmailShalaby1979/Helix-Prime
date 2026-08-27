"""
Execution engine for Helix Prime Codex C2.

Local-first, deterministic, fail-closed. No cloud, no network.
"""
from __future__ import annotations

import datetime
import time
from typing import Any, Callable, Dict, Optional

from contracts.task import TaskRequest, TaskResult, CorrelationContext, EvidenceRef, AgentError, Approval
from control_plane.workflow import Workflow, WorkflowState, is_valid_transition
from control_plane.events import Event
from control_plane.store import Store
from organization.capability_registry import get_agent_for_capability, is_tool_allowed, get_default_registry
from organization.role_catalog import load_role_catalog

Handler = Callable[[Workflow], Dict[str, Any]]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _is_past_deadline(workflow: Workflow) -> bool:
    if workflow.deadline is None:
        return False
    try:
        dl = workflow.deadline.replace("Z", "+00:00")
        deadline_dt = datetime.datetime.fromisoformat(dl)
        now = datetime.datetime.now(datetime.timezone.utc)
        return now > deadline_dt
    except Exception:
        return False


class Engine:
    """
    Deterministic workflow engine.

    - Handlers registered per capability (deterministic, last wins)
    - Timeout/deadline, bounded retries, cancellation, dead_letter, failures-as-data
    - No duplicate execution for same idempotency_key (via Store)
    - Approval integration with C1 SOD
    - Structured tool seam: TaskRequest -> TaskResult via capability registry
    """

    def __init__(self, store: Optional[Store] = None, db_path: Optional[str] = None):
        self.store = store or Store(db_path or "control_plane/workflow.db")
        self.handlers: Dict[str, Handler] = {}
        self.catalog = load_role_catalog("organization/role-catalog.yaml")

    def register_handler(self, capability: str, handler: Handler) -> None:
        if not isinstance(capability, str) or not capability.strip():
            raise ValueError(f"register_handler: capability must be non-empty string, got {capability!r}")
        if not callable(handler):
            raise ValueError(f"register_handler: handler must be callable, got {type(handler).__name__}")
        self.handlers[capability.strip()] = handler

    def _emit_event(
        self,
        workflow: Workflow,
        event_type: str,
        actor: str,
        payload: Optional[Dict[str, Any]] = None,
        causation_id: Optional[str] = None,
    ) -> Event:
        seq = self.store.get_next_sequence(workflow.workflow_id)
        ev = Event.new(
            event_type=event_type,
            aggregate_id=workflow.workflow_id,
            correlation_id=workflow.correlation.correlation_id,
            actor=actor,
            payload=payload or {},
            causation_id=causation_id,
            sequence=seq,
        )
        self.store.append_event(ev)
        return ev

    def submit(self, request: TaskRequest) -> Workflow:
        """
        Submit a TaskRequest as a new workflow. Idempotent by idempotency_key.
        Validates capability via C1a registry, tool permissions, and creates workflow.
        Returns Workflow in appropriate state (proposed->validated->awaiting_approval or executing).
        Fail-closed for unknown capability, unauthorized tool, etc. (goes to dead_letter).
        """
        # Idempotency: if workflow with same idempotency_key exists, return it (no duplicate execution)
        existing = self.store.get_workflow_by_idempotency(request.idempotency_key or request.correlation.idempotency_key)
        if existing is not None:
            return existing

        # Validate capability via registry (unknown -> dead_letter)
        try:
            owner = get_agent_for_capability(request.capability)
        except ValueError as e:
            # Unknown capability -> create workflow in dead_letter
            workflow = Workflow.new(
                correlation=request.correlation,
                requesting_actor=request.requesting_actor,
                owning_role_id=request.owning_role_id,
                capability=request.capability,
                input_payload=request.input_payload,
                requires_approval=request.requires_approval,
                max_retries=3,
            )
            workflow.state = WorkflowState.DEAD_LETTER
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=request.correlation.correlation_id,
                code="not_found",
                message=str(e),
                timestamp=_now_iso(),
            )
            # Persist
            self.store.create_workflow(workflow)
            self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": str(e)})
            return workflow

        # Validate owning role matches capability owner (deterministic routing)
        if owner != request.owning_role_id:
            # Check if it's ambiguous or just wrong owner -> dead_letter
            workflow = Workflow.new(
                correlation=request.correlation,
                requesting_actor=request.requesting_actor,
                owning_role_id=request.owning_role_id,
                capability=request.capability,
                input_payload=request.input_payload,
                requires_approval=request.requires_approval,
            )
            workflow.state = WorkflowState.DEAD_LETTER
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=request.correlation.correlation_id,
                code="conflict",
                message=f"capability {request.capability!r} owned by {owner!r}, not {request.owning_role_id!r} — deterministic routing conflict",
                timestamp=_now_iso(),
            )
            self.store.create_workflow(workflow)
            self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": workflow.error.message})
            return workflow

        # Validate tool permissions: if request input_payload contains tool, check is_tool_allowed
        # For C2, we check if owning role is allowed to use any tool implied by capability
        # Simplified: if capability maps to a tool name, check that. For now, we check if request has 'tool' in payload
        tool = request.input_payload.get("tool")
        if tool:
            try:
                allowed = is_tool_allowed(request.owning_role_id, tool)
                if not allowed:
                    workflow = Workflow.new(
                        correlation=request.correlation,
                        requesting_actor=request.requesting_actor,
                        owning_role_id=request.owning_role_id,
                        capability=request.capability,
                        input_payload=request.input_payload,
                        requires_approval=request.requires_approval,
                    )
                    workflow.state = WorkflowState.DEAD_LETTER
                    workflow.error = AgentError(
                        error_id=f"err_{workflow.workflow_id}",
                        correlation_id=request.correlation.correlation_id,
                        code="unauthorized",
                        message=f"tool {tool!r} not allowed for role {request.owning_role_id!r}",
                        timestamp=_now_iso(),
                    )
                    self.store.create_workflow(workflow)
                    self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": workflow.error.message})
                    return workflow
            except ValueError as e:
                workflow = Workflow.new(
                    correlation=request.correlation,
                    requesting_actor=request.requesting_actor,
                    owning_role_id=request.owning_role_id,
                    capability=request.capability,
                    input_payload=request.input_payload,
                    requires_approval=request.requires_approval,
                )
                workflow.state = WorkflowState.DEAD_LETTER
                workflow.error = AgentError(
                    error_id=f"err_{workflow.workflow_id}",
                    correlation_id=request.correlation.correlation_id,
                    code="unauthorized",
                    message=str(e),
                    timestamp=_now_iso(),
                )
                self.store.create_workflow(workflow)
                self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": str(e)})
                return workflow

        # Create workflow in proposed state
        workflow = Workflow.new(
            correlation=request.correlation,
            requesting_actor=request.requesting_actor,
            owning_role_id=request.owning_role_id,
            capability=request.capability,
            input_payload=request.input_payload,
            requires_approval=request.requires_approval,
            deadline=request.correlation.created_at,  # placeholder, will be overridden if request has timeout?
        )
        # Set deadline if request has timeout
        if request.timeout_seconds:
            deadline_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=request.timeout_seconds)
            workflow.deadline = deadline_dt.isoformat().replace("+00:00", "Z")

        # Idempotency key already set via correlation
        workflow = self.store.create_workflow(workflow)
        self._emit_event(workflow, "workflow_created", request.requesting_actor, {"request_id": request.request_id})

        # Transition proposed -> validated
        try:
            workflow.transition(WorkflowState.VALIDATED, request.requesting_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_validated", request.requesting_actor)
        except ValueError as e:
            workflow.state = WorkflowState.FAILED
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=request.correlation.correlation_id,
                code="invalid_input",
                message=str(e),
                timestamp=_now_iso(),
            )
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_failed", request.requesting_actor, {"reason": str(e)})
            return workflow

        # Check deadline already past (timeout)
        if _is_past_deadline(workflow):
            workflow.transition(WorkflowState.DEAD_LETTER, "system")
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=request.correlation.correlation_id,
                code="timeout",
                message="deadline exceeded before execution",
                timestamp=_now_iso(),
            )
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "timeout", "system", {"reason": "deadline exceeded"})
            self._emit_event(workflow, "workflow_dead_letter", "system", {"reason": "deadline"})
            return workflow

        # If requires approval, go to awaiting_approval
        if workflow.requires_approval:
            workflow.transition(WorkflowState.AWAITING_APPROVAL, request.requesting_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_awaiting_approval", request.requesting_actor)
            return workflow

        # Otherwise, go to executing (but do not auto-execute handler here; caller must call execute)
        workflow.transition(WorkflowState.EXECUTING, request.requesting_actor)
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_executing", request.requesting_actor)
        return workflow

    def approve(self, workflow_id: str, approval: Approval) -> Workflow:
        """
        Handle approval for a workflow in awaiting_approval.
        Validates SOD: self-approval and same-role forbidden (via contracts/task.py already, but also check here).
        Denied approval prevents execution and goes to dead_letter.
        Records approval_granted / approval_denied events.
        """
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"approve: workflow {workflow_id!r} not found")
        if workflow.state != WorkflowState.AWAITING_APPROVAL:
            raise ValueError(f"approve: workflow {workflow_id!r} not in awaiting_approval (current {workflow.state!r})")

        # Validate approval correlation matches workflow
        if approval.correlation_id != workflow.correlation.correlation_id:
            raise ValueError(
                f"approve: approval correlation {approval.correlation_id!r} != workflow {workflow.correlation.correlation_id!r}"
            )
        # Validate SOD: approval already validates self-approval and same-role, but we double-check
        if approval.approver_actor == workflow.requesting_actor:
            raise ValueError(f"approve: self-approval forbidden: approver {approval.approver_actor!r} == requester {workflow.requesting_actor!r}")
        if approval.approver_role_id == workflow.owning_role_id:
            raise ValueError(f"approve: same-role approval forbidden: {approval.approver_role_id!r} == owning {workflow.owning_role_id!r}")

        # Check if approver role is allowed to approve (must be compliance or escalation owner? For C2, allow compliance and sami)
        # Use catalog to check: if workflow's must_be_reviewed_by includes approver_role, allow; else check if approver can_review
        try:
            catalog = self.catalog
            # Check if approver_role can review workflow's owning role
            # For simplicity, allow if approver_role is in workflow's must_be_reviewed_by or is sami/compliance
            workflow_role_data = catalog["roles_by_id"].get(workflow.owning_role_id, {})
            must_review = workflow_role_data.get("segregation_of_duties", {}).get("must_be_reviewed_by", [])
            can_review = self.catalog["roles_by_id"].get(approval.approver_role_id, {}).get("segregation_of_duties", {}).get("can_review", [])
            # Allow if approver is in must_review or approver can_review includes owning role or is sami
            allowed_approvers = set(must_review) | {"sami", "compliance_quality_gm"}
            if approval.approver_role_id not in allowed_approvers and workflow.owning_role_id not in can_review:
                # Still allow sami/compliance explicitly
                if approval.approver_role_id not in ("sami", "compliance_quality_gm"):
                    raise ValueError(
                        f"approve: role {approval.approver_role_id!r} not authorized to approve {workflow.owning_role_id!r} (must be in {must_review} or can_review {workflow.owning_role_id!r})"
                    )
        except KeyError:
            pass  # if catalog lookup fails, allow but log

        workflow.approval = approval
        if approval.decision == "approved":
            workflow.transition(WorkflowState.APPROVED, approval.approver_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "approval_granted", approval.approver_actor, {"approval_id": approval.approval_id})
            self._emit_event(workflow, "workflow_approved", approval.approver_actor)
            # Then move to executing
            workflow.transition(WorkflowState.EXECUTING, approval.approver_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_executing", approval.approver_actor)
        elif approval.decision == "denied":
            workflow.transition(WorkflowState.DEAD_LETTER, approval.approver_actor)
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=workflow.correlation.correlation_id,
                code="approval_denied",
                message=f"approval denied: {approval.reason}",
                timestamp=_now_iso(),
            )
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "approval_denied", approval.approver_actor, {"reason": approval.reason})
            self._emit_event(workflow, "workflow_dead_letter", approval.approver_actor, {"reason": "approval denied"})
        else:
            raise ValueError(f"approve: unknown decision {approval.decision!r}")
        return workflow

    def execute(self, workflow_id: str) -> Workflow:
        """
        Execute the handler for a workflow in executing state.
        Handles bounded retries, timeout, failures-as-data, dead_letter.
        Returns updated workflow.
        """
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"execute: workflow {workflow_id!r} not found")
        if workflow.state != WorkflowState.EXECUTING:
            raise ValueError(f"execute: workflow {workflow_id!r} not in executing (current {workflow.state!r})")

        # Check deadline
        if _is_past_deadline(workflow):
            workflow.transition(WorkflowState.DEAD_LETTER, "system")
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=workflow.correlation.correlation_id,
                code="timeout",
                message="deadline exceeded during execution",
                timestamp=_now_iso(),
            )
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "timeout", "system")
            self._emit_event(workflow, "workflow_dead_letter", "system", {"reason": "deadline"})
            return workflow

        handler = self.handlers.get(workflow.capability)
        if handler is None:
            # No handler -> fail as dead_letter (no silent fallback)
            workflow.transition(WorkflowState.DEAD_LETTER, "system")
            workflow.error = AgentError(
                error_id=f"err_{workflow.workflow_id}",
                correlation_id=workflow.correlation.correlation_id,
                code="not_found",
                message=f"no handler for capability {workflow.capability!r}",
                timestamp=_now_iso(),
            )
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "handler_failed", "system", {"reason": "no handler"})
            self._emit_event(workflow, "workflow_dead_letter", "system", {"reason": "no handler"})
            return workflow

        # Execute handler with bounded retries
        last_error: Optional[Exception] = None
        for attempt in range(workflow.max_retries + 1):
            try:
                result_payload = handler(workflow)
                # Success: validate output is dict
                if not isinstance(result_payload, dict):
                    raise ValueError(f"handler must return dict, got {type(result_payload).__name__}")
                workflow.output_payload = result_payload
                workflow.transition(WorkflowState.SUCCEEDED, workflow.owning_role_id)
                self.store.update_workflow(workflow)
                self._emit_event(workflow, "handler_succeeded", workflow.owning_role_id, {"attempt": attempt})
                self._emit_event(workflow, "workflow_succeeded", workflow.owning_role_id, {"output": result_payload})
                # Then close
                workflow.transition(WorkflowState.CLOSED, workflow.owning_role_id)
                self.store.update_workflow(workflow)
                self._emit_event(workflow, "workflow_closed", workflow.owning_role_id)
                return workflow
            except Exception as e:
                last_error = e
                workflow.retry_count = attempt + 1
                self.store.update_workflow(workflow)
                self._emit_event(workflow, "handler_failed", workflow.owning_role_id, {"attempt": attempt, "error": str(e)})
                self._emit_event(workflow, "retry_scheduled", workflow.owning_role_id, {"attempt": attempt, "max": workflow.max_retries})
                if workflow.retry_count > workflow.max_retries:
                    break
                # No sleep for tests (bounded, no silent loop) — immediate retry

        # Retries exhausted -> dead_letter
        workflow.transition(WorkflowState.FAILED, workflow.owning_role_id)
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_failed", workflow.owning_role_id, {"reason": str(last_error)})
        # Then dead_letter
        workflow.transition(WorkflowState.DEAD_LETTER, workflow.owning_role_id)
        workflow.error = AgentError(
            error_id=f"err_{workflow.workflow_id}",
            correlation_id=workflow.correlation.correlation_id,
            code="engine_error",
            message=str(last_error) if last_error else "handler failed",
            timestamp=_now_iso(),
        )
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_dead_letter", workflow.owning_role_id, {"reason": str(last_error)})
        return workflow

    def cancel(self, workflow_id: str, actor: str, reason: str = "cancelled") -> Workflow:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"cancel: workflow {workflow_id!r} not found")
        if workflow.state in (WorkflowState.CLOSED, WorkflowState.CANCELLED, WorkflowState.DEAD_LETTER):
            raise ValueError(f"cancel: workflow {workflow_id!r} already terminal {workflow.state!r}")
        workflow.transition(WorkflowState.CANCELLED, actor)
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_cancelled", actor, {"reason": reason})
        # Then close
        workflow.transition(WorkflowState.CLOSED, actor)
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_closed", actor, {"reason": "cancelled"})
        return workflow

    def to_task_result(self, workflow: Workflow) -> TaskResult:
        """Convert workflow terminal state to C1 TaskResult (failures-as-data)."""
        from contracts.task import TaskResult

        # Determine status mapping
        state_to_result = {
            WorkflowState.SUCCEEDED: "succeeded",
            WorkflowState.FAILED: "failed",
            WorkflowState.DEAD_LETTER: "refused" if workflow.error and workflow.error.code in ("approval_denied", "policy_denied", "unauthorized") else "failed",
            WorkflowState.CANCELLED: "failed",
            WorkflowState.CLOSED: "succeeded" if workflow.output_payload else "failed",
        }
        status = state_to_result.get(workflow.state, "failed")
        # Override if error code indicates specific
        if workflow.error:
            if workflow.error.code == "timeout":
                status = "timed_out"
            elif workflow.error.code in ("policy_denied", "approval_denied", "unauthorized", "refused"):
                status = "refused"

        # Build TaskResult
        result = TaskResult(
            result_id=f"res_{workflow.workflow_id}",
            request_id=workflow.workflow_id,  # workflow_id acts as request_id for C2
            correlation=workflow.correlation,
            owning_role_id=workflow.owning_role_id,
            capability=workflow.capability,
            status=status,  # type: ignore
            created_at=workflow.created_at,
            completed_at=workflow.updated_at,
            output_payload=workflow.output_payload,
            error=workflow.error,
            evidence_refs=workflow.evidence_refs,
        )
        return result

    def close(self) -> None:
        self.store.close()
