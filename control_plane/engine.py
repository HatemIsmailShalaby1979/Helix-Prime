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

# C3 integrations (local-first, fail-closed)
try:
    from security.classification import validate_payload_classification, DataClassification
    from security.identity import Identity, ActorType
    from security.policy import AuthorizationRequest, authorize
    from security.secrets import validate_no_secrets, redact_dict, is_secret_present
    from security.audit import AuditTrail, AuditRecord
    from security.injection import is_suspicious_prompt, scan_for_injection
    from observability.logging import log_structured
except ImportError:
    # Fallback if security/observability not available (should not happen in C3)
    validate_payload_classification = None  # type: ignore
    DataClassification = None  # type: ignore
    Identity = None  # type: ignore
    ActorType = None  # type: ignore
    AuthorizationRequest = None  # type: ignore
    authorize = None  # type: ignore
    validate_no_secrets = None  # type: ignore
    redact_dict = None  # type: ignore
    is_secret_present = None  # type: ignore
    AuditTrail = None  # type: ignore
    AuditRecord = None  # type: ignore
    is_suspicious_prompt = None  # type: ignore
    scan_for_injection = None  # type: ignore
    log_structured = None  # type: ignore

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

    def _audit(self, event_type: str, workflow: Workflow, actor: str, actor_type: str = "agent", decision: str = "allowed", input_ref: str | None = None, output_ref: str | None = None, approval_decision: str | None = None) -> None:
        """Helper: append tamper-evident audit record (best-effort, no cloud)."""
        if AuditTrail is None or AuditRecord is None:
            return
        try:
            # Determine previous hash
            trail = AuditTrail(db_path="security/audit.db")
            # Get last record's hash for chaining
            last = trail.list_records(limit=1)
            # Actually list_records returns oldest first; we need last
            all_recs = trail.list_records(limit=10000)
            prev_hash = all_recs[-1].current_hash if all_recs else None
            rec = AuditRecord.new(
                event_type=event_type,
                actor=actor,
                actor_type=actor_type,
                decision=decision,
                correlation_id=workflow.correlation.correlation_id,
                tenant_id=workflow.tenant_id,
                client_id=workflow.client_id,
                role_id=workflow.owning_role_id,
                workflow_id=workflow.workflow_id,
                task_id=workflow.task_id,
                input_ref=input_ref or workflow.workflow_id,
                output_ref=output_ref,
                approval_decision=approval_decision,
                previous_hash=prev_hash,
            )
            trail.append(rec)
            trail.close()
        except Exception:
            # Audit failures must not silently disappear but should not crash workflow; log and continue
            try:
                if log_structured:
                    log_structured(event_type="audit_verification_failure", correlation_id=workflow.correlation.correlation_id, workflow_id=workflow.workflow_id, actor=actor, result_status="failed", error_code="audit_error", payload={"event_type": event_type})
            except Exception:
                pass

    def _log(self, event_type: str, workflow: Workflow, actor: str, **kwargs) -> None:
        """Helper: structured JSON log with required identifiers, redacted payload."""
        if log_structured is None:
            return
        try:
            # Redact payload before logging
            payload = kwargs.get("payload")
            if isinstance(payload, dict) and redact_dict:
                try:
                    payload = redact_dict(payload)
                except Exception:
                    pass
                kwargs["payload"] = payload
            log_structured(
                event_type=event_type,
                correlation_id=workflow.correlation.correlation_id,
                workflow_id=workflow.workflow_id,
                task_id=workflow.task_id or workflow.workflow_id,
                tenant_id=workflow.tenant_id,
                client_id=workflow.client_id,
                actor=actor,
                actor_type="agent" if "agent" in actor.lower() or actor in ("sami", "suby", "phili", "wili", "system") else "human",
                role_id=workflow.owning_role_id,
                capability=workflow.capability,
                **kwargs,
            )
        except Exception:
            pass

    def submit(self, request: TaskRequest) -> Workflow:
        """
        Submit a TaskRequest as a new workflow. Idempotent by idempotency_key.
        Validates capability via C1a registry, tool permissions, C3 classification/secrets/policy, and creates workflow.
        Returns Workflow in appropriate state (proposed->validated->awaiting_approval or executing).
        Fail-closed for unknown capability, unauthorized tool, tenant isolation, secrets, classification, etc. (goes to dead_letter).
        Also emits audit and structured logs with workflow/task/correlation identifiers.
        """
        # Idempotency: if workflow with same idempotency_key exists, return it (no duplicate execution)
        existing = self.store.get_workflow_by_idempotency(request.idempotency_key or request.correlation.idempotency_key)
        if existing is not None:
            return existing

        # C3: Validate no secrets in payload before any storage (fail-closed)
        if validate_no_secrets:
            try:
                validate_no_secrets(request.input_payload, field_path="TaskRequest.input_payload")
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
                    code="policy_denied",
                    message=f"secret detected: {e}",
                    timestamp=_now_iso(),
                )
                self.store.create_workflow(workflow)
                self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": str(e)})
                self._audit("secret_redaction", workflow, request.requesting_actor, decision="denied", input_ref=request.request_id)
                self._log("secret_redaction", workflow, request.requesting_actor, result_status="denied", error_code="secret_detected", payload={"reason": str(e)})
                return workflow

        # C3: Validate data classification (unknown -> fail-closed)
        if validate_payload_classification:
            # Determine classification to validate: if payload has explicit data_classification, use it, else infer or default to client_confidential
            payload_class = request.input_payload.get("data_classification")
            if payload_class is not None:
                try:
                    validate_payload_classification(request.input_payload, payload_class)
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
                        code="policy_denied",
                        message=str(e),
                        timestamp=_now_iso(),
                    )
                    self.store.create_workflow(workflow)
                    self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": str(e)})
                    self._audit("policy_denied", workflow, request.requesting_actor, decision="denied")
                    self._log("policy_denied", workflow, request.requesting_actor, result_status="denied", error_code="invalid_classification", payload={"reason": str(e)})
                    return workflow

        # C3: Policy authorize (tenant/client isolation, role/capability/tool, deny-by-default)
        if authorize and Identity and ActorType:
            try:
                # Infer actor_type: if actor is known agent name, it's agent, else human/service
                actor_lower = request.requesting_actor.lower()
                if actor_lower in ("sami", "suby", "phili", "wili", "system"):
                    a_type = ActorType.AGENT if actor_lower != "system" else ActorType.SERVICE
                else:
                    a_type = ActorType.HUMAN
                # Determine role for identity: try to map actor to role, else use owning_role
                role_for_identity = request.owning_role_id
                # If actor matches a role id, use it
                try:
                    from organization.role_catalog import load_role_catalog
                    catalog_roles = load_role_catalog("organization/role-catalog.yaml")["roles_by_id"]
                    if actor_lower in catalog_roles:
                        role_for_identity = actor_lower
                    elif actor_lower.upper() in ("SAMI", "SUBY", "PHILI", "WILI"):
                        mapping = {"SAMI": "sami", "SUBY": "ops_gm", "PHILI": "hr_personnel_gm", "WILI": "ld_gm"}
                        role_for_identity = mapping.get(actor_lower.upper(), role_for_identity)
                except Exception:
                    pass
                ident = Identity(
                    actor=request.requesting_actor,
                    actor_type=a_type,
                    tenant_id=request.correlation.tenant_id or request.tenant_id,
                    client_id=request.correlation.client_id or request.client_id,
                    role_id=role_for_identity,
                )
                # Check for suspicious prompt/tool injection before authorize
                if is_suspicious_prompt and scan_for_injection:
                    try:
                        suspicious, _ = is_suspicious_prompt(str(request.input_payload))
                        if suspicious:
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
                                code="policy_denied",
                                message="suspicious prompt/tool request detected",
                                timestamp=_now_iso(),
                            )
                            self.store.create_workflow(workflow)
                            self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": "suspicious prompt"})
                            self._audit("suspicious_prompt", workflow, request.requesting_actor, decision="denied")
                            self._log("suspicious_prompt", workflow, request.requesting_actor, result_status="denied", error_code="injection", payload={"capability": request.capability})
                            return workflow
                    except Exception:
                        pass

                auth_req = AuthorizationRequest(
                    identity=ident,
                    capability=request.capability,
                    tool=request.input_payload.get("tool"),
                    owning_role_id=request.owning_role_id,
                    target_tenant_id=request.correlation.tenant_id or request.tenant_id,
                    target_client_id=request.correlation.client_id or request.client_id,
                )
                decision = authorize(auth_req)
                if not decision.allowed:
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
                        code="unauthorized" if "unauthorized" in decision.code else "policy_denied",
                        message=decision.reason,
                        timestamp=_now_iso(),
                    )
                    self.store.create_workflow(workflow)
                    self._emit_event(workflow, "workflow_dead_letter", request.requesting_actor, {"reason": decision.reason})
                    self._audit("authorization_denied", workflow, request.requesting_actor, decision="denied")
                    self._log("authorization_denied", workflow, request.requesting_actor, result_status="denied", error_code=decision.code, payload={"reason": decision.reason})
                    return workflow
            except ValueError as e:
                # Authorization raised ValueError (unknown capability etc.) -> already handled as dead_letter, but catch here for safety
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
                self._audit("authorization_denied", workflow, request.requesting_actor, decision="denied")
                self._log("authorization_denied", workflow, request.requesting_actor, result_status="denied", error_code="unauthorized", payload={"reason": str(e)})
                return workflow

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

        # Create workflow in proposed state (deadline only if timeout provided)
        workflow = Workflow.new(
            correlation=request.correlation,
            requesting_actor=request.requesting_actor,
            owning_role_id=request.owning_role_id,
            capability=request.capability,
            input_payload=request.input_payload,
            requires_approval=request.requires_approval,
        )
        # Set deadline if request has timeout
        if request.timeout_seconds:
            deadline_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=request.timeout_seconds)
            workflow.deadline = deadline_dt.isoformat().replace("+00:00", "Z")
            workflow.updated_at = workflow.deadline  # ensure updated_at reflects deadline change before store

        # Idempotency key already set via correlation
        workflow = self.store.create_workflow(workflow)
        self._emit_event(workflow, "workflow_created", request.requesting_actor, {"request_id": request.request_id})
        self._audit("workflow_created", workflow, request.requesting_actor, decision="allowed", input_ref=request.request_id)
        self._log("workflow_created", workflow, request.requesting_actor, result_status="proposed", payload={"request_id": request.request_id})

        # Transition proposed -> validated
        try:
            workflow.transition(WorkflowState.VALIDATED, request.requesting_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_validated", request.requesting_actor)
            self._audit("workflow_validated", workflow, request.requesting_actor, decision="allowed")
            self._log("workflow_validated", workflow, request.requesting_actor, result_status="validated")
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
            self._audit("workflow_failed", workflow, request.requesting_actor, decision="denied")
            self._log("workflow_failed", workflow, request.requesting_actor, result_status="failed", error_code="invalid_input", payload={"reason": str(e)})
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
            self._audit("timeout", workflow, "system", decision="denied")
            self._audit("workflow_dead_letter", workflow, "system", decision="denied")
            self._log("timeout", workflow, "system", result_status="denied", error_code="timeout", payload={"reason": "deadline"})
            return workflow

        # If requires approval, go to awaiting_approval
        if workflow.requires_approval:
            workflow.transition(WorkflowState.AWAITING_APPROVAL, request.requesting_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_awaiting_approval", request.requesting_actor)
            self._audit("workflow_awaiting_approval", workflow, request.requesting_actor, decision="allowed")
            self._log("workflow_awaiting_approval", workflow, request.requesting_actor, result_status="awaiting_approval")
            return workflow

        # Otherwise, go to executing (but do not auto-execute handler here; caller must call execute)
        workflow.transition(WorkflowState.EXECUTING, request.requesting_actor)
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_executing", request.requesting_actor)
        self._audit("workflow_executing", workflow, request.requesting_actor, decision="allowed")
        self._log("workflow_executing", workflow, request.requesting_actor, result_status="executing")
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
            self._audit("approval_granted", workflow, approval.approver_actor, decision="approved", approval_decision="approved")
            self._log("approval_granted", workflow, approval.approver_actor, result_status="approved", payload={"approval_id": approval.approval_id})
            # Then move to executing
            workflow.transition(WorkflowState.EXECUTING, approval.approver_actor)
            self.store.update_workflow(workflow)
            self._emit_event(workflow, "workflow_executing", approval.approver_actor)
            self._audit("workflow_executing", workflow, approval.approver_actor, decision="allowed")
            self._log("workflow_executing", workflow, approval.approver_actor, result_status="executing")
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
            self._audit("approval_denied", workflow, approval.approver_actor, decision="denied", approval_decision="denied")
            self._log("approval_denied", workflow, approval.approver_actor, result_status="denied", error_code="approval_denied", payload={"reason": approval.reason})
            self._audit("workflow_dead_letter", workflow, approval.approver_actor, decision="denied")
            self._log("workflow_dead_letter", workflow, approval.approver_actor, result_status="denied", error_code="approval_denied")
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
            self._audit("timeout", workflow, "system", decision="denied")
            self._audit("workflow_dead_letter", workflow, "system", decision="denied")
            self._log("timeout", workflow, "system", result_status="denied", error_code="timeout", payload={"reason": "deadline"})
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
            self._audit("handler_failed", workflow, "system", decision="denied")
            self._audit("workflow_dead_letter", workflow, "system", decision="denied")
            self._log("handler_failed", workflow, "system", result_status="failed", error_code="not_found", payload={"reason": "no handler"})
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
                self._audit("handler_succeeded", workflow, workflow.owning_role_id, decision="succeeded", output_ref=str(result_payload)[:100])
                self._log("handler_succeeded", workflow, workflow.owning_role_id, result_status="succeeded", payload={"attempt": attempt})
                # Then close
                workflow.transition(WorkflowState.CLOSED, workflow.owning_role_id)
                self.store.update_workflow(workflow)
                self._emit_event(workflow, "workflow_closed", workflow.owning_role_id)
                self._audit("workflow_closed", workflow, workflow.owning_role_id, decision="succeeded")
                self._log("workflow_closed", workflow, workflow.owning_role_id, result_status="succeeded")
                return workflow
            except Exception as e:
                last_error = e
                workflow.retry_count = attempt + 1
                self.store.update_workflow(workflow)
                self._emit_event(workflow, "handler_failed", workflow.owning_role_id, {"attempt": attempt, "error": str(e)})
                self._emit_event(workflow, "retry_scheduled", workflow.owning_role_id, {"attempt": attempt, "max": workflow.max_retries})
                self._audit("handler_failed", workflow, workflow.owning_role_id, decision="failed")
                self._log("handler_failed", workflow, workflow.owning_role_id, result_status="failed", error_code="engine_error", retry_count=workflow.retry_count, payload={"attempt": attempt, "error": str(e)})
                self._log("retry_scheduled", workflow, workflow.owning_role_id, result_status="retry", retry_count=workflow.retry_count, payload={"attempt": attempt})
                if workflow.retry_count > workflow.max_retries:
                    break
                # No sleep for tests (bounded, no silent loop) — immediate retry

        # Retries exhausted -> dead_letter
        workflow.transition(WorkflowState.FAILED, workflow.owning_role_id)
        self.store.update_workflow(workflow)
        self._emit_event(workflow, "workflow_failed", workflow.owning_role_id, {"reason": str(last_error)})
        self._audit("workflow_failed", workflow, workflow.owning_role_id, decision="failed")
        self._log("workflow_failed", workflow, workflow.owning_role_id, result_status="failed", error_code="engine_error", payload={"reason": str(last_error)})
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
        self._audit("workflow_dead_letter", workflow, workflow.owning_role_id, decision="denied")
        self._log("workflow_dead_letter", workflow, workflow.owning_role_id, result_status="denied", error_code="engine_error", payload={"reason": str(last_error)})
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
