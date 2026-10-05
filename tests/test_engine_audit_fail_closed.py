"""
Tests for control_plane/engine.py audit-failure handling (Prompt C, sub-task 1).

The audit trail must never fail silently. A *consequential* audit (one that
commits a forward state change) must move the workflow to DEAD_LETTER when the
write fails; a non-consequential audit stays best-effort and must not raise.
"""
from __future__ import annotations

import pytest

from contracts.task import CorrelationContext, TaskRequest
from control_plane.engine import AuditUnavailable, Engine, WorkflowState
from control_plane.store import Store
from control_plane.workflow import Workflow

FIXED_TS = "2026-08-27T18:00:00Z"


def _make_engine(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(store=store, audit_db_path=str(tmp_path / "audit.db"))
    engine.register_handler("ops_execution", lambda wf: {"ok": True})
    return engine


def _make_workflow_request(
    capability="ops_execution",
    owning_role_id="ops_gm",
    requesting_actor="suby",
    input_payload=None,
):
    if input_payload is None:
        input_payload = {}
    corr = CorrelationContext(
        correlation_id=f"corr_{capability}_{owning_role_id}",
        idempotency_key=f"idem_{capability}_{owning_role_id}",
        tenant_id="helix-prime",
        client_id="Account Alpha",
        created_at=FIXED_TS,
    )
    return TaskRequest(
        request_id=f"req_{capability}",
        correlation=corr,
        requesting_actor=requesting_actor,
        owning_role_id=owning_role_id,
        capability=capability,
        input_payload=input_payload,
        requires_approval=True,
        status="proposed",
        created_at=FIXED_TS,
        client_id="Account Alpha",
    )


def _patch_audit_append_to_fail(monkeypatch):
    import control_plane.engine as engine_mod

    def _boom(self, record):
        raise OSError("disk full")

    monkeypatch.setattr(engine_mod.AuditTrail, "append", _boom)


def test_submit_dead_letters_when_consequential_audit_fails(monkeypatch, tmp_path):
    """A failed consequential audit must not silently proceed: the workflow is
    failed closed into DEAD_LETTER with a dedicated error code."""
    eng = _make_engine(tmp_path)
    _patch_audit_append_to_fail(monkeypatch)

    wf = eng.submit(_make_workflow_request())

    assert wf.state == WorkflowState.DEAD_LETTER
    assert wf.error is not None
    assert wf.error.code == "dependency_unavailable"


def test_nonconsequential_audit_failure_is_swallowed_but_consequential_raises(
    monkeypatch, tmp_path
):
    """Best-effort (non-consequential) audits must not raise; consequential ones
    must raise AuditUnavailable so the caller can fail closed."""

    eng = _make_engine(tmp_path)
    req = _make_workflow_request()
    wf = Workflow.new(
        correlation=req.correlation,
        requesting_actor=req.requesting_actor,
        owning_role_id=req.owning_role_id,
        capability=req.capability,
        input_payload=req.input_payload,
    )
    _patch_audit_append_to_fail(monkeypatch)

    # Non-consequential: must not raise.
    eng._audit("probe_event", wf, req.requesting_actor, consequential=False)

    # Consequential: must surface as AuditUnavailable.
    with pytest.raises(AuditUnavailable):
        eng._audit("probe_event", wf, req.requesting_actor, consequential=True)
