"""FastAPI application factory for the Helix Codex App.

The product factory builds the same lifespan as the ops spine through
server.deps, so one process holds one Engine. It mounts the app shell at /
and /app, serves static assets, and includes feature routers as they land.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from helix_codex_app.config import AppSettings, get_app_settings
from server import deps
from server.config import get_settings as get_server_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
health_router = APIRouter()
shell_router = APIRouter()


def render(request: Request, name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    """Render a template with the app settings and a csrf placeholder loaded."""
    ctx = {
        "csrf_token": "",
        "settings": request.app.state.settings,
        **(context or {}),
    }
    return templates.TemplateResponse(request, name, ctx)


@health_router.get("/app/healthz")
def healthz() -> dict[str, str]:
    """Readiness probe for the app shell."""
    return {"status": "ok", "app": "helix-codex"}


@shell_router.get("/")
def index(request: Request) -> HTMLResponse:
    """Serve the app home screen at the root path."""
    return render(request, "shell/home.html", {"active_nav": "home"})


@shell_router.get("/app")
def app_index(request: Request) -> HTMLResponse:
    """Serve the app home screen at the /app path."""
    return render(request, "shell/home.html", {"active_nav": "home"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    server_settings = get_server_settings()
    provider = deps.EngineProvider(server_settings)
    provider.startup()
    deps.set_provider(provider)
    try:
        yield
    finally:
        provider.shutdown()


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or get_app_settings()
    settings.require_safe_defaults()

    app = FastAPI(
        title="Helix Codex App",
        version="0.9.0",
        description="Daily-use product shell over the governed Helix Codex OS core.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router)
    app.include_router(shell_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
