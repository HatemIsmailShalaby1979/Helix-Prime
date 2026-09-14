"""Document isolation tests (P3.4 close-out).

Service-level tests prove the P3 isolation invariants in one place: a document
lives inside exactly one tenant and is invisible in any other, and a private
note is invisible to a peer employee but visible to its owner and to a manager.
HTTP tests drive the mounted docs router through TestClient so the same rules
hold at the wire, where a foreign read is a plain 404 with no row leakage.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import NotFoundError
from helix_codex_app.modules.docs.service import DocsService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SESSION_COOKIE, SessionStore


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    omar = repo.create_account(
        domain_a.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    layla = repo.create_account(
        domain_a.domain_id, "layla", role_id="manager", password_hash=hash_password("x")
    )
    ghada = repo.create_account(
        domain_b.domain_id, "ghada", role_id="employee", password_hash=hash_password("x")
    )
    settings = AppSettings(db_path=db_path, cookie_secure=False)
    store = SessionStore(conn, settings)
    service = DocsService(conn)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain_a=domain_a,
        domain_b=domain_b,
        amira=amira,
        omar=omar,
        layla=layla,
        ghada=ghada,
        settings=settings,
        store=store,
        service=service,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as test_client:
        yield test_client


def _login(ctx, account) -> tuple[dict, dict]:
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


# --- service: tenant isolation -------------------------------------------------


def test_a_document_in_tenant_a_is_invisible_in_tenant_b(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Tenant A Doc")
    with pytest.raises(NotFoundError):
        ctx.service.get_document(ctx.ghada, document.document_id)
    assert ctx.service.list_documents(ctx.ghada, {}) == []
    titles = [doc.title for doc in ctx.service.list_documents(ctx.amira, {})]
    assert titles == ["Tenant A Doc"]


def test_a_published_kb_in_tenant_a_is_invisible_in_tenant_b(ctx) -> None:
    kb = ctx.service.create_document(ctx.amira, "Fee FAQ", doc_type="kb")
    with pytest.raises(NotFoundError):
        ctx.service.get_document(ctx.ghada, kb.document_id)
    assert ctx.service.list_documents(ctx.ghada, {}) == []


def test_a_foreign_blocks_and_versions_are_invisible(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Foreign Blocks")
    ctx.service.insert_block(ctx.amira, document.document_id, "only here")
    ctx.service.snapshot_version(ctx.amira, document.document_id)
    with pytest.raises(NotFoundError):
        ctx.service.list_blocks(ctx.ghada, document.document_id)
    with pytest.raises(NotFoundError):
        ctx.service.insert_block(ctx.ghada, document.document_id, "sneak in")
    with pytest.raises(NotFoundError):
        ctx.service.snapshot_version(ctx.ghada, document.document_id)


def test_no_governed_writes_are_recorded_for_a_foreign_document(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "No Foreign Writes")
    node_count = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM nodes WHERE tenant_id = ?", ("tenant-b",)
    ).fetchone()[0]
    with pytest.raises(NotFoundError):
        ctx.service.insert_block(ctx.ghada, document.document_id, "block")
    with pytest.raises(NotFoundError):
        ctx.service.restore_version(ctx.ghada, document.document_id, 1)
    assert node_count == 0


# --- service: note visibility --------------------------------------------------


def test_a_private_note_is_invisible_to_a_peer_employee(ctx) -> None:
    note = ctx.service.create_document(ctx.amira, "Private Note")
    with pytest.raises(NotFoundError):
        ctx.service.get_document(ctx.omar, note.document_id)
    assert ctx.service.list_documents(ctx.omar, {}) == []


def test_a_private_note_is_visible_to_its_owner_and_a_manager(ctx) -> None:
    note = ctx.service.create_document(ctx.amira, "Private Note")
    assert ctx.service.get_document(ctx.amira, note.document_id).title == "Private Note"
    assert ctx.service.get_document(ctx.layla, note.document_id).title == "Private Note"
    manager_titles = [doc.title for doc in ctx.service.list_documents(ctx.layla, {})]
    assert manager_titles == ["Private Note"]


def test_a_peer_employee_cannot_edit_a_private_note(ctx) -> None:
    note = ctx.service.create_document(ctx.amira, "Private Note")
    ctx.service.insert_block(ctx.amira, note.document_id, "owned by amira")
    with pytest.raises(NotFoundError):
        ctx.service.insert_block(ctx.omar, note.document_id, "peer write")
    with pytest.raises(NotFoundError):
        ctx.service.snapshot_version(ctx.omar, note.document_id)
    blocks = ctx.service.list_blocks(ctx.amira, note.document_id)
    assert [block.content for block in blocks] == ["owned by amira"]


# --- HTTP: the same rules at the wire -------------------------------------------


def test_editor_screen_is_404_across_tenants(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "Tenant A Doc")
    client_ghada_cookies, _ = _login(ctx, ctx.ghada)
    response = client.get(f"/app/docs/{document.document_id}", cookies=client_ghada_cookies)
    assert response.status_code == 404


def test_editor_screen_is_404_for_a_peer_employee_note(ctx, client) -> None:
    note = ctx.service.create_document(ctx.amira, "Private Note")
    client_omar_cookies, _ = _login(ctx, ctx.omar)
    response = client.get(f"/app/docs/{note.document_id}", cookies=client_omar_cookies)
    assert response.status_code == 404


def test_list_screen_hides_foreign_documents_and_peer_notes(ctx, client) -> None:
    ctx.service.create_document(ctx.amira, "Tenant A Doc")
    ghada_cookies, _ = _login(ctx, ctx.ghada)
    omar_cookies, _ = _login(ctx, ctx.omar)
    amira_cookies, _ = _login(ctx, ctx.amira)
    foreign = client.get("/app/docs", cookies=ghada_cookies)
    assert foreign.status_code == 200
    assert "No documents yet" in foreign.text
    peer = client.get("/app/docs", cookies=omar_cookies)
    assert peer.status_code == 200
    assert "No documents yet" in peer.text
    owner = client.get("/app/docs", cookies=amira_cookies)
    assert owner.status_code == 200
    assert "Tenant A Doc" in owner.text
