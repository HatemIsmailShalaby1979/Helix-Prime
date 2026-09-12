"""
Sibling-project integration contracts (C7).

The three sister systems — Helix Education, Study Studio and the L&D Command
Center — are external services. They exchange versioned events over the bus
defined here. They never import each other's code.

Public surface
--------------
* :class:`SiblingEventEnvelope` — the transport-agnostic wrapper every event
  travels in, with a content digest so receivers can detect tampering.
* :mod:`v1` payload contracts: ``CompetencyGapDetected``,
  ``LearningPlanRequested``, ``LearningArtifactReady``,
  ``AssessmentCompleted``.
* :mod:`boundary` — the executable separation rule (no imports, no vendoring,
  no cross-project datastore reads) plus a CI-ready scanner.
* :mod:`registry` — schema lookup and JSON Schema emission for sibling teams.

Usage
-----
    from control_plane.schemas.sibling_events import (
        SiblingEventEnvelope, dispatch, receive,
    )

    env = dispatch(gap_event, correlation_id=corr)
    wire = env.to_json()          # this is the entire integration surface
    payload = receive(wire)       # validated on the far side
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from control_plane.schemas.sibling_events import boundary, registry
from control_plane.schemas.sibling_events.envelope import (
    EVENT_DIRECTIONS,
    EVENT_OWNERS,
    EVENT_TYPES,
    SCHEMA_NAMESPACE,
    SUPPORTED_ENVELOPE_VERSIONS,
    SiblingEventEnvelope,
)
from control_plane.schemas.sibling_events.v1 import (
    V1,
    V1_EVENT_CLASSES,
    AssessmentCompleted,
    CompetencyGapDetected,
    LearningArtifactReady,
    LearningPlanRequested,
    build_payload,
)

SCHEMA_DIR = "control_plane/schemas/sibling_events/schemas"
CONTRACT_VERSION = "1.0"


def dispatch(payload_obj: Any, correlation_id: str, **kwargs: Any) -> SiblingEventEnvelope:
    """
    Wrap a v1 payload dataclass into a sealed, validated envelope for the bus.

    This is the only sanctioned way for Helix Prime to emit a sibling event.
    """
    to_envelope = getattr(payload_obj, "to_envelope", None)
    if to_envelope is None:
        raise TypeError(
            f"dispatch: {type(payload_obj).__name__} has no to_envelope(); "
            "pass a v1 payload dataclass from this package"
        )
    envelope = to_envelope(correlation_id, **kwargs)
    if not envelope.verify():
        raise ValueError("dispatch: envelope failed its own digest check")
    return envelope


def receive(raw: str | Mapping[str, Any]) -> SiblingEventEnvelope:
    """
    Accept an inbound event: parse, validate the envelope, then validate the
    payload against its v1 contract.

    Raises ``ValueError`` on anything malformed. Inbound data is never trusted
    and never repaired — a bad event is rejected, not coerced.
    """
    envelope = (
        SiblingEventEnvelope.from_json(raw)
        if isinstance(raw, str)
        else SiblingEventEnvelope.from_dict(raw)
    )
    if not envelope.verify():
        raise ValueError(
            f"receive: payload digest mismatch for {envelope.event_type} "
            f"(event_id={envelope.event_id}) — event rejected"
        )
    build_payload(envelope.event_type, envelope.payload)
    return envelope


def event_catalogue() -> Dict[str, Dict[str, str]]:
    """Human-readable catalogue of the v1 contract, for docs and the cockpit."""
    return {
        event_type: {
            "direction": EVENT_DIRECTIONS[event_type],
            "owner": EVENT_OWNERS[event_type],
            "schema": f"{SCHEMA_NAMESPACE}/v{V1}/{event_type}.json",
        }
        for event_type in EVENT_TYPES
    }


__all__ = [
    "AssessmentCompleted",
    "CONTRACT_VERSION",
    "CompetencyGapDetected",
    "EVENT_DIRECTIONS",
    "EVENT_OWNERS",
    "EVENT_TYPES",
    "LearningArtifactReady",
    "LearningPlanRequested",
    "SCHEMA_DIR",
    "SCHEMA_NAMESPACE",
    "SUPPORTED_ENVELOPE_VERSIONS",
    "SiblingEventEnvelope",
    "V1",
    "V1_EVENT_CLASSES",
    "boundary",
    "build_payload",
    "dispatch",
    "event_catalogue",
    "receive",
    "registry",
]
