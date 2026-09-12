"""Unifying Node model for the super-app.

Chat, docs, tasks, and workflows are the same object viewed through four
lenses. Every user action is already a governance event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CLIENT_CONFIDENTIAL = "client_confidential"
    RESTRICTED = "restricted"


class Nature(str, Enum):
    VERIFIED_FACT = "verified_fact"
    USER_CLAIM = "user_claim"
    MODEL_INFERENCE = "model_inference"
    SIMULATED_EVENT = "simulated_event"
    HISTORICAL_EVENT = "historical_event"
    VERIFIED_OUTCOME = "verified_outcome"


class NodeKind(str, Enum):
    MESSAGE = "message"
    DOCUMENT = "document"
    BLOCK = "block"
    TASK = "task"
    WORKFLOW = "workflow"
    DECISION = "decision"
    PROPOSAL = "proposal"


@dataclass(frozen=True)
class Provenance:
    source: str
    data_mode: str
    retrieved_at: str


@dataclass(frozen=True)
class NodeEnvelope:
    """Invariant envelope for every node."""

    node_id: str
    tenant_id: str  # never optional
    client_id: str | None
    correlation_id: str
    causation_id: str | None
    classification: Classification
    provenance: Provenance
    nature: Nature
    created_by: str  # human user_id OR agent role_id — same field
    created_at: str


@dataclass
class Node:
    """Unified object model for the super-app."""

    envelope: NodeEnvelope
    kind: NodeKind
    body: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "node_id": self.envelope.node_id,
            "tenant_id": self.envelope.tenant_id,
            "client_id": self.envelope.client_id,
            "correlation_id": self.envelope.correlation_id,
            "causation_id": self.envelope.causation_id,
            "classification": self.envelope.classification.value,
            "nature": self.envelope.nature.value,
            "created_by": self.envelope.created_by,
            "created_at": self.envelope.created_at,
            "kind": self.kind.value,
            "body": self.body,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        """Deserialize from dictionary."""
        envelope_data = {
            k: data[k]
            for k in (
                "node_id",
                "tenant_id",
                "client_id",
                "correlation_id",
                "causation_id",
                "created_by",
                "created_at",
            )
            if k in data
        }
        envelope_data["classification"] = Classification(data.get("classification", "internal"))
        envelope_data["nature"] = Nature(data.get("nature", "user_claim"))
        envelope_data["provenance"] = Provenance(
            source=data.get("provenance", {}).get("source", "unknown"),
            data_mode=data.get("provenance", {}).get("data_mode", "simulated_realistic"),
            retrieved_at=datetime.now().isoformat(),
        )

        envelope = NodeEnvelope(**envelope_data)
        kind = NodeKind(data.get("kind", "message"))
        body = data.get("body", {})

        return cls(envelope=envelope, kind=kind, body=body)


@dataclass
class ChatMessage(Node):
    """Chat message node."""

    kind: NodeKind = field(default=NodeKind.MESSAGE, init=False)

    @property
    def content(self) -> str:
        return self.body.get("content", "")

    @content.setter
    def content(self, value: str) -> None:
        self.body["content"] = value


@dataclass
class TaskNode(Node):
    """Task node."""

    kind: NodeKind = field(default=NodeKind.TASK, init=False)

    @property
    def title(self) -> str:
        return self.body.get("title", "")

    @property
    def status(self) -> str:
        return self.body.get("status", "open")

    @property
    def assignee(self) -> str | None:
        return self.body.get("assignee")


@dataclass
class DocumentNode(Node):
    """Document node."""

    kind: NodeKind = field(default=NodeKind.DOCUMENT, init=False)

    @property
    def title(self) -> str:
        return self.body.get("title", "")

    @property
    def content(self) -> str:
        return self.body.get("content", "")
