"""Promotion into org memory (P5.5).

A promotion is the bridge between one person's memory and the company's. These
tests pin the rules that make that safe: the author's own approval is never
enough, only a manager or owner may decide, exactly one org rule appears when a
promotion is approved, and rolling back retires that rule and says so in both
ledgers.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.errors import InvalidStateError, PermissionDenied
from helix_codex_app.modules.memory import router as memory_router
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
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        ravi=ravi,
        layla=layla,
        service=service,
        memory_root=memory_root,
        db_path=db_path,
    )
    db.close(conn)


def _approved_proposal(ctx):
    """A personal rule that has been evaluated and approved by somebody else."""
    proposal = ctx.service.propose(
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
    )
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.approve(ctx.layla, proposal.proposal_id, reason="evidence is sound")
    return proposal


def _org_rules(ctx):
    return [
        record
        for record in ctx.service.stores.read_org(ctx.ravi, limit=200)
        if record.kind == "policy"
    ]


# --- the happy path ----------------------------------------------------------
def test_a_promotion_can_be_requested_and_approved(ctx):
    proposal = _approved_proposal(ctx)
    assert _org_rules(ctx) == []
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    assert promotion.state == "requested"
    assert promotion.org_proposal_id

    decided = ctx.service.approve_promotion(ctx.layla, promotion.promotion_id, reason="worth it")
    assert decided.state == "approved"
    assert decided.approved_by == ctx.layla.account_id


def test_the_org_store_gains_exactly_one_rule_on_approval(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    ctx.service.approve_promotion(ctx.layla, promotion.promotion_id)
    rules = _org_rules(ctx)
    assert len(rules) == 1
    assert rules[0].body["promotion_id"] == promotion.promotion_id
    assert rules[0].body["promoted_from_account_id"] == ctx.ravi.account_id
    assert rules[0].body["source_proposal_id"] == proposal.proposal_id
    assert rules[0].evidence_refs == [proposal.proposal_id]


# --- the rules that make it safe ---------------------------------------------
def test_the_author_cannot_approve_their_own_promotion(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    with pytest.raises(PermissionDenied):
        ctx.service.approve_promotion(ctx.ravi, promotion.promotion_id)
    assert ctx.service.list_promotions(ctx.ravi, state="requested")[0].state == "requested"
    assert _org_rules(ctx) == []


def test_an_unapproved_proposal_cannot_be_promoted(ctx):
    proposal = ctx.service.propose(
        ctx.ravi,
        kind="policy",
        target="follow_up_threshold",
        baseline="threshold=0.5",
        proposed="threshold=0.3",
        baseline_policy={"value": 0.5},
        proposed_policy={"value": 0.3},
        hypothesis="a lower threshold catches more at-risk accounts",
        risk_assessment="low",
        rollback_plan="restore the previous threshold",
    )
    with pytest.raises(InvalidStateError):
        ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)


def test_a_rejection_needs_a_reason(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    with pytest.raises(ValueError):
        ctx.service.reject_promotion(ctx.layla, promotion.promotion_id, reason="  ")


def test_a_rejected_promotion_creates_no_org_rule(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    rejected = ctx.service.reject_promotion(
        ctx.layla, promotion.promotion_id, reason="not for everyone"
    )
    assert rejected.state == "rejected"
    assert _org_rules(ctx) == []


# --- rollback ----------------------------------------------------------------
def test_rollback_retires_the_org_rule_and_records_it_in_both_stores(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    ctx.service.approve_promotion(ctx.layla, promotion.promotion_id)
    assert len(_org_rules(ctx)) == 1

    rolled = ctx.service.rollback_promotion(
        ctx.layla, promotion.promotion_id, reason="numbers moved"
    )
    assert rolled.state == "rolled_back"
    # the org rule is retired: still in the ledger, no longer retrievable
    assert _org_rules(ctx) == []
    org_all = ctx.service.stores.org_store_for(ctx.ravi).retrieve(
        tenant_id=ctx.ravi.tenant_id, include_deleted=True
    )
    retired = [r for r in org_all if r.body.get("promotion_id") == promotion.promotion_id]
    assert len(retired) == 1
    assert retired[0].deleted == "numbers moved"
    assert retired[0].retention_status == "deleted"
    # and the author's own store carries the reversal note
    notes = [
        record
        for record in ctx.service.stores.read(ctx.ravi, limit=200)
        if record.source == "promotion_reversal"
    ]
    assert len(notes) == 1
    assert notes[0].body["promotion_id"] == promotion.promotion_id


def test_rollback_before_approval_is_refused(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    with pytest.raises(InvalidStateError):
        ctx.service.rollback_promotion(ctx.layla, promotion.promotion_id, reason="too early")


# --- the queue ---------------------------------------------------------------
def test_an_employee_is_refused_the_promotion_queue(ctx):
    request = SimpleNamespace(
        state=SimpleNamespace(account=ctx.ravi),
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(db_path=ctx.db_path))),
    )
    with pytest.raises(PermissionDenied):
        memory_router.promotions_screen(request)


def test_a_manager_sees_the_promotion_in_the_queue(ctx):
    proposal = _approved_proposal(ctx)
    promotion = ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    rows = ctx.service.list_promotions(ctx.layla, state="requested")
    assert [row.promotion_id for row in rows] == [promotion.promotion_id]
    assert rows[0].state == "requested"


def test_a_promotion_does_not_cross_tenants(ctx):
    other = ctx.repo.create_domain("other.test", tenant_id="tenant-b", client_id="client-b")
    outsider = ctx.repo.create_account(
        other.domain_id, "outsider", role_id="owner", password_hash=hash_password("your-password")
    )
    proposal = _approved_proposal(ctx)
    ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)
    assert ctx.service.list_promotions(outsider) == []
