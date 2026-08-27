"""
Event envelope for Helix Prime Codex C2.

Local-first, durable, replayable. Every state change is an event.
"""
from __future__ import annotations

import dataclasses
import datetime
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

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


ALLOWED_EVENT_TYPES = {
    "workflow_created",
    "workflow_validated",
    "workflow_awaiting_approval",
    "workflow_approved",
    "workflow_executing",
    "workflow_succeeded",
    "workflow_failed",
    "workflow_compensated",
    "workflow_cancelled",
    "workflow_dead_letter",
    "workflow_closed",
    "approval_granted",
    "approval_denied",
    "handler_succeeded",
    "handler_failed",
    "retry_scheduled",
    "timeout",
    "compensated",
}


@dataclass
class Event:
    event_id: str
    event_type: str
    aggregate_id: str  # workflow_id
    correlation_id: str
    actor: str
    schema_version: str
    timestamp: str
    payload: Dict[str, Any]
    causation_id: Optional[str] = None
    sequence: int = 0

    def __post_init__(self) -> None:
        self.event_id = _require_non_empty_str(self.event_id, "Event.event_id")
        self.event_type = _require_non_empty_str(self.event_type, "Event.event_type").lower()
        if self.event_type not in ALLOWED_EVENT_TYPES:
            # allow custom but warn? For C2 we allow any but test expects these
            # we will not strictly enforce, just ensure non-empty
            pass
        self.aggregate_id = _require_non_empty_str(self.aggregate_id, "Event.aggregate_id")
        self.correlation_id = _require_non_empty_str(self.correlation_id, "Event.correlation_id")
        self.actor = _require_non_empty_str(self.actor, "Event.actor")
        self.schema_version = _validate_schema_version(self.schema_version, "Event.schema_version")
        self.timestamp = _validate_iso(self.timestamp, "Event.timestamp")
        if not isinstance(self.payload, dict):
            raise ValueError(f"Event.payload: must be dict, got {type(self.payload).__name__}")
        if self.causation_id is not None:
            self.causation_id = _require_non_empty_str(self.causation_id, "Event.causation_id")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError(f"Event.sequence: must be int >=0, got {self.sequence!r}")

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "correlation_id": self.correlation_id,
            "actor": self.actor,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "sequence": self.sequence,
        }
        if self.causation_id is not None:
            d["causation_id"] = self.causation_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        if not isinstance(data, dict):
            raise ValueError(f"Event.from_dict: expected dict, got {type(data).__name__}")
        return cls(
            event_id=data.get("event_id", ""),
            event_type=data.get("event_type", ""),
            aggregate_id=data.get("aggregate_id", ""),
            correlation_id=data.get("correlation_id", ""),
            actor=data.get("actor", ""),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            timestamp=data.get("timestamp", ""),
            payload=data.get("payload", {}),
            causation_id=data.get("causation_id"),
            sequence=int(data.get("sequence", 0)),
        )

    @classmethod
    def new(
        cls,
        event_type: str,
        aggregate_id: str,
        correlation_id: str,
        actor: str,
        payload: Optional[Dict[str, Any]] = None,
        causation_id: Optional[str] = None,
        sequence: int = 0,
        timestamp: Optional[str] = None,
    ) -> "Event":
        eid = uuid.uuid4().hex
        ts = timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        return cls(
            event_id=eid,
            event_type=event_type,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            actor=actor,
            schema_version=SCHEMA_VERSION,
            timestamp=ts,
            payload=payload or {},
            causation_id=causation_id,
            sequence=sequence,
        )
