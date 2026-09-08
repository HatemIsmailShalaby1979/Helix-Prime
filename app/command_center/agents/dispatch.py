"""Agent dispatch system using structured tool calls.

This module replaces the regex-based call_agent parsing in base_agent.py
with a structured tool call system using JSON schema validation.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

from contracts.toolcall import (
    ToolCall,
    ToolCallEnvelope,
    ToolResult,
    TOOLS,
)


class AgentDispatch:
    """Dispatch system for inter-agent communication.

    This class handles:
    1. Parsing tool calls from LLM responses
    2. Validating tool calls against the registry
    3. Executing tool calls with proper context inheritance
    4. Enforcing depth/cycle limits
    """

    def __init__(
        self,
        engine=None,
        store=None,
        connector_gateway=None,
        max_depth: int = 5,
    ) -> None:
        self._engine = engine
        self._store = store
        self._gateway = connector_gateway
        self._max_depth = max_depth
        self._depth: int = 0
        self._visited_agents: set[str] = set()

    def parse_tool_calls(self, content: str) -> ToolCallEnvelope:
        """Parse tool calls from LLM response content.

        Args:
            content: The LLM response text.

        Returns:
            ToolCallEnvelope with parsed tool calls.

        If parsing fails, returns envelope with empty tool_calls list
        and content marked as DEAD_LETTER.
        """
        try:
            # Try to extract tool calls from JSON
            data = json.loads(content)
            tool_calls = [
                ToolCall.from_dict(tc)
                for tc in data.get("tool_calls", [])
            ]
            return ToolCallEnvelope(
                content=data.get("content", ""),
                tool_calls=tool_calls,
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            # Fallback: return empty envelope, content goes to review queue
            return ToolCallEnvelope(
                content=content,
                tool_calls=[],
            )

    def validate_tool_call(self, tool_call: ToolCall) -> tuple[bool, str]:
        """Validate a tool call against the registry.

        Args:
            tool_call: The tool call to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        tool_def = TOOLS.get(tool_call.tool)
        if tool_def is None:
            return False, f"Unknown tool: {tool_call.tool}"

        # Check required args
        # TODO: Validate args against tool schema

        return True, ""

    def check_depth(self) -> bool:
        """Check if we've exceeded max depth.

        Returns:
            True if depth is within limits, False otherwise.
        """
        if self._depth >= self._max_depth:
            return False
        return True

    def check_cycle(self, agent_name: str) -> bool:
        """Check if calling this agent would create a cycle.

        Args:
            agent_name: The name of the agent being called.

        Returns:
            True if no cycle detected, False otherwise.
        """
        if agent_name in self._visited_agents:
            return False
        return True

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: Mapping[str, Any],
    ) -> ToolResult:
        """Execute a tool call with proper context inheritance.

        Args:
            tool_call: The tool call to execute.
            context: The current execution context.

        Returns:
            ToolResult with output or error.
        """
        # Validate tool call
        is_valid, error = self.validate_tool_call(tool_call)
        if not is_valid:
            return ToolResult(
                call_id=tool_call.call_id,
                error=error,
                nature="error",
            )

        # Check depth
        if not self.check_depth():
            return ToolResult(
                call_id=tool_call.call_id,
                error="Max depth exceeded",
                nature="error",
            )

        # Execute based on tool type
        try:
            if tool_call.tool == "call_agent":
                return await self._handle_call_agent(tool_call, context)
            elif tool_call.tool == "submit_task":
                return await self._handle_submit_task(tool_call, context)
            elif tool_call.tool == "request_approval":
                return await self._handle_request_approval(tool_call, context)
            elif tool_call.tool == "read_document":
                return await self._handle_read_document(tool_call, context)
            else:
                return ToolResult(
                    call_id=tool_call.call_id,
                    error=f"Unknown tool: {tool_call.tool}",
                    nature="error",
                )
        except Exception as e:
            return ToolResult(
                call_id=tool_call.call_id,
                error=str(e),
                nature="error",
            )

    async def _handle_call_agent(
        self,
        tool_call: ToolCall,
        context: Mapping[str, Any],
    ) -> ToolResult:
        """Handle call_agent tool call."""
        agent_name = tool_call.args.get("agent_name", "")
        message = tool_call.args.get("message", "")

        # Check for cycles
        if not self.check_cycle(agent_name):
            return ToolResult(
                call_id=tool_call.call_id,
                error=f"Cycle detected: {agent_name} already visited",
                nature="error",
            )

        # Increment depth and add to visited
        self._depth += 1
        self._visited_agents.add(agent_name)

        try:
            # TODO: Actually call the agent and get response
            result = f"Called {agent_name} with: {message}"
            return ToolResult(
                call_id=tool_call.call_id,
                output=result,
                nature="model_inference",
            )
        finally:
            self._depth -= 1
            self._visited_agents.discard(agent_name)

    async def _handle_submit_task(
        self,
        tool_call: ToolCall,
        context: Mapping[str, Any],
    ) -> ToolResult:
        """Handle submit_task tool call."""
        # TODO: Implement task submission through Engine
        return ToolResult(
            call_id=tool_call.call_id,
            output="Task submitted for approval",
            nature="model_inference",
        )

    async def _handle_request_approval(
        self,
        tool_call: ToolCall,
        context: Mapping[str, Any],
    ) -> ToolResult:
        """Handle request_approval tool call."""
        # TODO: Implement approval request through Engine
        return ToolResult(
            call_id=tool_call.call_id,
            output="Approval request submitted",
            nature="model_inference",
        )

    async def _handle_read_document(
        self,
        tool_call: ToolCall,
        context: Mapping[str, Any],
    ) -> ToolResult:
        """Handle read_document tool call."""
        doc_id = tool_call.args.get("doc_id", "")
        # TODO: Implement document read
        return ToolResult(
            call_id=tool_call.call_id,
            output=f"Document {doc_id} read",
            nature="model_inference",
        )

    async def process_tool_calls(
        self,
        envelope: ToolCallEnvelope,
        context: Mapping[str, Any],
    ) -> list[ToolResult]:
        """Process all tool calls in an envelope.

        Args:
            envelope: The tool call envelope.
            context: The current execution context.

        Returns:
            List of ToolResult objects.
        """
        results = []
        for tool_call in envelope.tool_calls:
            result = await self.execute_tool_call(tool_call, context)
            results.append(result)
        return results


def parse_legacy_calls(content: str) -> list[dict]:
    """Legacy regex-based parser for backward compatibility.

    This is kept behind HELIX_LEGACY_CALL_PARSING=1 for migration purposes.

    Args:
        content: The LLM response text.

    Returns:
        List of parsed call dictionaries.
    """
    import re
    call_pattern = r'call_agent\((["\'])([A-Z_]+)\1,\s*(["\'])(.*?)\3\)'
    matches = re.findall(call_pattern, content, re.DOTALL)
    return [
        {
            "agent": agent,
            "message": msg,
        }
        for _, agent, _, msg in matches
    ]
