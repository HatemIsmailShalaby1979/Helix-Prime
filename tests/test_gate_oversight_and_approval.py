"""
Regression tests for the two gate defects recorded in ``docs/KNOWN_ISSUES.md``.

Issue 1 — ``evaluate_gate`` parsed ``oversight_only`` but never enforced it, so an
oversight-only seat (``compliance_quality_gm``) reached ``EXECUTING`` when a task
named no ``target_engine``; ``RoleSpec.owns_engine(None)`` returned ``True`` and let
the no-engine case slip past the ownership boundary.

Issue 2 — ``Engine.submit`` did not forward ``requires_approval`` to the gate, so the
gate's ``approval_requested`` branch was unreachable from that path while
``GovernedWorkflowManager.submit`` reached it.

Each test reproduces the exact case its issue records and pins the fixed behaviour.
No production code outside the two fixes is exercised here.
"""
from __future__ import annotations

import uuid
from typing import Optional

from contracts.task import CorrelationContext, TaskRequest
from control_plane.engine import Engine
from control_plane.governance import (
    CorrelationContext as GovernanceCorrelationContext,
)
from control_plane.governance import (
    GovernedWorkflowManager,
    evaluate_gate,
    get_role,
)
from control_plane.governance import (
    TaskRequest as GovernanceTaskRequest,
)
from control_plane.store import Store
from control_plane.workflow import WorkflowState

TS = "2026-09-29T00:00:00Z"


# ── builders ───────────────────────────────────────────────────────────────


def _engine_request(
    *,
    requires_approval: bool,
    actor: str = "sami",
    role: str = "ops_gm",
    capability: str = "wfm_forecast",
) -> TaskRequest:
    """A canonical C1 request that reaches the C2 gate with no boundary breach."""
    return TaskRequest(
        request_id="req-engine-approval",
        correlation=CorrelationContext(
            correlation_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            tenant_id="helix-prime",
            client_id="Account Alpha",
            created_at=TS,
        ),
        requesting_actor=actor,
        owning_role_id=role,
        capability=capability,
        input_payload={},
        requires_approval=requires_approval,
        status="proposed",
        created_at=TS,
        client_id="Account Alpha",
    )


def _gov_request(
    *,
    role: str = "ops_gm",
    actor: str = "sami",
    engine: Optional[str] = None,
    capability: str = "wfm_forecast",
    requires_approval: bool = False,
) -> GovernanceTaskRequest:
    """A governance request for the ``GovernedWorkflowManager`` submission path."""
    return GovernanceTaskRequest(
        request_id="req-gov-approval",
        correlation=GovernanceCorrelationContext(
            correlation_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            tenant_id="helix-prime",
            client_id="Account Alpha",
            created_at=TS,
            actor_id=actor,
        ),
        requesting_actor=actor,
        owning_role_id=role,
        capability=capability,
        input_payload={},
        requires_approval=requires_approval,
        status="proposed",
        created_at=TS,
        tenant_id="helix-prime",
        client_id="Account Alpha",
        target_engine=engine,
        estimated_financial_cost=0.0,
        confidence_score=0.95,
        requested_data_classification="internal",
    )


# ── issue 1 — oversight_only must be enforced by the gate ──────────────────


def test_oversight_only_role_never_reaches_executing_without_a_target_engine(tmp_path):
    """The exact case in ``KNOWN_ISSUES.md`` issue 1.

    ``compliance_quality_gm``, cost 0, confidence >= 0.75, no ``target_engine``.
    Before the fix this returned ``within_bounds`` / ``EXECUTING``; it must now be
    refused as a hard deny, because no human approval could make an oversight-only
    seat legally execute.
    """
    decision = evaluate_gate(
        "compliance_quality_gm",
        estimated_financial_cost=0.0,
        confidence_score=0.9,
        data_classification="internal",
        target_engine=None,
    )
    assert decision.state != WorkflowState.EXECUTING
    assert decision.state == WorkflowState.DEAD_LETTER
    assert decision.allowed is False
    assert decision.requires_human_approval is False
    assert decision.reason_code == "oversight_only"

    # The enforcement is independent of ``target_engine``. A named engine is already
    # refused by the ownership boundary (``access_denied``); the no-engine case is the
    # loophole this fix closes. Either way the state is never ``executing``.
    for engine in (None, "wfm", "control_plane", "crm"):
        variant = evaluate_gate("compliance_quality_gm", target_engine=engine)
        assert variant.state != WorkflowState.EXECUTING, engine
        assert variant.allowed is False, engine

    # ``owns_engine(None)`` now answers "does this seat own any engine at all?". An
    # engine-less oversight seat owns nothing and answers ``False``; a seat that owns
    # engines still answers ``True`` for the no-engine case.
    assert get_role("compliance_quality_gm").owns_engine(None) is False
    assert get_role("ops_gm").owns_engine(None) is True

    # End to end through the governed submission path, the same case is isolated.
    mgr = GovernedWorkflowManager(store=Store(db_path=str(tmp_path / "gov.db")))
    record = mgr.submit(
        _gov_request(
            role="compliance_quality_gm",
            actor="andy",
            engine=None,
            capability="policy_enforcement",
        )
    )
    assert record.state == WorkflowState.DEAD_LETTER
    assert record.reason_code == "oversight_only"


def test_oversight_only_submission_dead_letters_through_engine_submit(tmp_path):
    """Issue 1 on the ``Engine.submit`` path.

    The same oversight-only, no-``target_engine`` case, submitted directly through
    ``Engine.submit``. The gate refuses it with ``requires_human_approval=False``;
    ``Engine.submit`` must act on ``allowed=False`` and isolate the task instead of
    falling through to ``EXECUTING``.
    """
    engine = Engine(
        store=Store(db_path=str(tmp_path / "wf.db")),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    workflow = engine.submit(
        _engine_request(
            requires_approval=False,
            actor="andy",
            role="compliance_quality_gm",
            capability="policy_enforcement",
        )
    )

    assert workflow.state != WorkflowState.EXECUTING
    assert workflow.state == WorkflowState.DEAD_LETTER
    assert workflow.error is not None
    # AgentError.code is constrained by contracts.task, so the gate's specific
    # reason_code is carried on the dead-letter event instead of the error code.
    assert workflow.error.code == "policy_denied"
    dead_letter_events = [
        event
        for event in engine.store.get_events(workflow.workflow_id)
        if event.event_type == "workflow_dead_letter"
    ]
    assert dead_letter_events
    assert dead_letter_events[-1].payload.get("reason_code") == "oversight_only"


# ── issue 2 — requires_approval must be forwarded on both paths ────────────


def test_explicit_approval_is_gated_identically_on_both_submission_paths(tmp_path):
    """The exact case in ``KNOWN_ISSUES.md`` issue 2.

    A task submitted with ``requires_approval=True`` must take the gate's
    ``approval_requested`` branch on *both* submission paths, so the two agree on
    the gate's verdict rather than only on the terminal state.
    """
    engine = Engine(
        store=Store(db_path=str(tmp_path / "wf.db")),
        audit_db_path=str(tmp_path / "audit.db"),
        log_path=str(tmp_path / "logs.jsonl"),
    )
    workflow = engine.submit(_engine_request(requires_approval=True))
    engine_reasons = [
        event.payload.get("reason_code")
        for event in engine.store.get_events(workflow.workflow_id)
        if event.event_type == "workflow_awaiting_approval"
    ]

    mgr = GovernedWorkflowManager(store=Store(db_path=str(tmp_path / "gov.db")))
    record = mgr.submit(_gov_request(requires_approval=True))

    assert workflow.state == WorkflowState.AWAITING_APPROVAL
    assert record.state == WorkflowState.AWAITING_APPROVAL
    # The gate's own ``approval_requested`` branch is now reachable from Engine.submit.
    assert engine_reasons == ["approval_requested"]
    assert record.reason_code == "approval_requested"
    # The two paths agree on the gate's verdict, not just the state.
    assert workflow.state == record.state
    assert engine_reasons[-1] == record.reason_code
