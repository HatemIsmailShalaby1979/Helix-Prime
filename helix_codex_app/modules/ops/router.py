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
from helix_codex_app.integration import engine_bridge
from helix_codex_app.integration.sse_bridge import encode, publish, subscribe, unsubscribe
from helix_codex_app.modules.ops.service import OpsService, workflow_card
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.guard import current_account, require_csrf, require_permission
from helix_codex_app.security.route_limits import (
    WFM_DEMO_SCREEN,
    WFM_DEMO_SUBMIT,
    limit_route,
)
from helix_codex_app.templating import render

HEARTBEAT_SECONDS = 15
STREAM_KEY_PREFIX = "workflow:"
# The demo's entire request surface, derived from the bridge's own validation
# ranges so the two cannot disagree about which fields exist.
WFM_DEMO_FIELDS = frozenset(engine_bridge.WFM_DEMO_NUMERIC_RANGES)
# The demo form's labels, defaults and unit explanations. The field ORDER and the
# set of names come from the bridge's own validation ranges, so a field can never
# appear on the form that the endpoint would refuse, or hide one it would accept.
WFM_DEMO_FIELD_HELP: dict[str, dict[str, Any]] = {
    "arrival_rate": {
        "label": "Calls per hour",
        "default": 14.2,
        "unit": "calls/hour",
        "hint": "How many calls arrive in an average hour. Must be above zero.",
    },
    "average_handling_time": {
        "label": "Average handling time",
        "default": 6.0,
        "unit": "minutes/call",
        "hint": "How long one call takes, wrap-up included. Must be above zero.",
    },
    "service_level_target": {
        "label": "Service-level target",
        "default": 0.8,
        "unit": "fraction",
        "hint": "The share of callers you want answered within 20 seconds. 0.8 means 80%.",
    },
    "average_calls_per_period": {
        "label": "Calls per day (your own history)",
        "default": engine_bridge.WFM_DEMO_AVERAGE_CALLS_PER_PERIOD,
        "unit": "calls/day",
        "hint": "The arrival history the forecast is compared against.",
    },
}
# Built in the engine's order, so the form reads the way the engine validates.
# A name with no label raises KeyError here at import, and a label with no field
# raises RuntimeError: the form and the endpoint cannot drift in either direction.
WFM_DEMO_FORM_FIELDS: list[dict[str, Any]] = [
    {"name": _name, **WFM_DEMO_FIELD_HELP[_name]} for _name in engine_bridge.WFM_DEMO_NUMERIC_RANGES
]
if set(WFM_DEMO_FIELD_HELP) != set(engine_bridge.WFM_DEMO_NUMERIC_RANGES):
    raise RuntimeError(
        "WFM_DEMO_FIELD_HELP and the engine's own ranges must name the same fields; "
        f"labels={sorted(WFM_DEMO_FIELD_HELP)}, "
        f"fields={sorted(engine_bridge.WFM_DEMO_NUMERIC_RANGES)}"
    )

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


@ops_router.get(
    "/ops/demo",
    response_model=None,
    dependencies=[Depends(limit_route(WFM_DEMO_SCREEN))],
)
def ops_demo_screen(request: Request) -> HTMLResponse:
    """The clickable WFM demo: four numbers in, one governed run out.

    Declared before `/ops/{engine_id}` deliberately. FastAPI matches in
    declaration order, so a screen added below the engine path would be
    swallowed as an engine whose id is "demo" and answered with an engine-lookup
    failure rather than this page.
    """
    account = _account(request)
    return render(
        request,
        "ops_demo.html",
        {
            "active_nav": "ops_demo",
            "account": account,
            "fields": WFM_DEMO_FORM_FIELDS,
            "data_mode": "simulated_realistic",
        },
    )


@ops_router.get("/ops/audit/{correlation_id}", response_model=None)
def ops_audit_screen(request: Request, correlation_id: str) -> HTMLResponse:
    """The recorded governance trail for one correlation id, read-only.

    Declared before `/ops/{engine_id}` for the same reason `/ops/demo` is: below
    the catch-all this path would be answered as an engine whose id is "audit".

    Nothing on this page is computed. The gate decision, the timestamps, the actor
    handoff and the executed/succeeded state are all read back from what the core
    already wrote, and the page says so rather than implying it re-derived them.
    """
    account = _account(request)
    return render(
        request,
        "ops_audit.html",
        {
            "active_nav": "ops_audit",
            "account": account,
            "trail": OpsService().audit_trail(account, correlation_id),
            "data_mode": "simulated_realistic",
        },
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


@ops_router.post(
    "/api/ops/demo/wfm",
    response_model=None,
    dependencies=[Depends(require_csrf), Depends(limit_route(WFM_DEMO_SUBMIT))],
)
async def run_wfm_demo(request: Request) -> JSONResponse | HTMLResponse:
    """Run the public WFM demo: governed submit, then governed execute.

    One request, one workflow, both lifecycle gates crossed. The four numeric
    inputs are the only thing a caller may set, and an unrecognised key is
    refused rather than ignored — a demo that silently dropped `is_sample` or
    `max_agents` from a request would look like it honoured them.

    A successful run answers JSON (201) to an API caller and the result fragment
    to htmx, so the screen can swap in place. Failures stay JSON on both paths:
    `shell.js` turns a non-2xx htmx response into a toast, which is the module's
    existing error convention rather than a second way to render a refusal.
    """
    account = _account(request)
    try:
        raw = await _payload(request)
        unknown = sorted(set(raw) - WFM_DEMO_FIELDS)
        if unknown:
            raise ValueError(
                f"the WFM demo accepts only {sorted(WFM_DEMO_FIELDS)}; refused {unknown}"
            )
        arrival_rate = _number_field(raw, "arrival_rate")
        average_handling_time = _number_field(raw, "average_handling_time")
        service_level_target = _number_field(raw, "service_level_target")
        average_calls_per_period = _number_field(
            raw,
            "average_calls_per_period",
            default=engine_bridge.WFM_DEMO_AVERAGE_CALLS_PER_PERIOD,
        )
        report = OpsService().wfm_demo(
            account,
            arrival_rate=arrival_rate,
            average_handling_time=average_handling_time,
            service_level_target=service_level_target,
            average_calls_per_period=average_calls_per_period,
        )
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    publish(STREAM_KEY_PREFIX + report["workflow_id"], "execution", report)
    if request.headers.get("hx-request") == "true":
        return render(
            request,
            "partials/wfm_demo_result.html",
            {
                "report": report,
                # What THIS run was given, not what the form now holds. A user
                # can retype a field after a run; showing the current value
                # beside the old result would quietly misreport the request.
                "inputs": {
                    "arrival_rate": arrival_rate,
                    "average_handling_time": average_handling_time,
                    "service_level_target": service_level_target,
                    "average_calls_per_period": average_calls_per_period,
                },
            },
        )
    return JSONResponse(report, status_code=201)


@ops_router.get("/api/ops/workflows/{workflow_id}", response_model=None)
def workflow_detail(request: Request, workflow_id: str) -> JSONResponse:
    """One workflow, scoped to the caller's tenant."""
    account = _account(request)
    try:
        workflow = OpsService().detail(account, workflow_id)
    except AppError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)
    return JSONResponse(workflow_card(workflow))


@ops_router.get("/api/ops/audit/{correlation_id}", response_model=None)
def audit_trail_json(request: Request, correlation_id: str) -> JSONResponse:
    """The same recorded trail the screen shows, for a machine caller."""
    account = _account(request)
    return JSONResponse(OpsService().audit_trail(account, correlation_id))


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


def _number_field(
    raw: dict[str, Any],
    key: str,
    *,
    default: float | None = None,
) -> Any:
    """One numeric request field, coerced from a form string or a JSON number.

    Only transport coercion happens here. Whether the number is in range is the
    bridge's business, so the same rule applies to a form post and a JSON body.
    """
    value = raw.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is None:
            raise ValueError(f"{key} is required")
        return default
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a number, got {value!r}")
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except ValueError:
        raise ValueError(f"{key} must be a number, got {value!r}") from None
