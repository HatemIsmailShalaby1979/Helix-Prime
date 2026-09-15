#!/usr/bin/env python3
"""
App database backup (P7.3, Prompt 37).

Copies the app database and the governed memory store tree into a target
directory alongside a backup manifest, reusing release/backup.py's
transaction-safe SQLite copy. The manifest records what was captured, when,
the node count in the app database, and the memory chain heads — so a
restore can later prove the state matches what was backed up.

Exit 0 = backup written. Exit 1 = nothing was captured or an error occurred.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sqlite3
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

APP_DB_REL = pathlib.Path("helix_codex_app") / "app.db"
MEMORY_STORES_REL = pathlib.Path("helix_codex_app") / "memory_stores"
BACKUP_VERSION = "1.0"


def backup_app(
    *,
    db_path: str,
    memory_root: str,
    target_dir: str,
) -> dict:
    """Copy db_path + memory_root into target_dir/state and write the manifest."""
    from release.backup import BackupError, _now, _sqlite_backup
    from scripts.export_evidence_pack import now_iso

    backup_root = pathlib.Path(target_dir)
    state_root = backup_root / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    captured: list[str] = []

    src_db = pathlib.Path(db_path)
    if src_db.exists():
        dst_db = state_root / APP_DB_REL
        dst_db.parent.mkdir(parents=True, exist_ok=True)
        _sqlite_backup(src_db, dst_db)
        captured.append(str(APP_DB_REL))
    else:
        raise BackupError(f"app database not found: {db_path}")

    src_memory = pathlib.Path(memory_root)
    if src_memory.exists():
        dst_memory = state_root / MEMORY_STORES_REL
        dst_memory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_memory, dst_memory)
        captured.append(str(MEMORY_STORES_REL))

    node_count = _count_nodes(str(dst_db))
    memory_chains = _memory_chain_status(str(dst_memory)) if src_memory.exists() else []
    all_verified = all(chain["verified"] for chain in memory_chains)

    manifest = {
        "backup_version": BACKUP_VERSION,
        "created_at": _now(),
        "captured_state": captured,
        "node_count": node_count,
        "memory_chains": memory_chains,
        "memory_chains_verified": all_verified,
        "generated_at": now_iso(),
    }
    (backup_root / "backup-manifest.json").write_text(
        json.dumps(manifest, default=str, indent=2), encoding="utf-8"
    )
    return manifest


def _count_nodes(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _memory_chain_status(memory_root: str) -> list[dict]:
    """Verify every governed memory ledger under the backup's tree."""
    from helix_codex_app.integration import memory_bridge

    results: list[dict] = []
    for ledger in sorted(pathlib.Path(memory_root).rglob("governed_memory.jsonl")):
        results.append(memory_bridge.verify_store_file(str(ledger)))
    return results


def main(argv: list[str] | None = None) -> int:
    from release.backup import BackupError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="helix_codex_app/app.db")
    parser.add_argument("--memory-root", default="helix_codex_app/memory_stores")
    parser.add_argument("--target", required=True, help="backup directory to create")
    args = parser.parse_args(argv)

    try:
        manifest = backup_app(
            db_path=args.db_path,
            memory_root=args.memory_root,
            target_dir=args.target,
        )
    except BackupError as exc:
        print(f"app backup failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"wrote {args.target} (captured={len(manifest['captured_state'])} "
        f"nodes={manifest['node_count']} memory_verified={manifest['memory_chains_verified']})"
    )
    return 0 if manifest["captured_state"] else 1


if __name__ == "__main__":
    sys.exit(main())
