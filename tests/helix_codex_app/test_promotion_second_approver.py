"""A promotion always needs a second, suitably senior person (P5.6).

The point of promotion is that a good idea can travel without anybody being able
to push their own rule onto the whole company. These three tests are the whole
argument: self-approval denied, a manager accepted, an ordinary employee denied.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.errors import PermissionDenied
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
    sam = repo.create_account(
        domain.domain_id, "sam", role_id="employee", password_hash=hash_password("your-password")
    )
    layla = repo.create_account(
        domain.domain_id, "layla", role_id="manager", password_hash=hash_password("your-password")
    )
    service = MemoryService(conn, memory_root=memory_root)
    yield SimpleNamespace(conn=conn, ravi=ravi, sam=sam, layla=layla, service=service)
    db.close(conn)


def _promotion(ctx):
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
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.approve(ctx.layla, proposal.proposal_id)
    return ctx.service.request_promotion(ctx.ravi, proposal.proposal_id)


def _org_rules(ctx):
    return [
        record
        for record in ctx.service.stores.read_org(ctx.ravi, limit=200)
        if record.kind == "policy"
    ]


def test_the_author_cannot_approve_their_own_promotion(ctx):
    promotion = _promotion(ctx)
    with pytest.raises(PermissionDenied):
        ctx.service.approve_promotion(ctx.ravi, promotion.promotion_id)
    assert _org_rules(ctx) == []


def test_a_peer_employee_cannot_approve_a_promotion(ctx):
    promotion = _promotion(ctx)
    with pytest.raises(PermissionDenied):
        ctx.service.approve_promotion(ctx.sam, promotion.promotion_id)
    assert _org_rules(ctx) == []


def test_a_manager_can_approve_a_promotion(ctx):
    promotion = _promotion(ctx)
    decided = ctx.service.approve_promotion(ctx.layla, promotion.promotion_id, reason="worth it")
    assert decided.state == "approved"
    assert decided.approved_by == ctx.layla.account_id
    assert len(_org_rules(ctx)) == 1


def test_a_peer_employee_cannot_reject_a_promotion_either(ctx):
    promotion = _promotion(ctx)
    with pytest.raises(PermissionDenied):
        ctx.service.reject_promotion(ctx.sam, promotion.promotion_id, reason="no")
    assert ctx.service.list_promotions(ctx.layla, state="requested")
