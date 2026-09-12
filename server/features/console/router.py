"""
Operator console — server-rendered HTMX pages.

Phase 2 surfaces: Chat, Docs, Tasks, Flows + agent rail on HTMX/SSE.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server import deps
from server.config import Settings
from server.features.approvals.service import ApprovalService
from server.features.workflows.repository import WorkflowRepository
from server.models.store import NodeStore

router = APIRouter(tags=["console"])

_TEMPLATES = Jinja2Templates(directory="server/templates")


def _get_store() -> NodeStore:
    settings: Settings = deps.get_provider().settings
    db_path = settings.db_path / "nodes.db"
    store = NodeStore(db_path)
    store.connect()
    return store


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
def chat_page(request: Request) -> HTMLResponse:
    """Chat surface."""
    store = _get_store()
    try:
        messages = store.list_by_tenant("default", limit=50)
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="partials/chat.html",
            context={"messages": [m.to_dict() for m in messages]},
        )
    finally:
        store.close()


@router.get("/tasks", response_class=HTMLResponse)
def tasks_page(request: Request) -> HTMLResponse:
    """Tasks surface."""
    store = _get_store()
    try:
        tasks = store.list_by_tenant("default", limit=100)
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="partials/tasks.html",
            context={"tasks": [t.to_dict() for t in tasks]},
        )
    finally:
        store.close()


@router.get("/docs", response_class=HTMLResponse)
def docs_page(request: Request) -> HTMLResponse:
    """Docs surface."""
    store = _get_store()
    try:
        docs = store.list_by_tenant("default", limit=100)
        return _TEMPLATES.TemplateResponse(
            request=request,
            name="partials/docs.html",
            context={"docs": [d.to_dict() for d in docs]},
        )
    finally:
        store.close()


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
    repository = WorkflowRepository(deps.get_engine())
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="partials/workflows.html",
        context={
            "workflows": [repository.to_response(w) for w in repository.list_recent(limit=25)]
        },
    )
