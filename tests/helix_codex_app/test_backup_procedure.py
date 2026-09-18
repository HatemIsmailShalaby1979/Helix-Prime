"""Backup-procedure tests for the self-hosted app.

Proves the integrity manifest (per-file hashes), the audit-chain and
release-metadata verification, the backup-version gate, the clean-target
refusal, the retention-prune safety policy, and the verify-only rehearsal
check. The tampered-backup test is the can-fail proof for the hash
inventory: it keeps the node count identical, so a count-only verification
would still pass and only the hash check fails it.
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from helix_codex_app import db
from helix_codex_app.integration.memory_bridge import AccountMemoryStore
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password


@pytest.fixture()
def ctx(tmp_path: pathlib.Path):
    db_path = str(tmp_path / "app.db")
    memory_root = str(tmp_path / "memory_stores")
    audit_db_path = str(tmp_path / "audit.db")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("c.academy", tenant_id="tenant-c", client_id="client-c")
    owner = repo.create_account(
        domain.domain_id,
        "carim",
        display_name="Carim D.",
        role_id="owner",
        password_hash=hash_password("owner-password"),
    )
    memory = AccountMemoryStore(conn=conn, memory_root=memory_root)
    release_manifest = tmp_path / "release-manifest.json"
    release_manifest.write_text(
        json.dumps({"product": "Helix-Prime-Codex", "version": "0.9.0-c8"}),
        encoding="utf-8",
    )
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        owner=owner,
        memory=memory,
        db_path=db_path,
        memory_root=memory_root,
        audit_db_path=audit_db_path,
        release_manifest_path=str(release_manifest),
    )
    db.close(conn)


def _write_node(conn, body_text: str = "original") -> None:
    conn.execute(
        "INSERT INTO nodes ("
        "node_id, tenant_id, client_id, domain_id, correlation_id, "
        "causation_id, classification, nature, kind, created_by, "
        "created_at, body, provenance_source, provenance_data_mode"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"node-{uuid.uuid4().hex}",
            "tenant-c",
            "client-c",
            "dom-c",
            f"corr-{uuid.uuid4().hex}",
            None,
            "internal",
            "historical_event",
            "admin",
            "system",
            datetime.now(timezone.utc).isoformat(),
            json.dumps({"text": body_text}),
            "helix_codex_app.admin",
            "app_runtime",
        ),
    )
    conn.commit()


def _make_memory_record(ctx) -> str:
    ctx.memory.record_org(
        ctx.owner,
        kind="decision",
        nature="historical_event",
        body={"test": True},
        correlation_id="backup-001",
        source="test",
    )
    return ctx.memory.resolve_org_store(ctx.owner)


def _make_audit_db(path: str) -> None:
    from security.audit import AuditRecord, AuditTrail

    trail = AuditTrail(db_path=path)
    try:
        prev = None
        for _ in range(2):
            rec = AuditRecord.new(
                event_type="backup-test",
                actor="backup-test",
                actor_type="service",
                decision="succeeded",
                previous_hash=prev,
            )
            trail.append(rec)
            prev = rec.current_hash
    finally:
        trail.close()


def _take_backup(ctx, tmp_path: pathlib.Path, name: str = "backup") -> str:
    from helix_codex_app.scripts.backup_app import backup_app

    target = str(tmp_path / name)
    backup_app(
        db_path=ctx.db_path,
        memory_root=ctx.memory_root,
        target_dir=target,
        audit_db_path=ctx.audit_db_path,
        release_manifest_path=ctx.release_manifest_path,
    )
    return target


def _seed(ctx) -> None:
    _write_node(ctx.conn)
    _make_memory_record(ctx)
    _make_audit_db(ctx.audit_db_path)


def test_backup_captures_audit_and_metadata_and_round_trips(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import restore_app

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    manifest = json.loads(
        (pathlib.Path(backup_dir) / "backup-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["audit_db"]["captured"] is True
    assert manifest["audit_db"]["chain_valid"] is True
    assert manifest["release_metadata"]["captured"] is True
    assert manifest["files"], "integrity inventory must not be empty"
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    report = restore_app(backup_dir=backup_dir, target_dir=str(restore_dir))
    assert report["verified"] is True
    assert report["audit"]["ok"] is True
    assert report["metadata"]["ok"] is True
    assert report["file_problems"] == []


def test_tampered_backup_fails_restore(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import restore_app

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    state_db = pathlib.Path(backup_dir) / "state" / "helix_codex_app" / "app.db"
    conn = sqlite3.connect(state_db)
    try:
        conn.execute("UPDATE nodes SET body = ? ", (json.dumps({"text": "tampered"}),))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    finally:
        conn.close()
    assert count == 1
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    report = restore_app(backup_dir=backup_dir, target_dir=str(restore_dir))
    assert report["verified"] is False
    assert report["file_problems"], "hash inventory must catch the tamper"


def test_missing_audit_db_in_backup_fails_restore(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import restore_app

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    (pathlib.Path(backup_dir) / "state" / "security" / "audit.db").unlink()
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    report = restore_app(backup_dir=backup_dir, target_dir=str(restore_dir))
    assert report["verified"] is False
    assert report["audit"]["ok"] is False


def test_corrupted_memory_chain_fails_restore(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import restore_app

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    ledgers = list((pathlib.Path(backup_dir) / "state").rglob("governed_memory.jsonl"))
    assert ledgers, "backup must contain a memory ledger"
    lines = ledgers[0].read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["record"]["body"] = {"tampered": True}
    lines[-1] = json.dumps(record)
    ledgers[0].write_text("\n".join(lines) + "\n", encoding="utf-8")
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    report = restore_app(backup_dir=backup_dir, target_dir=str(restore_dir))
    assert report["verified"] is False
    assert report["chains_verified"] is False


def test_incompatible_backup_version_is_refused(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import restore_app
    from release.backup import BackupError

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    manifest_path = pathlib.Path(backup_dir) / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["backup_version"] = "9.9"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    with pytest.raises(BackupError, match="not supported"):
        restore_app(backup_dir=backup_dir, target_dir=str(restore_dir))


def test_restore_into_non_empty_target_is_refused(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import restore_app
    from release.backup import BackupError

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    (restore_dir / "existing.txt").write_text("live data", encoding="utf-8")
    with pytest.raises(BackupError, match="clean/empty"):
        restore_app(backup_dir=backup_dir, target_dir=str(restore_dir))


def _make_dated_backup_dir(root: pathlib.Path, name: str, age_days: int) -> None:
    path = root / name
    path.mkdir(parents=True)
    (path / "backup-manifest.json").write_text("{}", encoding="utf-8")
    old = datetime.now(timezone.utc).timestamp() - age_days * 86400
    os.utime(path, (old, old))


def test_retention_prune_keeps_newest_and_bound(tmp_path) -> None:
    from helix_codex_app.scripts.backup_app import prune_backups

    root = tmp_path / "backups"
    root.mkdir()
    for i in range(5):
        _make_dated_backup_dir(root, f"helix-backup-00{i}", age_days=40 - i * 10)
    (root / "not-a-backup").mkdir()
    report = prune_backups(str(root), keep_last=3, keep_days=30)
    remaining = sorted(child.name for child in root.iterdir())
    assert "not-a-backup" in remaining
    assert "helix-backup-004" in remaining
    assert report["kept"] == ["helix-backup-002", "helix-backup-003", "helix-backup-004"]
    assert report["deleted"] == ["helix-backup-000", "helix-backup-001"]


def test_retention_dry_run_changes_nothing(tmp_path) -> None:
    from helix_codex_app.scripts.backup_app import prune_backups

    root = tmp_path / "backups"
    root.mkdir()
    for i in range(3):
        _make_dated_backup_dir(root, f"helix-backup-00{i}", age_days=50)
    before = sorted(child.name for child in root.iterdir())
    report = prune_backups(str(root), keep_last=1, keep_days=30, dry_run=True)
    assert sorted(child.name for child in root.iterdir()) == before
    assert report["deleted"], "dry run must still report what would go"


def test_verify_only_rehearsal_passes_and_fails(ctx, tmp_path) -> None:
    from helix_codex_app.scripts.restore_app import main as restore_main
    from helix_codex_app.scripts.restore_app import verify_backup

    _seed(ctx)
    backup_dir = _take_backup(ctx, tmp_path)
    assert verify_backup(backup_dir=backup_dir)["verified"] is True
    assert restore_main(["--backup", backup_dir, "--verify-only"]) == 0
    state_db = pathlib.Path(backup_dir) / "state" / "helix_codex_app" / "app.db"
    conn = sqlite3.connect(state_db)
    try:
        conn.execute("UPDATE nodes SET body = ?", (json.dumps({"text": "tampered"}),))
        conn.commit()
    finally:
        conn.close()
    assert verify_backup(backup_dir=backup_dir)["verified"] is False
    assert restore_main(["--backup", backup_dir, "--verify-only"]) == 1
