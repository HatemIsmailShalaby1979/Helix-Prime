"""Evidence export: owner-only zip of the app's governed audit trail.

The export is a self-contained, reviewable dossier containing:
* app audit trail (the nodes table, tenant-scoped, insertion-ordered);
* node counts by kind;
* memory store chain verification results;
* the release manifest from the repository root.

Read-only: the source database is never modified. The zip never includes
password hashes, session tokens, or raw secrets — the nodes table does
not carry these by construction.
"""
from __future__ import annotations

import io
import json
import pathlib
import sqlite3
import zipfile
from datetime import datetime, timezone
from typing import Any

from helix_codex_app import db

EVIDENCE_SCHEMA_VERSION = "1.0"

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _app_audit_trail(conn: sqlite3.Connection, tenant_id: str) -> list[dict[str, Any]]:
    """All nodes for the tenant, ordered by rowid (insertion order)."""
    rows = conn.execute(
        "SELECT node_id, tenant_id, client_id, domain_id, correlation_id, "
        "causation_id, classification, nature, kind, created_by, created_at, "
        "body, provenance_source, provenance_data_mode, "
        "provenance_retrieved_at, parent_node_id, thread_id "
        "FROM nodes WHERE tenant_id = ? ORDER BY rowid ASC",
        (tenant_id,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        try:
            d["body"] = json.loads(d["body"]) if d["body"] else None
        except (json.JSONDecodeError, TypeError):
            d["body"] = {"_parse_error": True}
        result.append(d)
    return result


def _node_counts_by_kind(conn: sqlite3.Connection, tenant_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT kind, COUNT(*) AS cnt "
        "FROM nodes WHERE tenant_id = ? GROUP BY kind ORDER BY kind",
        (tenant_id,),
    ).fetchall()
    return {row["kind"]: row["cnt"] for row in rows}


def _memory_store_verification(conn: sqlite3.Connection, tenant_id: str) -> list[dict[str, Any]]:
    from helix_codex_app.integration import memory_bridge

    stores = db.list_stores(conn, tenant_id)
    results: list[dict[str, Any]] = []
    for store in stores:
        results.append(memory_bridge.verify_store_file(store["path"]))
    return results


def _release_manifest() -> dict[str, Any]:
    manifest_path = _REPO_ROOT / "release" / "release-manifest.json"
    if not manifest_path.exists():
        return {"status": "not_found", "path": str(manifest_path)}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _readme(
    total_nodes: int,
    kind_counts: dict[str, int],
    store_count: int,
    all_verified: bool,
    started: str,
) -> str:
    lines = [
        "Helix Codex App - Evidence Export",
        "=" * 40,
        f"Generated at: {started}",
        f"Schema version: {EVIDENCE_SCHEMA_VERSION}",
        "",
        "Files in this archive:",
        "",
        "  app-audit-trail.json",
        "    The complete governed audit trail (nodes table) for this tenant.",
        f"    {total_nodes} record(s), insertion-ordered.",
        "",
        "  node-counts-by-kind.json",
        "    Aggregate counts of governed nodes by kind.",
    ]
    for kind, count in sorted(kind_counts.items()):
        lines.append(f"    {kind}: {count}")
    lines += [
        "",
        "  memory-store-verification.json",
        f"    Hash-chain verification for {store_count} governed memory store(s).",
        f"    All stores verified: {all_verified}",
        "",
        "  release-manifest.json",
        "    The release manifest from the repository root.",
        "",
        "Constraints:",
        "  - No password hashes, session tokens, or raw secrets are included.",
        "  - The nodes table does not carry these by construction.",
        "  - Read-only export: the source database is never modified.",
    ]
    return "\n".join(lines) + "\n"


def build_evidence_zip(
    conn: sqlite3.Connection,
    *,
    tenant_id: str,
    db_path: str,
) -> bytes:
    """Build the owner-only evidence export zip as raw bytes.

    Read-only: the source database is never modified. Raises if the
    tenant has no domain (a defensive check; callers are owner-scoped).
    """
    started = _now_iso()

    trail = _app_audit_trail(conn, tenant_id)
    kind_counts = _node_counts_by_kind(conn, tenant_id)
    total_nodes = sum(kind_counts.values())
    store_results = _memory_store_verification(conn, tenant_id)
    all_verified = all(r["verified"] for r in store_results)
    manifest = _release_manifest()
    readme = _readme(total_nodes, kind_counts, len(store_results), all_verified, started)

    envelope = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": started,
        "source": {"db_path": db_path, "read_only": True},
        "tenant_id": tenant_id,
        "record_count": len(trail),
        "records": trail,
    }

    entries: dict[str, bytes] = {
        "README.txt": readme.encode("utf-8"),
        "app-audit-trail.json": _json_bytes(envelope),
        "node-counts-by-kind.json": _json_bytes(
            {
                "tenant_id": tenant_id,
                "total_count": total_nodes,
                "counts_by_kind": kind_counts,
            }
        ),
        "memory-store-verification.json": _json_bytes(
            {
                "tenant_id": tenant_id,
                "store_count": len(store_results),
                "all_verified": all_verified,
                "stores": store_results,
            }
        ),
        "release-manifest.json": _json_bytes(manifest),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n").encode("utf-8")
