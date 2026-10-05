"""
Tests for control_plane/engine.py submit dead-letter audit coverage
(Prompt C, sub-task 3).

Every dead-letter path in submit must write an audit record with
decision="denied". Four paths previously emitted workflow_dead_letter without
auditing: unknown capability, owning-role mismatch, tool not allowed, and a
tool-permission ValueError.
"""
from __future__ import annotations

from contracts.task import CorrelationContext, TaskRequest
from control_plane.engine import Engine, WorkflowState
from control_plane.store import Store

FIXED_TS = "2026-08-27T18:00:00Z"


def _make_engine(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(store=store, audit_db_path=str(tmp_path / "audit.db"))
    engine.register_handler("ops_execution", lambda wf: {"ok": True})
    return engine


def _make_request(
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


def _record_audits(monkeypatch):
    recorded = []
    orig = Engine._audit

    def spy(self, event_type, workflow, actor, *args, **kwargs):
        recorded.append((event_type, kwargs.get("decision", "allowed")))
        return orig(self, event_type, workflow, actor, *args, **kwargs)

    monkeypatch.setattr(Engine, "_audit", spy)
    return recorded


def _assert_dead_letter_audited(recorded):
    assert ("workflow_dead_letter", "denied") in recorded


def test_unknown_capability_dead_letter_is_audited(monkeypatch, tmp_path):
    import control_plane.engine as engine_mod

    eng = _make_engine(tmp_path)
    recorded = _record_audits(monkeypatch)
    monkeypatch.setattr(engine_mod, "authorize", None)  # bypass the policy gate
    wf = eng.submit(_make_request(capability="no_such_capability"))
    assert wf.state == WorkflowState.DEAD_LETTER
    assert wf.error is not None and wf.error.code == "not_found"
    _assert_dead_letter_audited(recorded)


def test_owner_mismatch_dead_letter_is_audited(monkeypatch, tmp_path):
    import control_plane.engine as engine_mod

    eng = _make_engine(tmp_path)
    recorded = _record_audits(monkeypatch)
    monkeypatch.setattr(engine_mod, "authorize", None)
    wf = eng.submit(_make_request(capability="ops_execution", owning_role_id="ld_gm"))
    assert wf.state == WorkflowState.DEAD_LETTER
    assert wf.error is not None and wf.error.code == "conflict"
    _assert_dead_letter_audited(recorded)


def test_tool_not_allowed_dead_letter_is_audited(monkeypatch, tmp_path):
    import control_plane.engine as engine_mod

    eng = _make_engine(tmp_path)
    recorded = _record_audits(monkeypatch)
    monkeypatch.setattr(engine_mod, "authorize", None)
    monkeypatch.setattr(engine_mod, "is_tool_allowed", lambda role, tool: False)
    wf = eng.submit(_make_request(input_payload={"tool": "forbidden_tool"}))
    assert wf.state == WorkflowState.DEAD_LETTER
    assert wf.error is not None and wf.error.code == "unauthorized"
    _assert_dead_letter_audited(recorded)


def test_tool_check_value_error_dead_letter_is_audited(monkeypatch, tmp_path):
    import control_plane.engine as engine_mod

    eng = _make_engine(tmp_path)
    recorded = _record_audits(monkeypatch)
    monkeypatch.setattr(engine_mod, "authorize", None)

    def _boom(role, tool):
        raise ValueError("tool registry unavailable")

    monkeypatch.setattr(engine_mod, "is_tool_allowed", _boom)
    wf = eng.submit(_make_request(input_payload={"tool": "any_tool"}))
    assert wf.state == WorkflowState.DEAD_LETTER
    assert wf.error is not None and wf.error.code == "unauthorized"
    _assert_dead_letter_audited(recorded)
