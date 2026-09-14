"""Document versions and the knowledge base tests (P3.2).

Service-level tests prove the P3.2 invariants: a restore appends a new
version whose content equals the old one (it never rewrites history), an
employee cannot set doc_type to sop or policy, and a version snapshot is
immutable once written. HTTP tests drive the mounted docs router through
TestClient for the versions API, the restore flow, the KB screen and its
type filter, CSRF, and cross-tenant isolation.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.errors import NotFoundError, PermissionDenied
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


def _four_version_document(service, account):
    """A document with four snapshots whose live blocks have drifted away.

    Returns (document, version_two_snapshot, snapshot_strings) where
    snapshot_strings maps version_no to the raw JSON text.
    """
    document = service.create_document(account, "Versions")
    a = service.insert_block(account, document.document_id, "A")
    b = service.insert_block(account, document.document_id, "B")
    c = service.insert_block(account, document.document_id, "C")
    v1 = service.snapshot_version(account, document.document_id)
    service.delete_block(account, document.document_id, b.block_id)
    v2 = service.snapshot_version(account, document.document_id)
    service.insert_block(account, document.document_id, "D")
    service.snapshot_version(account, document.document_id)
    service.update_block(account, document.document_id, c.block_id, "C2")
    v4 = service.snapshot_version(account, document.document_id)
    snapshots = {
        v1.version_no: v1.snapshot,
        v2.version_no: v2.snapshot,
        v4.version_no: v4.snapshot,
    }
    return document, v2, snapshots


# --- service: the required P3.2 invariants ------------------------------------


def test_restoring_version_2_of_four_produces_version_5_with_its_content(ctx) -> None:
    document, v2, _ = _four_version_document(ctx.service, ctx.amira)
    restored = ctx.service.restore_version(ctx.amira, document.document_id, v2.version_no)
    assert restored.version_no == 5
    blocks = ctx.service.list_blocks(ctx.amira, document.document_id)
    assert [block.content for block in blocks] == ["A", "C"]
    versions = ctx.service.list_versions(ctx.amira, document.document_id)
    assert sorted(version.version_no for version in versions) == [1, 2, 3, 4, 5]
    restored_cnt = _node_rows(ctx.conn, "version", document.document_id)
    assert '"restored_from": 2, "block_count": 2}' in restored_cnt[-1]["body"]


def test_restore_appends_and_never_rewrites_the_old_version(ctx) -> None:
    document, v2, snapshots = _four_version_document(ctx.service, ctx.amira)
    before = _node_rows(ctx.conn, "version", document.document_id)
    ctx.service.restore_version(ctx.amira, document.document_id, v2.version_no)
    after = _node_rows(ctx.conn, "version", document.document_id)
    assert len(after) == len(before) + 1
    row = ctx.conn.execute(
        "SELECT snapshot FROM document_versions WHERE document_id = ? AND version_no = ?",
        (document.document_id, v2.version_no),
    ).fetchone()
    assert row["snapshot"] == snapshots[v2.version_no]


def test_a_version_snapshot_is_immutable(ctx) -> None:
    document, v2, snapshots = _four_version_document(ctx.service, ctx.amira)
    ctx.service.restore_version(ctx.amira, document.document_id, v2.version_no)
    row = ctx.conn.execute(
        "SELECT snapshot FROM document_versions WHERE document_id = ? AND version_no = ?",
        (document.document_id, 2),
    ).fetchone()
    assert row["snapshot"] == snapshots[2]
    rows = ctx.conn.execute(
        "SELECT COUNT(*) AS n FROM document_versions WHERE document_id = ?",
        (document.document_id,),
    ).fetchone()
    assert rows["n"] == 5


def test_an_employee_cannot_set_doc_type_to_policy_or_sop(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Employee Note")
    for forbidden in ("policy", "sop"):
        with pytest.raises(PermissionDenied):
            ctx.service.create_document(ctx.amira, "Employee Publish", doc_type=forbidden)
        with pytest.raises(PermissionDenied):
            ctx.service.set_doc_type(ctx.amira, document.document_id, forbidden)


def test_a_manager_can_publish_sop_and_policy(ctx) -> None:
    document = ctx.service.create_document(ctx.layla, "Sop Draft")
    published = ctx.service.set_doc_type(ctx.layla, document.document_id, "sop")
    assert published.doc_type == "sop"
    created = ctx.service.create_document(ctx.layla, "Policy Draft", doc_type="policy")
    assert created.doc_type == "policy"
    nodes = _node_rows(ctx.conn, "document", document.document_id)
    assert '"doc_type": "sop"}' in nodes[-1]["body"]


def test_unknown_doc_type_is_rejected(ctx) -> None:
    with pytest.raises(ValueError):
        ctx.service.create_document(ctx.amira, "X", doc_type="manual")


# --- service: visibility ------------------------------------------------------


def test_a_note_is_invisible_to_a_peer_employee_but_visible_to_a_manager(ctx) -> None:
    note = ctx.service.create_document(ctx.amira, "Private Note")
    with pytest.raises(NotFoundError):
        ctx.service.get_document(ctx.omar, note.document_id)
    assert ctx.service.list_documents(ctx.omar, {}) == []
    assert ctx.service.get_document(ctx.layla, note.document_id).title == "Private Note"
    titles = [doc.title for doc in ctx.service.list_documents(ctx.layla, {})]
    assert "Private Note" in titles


def test_sop_kb_and_policy_are_visible_to_everyone_in_the_tenant(ctx) -> None:
    sop = ctx.service.create_document(ctx.layla, "Room Booking SOP", doc_type="sop")
    kb = ctx.service.create_document(ctx.layla, "Fee FAQ", doc_type="kb")
    policy = ctx.service.create_document(ctx.layla, "Attendance Policy", doc_type="policy")
    assert ctx.service.get_document(ctx.omar, sop.document_id).title == "Room Booking SOP"
    assert ctx.service.get_document(ctx.omar, kb.document_id).title == "Fee FAQ"
    assert ctx.service.get_document(ctx.omar, policy.document_id).title == "Attendance Policy"
    titles = [doc.title for doc in ctx.service.list_documents(ctx.omar, {})]
    assert {"Room Booking SOP", "Fee FAQ", "Attendance Policy"}.issubset(set(titles))


def test_kb_list_contains_only_sop_and_kb(ctx) -> None:
    ctx.service.create_document(ctx.layla, "Onboarding SOP", doc_type="sop")
    ctx.service.create_document(ctx.layla, "Billing FAQ", doc_type="kb")
    ctx.service.create_document(ctx.layla, "Policy Only", doc_type="policy")
    ctx.service.create_document(ctx.layla, "Private Note")
    docs = ctx.service.list_documents(ctx.omar, {"doc_types": ("sop", "kb")})
    assert sorted(doc.title for doc in docs) == ["Billing FAQ", "Onboarding SOP"]


def test_a_foreign_version_is_not_found(ctx) -> None:
    document = ctx.service.create_document(ctx.ghada, "Foreign")
    version = ctx.service.snapshot_version(ctx.ghada, document.document_id)
    with pytest.raises(NotFoundError):
        ctx.service.get_version(ctx.amira, version.version_id)
    with pytest.raises(NotFoundError):
        ctx.service.list_versions(ctx.amira, document.document_id)
    with pytest.raises(NotFoundError):
        ctx.service.restore_version(ctx.amira, document.document_id, version.version_no)


# --- HTTP: the versions API ---------------------------------------------------


def test_snapshot_api_returns_201_and_one_version_node(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "Snap")
    ctx.service.insert_block(ctx.amira, document.document_id, "one block")
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions",
        cookies=cookies,
        headers=csrf,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["version_no"] == 1
    assert payload["document_id"] == document.document_id
    nodes = _node_rows(ctx.conn, "version", document.document_id)
    assert len(nodes) == 1
    assert nodes[0]["correlation_id"].startswith("doc-")


def test_snapshot_api_requires_csrf_and_docs_write(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "Snap No Csrf")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.post(f"/app/api/documents/{document.document_id}/versions", cookies=cookies)
    assert response.status_code == 403


def test_snapshot_api_is_404_for_a_foreign_document(ctx, client) -> None:
    document = ctx.service.create_document(ctx.ghada, "Foreign Snap")
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions",
        cookies=cookies,
        headers=csrf,
    )
    assert response.status_code == 404


def test_list_versions_api_returns_newest_first(ctx, client) -> None:
    document, _, _ = _four_version_document(ctx.service, ctx.amira)
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/api/documents/{document.document_id}/versions", cookies=cookies)
    assert response.status_code == 200
    versions = response.json()["versions"]
    assert [version["version_no"] for version in versions] == [4, 3, 2, 1]
    assert versions[0]["snapshot"]  # the snapshot payload is preserved


def test_list_versions_api_is_404_for_a_foreign_document(ctx, client) -> None:
    document = ctx.service.create_document(ctx.ghada, "Foreign V")
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/api/documents/{document.document_id}/versions", cookies=cookies)
    assert response.status_code == 404


def test_restore_api_appends_and_reverts_live_blocks(ctx, client) -> None:
    document, v2, _ = _four_version_document(ctx.service, ctx.amira)
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions/{v2.version_no}/restore",
        cookies=cookies,
        headers=csrf,
    )
    assert response.status_code == 201
    assert response.json()["version_no"] == 5
    blocks = ctx.service.list_blocks(ctx.amira, document.document_id)
    assert [block.content for block in blocks] == ["A", "C"]


def test_restore_api_requires_csrf(ctx, client) -> None:
    document, v2, _ = _four_version_document(ctx.service, ctx.amira)
    cookies, _ = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions/{v2.version_no}/restore",
        cookies=cookies,
    )
    assert response.status_code == 403


def test_restore_api_rejects_a_bad_version_number_and_missing_version(ctx, client) -> None:
    document, _, _ = _four_version_document(ctx.service, ctx.amira)
    cookies, csrf = _login(ctx, ctx.amira)
    bad = client.post(
        f"/app/api/documents/{document.document_id}/versions/nope/restore",
        cookies=cookies,
        headers=csrf,
    )
    assert bad.status_code == 400
    missing = client.post(
        f"/app/api/documents/{document.document_id}/versions/99/restore",
        cookies=cookies,
        headers=csrf,
    )
    assert missing.status_code == 404


def test_restore_api_is_404_for_a_foreign_document(ctx, client) -> None:
    document = ctx.service.create_document(ctx.ghada, "Foreign Restore")
    ctx.service.insert_block(ctx.ghada, document.document_id, "b")
    version = ctx.service.snapshot_version(ctx.ghada, document.document_id)
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions/{version.version_no}/restore",
        cookies=cookies,
        headers=csrf,
    )
    assert response.status_code == 404


# --- HTTP: the HTMX fragments ------------------------------------------------


def test_snapshot_htmx_returns_the_doc_page_fragment(ctx, client) -> None:
    document = ctx.service.create_document(ctx.amira, "HX Snap")
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions",
        cookies=cookies,
        headers={**csrf, "HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="doc-page"' in response.text
    assert 'id="doc-versions"' in response.text
    assert "Version 1" in response.text


def test_restore_htmx_returns_reverted_blocks_and_the_new_version(ctx, client) -> None:
    document, v2, _ = _four_version_document(ctx.service, ctx.amira)
    cookies, csrf = _login(ctx, ctx.amira)
    response = client.post(
        f"/app/api/documents/{document.document_id}/versions/{v2.version_no}/restore",
        cookies=cookies,
        headers={**csrf, "HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'id="doc-page"' in response.text
    assert "A" in response.text
    assert "C" in response.text
    assert "Version 5" in response.text


def test_editor_screen_shows_the_version_history(ctx, client) -> None:
    document, _, _ = _four_version_document(ctx.service, ctx.amira)
    cookies, _ = _login(ctx, ctx.amira)
    response = client.get(f"/app/docs/{document.document_id}", cookies=cookies)
    assert response.status_code == 200
    assert 'id="doc-versions"' in response.text
    assert "Version 4" in response.text
    assert "Snapshot now" in response.text


# --- HTTP: the knowledge base -------------------------------------------------


def _seed_kb(ctx):
    ctx.service.create_document(ctx.layla, "Facility SOP", doc_type="sop")
    ctx.service.create_document(ctx.layla, "Billing SOP", doc_type="sop")
    ctx.service.create_document(ctx.layla, "Fee FAQ", doc_type="kb")
    ctx.service.create_document(ctx.layla, "Private Note")


def test_kb_screen_groups_sops_first_and_shows_search(ctx, client) -> None:
    _seed_kb(ctx)
    cookies, _ = _login(ctx, ctx.omar)
    response = client.get("/app/kb", cookies=cookies)
    assert response.status_code == 200
    text = response.text
    assert "Facility SOP" in text and "Billing SOP" in text
    assert "Fee FAQ" in text
    assert "Private Note" not in text
    assert 'class="doc-search"' in response.text
    assert text.index('kb-group__title">SOPs') < text.index('kb-group__title">Knowledge base')


def test_kb_screen_type_filter(ctx, client) -> None:
    _seed_kb(ctx)
    cookies, _ = _login(ctx, ctx.omar)
    sop = client.get("/app/kb?type=sop", cookies=cookies)
    assert "Facility SOP" in sop.text
    assert "Fee FAQ" not in sop.text
    kb_only = client.get("/app/kb?type=kb", cookies=cookies)
    assert "Fee FAQ" in kb_only.text
    assert "Facility SOP" not in kb_only.text


def test_kb_screen_search_filters_titles(ctx, client) -> None:
    _seed_kb(ctx)
    cookies, _ = _login(ctx, ctx.omar)
    response = client.get("/app/kb?q=billing", cookies=cookies)
    assert "Billing SOP" in response.text
    assert "Facility SOP" not in response.text
    assert "Fee FAQ" not in response.text


def test_kb_screen_requires_auth(client) -> None:
    response = client.get("/app/kb")
    assert response.status_code == 401
