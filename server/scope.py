"""
API tenant-scope enforcement for the headless FastAPI surface.

Every bearer token is bound to a tenant scope at authentication time
(``server.auth.current_identity``). The helpers here turn that scope into the
effective tenant/client for a request: a scoped identity may only ever act
inside its own scope, and any request value naming another tenant or client is
refused with 403. A global-operator identity (tenant scope ``None``) may name
any tenant, and every such access is written to the structured log with actor,
target tenant, client, route, and correlation id.

Isolation itself is still enforced by the single policy seam
(``security.policy.authorize``) inside the control plane; this module only
derives the effective scope from the authenticated identity so that no route
treats a caller-supplied tenant id as the authorization boundary.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request, status

from security.identity import Identity

GLOBAL_TARGET = "*"


def is_global(identity: Identity) -> bool:
    return identity.tenant_id is None


def require_tenant(
    identity: Identity,
    requested: Optional[str],
    *,
    route: str,
    request: Optional[Request] = None,
) -> Optional[str]:
    if is_global(identity):
        audit_global_access(
            identity,
            target_tenant=requested if requested is not None else GLOBAL_TARGET,
            target_client=None,
            route=route,
            request=request,
        )
        return requested
    if requested is None:
        return identity.tenant_id
    if requested != identity.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "tenant scope mismatch: token is scoped to "
                f"{identity.tenant_id!r} and cannot act on {requested!r}"
            ),
        )
    return requested


def require_client(
    identity: Identity,
    requested: Optional[str],
) -> Optional[str]:
    if requested is None:
        return None if is_global(identity) else identity.client_id
    if (
        not is_global(identity)
        and identity.client_id is not None
        and requested != identity.client_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "client scope mismatch: token is scoped to "
                f"{identity.client_id!r} and cannot act on {requested!r}"
            ),
        )
    return requested


def audit_global_access(
    identity: Identity,
    *,
    target_tenant: Optional[str],
    target_client: Optional[str],
    route: str,
    request: Optional[Request] = None,
) -> None:
    from observability.logging import log_structured

    correlation_id: Optional[str] = None
    state = getattr(request, "state", None)
    if state is not None:
        correlation_id = getattr(state, "correlation_id", None)
    log_structured(
        event_type="global_scope_access",
        correlation_id=correlation_id,
        tenant_id=target_tenant,
        client_id=target_client,
        actor=identity.actor,
        actor_type=identity.actor_type,
        role_id=identity.role_id,
        result_status="allowed",
        payload={"route": route},
        log_path=_log_path(),
    )


def _log_path() -> str:
    try:
        from server import deps

        return deps.get_provider().settings.log_path
    except RuntimeError:
        from observability.logging import DEFAULT_LOG_PATH

        return DEFAULT_LOG_PATH
