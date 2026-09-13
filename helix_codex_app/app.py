"""FastAPI application factory for the Helix Codex App.

The product factory builds the same lifespan as the ops spine through
server.deps, so one process holds one Engine. It mounts the app shell at /
and /app, serves static assets, and includes feature routers as they land.
Every /app route except the health route and the static mount runs the
account guard; every mutating /app route also runs the CSRF check. Both are
wired once, at the router boundary, not per handler.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from helix_codex_app import db
from helix_codex_app.config import AppSettings, get_app_settings
from helix_codex_app.errors import AppError
from helix_codex_app.security.guard import current_account, require_csrf
from server import deps
from server.config import get_settings as get_server_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
health_router = APIRouter()
shell_router = APIRouter()
app_router = APIRouter(prefix="/app", dependencies=[Depends(current_account)])
csrf_router = APIRouter(
    prefix="/app",
    dependencies=[Depends(current_account), Depends(require_csrf)],
)


def render(request: Request, name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    """Render a template with the app settings and the caller's CSRF token."""
    session = getattr(request.state, "session", None)
    ctx = {
        "csrf_token": session.csrf_token if session else "",
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


@app_router.get("/")
def app_index(request: Request) -> HTMLResponse:
    """Serve the app home screen at /app, behind the account guard."""
    return render(request, "shell/home.html", {"active_nav": "home"})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings
    conn = db.connect(db_path=settings.db_path)
    db._init_schema(conn)
    db.close(conn)
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
    app.include_router(app_router)
    app.include_router(csrf_router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    return app
