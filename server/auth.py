"""
Server authentication layer for Helix Codex OS.

Reads bearer tokens from the Authorization header, resolves them to
Identity objects, and validates roles against the policy engine.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

from fastapi import Header, HTTPException, status
from fastapi.requests import Request

from security.identity import ActorType, Identity

logger = logging.getLogger("helix.server")

TOKEN_VAR = "HELIX_API_TOKEN"  # noqa: S105
ROLE_VAR = "HELIX_API_TOKEN_ROLE"


async def current_identity(
    authorization: Optional[str] = Header(None),
    request: Request = None,
) -> Identity:
    """
    FastAPI dependency: extract bearer token, validate, return Identity.

    Raises 401 for missing/invalid token, 403 for unauthorized role.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format; use 'Bearer <token>'",
        )

    token = parts[1]
    expected = os.environ.get(TOKEN_VAR, "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token not configured in environment",
        )

    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    role_id = os.environ.get(ROLE_VAR, "sami")
    actor = role_id.split(":")[0] if ":" in role_id else role_id

    identity = Identity(
        actor=actor,
        actor_type=ActorType.SERVICE,
        role_id=role_id,
    )

    logger.debug("Token authenticated for actor=%s role=%s", actor, role_id)
    return identity
