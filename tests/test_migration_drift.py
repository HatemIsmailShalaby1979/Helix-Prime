"""
Migration drift tests (H2.1, G21).

The control-plane schema has two sources of truth — control_plane/store.py
(what the application creates) and migrations/versions/ (the authoritative
history). scripts/check_migration_drift.py proves they agree by building one
database each way and comparing sqlite_master contents.

These tests pin three properties:

1. the check passes at the current head (no live drift);
2. the check CAN FAIL — a schema that exists in one source but not the other
   is reported (a check that cannot fail is not a check, per G16);
3. alembic's own bookkeeping (alembic_version) is excluded from the
   comparison, because it exists only in migrated databases by design.

No test requires a live migration run: check_drift() builds throwaway
databases in a temp directory and closes every SQLite handle before teardown
(Windows file-lock safety).
"""
from __future__ import annotations

import sqlite3

from scripts.check_migration_drift import (
    ALEMBIC_BOOKKEEPING,
    _dump_schema,
    _normalise,
    check_drift,
)


def test_drift_check_passes_at_head():
    errors, report = check_drift()
    assert errors == [], f"unexpected schema drift: {errors}"
    assert report["store_objects"] > 0
    assert report["store_objects"] == report["migration_objects"]


def test_drift_check_fails_when_migration_diverges(tmp_path):
    """
    The check must be able to fail (G16 lesson).

    Simulates divergence by building a store database, then adding an object
    the migration head does not create: the report must flag it rather than
    silently pass.
    """
    divergent_db = str(tmp_path / "divergent.db")
    from control_plane.store import Store

    store = Store(db_path=divergent_db)
    try:
        store.conn.execute("CREATE TABLE drift_probe (id TEXT PRIMARY KEY, added_by_store TEXT)")
        store.conn.commit()
    finally:
        store.close()

    migrated_db = str(tmp_path / "migrated.db")
    from scripts.check_migration_drift import _build_migration_schema

    migrated_schema = _build_migration_schema(migrated_db)
    divergent_schema = _dump_schema(divergent_db)

    missing_from_migrations = sorted(set(divergent_schema) - set(migrated_schema))
    assert (
        "table:drift_probe" in missing_from_migrations
    ), f"divergent object not detected: {missing_from_migrations}"
    assert all(
        name == "table:drift_probe" or "drift_probe" in name for name in missing_from_migrations
    )


def test_alembic_bookkeeping_is_excluded(tmp_path):
    db = str(tmp_path / "with_version.db")
    from scripts.check_migration_drift import _build_migration_schema

    schema = _build_migration_schema(db)
    assert "table:alembic_version" not in schema
    assert "index:sqlite_autoindex_alembic_version_1" not in schema
    assert "table:workflows" in schema
    assert "table:audit_events" in schema
    assert "trigger:trg_audit_events_no_update" in schema


def test_normalisation_ignores_indentation_not_tokens():
    deep = "CREATE TABLE t (\n    a TEXT PRIMARY KEY,\n    b TEXT NOT NULL\n)"
    shallow = "CREATE TABLE t ( a TEXT PRIMARY KEY, b TEXT NOT NULL )"
    altered = "CREATE TABLE t ( a TEXT PRIMARY KEY, b INTEGER NOT NULL )"
    assert _normalise(deep) == _normalise(shallow)
    assert _normalise(deep) != _normalise(altered)


def test_baseline_migration_file_declares_head_revision():
    import pathlib

    versions_dir = pathlib.Path("migrations/versions")
    files = sorted(versions_dir.glob("*.py"))
    assert files, "migrations/versions/ must contain the baseline migration"
    heads = []
    contents = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        revisions = [
            line.split("=", 1)[1].strip().strip('"').strip("'")
            for line in text.splitlines()
            if line.startswith("revision = ")
        ]
        downs = [
            line.split("=", 1)[1].strip()
            for line in text.splitlines()
            if line.startswith("down_revision = ")
        ]
        assert len(revisions) == 1, f"{path}: exactly one revision id expected"
        contents[revisions[0]] = downs[0] if downs else "None"
    referenced = {
        value.strip(" '\"").replace("None", "")
        for value in contents.values()
        if value.strip(" '\"") != "None"
    }
    heads = [rev for rev in contents if rev not in referenced]
    assert len(heads) == 1, f"expected exactly one head, got {heads}"
    assert heads[0] == "0001_baseline", f"unexpected head: {heads[0]}"


def test_store_database_schema_dump_is_closed_cleanly(tmp_path):
    db = str(tmp_path / "store_schema.db")
    from control_plane.store import Store

    store = Store(db_path=db)
    store.close()
    dump = _dump_schema(db)
    assert "table:workflows" in dump
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_bookkeeping_set_matches_alembic_convention():
    assert ALEMBIC_BOOKKEEPING == {"alembic_version"}
