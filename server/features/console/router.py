"""
Operator console — server-rendered HTMX pages.

Phase 2 surfaces: Chat, Docs, Tasks, Flows + agent rail on HTMX/SSE.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from security.identity import Identity
from server import deps
from server import scope as api_scope
from server.auth import current_identity
from server.features.approvals.service import ApprovalService
from server.features.workflows.repository import WorkflowRepository

router = APIRouter(tags=["console"])

_TEMPLATES = Jinja2Templates(directory="server/templates")


def _scope_tenant(identity: Identity) -> str:
    if api_scope.is_global(identity) or identity.tenant_id is None:
        return "default"
    return identity.tenant_id


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


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, identity: Identity = Depends(current_identity)) -> HTMLResponse:
    """Chat surface."""
    with deps.node_store() as store:
        messages = store.list_by_tenant(_scope_tenant(identity), limit=50)
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="partials/chat.html",
            context={"messages": [m.to_dict() for m in messages]},
        )


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request, identity: Identity = Depends(current_identity)) -> HTMLResponse:
    """Tasks surface."""
    with deps.node_store() as store:
        tasks = store.list_by_tenant(_scope_tenant(identity), limit=100)
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="partials/tasks.html",
            context={"tasks": [t.to_dict() for t in tasks]},
        )


@router.get("/docs", response_class=HTMLResponse)
def docs_page(request: Request, identity: Identity = Depends(current_identity)) -> HTMLResponse:
    """Docs surface."""
    with deps.node_store() as store:
        docs = store.list_by_tenant(_scope_tenant(identity), limit=100)
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="partials/docs.html",
            context={"docs": [d.to_dict() for d in docs]},
        )


@router.get("/console/approvals", response_class=HTMLResponse)
def approvals_partial(
    request: Request, identity: Identity = Depends(current_identity)
) -> HTMLResponse:
    """HTMX fragment for the approval rail."""
    service = ApprovalService(deps.get_engine())
    pending = service.pending()
    if not api_scope.is_global(identity):
        pending = [item for item in pending if item.get("tenant_id") == identity.tenant_id]
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="partials/approvals.html",
        context={"pending": pending},
    )


@router.get("/console/workflows", response_class=HTMLResponse)
def workflows_partial(
    request: Request, identity: Identity = Depends(current_identity)
) -> HTMLResponse:
    """HTMX fragment for the recent-runs list."""
    repository = WorkflowRepository(deps.get_engine())
    workflows = repository.list_recent(limit=25)
    if not api_scope.is_global(identity):
        workflows = [w for w in workflows if w.tenant_id == identity.tenant_id]
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="partials/workflows.html",
        context={"workflows": [repository.to_response(w) for w in workflows]},
    )
