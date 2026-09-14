"""Documents and the block editor tests (P3.1).

Service-level tests prove the P3.1 invariants: one governed node per write,
in-place block edits, blocks kept in order through a reorder, and a block
that belongs to another document refused through the wrong route. HTTP tests
drive the mounted docs router through TestClient for the screens, the JSON
contract, the HTMX fragment path, CSRF, and cross-tenant isolation (a
foreign document is a plain 404 everywhere, never a clue).
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
    """Return (cookies, headers) for one account: cookie + CSRF header."""
    token, _session = ctx.store.issue_session(account)
    session = ctx.store.verify(token)
    assert session is not None
    return {SESSION_COOKIE: token}, {"X-CSRF-Token": session.csrf_token}


def _node_rows(conn, kind: str, document_id: str) -> list:
    rows = conn.execute(
        "SELECT n.node_id, n.kind, n.body, n.correlation_id FROM nodes n WHERE n.kind = ?",
        (kind,),
    ).fetchall()
    return [
        {
            "node_id": r["node_id"],
            "kind": r["kind"],
            "body": r["body"],
            "correlation_id": r["correlation_id"],
        }
        for r in rows
        if r["body"] and document_id in r["body"]
    ]


# --- service: the required P3.1 invariants ----------------------------------


def test_create_document_writes_exactly_one_node(ctx) -> None:
    before = _node_rows(ctx.conn, "document", "doc")
    document = ctx.service.create_document(ctx.amira, "Policy Handbook")
    after = _node_rows(ctx.conn, "document", document.document_id)
    assert len(after) == len(before) + 1
    node = after[-1]
    assert node["correlation_id"].startswith("doc-")
    assert document.title == "Policy Handbook"
    assert document.tenant_id == "tenant-a"
    assert document.status == "active"
    assert document.current_version == 1


def test_edit_block_updates_row_and_writes_one_node(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Onboarding")
    block = ctx.service.insert_block(ctx.amira, document.document_id, "draft")
    before = _node_rows(ctx.conn, "block", block.block_id)
    updated = ctx.service.update_block(ctx.amira, document.document_id, block.block_id, "final")
    after = _node_rows(ctx.conn, "block", block.block_id)
    assert updated.content == "final"
    assert updated.block_id == block.block_id
    assert len(after) == len(before) + 1
    assert after[-1]["correlation_id"].startswith("doc-")
    row = ctx.conn.execute(
        "SELECT content, updated_by FROM doc_blocks WHERE block_id = ?", (block.block_id,)
    ).fetchone()
    assert row["content"] == "final"
    assert row["updated_by"] == ctx.amira.account_id


def test_blocks_keep_their_order_after_a_reorder(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Runbook")
    a = ctx.service.insert_block(ctx.amira, document.document_id, "first")
    b = ctx.service.insert_block(ctx.amira, document.document_id, "second")
    c = ctx.service.insert_block(ctx.amira, document.document_id, "third")
    reordered = ctx.service.reorder_blocks(
        ctx.amira, document.document_id, [c.block_id, a.block_id, b.block_id]
    )
    assert [block.block_id for block in reordered] == [c.block_id, a.block_id, b.block_id]
    rows = ctx.conn.execute(
        "SELECT block_id, ordinal FROM doc_blocks WHERE document_id = ? ORDER BY ordinal",
        (document.document_id,),
    ).fetchall()
    assert [row["block_id"] for row in rows] == [c.block_id, a.block_id, b.block_id]
    assert [row["ordinal"] for row in rows] == [0, 1, 2]


def test_a_block_of_another_document_cannot_be_edited_through_this_document(ctx) -> None:
    first = ctx.service.create_document(ctx.amira, "First")
    second = ctx.service.create_document(ctx.amira, "Second")
    block = ctx.service.insert_block(ctx.amira, first.document_id, "belongs to first")
    blocks_in_second = ctx.service.list_blocks(ctx.amira, second.document_id)
    assert blocks_in_second == []
    with pytest.raises(NotFoundError):
        ctx.service.update_block(ctx.amira, second.document_id, block.block_id, "no")


# --- service: rules around content, order, and archive ------------------------


def test_insert_block_appends_and_delete_renumbers(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Notes")
    a = ctx.service.insert_block(ctx.amira, document.document_id, "a")
    b = ctx.service.insert_block(ctx.amira, document.document_id, "b")
    c = ctx.service.insert_block(ctx.amira, document.document_id, "c")
    assert ctx.service.delete_block(ctx.amira, document.document_id, b.block_id) is True
    remaining = ctx.service.list_blocks(ctx.amira, document.document_id)
    assert [block.block_id for block in remaining] == [a.block_id, c.block_id]
    assert [block.ordinal for block in remaining] == [0, 1]
    assert ctx.service.delete_block(ctx.amira, document.document_id, b.block_id) is False


def test_reorder_refuses_a_partial_list(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Agenda")
    a = ctx.service.insert_block(ctx.amira, document.document_id, "a")
    b = ctx.service.insert_block(ctx.amira, document.document_id, "b")
    with pytest.raises(ValueError):
        ctx.service.reorder_blocks(ctx.amira, document.document_id, [a.block_id])
    assert "a" not in str(
        ctx.conn.execute(
            "SELECT COUNT(*) AS n FROM doc_blocks WHERE document_id = ?", (document.document_id,)
        ).fetchone()["n"]
    )


def test_archive_moves_document_out_of_the_active_list(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Season Plan")
    archived = ctx.service.archive_document(ctx.amira, document.document_id)
    assert archived.status == "archived"
    active = ctx.service.list_documents(ctx.amira, {})
    assert document.document_id not in [doc.document_id for doc in active]
    archived_list = ctx.service.list_documents(ctx.amira, {"status": "archived"})
    assert document.document_id in [doc.document_id for doc in archived_list]


def test_list_documents_filters_by_search_term(ctx) -> None:
    ctx.service.create_document(ctx.amira, "Attendance Policy")
    ctx.service.create_document(ctx.amira, "Fee Schedule")
    hits = ctx.service.list_documents(ctx.amira, {"q": "attendance"})
    assert [doc.title for doc in hits] == ["Attendance Policy"]


def test_blank_title_and_oversized_block_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_document(ctx.amira, "   ")
    document = ctx.service.create_document(ctx.amira, "Limits")
    with pytest.raises(ValueError):
        ctx.service.update_block(ctx.amira, document.document_id, "does-not-exist", "x" * 20001)


# --- isolation: a foreign document is a plain 404 -----------------------------


def test_foreign_tenant_document_is_not_found(ctx) -> None:
    document = ctx.service.create_document(ctx.ghada, "Tenant B Doc")
    with pytest.raises(NotFoundError):
        ctx.service.get_document(ctx.amira, document.document_id)
    assert ctx.service.list_documents(ctx.amira, {}) == []
    block = ctx.service.insert_block(ctx.ghada, document.document_id, "b only")
    with pytest.raises(NotFoundError):
        ctx.service.update_block(ctx.amira, document.document_id, block.block_id, "no")


def test_gate_database_rows_are_isolated(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "A Rows")
    ctx.service.insert_block(ctx.amira, document.document_id, "a")
    rows_b = ctx.conn.execute(
        "SELECT document_id FROM documents WHERE tenant_id = ?", ("tenant-b",)
    ).fetchall()
    blocks_b = ctx.conn.execute(
        "SELECT block_id FROM doc_blocks WHERE document_id = ?", (document.document_id,)
    ).fetchall()
    assert rows_b == []
    assert len(blocks_b) == 1


# --- HTTP: screens -----------------------------------------------------------


def test_docs_list_screen_renders_empty_state_and_create_form(ctx, client) -> None:
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get("/app/docs", cookies=cookies)
    assert response.status_code == 200
    assert "Documents" in response.text
    assert "No documents yet" in response.text
    assert 'hx-post="/app/api/documents"' in response.text


def test_docs_list_screen_requires_auth(client) -> None:
    response = client.get("/app/docs")
    assert response.status_code == 401


def test_editor_screen_renders_document_and_blocks(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "Syllabus")
    ctx.service.insert_block(ctx.amira, document.document_id, "Block one")
    ctx.service.insert_block(ctx.amira, document.document_id, "Block two")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/docs/{document.document_id}", cookies=cookies)
    assert response.status_code == 200
    assert "Syllabus" in response.text
    assert "Block one" in response.text
    assert "Block two" in response.text
    assert "contenteditable" in response.text
    assert f"/app/api/documents/{document.document_id}/blocks/" in response.text


def test_editor_screen_is_404_for_a_foreign_document(ctx, client) -> None:
    document = ctx.service.create_document(ctx.ghada, "Foreign")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/docs/{document.document_id}", cookies=cookies)
    assert response.status_code == 404


# --- HTTP: the JSON API ------------------------------------------------------


def test_create_document_api_201_and_one_node(ctx, client) -> None:
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/documents",
        cookies=cookies,
        headers=csrf,
        json={"title": "Created over HTTP"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Created over HTTP"
    assert _node_rows(ctx.conn, "document", payload["document_id"]) != []


def test_create_document_api_requires_csrf_and_permission(ctx, client) -> None:
    cookies, _ = _login(ctx, ctx.amira)
    no_csrf = client.post("/app/api/documents", cookies=cookies, json={"title": "x"})
    assert no_csrf.status_code == 403


def test_create_document_api_rejects_a_blank_title(ctx, client) -> None:
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/documents", cookies=cookies, headers=csrf, json={"title": "  "}
    )
    assert response.status_code == 400


def test_create_document_htmx_returns_the_list_fragment(ctx, client) -> None:
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        "/app/api/documents",
        cookies=cookies,
        headers={**csrf, "HX-Request": "true"},
        data={"title": "From the shell"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="docs-section"' in response.text
    assert "From the shell" in response.text


def test_get_document_api_returns_document_and_blocks(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "One Two Three")
    ctx.service.insert_block(ctx.amira, document.document_id, "first")
    ctx.service.insert_block(ctx.amira, document.document_id, "second")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/api/documents/{document.document_id}", cookies=cookies)
    assert response.status_code == 200
    payload = response.json()
    assert payload["document"]["title"] == "One Two Three"
    assert [block["content"] for block in payload["blocks"]] == ["first", "second"]


def test_get_document_api_404_for_foreign_tenant(ctx, client) -> None:
    document = ctx.service.create_document(ctx.ghada, "Foreign")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/api/documents/{document.document_id}", cookies=cookies)
    assert response.status_code == 404


# --- HTTP: block editing -----------------------------------------------------


def test_put_block_updates_and_writes_one_node(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "Drafting")
    block = ctx.service.insert_block(ctx.amira, document.document_id, "old")
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.put(
        f"/app/api/documents/{document.document_id}/blocks/{block.block_id}",
        cookies=cookies,
        headers=csrf,
        json={"content": "new"},
    )
    assert response.status_code == 200
    assert response.json()["content"] == "new"
    nodes = _node_rows(ctx.conn, "block", block.block_id)
    assert len(nodes) == 2  # insert + update
    assert nodes[-1]["correlation_id"].startswith("doc-")


def test_put_block_rejects_a_block_from_another_document(ctx, client) -> None:
    first = ctx.service.create_document(ctx.amira, "First")
    second = ctx.service.create_document(ctx.amira, "Second")
    block = ctx.service.insert_block(ctx.amira, first.document_id, "belongs to first")
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.put(
        f"/app/api/documents/{second.document_id}/blocks/{block.block_id}",
        cookies=cookies,
        headers=csrf,
        json={"content": "tamper"},
    )
    assert response.status_code == 404
    row = ctx.conn.execute(
        "SELECT content FROM doc_blocks WHERE block_id = ?", (block.block_id,)
    ).fetchone()
    assert row["content"] == "belongs to first"


def test_put_block_requires_csrf(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "No Csrf")
    block = ctx.service.insert_block(ctx.amira, document.document_id, "x")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.put(
        f"/app/api/documents/{document.document_id}/blocks/{block.block_id}",
        cookies=cookies,
        json={"content": "y"},
    )
    assert response.status_code == 403


def test_post_block_appends_and_htmx_returns_the_editor_fragment(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "Sprints")
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/blocks",
        cookies=cookies,
        headers={**csrf, "HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="doc-editor"' in response.text
    blocks = ctx.service.list_blocks(ctx.amira, document.document_id)
    assert len(blocks) == 1
    assert blocks[0].content == ""
