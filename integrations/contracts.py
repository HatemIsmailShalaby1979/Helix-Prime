"""
Shared integration contracts for Helix Prime sibling-project connections.

Helix Prime Codex owns organization, identity, policy, workflow, evidence, and GM coordination.
Sibling projects are specialized services with their own boundaries:
- Helix Education: event-sourced learning state, competency, progress, assessments, adaptive paths
- Study Studio: learner/content experience and provider-agnostic AI runtime
- L&D Command Center: content production, media/export, career, and L&D workbench workflows

This module defines versioned, validated contracts and events for cross-system communication.
All contracts use C1 SCHEMA_VERSION = "1.0" and follow C3 classification, audit, and authorization controls.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from contracts.task import SCHEMA_VERSION, _require_non_empty_str, _validate_iso_timestamp

# ── Canonical integration identifiers ────────────────────────────────────────
SOURCE_SYSTEM_HELIX_PRIME = "helix-prime"
SOURCE_SYSTEM_HELIX_EDUCATION = "helix-education"
SOURCE_SYSTEM_STUDY_STUDIO = "study-studio"
SOURCE_SYSTEM_LD_COMMAND_CENTER = "ld-command-center"

VALID_SOURCE_SYSTEMS = {
    SOURCE_SYSTEM_HELIX_PRIME,
    SOURCE_SYSTEM_HELIX_EDUCATION,
    SOURCE_SYSTEM_STUDY_STUDIO,
    SOURCE_SYSTEM_LD_COMMAND_CENTER,
}

VALID_TARGET_SYSTEMS = VALID_SOURCE_SYSTEMS.copy()

VALID_EVENT_TYPES = {
    # Competency & Learning (Helix Education ↔ Helix Prime)
    "CompetencyGapDetected",
    "LearningPlanRequested",
    "LearningArtifactReady",
    "AssessmentCompleted",
    "CompetencyUpdated",
    # Content Generation (Study Studio ↔ Helix Prime)
    "ContentGenerationRequested",
    "ContentGenerationCompleted",
    # Media & Export (L&D Command Center ↔ Helix Prime)
    "MediaArtifactRequested",
    "MediaArtifactReady",
    # Career & Signals (L&D Command Center ↔ Helix Prime)
    "CareerLearningSignal",
    # Error/Status
    "IntegrationError",
}

VALID_DATA_CLASSIFICATIONS = {
    "public",
    "internal",
    "client_confidential",
    "personnel_sensitive",
    "financial",
    "regulated",
}

VALID_INTEGRATION_STATUSES = {
    "pending",
    "acknowledged",
    "rejected",
    "completed",
    "dead_letter",
}

VALID_ERROR_CODES = {
    "invalid_source_system",
    "invalid_target_system",
    "invalid_event_type",
    "invalid_data_classification",
    "invalid_schema_version",
    "missing_correlation",
    "tenant_mismatch",
    "unauthorized",
    "sibling_unavailable",
    "malformed_payload",
    "validation_failed",
    "idempotency_conflict",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex


def _validate_source_system(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if s not in VALID_SOURCE_SYSTEMS:
        raise ValueError(f"{field_path}: invalid source_system {s!r}, must be one of {sorted(VALID_SOURCE_SYSTEMS)}")
    return s


def _validate_target_system(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if s not in VALID_TARGET_SYSTEMS:
        raise ValueError(f"{field_path}: invalid target_system {s!r}, must be one of {sorted(VALID_TARGET_SYSTEMS)}")
    return s


def _validate_event_type(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if s not in VALID_EVENT_TYPES:
        raise ValueError(f"{field_path}: invalid event_type {s!r}, must be one of {sorted(VALID_EVENT_TYPES)}")
    return s


def _validate_data_classification(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if s not in VALID_DATA_CLASSIFICATIONS:
        raise ValueError(f"{field_path}: invalid data_classification {s!r}, must be one of {sorted(VALID_DATA_CLASSIFICATIONS)}")
    return s


def _validate_integration_status(value: Any, field_path: str) -> str:
    s = _require_non_empty_str(value, field_path)
    if s not in VALID_INTEGRATION_STATUSES:
        raise ValueError(f"{field_path}: invalid status {s!r}, must be one of {sorted(VALID_INTEGRATION_STATUSES)}")
    return s


# ── Base Integration Event ───────────────────────────────────────────────────

@dataclass
class IntegrationEvent:
    """
    Base event for all sibling-project integration communication.

    Every event carries full traceability: correlation/causation IDs,
    tenant/client isolation, source/target system identity, and evidence references.
    Unknown source/target/classification/schema versions fail closed.
    """
    event_id: str
    event_type: str
    schema_version: str
    source_system: str
    target_system: str
    tenant_id: Optional[str]
    client_id: Optional[str]
    actor: str
    role_id: str
    correlation_id: str
    causation_id: Optional[str]
    idempotency_key: str
    timestamp: str
    data_classification: str
    payload: Dict[str, Any]
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    error: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.event_id = _require_non_empty_str(self.event_id, "IntegrationEvent.event_id")
        self.event_type = _validate_event_type(self.event_type, "IntegrationEvent.event_type")
        self.schema_version = SCHEMA_VERSION  # Enforce canonical version
        self.source_system = _validate_source_system(self.source_system, "IntegrationEvent.source_system")
        self.target_system = _validate_target_system(self.target_system, "IntegrationEvent.target_system")
        if self.tenant_id is not None:
            self.tenant_id = _require_non_empty_str(self.tenant_id, "IntegrationEvent.tenant_id")
        if self.client_id is not None:
            self.client_id = _require_non_empty_str(self.client_id, "IntegrationEvent.client_id")
        if not self.tenant_id and not self.client_id:
            raise ValueError("IntegrationEvent: at least one of tenant_id or client_id must be non-empty")
        self.actor = _require_non_empty_str(self.actor, "IntegrationEvent.actor")
        self.role_id = _require_non_empty_str(self.role_id, "IntegrationEvent.role_id")
        self.correlation_id = _require_non_empty_str(self.correlation_id, "IntegrationEvent.correlation_id")
        if self.causation_id is not None:
            self.causation_id = _require_non_empty_str(self.causation_id, "IntegrationEvent.causation_id")
        self.idempotency_key = _require_non_empty_str(self.idempotency_key, "IntegrationEvent.idempotency_key")
        self.timestamp = _validate_iso_timestamp(self.timestamp, "IntegrationEvent.timestamp")
        self.data_classification = _validate_data_classification(self.data_classification, "IntegrationEvent.data_classification")
        if not isinstance(self.payload, dict):
            raise ValueError(f"IntegrationEvent.payload: must be dict, got {type(self.payload).__name__}")
        if not isinstance(self.evidence_refs, list):
            raise ValueError(f"IntegrationEvent.evidence_refs: must be list, got {type(self.evidence_refs).__name__}")
        for i, ev in enumerate(self.evidence_refs):
            if not isinstance(ev, dict):
                raise ValueError(f"IntegrationEvent.evidence_refs[{i}]: must be dict, got {type(ev).__name__}")
        self.status = _validate_integration_status(self.status, "IntegrationEvent.status")
        if self.error is not None:
            if not isinstance(self.error, dict):
                raise ValueError(f"IntegrationEvent.error: must be dict or null, got {type(self.error).__name__}")
            if "code" in self.error:
                self.error["code"] = _require_non_empty_str(self.error["code"], "IntegrationEvent.error.code")
                if self.error["code"] not in VALID_ERROR_CODES:
                    raise ValueError(f"IntegrationEvent.error.code: {self.error['code']!r} not in {sorted(VALID_ERROR_CODES)}")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "source_system": self.source_system,
            "target_system": self.target_system,
            "actor": self.actor,
            "role_id": self.role_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "timestamp": self.timestamp,
            "data_classification": self.data_classification,
            "payload": self.payload,
            "evidence_refs": self.evidence_refs,
            "status": self.status,
        }
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.client_id is not None:
            d["client_id"] = self.client_id
        if self.causation_id is not None:
            d["causation_id"] = self.causation_id
        if self.error is not None:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntegrationEvent":
        if not isinstance(data, dict):
            raise ValueError(f"IntegrationEvent.from_dict: expected dict, got {type(data).__name__}")
        return cls(
            event_id=data.get("event_id", ""),
            event_type=data.get("event_type", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            source_system=data.get("source_system", ""),
            target_system=data.get("target_system", ""),
            tenant_id=data.get("tenant_id"),
            client_id=data.get("client_id"),
            actor=data.get("actor", ""),
            role_id=data.get("role_id", ""),
            correlation_id=data.get("correlation_id", ""),
            causation_id=data.get("causation_id"),
            idempotency_key=data.get("idempotency_key", ""),
            timestamp=data.get("timestamp", ""),
            data_classification=data.get("data_classification", "internal"),
            payload=data.get("payload", {}),
            evidence_refs=data.get("evidence_refs", []),
            status=data.get("status", "pending"),
            error=data.get("error"),
        )


# ── Competency & Learning Events (Helix Education) ───────────────────────────

@dataclass
class CompetencyGapDetected(IntegrationEvent):
    """Helix Prime → Helix Education: A competency gap was detected for an employee."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["employee_id", "gap_name", "required_level"]:
            if key not in p:
                raise ValueError(f"CompetencyGapDetected.payload missing required field: {key}")


@dataclass
class LearningPlanRequested(IntegrationEvent):
    """Helix Prime → Helix Education: Request a learning plan for a competency gap."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["employee_id", "gap_id", "learning_objectives"]:
            if key not in p:
                raise ValueError(f"LearningPlanRequested.payload missing required field: {key}")


@dataclass
class LearningArtifactReady(IntegrationEvent):
    """Helix Education → Helix Prime: A learning artifact (lesson, content) is ready."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["artifact_id", "artifact_type", "employee_id"]:
            if key not in p:
                raise ValueError(f"LearningArtifactReady.payload missing required field: {key}")


@dataclass
class AssessmentCompleted(IntegrationEvent):
    """Helix Education → Helix Prime: An assessment was completed by an employee."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["assessment_id", "employee_id", "competency_id", "score", "passed"]:
            if key not in p:
                raise ValueError(f"AssessmentCompleted.payload missing required field: {key}")


@dataclass
class CompetencyUpdated(IntegrationEvent):
    """Helix Education → Helix Prime: An employee's competency level was updated."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["employee_id", "competency_id", "old_level", "new_level"]:
            if key not in p:
                raise ValueError(f"CompetencyUpdated.payload missing required field: {key}")


# ── Content Generation Events (Study Studio) ─────────────────────────────────

@dataclass
class ContentGenerationRequested(IntegrationEvent):
    """Helix Prime → Study Studio: Request content generation (lesson, quiz, podcast)."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["request_id", "content_type", "topic", "language", "level"]:
            if key not in p:
                raise ValueError(f"ContentGenerationRequested.payload missing required field: {key}")
        if p["content_type"] not in {"lesson", "quiz", "podcast", "glossary", "podcast_script"}:
            raise ValueError("ContentGenerationRequested.content_type must be one of: lesson, quiz, podcast, glossary, podcast_script")


@dataclass
class ContentGenerationCompleted(IntegrationEvent):
    """Study Studio → Helix Prime: Content generation completed (success or failure)."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["request_id", "content_type", "status"]:
            if key not in p:
                raise ValueError(f"ContentGenerationCompleted.payload missing required field: {key}")
        if p["status"] not in {"completed", "failed", "partial"}:
            raise ValueError("ContentGenerationCompleted.status must be completed, failed, or partial")


# ── Media & Export Events (L&D Command Center) ───────────────────────────────

@dataclass
class MediaArtifactRequested(IntegrationEvent):
    """Helix Prime → L&D Command Center: Request media/export work (audio, video, PDF, etc.)."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["request_id", "artifact_type", "source_ref", "format"]:
            if key not in p:
                raise ValueError(f"MediaArtifactRequested.payload missing required field: {key}")
        if p["artifact_type"] not in {"audio", "video", "pdf", "docx", "pptx", "xlsx", "tts", "podcast"}:
            raise ValueError("MediaArtifactRequested.artifact_type invalid")


@dataclass
class MediaArtifactReady(IntegrationEvent):
    """L&D Command Center → Helix Prime: Media/export artifact is ready."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["request_id", "artifact_id", "artifact_type", "format", "status"]:
            if key not in p:
                raise ValueError(f"MediaArtifactReady.payload missing required field: {key}")
        if p["status"] not in {"completed", "failed", "partial"}:
            raise ValueError("MediaArtifactReady.status must be completed, failed, or partial")


# ── Career & Learning Signals (L&D Command Center) ───────────────────────────

@dataclass
class CareerLearningSignal(IntegrationEvent):
    """L&D Command Center → Helix Prime: Career/learning signal (job match, skill gap, etc.)."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        if "signal_type" not in p:
            raise ValueError("CareerLearningSignal.payload missing required field: signal_type")
        if p["signal_type"] not in {"job_match", "skill_gap", "career_path", "learning_recommendation", "resume_update"}:
            raise ValueError("CareerLearningSignal.signal_type invalid")


# ── Content / Artifact / Signal Type Sets ────────────────────────────────────

VALID_CONTENT_TYPES = {
    "lesson",
    "quiz",
    "podcast",
    "glossary",
    "podcast_script",
}

VALID_ARTIFACT_TYPES = {
    "audio",
    "video",
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "tts",
    "podcast",
}

VALID_SIGNAL_TYPES = {
    "job_match",
    "skill_gap",
    "career_path",
    "learning_recommendation",
    "resume_update",
}

# ── Error Event ──────────────────────────────────────────────────────────────

@dataclass
class IntegrationError(IntegrationEvent):
    """Generic integration error event for dead-letter and retry tracking."""

    def __post_init__(self) -> None:
        super().__post_init__()
        p = self.payload
        for key in ["original_event_id", "error_code", "error_message"]:
            if key not in p:
                raise ValueError(f"IntegrationError.payload missing required field: {key}")
        if p["error_code"] not in VALID_ERROR_CODES:
            raise ValueError(f"IntegrationError.error_code must be one of {sorted(VALID_ERROR_CODES)}")


# ── Event Factory ────────────────────────────────────────────────────────────

def create_integration_event(
    event_type: str,
    source_system: str,
    target_system: str,
    tenant_id: Optional[str],
    client_id: Optional[str],
    actor: str,
    role_id: str,
    correlation_id: str,
    causation_id: Optional[str],
    payload: Dict[str, Any],
    data_classification: str = "internal",
    evidence_refs: Optional[List[Dict[str, Any]]] = None,
) -> IntegrationEvent:
    """Factory to create typed integration events with proper IDs and timestamp."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    event_class = {
        "CompetencyGapDetected": CompetencyGapDetected,
        "LearningPlanRequested": LearningPlanRequested,
        "LearningArtifactReady": LearningArtifactReady,
        "AssessmentCompleted": AssessmentCompleted,
        "CompetencyUpdated": CompetencyUpdated,
        "ContentGenerationRequested": ContentGenerationRequested,
        "ContentGenerationCompleted": ContentGenerationCompleted,
        "MediaArtifactRequested": MediaArtifactRequested,
        "MediaArtifactReady": MediaArtifactReady,
        "CareerLearningSignal": CareerLearningSignal,
        "IntegrationError": IntegrationError,
    }.get(event_type, IntegrationEvent)

    return event_class(
        event_id=_new_id("evt_"),
        event_type=event_type,
        schema_version=SCHEMA_VERSION,
        source_system=source_system,
        target_system=target_system,
        tenant_id=tenant_id,
        client_id=client_id,
        actor=actor,
        role_id=role_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=_new_id("idem_"),
        timestamp=now,
        data_classification=data_classification,
        payload=payload,
        evidence_refs=evidence_refs or [],
        status="pending",
        error=None,
    )


def build_event_from_dict(data: Dict[str, Any]) -> IntegrationEvent:
    """Rebuild a typed IntegrationEvent (subclass) from a dict payload.

    Uses the event_type field to select the concrete subclass so that
    transport round-trips preserve validation and required-field semantics.
    """
    if not isinstance(data, dict):
        raise ValueError(f"build_event_from_dict: expected dict, got {type(data).__name__}")
    event_type = data.get("event_type", "")
    event_class = {
        "CompetencyGapDetected": CompetencyGapDetected,
        "LearningPlanRequested": LearningPlanRequested,
        "LearningArtifactReady": LearningArtifactReady,
        "AssessmentCompleted": AssessmentCompleted,
        "CompetencyUpdated": CompetencyUpdated,
        "ContentGenerationRequested": ContentGenerationRequested,
        "ContentGenerationCompleted": ContentGenerationCompleted,
        "MediaArtifactRequested": MediaArtifactRequested,
        "MediaArtifactReady": MediaArtifactReady,
        "CareerLearningSignal": CareerLearningSignal,
        "IntegrationError": IntegrationError,
    }.get(event_type, IntegrationEvent)
    return event_class.from_dict(data)


# All exported event types
__all__ = [
    "SCHEMA_VERSION",
    "VALID_SOURCE_SYSTEMS",
    "VALID_TARGET_SYSTEMS",
    "VALID_EVENT_TYPES",
    "VALID_DATA_CLASSIFICATIONS",
    "VALID_INTEGRATION_STATUSES",
    "VALID_ERROR_CODES",
    "VALID_CONTENT_TYPES",
    "VALID_ARTIFACT_TYPES",
    "VALID_SIGNAL_TYPES",
    "IntegrationEvent",
    "CompetencyGapDetected",
    "LearningPlanRequested",
    "LearningArtifactReady",
    "AssessmentCompleted",
    "CompetencyUpdated",
    "ContentGenerationRequested",
    "ContentGenerationCompleted",
    "MediaArtifactRequested",
    "MediaArtifactReady",
    "CareerLearningSignal",
    "IntegrationError",
    "create_integration_event",
    "build_event_from_dict",
]