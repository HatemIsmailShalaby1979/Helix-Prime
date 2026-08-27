"""C2 preflight regression tests — Part 0 before C3.

Covers:
- per-aggregate sequence allows 1 for multiple workflows while rejecting duplicate (aggregate_id, sequence)
- safe transactions: repeated/concurrent submissions do not duplicate workflows/events
- default DB path is ignored via .gitignore
"""
import pathlib

import pytest

from control_plane.store import Store, DEFAULT_DB_PATH
from control_plane.events import Event


def test_per_aggregate_allows_same_sequence_for_multiple_workflows():
    store = Store(db_path=":memory:")
    # Same sequence 0 for different aggregates should be allowed (per-aggregate, not global)
    ev_a0 = Event.new(event_type="workflow_created", aggregate_id="wf_A", correlation_id="corr_A", actor="sami", payload={}, sequence=0)
    ev_b0 = Event.new(event_type="workflow_created", aggregate_id="wf_B", correlation_id="corr_B", actor="sami", payload={}, sequence=0)
    store.append_event(ev_a0)
    store.append_event(ev_b0)
    # Same sequence 1 for both should also be allowed
    ev_a1 = Event.new(event_type="workflow_validated", aggregate_id="wf_A", correlation_id="corr_A", actor="sami", payload={}, sequence=1)
    ev_b1 = Event.new(event_type="workflow_validated", aggregate_id="wf_B", correlation_id="corr_B", actor="sami", payload={}, sequence=1)
    store.append_event(ev_a1)
    store.append_event(ev_b1)
    assert len(store.get_events("wf_A")) == 2
    assert len(store.get_events("wf_B")) == 2


def test_duplicate_aggregate_sequence_rejected():
    store = Store(db_path=":memory:")
    ev0 = Event.new(event_type="workflow_created", aggregate_id="wf_X", correlation_id="corr_X", actor="sami", payload={}, sequence=0)
    store.append_event(ev0)
    # Same aggregate, same sequence, different event_id must be rejected (per-aggregate unique)
    dup = Event(
        event_id="different_id",
        event_type="workflow_validated",
        aggregate_id="wf_X",
        correlation_id="corr_X",
        actor="sami",
        schema_version="1.0",
        timestamp=ev0.timestamp,
        payload={},
        sequence=0,
    )
    with pytest.raises(ValueError, match="out-of-order|UNIQUE|duplicate"):
        store.append_event(dup)


def test_repeated_submission_does_not_duplicate_workflow(tmp_path):
    from contracts.task import TaskRequest, CorrelationContext
    from control_plane.engine import Engine

    db = str(tmp_path / "preflight.db")
    store = Store(db_path=db)
    engine = Engine(store=store)
    corr = CorrelationContext(correlation_id="corr_pre", idempotency_key="idem_pre", tenant_id="t", client_id="c", created_at="2026-08-27T18:00:00Z")
    req = TaskRequest(
        request_id="req_pre",
        correlation=corr,
        requesting_actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        input_payload={},
        requires_approval=False,
        status="proposed",
        created_at="2026-08-27T18:00:00Z",
        client_id="c",
    )
    wf1 = engine.submit(req)
    # Repeated submission with same idempotency_key (simulating concurrent/retry) must return same workflow_id, not duplicate
    req2 = TaskRequest(
        request_id="req_pre2",
        correlation=corr,  # same idempotency_key
        requesting_actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        input_payload={},
        requires_approval=False,
        status="proposed",
        created_at="2026-08-27T18:00:00Z",
        client_id="c",
    )
    wf2 = engine.submit(req2)
    assert wf1.workflow_id == wf2.workflow_id
    assert len(store.list_workflows()) == 1

    # Repeated event append with same event_id is idempotent (returns existing, no duplicate)
    ev = Event.new(event_type="workflow_created", aggregate_id="wf_dup_event", correlation_id="corr_dup", actor="sami", payload={}, sequence=0)
    store2 = Store(db_path=":memory:")
    ev_first = store2.append_event(ev)
    ev_second = store2.append_event(ev)  # same event_id again
    assert ev_first.event_id == ev_second.event_id
    assert len(store2.get_events("wf_dup_event")) == 1


def test_default_db_path_is_ignored():
    # Default DB path must be ignored via .gitignore and not committed as source
    assert DEFAULT_DB_PATH == "control_plane/workflow.db"
    gitignore = pathlib.Path(".gitignore").read_text(encoding="utf-8")
    # Must have at least one of these patterns
    assert "*.db" in gitignore or "control_plane/workflow.db" in gitignore or "control_plane/*.db" in gitignore
    # Must not be tracked
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", DEFAULT_DB_PATH],
        capture_output=True,
        text=True,
    )
    # git ls-files --error-unmatch exits 1 if not tracked (expected)
    assert result.returncode != 0, f"{DEFAULT_DB_PATH} should not be tracked by git"


def test_store_preserves_across_restart(tmp_path):
    # Verify persistence across process restart (re-open)
    from contracts.task import TaskRequest, CorrelationContext
    from control_plane.engine import Engine

    db_path = str(tmp_path / "restart.db")
    store1 = Store(db_path=db_path)
    engine1 = Engine(store=store1)
    corr = CorrelationContext(correlation_id="corr_restart", idempotency_key="idem_restart", tenant_id="t", client_id="c", created_at="2026-08-27T18:00:00Z")
    req = TaskRequest(request_id="req_restart", correlation=corr, requesting_actor="sami", owning_role_id="ops_gm", capability="wfm_forecast", input_payload={}, requires_approval=False, status="proposed", created_at="2026-08-27T18:00:00Z", client_id="c")
    wf1 = engine1.submit(req)
    wf_id = wf1.workflow_id
    store1.close()

    # Reopen store (simulates process restart) and verify workflow + events still there
    store2 = Store(db_path=db_path)
    wf_reloaded = store2.get_workflow(wf_id)
    assert wf_reloaded is not None
    assert wf_reloaded.workflow_id == wf_id
    events = store2.get_events(wf_id)
    assert len(events) >= 2
