"""HTTP surface for the emergency halt (kill switch).

Engage and release are restricted to the catalog's universal approvers: an
emergency stop is a platform-wide committal action and must not be reachable
by ordinary operator roles. The check is catalog-driven (read from
organization/role-catalog.yaml at request time) rather than a hardcoded role
list, and it fails closed — an unreadable catalog denies the operation.
Status is read-only and available to any authenticated identity.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from security.identity import Identity
from server import deps
from server.auth import current_identity

router = APIRouter(prefix="/api/halt", tags=["halt"])

_ROLE_CATALOG_PATH = pathlib.Path("organization/role-catalog.yaml")


class HaltEngageRequest(BaseModel):
    reason: str = Field(min_length=1)
    tenant_id: Optional[str] = Field(default=None, min_length=1)


class HaltReleaseRequest(BaseModel):
    tenant_id: Optional[str] = Field(default=None, min_length=1)


def _halt_authorized_roles() -> set:
    try:
        data = yaml.safe_load(_ROLE_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"halt authority unverifiable (role catalog unreadable: {exc})",
        ) from exc
    roles = set(data.get("universal_approvers") or [])
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="halt authority unverifiable (role catalog declares no universal approvers)",
        )
    return roles


def _require_halt_authority(identity: Identity = Depends(current_identity)) -> Identity:
    if identity.role_id not in _halt_authorized_roles():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role {identity.role_id!r} is not authorized to operate the kill switch",
        )
    return identity


def _switch():
    return deps.get_engine().kill_switch


@router.get("/status")
def halt_status(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        return _switch().status(tenant_id=tenant_id)
    except Exception as exc:
        return {"engaged": True, "error": f"halt state unreadable, failing closed: {exc}"}


@router.post("/engage")
def halt_engage(
    payload: HaltEngageRequest, identity: Identity = Depends(_require_halt_authority)
) -> Dict[str, Any]:
    try:
        return _switch().engage(payload.reason, identity.actor, tenant_id=payload.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/release")
def halt_release(
    payload: HaltReleaseRequest, identity: Identity = Depends(_require_halt_authority)
) -> Dict[str, Any]:
    try:
        return _switch().release(identity.actor, tenant_id=payload.tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
