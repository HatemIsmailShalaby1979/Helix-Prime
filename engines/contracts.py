"""
Canonical engine adapter contract for Helix Prime Codex C4.

Versioned, typed, local-first. Every adapter returns EngineResult, never raw engine output or cockpit placeholder.
Distinguishes calculated engine output, model-generated recommendation, and human decision. Labels sample/demo vs real.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "1.0"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_payload(payload: Dict[str, Any]) -> str:
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    except Exception:
        canonical = str(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class EngineResult:
    """
    Shared typed result envelope for all six engines.

    - engine_id: e.g., "wfm", "rta", "cx", "b2b", "personnel", "crm"
    - display_name: e.g., "WFM Forecasting / Erlang C"
    - capability_ids: list of capability strings this result covers
    - schema_version / contract_version: both "1.0" for C4
    - input_version / output_version: hash or version of input/output payloads
    - tenant_id / client_id / correlation_id / causation_id / actor / owning_role
    - metrics: calculated engine metrics (dict, deterministic)
    - recommendations: model-generated suggestions (list, may be empty before model)
    - evidence: provenance references (list of EvidenceRef dicts or simple refs)
    - warnings: list of strings for partial/missing data
    - error: None or {code, message} for typed errors (failures-as-data)
    - duration_ms: int
    - data_classification: one of 6 canonical (validated)
    - data_mode: "real" or "sample" (explicit, never mislabel sample as real)
    - is_sample: bool (true if sample/demo)
    """

    engine_id: str
    display_name: str
    capability_ids: List[str]
    schema_version: str
    contract_version: str
    input_version: str
    output_version: str
    tenant_id: Optional[str]
    client_id: Optional[str]
    correlation_id: str
    causation_id: Optional[str]
    actor: str
    owning_role_id: str
    metrics: Dict[str, Any]
    recommendations: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    warnings: List[str]
    error: Optional[Dict[str, str]]
    duration_ms: int
    data_classification: str
    data_mode: str
    is_sample: bool
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "display_name": self.display_name,
            "capability_ids": self.capability_ids,
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "input_version": self.input_version,
            "output_version": self.output_version,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "actor": self.actor,
            "owning_role_id": self.owning_role_id,
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "evidence": self.evidence,
            "warnings": self.warnings,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "data_classification": self.data_classification,
            "data_mode": self.data_mode,
            "is_sample": self.is_sample,
            "timestamp": self.timestamp,
        }

    @classmethod
    def success(
        cls,
        engine_id: str,
        display_name: str,
        capability_ids: List[str],
        tenant_id: Optional[str],
        client_id: Optional[str],
        correlation_id: str,
        causation_id: Optional[str],
        actor: str,
        owning_role_id: str,
        metrics: Dict[str, Any],
        input_payload: Dict[str, Any],
        recommendations: Optional[List[Dict[str, Any]]] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[str]] = None,
        data_classification: str = "internal",
        data_mode: str = "real",
        is_sample: bool = False,
        duration_ms: int = 0,
    ) -> "EngineResult":
        inp_ver = _hash_payload(input_payload or {})
        out_ver = _hash_payload(metrics or {})
        return cls(
            engine_id=engine_id,
            display_name=display_name,
            capability_ids=capability_ids,
            schema_version=SCHEMA_VERSION,
            contract_version=CONTRACT_VERSION,
            input_version=inp_ver,
            output_version=out_ver,
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            metrics=metrics or {},
            recommendations=recommendations or [],
            evidence=evidence or [],
            warnings=warnings or [],
            error=None,
            duration_ms=duration_ms,
            data_classification=data_classification,
            data_mode=data_mode,
            is_sample=is_sample,
        )

    @classmethod
    def failure(
        cls,
        engine_id: str,
        display_name: str,
        capability_ids: List[str],
        tenant_id: Optional[str],
        client_id: Optional[str],
        correlation_id: str,
        causation_id: Optional[str],
        actor: str,
        owning_role_id: str,
        input_payload: Dict[str, Any],
        error_code: str,
        error_message: str,
        warnings: Optional[List[str]] = None,
        data_classification: str = "internal",
        data_mode: str = "real",
        is_sample: bool = False,
        duration_ms: int = 0,
    ) -> "EngineResult":
        inp_ver = _hash_payload(input_payload or {})
        return cls(
            engine_id=engine_id,
            display_name=display_name,
            capability_ids=capability_ids,
            schema_version=SCHEMA_VERSION,
            contract_version=CONTRACT_VERSION,
            input_version=inp_ver,
            output_version=_hash_payload({}),
            tenant_id=tenant_id,
            client_id=client_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            owning_role_id=owning_role_id,
            metrics={},
            recommendations=[],
            evidence=[],
            warnings=warnings or [],
            error={"code": error_code, "message": error_message},
            duration_ms=duration_ms,
            data_classification=data_classification,
            data_mode=data_mode,
            is_sample=is_sample,
        )
