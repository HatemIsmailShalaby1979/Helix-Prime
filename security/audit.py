"""
Tamper-evident audit trail for Helix Prime Codex C3.

Append-oriented, hash-chained, tamper-evident until deletion/access-control/backup proven.
Do NOT call it immutable ledger.

Records: audit ID, event/action type, actor, actor type, tenant/client, role, workflow/task/correlation IDs,
input/output references, decision, approval/denial, timestamp, previous hash, current hash, schema version.

Uses deterministic SHA-256 hash chain.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"


def _require_non_empty_str(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be non-empty string, got {value!r}")
    return value.strip()


def _validate_iso(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    try:
        cand = s.replace("Z", "+00:00") if s.endswith("Z") else s
        datetime.datetime.fromisoformat(cand)
    except Exception as e:
        raise ValueError(f"{field_path}: must be ISO8601, got {s!r}: {e}") from e
    return s


def _validate_schema_version(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if not re.match(r"^\d+\.\d+$", s):
        raise ValueError(f"{field_path}: must be semver '1.0', got {s!r}")
    return s


def _hash_record(data: Dict[str, Any]) -> str:
    """Deterministic SHA-256 over canonical JSON (sorted keys, no whitespace)."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class AuditRecord:
    audit_id: str
    event_type: str  # e.g., authorization_denied, workflow_created, approval_granted
    actor: str
    actor_type: str  # human/agent/service
    tenant_id: Optional[str]
    client_id: Optional[str]
    role_id: Optional[str]
    workflow_id: Optional[str]
    task_id: Optional[str]
    correlation_id: Optional[str]
    input_ref: Optional[str]  # reference to input (e.g., request_id or hash)
    output_ref: Optional[str]
    decision: str  # e.g., allowed, denied, succeeded, failed
    approval_decision: Optional[str]  # approved/denied
    timestamp: str
    previous_hash: Optional[str]  # hash of previous record, None for genesis
    current_hash: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.audit_id = _require_non_empty_str(self.audit_id, "AuditRecord.audit_id")
        self.event_type = _require_non_empty_str(self.event_type, "AuditRecord.event_type")
        self.actor = _require_non_empty_str(self.actor, "AuditRecord.actor")
        if self.actor_type not in ("human", "agent", "service"):
            raise ValueError(f"AuditRecord.actor_type: must be human/agent/service, got {self.actor_type!r}")
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "AuditRecord.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "AuditRecord.client_id")
        if self.role_id is not None:
            self.role_id = _require_non_empty_str(self.role_id, "AuditRecord.role_id")
        if self.workflow_id is not None:
            self.workflow_id = _require_non_empty_str(self.workflow_id, "AuditRecord.workflow_id")
        if self.task_id is not None:
            self.task_id = _require_non_empty_str(self.task_id, "AuditRecord.task_id")
        if self.correlation_id is not None:
            self.correlation_id = _require_non_empty_str(self.correlation_id, "AuditRecord.correlation_id")
        if self.input_ref is not None:
            self.input_ref = _require_non_empty_str(self.input_ref, "AuditRecord.input_ref")
        if self.output_ref is not None:
            self.output_ref = _require_non_empty_str(self.output_ref, "AuditRecord.output_ref")
        self.decision = _require_non_empty_str(self.decision, "AuditRecord.decision")
        if self.approval_decision is not None:
            if self.approval_decision not in ("approved", "denied", None):
                # allow other strings but normalize
                self.approval_decision = _require_non_empty_str(self.approval_decision, "AuditRecord.approval_decision").lower()
        self.timestamp = _validate_iso(self.timestamp, "AuditRecord.timestamp")
        if self.previous_hash is not None:
            if not isinstance(self.previous_hash, str) or len(self.previous_hash) != 64:
                raise ValueError(f"AuditRecord.previous_hash: must be 64-char hex or None, got {self.previous_hash!r}")
        if not isinstance(self.current_hash, str) or len(self.current_hash) != 64:
            raise ValueError(f"AuditRecord.current_hash: must be 64-char hex, got {self.current_hash!r}")
        self.schema_version = _validate_schema_version(self.schema_version, "AuditRecord.schema_version")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "audit_id": self.audit_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "actor_type": self.actor_type,
            "decision": self.decision,
            "timestamp": self.timestamp,
            "current_hash": self.current_hash,
            "schema_version": self.schema_version,
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.role_id is not None:
            d["role_id"] = self.role_id
        if self.workflow_id is not None:
            d["workflow_id"] = self.workflow_id
        if self.task_id is not None:
            d["task_id"] = self.task_id
        if self.correlation_id is not None:
            d["correlation_id"] = self.correlation_id
        if self.input_ref is not None:
            d["input_ref"] = self.input_ref
        if self.output_ref is not None:
            d["output_ref"] = self.output_ref
        if self.approval_decision is not None:
            d["approval_decision"] = self.approval_decision
        if self.previous_hash is not None:
            d["previous_hash"] = self.previous_hash
        return d

    @classmethod
    def new(
        cls,
        event_type: str,
        actor: str,
        actor_type: str,
        decision: str,
        correlation_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        role_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        input_ref: Optional[str] = None,
        output_ref: Optional[str] = None,
        approval_decision: Optional[str] = None,
        previous_hash: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> "AuditRecord":
        audit_id = uuid.uuid4().hex
        ts = timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        # Compute current_hash deterministically from content + previous_hash
        # Use canonical dict without current_hash itself
        content = {
            "audit_id": audit_id,
            "event_type": event_type,
            "actor": actor,
            "actor_type": actor_type,
            "tenant_id": tenant_id,
            "client_id": client_id,
            "role_id": role_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "correlation_id": correlation_id,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "decision": decision,
            "approval_decision": approval_decision,
            "timestamp": ts,
            "previous_hash": previous_hash,
            "schema_version": SCHEMA_VERSION,
        }
        # Remove None values for hashing consistency
        content_filtered = {k: v for k, v in content.items() if v is not None}
        current_hash = _hash_record(content_filtered)
        return cls(
            audit_id=audit_id,
            event_type=event_type,
            actor=actor,
            actor_type=actor_type,
            tenant_id=tenant_id,
            client_id=client_id,
            role_id=role_id,
            workflow_id=workflow_id,
            task_id=task_id,
            correlation_id=correlation_id,
            input_ref=input_ref,
            output_ref=output_ref,
            decision=decision,
            approval_decision=approval_decision,
            timestamp=ts,
            previous_hash=previous_hash,
            current_hash=current_hash,
        )


class AuditTrail:
    """
    Append-oriented audit trail with hash chain, SQLite-backed.

    - SQLite file default: security/audit.db (local-first)
    - Append is atomic, previous_hash is enforced to be previous record's current_hash
    - verify_chain() detects tampering, missing, or out-of-order records
    - Do NOT call immutable ledger; document as tamper-evident until deletion/backup proven
    """

    def __init__(self, db_path: str = "security/audit.db"):
        self.db_path = db_path
        import pathlib

        pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                audit_id TEXT PRIMARY KEY,
                previous_hash TEXT,
                current_hash TEXT UNIQUE,
                data TEXT NOT NULL,
                timestamp TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_prev ON audit(previous_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(timestamp)")
        self.conn.commit()

    def append(self, record: AuditRecord) -> AuditRecord:
        # Verify previous_hash matches last record's current_hash (unless genesis)
        cur = self.conn.cursor()
        cur.execute("SELECT current_hash FROM audit ORDER BY timestamp DESC, audit_id DESC LIMIT 1")
        row = cur.fetchone()
        last_hash = row[0] if row else None
        # For genesis, previous_hash should be None; otherwise must match last_hash
        if last_hash is None:
            if record.previous_hash is not None:
                raise ValueError(f"AuditTrail.append: genesis record must have previous_hash=None, got {record.previous_hash!r}")
        else:
            if record.previous_hash != last_hash:
                raise ValueError(
                    f"AuditTrail.append: previous_hash {record.previous_hash!r} != last record current_hash {last_hash!r} — out-of-order or tampered"
                )
        # Also ensure current_hash is correct (recompute to verify)
        # Recompute expected hash
        content = {
            "audit_id": record.audit_id,
            "event_type": record.event_type,
            "actor": record.actor,
            "actor_type": record.actor_type,
            "tenant_id": record.tenant_id,
            "client_id": record.client_id,
            "role_id": record.role_id,
            "workflow_id": record.workflow_id,
            "task_id": record.task_id,
            "correlation_id": record.correlation_id,
            "input_ref": record.input_ref,
            "output_ref": record.output_ref,
            "decision": record.decision,
            "approval_decision": record.approval_decision,
            "timestamp": record.timestamp,
            "previous_hash": record.previous_hash,
            "schema_version": record.schema_version,
        }
        content_filtered = {k: v for k, v in content.items() if v is not None}
        expected_hash = _hash_record(content_filtered)
        if expected_hash != record.current_hash:
            raise ValueError(f"AuditTrail.append: current_hash mismatch: expected {expected_hash}, got {record.current_hash}")

        data_json = json.dumps(record.to_dict(), default=str)
        try:
            cur.execute("BEGIN IMMEDIATE")
            cur.execute(
                "INSERT INTO audit (audit_id, previous_hash, current_hash, data, timestamp) VALUES (?, ?, ?, ?, ?)",
                (record.audit_id, record.previous_hash, record.current_hash, data_json, record.timestamp),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            # Check if duplicate audit_id
            cur.execute("SELECT data FROM audit WHERE audit_id = ?", (record.audit_id,))
            row = cur.fetchone()
            if row is not None:
                return AuditRecord(**json.loads(row[0]))  # type: ignore
            raise ValueError(f"AuditTrail.append integrity error: {e}") from e
        except Exception:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        return record

    def list_records(self, limit: int = 100) -> list[AuditRecord]:
        cur = self.conn.cursor()
        cur.execute("SELECT data FROM audit ORDER BY timestamp ASC, audit_id ASC LIMIT ?", (limit,))
        rows = cur.fetchall()
        # This is simplified: we need to reconstruct AuditRecord from dict, but to_dict loses some fields like previous_hash handling
        # Instead, we should store full record dict with all fields
        records = []
        for r in rows:
            data = json.loads(r[0])
            # Reconstruct via AuditRecord fields
            rec = AuditRecord(
                audit_id=data["audit_id"],
                event_type=data["event_type"],
                actor=data["actor"],
                actor_type=data["actor_type"],
                tenant_id=data.get("tenant_id"),
                client_id=data.get("client_id"),
                role_id=data.get("role_id"),
                workflow_id=data.get("workflow_id"),
                task_id=data.get("task_id"),
                correlation_id=data.get("correlation_id"),
                input_ref=data.get("input_ref"),
                output_ref=data.get("output_ref"),
                decision=data["decision"],
                approval_decision=data.get("approval_decision"),
                timestamp=data["timestamp"],
                previous_hash=data.get("previous_hash"),
                current_hash=data["current_hash"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
            records.append(rec)
        return records

    def verify_chain(self) -> tuple[bool, str]:
        """
        Verify hash chain integrity.
        Returns (is_valid, message).
        Checks that each record's previous_hash == previous record's current_hash and current_hash is correct.
        """
        records = self.list_records(limit=10000)
        if not records:
            return True, "empty chain is valid"
        prev_hash = None
        for rec in records:
            if rec.previous_hash != prev_hash:
                return False, f"tamper detected: record {rec.audit_id} previous_hash {rec.previous_hash!r} != expected {prev_hash!r}"
            # Recompute hash
            content = {
                "audit_id": rec.audit_id,
                "event_type": rec.event_type,
                "actor": rec.actor,
                "actor_type": rec.actor_type,
                "tenant_id": rec.tenant_id,
                "client_id": rec.client_id,
                "role_id": rec.role_id,
                "workflow_id": rec.workflow_id,
                "task_id": rec.task_id,
                "correlation_id": rec.correlation_id,
                "input_ref": rec.input_ref,
                "output_ref": rec.output_ref,
                "decision": rec.decision,
                "approval_decision": rec.approval_decision,
                "timestamp": rec.timestamp,
                "previous_hash": rec.previous_hash,
                "schema_version": rec.schema_version,
            }
            content_filtered = {k: v for k, v in content.items() if v is not None}
            expected = _hash_record(content_filtered)
            if expected != rec.current_hash:
                return False, f"tamper detected: record {rec.audit_id} current_hash mismatch"
            prev_hash = rec.current_hash
        return True, f"chain valid with {len(records)} records"

    def clear_for_tests(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM audit")
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


def verify_chain(db_path: str = "security/audit.db") -> tuple[bool, str]:
    trail = AuditTrail(db_path=db_path)
    try:
        return trail.verify_chain()
    finally:
        trail.close()
