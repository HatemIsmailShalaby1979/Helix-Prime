"""Governed organizational memory (Prompt 7).

A local-first, deterministic, file-backed memory boundary that replaces the
previous in-memory outcome store. It is the single governed store for the whole
organizational memory surface:

* record kinds: decision, recommendation, approval, outcome, failure, correction,
  policy, customer_context, workflow_history
* epistemic nature: verified_fact, user_claim, model_inference, simulated_event,
  historical_event, verified_outcome

Controls (all enforced locally, no cloud, no paid vector DB):
* tenant-isolated retrieval (tenant_id is mandatory on every read)
* classification-aware retrieval (clearance ordering)
* provenance preservation (every record carries provenance)
* correction & supersession (additive, never mutates the original ledger line)
* retention handling (expiry is flagged, never silently dropped)
* audit recording (append-only ledger with a SHA-256 hash chain)
* no unverified inference presented as fact (nature is explicit; facts queryable)
* no cross-tenant leakage (reads are scoped; global dumps rejected)
* no silent memory deletion (deletes are soft + audited; data persists)
* no automatic policy/behavior changes (memory is read-only for behavior)

Determinism: no wall-clock, no RNG. Callers supply `timestamp` and `correlation_id`.
Record IDs are `mem-{seq:06d}` derived from ledger position.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

CLASSIFICATION_LEVELS = ("public", "internal", "client_confidential", "restricted")
NATURES = (
    "verified_fact",
    "user_claim",
    "model_inference",
    "simulated_event",
    "historical_event",
    "verified_outcome",
)
KINDS = (
    "decision",
    "recommendation",
    "approval",
    "outcome",
    "failure",
    "correction",
    "policy",
    "customer_context",
    "workflow_history",
)
GENESIS_HASH = "0" * 64
_VERIFIED_NATURES = ("verified_fact", "verified_outcome")


@dataclass
class MemoryRecord:
    record_id: str
    kind: str
    nature: str
    tenant_id: str
    client_id: str
    actor: str
    role_id: str
    source: str
    classification: str
    timestamp: str
    correlation_id: str
    confidence: float
    evidence_refs: list = field(default_factory=list)
    data_mode: str = "simulated_realistic"
    retention_status: str = "active"
    retention_until: Optional[str] = None
    provenance: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    corrects: Optional[str] = None
    supersedes: Optional[str] = None
    deleted: Optional[str] = None
    # populated in-memory on load; NOT persisted (reconstructed from ledger)
    supersession: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "kind": self.kind,
            "nature": self.nature,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "actor": self.actor,
            "role_id": self.role_id,
            "source": self.source,
            "classification": self.classification,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "data_mode": self.data_mode,
            "retention_status": self.retention_status,
            "retention_until": self.retention_until,
            "provenance": dict(self.provenance),
            "body": dict(self.body),
            "corrects": self.corrects,
            "supersedes": self.supersedes,
            "deleted": self.deleted,
        }

    def is_verified_fact(self) -> bool:
        return self.nature in _VERIFIED_NATURES


_REC_FIELDS = tuple(MemoryRecord.__dataclass_fields__.keys())  # type: ignore[attr-defined]


class MemoryTamperError(Exception):
    """Raised when the audit hash chain does not verify."""


def _level(classification: str) -> int:
    if classification not in CLASSIFICATION_LEVELS:
        raise ValueError(f"unknown classification {classification!r}")
    return CLASSIFICATION_LEVELS.index(classification)


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


class GovernedMemory:
    """Append-only, tenant-isolated, classification-aware governed memory.

    If ``path`` is given, the ledger is persisted as JSONL (one envelope per
    line). If ``path`` is None, the store is in-memory only (still deterministic).
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self._ledger: list[dict] = []  # envelopes: {record, prev_hash, hash}
        self._records: list[MemoryRecord] = []
        self._by_id: dict[str, MemoryRecord] = {}
        # Memory is strictly read-only for system behavior. Storing a `policy`
        # record never changes retrieval or behavior automatically.
        self.auto_apply_policies = False
        if path and os.path.exists(path):
            self._load()

    # ------------------------------------------------------------- persistence
    def _load(self) -> None:
        assert self.path is not None
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                env = json.loads(line)
                self._ledger.append(env)
                rec = MemoryRecord(**env["record"])
                self._records.append(rec)
                self._by_id[rec.record_id] = rec
        self._rebuild_supersession()

    def _rebuild_supersession(self) -> None:
        for rec in self._records:
            rec.supersession = []
        for rec in self._records:
            if rec.corrects and rec.corrects in self._by_id:
                self._by_id[rec.corrects].supersession.append(
                    {"record_id": rec.record_id, "relation": "corrects", "reason": rec.body.get("reason")}
                )
            if rec.supersedes and rec.supersedes in self._by_id:
                self._by_id[rec.supersedes].supersession.append(
                    {"record_id": rec.record_id, "relation": "supersedes", "reason": rec.body.get("reason")}
                )
            if rec.deleted and rec.deleted.startswith("superseded_by:"):
                target = rec.deleted.split(":", 1)[1]
                if target in self._by_id:
                    self._by_id[target].supersession.append(
                        {"record_id": rec.record_id, "relation": "superseded_by", "reason": rec.body.get("reason")}
                    )

    def _append_envelope(self, env: dict) -> None:
        self._ledger.append(env)
        rec = MemoryRecord(**env["record"])
        self._records.append(rec)
        self._by_id[rec.record_id] = rec
        if rec.corrects and rec.corrects in self._by_id:
            self._by_id[rec.corrects].supersession.append(
                {"record_id": rec.record_id, "relation": "corrects", "reason": rec.body.get("reason")}
            )
        if rec.supersedes and rec.supersedes in self._by_id:
            self._by_id[rec.supersedes].supersession.append(
                {"record_id": rec.record_id, "relation": "supersedes", "reason": rec.body.get("reason")}
            )
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(env, default=str) + "\n")

    # ------------------------------------------------------------------- writes
    def add(
        self,
        *,
        kind: str,
        nature: str,
        tenant_id: str,
        client_id: str,
        actor: str,
        role_id: str,
        source: str,
        classification: str,
        timestamp: str,
        correlation_id: str,
        confidence: float,
        evidence_refs: Optional[Sequence[str]] = None,
        data_mode: str = "simulated_realistic",
        retention_status: str = "active",
        retention_until: Optional[str] = None,
        provenance: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
        corrects: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> MemoryRecord:
        if kind not in KINDS:
            raise ValueError(f"unknown record kind {kind!r}")
        if nature not in NATURES:
            raise ValueError(f"unknown nature {nature!r}")
        _level(classification)  # validate
        if not tenant_id:
            raise ValueError("tenant_id is required")
        seq = len(self._records) + 1
        rec = MemoryRecord(
            record_id=f"mem-{seq:06d}",
            kind=kind,
            nature=nature,
            tenant_id=tenant_id,
            client_id=client_id,
            actor=actor,
            role_id=role_id,
            source=source,
            classification=classification,
            timestamp=timestamp,
            correlation_id=correlation_id,
            confidence=float(confidence),
            evidence_refs=list(evidence_refs or []),
            data_mode=data_mode,
            retention_status=retention_status,
            retention_until=retention_until,
            provenance=dict(provenance or {}),
            body=dict(body or {}),
            corrects=corrects,
            supersedes=supersedes,
        )
        prev_hash = self._ledger[-1]["hash"] if self._ledger else GENESIS_HASH
        payload = rec.to_dict()
        h = hashlib.sha256((_canonical(payload) + "|" + prev_hash).encode("utf-8")).hexdigest()
        self._append_envelope({"record": payload, "prev_hash": prev_hash, "hash": h})
        return rec

    def correct(
        self,
        *,
        record_id: str,
        actor: str,
        role_id: str,
        reason: str,
        correction_body: Mapping[str, Any],
        nature: str = "user_claim",
        classification: str = "client_confidential",
        correlation_id: str = "",
        timestamp: str,
        confidence: float = 1.0,
        evidence_refs: Optional[Sequence[str]] = None,
        data_mode: str = "simulated_realistic",
        source: str = "memory_correction",
    ) -> MemoryRecord:
        target = self._require(record_id)
        rec = self.add(
            kind="correction",
            nature=nature,
            tenant_id=target.tenant_id,
            client_id=target.client_id,
            actor=actor,
            role_id=role_id,
            source=source,
            classification=classification,
            timestamp=timestamp,
            correlation_id=correlation_id or target.correlation_id,
            confidence=confidence,
            evidence_refs=evidence_refs,
            data_mode=data_mode,
            provenance={"correlation_id": correlation_id or target.correlation_id, "data_mode": data_mode,
                        "basis": "correction", "sources": [target.record_id]},
            body={"reason": reason, "corrects": record_id, **dict(correction_body)},
            corrects=record_id,
        )
        target.retention_status = "corrected"
        return rec

    def supersede(
        self,
        *,
        record_id: str,
        actor: str,
        role_id: str,
        reason: str,
        superseding_body: Mapping[str, Any],
        nature: str,
        classification: str,
        correlation_id: str,
        timestamp: str,
        confidence: float,
        evidence_refs: Optional[Sequence[str]] = None,
        data_mode: str = "simulated_realistic",
        source: str = "memory_supersession",
    ) -> MemoryRecord:
        target = self._require(record_id)
        rec = self.add(
            kind=target.kind,
            nature=nature,
            tenant_id=target.tenant_id,
            client_id=target.client_id,
            actor=actor,
            role_id=role_id,
            source=source,
            classification=classification,
            timestamp=timestamp,
            correlation_id=correlation_id,
            confidence=confidence,
            evidence_refs=evidence_refs,
            data_mode=data_mode,
            provenance={"correlation_id": correlation_id, "data_mode": data_mode,
                        "basis": "supersession", "sources": [target.record_id]},
            body={"reason": reason, "supersedes": record_id, **dict(superseding_body)},
            supersedes=record_id,
        )
        target.retention_status = "superseded"
        return rec

    def delete(self, *, record_id: str, actor: str, role_id: str, reason: str,
               timestamp: str, correlation_id: str = "") -> MemoryRecord:
        """Soft delete. The original record is flagged + audited but NEVER removed
        from the ledger (no silent deletion). Retrieval excludes it by default."""
        target = self._require(record_id)
        if target.deleted:
            return target
        target.deleted = reason
        target.retention_status = "deleted"
        rec = self.add(
            kind="workflow_history",
            nature="verified_outcome",
            tenant_id=target.tenant_id,
            client_id=target.client_id,
            actor=actor,
            role_id=role_id,
            source="memory_delete",
            classification=target.classification,
            timestamp=timestamp,
            correlation_id=correlation_id or target.correlation_id,
            confidence=1.0,
            evidence_refs=[target.record_id],
            data_mode=target.data_mode,
            provenance={"correlation_id": correlation_id or target.correlation_id,
                        "data_mode": target.data_mode, "basis": "delete", "sources": [target.record_id]},
            body={"action": "delete", "target": record_id, "reason": reason},
        )
        return rec

    # --------------------------------------------------------------- retrieval
    def _require(self, record_id: str) -> MemoryRecord:
        if record_id not in self._by_id:
            raise KeyError(f"no such record {record_id!r}")
        return self._by_id[record_id]

    def retrieve(
        self,
        *,
        tenant_id: str,
        client_id: Optional[str] = None,
        kinds: Optional[Sequence[str]] = None,
        max_classification: Optional[str] = None,
        include_deleted: bool = False,
        include_expired: bool = True,
        verified_only: bool = False,
    ) -> list[MemoryRecord]:
        """Tenant-scoped retrieval. ``tenant_id`` is mandatory — a missing or empty
        tenant_id is rejected to prevent accidental cross-tenant exposure."""
        if not tenant_id:
            raise ValueError("tenant_id is required for retrieval (no cross-tenant reads)")
        max_lvl = _level(max_classification) if max_classification else len(CLASSIFICATION_LEVELS) - 1
        out = []
        for rec in self._records:
            if rec.tenant_id != tenant_id:
                continue
            if client_id is not None and rec.client_id != client_id:
                continue
            if kinds is not None and rec.kind not in set(kinds):
                continue
            if _level(rec.classification) > max_lvl:
                continue
            if rec.deleted and not include_deleted:
                continue
            if rec.retention_status == "expired" and not include_expired:
                continue
            if verified_only and not rec.is_verified_fact():
                continue
            out.append(rec)
        return out

    def retrieve_facts(self, *, tenant_id: str, **kw: Any) -> list[MemoryRecord]:
        """Only verified facts/outcomes — never returns unverified inference."""
        return self.retrieve(tenant_id=tenant_id, verified_only=True, **kw)

    # --------------------------------------------------------------- retention
    def apply_retention(self, as_of: str) -> int:
        """Flag records past ``retention_until`` as expired. They are NOT deleted."""
        count = 0
        for rec in self._records:
            if rec.retention_status in ("deleted", "retained", "expired"):
                continue
            if rec.retention_until and as_of > rec.retention_until:
                rec.retention_status = "expired"
                count += 1
        return count

    # ------------------------------------------------------------------- audit
    def verify_chain(self) -> tuple[bool, str]:
        prev = GENESIS_HASH
        for env in self._ledger:
            payload = env["record"]
            expected = hashlib.sha256(
                (_canonical(payload) + "|" + prev).encode("utf-8")
            ).hexdigest()
            if env.get("prev_hash") != prev or env.get("hash") != expected:
                return False, f"chain broken at {payload.get('record_id')}"
            prev = env["hash"]
        return True, "chain intact"

    def audit_status(self) -> str:
        if self.path is None:
            return "in_memory_not_persisted"
        ok, _ = self.verify_chain()
        return "verified" if ok else "broken"

    # ---------------------------------------------------------- demo utilities
    def clear_for_demo(self, *, actor: str, role_id: str, timestamp: str,
                       correlation_id: str = "demo-reset") -> MemoryRecord:
        """Explicit, audited synthetic-demo reset. Soft-deletes every active record
        (data persists in the ledger) and records a reset marker. Never silently
        destroys data."""
        for rec in list(self._records):
            if not rec.deleted and rec.retention_status not in ("deleted", "expired"):
                self.delete(record_id=rec.record_id, actor=actor, role_id=role_id,
                            reason="synthetic demo reset", timestamp=timestamp,
                            correlation_id=correlation_id)
        return self.add(
            kind="workflow_history",
            nature="verified_outcome",
            tenant_id="*demo*",
            client_id="*demo*",
            actor=actor,
            role_id=role_id,
            source="memory_reset",
            classification="internal",
            timestamp=timestamp,
            correlation_id=correlation_id,
            confidence=1.0,
            evidence_refs=[],
            data_mode="simulated_realistic",
            body={"action": "reset", "reason": "synthetic demo reset"},
        )
