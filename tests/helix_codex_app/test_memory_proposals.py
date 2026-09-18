"""Memory proposal lifecycle tests (P5.3).

The ledger is the source of truth and the projection follows it. These tests walk
the whole path — propose, evaluate, review, roll back — and pin the two rules
that make the promise worth anything: a proposal cannot be approved before it has
been evaluated, and nobody can approve their own. They also pin the guard that
stops a rejected proposal being quietly revived.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.errors import InvalidStateError, NotFoundError, PermissionDenied
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
        domain.domain_id,
        "ravi",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    layla = repo.create_account(
        domain.domain_id,
        "layla",
        role_id="manager",
        password_hash=hash_password("your-password"),
    )
    service = MemoryService(conn, memory_root=memory_root)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        ravi=ravi,
        layla=layla,
        service=service,
        memory_root=memory_root,
    )
    db.close(conn)


def _propose(ctx, *, proposer=None, baseline=0.5, proposed=0.3, min_improvement=0.0):
    return ctx.service.propose(
        proposer or ctx.ravi,
        kind="policy",
        target="follow_up_threshold",
        baseline=f"threshold={baseline}",
        proposed=f"threshold={proposed}",
        baseline_policy={"value": baseline},
        proposed_policy={"value": proposed},
        hypothesis="a lower threshold catches more at-risk accounts",
        risk_assessment="low: reversible and monitored",
        rollback_plan="restore the previous threshold",
        evidence=["mem-000001"],
        min_improvement=min_improvement,
    )


def _seed_evidence(ctx, *, confidence=0.4):
    ctx.service.stores.record(
        ctx.ravi,
        kind="outcome",
        nature="simulated_event",
        body={"note": "followed up"},
        confidence=confidence,
    )


# --- the happy path ----------------------------------------------------------
def test_a_proposal_can_be_created_and_evaluated(ctx):
    _seed_evidence(ctx, confidence=0.4)
    proposal = _propose(ctx)
    assert proposal.approval_state == "draft"
    result = ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    assert result.baseline_rate == 0.0
    assert result.proposed_rate == 1.0
    assert result.passed is True
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "evaluated"


def test_a_cross_role_reviewer_can_approve(ctx):
    _seed_evidence(ctx)
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    approved = ctx.service.approve(ctx.layla, proposal.proposal_id, reason="evidence is sound")
    assert approved.approval_state == "approved"
    assert [r["decision"] for r in ctx.service.list_reviews(proposal.proposal_id)] == ["allowed"]


def test_rollback_records_the_reversal(ctx):
    _seed_evidence(ctx)
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.approve(ctx.layla, proposal.proposal_id)
    rolled = ctx.service.rollback(ctx.layla, proposal.proposal_id, reason="numbers moved")
    assert rolled.approval_state == "rolled_back"
    decisions = [r["decision"] for r in ctx.service.list_reviews(proposal.proposal_id)]
    assert decisions == ["allowed", "rolled_back"]


# --- the rules that make it mean something -----------------------------------
def test_approving_before_evaluation_raises(ctx):
    proposal = _propose(ctx)
    with pytest.raises(InvalidStateError):
        ctx.service.approve(ctx.layla, proposal.proposal_id)
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "draft"


def test_nobody_can_approve_their_own_proposal(ctx):
    _seed_evidence(ctx)
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    with pytest.raises(PermissionDenied):
        ctx.service.approve(ctx.ravi, proposal.proposal_id)
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "evaluated"


def test_a_rejected_proposal_cannot_be_evaluated_again(ctx):
    """Otherwise reject -> evaluate -> approve would quietly undo the rejection."""
    _seed_evidence(ctx)
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.reject(ctx.layla, proposal.proposal_id, reason="not convinced")
    with pytest.raises(InvalidStateError):
        ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "rejected"


def test_rollback_before_approval_is_refused(ctx):
    proposal = _propose(ctx)
    with pytest.raises(InvalidStateError):
        ctx.service.rollback(ctx.layla, proposal.proposal_id, reason="too early")


def test_rejection_needs_a_reason(ctx):
    _seed_evidence(ctx)
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    with pytest.raises(ValueError):
        ctx.service.reject(ctx.layla, proposal.proposal_id, reason="   ")


# --- the ledger leads, the projection follows --------------------------------
def test_a_rebuilt_projection_matches_the_ledger(ctx):
    _seed_evidence(ctx)
    first = _propose(ctx)
    second = _propose(ctx, proposed=0.2)
    ctx.service.evaluate(ctx.ravi, first.proposal_id)
    ctx.service.approve(ctx.layla, first.proposal_id)
    before = {row.proposal_id: row.state for row in ctx.service.list_proposals(ctx.ravi)}
    assert ctx.service.rebuild_projection(ctx.ravi) == 2
    after = {row.proposal_id: row.state for row in ctx.service.list_proposals(ctx.ravi)}
    assert after == before
    assert after[first.proposal_id] == "approved"
    assert after[second.proposal_id] == "draft"


def test_every_transition_writes_a_governed_node(ctx):
    _seed_evidence(ctx)
    proposal = _propose(ctx)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.approve(ctx.layla, proposal.proposal_id)
    rows = ctx.conn.execute("SELECT body FROM nodes WHERE kind = 'proposal'").fetchall()
    states = [json.loads(row["body"])["state"] for row in rows]
    assert states == ["draft", "evaluated", "approved"]


def test_the_ledger_verifies(ctx):
    _propose(ctx)
    result = ctx.service.verify_ledger(ctx.ravi)
    assert result["ok"] is True
    assert result["detail"] == "chain intact"


# --- isolation ---------------------------------------------------------------
def test_another_account_cannot_read_your_proposal(ctx):
    proposal = _propose(ctx)
    sam = ctx.repo.create_account(
        ctx.domain.domain_id,
        "sam",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    assert ctx.service.list_proposals(sam) == []
    with pytest.raises(NotFoundError):
        ctx.service.get_proposal(sam, proposal.proposal_id)
