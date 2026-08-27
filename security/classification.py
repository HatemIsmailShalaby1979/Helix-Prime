"""
Data classification for Helix Prime Codex C3.

Canonical classifications (one source of truth):
- public
- internal
- client_confidential
- personnel_sensitive
- financial
- regulated_high_risk

Unknown classifications must fail closed (ValueError).
Validation is typed and deterministic for task payloads, evidence, logs, workflow outputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class DataClassification:
    PUBLIC = "public"
    INTERNAL = "internal"
    CLIENT_CONFIDENTIAL = "client_confidential"
    PERSONNEL_SENSITIVE = "personnel_sensitive"
    FINANCIAL = "financial"
    REGULATED_HIGH_RISK = "regulated_high_risk"

    ALL = {
        PUBLIC,
        INTERNAL,
        CLIENT_CONFIDENTIAL,
        PERSONNEL_SENSITIVE,
        FINANCIAL,
        REGULATED_HIGH_RISK,
    }

    # Ordered by sensitivity (for future retention/policy)
    SENSITIVITY_ORDER = [
        PUBLIC,
        INTERNAL,
        CLIENT_CONFIDENTIAL,
        FINANCIAL,
        PERSONNEL_SENSITIVE,
        REGULATED_HIGH_RISK,
    ]


def is_valid_classification(value: str) -> bool:
    return value in DataClassification.ALL


def _require_valid_classification(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: classification must be non-empty string, got {value!r}")
    v = value.strip().lower()
    if v not in DataClassification.ALL:
        raise ValueError(f"{field_path}: unknown classification {value!r} — fail closed (allowed: {sorted(DataClassification.ALL)})")
    return v


@dataclass
class ClassificationMetadata:
    classification: str
    reason: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    source: Optional[str] = None

    def __post_init__(self) -> None:
        self.classification = _require_valid_classification(self.classification, "ClassificationMetadata.classification")
        if self.reason is not None:
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise ValueError(f"ClassificationMetadata.reason: must be non-empty string or None, got {self.reason!r}")
            self.reason = self.reason.strip()
        if self.tenant_id is not None:
            if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
                raise ValueError(f"ClassificationMetadata.tenant_id: must be non-empty string or None, got {self.tenant_id!r}")
            self.tenant_id = self.tenant_id.strip()
        if self.client_id is not None:
            if not isinstance(self.client_id, str) or not self.client_id.strip():
                raise ValueError(f"ClassificationMetadata.client_id: must be non-empty string or None, got {self.client_id!r}")
            self.client_id = self.client_id.strip()
        if self.source is not None:
            if not isinstance(self.source, str) or not self.source.strip():
                raise ValueError(f"ClassificationMetadata.source: must be non-empty string or None, got {self.source!r}")
            self.source = self.source.strip()

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"classification": self.classification}
        if self.reason is not None:
            d["reason"] = self.reason
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.source is not None:
            d["source"] = self.source
        return d


def validate_payload_classification(
    payload: Dict[str, Any],
    classification: str,
    field_path: str = "payload",
) -> str:
    """
    Validate that a payload's classification is known and consistent.
    - Unknown classification fails closed (ValueError)
    - Payload must be dict
    - If payload contains 'data_classification' field, it must match the provided classification
    """
    if not isinstance(payload, dict):
        raise ValueError(f"{field_path}: must be dict, got {type(payload).__name__}")
    cls = _require_valid_classification(classification, f"{field_path}.classification")
    # If payload embeds classification, ensure it matches
    embedded = payload.get("data_classification")
    if embedded is not None:
        emb = _require_valid_classification(embedded, f"{field_path}.data_classification")
        if emb != cls:
            raise ValueError(f"{field_path}: embedded classification {emb!r} != declared {cls!r} — fail closed")
    return cls


def validate_evidence_classification(evidence: Any, classification: str) -> str:
    """Validate evidence classification (for EvidenceRef, logs, workflow outputs)."""
    return _require_valid_classification(classification, "evidence.classification")


def classify_for_tenant_client(
    payload: Dict[str, Any],
    tenant_id: Optional[str],
    client_id: Optional[str],
) -> str:
    """
    Helper: infer classification from tenant/client context.
    For C3, this is a simple heuristic for tests:
    - if client_id contains "personnel" or payload has personnel fields → personnel_sensitive
    - if payload has financial fields → financial
    - if tenant is set and client is set → client_confidential (default for workflows)
    - else internal
    This is not a production classifier; it's a deterministic seam for C4/C5.
    """
    payload_str = str(payload).lower()
    if "salary" in payload_str or "ssn" in payload_str or "personnel" in payload_str:
        return DataClassification.PERSONNEL_SENSITIVE
    if "revenue" in payload_str or "financial" in payload_str or "leakage" in payload_str:
        return DataClassification.FINANCIAL
    if tenant_id and client_id:
        return DataClassification.CLIENT_CONFIDENTIAL
    return DataClassification.INTERNAL
