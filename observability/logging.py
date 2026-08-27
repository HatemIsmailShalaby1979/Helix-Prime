"""
Structured JSON logs for Helix Prime Codex C3 — local-first, no cloud.

Fields: correlation_id, causation_id, workflow_id, task_id, tenant/client, actor/role,
capability/tool, duration, result status, error code, retry count, model/provider status.
"""
from __future__ import annotations

import datetime
import json
import pathlib
from typing import Any, Dict, Optional

DEFAULT_LOG_PATH = "observability/logs.jsonl"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def log_structured(
    *,
    event_type: str,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    task_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    actor: Optional[str] = None,
    actor_type: Optional[str] = None,
    role_id: Optional[str] = None,
    capability: Optional[str] = None,
    tool: Optional[str] = None,
    duration_ms: Optional[int] = None,
    result_status: Optional[str] = None,
    error_code: Optional[str] = None,
    retry_count: Optional[int] = None,
    model_status: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    log_path: str = DEFAULT_LOG_PATH,
) -> Dict[str, Any]:
    """
    Emit a structured JSON log line (append to log_path) and return the dict.
    All fields are optional except event_type; caller should provide correlation/causation for tracing.
    """
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError(f"log_structured: event_type must be non-empty string, got {event_type!r}")
    entry: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "event_type": event_type.strip(),
        "schema_version": "1.0",
    }
    # Only include non-None fields
    if correlation_id is not None:
        entry["correlation_id"] = correlation_id
    if causation_id is not None:
        entry["causation_id"] = causation_id
    if workflow_id is not None:
        entry["workflow_id"] = workflow_id
    if task_id is not None:
        entry["task_id"] = task_id
    if tenant_id is not None:
        entry["tenant_id"] = tenant_id
    if client_id is not None:
        entry["client_id"] = client_id
    if actor is not None:
        entry["actor"] = actor
    if actor_type is not None:
        entry["actor_type"] = actor_type
    if role_id is not None:
        entry["role_id"] = role_id
    if capability is not None:
        entry["capability"] = capability
    if tool is not None:
        entry["tool"] = tool
    if duration_ms is not None:
        if not isinstance(duration_ms, int) or duration_ms < 0:
            raise ValueError(f"log_structured: duration_ms must be int >=0, got {duration_ms!r}")
        entry["duration_ms"] = duration_ms
    if result_status is not None:
        entry["result_status"] = result_status
    if error_code is not None:
        entry["error_code"] = error_code
    if retry_count is not None:
        if not isinstance(retry_count, int) or retry_count < 0:
            raise ValueError(f"log_structured: retry_count must be int >=0, got {retry_count!r}")
        entry["retry_count"] = retry_count
    if model_status is not None:
        entry["model_status"] = model_status
    if payload is not None:
        if not isinstance(payload, dict):
            raise ValueError(f"log_structured: payload must be dict, got {type(payload).__name__}")
        entry["payload"] = payload

    # Ensure directory exists
    pathlib.Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    # Append JSONL (one JSON per line)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def get_logger(log_path: str = DEFAULT_LOG_PATH):
    """Return a simple logger closure for the given path."""
    def logger(event_type: str, **kwargs: Any) -> Dict[str, Any]:
        return log_structured(event_type=event_type, log_path=log_path, **kwargs)

    return logger
