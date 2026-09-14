"""Governed node invariants across every P3 write path (P3.4 close-out).

Each write path in the docs and tasks modules must append exactly one governed
nodes row carrying the full envelope: a non-null tenant_id, a non-empty
correlation_id, a classification from the allowed set, and a provenance
data_mode. Comments land under the task kind, so the comment write is covered
here too. A sweep at the end proves every node the P3 paths produce in one
session passes the envelope — there is no un-enveloped write hiding in a side
branch.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.modules.docs.service import DocsService
from helix_codex_app.modules.tasks.service import TaskService
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
    omar = repo.create_account(
        domain_a.domain_id, "omar", role_id="employee", password_hash=hash_password("x")
    )
    service = DocsService(conn)
    task_service = TaskService(conn)
    yield SimpleNamespace(
        conn=conn,
        amira=amira,
        omar=omar,
        service=service,
        task_service=task_service,
    )
    db.close(conn)


def _watermark(conn) -> int:
    row = conn.execute("SELECT MAX(rowid) AS rowid FROM nodes").fetchone()
    return row["rowid"] or 0


def _new_nodes(conn, after_rowid: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM nodes WHERE rowid > ? ORDER BY rowid ASC", (after_rowid,)
    ).fetchall()
    return [dict(row) for row in rows]


def _kinds(nodes: list[dict]) -> list[str]:
    return [node["kind"] for node in nodes]


def _assert_full_envelope(node: dict, actor) -> None:
    assert node["tenant_id"] == actor.tenant_id
    assert node["correlation_id"] and node["correlation_id"].strip()
    assert node["classification"] in db.CLASSIFICATIONS
    assert node["nature"] and node["nature"].strip()
    assert node["created_by"] == actor.account_id
    assert node["provenance_source"] and node["provenance_source"].strip()
    assert node["provenance_data_mode"] == "app_runtime"
    assert node["kind"] and node["kind"].strip()
    assert node["body"] and node["body"].strip()


def _first_kind(nodes: list[dict], kind: str) -> dict:
    return next(node for node in nodes if node["kind"] == kind)


# --- documents and blocks ------------------------------------------------------


def test_create_document_writes_one_document_node(ctx) -> None:
    before = _watermark(ctx.conn)
    ctx.service.create_document(ctx.amira, "Invariant Doc")
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["document"]
    node = nodes[0]
    _assert_full_envelope(node, ctx.amira)
    assert node["correlation_id"].startswith("doc-")


def test_insert_and_update_block_write_block_nodes(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Blocks")
    before = _watermark(ctx.conn)
    block = ctx.service.insert_block(ctx.amira, document.document_id, "first")
    ctx.service.update_block(ctx.amira, document.document_id, block.block_id, "first edit")
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["block", "block"]
    for node in nodes:
        _assert_full_envelope(node, ctx.amira)
        assert node["correlation_id"].startswith("doc-")


def test_delete_block_records_a_block_node(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Delete")
    block = ctx.service.insert_block(ctx.amira, document.document_id, "gone")
    before = _watermark(ctx.conn)
    ctx.service.delete_block(ctx.amira, document.document_id, block.block_id)
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["block"]
    _assert_full_envelope(nodes[0], ctx.amira)


def test_set_doc_type_records_a_document_node(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Type Change")
    before = _watermark(ctx.conn)
    ctx.service.set_doc_type(ctx.amira, document.document_id, "kb")
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["document"]
    _assert_full_envelope(nodes[0], ctx.amira)


# --- versions ------------------------------------------------------------------


def test_snapshot_version_writes_a_version_node(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Snap")
    ctx.service.insert_block(ctx.amira, document.document_id, "one")
    before = _watermark(ctx.conn)
    ctx.service.snapshot_version(ctx.amira, document.document_id)
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["version"]
    _assert_full_envelope(nodes[0], ctx.amira)


def test_restore_version_writes_a_version_node(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Restore")
    ctx.service.insert_block(ctx.amira, document.document_id, "one")
    ctx.service.snapshot_version(ctx.amira, document.document_id)
    before = _watermark(ctx.conn)
    ctx.service.restore_version(ctx.amira, document.document_id, 1)
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["version"]
    node = nodes[0]
    _assert_full_envelope(node, ctx.amira)
    assert '"restored_from": 1' in node["body"]


# --- tasks and comments --------------------------------------------------------


def test_create_task_writes_one_task_node(ctx) -> None:
    before = _watermark(ctx.conn)
    ctx.task_service.create_task(ctx.amira, title="Invariant Task")
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["task"]
    node = nodes[0]
    _assert_full_envelope(node, ctx.amira)
    assert node["correlation_id"].startswith("task-")


def test_set_status_and_update_task_write_task_nodes(ctx) -> None:
    task = ctx.task_service.create_task(ctx.amira, title="t")
    before = _watermark(ctx.conn)
    ctx.task_service.set_status(ctx.amira, task.task_id, "doing")
    ctx.task_service.update_task(ctx.amira, task.task_id, title="t2", priority="high")
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["task", "task"]
    for node in nodes:
        _assert_full_envelope(node, ctx.amira)


def test_assign_writes_a_task_node_plus_its_notification_node(ctx) -> None:
    task = ctx.task_service.create_task(ctx.amira, title="t")
    before = _watermark(ctx.conn)
    ctx.task_service.assign(ctx.amira, task.task_id, ctx.omar.account_id)
    nodes = _new_nodes(ctx.conn, before)
    assert sorted(_kinds(nodes)) == ["notification", "task"]
    for node in nodes:
        _assert_full_envelope(node, ctx.amira)


def test_add_comment_writes_a_task_node(ctx) -> None:
    task = ctx.task_service.create_task(ctx.amira, title="t")
    before = _watermark(ctx.conn)
    ctx.task_service.add_comment(ctx.omar, task.task_id, "a comment")
    nodes = _new_nodes(ctx.conn, before)
    assert _kinds(nodes) == ["task"]
    node = nodes[0]
    _assert_full_envelope(node, ctx.omar)
    assert node["correlation_id"].startswith("task-")
    assert "comment_id" in node["body"]


# --- the sweep: no un-enveloped node anywhere ----------------------------------


def test_every_node_a_p3_session_produces_passes_the_envelope(ctx) -> None:
    document = ctx.service.create_document(ctx.amira, "Sweep")
    block = ctx.service.insert_block(ctx.amira, document.document_id, "A")
    ctx.service.update_block(ctx.amira, document.document_id, block.block_id, "A2")
    ctx.service.snapshot_version(ctx.amira, document.document_id)
    ctx.service.restore_version(ctx.amira, document.document_id, 1)
    task = ctx.task_service.create_task(
        ctx.amira, title="Sweep Task", assignee_account_id=ctx.omar.account_id
    )
    ctx.task_service.set_status(ctx.omar, task.task_id, "done")
    ctx.task_service.add_comment(ctx.omar, task.task_id, "done is done")
    rows = ctx.conn.execute(
        "SELECT * FROM nodes WHERE tenant_id = ? ORDER BY rowid ASC", (ctx.amira.tenant_id,)
    ).fetchall()
    assert len(rows) >= 7
    for row in rows:
        node = dict(row)
        assert node["tenant_id"] == "tenant-a"
        assert node["correlation_id"] and node["correlation_id"].strip()
        assert node["classification"] in db.CLASSIFICATIONS
        assert node["kind"] in {"document", "block", "version", "task", "notification"}
        assert node["nature"] and node["nature"].strip()
        assert node["created_by"] and node["created_by"].strip()
        assert node["provenance_source"] and node["provenance_source"].strip()
        assert node["provenance_data_mode"] == "app_runtime"
        assert node["body"] and node["body"].strip()
