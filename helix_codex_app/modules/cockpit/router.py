"""The cockpit surface: the owner's board, behind a manager-and-owner gate.

Every route is gated by cockpit.view at the router boundary, so an employee never
reaches any of them. The screens are read-only, and the service re-checks the
permission before it computes anything, so a route added later without the
dependency still fails closed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from helix_codex_app.errors import AppError
from helix_codex_app.modules.cockpit.service import CockpitService
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_permission
from helix_codex_app.templating import render

cockpit_router = APIRouter(
    prefix="/app",
    dependencies=[
        Depends(current_account),
        Depends(require_permission("cockpit.view")),
    ],
)


@cockpit_router.get("/cockpit", response_model=None)
def cockpit_landing(request: Request) -> HTMLResponse:
    """The cockpit landing: the owner's numbers and the sections on offer."""
    account = _account(request)
    try:
        context = CockpitService().landing(account)
    except AppError as exc:
        return render(
            request,
            "cockpit.html",
            {"active_nav": "cockpit", "account": account, "error": exc.to_dict()},
            status_code=exc.status_code,
        )
    return render(
        request,
        "cockpit.html",
        {"active_nav": "cockpit", "account": account, **context},
    )


@cockpit_router.get("/cockpit/owner", response_model=None)
def cockpit_owner(request: Request) -> HTMLResponse:
    """The owner's board: five numbers, attendance, at-risk, the approval queue."""
    account = _account(request)
    try:
        context = CockpitService().owner(account)
    except AppError as exc:
        return render(
            request,
            "cockpit_owner.html",
            {"active_nav": "cockpit", "account": account, "error": exc.to_dict()},
            status_code=exc.status_code,
        )
    return render(
        request,
        "cockpit_owner.html",
        {"active_nav": "cockpit", "account": account, **context},
    )


@cockpit_router.get("/api/cockpit/summary", response_model=None)
def cockpit_summary(request: Request) -> JSONResponse:
    """The owner summary as JSON, for the same numbers without the page."""
    account = _account(request)
    try:
        summary = CockpitService().summary(account)
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    return JSONResponse(summary)


def _account(request: Request) -> Account:
    return request.state.account
