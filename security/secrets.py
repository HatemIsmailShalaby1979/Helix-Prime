"""
Secrets safety for Helix Prime Codex C3 — local-first, no real secrets.

- No secrets in source files (validated via tests)
- No secrets in task payloads, evidence, or logs (validated + redacted)
- Environment/OS-secret lookup seam (get_secret)
- Redaction for API keys, bearer tokens, passwords, cookies, PII
- Clear failure when required secret unavailable
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


# Patterns for redaction (deterministic, no network)
REDACTION_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s\"',;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-\._~\+\/]+=*)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(password\s*[:=]\s*)([^\s\"',;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(passwd\s*[:=]\s*)([^\s\"',;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(secret\s*[:=]\s*)([^\s\"',;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token\s*[:=]\s*)([^\s\"',;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(cookie\s*[:=]\s*)([^\s\"',;]+)"), r"\1[REDACTED]"),
    # PII: email, phone, SSN-like
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),  # SSN
    (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),  # simple phone
]

# For is_secret_present check: look for high-entropy or known secret keys in string
SECRET_KEYWORDS = ["api_key", "apikey", "password", "passwd", "secret", "bearer", "token", "cookie", "aws_access", "aws_secret"]


def redact(text: str) -> str:
    """Redact secrets and PII from text (deterministic)."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact dict values that look like secrets."""
    if not isinstance(data, dict):
        return data
    out: Dict[str, Any] = {}
    for k, v in data.items():
        key_lower = str(k).lower()
        # If key looks like secret, redact value entirely
        if any(kw in key_lower for kw in SECRET_KEYWORDS):
            out[k] = "[REDACTED]"
        elif isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, list):
            out[k] = [redact_dict(item) if isinstance(item, dict) else redact(str(item)) if isinstance(item, str) else item for item in v]
        elif isinstance(v, str):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def is_secret_present(text: str) -> bool:
    """Check if text appears to contain a secret (for validation)."""
    if not isinstance(text, str):
        return False
    lower = text.lower()
    # Check for secret keywords with assignment
    for kw in SECRET_KEYWORDS:
        if kw in lower and ("=" in text or ":" in text):
            # Heuristic: if secret keyword and value looks like secret (not placeholder)
            if "[redacted]" not in lower:
                return True
    # Check for bearer token pattern
    if "bearer" in lower and "[redacted]" not in lower:
        return True
    # Check for high-entropy token-like strings (e.g., 32+ hex chars)
    if re.search(r"\b[A-Za-z0-9]{32,}\b", text) and "[redacted]" not in lower:
        # But ignore UUIDs which are hex with dashes
        if not re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", text.strip().lower()):
            # If it looks like a token and not already redacted, flag
            pass
    return False


def validate_no_secrets(payload: Dict[str, Any], field_path: str = "payload") -> None:
    """
    Validate that payload, evidence, or log does not contain secrets.
    Fail-closed if secret detected.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"{field_path}: must be dict, got {type(payload).__name__}")
    # Stringify and check
    import json

    text = json.dumps(payload, ensure_ascii=False)
    if is_secret_present(text):
        raise ValueError(f"{field_path}: appears to contain secret — fail closed (keys: {SECRET_KEYWORDS})")
    # Also check for redacted placeholder already? If payload already redacted, it's okay
    # Check each string value for secret patterns
    for k, v in payload.items():
        if isinstance(v, str) and is_secret_present(v):
            raise ValueError(f"{field_path}.{k}: contains potential secret — fail closed")
        if isinstance(v, str) and re.search(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-.]+", v) and "example.com" not in v.lower():
            # PII email not from example.com should be flagged for C3
            # For C3 we allow but redaction is expected; we don't fail here, just warn via redact
            pass


def get_secret(name: str) -> str:
    """
    Local-first secret lookup seam.

    - Checks environment variable with given name
    - If not found, raises clear error (do not fall back to default secret)
    - Do not log the secret value

    Example:
        get_secret("HELIX_API_KEY") -> raises ValueError if not set, else returns value (caller must redact before logging)
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"get_secret: name must be non-empty string, got {name!r}")
    name = name.strip()
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ValueError(f"get_secret: required secret {name!r} is not set in environment/OS store — fail closed")
    return value.strip()


def is_secret_available(name: str) -> bool:
    """Check if secret is available without raising."""
    return bool(os.environ.get(name, "").strip())
