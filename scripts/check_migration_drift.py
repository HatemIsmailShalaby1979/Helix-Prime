#!/usr/bin/env python3
"""
Migration drift check (H2.1, G21).

The control-plane schema has two sources of truth:
  1. control_plane/store.py      — what the application creates at runtime
  2. migrations/versions/        — the authoritative schema history

This script proves they agree, empirically: it builds one database via Store
and one via ``alembic upgrade head``, then compares their full sqlite_master
contents (tables, indexes, triggers — names and DDL text). Any divergence in
either direction fails CI with a per-object report.

Alembic's own bookkeeping (``alembic_version`` and its autoindex) is excluded:
it exists only in the migrated database and carries no schema meaning.

Exit 0 = no drift. Exit 1 = drift found (or the check could not run).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALEMBIC_BOOKKEEPING = {"alembic_version"}


def _dump_schema(db_path: str) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master"
            " WHERE name NOT IN ('alembic_version', 'sqlite_autoindex_alembic_version_1')"
            " ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()
    return {f"{obj_type}:{name}": _normalise(sql or "") for obj_type, name, sql in rows}


def _normalise(ddl: str) -> str:
    """
    Token-level normalisation of a DDL statement.

    SQLite stores DDL text verbatim, so the same schema written at two indent
    depths produces two different sqlite_master strings. Schema equivalence is
    about tokens: any column, type, constraint, or trigger-body change alters
    the token sequence, while indentation-only reformatting must not. The
    comparison below is on this normalised form.
    """
    return " ".join(ddl.split()).replace("( ", "(").replace(" )", ")")


def _close_silently(store) -> None:
    closer = getattr(store, "close", None)
    if callable(closer):
        closer()


def _build_store_schema(db_path: str) -> dict[str, str]:
    from control_plane.store import Store

    store = Store(db_path=db_path)
    try:
        store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    except Exception:
        pass
    _close_silently(store)
    return _dump_schema(db_path)


def _build_migration_schema(db_path: str) -> dict[str, str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "-x",
            f"db={db_path}",
            "upgrade",
            "head",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return _dump_schema(db_path)


def _checkpoint_sidecars(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def check_drift() -> tuple[list[str], dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix="helix_migration_drift_") as work:
        store_db = str(pathlib.Path(work) / "store_created.db")
        migrated_db = str(pathlib.Path(work) / "migration_created.db")

        store_schema = _build_store_schema(store_db)
        migrated_schema = _build_migration_schema(migrated_db)

        for path in (store_db, migrated_db):
            _checkpoint_sidecars(path)

        errors: list[str] = []
        missing_from_migrations = sorted(set(store_schema) - set(migrated_schema))
        missing_from_store = sorted(set(migrated_schema) - set(store_schema))
        altered = sorted(
            name
            for name in set(store_schema) & set(migrated_schema)
            if store_schema[name] != migrated_schema[name]
        )

        for name in missing_from_migrations:
            errors.append(
                f"{name}: created by control_plane/store.py but absent from the migration head"
            )
        for name in missing_from_store:
            errors.append(
                f"{name}: present in the migration head but control_plane/store.py does not create it"
            )
        for name in altered:
            errors.append(
                f"{name}: DDL differs between control_plane/store.py and the migration head"
                f" (store: {store_schema[name]!r} vs migration: {migrated_schema[name]!r})"
            )

        report = {
            "store_objects": len(store_schema),
            "migration_objects": len(migrated_schema),
            "missing_from_migrations": missing_from_migrations,
            "missing_from_store": missing_from_store,
            "altered": altered,
            "errors": errors,
        }
        return errors, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    try:
        errors, report = check_drift()
    except Exception as exc:  # noqa: BLE001 - a control that cannot run fails closed
        if args.json:
            print(json.dumps({"errors": [f"drift check could not run: {exc}"]}, indent=2))
        else:
            print(f"ERROR drift check could not run: {exc}")
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Migration drift check: store objects={report['store_objects']}, "
            f"migration objects={report['migration_objects']}"
        )
        if errors:
            print("Schema drift detected:")
            for error in errors:
                print(f"  ERROR {error}")
        else:
            print("No drift: control_plane/store.py and migrations/ head agree.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
