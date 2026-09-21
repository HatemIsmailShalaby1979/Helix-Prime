"""Streamlit manager console for the Helix Ops Cockpit (human-in-the-loop surface).

Polls the ingest engine for the current ops summary and puts the decisions that
need a human in front of one: metrics at the top, live interventions in the
middle, and the audit trail underneath. The console owns no operational state of
its own beyond what it needs to survive a rerun -- the engine is the system of
record.

Data flow
    GET  /api/v1/cockpit/state    every 2 s, matching the twin's tick cadence
    POST /api/v1/cockpit/approve  once per manager decision, never retried

Polling
    The dashboard renders inside whichever refresh mechanism the installation
    offers, in this order: ``streamlit_autorefresh`` when that package is
    importable, otherwise the native ``st.fragment(run_every=...)``, otherwise a
    ``time.sleep`` + ``st.rerun`` loop. The fragment path is preferred over the
    sleep loop because it refreshes the panel without freezing the page, and it
    is native to Streamlit 1.37+. The dashboard reads its configuration from
    ``st.session_state`` rather than from arguments, so a timer refresh replays
    the current settings instead of the ones captured when the fragment was first
    called.

Click durability
    A decision is never taken inside an ``if st.button(...)`` branch. Those
    branches are one-shot: the button reports ``True`` on the single rerun that
    delivers the click, and a timer rerun landing first can reach the script
    before that branch does, dropping the manager's decision silently. Instead
    each button carries an ``on_click`` callback, which Streamlit invokes from the
    delivered widget state, exactly once, independently of the script body. The
    callback only appends to a session-state queue; the queue is drained at the
    top of the next render, which is where the POST happens.

Decision semantics
    Unlike telemetry, a decision is an authority action and is never retried
    automatically. A failed POST is reported to the manager, who decides again;
    the engine answers 409 for a second decision on the same intervention and 404
    for an unknown one, so a blind retry would only manufacture confusing errors.
    The queue is emptied before the POST so a rerun can never replay it, and every
    outcome -- including failure -- is surfaced as a flash message.

Degraded mode
    The last snapshot received is kept in session state. If a poll fails, the
    console renders that snapshot under a warning instead of blanking the floor
    status, and the next successful poll clears it.

Timebase
    Intervention timestamps come from the twin's simulated clock, not the wall
    clock, so the console labels them as operational time. The only wall-clock
    value on screen is the poll time in the header.

Run
    python -m streamlit run cockpit_ui.py
    python -m streamlit run cockpit_ui.py --server.address 127.0.0.1
"""

from __future__ import annotations

import importlib.util
import time
from datetime import datetime, timezone
from typing import Any, Callable, Final

import httpx
import pandas as pd
import streamlit as st

DEFAULT_ENDPOINT: Final[str] = "http://127.0.0.1:8000"
STATE_PATH: Final[str] = "/api/v1/cockpit/state"
APPROVE_PATH: Final[str] = "/api/v1/cockpit/approve"
DEFAULT_MANAGER_ID: Final[str] = "MGR-01"

POLL_SECONDS: Final[float] = 2.0
REQUEST_TIMEOUT_SECONDS: Final[float] = 2.0
SLA_TARGET_PERCENTAGE: Final[float] = 80.0
VELOCITY_TRIGGER_PER_TICK: Final[float] = 15.0
HISTORY_LIMIT: Final[int] = 60
AUDIT_ROWS: Final[int] = 15
TARGET_LABEL: Final[str] = "80% target"
PENDING_STATUS: Final[str] = "PENDING"

DECIDED_STATUSES: Final[frozenset[str]] = frozenset({"APPROVED", "REJECTED", "EXECUTED"})
ACTION_LABELS: Final[dict[str, str]] = {
    "PULL_AUX_TO_CALLS": "Pull auxiliary agents to calls",
    "OPEN_VOLUNTARY_OVERTIME": "Open voluntary overtime",
    "REROUTE_LOW_PRIORITY_QUEUES": "Reroute low-priority queues",
    "REBALANCING_SKILLS": "Rebalance skills",
}
SEVERITY_BANDS: Final[tuple[tuple[float, str], ...]] = (
    (65.0, "critical"),
    (40.0, "severe"),
    (0.0, "moderate"),
)


def _probe_autorefresh() -> bool:
    """Report whether the optional `streamlit_autorefresh` package is importable."""
    return importlib.util.find_spec("streamlit_autorefresh") is not None


HAS_AUTOREFRESH: Final[bool] = _probe_autorefresh()


def _autorefresh(interval_ms: int) -> None:
    """Arm the optional autorefresh component, imported only when it is present."""
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(interval=interval_ms, key="cockpit-refresh")


@st.cache_resource
def _client() -> httpx.Client:
    """One pooled HTTP client for the server process.

    The ambient proxy environment is ignored: this is a loopback control-plane
    call, and honouring a configured proxy would detour every poll through an
    intermediary.
    """
    return httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        trust_env=False,
        headers={"accept": "application/json"},
    )


def _format_operational_time(epoch_seconds: float) -> str:
    """Render a telemetry-clock timestamp as UTC, which is the twin's timebase."""
    moment = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%SZ")


def _severity(projected_drop: float) -> str:
    """Band a projected service-level drop into a label the console can show."""
    for threshold, label in SEVERITY_BANDS:
        if projected_drop >= threshold:
            return label
    return SEVERITY_BANDS[-1][1]


def _action_label(action: str) -> str:
    """Humanise a proposed action, preferring the curated label."""
    return ACTION_LABELS.get(action, action.replace("_", " ").title())


def _as_dict(value: Any) -> dict[str, Any]:
    """Narrow an untyped payload member to a dict, or to an empty one."""
    return value if isinstance(value, dict) else {}


def _fetch_state(client: httpx.Client, endpoint: str) -> tuple[dict[str, Any] | None, str | None]:
    """Read the ops summary, returning either the payload or a readable error."""
    try:
        response = client.get(f"{endpoint.rstrip('/')}{STATE_PATH}")
    except httpx.HTTPError as error:
        return None, type(error).__name__
    if response.status_code != httpx.codes.OK:
        return None, f"HTTP {response.status_code} {response.reason_phrase}"
    try:
        payload = response.json()
    except ValueError as error:
        return None, f"malformed JSON ({error})"
    if not isinstance(payload, dict):
        return None, "unexpected payload shape"
    return payload, None


def _post_decision(
    client: httpx.Client, endpoint: str, intervention_id: str, decision: str, manager_id: str
) -> tuple[bool, str]:
    """Submit one manager decision, translating every failure into a message."""
    body = {
        "intervention_id": intervention_id,
        "decision": decision,
        "manager_id": manager_id,
    }
    short_id = intervention_id[:8]
    try:
        response = client.post(f"{endpoint.rstrip('/')}{APPROVE_PATH}", json=body)
    except httpx.HTTPError as error:
        return False, (
            f"{decision} failed for {short_id}: engine unreachable "
            f"({type(error).__name__}) -- the intervention is still pending"
        )
    if response.status_code == httpx.codes.OK:
        try:
            status = response.json().get("intervention", {}).get("status", "recorded")
        except ValueError:
            status = "recorded"
        return True, f"{decision} accepted for {short_id} -- now {status}"
    if response.status_code == httpx.codes.NOT_FOUND:
        return False, f"{short_id} is unknown to the engine; refreshing"
    if response.status_code == httpx.codes.CONFLICT:
        return False, f"{short_id} was already decided by another manager"
    return False, (
        f"{decision} rejected for {short_id}: HTTP {response.status_code} "
        f"{response.reason_phrase} {response.text[:120]}"
    )


def _enqueue_decision(intervention_id: str, decision: str) -> None:
    """Widget callback: record the manager's intent without touching the network."""
    queue: list[dict[str, str]] = st.session_state.setdefault("pending_decisions", [])
    if any(item["intervention_id"] == intervention_id for item in queue):
        return
    queue.append({"intervention_id": intervention_id, "decision": decision})


def _drain_decisions(client: httpx.Client, endpoint: str, manager_id: str) -> bool:
    """Execute queued decisions exactly once, then ask for a rerun to clear them."""
    queue: list[dict[str, str]] = st.session_state.get("pending_decisions") or []
    if not queue:
        return False
    st.session_state["pending_decisions"] = []
    for item in queue:
        st.session_state["flash"] = _post_decision(
            client, endpoint, item["intervention_id"], item["decision"], manager_id
        )
    return True


def _remember_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Append the current sample to the session history, one entry per twin tick."""
    history: list[dict[str, Any]] = st.session_state.setdefault("history", [])
    metrics = _as_dict(payload.get("latest_metrics"))
    stamp = metrics.get("timestamp")
    if not isinstance(stamp, int | float):
        return history
    if not history or history[-1].get("timestamp") != stamp:
        history.append(metrics)
        del history[:-HISTORY_LIMIT]
    return history


def _previous(history: list[dict[str, Any]], key: str) -> float | None:
    """Second-to-last reading of a metric, for the delta shown on a tile."""
    if len(history) < 2:
        return None
    value = history[-2].get(key)
    return float(value) if isinstance(value, int | float) else None


def _render_metrics(payload: dict[str, Any], history: list[dict[str, Any]]) -> None:
    """Floor status: the five headline tiles, then the service-level trend."""
    metrics = _as_dict(payload.get("latest_metrics"))
    velocity = _as_dict(payload.get("velocity"))
    if not metrics:
        st.info("No telemetry has reached the engine yet.")
        return
    sla = float(metrics.get("sla_percentage", 0.0))
    waiting = float(metrics.get("calls_waiting", 0.0))
    longest = float(metrics.get("longest_wait_time", 0.0))
    agents = float(metrics.get("active_agents", 0.0))
    per_tick = float(velocity.get("backlog_velocity_per_tick", 0.0))
    previous_waiting = _previous(history, "calls_waiting")
    previous_longest = _previous(history, "longest_wait_time")
    previous_agents = _previous(history, "active_agents")

    columns = st.columns(5)
    columns[0].metric(
        "Service level",
        f"{sla:.1f}%",
        delta=f"{sla - SLA_TARGET_PERCENTAGE:+.1f}pt vs {TARGET_LABEL}",
        delta_color="normal",
    )
    columns[1].metric(
        "Calls waiting",
        f"{waiting:,.0f}",
        delta=None if previous_waiting is None else f"{waiting - previous_waiting:+,.0f}",
        delta_color="inverse",
    )
    columns[2].metric(
        "Longest wait",
        f"{longest:,.0f} s",
        delta=None if previous_longest is None else f"{longest - previous_longest:+,.0f} s",
        delta_color="inverse",
    )
    columns[3].metric(
        "Active agents",
        f"{agents:,.0f}",
        delta=None if previous_agents is None else f"{agents - previous_agents:+,.0f}",
        delta_color="normal",
    )
    columns[4].metric(
        "Backlog velocity",
        f"{per_tick:.1f}",
        delta=f"{per_tick - VELOCITY_TRIGGER_PER_TICK:+.1f} vs trigger",
        delta_color="inverse",
    )
    if len(history) >= 2:
        frame = pd.DataFrame(history)
        frame["Operational time"] = frame["timestamp"].map(_format_operational_time)
        st.line_chart(
            frame.set_index("Operational time")[["sla_percentage"]],
            x_label="operational time",
            y_label="service level %",
        )


def _render_intervention(recommendation: dict[str, Any]) -> None:
    """One pending intervention with its reasoning, exposure and decision buttons."""
    intervention_id = str(recommendation.get("id", ""))
    action = str(recommendation.get("proposed_action", ""))
    drop = float(recommendation.get("projected_sla_drop", 0.0))
    saving = float(recommendation.get("estimated_financial_saving_usd", 0.0))
    trace = str(recommendation.get("reasoning_trace", "no trace recorded"))
    with st.container(border=True):
        st.error(f"TRIGGER — {recommendation.get('trigger_condition', 'unspecified')}")
        st.subheader(f"{_action_label(action)} · {_severity(drop)}")
        columns = st.columns(4)
        columns[0].metric("SLA at raise", f"{float(recommendation.get('current_sla', 0.0)):.1f}%")
        columns[1].metric("Projected drop", f"{drop:.1f}pt")
        columns[2].metric("Exposure avoided", f"${saving:,.0f}")
        columns[3].metric(
            "Raised at", _format_operational_time(float(recommendation.get("timestamp", 0.0)))
        )
        st.markdown("**Reasoning trace**")
        st.markdown(f"> {trace}".replace("\n", "\n> "))
        approve, reject, reference = st.columns([1, 1, 4])
        approve.button(
            "Approve",
            key=f"approve-{intervention_id}",
            type="primary",
            on_click=_enqueue_decision,
            args=(intervention_id, "approve"),
        )
        reject.button(
            "Reject",
            key=f"reject-{intervention_id}",
            on_click=_enqueue_decision,
            args=(intervention_id, "reject"),
        )
        reference.caption(f"id {intervention_id[:8]}")


def _render_interventions(payload: dict[str, Any]) -> None:
    """The action centre: everything currently awaiting a manager decision."""
    pending = [
        item
        for item in payload.get("pending_interventions") or []
        if isinstance(item, dict) and item.get("status") == PENDING_STATUS
    ]
    st.subheader("Action centre")
    if not pending:
        st.success("No intervention is awaiting a decision.")
        return
    st.caption(f"{len(pending)} intervention(s) awaiting a decision.")
    for recommendation in pending:
        _render_intervention(recommendation)


def _render_audit(payload: dict[str, Any]) -> None:
    """Recent decided interventions, newest first, on the operational clock."""
    decided = [
        item
        for item in payload.get("recommendations") or []
        if isinstance(item, dict) and item.get("status") in DECIDED_STATUSES
    ]
    st.subheader("Audit trail")
    if not decided:
        st.caption("No intervention has been decided yet.")
        return
    decided.sort(key=lambda item: float(item.get("timestamp", 0.0)), reverse=True)
    rows = [
        {
            "Operational time": _format_operational_time(float(item.get("timestamp", 0.0))),
            "Status": item.get("status", ""),
            "Action": _action_label(str(item.get("proposed_action", ""))),
            "Trigger": item.get("trigger_condition", ""),
            "SLA at raise": f"{float(item.get('current_sla', 0.0)):.1f}%",
            "Projected drop": f"{float(item.get('projected_sla_drop', 0.0)):.1f}pt",
            "Exposure avoided": f"${float(item.get('estimated_financial_saving_usd', 0.0)):,.0f}",
            "ID": str(item.get("id", ""))[:8],
        }
        for item in decided[:AUDIT_ROWS]
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption(
        "Operational time is the twin's simulated clock. EXECUTED follows APPROVED "
        "once the control loop dispatches the action on the next ingested tick."
    )


def _render_header(payload: dict[str, Any], error: str | None) -> None:
    """Header line: freshness, window depth, control-plane state, and staleness."""
    metrics = _as_dict(payload.get("latest_metrics"))
    twin_state = _as_dict(payload.get("latest_state"))
    parts = [
        f"polled {datetime.now().strftime('%H:%M:%S')}",
        f"window {payload.get('window_samples', 0)} samples",
        f"operational time {_format_operational_time(float(metrics.get('timestamp', 0.0)))}",
    ]
    if twin_state.get("is_spike_active"):
        parts.append("VOLUME SPIKE ACTIVE")
    st.caption(" · ".join(parts))
    if error is not None:
        st.warning(f"Engine is not answering ({error}) — showing the last snapshot received.")


def render_dashboard() -> None:
    """One full render: drain decisions, poll, metrics, action centre, audit."""
    client = _client()
    endpoint = st.session_state.get("endpoint", DEFAULT_ENDPOINT)
    manager_id = st.session_state.get("manager_id", DEFAULT_MANAGER_ID)

    if _drain_decisions(client, endpoint, manager_id):
        st.rerun()

    payload, error = _fetch_state(client, endpoint)
    if payload is None:
        cached = st.session_state.get("last_good")
        if not isinstance(cached, dict):
            st.error(f"Engine unreachable at {endpoint} — {error}")
            return
        payload = cached

    st.session_state["last_good"] = payload
    flash = st.session_state.pop("flash", None)
    if isinstance(flash, tuple) and len(flash) == 2:
        (st.success if flash[0] else st.error)(flash[1])

    history = _remember_metrics(payload)
    _render_header(payload, error)
    _render_metrics(payload, history)
    st.divider()
    _render_interventions(payload)
    st.divider()
    _render_audit(payload)


def _sidebar() -> None:
    """Operator settings: who is deciding, and which engine they decide against."""
    st.sidebar.title("Cockpit console")
    st.sidebar.text_input("Manager ID", value=DEFAULT_MANAGER_ID, key="manager_id")
    st.sidebar.text_input("Ingest engine", value=DEFAULT_ENDPOINT, key="endpoint")
    st.sidebar.caption(
        f"Polling {STATE_PATH} every {POLL_SECONDS:.0f}s. Decisions post to "
        f"{APPROVE_PATH} once and are never retried automatically."
    )


def _refresh(run: Callable[[], None]) -> None:
    """Run the dashboard under the best refresh mechanism the installation offers."""
    if HAS_AUTOREFRESH:
        _autorefresh(int(POLL_SECONDS * 1000))
        run()
        return
    if hasattr(st, "fragment"):
        st.fragment(run_every=POLL_SECONDS)(run)()
        return
    run()
    time.sleep(POLL_SECONDS)
    st.rerun()


def main() -> None:
    """Entry point for `streamlit run cockpit_ui.py`."""
    st.set_page_config(
        page_title="Helix Ops Cockpit",
        page_icon="§",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _sidebar()
    st.title("Helix Ops Cockpit")
    st.caption(
        "Human-in-the-loop console for the ingest engine. Telemetry is simulated by the "
        "operations twin; every decision taken here is recorded as an authority action."
    )
    _refresh(render_dashboard)


if __name__ == "__main__":
    main()
