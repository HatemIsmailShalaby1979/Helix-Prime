"""Structured tool call contracts for agent dispatch.

This module defines the tool call envelope and validation for inter-agent
communication. It replaces the regex-based parsing in base_agent.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class SideEffect(Enum):
    """Types of side effects a tool call may have."""

    NONE = "none"
    LOCAL_WRITE = "local_write"
    EXTERNAL_WRITE = "external_write"


@dataclass(frozen=True)
class ToolCall:
    """A structured tool call from an agent.

    Attributes:
        call_id: Unique identifier for this call.
        tool: The tool name being called.
        args: The arguments to the tool.
        idempotency_key: Optional key for replay safety.
    """

    call_id: str
    tool: str
    args: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "call_id": self.call_id,
            "tool": self.tool,
            "args": dict(self.args),
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCall:
        """Parse from dictionary (e.g., from JSON)."""
        return cls(
            call_id=data["call_id"],
            tool=data["tool"],
            args=data.get("args", {}),
            idempotency_key=data.get("idempotency_key"),
        )


@dataclass(frozen=True)
class ToolResult:
    """Result from executing a tool call.

    Attributes:
        call_id: The call_id this result corresponds to.
        output: The result data.
        error: Optional error message if the call failed.
        nature: The nature of the result (verified_fact, model_inference, etc.)
    """

    call_id: str
    output: Any = None
    error: str | None = None
    nature: str = "model_inference"


@dataclass(frozen=True)
class ToolCallEnvelope:
    """Envelope containing tool calls from an LLM response.

    This wraps the tool calls in a structured envelope that includes
    tenant, client, and correlation context.
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallEnvelope:
        """Parse from dictionary (e.g., from JSON)."""
        tool_calls = [ToolCall.from_dict(tc) for tc in data.get("tool_calls", [])]
        return cls(
            content=data.get("content", ""),
            tool_calls=tool_calls,
        )


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of an available tool.

    Attributes:
        name: The tool name.
        description: Human-readable description.
        owning_role: The role that owns this tool.
        capability: The capability this tool belongs to.
        side_effect: The type of side effect.
    """

    name: str
    description: str
    owning_role: str
    capability: str
    side_effect: SideEffect = SideEffect.NONE


class ToolRegistry:
    """Registry of available tools for agents."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())


# Default tool registry with core tools
TOOLS = ToolRegistry()

# Register core tools
TOOLS.register(
    ToolDefinition(
        name="call_agent",
        description="Call another agent to consult their expertise",
        owning_role="any",
        capability="agent_consult",
        side_effect=SideEffect.NONE,
    )
)
TOOLS.register(
    ToolDefinition(
        name="submit_task",
        description="Submit a task for approval and execution",
        owning_role="any",
        capability="task_submission",
        side_effect=SideEffect.LOCAL_WRITE,
    )
)
TOOLS.register(
    ToolDefinition(
        name="request_approval",
        description="Request approval for a decision or action",
        owning_role="any",
        capability="approval_request",
        side_effect=SideEffect.LOCAL_WRITE,
    )
)
TOOLS.register(
    ToolDefinition(
        name="read_document",
        description="Read a document from the workspace",
        owning_role="any",
        capability="document_read",
        side_effect=SideEffect.NONE,
    )
)
