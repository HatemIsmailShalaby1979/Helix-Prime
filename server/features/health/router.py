"""
Liveness and readiness.

``/healthz`` answers "is the process alive" and must never touch the database —
a liveness probe that depends on storage turns a slow disk into a restart loop.

``/readyz`` answers "can this instance serve traffic" and therefore *does*
check storage: workflow store reachable and the audit store present, readable,
and chain-verified. A missing, unreadable, or broken audit store makes the
instance not-ready on purpose — serving traffic from a ledger that cannot be
verified is worse than being down. The probe never creates the audit store:
fresh-install bootstrap (``server.deps.EngineProvider.startup``) initializes
it explicitly, so a missing file at probe time means runtime loss, not first
boot. Failure details name the failed check only, never paths or internals.
"""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Response, status

from observability.metrics import REGISTRY as metrics_registry
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

    try:
        engine = provider.engine
        engine.store.list_workflows(limit=1)
        checks["workflow_store"] = True
    except Exception:
        checks["workflow_store"] = False
        metrics_registry.record_readiness_failure("workflow_store")
        return _not_ready(response, checks, "workflow store unavailable")

    audit_path = pathlib.Path(str(provider.settings.audit_db_path))
    if not audit_path.exists():
        checks["audit_chain"] = False
        metrics_registry.record_readiness_failure("audit_chain")
        return _not_ready(response, checks, "audit store missing")
    if not audit_path.is_file():
        checks["audit_chain"] = False
        metrics_registry.record_readiness_failure("audit_chain")
        return _not_ready(response, checks, "audit store unreadable")

    try:
        from security.audit import AuditTrail

        trail = AuditTrail(db_path=str(audit_path))
        try:
            ok, _detail = trail.verify_chain()
            checks["audit_chain"] = bool(ok)
            if not ok:
                metrics_registry.record_readiness_failure("audit_chain")
                return _not_ready(response, checks, "audit chain invalid")
        finally:
            trail.close()
    except Exception:
        checks["audit_chain"] = False
        metrics_registry.record_readiness_failure("audit_chain")
        return _not_ready(response, checks, "audit store unreadable")

    return ReadinessResponse(ready=True, checks=checks)


def _not_ready(response: Response, checks: dict, detail: str) -> ReadinessResponse:
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(ready=False, checks=checks, detail=detail)
