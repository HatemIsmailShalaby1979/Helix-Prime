"""FastAPI application factory for the Helix Codex App.

The product factory builds the same lifespan as the ops spine through
server.deps, so one process holds one Engine. This factory only mounts the
app health route; feature modules join later and include their routers.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from helix_codex_app.config import AppSettings, get_app_settings
from server import deps
from server.config import get_settings as get_server_settings

health_router = APIRouter()


@health_router.get("/app/healthz")
def healthz() -> dict[str, str]:
    """Readiness probe for the app shell."""
    return {"status": "ok", "app": "helix-codex"}


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
    return app
