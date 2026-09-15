"""The memory surface: a person's governed memory and their proposals.

The screen lists the account's own records and proposals. The API routes drive
the lifecycle: propose, evaluate, approve, reject, roll back. Approval and
rejection both need the memory.review permission, and the engine's separation of
duties decides whether the caller may review this particular proposal — a person
can never approve their own.

Every route is scoped to the signed-in account's own ledger. There is no route
that takes a proposal id belonging to somebody else and returns it.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from helix_codex_app.db import close, connect
from helix_codex_app.errors import AppError
from helix_codex_app.modules.memory.service import MemoryService
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.templating import render

memory_router = APIRouter(
    prefix="/app",
    dependencies=[
        Depends(current_account),
        Depends(require_permission("memory.propose")),
    ],
)

_REVIEW_DEP = [Depends(require_csrf), Depends(require_permission("memory.review"))]
_WRITE_DEP = [Depends(require_csrf)]


@memory_router.get("/memory", response_model=None)
def memory_screen(request: Request) -> HTMLResponse:
    """The account's own memory: recent records and the proposal list."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MemoryService(conn, memory_root=_memory_root(request))
        context = _page_context(service, account)
    finally:
        close(conn)
    return render(request, "memory.html", context)


@memory_router.get("/memory/proposals", response_model=None)
def proposals_screen(request: Request) -> JSONResponse:
    """The account's proposals as JSON, optionally filtered by state."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MemoryService(conn, memory_root=_memory_root(request))
        state = request.query_params.get("state") or None
        rows = service.list_proposals(account, state=state)
    finally:
        close(conn)
    return JSONResponse({"proposals": [_row_dict(row) for row in rows]})


@memory_router.get("/memory/proposals/{proposal_id}", response_model=None)
def proposal_screen(request: Request, proposal_id: str) -> JSONResponse:
    """One proposal with its evidence report and its review history."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MemoryService(conn, memory_root=_memory_root(request))
        report = service.evidence_report(account, proposal_id)
        reviews = [dict(row) for row in service.list_reviews(proposal_id)]
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    finally:
        close(conn)
    return JSONResponse({"proposal": report, "reviews": reviews})


@memory_router.get("/memory/ledger/verify", response_model=None)
def ledger_verify(request: Request) -> JSONResponse:
    """Verify the account's own ledger chain."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MemoryService(conn, memory_root=_memory_root(request))
        result = service.verify_ledger(account)
    finally:
        close(conn)
    return JSONResponse(result)


@memory_router.post("/api/memory/proposals", response_model=None, dependencies=_WRITE_DEP)
async def create_proposal(request: Request) -> JSONResponse:
    """Record a new proposal in the account's own ledger."""
    account = _account(request)
    conn = _conn(request)
    try:
        raw = await _payload(request)
        service = MemoryService(conn, memory_root=_memory_root(request))
        proposal = service.propose(
            account,
            kind=str(raw.get("kind", "")).strip(),
            target=str(raw.get("target", "")).strip(),
            baseline=str(raw.get("baseline", "")),
            proposed=str(raw.get("proposed", "")),
            baseline_policy=_json_field(raw, "baseline_policy"),
            proposed_policy=_json_field(raw, "proposed_policy"),
            hypothesis=str(raw.get("hypothesis", "")),
            risk_assessment=str(raw.get("risk_assessment", "")),
            rollback_plan=str(raw.get("rollback_plan", "")),
            evidence=_list_field(raw, "evidence"),
            min_improvement=float(raw.get("min_improvement", 0) or 0),
        )
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse(
        {"proposal_id": proposal.proposal_id, "state": proposal.approval_state}, 201
    )


@memory_router.post(
    "/api/memory/proposals/{proposal_id}/evaluate", response_model=None, dependencies=_WRITE_DEP
)
async def evaluate_proposal(request: Request, proposal_id: str) -> JSONResponse:
    """Score the proposed policy against the baseline and store the result."""
    account = _account(request)
    conn = _conn(request)
    try:
        service = MemoryService(conn, memory_root=_memory_root(request))
        result = service.evaluate(account, proposal_id)
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse({"evaluation": result.__dict__})


@memory_router.post(
    "/api/memory/proposals/{proposal_id}/approve", response_model=None, dependencies=_REVIEW_DEP
)
async def approve_proposal(request: Request, proposal_id: str) -> JSONResponse:
    """Approve a proposal, subject to the engine's separation of duties."""
    return await _review_action(request, proposal_id, "approve")


@memory_router.post(
    "/api/memory/proposals/{proposal_id}/reject", response_model=None, dependencies=_REVIEW_DEP
)
async def reject_proposal(request: Request, proposal_id: str) -> JSONResponse:
    """Reject a proposal. A reason is required."""
    return await _review_action(request, proposal_id, "reject")


@memory_router.post(
    "/api/memory/proposals/{proposal_id}/rollback", response_model=None, dependencies=_REVIEW_DEP
)
async def rollback_proposal(request: Request, proposal_id: str) -> JSONResponse:
    """Roll an applied proposal back."""
    return await _review_action(request, proposal_id, "rollback")


async def _review_action(request: Request, proposal_id: str, action: str) -> JSONResponse:
    account = _account(request)
    conn = _conn(request)
    try:
        raw = await _payload(request)
        reason = str(raw.get("reason", "")).strip() or request.query_params.get("reason", "")
        service = MemoryService(conn, memory_root=_memory_root(request))
        if action == "approve":
            proposal = service.approve(account, proposal_id, reason=reason)
        elif action == "reject":
            proposal = service.reject(account, proposal_id, reason=reason)
        else:
            proposal = service.rollback(account, proposal_id, reason=reason)
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    finally:
        close(conn)
    return JSONResponse({"proposal_id": proposal.proposal_id, "state": proposal.approval_state})


def _page_context(service: MemoryService, account: Account) -> dict[str, Any]:
    proposals = service.list_proposals(account)
    return {
        "active_nav": "memory",
        "account": account,
        "records": service.stores.read(account, limit=20),
        "proposals": proposals,
        "proposal_rows": [_row_dict(row) for row in proposals],
        "ledger": service.verify_ledger(account),
        "data_mode": "simulated_realistic",
    }


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        "proposal_id": row.proposal_id,
        "kind": row.kind,
        "target": row.target,
        "state": row.state,
        "version": row.version,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _memory_root(request: Request) -> str | None:
    return getattr(request.app.state.settings, "memory_root", None)


def _account(request: Request) -> Account:
    return request.state.account


def _conn(request: Request):
    return connect(db_path=request.app.state.settings.db_path)


async def _payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    return {key: str(value) for key, value in form.multi_items()}


def _json_field(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError(f"{key} must be a JSON object")
        return parsed
    return {}


def _list_field(raw: dict[str, Any], key: str) -> list[str]:
    value = raw.get(key)
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []
