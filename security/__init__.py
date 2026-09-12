"""Security package for Helix Prime Codex C3 — local-first, fail-closed."""
from security.audit import AuditRecord, AuditTrail, verify_chain
from security.classification import (
    DataClassification,
    is_valid_classification,
    validate_payload_classification,
)
from security.identity import ActorType, Identity
from security.policy import AuthorizationDecision, AuthorizationRequest, authorize
from security.secrets import get_secret, is_secret_present, redact, validate_no_secrets

__all__ = [
    "DataClassification",
    "is_valid_classification",
    "validate_payload_classification",
    "ActorType",
    "Identity",
    "AuthorizationRequest",
    "AuthorizationDecision",
    "authorize",
    "get_secret",
    "redact",
    "is_secret_present",
    "validate_no_secrets",
    "AuditRecord",
    "AuditTrail",
    "verify_chain",
]
