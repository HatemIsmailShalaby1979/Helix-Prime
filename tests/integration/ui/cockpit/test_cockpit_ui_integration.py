"""Integration coverage for the Streamlit manager console.

Reconstructed from the scratch harness whose 46 checks are recorded in AGENTS.md
§19.4. Unlike the other two modules in this tier this is a faithful port rather than
a re-authoring: the original source was still available, so the sequence, the
assertions and the check labels are the ones that actually ran.

Driven through Streamlit's own ``AppTest``, which executes the real script against a
live ingest engine. The decision lifecycle test deliberately covers approve and
reject in one session: the engine raises at most one intervention at a time, so a
second rejection is only observable after the first decision has been recorded and
the post-decision cooldown has elapsed.

One check was made less brittle than the original: the autorefresh probe asserted
that the optional package was *absent*, which would fail the moment somebody
installed it. It now asserts the probe returns a boolean and reports which branch
the refresh cascade took.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import cockpit_ui
import telemetry_simulator as sim

from .conftest import LiveEngine

pytestmark = pytest.mark.ui_integration

REPO_ROOT = Path(__file__).resolve().parents[4]
UI_PATH = REPO_ROOT / "cockpit_ui.py"
DEAD_ENDPOINT = "http://127.0.0.1:9"
MANAGER_ID = "MGR-01"
SPIKE_AFTER = 3
FIRST_BATCH_TICKS = 8
SECOND_BATCH_TICKS = 24
EXPECTED_FLOOR_TILES = 5
TILES_PER_INTERVENTION = 4

Check = Callable[[str, bool, object], None]


def values(elements: Any) -> list[str]:
    """Stringify the ``value`` of each element in a Streamlit element list."""
    return [str(getattr(element, "value", "")) for element in elements]


def button_by_key(app: AppTest, key: str) -> Any | None:
    """Find a button by its widget key, or None."""
    for button in app.button:
        if button.key == key:
            return button
    return None


def build_app(endpoint: str) -> AppTest:
    """Run the console script once against the given engine endpoint."""
    app = AppTest.from_file(str(UI_PATH), default_timeout=20)
    app.session_state["endpoint"] = endpoint
    app.session_state["manager_id"] = MANAGER_ID
    app.run()
    return app


def feed_ticks(engine: LiveEngine, generator: sim.TelemetryGenerator, until_tick: int) -> None:
    """Advance the twin and POST each tick, so the engine's clock never rewinds."""

    async def feed() -> None:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            async for metrics in generator.generate_tick():
                if generator.tick_index == SPIKE_AFTER:
                    await generator.trigger_spike()
                payload = {
                    "metrics": metrics.model_dump(mode="json"),
                    "state": generator.state.model_dump(mode="json"),
                }
                await client.post(engine.telemetry_url, json=payload)
                if generator.tick_index >= until_tick:
                    break

    asyncio.run(feed())


class FakeState:
    """Minimal session-state stand-in: Streamlit state is inert outside a script run."""

    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def setdefault(self, key: str, default: object = None) -> object:
        """Mirror ``dict.setdefault``."""
        return self._data.setdefault(key, default)

    def get(self, key: str, default: object = None) -> object:
        """Mirror ``dict.get``."""
        return self._data.get(key, default)

    def __setitem__(self, key: str, value: object) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> object:
        return self._data[key]


def test_pure_helpers(check: Check) -> None:
    """The formatting and banding helpers the console renders with."""
    check(
        "severity bands",
        cockpit_ui._severity(70.0) == "critical"
        and cockpit_ui._severity(45.0) == "severe"
        and cockpit_ui._severity(5.0) == "moderate",
    )
    rendered = cockpit_ui._format_operational_time(1767600300.0)
    check("operational time rendered in UTC", rendered == "2026-01-05 08:05:00Z", rendered)
    check(
        "action labels humanised",
        cockpit_ui._action_label("PULL_AUX_TO_CALLS") == "Pull auxiliary agents to calls",
    )
    check("unknown action falls back", cockpit_ui._action_label("SOME_NEW_LEVER") == "Some New Lever")
    check(
        "empty payload narrowed safely",
        cockpit_ui._as_dict(None) == {} and cockpit_ui._as_dict([]) == {},
    )
    check(
        "autorefresh probe reports a boolean",
        isinstance(cockpit_ui.HAS_AUTOREFRESH, bool),
        f"optional package installed={cockpit_ui.HAS_AUTOREFRESH}",
    )
    check("poll interval matches the twin cadence", cockpit_ui.POLL_SECONDS == 2.0)


def test_decision_queue_primitives(check: Check) -> None:
    """on_click durability: the queue the buttons write to and the render drains."""
    original = cockpit_ui.st.session_state
    fake = FakeState()
    cockpit_ui.st.session_state = fake  # type: ignore[assignment]
    try:
        cockpit_ui._enqueue_decision("abc-123", "approve")
        cockpit_ui._enqueue_decision("abc-123", "approve")
        queue = fake.get("pending_decisions")
        check(
            "duplicate intent collapsed",
            isinstance(queue, list) and len(queue) == 1,
            f"queued={len(queue) if isinstance(queue, list) else '?'}",
        )
        cockpit_ui._enqueue_decision("def-456", "reject")
        queued = fake.get("pending_decisions")
        check("distinct intent queued", isinstance(queued, list) and len(queued) == 2)
        check(
            "queued payload shape",
            isinstance(queued, list)
            and queued[0] == {"intervention_id": "abc-123", "decision": "approve"},
            queued[0] if isinstance(queued, list) else queued,
        )
    finally:
        cockpit_ui.st.session_state = original


def test_decision_lifecycle(check: Check, engine: LiveEngine) -> None:
    """Floor status renders, then approve -> EXECUTED and reject -> REJECTED."""
    generator = sim.TelemetryGenerator(tick_seconds=0.001)
    feed_ticks(engine, generator, FIRST_BATCH_TICKS)

    state = engine.state()
    pending = state["pending_interventions"]
    check("engine holds a PENDING intervention", len(pending) == 1, f"pending={len(pending)}")
    if not pending:
        return
    intervention = pending[0]

    app = build_app(engine.base)
    check("no exception during render", not app.exception, str(app.exception))
    expected_tiles = EXPECTED_FLOOR_TILES + TILES_PER_INTERVENTION * len(pending)
    check(
        "five floor tiles plus four per intervention",
        len(app.metric) == expected_tiles,
        f"tiles={len(app.metric)} expected={expected_tiles}",
    )
    labels = [metric.label for metric in app.metric]
    for expected in (
        "Service level",
        "Calls waiting",
        "Longest wait",
        "Active agents",
        "Backlog velocity",
    ):
        check(f"tile present: {expected}", expected in labels)
    service = next(metric for metric in app.metric if metric.label == "Service level")
    check(
        "service level tile carries the 80% target delta",
        "80% target" in str(service.delta),
        f"{service.value} / {service.delta}",
    )
    check(
        "trigger condition surfaced as an alert",
        any("TRIGGER" in value for value in values(app.error)),
        values(app.error)[:1],
    )
    check(
        "reasoning trace rendered",
        any(str(intervention["reasoning_trace"])[:40] in str(block.value) for block in app.markdown),
    )
    check("action centre headed", any("Action centre" in str(item.value) for item in app.subheader))
    check("exposure shown in USD", any("$" in str(metric.value) for metric in app.metric))
    check(
        "header reports the simulated timebase",
        any("operational time" in value for value in values(app.caption)),
    )
    approve = button_by_key(app, f"approve-{intervention['id']}")
    check("approve button present", approve is not None)
    check("reject button present", button_by_key(app, f"reject-{intervention['id']}") is not None)
    if approve is None:
        return

    approve.click()
    app.run()
    check("no exception after approve", not app.exception, str(app.exception))
    check(
        "approval confirmed to the manager",
        any("approve accepted" in value.lower() for value in values(app.success)),
        values(app.success)[:1],
    )
    after = engine.state()
    decided = [item for item in after["recommendations"] if item["id"] == intervention["id"]]
    check(
        "engine recorded the decision",
        bool(decided) and decided[0]["status"] in {"APPROVED", "EXECUTED"},
        decided[0]["status"] if decided else "missing",
    )
    check("intervention cleared from the action centre", not after["pending_interventions"])
    check("audit trail rendered", len(app.dataframe) >= 1, f"frames={len(app.dataframe)}")
    approved_id = intervention["id"]
    audit = app.dataframe[0].value
    check(
        "audit row carries the decided status",
        intervention["id"][:8] in audit["ID"].tolist()
        and audit["Status"].tolist()[0] in {"APPROVED", "EXECUTED"},
        audit["Status"].tolist(),
    )

    feed_ticks(engine, generator, SECOND_BATCH_TICKS)
    pending = engine.state()["pending_interventions"]
    check("a second intervention was raised", len(pending) == 1, f"pending={len(pending)}")
    if not pending:
        return
    second = pending[0]
    app = build_app(engine.base)
    reject = button_by_key(app, f"reject-{second['id']}")
    check("reject button present for the new intervention", reject is not None)
    if reject is None:
        return
    reject.click()
    app.run()
    check("no exception after reject", not app.exception, str(app.exception))
    check(
        "rejection confirmed to the manager",
        any("reject accepted" in value.lower() for value in values(app.success)),
        values(app.success)[:1],
    )
    after = engine.state()
    recorded = [item for item in after["recommendations"] if item["id"] == second["id"]]
    check(
        "engine recorded REJECTED",
        bool(recorded) and recorded[0]["status"] == "REJECTED",
        recorded[0]["status"] if recorded else "missing",
    )
    check("rejected intervention left the action centre", not after["pending_interventions"])
    audit = app.dataframe[0].value
    by_id = dict(zip(audit["ID"].tolist(), audit["Status"].tolist(), strict=True))
    check("audit trail lists both interventions", len(audit) == 2, audit["ID"].tolist())
    check(
        "approved intervention advanced to EXECUTED",
        by_id.get(approved_id[:8]) == "EXECUTED",
        by_id,
    )
    check(
        "rejected intervention recorded as REJECTED",
        by_id.get(second["id"][:8]) == "REJECTED",
        by_id,
    )


def test_degraded_engine_unreachable(check: Check) -> None:
    """An engine that never answers is reported, not crashed on."""
    app = build_app(DEAD_ENDPOINT)
    check("no exception with the engine down", not app.exception, str(app.exception))
    check(
        "unreachable engine reported",
        any("unreachable" in value.lower() for value in values(app.error)),
        values(app.error)[:1],
    )


def test_stale_snapshot_retained(check: Check, engine: LiveEngine) -> None:
    """Losing the engine mid-session warns and keeps the floor status on screen.

    Ticks are fed first: the console renders the floor from the snapshot it cached,
    and an engine nobody has written to caches a snapshot with no metrics in it, so
    the retention claim is only meaningful once there is something to retain.
    """
    generator = sim.TelemetryGenerator(tick_seconds=0.001)
    feed_ticks(engine, generator, FIRST_BATCH_TICKS)

    app = build_app(engine.base)
    check("no exception against the live engine", not app.exception, str(app.exception))
    check(
        "floor rendered while the engine answers",
        len(app.metric) >= EXPECTED_FLOOR_TILES,
        f"tiles={len(app.metric)}",
    )
    app.session_state["endpoint"] = DEAD_ENDPOINT
    app.run()
    check("no exception when the engine drops", not app.exception, str(app.exception))
    check(
        "stale snapshot flagged",
        any("last snapshot" in value.lower() for value in values(app.warning)),
        values(app.warning)[:1],
    )
    check(
        "floor status still rendered from cache",
        len(app.metric) >= EXPECTED_FLOOR_TILES,
        f"tiles={len(app.metric)}",
    )
