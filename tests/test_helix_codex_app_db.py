"""Tests for helix_codex_app/db.py: the app database and the single node writer.

The node envelope is validated inside record_node, so every test here asserts
that a skipped or bad field raises ValueError. Fail closed, never silently.
"""
from __future__ import annotations

import pytest

from helix_codex_app import db

VALID_ENVELOPE = dict(
    tenant_id="tenant-academy-1",
    correlation_id="corr-p1-001",
    classification="internal",
    nature="verified_fact",
    created_by="account-owner-1",
    provenance_source="app",
    provenance_data_mode="simulated_realistic",
    kind="decision",
)


def _store(tmp_path):
    conn = db.connect(db_path=str(tmp_path / "app.db"))
    db._init_schema(conn)
    return conn


def test_schema_creates_every_planned_table(tmp_path):
    conn = _store(tmp_path)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        db.close(conn)
    assert {
        "nodes",
        "domains",
        "org_units",
        "accounts",
        "sessions",
        "account_capabilities",
        "account_limits",
        "login_events",
        "conversations",
        "conversation_members",
        "messages",
        "documents",
        "doc_blocks",
        "document_versions",
        "tasks",
        "task_comments",
        "events",
        "event_attendees",
        "oncall_shifts",
        "notifications",
        "punch_records",
        "files",
        "memory_stores",
        "proposals",
        "proposal_reviews",
        "promotions",
        "sections",
        "capability_packs",
    } <= tables


def test_record_node_rejects_blank_tenant_id(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["tenant_id"] = "   "
        with pytest.raises(ValueError, match="tenant_id"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_blank_correlation_id(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["correlation_id"] = ""
        with pytest.raises(ValueError, match="correlation_id"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_unknown_classification(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["classification"] = "top_secret_paranoia"
        with pytest.raises(ValueError, match="classification"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_missing_nature(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["nature"] = ""
        with pytest.raises(ValueError, match="nature"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_missing_provenance_data_mode(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["provenance_data_mode"] = ""
        with pytest.raises(ValueError, match="data_mode"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_blank_created_by(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["created_by"] = "   "
        with pytest.raises(ValueError, match="created_by"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_writes_the_full_envelope(tmp_path):
    conn = _store(tmp_path)
    try:
        node_id = db.record_node(conn, **VALID_ENVELOPE)
        rows = conn.execute(
            "SELECT node_id, tenant_id, correlation_id, classification, nature,"
            " kind, created_by, provenance_source, provenance_data_mode,"
            " provenance_retrieved_at FROM nodes WHERE node_id = ?",
            (node_id,),
        ).fetchall()
    finally:
        db.close(conn)
    assert len(rows) == 1
    row = rows[0]
    assert row["node_id"] == node_id
    assert row["tenant_id"] == "tenant-academy-1"
    assert row["correlation_id"] == "corr-p1-001"
    assert row["classification"] == "internal"
    assert row["nature"] == "verified_fact"
    assert row["kind"] == "decision"
    assert row["created_by"] == "account-owner-1"
    assert row["provenance_source"] == "app"
    assert row["provenance_data_mode"] == "simulated_realistic"


# ── A4: the node envelope validates declared vocabularies, not just blanks ──


def test_the_classification_vocabulary_is_the_shared_single_declaration():
    from contracts.vocabulary import MEMORY_CLASSIFICATIONS

    assert db.CLASSIFICATIONS is MEMORY_CLASSIFICATIONS


def test_the_node_vocabulary_is_the_canonical_seam_plus_app_nouns():
    from contracts.vocabulary import GOVERNED_MEMORY_KINDS, GOVERNED_MEMORY_NATURES

    assert db.NODE_KINDS >= GOVERNED_MEMORY_KINDS
    assert db.NODE_NATURES >= GOVERNED_MEMORY_NATURES
    # The app adds exactly one nature of its own; anything else is a bug.
    assert db.NODE_NATURES - GOVERNED_MEMORY_NATURES == {"system_event"}


def test_record_node_rejects_an_undeclared_nature(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["nature"] = "totally_made_up"
        with pytest.raises(ValueError, match="unknown nature"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_rejects_an_undeclared_kind(tmp_path):
    conn = _store(tmp_path)
    try:
        envelope = dict(**VALID_ENVELOPE)
        envelope["kind"] = "totally_made_up"
        with pytest.raises(ValueError, match="unknown kind"):
            db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_accepts_every_declared_nature(tmp_path):
    conn = _store(tmp_path)
    try:
        for nature in sorted(db.NODE_NATURES):
            envelope = dict(**VALID_ENVELOPE)
            envelope["nature"] = nature
            assert db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def test_record_node_accepts_every_declared_kind(tmp_path):
    conn = _store(tmp_path)
    try:
        for kind in sorted(db.NODE_KINDS):
            envelope = dict(**VALID_ENVELOPE)
            envelope["kind"] = kind
            assert db.record_node(conn, **envelope)
    finally:
        db.close(conn)


def _kinds_and_natures_written_by_the_app() -> tuple[set[str], set[str]]:
    """Literal ``kind=`` / ``nature=`` arguments passed to record_node in the app."""
    import ast
    import pathlib

    root = pathlib.Path(db.__file__).resolve().parent
    kinds: set[str] = set()
    natures: set[str] = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in ("record_node", "_record_node"):
                continue
            for keyword in node.keywords:
                if not isinstance(keyword.value, ast.Constant):
                    continue
                if keyword.arg == "kind":
                    kinds.add(keyword.value.value)
                elif keyword.arg == "nature":
                    natures.add(keyword.value.value)
    return kinds, natures


def test_the_declared_vocabulary_covers_every_kind_and_nature_the_app_writes():
    """The vocabulary cannot fall behind the code that writes to it."""
    kinds, natures = _kinds_and_natures_written_by_the_app()
    assert kinds, "expected to find record_node call sites"
    assert natures, "expected to find record_node call sites"
    assert kinds <= db.NODE_KINDS, f"undeclared kinds written: {sorted(kinds - db.NODE_KINDS)}"
    assert (
        natures <= db.NODE_NATURES
    ), f"undeclared natures written: {sorted(natures - db.NODE_NATURES)}"


def test_the_vocabulary_guard_can_fail(tmp_path, monkeypatch):
    """Can-fail proof: an undeclared literal is caught, not ignored."""
    import pathlib

    (tmp_path / "writer.py").write_text(
        "def write(conn):\n"
        "    return record_node(conn, kind='undeclared_noun', nature='user_claim')\n",
        encoding="utf-8",
    )
    real_file = pathlib.Path(db.__file__).resolve()
    monkeypatch.setattr(db, "__file__", str(tmp_path / "db.py"))
    try:
        kinds, _ = _kinds_and_natures_written_by_the_app()
        assert kinds == {"undeclared_noun"}
        assert not kinds <= db.NODE_KINDS
    finally:
        monkeypatch.undo()
    assert real_file.exists()
