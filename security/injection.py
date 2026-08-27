"""
Prompt/tool injection detection seam for Helix Prime Codex C3.

Local-first, deterministic, no network.
Detects suspicious prompt/tool requests that could be injection attempts.
"""
from __future__ import annotations

import re
from typing import Dict, Any, List


# Patterns for suspicious injection
INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+previous\s+instructions"),
    re.compile(r"(?i)system\s*:\s*"),
    re.compile(r"(?i)pretend\s+you\s+are"),
    re.compile(r"(?i)do\s+anything\s+now"),
    re.compile(r"(?i)call_agent\s*\(\s*[\"']\s*SAMI\s*[\"']\s*,.*\)"),  # direct model trying to call SAMI as if system
    re.compile(r"(?i)tool\s*:\s*exec"),
    re.compile(r"(?i)```.*\b(python|bash|sh)\b"),
    re.compile(r"(?i)\b(drop\s+table|delete\s+from|truncate)\b"),
]

TOOL_ABUSE_PATTERNS = [
    re.compile(r"(?i)tool\s*[:=]\s*[^a-z_]", re.IGNORECASE),
]


def is_suspicious_prompt(text: str) -> tuple[bool, str]:
    """
    Check if prompt text looks like injection attempt.
    Returns (is_suspicious, reason).
    Fail-closed: if suspicious, caller should route to review queue / dead_letter, not execute.
    """
    if not isinstance(text, str):
        return False, "not a string"
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            return True, f"matched injection pattern {pat.pattern!r}"
    return False, "clean"


def is_suspicious_tool_request(tool: str, capability: str, payload: Dict[str, Any]) -> tuple[bool, str]:
    """
    Check if tool request looks suspicious.
    - tool name should be alphanumeric + underscore, known from capability registry
    - payload should not contain injection patterns
    """
    if not isinstance(tool, str) or not tool.strip():
        return True, "tool must be non-empty string"
    # Check payload for injection
    import json

    payload_text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)
    suspicious, reason = is_suspicious_prompt(payload_text)
    if suspicious:
        return True, f"suspicious payload: {reason}"
    # Check tool name format
    if not re.match(r"^[a-z_][a-z0-9_]*$", tool.strip()):
        return True, f"tool name {tool!r} does not match allowed pattern ^[a-z_][a-z0-9_]*$"
    return False, "clean"


def scan_for_injection(payload: Dict[str, Any]) -> List[str]:
    """Scan dict payload for injection patterns, return list of reasons."""
    reasons: List[str] = []
    import json

    text = json.dumps(payload, ensure_ascii=False)
    for pat in INJECTION_PATTERNS:
        if pat.search(text):
            reasons.append(pat.pattern)
    return reasons
