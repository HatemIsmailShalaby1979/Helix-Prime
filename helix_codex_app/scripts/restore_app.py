#!/usr/bin/env python3
"""
App database restore (P7.3, Prompt 37).

Restores a backup written by backup_app.py into a CLEAN target directory,
reusing release/backup.py's restore discipline: the target must be empty,
and the restore verifies the governed memory chains AFTER copying. A node
count that disagrees with the manifest, or a broken memory chain, fails the
restore loudly (exit 1) — a restore that silently lost data is not a restore.

Exit 0 = restored and verified. Exit 1 = not restored, or verification failed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def restore_app(*, backup_dir: str, target_dir: str) -> dict:
    """Restore a backup into a CLEAN target and verify the result."""
    from release.backup import restore_state

    restore_state(backup_dir=backup_dir, target_dir=target_dir)

    manifest_path = pathlib.Path(backup_dir) / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    restored = _verify_restored(target_dir=target_dir, manifest=manifest)
    return {
        "target_dir": target_dir,
        "expected_node_count": int(manifest["node_count"]),
        "actual_node_count": restored["actual_node_count"],
        "chains": restored["chains"],
        "chains_verified": restored["chains_verified"],
        "verified": (
            restored["actual_node_count"] == int(manifest["node_count"])
            and restored["chains_verified"]
        ),
    }


def _verify_restored(*, target_dir: str, manifest: dict) -> dict:
    from helix_codex_app import db
    from helix_codex_app.integration import memory_bridge

    target = pathlib.Path(target_dir)

    node_count = 0
    db_path = target / "helix_codex_app" / "app.db"
    conn = db.connect(db_path=str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        node_count = int(row[0]) if row else 0
    finally:
        db.close(conn)

    chains: list[dict] = []
    for ledger in sorted(
        (target / "helix_codex_app" / "memory_stores").rglob("governed_memory.jsonl")
    ):
        chains.append(memory_bridge.verify_store_file(str(ledger)))
    chains_verified = all(chain["verified"] for chain in chains)

    return {
        "actual_node_count": node_count,
        "chains": chains,
        "chains_verified": chains_verified,
    }


def main(argv: list[str] | None = None) -> int:
    from release.backup import BackupError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, help="backup directory")
    parser.add_argument("--target", required=True, help="CLEAN target directory")
    args = parser.parse_args(argv)

    try:
        report = restore_app(backup_dir=args.backup, target_dir=args.target)
    except BackupError as exc:
        print(f"app restore failed: {exc}", file=sys.stderr)
        return 1

    if not report["verified"]:
        print(
            f"app restore FAILED verification: expected {report['expected_node_count']} nodes, "
            f"restored {report['actual_node_count']}; chains_verified={report['chains_verified']}",
            file=sys.stderr,
        )
        return 1
    print(
        f"restored {args.target} (nodes={report['actual_node_count']} "
        f"chains_verified={report['chains_verified']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
