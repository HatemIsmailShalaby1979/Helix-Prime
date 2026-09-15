"""Evidence export, backup, and restore (P7.3, Prompt 37).

Tests the zip dossier's contents, the owner-only gate, the backup copy, and
the restore round-trip (identical node count + verifying memory chain).
"""
from __future__ import annotations

import io
import json
import pathlib
import uuid
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from helix_codex_app import db
from helix_codex_app.app import create_app
from helix_codex_app.config import AppSettings
from helix_codex_app.integration.memory_bridge import AccountMemoryStore, verify_store_file
from helix_codex_app.modules.admin.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    build_evidence_zip,
)
from helix_codex_app.security.accounts import AccountRepository
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.sessions import SessionStore

# â”€â”€ fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@pytest.fixture()
def ctx(tmp_path: pathlib.Path):
    db_path = str(tmp_path / "app.db")
    memory_root = str(tmp_path / "memory_stores")
    conn = db.connect(db_path=db_path)
    db._init_schema(conn)
    repo = AccountRepository(conn)
    domain = repo.create_domain("b.academy", tenant_id="tenant-b", client_id="client-b")
    owner = repo.create_account(
        domain.domain_id,
        "dalia",
        display_name="Dalia O.",
        role_id="owner",
        password_hash=hash_password("owner-password"),
    )
    manager = repo.create_account(
        domain.domain_id,
        "amira",
        display_name="Amira K.",
        role_id="manager",
        password_hash=hash_password("manager-password"),
    )
    settings = AppSettings(
        db_path=db_path,
        memory_root=memory_root,
        cookie_secure=False,
    )
    memory = AccountMemoryStore(conn=conn, memory_root=memory_root)
    store = SessionStore(conn, settings)
    yield SimpleNamespace(
        conn=conn,
        repo=repo,
        domain=domain,
        owner=owner,
        manager=manager,
        settings=settings,
        memory=memory,
        store=store,
        db_path=db_path,
        memory_root=memory_root,
    )
    db.close(conn)


@pytest.fixture()
def client(ctx):
    with TestClient(create_app(ctx.settings), follow_redirects=False) as c:
        yield c


def _token(ctx, account) -> str:
    token, _ = ctx.store.issue_session(account)
    return token


# â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _write_governed_node(conn, *, tenant_id: str, kind: str = "admin") -> None:
    conn.execute(
        "INSERT INTO nodes ("
        "node_id, tenant_id, client_id, domain_id, correlation_id, "
        "causation_id, classification, nature, kind, created_by, "
        "created_at, body, provenance_source, provenance_data_mode"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"node-{uuid.uuid4().hex}",
            tenant_id,
            "client-x",
            "dom-x",
            f"corr-{uuid.uuid4().hex}",
            None,
            "internal",
            "historical_event",
            kind,
            "system",
            datetime.now(timezone.utc).isoformat(),
            json.dumps({"test": True}),
            "helix_codex_app.admin",
            "app_runtime",
        ),
    )
    conn.commit()


def _make_memory_store(ctx) -> str:
    """Create a valid chained org store for the tenant and register it."""
    ctx.memory.record_org(
        ctx.owner,
        kind="decision",
        nature="historical_event",
        body={"test": True},
        correlation_id="test-001",
        source="test",
    )
    return ctx.memory.resolve_org_store(ctx.owner)


# â”€â”€ evidence unit tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBuildEvidenceZip:
    def test_zip_contains_all_expected_entries(self, ctx: SimpleNamespace) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="admin")
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        expected = {
            "README.txt",
            "app-audit-trail.json",
            "node-counts-by-kind.json",
            "memory-store-verification.json",
            "release-manifest.json",
        }
        assert expected == names

    def test_readme_mentions_schema_version_and_constraints(self, ctx: SimpleNamespace) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b")
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            readme = zf.read("README.txt").decode("utf-8")
        assert EVIDENCE_SCHEMA_VERSION in readme
        assert "No password hashes" in readme
        assert "Read-only export" in readme

    def test_audit_trail_round_trip(self, ctx: SimpleNamespace) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="admin")
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="message")
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            envelope = json.loads(zf.read("app-audit-trail.json"))
        assert envelope["tenant_id"] == "tenant-b"
        assert envelope["record_count"] == 2
        assert envelope["schema_version"] == EVIDENCE_SCHEMA_VERSION
        assert envelope["source"]["read_only"] is True
        assert len(envelope["records"]) == 2
        assert envelope["records"][0]["kind"] == "admin"
        assert envelope["records"][1]["kind"] == "message"

    def test_node_counts_by_kind(self, ctx: SimpleNamespace) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="admin")
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="admin")
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="message")
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            counts = json.loads(zf.read("node-counts-by-kind.json"))
        assert counts["tenant_id"] == "tenant-b"
        assert counts["total_count"] == 3
        assert counts["counts_by_kind"] == {"admin": 2, "message": 1}

    def test_memory_store_verification_in_zip(self, ctx: SimpleNamespace) -> None:
        _make_memory_store(ctx)
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            verification = json.loads(zf.read("memory-store-verification.json"))
        assert verification["store_count"] >= 1
        assert verification["all_verified"] is True
        assert verification["stores"][0]["verified"] is True

    def test_empty_tenant_zip(self, ctx: SimpleNamespace) -> None:
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            envelope = json.loads(zf.read("app-audit-trail.json"))
            counts = json.loads(zf.read("node-counts-by-kind.json"))
            verification = json.loads(zf.read("memory-store-verification.json"))
        assert envelope["record_count"] == 0
        assert envelope["records"] == []
        assert counts["total_count"] == 0
        assert counts["counts_by_kind"] == {}
        assert verification["store_count"] == 0
        assert verification["all_verified"] is True

    def test_zip_never_includes_password_hash(self, ctx: SimpleNamespace) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b")
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        raw = payload.decode("latin-1")
        assert "password_hash" not in raw

    def test_release_manifest_present(self, ctx: SimpleNamespace) -> None:
        payload = build_evidence_zip(ctx.conn, tenant_id="tenant-b", db_path=ctx.db_path)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("release-manifest.json"))
        assert isinstance(manifest, dict)


# â”€â”€ HTTP evidence export tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestEvidenceExportRoute:
    def test_owner_gets_zip(self, ctx: SimpleNamespace, client: TestClient) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b")
        token = _token(ctx, ctx.owner)
        resp = client.get(
            "/app/admin/evidence/export",
            cookies={"helix_session": token},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "evidence-export.zip" in resp.headers.get("content-disposition", "")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            assert "README.txt" in zf.namelist()

    def test_manager_is_denied(self, ctx: SimpleNamespace, client: TestClient) -> None:
        token = _token(ctx, ctx.manager)
        resp = client.get(
            "/app/admin/evidence/export",
            cookies={"helix_session": token},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "permission_denied"

    def test_unauthenticated_is_denied(self, client: TestClient) -> None:
        resp = client.get("/app/admin/evidence/export")
        assert resp.status_code == 401


# â”€â”€ verify_store_file unit tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestVerifyStoreFile:
    def test_intact_chain_verifies(self, ctx: SimpleNamespace) -> None:
        path = _make_memory_store(ctx)
        result = verify_store_file(path)
        assert result["verified"] is True
        assert result["record_count"] == 1
        assert result["chain_head"] is not None

    def test_tampered_chain_fails(self, ctx: SimpleNamespace) -> None:
        path = _make_memory_store(ctx)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        env = json.loads(lines[-1])
        env["record"]["body"] = {"tampered": True}
        lines[-1] = json.dumps(env) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        result = verify_store_file(path)
        assert result["verified"] is False

    def test_missing_file_verifies_as_empty(self, ctx: SimpleNamespace) -> None:
        fake_path = str(pathlib.Path(ctx.memory_root) / "nonexistent" / "governed_memory.jsonl")
        result = verify_store_file(fake_path)
        assert result["record_count"] == 0
        assert result["chain_head"] == "0" * 64


# â”€â”€ backup / restore tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class TestBackupRestore:
    def test_backup_creates_manifest_and_nodes(
        self, ctx: SimpleNamespace, tmp_path: pathlib.Path
    ) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="admin")
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="message")
        from helix_codex_app.scripts.backup_app import backup_app

        target = str(tmp_path / "backup_out")
        manifest = backup_app(
            db_path=ctx.db_path,
            memory_root=ctx.memory_root,
            target_dir=target,
        )
        assert manifest["node_count"] == 2
        assert manifest["captured_state"]
        assert pathlib.Path(target, "backup-manifest.json").exists()
        assert pathlib.Path(target, "state", "helix_codex_app", "app.db").exists()

    def test_restore_round_trip_node_count_matches(
        self, ctx: SimpleNamespace, tmp_path: pathlib.Path
    ) -> None:
        _write_governed_node(ctx.conn, tenant_id="tenant-b", kind="admin")
        _make_memory_store(ctx)
        from helix_codex_app.scripts.backup_app import backup_app
        from helix_codex_app.scripts.restore_app import restore_app

        backup_dir = str(tmp_path / "backup_out")
        restore_dir = str(tmp_path / "restore_out")
        pathlib.Path(restore_dir).mkdir(parents=True)
        manifest = backup_app(
            db_path=ctx.db_path,
            memory_root=ctx.memory_root,
            target_dir=backup_dir,
        )
        report = restore_app(backup_dir=backup_dir, target_dir=restore_dir)
        assert report["verified"] is True
        assert report["actual_node_count"] == manifest["node_count"]
        assert report["chains_verified"] is True

    def test_restore_fails_on_missing_manifest(self, tmp_path: pathlib.Path) -> None:
        from helix_codex_app.scripts.restore_app import restore_app

        with pytest.raises(Exception):
            restore_app(backup_dir=str(tmp_path / "empty"), target_dir=str(tmp_path / "target"))

    def test_backup_memory_chain_verified(
        self, ctx: SimpleNamespace, tmp_path: pathlib.Path
    ) -> None:
        _make_memory_store(ctx)
        from helix_codex_app.scripts.backup_app import backup_app

        target = str(tmp_path / "backup_out")
        manifest = backup_app(
            db_path=ctx.db_path,
            memory_root=ctx.memory_root,
            target_dir=target,
        )
        assert manifest["memory_chains_verified"] is True
        assert len(manifest["memory_chains"]) >= 1
        assert manifest["memory_chains"][0]["verified"] is True
