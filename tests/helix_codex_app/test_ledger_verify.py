"""Ledger verification, for both ledgers the app keeps (P5.6).

A memory store and a proposals ledger each carry their own hash chain. These
tests prove an intact chain verifies and a tampered one does not — on both, and
at both ends of the chain, because a chain that only catches edits to the first
line is not a chain.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from helix_codex_app import db
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
    service = MemoryService(conn, memory_root=memory_root)
    yield SimpleNamespace(conn=conn, ravi=ravi, service=service, memory_root=memory_root)
    db.close(conn)


def _seed_memory(ctx, count=2):
    for index in range(count):
        ctx.service.stores.record(
            ctx.ravi,
            kind="outcome",
            nature="simulated_event",
            body={"note": f"record {index}"},
            confidence=0.4,
        )


def _seed_proposals(ctx, count=2):
    for index in range(count):
        ctx.service.propose(
            ctx.ravi,
            kind="policy",
            target=f"threshold_{index}",
            baseline="threshold=0.5",
            proposed="threshold=0.3",
            baseline_policy={"value": 0.5},
            proposed_policy={"value": 0.3},
            hypothesis="a lower threshold catches more at-risk accounts",
            risk_assessment="low",
            rollback_plan="restore the previous threshold",
        )


def _tamper(path, line_index, *, field="body", value=None):
    """Rewrite one ledger line with a changed field, leaving the stored hash alone.

    The field has to be one the record actually has: a memory record carries
    `body`, a proposal does not, and inventing a key makes the reload fail before
    the chain is ever checked.
    """
    lines = open(path, encoding="utf-8").read().splitlines()
    envelope = json.loads(lines[line_index])
    envelope["record"][field] = {"tampered": True} if value is None else value
    with open(path, "w", encoding="utf-8") as handle:
        for position, line in enumerate(lines):
            handle.write(json.dumps(envelope) + "\n" if position == line_index else line + "\n")


# --- the memory store --------------------------------------------------------
def test_an_intact_memory_chain_verifies(ctx):
    _seed_memory(ctx, count=3)
    result = ctx.service.verify_ledger(ctx.ravi)
    assert result["ok"] is True
    assert result["detail"] == "chain intact"


def test_a_tampered_memory_line_fails_verification(ctx):
    _seed_memory(ctx, count=3)
    path = ctx.service.stores.resolve_store(ctx.ravi)
    _tamper(path, 1)
    fresh = MemoryService(ctx.conn, memory_root=ctx.memory_root)
    assert fresh.verify_ledger(ctx.ravi)["ok"] is False


def test_tampering_with_the_last_memory_line_fails_too(ctx):
    _seed_memory(ctx, count=3)
    path = ctx.service.stores.resolve_store(ctx.ravi)
    _tamper(path, 2)
    fresh = MemoryService(ctx.conn, memory_root=ctx.memory_root)
    assert fresh.verify_ledger(ctx.ravi)["ok"] is False


# --- the proposals ledger ----------------------------------------------------
def test_an_intact_proposals_chain_verifies(ctx):
    _seed_proposals(ctx, count=3)
    assert ctx.service.verify_ledger(ctx.ravi)["ok"] is True


def test_a_tampered_proposals_line_fails_verification(ctx):
    _seed_proposals(ctx, count=3)
    path = ctx.service.engines.resolve_path(ctx.ravi)
    _tamper(path, 0, field="hypothesis", value="tampered")
    fresh = MemoryService(ctx.conn, memory_root=ctx.memory_root)
    assert fresh.verify_ledger(ctx.ravi)["ok"] is False


def test_the_two_ledgers_are_separate_files(ctx):
    _seed_memory(ctx, count=1)
    _seed_proposals(ctx, count=1)
    memory_path = ctx.service.stores.resolve_store(ctx.ravi)
    proposals_path = ctx.service.engines.resolve_path(ctx.ravi)
    assert memory_path != proposals_path
    assert memory_path.endswith("governed_memory.jsonl")
    assert proposals_path.endswith("proposals.jsonl")
