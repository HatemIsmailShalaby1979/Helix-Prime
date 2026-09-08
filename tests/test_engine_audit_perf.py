"""
Engine audit performance — the test that would have caught a known defect.

``Engine._audit`` used to reconstruct the tip of the audit hash chain by loading
up to 10,000 ``AuditRecord`` rows and taking the last one, on **every** audit
write. Audit cost was therefore linear in the length of the chain, and the
workflow that had been running longest paid the most. Nobody noticed because
the chain is short in tests and the failure mode is "slow", not "wrong".

This test pins the property, not the implementation: the number of statements
``_audit`` issues must not depend on how many records are already in the trail.
"""
from __future__ import annotations

import pytest

from contracts.task import CorrelationContext
from control_plane import engine as engine_module
from control_plane.workflow import Workflow
from security.audit import AuditRecord, AuditTrail


class _TracingAuditTrail(AuditTrail):
    """An AuditTrail that records every statement executed against its connection."""

    def __init__(self, db_path: str, statements: list[str]) -> None:
        super().__init__(db_path=db_path)
        self.conn.set_trace_callback(statements.append)


def _workflow() -> Workflow:
    return Workflow.new(
        correlation=CorrelationContext.new(tenant_id="tenant-audit", client_id="client-audit"),
        requesting_actor="suby",
        owning_role_id="ops_gm",
        capability="rta_adherence",
        input_payload={"probe": True},
        requires_approval=False,
    )


def _seed(trail: AuditTrail, count: int) -> None:
    prev = None
    for _ in range(count):
        rec = AuditRecord.new(
            event_type="seed",
            actor="seeder",
            actor_type="service",
            decision="allowed",
            previous_hash=prev,
        )
        trail.append(rec)
        prev = rec.current_hash


def _count_statements(engine, statements: list[str]) -> int:
    statements.clear()
    engine._audit("workflow_submitted", _workflow(), "suby")
    return sum(1 for s in statements if s.strip().upper().startswith("SELECT"))


def test_audit_cost_is_independent_of_chain_length(tmp_path, monkeypatch) -> None:
    short_db = tmp_path / "short" / "audit.db"
    short_db.parent.mkdir(parents=True)
    short_trail = AuditTrail(db_path=str(short_db))
    _seed(short_trail, 5)
    short_trail.close()

    long_db = tmp_path / "long" / "audit.db"
    long_db.parent.mkdir(parents=True)
    long_trail = AuditTrail(db_path=str(long_db))
    _seed(long_trail, 200)
    long_trail.close()

    statements: list[str] = []
    monkeypatch.setattr(
        engine_module,
        "AuditTrail",
        lambda db_path: _TracingAuditTrail(db_path, statements),
    )

    engine_short = engine_module.Engine(
        db_path=str(tmp_path / "short" / "wf.db"),
        audit_db_path=str(short_db),
    )
    engine_long = engine_module.Engine(
        db_path=str(tmp_path / "long" / "wf.db"),
        audit_db_path=str(long_db),
    )

    # Two calls each: the first primes the cached tip, the second is steady state.
    short_first = _count_statements(engine_short, statements)
    short_steady = _count_statements(engine_short, statements)
    long_first = _count_statements(engine_long, statements)
    long_steady = _count_statements(engine_long, statements)

    assert short_steady == long_steady, (
        f"audit cost scales with chain length: {short_steady} selects at 5 records "
        f"vs {long_steady} at 200"
    )
    assert max(short_first, long_first) <= 2, "cold read of the chain tip must be a single lookup"
    assert max(short_steady, long_steady) <= 1, "steady-state append must issue at most one read"

    # No statement may scan the whole table.
    assert not any("LIMIT 10000" in s.upper() for s in statements)


def test_audit_chain_stays_valid_after_engine_writes(tmp_path) -> None:
    """The optimisation must not corrupt the hash chain."""
    db = tmp_path / "audit.db"
    engine = engine_module.Engine(
        db_path=str(tmp_path / "wf.db"),
        audit_db_path=str(db),
    )
    for _ in range(3):
        engine._audit("workflow_submitted", _workflow(), "suby")

    trail = AuditTrail(db_path=str(db))
    try:
        ok, detail = trail.verify_chain()
        assert ok is True, detail
        assert len(trail.list_records(limit=100)) == 3
    finally:
        trail.close()


@pytest.mark.parametrize("records", [0, 1, 25])
def test_last_hash_returns_chain_tip(tmp_path, records: int) -> None:
    db = tmp_path / "audit.db"
    trail = AuditTrail(db_path=str(db))
    try:
        assert trail.last_hash() is None
        _seed(trail, records)
        if records == 0:
            assert trail.last_hash() is None
        else:
            assert trail.last_hash() is not None
    finally:
        trail.close()
