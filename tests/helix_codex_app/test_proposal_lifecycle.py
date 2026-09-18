"""The full proposal lifecycle, end to end (P5.6).

One test walks the whole path a person and their reviewer actually take, and the
rest pin the refusals that make the path worth trusting.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.errors import InvalidStateError, PermissionDenied
from helix_codex_app.modules.memory.service import MemoryService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    memory_root = str(tmp_path / "memory_stores")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("academy.test", tenant_id="tenant-a", client_id="client-a")
    ravi = repo.create_account(
        domain.domain_id, "ravi", role_id="employee", password_hash=hash_password("your-password")
    )
    layla = repo.create_account(
        domain.domain_id, "layla", role_id="manager", password_hash=hash_password("your-password")
    )
    service = MemoryService(conn, memory_root=memory_root)
    yield SimpleNamespace(conn=conn, ravi=ravi, layla=layla, service=service)
    db.close(conn)


def _propose(ctx):
    return ctx.service.propose(
        ctx.ravi,
        kind="policy",
        target="follow_up_threshold",
        baseline="threshold=0.5",
        proposed="threshold=0.3",
        baseline_policy={"value": 0.5},
        proposed_policy={"value": 0.3},
        hypothesis="a lower threshold catches more at-risk accounts",
        risk_assessment="low: reversible and monitored",
        rollback_plan="restore the previous threshold",
        evidence=["mem-000001"],
    )


def test_the_whole_lifecycle_end_to_end(ctx):
    """draft -> evaluated -> approved -> rolled back, with the ledger intact."""
    ctx.service.stores.record(
        ctx.ravi, kind="outcome", nature="simulated_event", body={"note": "n"}, confidence=0.4
    )
    proposal = _propose(ctx)
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "draft"

    result = ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    assert result.passed is True
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "evaluated"

    approved = ctx.service.approve(ctx.layla, proposal.proposal_id, reason="evidence is sound")
    assert approved.approval_state == "approved"
    assert approved.reviewer == ctx.layla.account_id

    rolled = ctx.service.rollback(ctx.layla, proposal.proposal_id, reason="numbers moved")
    assert rolled.approval_state == "rolled_back"

    decisions = [row["decision"] for row in ctx.service.list_reviews(proposal.proposal_id)]
    assert decisions == ["allowed", "rolled_back"]
    assert ctx.service.verify_ledger(ctx.ravi)["ok"] is True
    # the projection still agrees with the ledger after all four transitions
    rebuilt = ctx.service.rebuild_projection(ctx.ravi)
    assert rebuilt == 1
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "rolled_back"


def test_the_separation_of_duties_denial_blocks_the_author(ctx):
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    with pytest.raises(PermissionDenied):
        ctx.service.approve(ctx.ravi, proposal.proposal_id)
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "evaluated"


def test_a_rejected_proposal_stays_rejected(ctx):
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.reject(ctx.layla, proposal.proposal_id, reason="not convinced")
    with pytest.raises(InvalidStateError):
        ctx.service.approve(ctx.layla, proposal.proposal_id)
    with pytest.raises(InvalidStateError):
        ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "rejected"


def test_every_transition_left_a_governed_node(ctx):
    import json

    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.approve(ctx.layla, proposal.proposal_id)
    ctx.service.rollback(ctx.layla, proposal.proposal_id, reason="reconsider")
    rows = ctx.conn.execute("SELECT body, created_by FROM nodes WHERE kind = 'proposal'").fetchall()
    states = [json.loads(row["body"])["state"] for row in rows]
    assert states == ["draft", "evaluated", "approved", "rolled_back"]
    # the reviewer is recorded as the actor on the review transitions
    assert [row["created_by"] for row in rows] == [
        ctx.ravi.account_id,
        ctx.ravi.account_id,
        ctx.layla.account_id,
        ctx.layla.account_id,
    ]
