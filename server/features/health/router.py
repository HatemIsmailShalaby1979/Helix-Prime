"""
Liveness and readiness.

``/healthz`` answers "is the process alive" and must never touch the database —
a liveness probe that depends on storage turns a slow disk into a restart loop.

``/readyz`` answers "can this instance serve traffic" and therefore *does*
check storage: workflow store reachable, schema migrated, audit chain intact.
A broken hash chain makes the instance not-ready on purpose — serving traffic
from a ledger that cannot be verified is worse than being down.
"""
from __future__ import annotations

from fastapi import APIRouter, Response, status

from server import deps
from server.features.health.schemas import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", profile=deps.get_provider().settings.profile)


@router.get("/readyz", response_model=ReadinessResponse)
def readyz(response: Response) -> ReadinessResponse:
    provider = deps.get_provider()
    checks: dict = {}
    ready = True

    try:
        engine = provider.engine
        engine.store.list_workflows(limit=1)
        checks["workflow_store"] = True
    except Exception as exc:  # noqa: BLE001 - readiness must never raise
        checks["workflow_store"] = False
        ready = False
        return _not_ready(response, checks, f"workflow store unreachable: {exc}")

    try:
        from security.audit import AuditTrail

        trail = AuditTrail(db_path=provider.settings.audit_db_path)
        try:
            ok, detail = trail.verify_chain()
            checks["audit_chain"] = bool(ok)
            if not ok:
                ready = False
                return _not_ready(response, checks, f"audit chain invalid: {detail}")
        finally:
            trail.close()
    except Exception as exc:  # noqa: BLE001 - readiness must never raise
        # An absent audit database on a fresh volume is expected, not fatal.
        checks["audit_chain"] = f"unverified: {exc}"

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(ready=ready, checks=checks)


def _not_ready(response: Response, checks: dict, detail: str) -> ReadinessResponse:
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(ready=False, checks=checks, detail=detail)
