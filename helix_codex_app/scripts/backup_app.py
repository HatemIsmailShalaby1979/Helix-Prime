#!/usr/bin/env python3
"""
App database backup (P7.3, Prompt 37).

Copies the app database and the governed memory store tree into a target
directory alongside a backup manifest, reusing release/backup.py's
transaction-safe SQLite copy. The manifest records what was captured, when,
the node count in the app database, and the memory chain heads — so a
restore can later prove the state matches what was backed up. The audit
database and the release manifest are captured too when their paths are
passed, and every captured file is hashed into the manifest for integrity.
`prune_backups` deletes aged backup directories under a keep-newest safety
policy for the retention schedule.

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
AUDIT_DB_REL = pathlib.Path("security") / "audit.db"
RELEASE_MANIFEST_REL = pathlib.Path("release") / "release-manifest.json"
BACKUP_VERSION = "1.0"

DEFAULT_KEEP_LAST = 7
DEFAULT_KEEP_DAYS = 30


def _sha256(path: pathlib.Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_app(
    *,
    db_path: str,
    memory_root: str,
    target_dir: str,
    audit_db_path: str | None = None,
    release_manifest_path: str | None = None,
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

    audit_record: dict = {"captured": False}
    if audit_db_path:
        src_audit = pathlib.Path(audit_db_path)
        if src_audit.exists():
            dst_audit = state_root / AUDIT_DB_REL
            dst_audit.parent.mkdir(parents=True, exist_ok=True)
            _sqlite_backup(src_audit, dst_audit)
            captured.append(str(AUDIT_DB_REL))
            audit_record = {"captured": True, "rel": str(AUDIT_DB_REL)}
            audit_record.update(_audit_chain_status(str(dst_audit)))

    metadata_record: dict = {"captured": False}
    if release_manifest_path:
        src_meta = pathlib.Path(release_manifest_path)
        if src_meta.exists():
            dst_meta = state_root / RELEASE_MANIFEST_REL
            dst_meta.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_meta, dst_meta)
            captured.append(str(RELEASE_MANIFEST_REL))
            metadata_record = {
                "captured": True,
                "rel": str(RELEASE_MANIFEST_REL),
                "sha256": _sha256(dst_meta),
            }

    node_count = _count_nodes(str(dst_db))
    memory_chains = _memory_chain_status(str(dst_memory)) if src_memory.exists() else []
    all_verified = all(chain["verified"] for chain in memory_chains)

    files = _file_inventory(state_root)

    manifest = {
        "backup_version": BACKUP_VERSION,
        "created_at": _now(),
        "captured_state": captured,
        "node_count": node_count,
        "memory_chains": memory_chains,
        "memory_chains_verified": all_verified,
        "audit_db": audit_record,
        "release_metadata": metadata_record,
        "files": files,
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


def _audit_chain_status(audit_db_path: str) -> dict:
    """Verify the captured audit database chain."""
    from security.audit import AuditTrail

    trail = AuditTrail(db_path=audit_db_path)
    try:
        valid, message = trail.verify_chain()
        count_row = trail.conn.execute("SELECT COUNT(*) FROM audit").fetchone()
        return {
            "chain_valid": bool(valid),
            "chain_message": message,
            "record_count": int(count_row[0]) if count_row else 0,
        }
    finally:
        trail.close()


def _file_inventory(state_root: pathlib.Path) -> list[dict]:
    """Hash every captured file so a restore can prove nothing changed."""
    entries: list[dict] = []
    for path in sorted(state_root.rglob("*")):
        if not path.is_file():
            continue
        entries.append(
            {
                "rel": str(path.relative_to(state_root).as_posix()),
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    return entries


def prune_backups(
    backup_root: str,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
    keep_days: int = DEFAULT_KEEP_DAYS,
    dry_run: bool = False,
) -> dict:
    """Delete aged backup directories under backup_root under a safety policy.

    Only directories carrying their own backup-manifest.json are candidates;
    anything else is left alone. The newest backup is never deleted, and a
    root holding fewer than two backups is left untouched. Returns the kept
    and deleted directory names without applying changes when dry_run is set.
    """
    from datetime import datetime, timezone

    from release.backup import BackupError

    root = pathlib.Path(backup_root)
    candidates = sorted(
        child
        for child in root.iterdir()
        if child.is_dir() and (child / "backup-manifest.json").exists()
    )
    if len(candidates) < 2:
        return {"kept": [child.name for child in candidates], "deleted": []}
    newest = candidates[-1]
    cutoff = datetime.now(timezone.utc).timestamp() - keep_days * 86400
    deletable = [
        child
        for child in candidates[:-1]
        if len(candidates) - candidates.index(child) > keep_last or child.stat().st_mtime < cutoff
    ]
    deleted: list[str] = []
    for child in deletable:
        if child == newest:
            raise BackupError(f"refusing to prune the newest backup: {child.name}")
        if dry_run:
            deleted.append(child.name)
            continue
        shutil.rmtree(child)
        deleted.append(child.name)
    kept = [child.name for child in candidates if child.name not in deleted]
    return {"kept": kept, "deleted": deleted}


def main(argv: list[str] | None = None) -> int:
    from release.backup import BackupError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="helix_codex_app/app.db")
    parser.add_argument("--memory-root", default="helix_codex_app/memory_stores")
    parser.add_argument("--target", default=None, help="backup directory to create")
    parser.add_argument("--audit-db-path", default=None, help="audit database to capture")
    parser.add_argument("--release-manifest", default=None, help="release manifest file to capture")
    parser.add_argument(
        "--prune-root",
        default=None,
        help="prune aged backups under this directory instead of taking a backup",
    )
    parser.add_argument("--keep-last", type=int, default=DEFAULT_KEEP_LAST)
    parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.prune_root:
        report = prune_backups(
            args.prune_root,
            keep_last=args.keep_last,
            keep_days=args.keep_days,
            dry_run=args.dry_run,
        )
        print(
            f"prune {args.prune_root} (kept={len(report['kept'])} "
            f"deleted={len(report['deleted'])} dry_run={args.dry_run})"
        )
        return 0

    if not args.target:
        print("app backup failed: --target is required without --prune-root", file=sys.stderr)
        return 1

    try:
        manifest = backup_app(
            db_path=args.db_path,
            memory_root=args.memory_root,
            target_dir=args.target,
            audit_db_path=args.audit_db_path,
            release_manifest_path=args.release_manifest,
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
