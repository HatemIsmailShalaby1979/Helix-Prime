#!/usr/bin/env python3
"""
App database restore (P7.3, Prompt 37).

Restores a backup written by backup_app.py into a CLEAN target directory,
reusing release/backup.py's restore discipline: the target must be empty,
the backup version must be supported, and the restore verifies the governed
memory chains, the file hashes, the audit chain, and the release metadata
AFTER copying. A node count that disagrees with the manifest, a missing or
mismatched file, a broken chain, or an unsupported backup version fails the
restore loudly (exit 1) — a restore that silently lost data is not a restore.
`--verify-only` runs the same verification against the backup in place
without restoring, for restore rehearsals.

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

SUPPORTED_BACKUP_VERSIONS = {"1.0"}


def _check_version(manifest: dict) -> None:
    from release.backup import BackupError

    version = manifest.get("backup_version")
    if version not in SUPPORTED_BACKUP_VERSIONS:
        raise BackupError(
            f"restore rejected: backup version {version!r} is not supported "
            f"(supported: {sorted(SUPPORTED_BACKUP_VERSIONS)})"
        )


def _check_files(state_root: pathlib.Path, manifest: dict) -> list[dict]:
    import hashlib

    mismatches: list[dict] = []
    for entry in manifest.get("files", []):
        path = state_root / entry["rel"]
        if not path.is_file():
            mismatches.append({"rel": entry["rel"], "problem": "missing"})
            continue
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        if digest.hexdigest() != entry.get("sha256"):
            mismatches.append({"rel": entry["rel"], "problem": "hash_mismatch"})
    return mismatches


def restore_app(*, backup_dir: str, target_dir: str) -> dict:
    """Restore a backup into a CLEAN target and verify the result."""
    from release.backup import restore_state

    manifest_path = pathlib.Path(backup_dir) / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _check_version(manifest)
    restore_state(backup_dir=backup_dir, target_dir=target_dir)

    restored = _verify_restored(target_dir=target_dir, manifest=manifest)
    file_problems = _check_files(pathlib.Path(target_dir), manifest)
    audit_ok = restored["audit"].get("ok", True)
    metadata_ok = restored["metadata"].get("ok", True)
    return {
        "target_dir": target_dir,
        "expected_node_count": int(manifest["node_count"]),
        "actual_node_count": restored["actual_node_count"],
        "chains": restored["chains"],
        "chains_verified": restored["chains_verified"],
        "file_problems": file_problems,
        "audit": restored["audit"],
        "metadata": restored["metadata"],
        "verified": (
            restored["actual_node_count"] == int(manifest["node_count"])
            and restored["chains_verified"]
            and not file_problems
            and audit_ok
            and metadata_ok
        ),
    }


def verify_backup(*, backup_dir: str) -> dict:
    """Verify a backup in place without restoring it (rehearsal check)."""
    from release.backup import BackupError

    backup_root = pathlib.Path(backup_dir)
    manifest_path = backup_root / "backup-manifest.json"
    if not manifest_path.exists():
        raise BackupError(f"missing backup manifest: {backup_root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _check_version(manifest)
    state_root = backup_root / "state"
    file_problems = _check_files(state_root, manifest)
    restored = _verify_restored_against(state_root, manifest)
    audit_ok = restored["audit"].get("ok", True)
    metadata_ok = restored["metadata"].get("ok", True)
    node_ok = restored["actual_node_count"] == int(manifest["node_count"])
    return {
        "backup_dir": backup_dir,
        "expected_node_count": int(manifest["node_count"]),
        "actual_node_count": restored["actual_node_count"],
        "chains_verified": restored["chains_verified"],
        "file_problems": file_problems,
        "audit": restored["audit"],
        "metadata": restored["metadata"],
        "verified": (
            node_ok
            and restored["chains_verified"]
            and not file_problems
            and audit_ok
            and metadata_ok
        ),
    }


def _verify_restored(*, target_dir: str, manifest: dict) -> dict:
    return _verify_restored_against(pathlib.Path(target_dir), manifest)


def _verify_restored_against(state_root: pathlib.Path, manifest: dict) -> dict:
    from helix_codex_app import db
    from helix_codex_app.integration import memory_bridge

    node_count = 0
    db_path = state_root / "helix_codex_app" / "app.db"
    if db_path.exists():
        conn = db.connect(db_path=str(db_path))
        try:
            row = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
            node_count = int(row[0]) if row else 0
        finally:
            db.close(conn)

    chains: list[dict] = []
    memory_root = state_root / "helix_codex_app" / "memory_stores"
    if memory_root.exists():
        for ledger in sorted(memory_root.rglob("governed_memory.jsonl")):
            chains.append(memory_bridge.verify_store_file(str(ledger)))
    chains_verified = all(chain["verified"] for chain in chains)

    audit = _verify_audit(state_root, manifest.get("audit_db", {"captured": False}))
    metadata = _verify_metadata(state_root, manifest.get("release_metadata", {"captured": False}))

    return {
        "actual_node_count": node_count,
        "chains": chains,
        "chains_verified": chains_verified,
        "audit": audit,
        "metadata": metadata,
    }


def _verify_audit(state_root: pathlib.Path, record: dict) -> dict:
    if not record.get("captured"):
        return {"captured": False, "ok": True}
    audit_path = state_root / str(record.get("rel", ""))
    if not audit_path.is_file():
        return {"captured": True, "ok": False, "problem": "missing"}
    from security.audit import AuditTrail

    trail = AuditTrail(db_path=str(audit_path))
    try:
        valid, message = trail.verify_chain()
    finally:
        trail.close()
    if not valid:
        return {"captured": True, "ok": False, "problem": "chain_invalid", "detail": message}
    return {"captured": True, "ok": True}


def _verify_metadata(state_root: pathlib.Path, record: dict) -> dict:
    import hashlib

    if not record.get("captured"):
        return {"captured": False, "ok": True}
    meta_path = state_root / str(record.get("rel", ""))
    if not meta_path.is_file():
        return {"captured": True, "ok": False, "problem": "missing"}
    digest = hashlib.sha256()
    with open(meta_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    if digest.hexdigest() != record.get("sha256"):
        return {"captured": True, "ok": False, "problem": "hash_mismatch"}
    return {"captured": True, "ok": True}


def main(argv: list[str] | None = None) -> int:
    from release.backup import BackupError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, help="backup directory")
    parser.add_argument("--target", required=False, help="CLEAN target directory")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify the backup in place without restoring it (rehearsal check)",
    )
    args = parser.parse_args(argv)

    if args.verify_only:
        try:
            report = verify_backup(backup_dir=args.backup)
        except BackupError as exc:
            print(f"backup verification failed: {exc}", file=sys.stderr)
            return 1
        if not report["verified"]:
            print(
                _failure_line(args.backup, report),
                file=sys.stderr,
            )
            return 1
        print(f"backup {args.backup} verifies clean")
        return 0

    if not args.target:
        print("app restore failed: --target is required without --verify-only", file=sys.stderr)
        return 1
    try:
        report = restore_app(backup_dir=args.backup, target_dir=args.target)
    except BackupError as exc:
        print(f"app restore failed: {exc}", file=sys.stderr)
        return 1

    if not report["verified"]:
        print(
            _failure_line(args.target, report),
            file=sys.stderr,
        )
        return 1
    print(
        f"restored {args.target} (nodes={report['actual_node_count']} "
        f"chains_verified={report['chains_verified']})"
    )
    return 0


def _failure_line(where: str, report: dict) -> str:
    return (
        f"app restore FAILED verification at {where}: "
        f"expected {report['expected_node_count']} nodes, "
        f"restored {report['actual_node_count']}; "
        f"chains_verified={report['chains_verified']}; "
        f"file_problems={report['file_problems']}; "
        f"audit={report['audit']}; metadata={report['metadata']}"
    )


if __name__ == "__main__":
    sys.exit(main())
