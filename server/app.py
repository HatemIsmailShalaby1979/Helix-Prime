"""
FastAPI application factory.

Two things this file exists to guarantee:

1. **Correlation survives every boundary.** Request-ID middleware reads or
   generates ``X-Request-ID``, binds it to the correlation context, and echoes
   it on every response. One place, not twenty.
2. **Errors are typed, not string-matched.** ``AppError`` subclasses map to
   status codes; anything else is a 500 with a correlation id and no internals.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server import deps
from server.config import Settings, get_settings
from server.errors import AppError
from server.features.approvals.router import router as approvals_router
from server.features.chat.router import router as chat_router
from server.features.console.router import router as console_router
from server.features.docs.router import router as docs_router
from server.features.health.router import router as health_router
from server.features.stream.router import router as stream_router
from server.features.tasks.router import router as tasks_router
from server.features.workflows.router import router as workflows_router

logger = logging.getLogger("helix.server")

CORRELATION_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.require_headless_safe()
    provider = deps.EngineProvider(settings)
    provider.startup()
    deps.set_provider(provider)
    logger.info("helix spine ready: profile=%s db=%s", settings.profile, settings.db_path)
    try:
        yield
    finally:
        provider.shutdown()
        logger.info("helix spine stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="Helix Codex OS",
        version="0.9.0",
        description=(
            "Local-first operations OS: six deterministic engines, nine governed "
            "agents, and an append-only audit trail. Self-hosted."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_HEADER) or f"req_{uuid.uuid4().hex[:20]}"
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
            headers={CORRELATION_HEADER: getattr(request.state, "correlation_id", "")},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals; always leave a handle for the operator.
        logger.exception("unhandled error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "unhandled error; see server logs for this correlation id",
                    "retryable": False,
                    "payload": {},
                }
            },
            headers={CORRELATION_HEADER: getattr(request.state, "correlation_id", "")},
        )

    app.include_router(health_router)
    app.include_router(workflows_router)
    app.include_router(approvals_router)
    app.include_router(stream_router)
    app.include_router(console_router)
    app.include_router(chat_router)
    app.include_router(tasks_router)
    app.include_router(docs_router)

    app.mount("/static", StaticFiles(directory="server/static"), name="static")
    return app
