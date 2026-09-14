"""Version restore append-only tests (P3.4 close-out).

A restore must append a NEW version row whose bytes equal the restored
snapshot and must NEVER rewrite any prior version row, including the restored
one. These tests prove that invariant at the row level: every original
snapshot keeps its exact bytes through restores, edits, further snapshots, and
chained restores, and each restore records its own governed version node.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.modules.docs.service import DocsService
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password


@pytest.fixture()
def ctx(tmp_path):
    db_path = str(tmp_path / "app.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a", client_id="client-a")
    amira = repo.create_account(
        domain_a.domain_id, "amira", role_id="employee", password_hash=hash_password("x")
    )
    service = DocsService(conn)
    yield SimpleNamespace(
        conn=conn,
        amira=amira,
        service=service,
    )
    db.close(conn)


def _snapshot_text(conn, document_id: str, version_no: int) -> str:
    row = conn.execute(
        "SELECT snapshot FROM document_versions WHERE document_id = ? AND version_no = ?",
        (document_id, version_no),
    ).fetchone()
    assert row is not None
    return row["snapshot"]


def _version_count(conn, document_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM document_versions WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    return row["n"]


def _version_nodes(conn, document_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT node_id, body, correlation_id FROM nodes WHERE kind = 'version' ORDER BY rowid ASC"
    ).fetchall()
    return [dict(row) for row in rows if row["body"] and document_id in row["body"]]


def _block_contents(snapshot: str) -> list[str]:
    return [block["content"] for block in json.loads(snapshot)]


def _four_version_document(ctx) -> tuple[object, dict[int, str]]:
    """A document with four snapshots and their exact original bytes.

    Returns (document, originals) where originals maps each version_no to the
    snapshot JSON string as it was first written — the bytes any later restore
    or edit must never change.
    """
    service = ctx.service
    document = service.create_document(ctx.amira, "Versions")
    a = service.insert_block(ctx.amira, document.document_id, "A")
    b = service.insert_block(ctx.amira, document.document_id, "B")
    c = service.insert_block(ctx.amira, document.document_id, "C")
    service.snapshot_version(ctx.amira, document.document_id)
    service.delete_block(ctx.amira, document.document_id, b.block_id)
    service.snapshot_version(ctx.amira, document.document_id)
    service.insert_block(ctx.amira, document.document_id, "D")
    service.snapshot_version(ctx.amira, document.document_id)
    service.update_block(ctx.amira, document.document_id, c.block_id, "C2")
    service.snapshot_version(ctx.amira, document.document_id)
    originals = {
        version_no: _snapshot_text(ctx.conn, document.document_id, version_no)
        for version_no in range(1, 5)
    }
    return document, originals


# --- append-only invariants ----------------------------------------------------


def test_restore_appends_a_version_and_leaves_the_old_row_untouched(ctx) -> None:
    document, originals = _four_version_document(ctx)
    count_before = _version_count(ctx.conn, document.document_id)
    restored = ctx.service.restore_version(ctx.amira, document.document_id, 2)
    assert restored.version_no == 5
    assert _version_count(ctx.conn, document.document_id) == count_before + 1
    assert _snapshot_text(ctx.conn, document.document_id, 5) == originals[2]
    assert _snapshot_text(ctx.conn, document.document_id, 2) == originals[2]


def test_restore_never_rewrites_any_prior_version(ctx) -> None:
    document, originals = _four_version_document(ctx)
    ctx.service.restore_version(ctx.amira, document.document_id, 2)
    ctx.service.insert_block(ctx.amira, document.document_id, "X")
    ctx.service.snapshot_version(ctx.amira, document.document_id)
    ctx.service.restore_version(ctx.amira, document.document_id, 1)
    for version_no in range(1, 5):
        assert _snapshot_text(ctx.conn, document.document_id, version_no) == originals[version_no]


def test_restoring_twice_appends_two_versions(ctx) -> None:
    document, originals = _four_version_document(ctx)
    count_before = _version_count(ctx.conn, document.document_id)
    ctx.service.restore_version(ctx.amira, document.document_id, 2)
    ctx.service.restore_version(ctx.amira, document.document_id, 2)
    assert _version_count(ctx.conn, document.document_id) == count_before + 2
    assert _snapshot_text(ctx.conn, document.document_id, 5) == originals[2]
    assert _snapshot_text(ctx.conn, document.document_id, 6) == originals[2]


def test_the_live_blocks_match_the_restored_snapshot(ctx) -> None:
    document, originals = _four_version_document(ctx)
    ctx.service.restore_version(ctx.amira, document.document_id, 2)
    blocks = ctx.service.list_blocks(ctx.amira, document.document_id)
    assert [block.content for block in blocks] == ["A", "C"]


def test_a_restored_version_is_itself_restorable(ctx) -> None:
    document, originals = _four_version_document(ctx)
    first = ctx.service.restore_version(ctx.amira, document.document_id, 2)
    second = ctx.service.restore_version(ctx.amira, document.document_id, first.version_no)
    assert second.version_no == 6
    assert _snapshot_text(ctx.conn, document.document_id, second.version_no) == originals[2]
    blocks = ctx.service.list_blocks(ctx.amira, document.document_id)
    assert [block.content for block in blocks] == ["A", "C"]


def test_a_snapshot_taken_after_restore_captures_the_restored_content(ctx) -> None:
    document, originals = _four_version_document(ctx)
    restored = ctx.service.restore_version(ctx.amira, document.document_id, 3)
    ctx.service.snapshot_version(ctx.amira, document.document_id)
    snapshot_after = _snapshot_text(ctx.conn, document.document_id, restored.version_no + 1)
    restored_rows = ctx.service.list_versions(ctx.amira, document.document_id)
    restored_versions = {version.version_no: version for version in restored_rows}
    assert _block_contents(snapshot_after) == _block_contents(
        restored_versions[restored.version_no].snapshot
    )


def test_each_restore_records_its_own_version_node(ctx) -> None:
    document, _ = _four_version_document(ctx)
    before = _version_nodes(ctx.conn, document.document_id)
    ctx.service.restore_version(ctx.amira, document.document_id, 2)
    ctx.service.restore_version(ctx.amira, document.document_id, 5)
    nodes = _version_nodes(ctx.conn, document.document_id)
    assert len(nodes) == len(before) + 2
    restored_rows = [node for node in nodes[-2:] if '"restored_from"' in node["body"]]
    assert len(restored_rows) == 2
