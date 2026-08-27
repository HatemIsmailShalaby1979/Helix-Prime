"""
Contracts package — Helix Prime Codex C1.

Typed agent contracts: CorrelationContext, TaskRequest, TaskResult, Recommendation, Action, Approval, EvidenceRef, AgentError.
Adapter in contracts.adapter shows migration path from model-text call_agent(...).
"""
from contracts.task import (
    SCHEMA_VERSION,
    Action,
    AgentError,
    Approval,
    CorrelationContext,
    EvidenceRef,
    Recommendation,
    TaskRequest,
    TaskResult,
)

__all__ = [
    "SCHEMA_VERSION",
    "CorrelationContext",
    "EvidenceRef",
    "AgentError",
    "TaskRequest",
    "TaskResult",
    "Recommendation",
    "Action",
    "Approval",
]
