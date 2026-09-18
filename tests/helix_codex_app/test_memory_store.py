"""Per-account governed memory store tests (P5.2).

Each account gets its own governed memory store, and each tenant gets one shared
org store. These tests prove the isolation holds by construction: the path is
derived from the authenticated account, so two people in the same tenant cannot
see each other's memory, while the org store is deliberately shared. They also
prove the memory_stores index tracks the ledger, and that a tampered line fails
verification.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.integration.memory_bridge import (
    ORG_KEY,
    AccountMemoryStore,
    resolve_store_path,
)
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
    nadia = repo.create_account(
        domain.domain_id,
        "nadia",
        role_id="manager",
        password_hash=hash_password("your-password"),
    )
    rami = repo.create_account(
        domain.domain_id,
        "rami",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    outsider = repo.create_account(
        other.domain_id,
        "outsider",
        role_id="owner",
        password_hash=hash_password("your-password"),
    )
    store = AccountMemoryStore(conn=conn, memory_root=memory_root)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        other=other,
        nadia=nadia,
        rami=rami,
        outsider=outsider,
        store=store,
        memory_root=memory_root,
    )
    db.close(conn)


# --- paths -------------------------------------------------------------------
def test_resolve_store_path_separates_accounts_from_the_org_store(tmp_path):
    root = str(tmp_path / "memory")
    account_path = resolve_store_path(memory_root=root, domain_id="dom-1", account_id="acc-1")
    org_path = resolve_store_path(memory_root=root, domain_id="dom-1", account_id=None)
    assert account_path != org_path
    assert "acc-1" in account_path
    assert ORG_KEY in org_path


def test_a_path_component_cannot_escape_its_directory(tmp_path):
    root = str(tmp_path / "memory")
    with pytest.raises(ValueError):
        resolve_store_path(memory_root=root, domain_id="../../etc", account_id="acc-1")
    with pytest.raises(ValueError):
        resolve_store_path(memory_root=root, domain_id="..", account_id=None)
    with pytest.raises(ValueError):
        resolve_store_path(memory_root=root, domain_id="dom", account_id="../../escape")
    with pytest.raises(ValueError):
        resolve_store_path(memory_root=root, domain_id="dom/../other", account_id=None)


def test_two_accounts_in_one_tenant_get_different_store_paths(ctx):
    nadia_path = ctx.store.resolve_store(ctx.nadia)
    rami_path = ctx.store.resolve_store(ctx.rami)
    assert nadia_path != rami_path
    assert ctx.nadia.account_id in nadia_path
    assert ctx.rami.account_id not in nadia_path


def test_a_foreign_tenant_account_gets_its_own_path(ctx):
    assert ctx.store.resolve_store(ctx.outsider) != ctx.store.resolve_store(ctx.nadia)
    assert ctx.outsider.domain_id not in ctx.store.resolve_store(ctx.nadia)


def test_two_domains_sharing_a_tenant_id_still_get_separate_stores(ctx):
    """A caller-supplied tenant_id must not be able to address another store.

    tenant_id arrives from a form when a domain is created, so it is not safe to
    key a store path on. The path is keyed on the server-generated domain id
    instead, and this is the case that proves it.
    """
    clash = ctx.repo.create_domain(
        "clash.test", tenant_id=ctx.domain.tenant_id, client_id="client-a"
    )
    intruder = ctx.repo.create_account(
        clash.domain_id,
        "intruder",
        role_id="owner",
        password_hash=hash_password("your-password"),
    )
    ctx.store.record_org(ctx.nadia, kind="policy", nature="user_claim", body={"rule": "private"})
    assert ctx.store.resolve_org_store(intruder) != ctx.store.resolve_org_store(ctx.nadia)
    assert ctx.store.read_org(intruder) == []


# --- isolation ---------------------------------------------------------------
def test_a_record_written_by_one_account_never_appears_in_another_store(ctx):
    ctx.store.record(
        ctx.nadia, kind="decision", nature="simulated_event", body={"text": "nadia only"}
    )
    assert len(ctx.store.read(ctx.nadia)) == 1
    assert ctx.store.read(ctx.rami) == []


def test_an_account_in_another_tenant_sees_nothing(ctx):
    ctx.store.record(ctx.nadia, kind="decision", nature="simulated_event", body={})
    assert ctx.store.read(ctx.outsider) == []


def test_the_org_store_is_shared_between_accounts_of_one_tenant(ctx):
    ctx.store.record_org(ctx.nadia, kind="policy", nature="user_claim", body={"rule": "shared"})
    nadia_org = ctx.store.read_org(ctx.nadia)
    rami_org = ctx.store.read_org(ctx.rami)
    assert len(nadia_org) == 1
    assert len(rami_org) == 1
    assert nadia_org[0].record_id == rami_org[0].record_id
    # and it is not the same thing as either account's own store
    assert ctx.store.read(ctx.nadia) == []


# --- provenance --------------------------------------------------------------
def test_a_record_carries_its_full_provenance(ctx):
    record = ctx.store.record(
        ctx.nadia,
        kind="decision",
        nature="verified_fact",
        body={"text": "x"},
        evidence_refs=["ev-1"],
        correlation_id="corr-9",
    )
    assert record.tenant_id == ctx.nadia.tenant_id
    assert record.actor == ctx.nadia.account_id
    assert record.provenance["correlation_id"] == "corr-9"
    assert record.provenance["basis"] == "account_memory"
    assert record.provenance["sources"] == ["ev-1"]
    assert record.data_mode == "simulated_realistic"


def test_an_unknown_kind_is_rejected(ctx):
    with pytest.raises(ValueError):
        ctx.store.record(ctx.nadia, kind="not_a_kind", nature="simulated_event", body={})


# --- the index ---------------------------------------------------------------
def test_the_index_tracks_the_ledger(ctx):
    ctx.store.record(ctx.nadia, kind="decision", nature="simulated_event", body={})
    ctx.store.record(ctx.nadia, kind="outcome", nature="simulated_event", body={})
    rows = [r for r in db.list_stores(ctx.conn, ctx.nadia.tenant_id) if r["kind"] == "account"]
    assert len(rows) == 1
    assert rows[0]["record_count"] == 2
    assert rows[0]["chain_head"]
    assert rows[0]["path"] == ctx.store.resolve_store(ctx.nadia)


def test_the_org_store_is_indexed_separately(ctx):
    ctx.store.record(ctx.nadia, kind="decision", nature="simulated_event", body={})
    ctx.store.record_org(ctx.nadia, kind="policy", nature="user_claim", body={})
    rows = db.list_stores(ctx.conn, ctx.nadia.tenant_id)
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["account", "org"]
    org_row = next(r for r in rows if r["kind"] == "org")
    assert org_row["account_id"] is None


# --- chain integrity ---------------------------------------------------------
def test_verify_chain_passes_on_a_fresh_store(ctx):
    ctx.store.record(ctx.nadia, kind="decision", nature="simulated_event", body={})
    ok, detail = ctx.store.verify_chain(ctx.nadia)
    assert ok is True
    assert detail == "chain intact"
    ok_org, _ = ctx.store.verify_org_chain(ctx.nadia)
    assert ok_org is True


def test_a_tampered_line_fails_verification(ctx):
    ctx.store.record(ctx.nadia, kind="decision", nature="simulated_event", body={"text": "x"})
    path = ctx.store.resolve_store(ctx.nadia)
    lines = open(path, encoding="utf-8").read().splitlines()
    envelope = json.loads(lines[0])
    envelope["record"]["body"] = {"tampered": True}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(envelope) + "\n")
        for line in lines[1:]:
            fh.write(line + "\n")
    fresh = AccountMemoryStore(conn=ctx.conn, memory_root=ctx.memory_root)
    ok, _ = fresh.verify_chain(ctx.nadia)
    assert ok is False


def test_a_record_survives_a_reopen(ctx):
    ctx.store.record(ctx.nadia, kind="decision", nature="simulated_event", body={"text": "kept"})
    fresh = AccountMemoryStore(conn=ctx.conn, memory_root=ctx.memory_root)
    records = fresh.read(ctx.nadia)
    assert len(records) == 1
    assert records[0].body["text"] == "kept"
    assert fresh.read(ctx.rami) == []
