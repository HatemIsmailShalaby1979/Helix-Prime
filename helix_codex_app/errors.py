"""Typed application errors for the Helix Codex App.

Every deliberate failure is an AppError subclass carrying a stable machine code
and an HTTP status. Callers match on code, never on message text.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for every error the app raises deliberately."""

    code: str = "app_error"
    status_code: int = 500

    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "payload": self.payload,
            }
        }


class AuthError(AppError):
    """The caller is not authenticated, or the session is invalid."""

    code = "auth_failed"
    status_code = 401


class PermissionDenied(AppError):
    """The caller cannot perform this action."""

    code = "permission_denied"
    status_code = 403


class LimitExceeded(AppError):
    """The account hit a quota or capability limit."""

    code = "limit_exceeded"
    status_code = 429


class NotFoundError(AppError):
    """The requested object does not exist, or is outside the caller's scope."""

    code = "not_found"
    status_code = 404


class EngineUnavailableError(AppError):
    """A governed engine could not be read, so a result would be unreliable."""

    code = "engine_unavailable"
    status_code = 503
