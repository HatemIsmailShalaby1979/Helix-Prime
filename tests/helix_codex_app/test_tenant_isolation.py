"""Tenant isolation tests for the app's identity tables (P1.7).

One domain is one tenant. Every read in the app package must resolve the
domain first and scope by it, so a query issued inside tenant A never
returns a row that belongs to tenant B. These tests build two tenants and
probe the reads the app actually uses: accounts, domains, org units, and
sessions. A foreign tenant's row is not merely hidden from a caller — it is
outside every query the app runs.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.config import AppSettings
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SessionStore

TENANT_TABLES = ("nodes", "conversations", "documents", "tasks", "events", "files")


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    unit_a = repo.create_org_unit(domain_a.domain_id, "Floor A")
    unit_b = repo.create_org_unit(domain_b.domain_id, "Floor B")
    amira = repo.create_account(
        domain_a.domain_id,
        "amira",
        role_id="owner",
        org_unit_id=unit_a.unit_id,
        password_hash=hash_password("your-password"),
    )
    omar = repo.create_account(
        domain_b.domain_id,
        "omar",
        role_id="owner",
        org_unit_id=unit_b.unit_id,
        password_hash=hash_password("your-password"),
    )
    stranger = repo.create_account(
        domain_b.domain_id,
        "ghada",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    token_a, _session = store.issue_session(amira)
    token_b, session_b = store.issue_session(omar)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        unit_a=unit_a,
        unit_b=unit_b,
        amira=amira,
        omar=omar,
        stranger=stranger,
        settings=settings,
        store=store,
        token_a=token_a,
        token_b=token_b,
        session_b=session_b,
    )
    db.close(conn)


def test_account_reads_never_cross_tenants(ctx) -> None:
    listed_a = ctx.repo.list_accounts(ctx.domain_a.domain_id)
    listed_b = ctx.repo.list_accounts(ctx.domain_b.domain_id)
    assert {a.account_id for a in listed_a} == {ctx.amira.account_id}
    assert {a.account_id for a in listed_b} == {
        ctx.omar.account_id,
        ctx.stranger.account_id,
    }
    by_login = ctx.repo.get_account_by_login("b.academy", "amira")
    assert by_login is None
    same_name_other_tenant = ctx.repo.get_account_by_login("b.academy", "omar")
    assert same_name_other_tenant is not None
    assert same_name_other_tenant.tenant_id == "tenant-b"


def test_domain_and_org_unit_reads_stay_scoped(ctx) -> None:
    assert ctx.repo.get_domain_by_name("a.academy").tenant_id == "tenant-a"
    assert ctx.repo.get_domain_by_name("b.academy").tenant_id == "tenant-b"
    units_a = ctx.repo.list_org_units(ctx.domain_a.domain_id)
    units_b = ctx.repo.list_org_units(ctx.domain_b.domain_id)
    assert {u.unit_id for u in units_a} == {ctx.unit_a.unit_id}
    assert {u.unit_id for u in units_b} == {ctx.unit_b.unit_id}
    assert ctx.repo.get_org_unit(ctx.unit_b.unit_id).domain_id == ctx.domain_b.domain_id


def test_sessions_of_tenant_b_do_not_verify_for_tenant_a_accounts(ctx) -> None:
    assert ctx.store.verify(ctx.token_a) is not None
    verified_b = ctx.store.verify(ctx.token_b)
    assert verified_b is not None
    assert verified_b.account_id == ctx.omar.account_id
    row = ctx.conn.execute(
        "SELECT account_id FROM sessions WHERE session_id = ?",
        (ctx.session_b.session_id,),
    ).fetchone()
    assert row["account_id"] == ctx.omar.account_id
    accounts_a = ctx.repo.list_accounts(ctx.domain_a.domain_id)
    assert ctx.session_b.account_id not in {a.account_id for a in accounts_a}


def test_same_username_in_two_tenants_is_two_accounts(ctx) -> None:
    twin = ctx.repo.create_account(
        ctx.domain_b.domain_id,
        "amira",
        role_id="employee",
        password_hash=hash_password("your-password"),
    )
    assert twin.account_id != ctx.amira.account_id
    assert twin.tenant_id == "tenant-b"
    assert ctx.amira.tenant_id == "tenant-a"
    assert ctx.repo.get_account_by_login("a.academy", "amira").account_id == (ctx.amira.account_id)
    assert ctx.repo.get_account_by_login("b.academy", "amira").account_id == (twin.account_id)


def test_record_node_tenant_column_is_isolated(ctx) -> None:
    node_a = db.record_node(
        ctx.conn,
        tenant_id="tenant-a",
        correlation_id="corr-a",
        classification="internal",
        nature="historical_event",
        created_by=ctx.amira.account_id,
        provenance_source="test",
        provenance_data_mode="app_runtime",
        kind="admin",
    )
    node_b = db.record_node(
        ctx.conn,
        tenant_id="tenant-b",
        correlation_id="corr-b",
        classification="internal",
        nature="historical_event",
        created_by=ctx.omar.account_id,
        provenance_source="test",
        provenance_data_mode="app_runtime",
        kind="admin",
    )
    rows = dict(
        ctx.conn.execute("SELECT tenant_id, COUNT(*) AS n FROM nodes GROUP BY tenant_id").fetchall()
    )
    assert rows["tenant-a"] >= 1
    assert rows["tenant-b"] >= 1
    single = ctx.conn.execute("SELECT tenant_id FROM nodes WHERE node_id = ?", (node_a,)).fetchone()
    assert single["tenant_id"] == "tenant-a"
    single_b = ctx.conn.execute(
        "SELECT tenant_id FROM nodes WHERE node_id = ?", (node_b,)
    ).fetchone()
    assert single_b["tenant_id"] == "tenant-b"


def test_every_tenant_carrying_table_declares_tenant_id(ctx) -> None:
    columns = dict((row["name"], row) for row in ctx.conn.execute("PRAGMA table_info(nodes)"))
    assert "tenant_id" in columns
    assert columns["tenant_id"]["notnull"] == 1
    for table in TENANT_TABLES:
        cols = {row["name"] for row in ctx.conn.execute(f"PRAGMA table_info({table})")}
        assert "tenant_id" in cols, table


def test_login_requires_the_own_domain_name(ctx) -> None:
    from helix_codex_app.modules.identity.service import LoginService

    service = LoginService(ctx.conn, ctx.settings)
    ok = service.login("a.academy", "amira", "your-password")
    assert ok.ok is True
    assert ok.account.tenant_id == "tenant-a"
    cross = service.login("b.academy", "amira", "your-password")
    assert cross.ok is False
    assert cross.code == "no_such_account"
