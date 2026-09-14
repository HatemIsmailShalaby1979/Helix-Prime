"""App migration drift tests (P1.7).

The app schema has two sources of truth — helix_codex_app/db.py (what the
application creates at runtime) and helix_codex_app/migrations/versions/
(the authoritative history). helix_codex_app/scripts/check_app_migration_drift.py
proves they agree by building one database each way and comparing
sqlite_master contents.

These tests pin three properties:

1. the check passes at the current head (no live drift);
2. the check CAN FAIL — an object that exists in only one source is
   reported (a check that cannot fail is not a check);
3. the normalisation ignores indentation but not tokens.

The script builds throwaway databases inside a temp directory and closes
every SQLite handle before teardown (Windows file-lock safety).
"""
from __future__ import annotations

import pathlib
import sys

from helix_codex_app.scripts.check_app_migration_drift import (
    _dump_schema,
    _normalise,
    check_drift,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_app_drift_check_passes_at_head():
    errors, report = check_drift()
    assert errors == [], f"unexpected app schema drift: {errors}"
    assert report["store_objects"] > 0
    assert report["store_objects"] == report["migration_objects"]


def test_app_drift_check_can_fail(tmp_path):
    divergent_db = str(tmp_path / "divergent.db")
    from helix_codex_app import db

    conn = db.connect(db_path=divergent_db)
    try:
        db._init_schema(conn)
        conn.execute("CREATE TABLE drift_probe (id TEXT PRIMARY KEY, added_by_store TEXT)")
        conn.commit()
    finally:
        db.close(conn)

    migrated_db = str(tmp_path / "migrated.db")
    from helix_codex_app.scripts.check_app_migration_drift import _build_migration_schema

    migrated_schema = _build_migration_schema(migrated_db)
    divergent_schema = _dump_schema(divergent_db)
    missing = sorted(set(divergent_schema) - set(migrated_schema))
    assert "table:drift_probe" in missing, f"divergence not detected: {missing}"


def test_normalisation_ignores_indentation_not_tokens():
    deep = "CREATE TABLE t (\n    a TEXT PRIMARY KEY,\n    b TEXT NOT NULL\n)"
    shallow = "CREATE TABLE t ( a TEXT PRIMARY KEY, b TEXT NOT NULL )"
    altered = "CREATE TABLE t ( a TEXT PRIMARY KEY, b INTEGER NOT NULL )"
    assert _normalise(deep) == _normalise(shallow)
    assert _normalise(deep) != _normalise(altered)
