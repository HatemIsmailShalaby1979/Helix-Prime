"""
Typed application errors.

The HTTP boundary maps these to status codes. Nothing at this boundary matches
on message substrings: the previous generation did (`if "unauthorized" in
str(e).lower()`), which made every error message part of the API.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "AppError",
    "AuthorizationRefused",
    "GateAwaitingApproval",
    "NotFound",
    "ProfileUnsatisfiable",
    "UpstreamUnavailable",
    "ValidationAppError",
]


class AppError(Exception):
    """Base class for every error the service raises deliberately."""

    code: str = "internal_error"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "payload": self.payload,
            }
        }


class ValidationAppError(AppError):
    code = "invalid_input"
    http_status = 422


class NotFound(AppError):
    code = "not_found"
    http_status = 404


class AuthorizationRefused(AppError):
    code = "unauthorized"
    http_status = 403


class ProfileUnsatisfiable(AppError):
    """The configured profile cannot be honoured on this host."""

    code = "profile_unsatisfiable"
    http_status = 503


class GateAwaitingApproval(AppError):
    """
    The governance gate froze the run.

    409 rather than 200: the request was understood and recorded, but the
    requested side effect has *not* happened and will not until a human
    decides. The decision payload is returned so the UI can render the queue
    entry without a second round trip.
    """

    code = "awaiting_approval"
    http_status = 409
    retryable = True

    def __init__(self, message: str, *, payload: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, payload=payload)


class UpstreamUnavailable(AppError):
    """Ollama, an engine, or the audit store is unreachable."""

    code = "dependency_unavailable"
    http_status = 503
    retryable = True
