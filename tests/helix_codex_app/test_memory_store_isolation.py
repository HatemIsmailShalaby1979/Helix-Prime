"""Per-account memory isolation, across every path (P5.6).

The promise is that a person's memory is theirs. These tests go after that claim
from every direction the app exposes: the records, the proposals, the chain
verification, and the rollback path. If any one of them leaked, the promise would
be decoration.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.errors import NotFoundError, PermissionDenied
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
    other = repo.create_domain("elsewhere.test", tenant_id="tenant-b", client_id="client-b")
    ravi = repo.create_account(
        domain.domain_id, "ravi", role_id="employee", password_hash=hash_password("your-password")
    )
    sam = repo.create_account(
        domain.domain_id, "sam", role_id="employee", password_hash=hash_password("your-password")
    )
    layla = repo.create_account(
        domain.domain_id, "layla", role_id="manager", password_hash=hash_password("your-password")
    )
    outsider = repo.create_account(
        other.domain_id, "outsider", role_id="owner", password_hash=hash_password("your-password")
    )
    service = MemoryService(conn, memory_root=memory_root)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        ravi=ravi,
        sam=sam,
        layla=layla,
        outsider=outsider,
        service=service,
        memory_root=memory_root,
    )
    db.close(conn)


def _propose(service, author, target="follow_up_threshold"):
    return service.propose(
        author,
        kind="policy",
        target=target,
        baseline="threshold=0.5",
        proposed="threshold=0.3",
        baseline_policy={"value": 0.5},
        proposed_policy={"value": 0.3},
        hypothesis="a lower threshold catches more at-risk accounts",
        risk_assessment="low",
        rollback_plan="restore the previous threshold",
    )


# --- records -----------------------------------------------------------------
def test_one_accounts_records_never_appear_in_anothers_store(ctx):
    ctx.service.stores.record(
        ctx.ravi, kind="outcome", nature="simulated_event", body={"note": "ravi"}, confidence=0.4
    )
    assert [r.body["note"] for r in ctx.service.stores.read(ctx.ravi)] == ["ravi"]
    assert ctx.service.stores.read(ctx.sam) == []


def test_an_account_in_another_tenant_sees_nothing(ctx):
    ctx.service.stores.record(
        ctx.ravi, kind="outcome", nature="simulated_event", body={"note": "ravi"}, confidence=0.4
    )
    assert ctx.service.stores.read(ctx.outsider) == []
    assert ctx.service.stores.read_org(ctx.outsider) == []


def test_the_two_stores_are_separate_files(ctx):
    ctx.service.stores.record(
        ctx.ravi, kind="outcome", nature="simulated_event", body={"note": "ravi"}, confidence=0.4
    )
    ravi_path = ctx.service.stores.resolve_store(ctx.ravi)
    sam_path = ctx.service.stores.resolve_store(ctx.sam)
    assert ravi_path != sam_path
    assert "ravi" not in sam_path
    assert ctx.sam.account_id in sam_path
    assert ctx.ravi.account_id not in sam_path


# --- proposals ---------------------------------------------------------------
def test_one_accounts_proposals_are_invisible_to_another(ctx):
    proposal = _propose(ctx.service, ctx.ravi)
    assert ctx.service.list_proposals(ctx.sam) == []
    with pytest.raises(NotFoundError):
        ctx.service.get_proposal(ctx.sam, proposal.proposal_id)
    with pytest.raises(NotFoundError):
        ctx.service.evidence_report(ctx.sam, proposal.proposal_id)


def test_another_account_cannot_evaluate_your_proposal(ctx):
    proposal = _propose(ctx.service, ctx.ravi)
    with pytest.raises(NotFoundError):
        ctx.service.evaluate(ctx.sam, proposal.proposal_id)


def test_another_account_cannot_roll_back_your_proposal(ctx):
    proposal = _propose(ctx.service, ctx.ravi)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    ctx.service.approve(ctx.layla, proposal.proposal_id)
    with pytest.raises(NotFoundError):
        ctx.service.rollback(ctx.sam, proposal.proposal_id, reason="not mine to touch")
    assert ctx.service.get_proposal(ctx.ravi, proposal.proposal_id).approval_state == "approved"


def test_a_same_role_peer_cannot_review_you(ctx):
    """Same-role review is refused by the engine, and the view refuses it too."""
    proposal = _propose(ctx.service, ctx.ravi)
    ctx.service.evaluate(ctx.ravi, proposal.proposal_id)
    with pytest.raises(PermissionDenied):
        ctx.service.approve(ctx.sam, proposal.proposal_id)


# --- chains ------------------------------------------------------------------
def test_tampering_with_one_ledger_does_not_affect_another(ctx):
    ctx.service.stores.record(
        ctx.ravi, kind="outcome", nature="simulated_event", body={"note": "ravi"}, confidence=0.4
    )
    ctx.service.stores.record(
        ctx.sam, kind="outcome", nature="simulated_event", body={"note": "sam"}, confidence=0.4
    )
    ravi_path = ctx.service.stores.resolve_store(ctx.ravi)
    lines = open(ravi_path, encoding="utf-8").read().splitlines()
    envelope = json.loads(lines[0])
    envelope["record"]["body"] = {"tampered": True}
    with open(ravi_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(envelope) + "\n")
        for line in lines[1:]:
            handle.write(line + "\n")

    fresh = MemoryService(ctx.conn, memory_root=ctx.memory_root)
    assert fresh.verify_ledger(ctx.ravi)["ok"] is False
    assert fresh.verify_ledger(ctx.sam)["ok"] is True


def test_the_org_store_is_shared_but_still_tenant_scoped(ctx):
    ctx.service.stores.record_org(
        ctx.ravi, kind="policy", nature="user_claim", body={"rule": "shared"}
    )
    assert len(ctx.service.stores.read_org(ctx.sam)) == 1
    assert ctx.service.stores.read_org(ctx.outsider) == []
