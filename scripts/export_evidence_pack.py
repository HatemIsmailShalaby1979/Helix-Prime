#!/usr/bin/env python
"""
Export the enterprise governance evidence pack (C8).

Reads the append-only ``audit_events`` ledger and writes one self-contained,
reviewable dossier containing:

* ledger integrity (hash-chain verification and head hash);
* uptime/health snapshot (database opened, schema present, chain valid);
* agent communication history (actors, roles, event types, correlations);
* audit validation trails (ordered rows with state handoffs, decisions and
  cryptographic fields);
* tenant/correlation counts for operational scoping.

The exporter is read-only. It never modifies the ledger and never includes
raw secrets or environment variables. A dossier is evidence only when
``integrity.verified`` is true.

Usage::

    python scripts/export_evidence_pack.py --db-path control_plane/workflow.db \
        --output evidence/governance_pack.json
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sqlite3
import sys
from collections import Counter
from typing import Any, Dict, List

SCHEMA_VERSION = "1.0"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def verify_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    previous = ""
    failures: List[Dict[str, Any]] = []
    for position, row in enumerate(rows):
        if row.get("prev_hash", "") != previous:
            failures.append(
                {
                    "position": position,
                    "event_id": row.get("event_id"),
                    "reason": "prev_hash does not match preceding record_hash",
                    "expected": previous,
                    "actual": row.get("prev_hash", ""),
                }
            )
        signing = {
            key: row.get(key)
            for key in (
                "event_id",
                "occurred_at",
                "correlation_id",
                "actor_id",
                "actor_role_id",
                "event_type",
                "decision",
                "reason_code",
                "reason",
                "task_id",
                "workflow_id",
                "from_state",
                "to_state",
                "payload",
                "prev_hash",
            )
        }
        expected_hash = hashlib.sha256(canonical(signing).encode("utf-8")).hexdigest()
        if row.get("record_hash") != expected_hash:
            failures.append(
                {
                    "position": position,
                    "event_id": row.get("event_id"),
                    "reason": "record_hash does not match canonical record",
                    "expected": expected_hash,
                    "actual": row.get("record_hash"),
                }
            )
        previous = row.get("record_hash", "")
    return {
        "verified": not failures,
        "record_count": len(rows),
        "head_hash": previous,
        "failures": failures,
    }


def load_ledger(db_path: pathlib.Path) -> List[Dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"ledger not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'"
        ).fetchone()
        if not table:
            raise RuntimeError("audit_events table is missing")
        rows = conn.execute("SELECT * FROM audit_events ORDER BY rowid ASC").fetchall()
        output: List[Dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            try:
                record["payload"] = json.loads(record.get("payload") or "{}")
            except json.JSONDecodeError:
                record["payload"] = {"_malformed": True, "raw_length": len(record.get("payload") or "")}
            output.append(record)
        return output
    finally:
        conn.close()


def build_pack(db_path: str | pathlib.Path) -> Dict[str, Any]:
    path = pathlib.Path(db_path)
    started = now_iso()
    rows = load_ledger(path)
    integrity = verify_rows(rows)

    actors = Counter(row.get("actor_id") or "unknown" for row in rows)
    roles = Counter(row.get("actor_role_id") or "unknown" for row in rows)
    event_types = Counter(row.get("event_type") or "unknown" for row in rows)
    decisions = Counter(row.get("decision") or "unknown" for row in rows)
    correlations = sorted({row.get("correlation_id") for row in rows if row.get("correlation_id")})
    tenants = sorted(
        {
            row.get("payload", {}).get("tenant_id")
            for row in rows
            if row.get("payload", {}).get("tenant_id")
        }
    )

    validation_trails = []
    for row in rows:
        validation_trails.append(
            {
                "event_id": row.get("event_id"),
                "occurred_at": row.get("occurred_at"),
                "correlation_id": row.get("correlation_id"),
                "task_id": row.get("task_id"),
                "workflow_id": row.get("workflow_id"),
                "actor_id": row.get("actor_id"),
                "actor_role_id": row.get("actor_role_id"),
                "event_type": row.get("event_type"),
                "decision": row.get("decision"),
                "reason_code": row.get("reason_code"),
                "from_state": row.get("from_state"),
                "to_state": row.get("to_state"),
                "prev_hash": row.get("prev_hash"),
                "record_hash": row.get("record_hash"),
                "payload": row.get("payload", {}),
            }
        )

    return {
        "pack_type": "helix_codex_enterprise_governance_evidence",
        "schema_version": SCHEMA_VERSION,
        "generated_at": started,
        "source": {"db_path": str(path), "ledger": "audit_events", "read_only": True},
        "integrity": integrity,
        "uptime_health": {
            "database_reachable": True,
            "audit_table_present": True,
            "ledger_chain_verified": integrity["verified"],
            "health_status": "healthy" if integrity["verified"] else "degraded",
            "checked_at": started,
        },
        "agent_communication_history": {
            "event_count": len(rows),
            "actors": dict(sorted(actors.items())),
            "roles": dict(sorted(roles.items())),
            "event_types": dict(sorted(event_types.items())),
            "decisions": dict(sorted(decisions.items())),
            "correlation_ids": correlations,
            "tenant_ids": tenants,
        },
        "audit_validation_trails": validation_trails,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="control_plane/workflow.db")
    parser.add_argument("--output", default="evidence/governance_evidence_pack.json")
    args = parser.parse_args()

    try:
        pack = build_pack(args.db_path)
    except Exception as exc:
        print(f"evidence export failed: {exc}", file=sys.stderr)
        return 1

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pack, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"wrote {output} (records={pack['integrity']['record_count']} verified={pack['integrity']['verified']})")
    return 0 if pack["integrity"]["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
