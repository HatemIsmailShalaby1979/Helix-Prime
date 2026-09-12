"""
Versioned event envelope for the sibling-project integration bus (C7).

Sibling repositories (Helix Education, Study Studio, L&D Command Center) are
external services. They never import from Helix Prime, and Helix Prime never
imports from them. The only thing that crosses the boundary is a serialised
:class:`SiblingEventEnvelope` — bytes that either side can validate against the
JSON Schema in ``schemas/`` without sharing a single line of code.

Design constraints
------------------
* Additive versioning only. ``v1`` schemas are frozen for the life of ``v1``.
  A breaking change increments the envelope version; consumers accept every
  version they were built against and reject the rest loudly.
* Tenant/client/correlation context is mandatory on every envelope. An event
  that cannot say whose data it carries is dropped, not guessed at.
* ``data_mode`` travels with the event so a learning plan built on sample data
  can never be mistaken for one built on measured operational data.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

SCHEMA_NAMESPACE = "https://helix.codex/schemas/sibling-events"

#: Envelope versions this build can emit and validate.
SUPPORTED_ENVELOPE_VERSIONS = ("1.0",)

#: Every event type in the v1 contract, with its direction and owning system.
EVENT_DIRECTIONS: Dict[str, str] = {
    "CompetencyGapDetected": "outbound",  # Helix Prime -> ecosystem
    "LearningPlanRequested": "outbound",  # Helix Prime -> Helix Education
    "LearningArtifactReady": "inbound",  # L&D Command Center -> Helix Prime
    "AssessmentCompleted": "inbound",  # Study Studio -> Helix Prime
}

EVENT_OWNERS: Dict[str, str] = {
    "CompetencyGapDetected": "helix_prime",
    "LearningPlanRequested": "helix_prime",
    "LearningArtifactReady": "ld_command_center",
    "AssessmentCompleted": "study_studio",
}

EVENT_TYPES = tuple(sorted(EVENT_DIRECTIONS))

_SEMVER_RE = re.compile(r"^\d+\.\d+$")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def _sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _require_non_empty(value: Any, field_path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_path}: must be a non-empty string, got {value!r}")
    return value.strip()


def _require_mapping(value: Any, field_path: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_path}: must be a mapping, got {type(value).__name__}")
    return dict(value)


@dataclass
class SiblingEventEnvelope:
    """
    Transport-agnostic wrapper around one sibling-project event.

    ``payload_digest`` is computed over the payload only, so a receiver can
    detect tampering or accidental mutation without trusting the sender's
    transport layer.
    """

    event_type: str
    payload: Dict[str, Any]
    tenant_id: str
    client_id: str
    correlation_id: str
    envelope_version: str = "1.0"
    event_id: str = field(default_factory=lambda: f"sev_{uuid.uuid4().hex[:24]}")
    causation_id: Optional[str] = None
    source_system: str = "helix_prime"
    target_system: Optional[str] = None
    data_mode: str = "live"
    data_classification: str = "internal"
    schema_version: str = "1.0"
    occurred_at: str = field(default_factory=_now_iso)
    payload_digest: Optional[str] = None

    def __post_init__(self) -> None:
        self.event_type = _require_non_empty(self.event_type, "SiblingEventEnvelope.event_type")
        if self.event_type not in EVENT_TYPES:
            raise ValueError(
                f"SiblingEventEnvelope.event_type: unknown event {self.event_type!r} "
                f"(known: {list(EVENT_TYPES)})"
            )
        self.payload = _require_mapping(self.payload, "SiblingEventEnvelope.payload")
        self.tenant_id = _require_non_empty(self.tenant_id, "SiblingEventEnvelope.tenant_id")
        self.client_id = _require_non_empty(self.client_id, "SiblingEventEnvelope.client_id")
        self.correlation_id = _require_non_empty(
            self.correlation_id, "SiblingEventEnvelope.correlation_id"
        )
        if self.envelope_version not in SUPPORTED_ENVELOPE_VERSIONS:
            raise ValueError(
                f"SiblingEventEnvelope.envelope_version: {self.envelope_version!r} not supported "
                f"(supported: {list(SUPPORTED_ENVELOPE_VERSIONS)})"
            )
        if self.data_mode not in ("live", "sample", "historical"):
            raise ValueError(
                f"SiblingEventEnvelope.data_mode: must be live|sample|historical, got {self.data_mode!r}"
            )
        if self.data_classification not in (
            "public",
            "internal",
            "client_confidential",
            "personnel_sensitive",
            "financial",
            "regulated_high_risk",
        ):
            raise ValueError(
                f"SiblingEventEnvelope.data_classification: unknown label {self.data_classification!r}"
            )
        # Digest is content-addressed; recompute unless the caller is replaying
        # a previously sealed envelope and the caller's digest already matches.
        computed = _sha256(self.payload)
        if self.payload_digest is None:
            self.payload_digest = computed
        elif self.payload_digest != computed:
            raise ValueError(
                f"SiblingEventEnvelope.payload_digest: {self.payload_digest!r} does not match "
                f"payload content ({computed!r})"
            )

    # ── serialisation ───────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "envelope_version": self.envelope_version,
            "schema_version": self.schema_version,
            "source_system": self.source_system,
            "target_system": self.target_system,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "data_mode": self.data_mode,
            "data_classification": self.data_classification,
            "occurred_at": self.occurred_at,
            "payload": dict(self.payload),
            "payload_digest": self.payload_digest,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SiblingEventEnvelope":
        if not isinstance(data, Mapping):
            raise ValueError(
                f"SiblingEventEnvelope.from_dict: expected mapping, got {type(data).__name__}"
            )
        version = str(data.get("envelope_version", "1.0"))
        if version not in SUPPORTED_ENVELOPE_VERSIONS:
            raise ValueError(
                f"SiblingEventEnvelope.from_dict: unsupported envelope_version {version!r} "
                f"(supported: {list(SUPPORTED_ENVELOPE_VERSIONS)})"
            )
        return cls(
            event_type=data.get("event_type", ""),
            payload=data.get("payload", {}),
            tenant_id=data.get("tenant_id", ""),
            client_id=data.get("client_id", ""),
            correlation_id=data.get("correlation_id", ""),
            envelope_version=version,
            event_id=data.get("event_id") or f"sev_{uuid.uuid4().hex[:24]}",
            causation_id=data.get("causation_id"),
            source_system=data.get("source_system", "helix_prime"),
            target_system=data.get("target_system"),
            data_mode=data.get("data_mode", "live"),
            data_classification=data.get("data_classification", "internal"),
            schema_version=data.get("schema_version", "1.0"),
            occurred_at=data.get("occurred_at") or _now_iso(),
            payload_digest=data.get("payload_digest"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "SiblingEventEnvelope":
        return cls.from_dict(json.loads(raw))

    # ── helpers ─────────────────────────────────────────────────────────────

    @property
    def direction(self) -> str:
        return EVENT_DIRECTIONS[self.event_type]

    @property
    def schema_id(self) -> str:
        return f"{SCHEMA_NAMESPACE}/v{self.schema_version}/{self.event_type}.json"

    def verify(self) -> bool:
        """Recompute the payload digest and confirm the envelope is untampered."""
        return self.payload_digest == _sha256(self.payload)
