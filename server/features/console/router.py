"""
Operator console — server-rendered HTMX pages.

This is intentionally thin. Phase 1's job is to prove the service spine boots
and the governance rail is reachable over HTTP; the full collaboration suite
(Chat/Docs/Tasks/Flows) is Phase 2. What ships here is the surface a pilot
operator actually needs on day one: submit, watch, approve.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server import deps
from server.features.approvals.service import ApprovalService
from server.features.workflows.repository import WorkflowRepository

router = APIRouter(tags=["console"])

_TEMPLATES = Jinja2Templates(directory="server/templates")


def _repo() -> WorkflowRepository:
    return WorkflowRepository(deps.get_engine())


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    settings = deps.get_provider().settings
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "profile": settings.profile,
            "sample_data_mode": settings.sample_data_mode,
        },
    )


@router.get("/console/approvals", response_class=HTMLResponse)
def approvals_partial(request: Request) -> HTMLResponse:
    """HTMX fragment for the approval rail."""
    service = ApprovalService(deps.get_engine())
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="partials/approvals.html",
        context={"pending": service.pending()},
    )


@router.get("/console/workflows", response_class=HTMLResponse)
def workflows_partial(request: Request) -> HTMLResponse:
    """HTMX fragment for the recent-runs list."""
    repository = _repo()
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="partials/workflows.html",
        context={"workflows": [repository.to_response(w) for w in repository.list_recent(limit=25)]},
    )
