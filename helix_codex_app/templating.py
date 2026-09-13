"""Shared template rendering for the app shell and the feature routers.

One Jinja environment serves every page, and render() is the single place
that decorates a template context with the caller's CSRF token and the app
settings. Keeping it here instead of in app.py lets a feature router render
pages without importing the application factory, which would be circular.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def render(request: Request, name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
    """Render a template with the app settings and the caller's CSRF token."""
    session = getattr(request.state, "session", None)
    ctx = {
        "csrf_token": session.csrf_token if session else "",
        "settings": request.app.state.settings,
        **(context or {}),
    }
    return templates.TemplateResponse(request, name, ctx)
