"""
Prometheus /metrics endpoint (H2.2, G22).

This route is deliberately BEHIND the standard auth dependency (it is
registered with the same ``current_identity`` guard as every other /api
surface, via create_app). The exposition exposes route templates, status
codes, latency distributions, governance decision counts, audit-chain
verification outcomes and the approval-queue depth — operational telemetry
about a governed control plane. That is deployment-sensitive information: an
unauthenticated scraper must not be able to enumerate the API surface or
watch the approval queue. Prometheus servers authenticate with the same bearer
token every other client uses.

The approval-queue depth is refreshed on scrape from the workflow store: a
gauge that only updates when its inputs change would go stale between
submissions, and a stale queue depth is worse than none.
"""
from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from control_plane.workflow import WorkflowState
from observability.metrics import REGISTRY
from server import deps

router = APIRouter(tags=["metrics"])


def _refresh_approval_queue_depth() -> None:
    engine = deps.get_engine()
    depth = sum(
        1
        for workflow in engine.store.list_workflows(limit=1000)
        if workflow.state == WorkflowState.AWAITING_APPROVAL
    )
    REGISTRY.set_approval_queue_depth(depth)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(response: Response) -> PlainTextResponse:
    _refresh_approval_queue_depth()
    response.headers["Cache-Control"] = "no-store"
    return PlainTextResponse(REGISTRY.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
