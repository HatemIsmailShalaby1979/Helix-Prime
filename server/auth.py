"""
Server authentication layer for Helix Codex OS.

Reads bearer tokens from the Authorization header, resolves them to
Identity objects, and validates roles against the policy engine.
"""
from __future__ import annotations

import hmac
import logging
import os
import pathlib
from typing import Optional

import yaml
from fastapi import Header, HTTPException, status
from fastapi.requests import Request

from security.identity import ActorType, Identity

logger = logging.getLogger("helix.server")

TOKEN_VAR = "HELIX_API_TOKEN"  # noqa: S105
ROLE_VAR = "HELIX_API_TOKEN_ROLE"
TENANT_VAR = "HELIX_API_TOKEN_TENANT_ID"
CLIENT_VAR = "HELIX_API_TOKEN_CLIENT_ID"
GLOBAL_FLAG = "HELIX_API_ALLOW_GLOBAL_OPERATOR"

_ROLE_CATALOG_PATH = pathlib.Path("organization/role-catalog.yaml")


def universal_approver_roles() -> set:
    try:
        data = yaml.safe_load(_ROLE_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"operator authority unverifiable (role catalog unreadable: {exc})",
        ) from exc
    roles = set(data.get("universal_approvers") or [])
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="operator authority unverifiable (role catalog declares no universal approvers)",
        )
    return roles


def _global_operator_allowed() -> bool:
    return os.environ.get(GLOBAL_FLAG, "").strip().lower() in {"1", "true", "yes"}


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
    # Unset, empty, or whitespace-only is not a token: refuse before any comparison
    # so a blank configured value can never authenticate a request.
    if not expected.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Token not configured in environment: set HELIX_API_TOKEN to a non-empty value"
            ),
        )

    # Compare as UTF-8 bytes: hmac.compare_digest rejects non-ASCII str operands, so
    # a non-ASCII bearer token would otherwise raise TypeError and surface as a 500.
    if not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # No default role: an unset or blank HELIX_API_TOKEN_ROLE must fail closed rather
    # than silently authenticate as a privileged seat.
    role_id = (os.environ.get(ROLE_VAR) or "").strip()
    if not role_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Token role not configured: set HELIX_API_TOKEN_ROLE to a role id from the catalog"
            ),
        )
    actor = role_id.split(":")[0] if ":" in role_id else role_id

    tenant_id = (os.environ.get(TENANT_VAR) or "").strip() or None
    client_id = (os.environ.get(CLIENT_VAR) or "").strip() or None
    if tenant_id is None:
        if client_id is not None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API token declares a client scope without a tenant scope",
            )
        if _global_operator_allowed() and role_id in universal_approver_roles():
            identity = Identity(
                actor=actor,
                actor_type=ActorType.SERVICE,
                role_id=role_id,
            )
            logger.debug("Token authenticated for global operator actor=%s role=%s", actor, role_id)
            return identity
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "API token has no tenant scope: set HELIX_API_TOKEN_TENANT_ID, "
                "or enable an explicit global operator with "
                "HELIX_API_ALLOW_GLOBAL_OPERATOR for a universal-approver role"
            ),
        )

    identity = Identity(
        actor=actor,
        actor_type=ActorType.SERVICE,
        tenant_id=tenant_id,
        client_id=client_id,
        role_id=role_id,
    )

    logger.debug(
        "Token authenticated for actor=%s role=%s tenant=%s client=%s",
        actor,
        role_id,
        tenant_id,
        client_id,
    )
    return identity
