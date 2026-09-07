"""
Schema registry for the sibling event bus (C7).

Sibling teams need the contract without needing this repository. This module
generates JSON Schema documents from the v1 dataclasses and writes them to
``schemas/``, so a sibling can validate against a static file in any language.

Registry rules
--------------
* A schema version, once published, is frozen. Changing a field's meaning
  requires a new version, not an edit.
* Every schema declares ``additionalProperties: false``. Unknown fields are a
  contract violation, because silently ignoring them is how two systems drift
  apart without either one failing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from control_plane.schemas.sibling_events import v1
from control_plane.schemas.sibling_events.envelope import (
    EVENT_DIRECTIONS,
    EVENT_OWNERS,
    SCHEMA_NAMESPACE,
)

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
PUBLISHED_VERSIONS = ("1.0",)

#: Hand-maintained field contracts. Kept explicit rather than reflected off the
#: dataclasses so an accidental type change shows up as a test failure instead
#: of silently rewriting the published contract.
_EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "CompetencyGapDetected": {
        "required": [
            "schema_version",
            "gap_id",
            "tenant_id",
            "client_id",
            "agent_ref",
            "capability",
            "measured_value",
            "target_value",
            "severity",
            "attribution_confidence",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "gap_id": {"type": "string", "minLength": 1},
            "tenant_id": {"type": "string", "minLength": 1},
            "client_id": {"type": "string", "minLength": 1},
            "agent_ref": {"type": "string", "minLength": 1},
            "capability": {"type": "string", "minLength": 1},
            "measured_value": {"type": "number"},
            "target_value": {"type": "number"},
            "gap_magnitude": {"type": "number"},
            "severity": {"type": "string", "enum": list(v1.VALID_SEVERITIES)},
            "attribution_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "kpis_affected": {"type": "array", "items": {"type": "string"}},
            "observed_window": {"type": ["string", "null"]},
            "evidence_refs": {"type": "array", "items": {"type": "object"}},
            "detected_at": {"type": "string"},
            "data_mode": {"type": "string", "enum": ["live", "sample", "historical"]},
        },
    },
    "LearningPlanRequested": {
        "required": [
            "schema_version",
            "request_id",
            "tenant_id",
            "client_id",
            "agent_ref",
            "target_capabilities",
            "proficiency_target",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "request_id": {"type": "string", "minLength": 1},
            "tenant_id": {"type": "string", "minLength": 1},
            "client_id": {"type": "string", "minLength": 1},
            "agent_ref": {"type": "string", "minLength": 1},
            "target_capabilities": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "proficiency_target": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "deadline": {"type": ["string", "null"]},
            "gap_id": {"type": ["string", "null"]},
            "priority": {"type": "string", "enum": list(v1.VALID_SEVERITIES)},
            "constraints": {"type": "object"},
            "requested_at": {"type": "string"},
            "data_mode": {"type": "string", "enum": ["live", "sample", "historical"]},
        },
    },
    "LearningArtifactReady": {
        "required": [
            "schema_version",
            "artifact_id",
            "tenant_id",
            "client_id",
            "request_id",
            "artifact_type",
            "artifact_locator",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "artifact_id": {"type": "string", "minLength": 1},
            "tenant_id": {"type": "string", "minLength": 1},
            "client_id": {"type": "string", "minLength": 1},
            "request_id": {"type": "string", "minLength": 1},
            "artifact_type": {"type": "string", "minLength": 1},
            "artifact_locator": {"type": "string", "minLength": 1},
            "covers_capabilities": {"type": "array", "items": {"type": "string"}},
            "estimated_duration_minutes": {"type": ["integer", "null"], "exclusiveMinimum": 0},
            "content_digest": {"type": ["string", "null"]},
            "produced_by": {"type": "string"},
            "produced_at": {"type": "string"},
            "data_mode": {"type": "string", "enum": ["live", "sample", "historical"]},
        },
    },
    "AssessmentCompleted": {
        "required": [
            "schema_version",
            "assessment_id",
            "tenant_id",
            "client_id",
            "agent_ref",
            "capability",
            "score",
            "passed",
            "qualification_token",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": "1.0"},
            "assessment_id": {"type": "string", "minLength": 1},
            "tenant_id": {"type": "string", "minLength": 1},
            "client_id": {"type": "string", "minLength": 1},
            "agent_ref": {"type": "string", "minLength": 1},
            "capability": {"type": "string", "minLength": 1},
            "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "passed": {"type": "boolean"},
            "qualification_token": {"type": "string", "minLength": 1},
            "request_id": {"type": ["string", "null"]},
            "artifact_id": {"type": ["string", "null"]},
            "assessed_at": {"type": "string"},
            "token_expires_at": {"type": ["string", "null"]},
            "data_mode": {"type": "string", "enum": ["live", "sample", "historical"]},
        },
    },
}

_ENVELOPE_SCHEMA: Dict[str, Any] = {
    "required": [
        "event_id",
        "event_type",
        "envelope_version",
        "tenant_id",
        "client_id",
        "correlation_id",
        "payload",
        "payload_digest",
    ],
    "properties": {
        "event_id": {"type": "string", "minLength": 1},
        "event_type": {"type": "string", "enum": sorted(EVENT_DIRECTIONS)},
        "envelope_version": {"type": "string", "enum": list(PUBLISHED_VERSIONS)},
        "schema_version": {"type": "string"},
        "source_system": {"type": "string"},
        "target_system": {"type": ["string", "null"]},
        "tenant_id": {"type": "string", "minLength": 1},
        "client_id": {"type": "string", "minLength": 1},
        "correlation_id": {"type": "string", "minLength": 1},
        "causation_id": {"type": ["string", "null"]},
        "data_mode": {"type": "string", "enum": ["live", "sample", "historical"]},
        "data_classification": {
            "type": "string",
            "enum": [
                "public",
                "internal",
                "client_confidential",
                "personnel_sensitive",
                "financial",
                "regulated_high_risk",
            ],
        },
        "occurred_at": {"type": "string"},
        "payload": {"type": "object"},
        "payload_digest": {"type": "string", "minLength": 1},
    },
}


def build_schema(event_type: str, version: str = "1.0") -> Dict[str, Any]:
    """Return the JSON Schema document for one event type."""
    if version not in PUBLISHED_VERSIONS:
        raise ValueError(f"build_schema: unknown schema version {version!r}")
    if event_type not in _EVENT_SCHEMAS:
        raise ValueError(
            f"build_schema: unknown event_type {event_type!r} (known: {sorted(_EVENT_SCHEMAS)})"
        )
    body = _EVENT_SCHEMAS[event_type]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_NAMESPACE}/v{version}/{event_type}.json",
        "title": event_type,
        "description": (
            f"{event_type} — {EVENT_DIRECTIONS[event_type]} event owned by "
            f"{EVENT_OWNERS[event_type]}. Published by the Helix Codex OS sibling bus (C7)."
        ),
        "type": "object",
        "required": body["required"],
        "properties": body["properties"],
        "additionalProperties": False,
    }


def build_envelope_schema(version: str = "1.0") -> Dict[str, Any]:
    """Return the JSON Schema document for the event envelope."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{SCHEMA_NAMESPACE}/v{version}/Envelope.json",
        "title": "SiblingEventEnvelope",
        "description": (
            "Transport-agnostic wrapper for every sibling-project event. "
            "payload_digest is a SHA-256 over the canonical JSON of payload."
        ),
        "type": "object",
        "required": _ENVELOPE_SCHEMA["required"],
        "properties": _ENVELOPE_SCHEMA["properties"],
        "additionalProperties": False,
    }


def list_schemas() -> List[Dict[str, str]]:
    return [
        {
            "event_type": event_type,
            "version": "1.0",
            "direction": EVENT_DIRECTIONS[event_type],
            "owner": EVENT_OWNERS[event_type],
            "schema_id": f"{SCHEMA_NAMESPACE}/v1.0/{event_type}.json",
        }
        for event_type in sorted(_EVENT_SCHEMAS)
    ]


def export_schemas(target_dir: str | Path | None = None) -> List[Path]:
    """
    Write every schema to ``schemas/`` and return the paths written.

    Called by CI so the published JSON Schema can never drift from the Python
    contract: the job regenerates them and fails if the tree is dirty.
    """
    target = Path(target_dir) if target_dir else SCHEMA_DIR
    target.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for event_type in sorted(_EVENT_SCHEMAS):
        path = target / f"{event_type}.v1.json"
        path.write_text(json.dumps(build_schema(event_type), indent=2) + "\n", encoding="utf-8")
        written.append(path)
    envelope_path = target / "Envelope.v1.json"
    envelope_path.write_text(json.dumps(build_envelope_schema(), indent=2) + "\n", encoding="utf-8")
    written.append(envelope_path)
    return written


def validate_against_schema(event_type: str, payload: Dict[str, Any]) -> List[str]:
    """
    Minimal structural validation without a JSON Schema library dependency.

    Returns a list of human-readable violations; empty means the payload
    satisfies the published contract. Used by tests and by ``receive()``
    fallbacks so the boundary stays enforceable with zero extra dependencies.
    """
    if event_type not in _EVENT_SCHEMAS:
        return [f"unknown event_type {event_type!r}"]
    schema = _EVENT_SCHEMAS[event_type]
    problems: List[str] = []

    for field_name in schema["required"]:
        if field_name not in payload:
            problems.append(f"missing required field '{field_name}'")

    allowed = set(schema["properties"])
    for key in payload:
        if key not in allowed:
            problems.append(f"additional property '{key}' is not permitted by the published schema")

    for key, value in payload.items():
        spec = schema["properties"].get(key)
        if not spec:
            continue
        problems.extend(_check_type(key, value, spec))
    return problems


def _check_type(key: str, value: Any, spec: Dict[str, Any]) -> List[str]:
    expected = spec.get("type")
    if expected is None:
        return []
    allowed_types = expected if isinstance(expected, list) else [expected]
    if value is None:
        return [] if "null" in allowed_types else [f"'{key}' must not be null"]

    if "string" in allowed_types:
        if not isinstance(value, str):
            return [f"'{key}' must be a string"]
        if "minLength" in spec and len(value) < spec["minLength"]:
            return [f"'{key}' must be non-empty"]
        if "enum" in spec and value not in spec["enum"]:
            return [f"'{key}' must be one of {spec['enum']}"]
        return []
    if "number" in allowed_types:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"'{key}' must be a number"]
        if "minimum" in spec and value < spec["minimum"]:
            return [f"'{key}' must be >= {spec['minimum']}"]
        if "maximum" in spec and value > spec["maximum"]:
            return [f"'{key}' must be <= {spec['maximum']}"]
        return []
    if "integer" in allowed_types:
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"'{key}' must be an integer"]
        if "exclusiveMinimum" in spec and value <= spec["exclusiveMinimum"]:
            return [f"'{key}' must be > {spec['exclusiveMinimum']}"]
        return []
    if "boolean" in allowed_types:
        return [] if isinstance(value, bool) else [f"'{key}' must be a boolean"]
    if "array" in allowed_types:
        if not isinstance(value, list):
            return [f"'{key}' must be an array"]
        if "minItems" in spec and len(value) < spec["minItems"]:
            return [f"'{key}' must contain at least {spec['minItems']} item(s)"]
        return []
    if "object" in allowed_types:
        return [] if isinstance(value, dict) else [f"'{key}' must be an object"]
    return []
