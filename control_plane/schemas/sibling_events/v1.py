"""
Sibling event payload contracts, schema version 1.0 (C7).

Four events close the loop between the operational core and the learning
ecosystem::

    CompetencyGapDetected   helix_prime       -> ecosystem
    LearningPlanRequested   helix_prime       -> Helix Education
    LearningArtifactReady   L&D Command Center -> helix_prime
    AssessmentCompleted     Study Studio      -> helix_prime

Each payload is a plain dataclass that validates on construction and round-trips
through ``to_dict``/``from_dict``. They are deliberately dependency-free: a
sibling repo can copy the JSON Schema from ``schemas/`` and implement these in
any language without importing Helix Prime.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from control_plane.schemas.sibling_events.envelope import (
    SiblingEventEnvelope,
    _require_non_empty,
)

V1 = "1.0"

VALID_SEVERITIES = ("low", "medium", "high", "critical")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _require_number(value: Any, field_path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_path}: must be a number, got {type(value).__name__}")
    return float(value)


def _require_list(value: Any, field_path: str) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_path}: must be a list, got {type(value).__name__}")
    return value


def _require_severity(value: Any, field_path: str) -> str:
    v = _require_non_empty(value, field_path).lower()
    if v not in VALID_SEVERITIES:
        raise ValueError(f"{field_path}: must be one of {list(VALID_SEVERITIES)}, got {value!r}")
    return v


# ── CompetencyGapDetected ───────────────────────────────────────────────────


@dataclass
class CompetencyGapDetected:
    """
    Emitted by the core OS when an operational KPI degrades and the degradation
    is attributable to agent performance rather than volume, tooling or data.

    ``attribution_confidence`` is mandatory: a gap that cannot be attributed
    with confidence is not a training problem and must not generate a learning
    plan. This is what stops the ecosystem from being flooded with coaching
    requests every time a queue dips.
    """

    gap_id: str
    tenant_id: str
    client_id: str
    agent_ref: str
    capability: str
    measured_value: float
    target_value: float
    severity: str
    attribution_confidence: float
    kpis_affected: List[str] = field(default_factory=list)
    observed_window: Optional[str] = None
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    detected_at: str = field(default_factory=_now_iso)
    data_mode: str = "live"
    schema_version: str = V1

    def __post_init__(self) -> None:
        self.gap_id = _require_non_empty(self.gap_id, "CompetencyGapDetected.gap_id")
        self.tenant_id = _require_non_empty(self.tenant_id, "CompetencyGapDetected.tenant_id")
        self.client_id = _require_non_empty(self.client_id, "CompetencyGapDetected.client_id")
        self.agent_ref = _require_non_empty(self.agent_ref, "CompetencyGapDetected.agent_ref")
        self.capability = _require_non_empty(self.capability, "CompetencyGapDetected.capability")
        self.measured_value = _require_number(
            self.measured_value, "CompetencyGapDetected.measured_value"
        )
        self.target_value = _require_number(self.target_value, "CompetencyGapDetected.target_value")
        self.severity = _require_severity(self.severity, "CompetencyGapDetected.severity")
        self.attribution_confidence = _require_number(
            self.attribution_confidence, "CompetencyGapDetected.attribution_confidence"
        )
        if not 0.0 <= self.attribution_confidence <= 1.0:
            raise ValueError(
                "CompetencyGapDetected.attribution_confidence: must be within [0, 1], "
                f"got {self.attribution_confidence}"
            )
        _require_list(self.kpis_affected, "CompetencyGapDetected.kpis_affected")
        _require_list(self.evidence_refs, "CompetencyGapDetected.evidence_refs")

    @property
    def gap_magnitude(self) -> float:
        """Signed shortfall against target. Positive means under target."""
        return self.target_value - self.measured_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gap_id": self.gap_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "agent_ref": self.agent_ref,
            "capability": self.capability,
            "measured_value": self.measured_value,
            "target_value": self.target_value,
            "gap_magnitude": self.gap_magnitude,
            "severity": self.severity,
            "attribution_confidence": self.attribution_confidence,
            "kpis_affected": list(self.kpis_affected),
            "observed_window": self.observed_window,
            "evidence_refs": list(self.evidence_refs),
            "detected_at": self.detected_at,
            "data_mode": self.data_mode,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompetencyGapDetected":
        return cls(
            gap_id=data.get("gap_id", ""),
            tenant_id=data.get("tenant_id", ""),
            client_id=data.get("client_id", ""),
            agent_ref=data.get("agent_ref", ""),
            capability=data.get("capability", ""),
            measured_value=data.get("measured_value"),
            target_value=data.get("target_value"),
            severity=data.get("severity", ""),
            attribution_confidence=data.get("attribution_confidence"),
            kpis_affected=list(data.get("kpis_affected") or []),
            observed_window=data.get("observed_window"),
            evidence_refs=list(data.get("evidence_refs") or []),
            detected_at=data.get("detected_at") or _now_iso(),
            data_mode=data.get("data_mode", "live"),
            schema_version=data.get("schema_version", V1),
        )

    def to_envelope(self, correlation_id: str, **kwargs: Any) -> SiblingEventEnvelope:
        return SiblingEventEnvelope(
            event_type="CompetencyGapDetected",
            payload=self.to_dict(),
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            correlation_id=correlation_id,
            data_mode=self.data_mode,
            **kwargs,
        )


# ── LearningPlanRequested ───────────────────────────────────────────────────


@dataclass
class LearningPlanRequested:
    """
    Ingested by Helix Education to build a personalised study map.

    Carries the gap it is responding to (``gap_id``) so the resulting plan is
    traceable back to the operational event that justified it.
    """

    request_id: str
    tenant_id: str
    client_id: str
    agent_ref: str
    target_capabilities: List[str]
    proficiency_target: float
    deadline: Optional[str] = None
    gap_id: Optional[str] = None
    priority: str = "medium"
    constraints: Dict[str, Any] = field(default_factory=dict)
    requested_at: str = field(default_factory=_now_iso)
    data_mode: str = "live"
    schema_version: str = V1

    def __post_init__(self) -> None:
        self.request_id = _require_non_empty(self.request_id, "LearningPlanRequested.request_id")
        self.tenant_id = _require_non_empty(self.tenant_id, "LearningPlanRequested.tenant_id")
        self.client_id = _require_non_empty(self.client_id, "LearningPlanRequested.client_id")
        self.agent_ref = _require_non_empty(self.agent_ref, "LearningPlanRequested.agent_ref")
        targets = _require_list(
            self.target_capabilities, "LearningPlanRequested.target_capabilities"
        )
        if not targets:
            raise ValueError(
                "LearningPlanRequested.target_capabilities: must contain at least one capability"
            )
        self.target_capabilities = [str(t) for t in targets]
        self.proficiency_target = _require_number(
            self.proficiency_target, "LearningPlanRequested.proficiency_target"
        )
        if not 0.0 <= self.proficiency_target <= 1.0:
            raise ValueError(
                f"LearningPlanRequested.proficiency_target: must be within [0, 1], got {self.proficiency_target}"
            )
        self.priority = _require_severity(self.priority, "LearningPlanRequested.priority")
        if not isinstance(self.constraints, dict):
            raise ValueError("LearningPlanRequested.constraints: must be a mapping")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "agent_ref": self.agent_ref,
            "target_capabilities": list(self.target_capabilities),
            "proficiency_target": self.proficiency_target,
            "deadline": self.deadline,
            "gap_id": self.gap_id,
            "priority": self.priority,
            "constraints": dict(self.constraints),
            "requested_at": self.requested_at,
            "data_mode": self.data_mode,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LearningPlanRequested":
        return cls(
            request_id=data.get("request_id", ""),
            tenant_id=data.get("tenant_id", ""),
            client_id=data.get("client_id", ""),
            agent_ref=data.get("agent_ref", ""),
            target_capabilities=list(data.get("target_capabilities") or []),
            proficiency_target=data.get("proficiency_target"),
            deadline=data.get("deadline"),
            gap_id=data.get("gap_id"),
            priority=data.get("priority", "medium"),
            constraints=dict(data.get("constraints") or {}),
            requested_at=data.get("requested_at") or _now_iso(),
            data_mode=data.get("data_mode", "live"),
            schema_version=data.get("schema_version", V1),
        )

    def to_envelope(self, correlation_id: str, **kwargs: Any) -> SiblingEventEnvelope:
        return SiblingEventEnvelope(
            event_type="LearningPlanRequested",
            payload=self.to_dict(),
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            correlation_id=correlation_id,
            target_system="helix_education",
            data_mode=self.data_mode,
            **kwargs,
        )


# ── LearningArtifactReady ───────────────────────────────────────────────────


@dataclass
class LearningArtifactReady:
    """
    Emitted by the L&D Command Center when training content for a gap exists.

    ``artifact_locator`` is a reference, never embedded content. Sibling systems
    exchange pointers; payloads stay small and no training material is copied
    into the operational database.
    """

    artifact_id: str
    tenant_id: str
    client_id: str
    request_id: str
    artifact_type: str
    artifact_locator: str
    covers_capabilities: List[str] = field(default_factory=list)
    estimated_duration_minutes: Optional[int] = None
    content_digest: Optional[str] = None
    produced_by: str = "ld_command_center"
    produced_at: str = field(default_factory=_now_iso)
    data_mode: str = "live"
    schema_version: str = V1

    def __post_init__(self) -> None:
        self.artifact_id = _require_non_empty(self.artifact_id, "LearningArtifactReady.artifact_id")
        self.tenant_id = _require_non_empty(self.tenant_id, "LearningArtifactReady.tenant_id")
        self.client_id = _require_non_empty(self.client_id, "LearningArtifactReady.client_id")
        self.request_id = _require_non_empty(self.request_id, "LearningArtifactReady.request_id")
        self.artifact_type = _require_non_empty(
            self.artifact_type, "LearningArtifactReady.artifact_type"
        )
        self.artifact_locator = _require_non_empty(
            self.artifact_locator, "LearningArtifactReady.artifact_locator"
        )
        _require_list(self.covers_capabilities, "LearningArtifactReady.covers_capabilities")
        if self.estimated_duration_minutes is not None:
            if isinstance(self.estimated_duration_minutes, bool) or not isinstance(
                self.estimated_duration_minutes, int
            ):
                raise ValueError("LearningArtifactReady.estimated_duration_minutes: must be an int")
            if self.estimated_duration_minutes <= 0:
                raise ValueError("LearningArtifactReady.estimated_duration_minutes: must be > 0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "request_id": self.request_id,
            "artifact_type": self.artifact_type,
            "artifact_locator": self.artifact_locator,
            "covers_capabilities": list(self.covers_capabilities),
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "content_digest": self.content_digest,
            "produced_by": self.produced_by,
            "produced_at": self.produced_at,
            "data_mode": self.data_mode,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LearningArtifactReady":
        return cls(
            artifact_id=data.get("artifact_id", ""),
            tenant_id=data.get("tenant_id", ""),
            client_id=data.get("client_id", ""),
            request_id=data.get("request_id", ""),
            artifact_type=data.get("artifact_type", ""),
            artifact_locator=data.get("artifact_locator", ""),
            covers_capabilities=list(data.get("covers_capabilities") or []),
            estimated_duration_minutes=data.get("estimated_duration_minutes"),
            content_digest=data.get("content_digest"),
            produced_by=data.get("produced_by", "ld_command_center"),
            produced_at=data.get("produced_at") or _now_iso(),
            data_mode=data.get("data_mode", "live"),
            schema_version=data.get("schema_version", V1),
        )

    def to_envelope(self, correlation_id: str, **kwargs: Any) -> SiblingEventEnvelope:
        return SiblingEventEnvelope(
            event_type="LearningArtifactReady",
            payload=self.to_dict(),
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            correlation_id=correlation_id,
            source_system="ld_command_center",
            target_system="helix_prime",
            data_mode=self.data_mode,
            **kwargs,
        )


# ── AssessmentCompleted ─────────────────────────────────────────────────────


@dataclass
class AssessmentCompleted:
    """
    Ingested by Helix Prime from Study Studio after an agent is assessed.

    ``qualification_token`` is Study Studio's signed statement of the resulting
    competency level. Helix Prime stores the token, not the claim: the token is
    what lets WFM and L&D later prove that a staffing or coaching decision was
    based on an assessment that actually happened.
    """

    assessment_id: str
    tenant_id: str
    client_id: str
    agent_ref: str
    capability: str
    score: float
    passed: bool
    qualification_token: str
    request_id: Optional[str] = None
    artifact_id: Optional[str] = None
    assessed_at: str = field(default_factory=_now_iso)
    token_expires_at: Optional[str] = None
    data_mode: str = "live"
    schema_version: str = V1

    def __post_init__(self) -> None:
        self.assessment_id = _require_non_empty(
            self.assessment_id, "AssessmentCompleted.assessment_id"
        )
        self.tenant_id = _require_non_empty(self.tenant_id, "AssessmentCompleted.tenant_id")
        self.client_id = _require_non_empty(self.client_id, "AssessmentCompleted.client_id")
        self.agent_ref = _require_non_empty(self.agent_ref, "AssessmentCompleted.agent_ref")
        self.capability = _require_non_empty(self.capability, "AssessmentCompleted.capability")
        self.score = _require_number(self.score, "AssessmentCompleted.score")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"AssessmentCompleted.score: must be within [0, 1], got {self.score}")
        if not isinstance(self.passed, bool):
            raise ValueError(
                f"AssessmentCompleted.passed: must be a bool, got {type(self.passed).__name__}"
            )
        self.qualification_token = _require_non_empty(
            self.qualification_token, "AssessmentCompleted.qualification_token"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "assessment_id": self.assessment_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "agent_ref": self.agent_ref,
            "capability": self.capability,
            "score": self.score,
            "passed": self.passed,
            "qualification_token": self.qualification_token,
            "request_id": self.request_id,
            "artifact_id": self.artifact_id,
            "assessed_at": self.assessed_at,
            "token_expires_at": self.token_expires_at,
            "data_mode": self.data_mode,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssessmentCompleted":
        return cls(
            assessment_id=data.get("assessment_id", ""),
            tenant_id=data.get("tenant_id", ""),
            client_id=data.get("client_id", ""),
            agent_ref=data.get("agent_ref", ""),
            capability=data.get("capability", ""),
            score=data.get("score"),
            passed=bool(data.get("passed", False)),
            qualification_token=data.get("qualification_token", ""),
            request_id=data.get("request_id"),
            artifact_id=data.get("artifact_id"),
            assessed_at=data.get("assessed_at") or _now_iso(),
            token_expires_at=data.get("token_expires_at"),
            data_mode=data.get("data_mode", "live"),
            schema_version=data.get("schema_version", V1),
        )

    def to_envelope(self, correlation_id: str, **kwargs: Any) -> SiblingEventEnvelope:
        return SiblingEventEnvelope(
            event_type="AssessmentCompleted",
            payload=self.to_dict(),
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            correlation_id=correlation_id,
            source_system="study_studio",
            target_system="helix_prime",
            data_mode=self.data_mode,
            **kwargs,
        )


V1_EVENT_CLASSES = {
    "CompetencyGapDetected": CompetencyGapDetected,
    "LearningPlanRequested": LearningPlanRequested,
    "LearningArtifactReady": LearningArtifactReady,
    "AssessmentCompleted": AssessmentCompleted,
}


def build_payload(event_type: str, data: Mapping[str, Any]):
    """Construct the v1 payload dataclass for ``event_type`` from a mapping."""
    try:
        cls = V1_EVENT_CLASSES[event_type]
    except KeyError:
        raise ValueError(
            f"build_payload: unknown event_type {event_type!r} (known: {sorted(V1_EVENT_CLASSES)})"
        ) from None
    return cls.from_dict(data)
