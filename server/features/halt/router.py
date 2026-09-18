"""HTTP surface for the emergency halt (kill switch).

Engage and release are restricted to the catalog's universal approvers: an
emergency stop is a platform-wide committal action and must not be reachable
by ordinary operator roles. The check is catalog-driven (read from
organization/role-catalog.yaml at request time) rather than a hardcoded role
list, and it fails closed — an unreadable catalog denies the operation.
Status is read-only and available to any authenticated identity.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity, universal_approver_roles

router = APIRouter(prefix="/api/halt", tags=["halt"])


class HaltEngageRequest(BaseModel):
    reason: str = Field(min_length=1)
    tenant_id: Optional[str] = Field(default=None, min_length=1)


class HaltReleaseRequest(BaseModel):
    tenant_id: Optional[str] = Field(default=None, min_length=1)


def _halt_authorized_roles() -> set:
    return universal_approver_roles()


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
def halt_status(
    request: Request,
    tenant_id: Optional[str] = None,
    identity: Identity = Depends(current_identity),
) -> Dict[str, Any]:
    target = api_scope.require_tenant(
        identity, tenant_id, route="GET /api/halt/status", request=request
    )
    if api_scope.is_global(identity):
        try:
            return _switch().status(tenant_id=target)
        except Exception as exc:
            return {"engaged": True, "error": f"halt state unreadable, failing closed: {exc}"}
    try:
        halt = _switch().active_halt(tenant_id=target)
    except Exception as exc:
        return {"engaged": True, "error": f"halt state unreadable, failing closed: {exc}"}
    if halt is None:
        return {
            "engaged": False,
            "scope": "none",
            "reason": None,
            "actor": None,
            "engaged_at": None,
            "tenants": [],
        }
    return {
        "engaged": True,
        "scope": halt["scope"],
        "reason": halt["reason"],
        "actor": halt["actor"],
        "engaged_at": halt["engaged_at"],
        "tenants": [target] if halt["scope"] != "global" else [],
    }


@router.post("/engage")
def halt_engage(
    payload: HaltEngageRequest,
    request: Request,
    identity: Identity = Depends(_require_halt_authority),
) -> Dict[str, Any]:
    target = api_scope.require_tenant(
        identity, payload.tenant_id, route="POST /api/halt/engage", request=request
    )
    try:
        return _switch().engage(payload.reason, identity.actor, tenant_id=target)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/release")
def halt_release(
    payload: HaltReleaseRequest,
    request: Request,
    identity: Identity = Depends(_require_halt_authority),
) -> Dict[str, Any]:
    target = api_scope.require_tenant(
        identity, payload.tenant_id, route="POST /api/halt/release", request=request
    )
    try:
        return _switch().release(identity.actor, tenant_id=target)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
