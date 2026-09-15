"""The operations surface: engine overview, governed submission, approvals.

Every route here is gated by ops.view at the router boundary, so an employee
never reaches any of it. Submission and approval both answer an HTMX fragment
when the request came from the browser, so a card updates in place rather than
reloading the page.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from helix_codex_app.errors import AppError
from helix_codex_app.integration.sse_bridge import encode, publish, subscribe, unsubscribe
from helix_codex_app.modules.ops.service import OpsService, workflow_card
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.templating import render

HEARTBEAT_SECONDS = 15
STREAM_KEY_PREFIX = "workflow:"

ops_router = APIRouter(
    prefix="/app",
    dependencies=[
        Depends(current_account),
        Depends(require_permission("ops.view")),
    ],
)


@ops_router.get("/ops", response_model=None)
def ops_screen(request: Request) -> HTMLResponse:
    """The engine overview: status per engine, counts, and recent requests."""
    account = _account(request)
    try:
        overview = OpsService().overview(account)
    except AppError as exc:
        return render(
            request,
            "ops.html",
            {"active_nav": "ops", "account": account, "error": exc.to_dict()},
            status_code=exc.status_code,
        )
    return render(
        request,
        "ops.html",
        {"active_nav": "ops", "account": account, **overview, "data_mode": "simulated_realistic"},
    )


@ops_router.get("/ops/{engine_id}", response_model=None)
def ops_engine_screen(request: Request, engine_id: str) -> HTMLResponse:
    """One engine's status and the tenant's requests on its capabilities."""
    account = _account(request)
    try:
        detail = OpsService().engine_detail(account, engine_id)
    except AppError as exc:
        return render(
            request,
            "ops_engine.html",
            {"active_nav": "ops", "account": account, "error": exc.to_dict()},
            status_code=exc.status_code,
        )
    return render(
        request,
        "ops_engine.html",
        {
            "active_nav": "ops",
            "account": account,
            **detail,
            "data_mode": "simulated_realistic",
        },
    )


@ops_router.post("/api/ops/workflows", response_model=None, dependencies=[Depends(require_csrf)])
async def submit_workflow(request: Request) -> JSONResponse:
    """Submit a governed request. It lands at the gate, not in the engine."""
    account = _account(request)
    try:
        raw = await _payload(request)
        workflow = OpsService().submit(
            account,
            capability=str(raw.get("capability", "")),
            input_payload=_json_field(raw, "input_payload"),
            requires_approval=_bool_field(raw, "requires_approval", default=True),
            idempotency_key=str(raw.get("idempotency_key", "")).strip() or None,
        )
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    card = workflow_card(workflow)
    publish(STREAM_KEY_PREFIX + workflow.workflow_id, "state", card)
    return JSONResponse(card, status_code=201)


@ops_router.get("/api/ops/workflows/{workflow_id}", response_model=None)
def workflow_detail(request: Request, workflow_id: str) -> JSONResponse:
    """One workflow, scoped to the caller's tenant."""
    account = _account(request)
    try:
        workflow = OpsService().detail(account, workflow_id)
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    return JSONResponse(workflow_card(workflow))


@ops_router.post(
    "/api/ops/workflows/{workflow_id}/approve",
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
async def approve_workflow(request: Request, workflow_id: str) -> JSONResponse | HTMLResponse:
    """Decide one workflow. Separation of duties is the core's call."""
    account = _account(request)
    try:
        raw = await _payload(request)
        decision = str(raw.get("decision", "approve")).strip() or "approve"
        reason = str(raw.get("reason", "")).strip()
        workflow = OpsService().approve(account, workflow_id, decision=decision, reason=reason)
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    card = workflow_card(workflow)
    publish(STREAM_KEY_PREFIX + workflow.workflow_id, "state", card)
    if request.headers.get("hx-request") == "true":
        return render(request, "partials/workflow_card.html", {"card": card, "can_decide": False})
    return JSONResponse(card)


@ops_router.get("/api/ops/stream/{workflow_id}", response_model=None)
async def workflow_stream(request: Request, workflow_id: str) -> StreamingResponse:
    """The live state stream for one workflow.

    The tenant check runs before the stream opens, so a workflow belonging to
    another tenant never gets a stream, and the generator itself touches nothing
    but the bus.
    """
    account = _account(request)
    OpsService().detail(account, workflow_id)
    return StreamingResponse(
        _workflow_frames(request, workflow_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _workflow_frames(request: Request, workflow_id: str):
    """Yield SSE frames for one workflow until the client goes away.

    Split out from the route so a test can drive it directly: an ASGI client
    cannot stream an infinite response to completion. The comment frame keeps
    a proxy from closing an idle stream.
    """
    key = STREAM_KEY_PREFIX + workflow_id
    queue = subscribe(key)
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield encode(frame["event"], frame["data"])
    finally:
        unsubscribe(key, queue)


def _account(request: Request) -> Account:
    return request.state.account


async def _payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    return {key: str(value) for key, value in form.multi_items()}


def _json_field(raw: dict[str, Any], key: str) -> dict[str, Any]:
    import json

    value = raw.get(key)
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError(f"{key} must be a JSON object")
        return parsed
    return {}


def _bool_field(raw: dict[str, Any], key: str, *, default: bool) -> bool:
    value = raw.get(key)
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")
