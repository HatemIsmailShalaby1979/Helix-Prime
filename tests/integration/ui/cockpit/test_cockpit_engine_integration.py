"""Integration coverage for the ingest engine's ingest, WebSocket and writer paths.

Reconstructed from the scratch harness whose 34 checks are recorded in AGENTS.md
§19.4, converted from script-style to pytest so a regression fails a named test
instead of printing a FAIL line into a console nobody reads.

Provenance, because it is not uniform:

* ``test_stream_lifecycle`` is a faithful port of the original session test -- the
  same sequence, the same 17 checks, the same assertions.
* The five ``ConnectionManager`` tests and the lifespan test are **re-authored
  equivalents**. The original bodies were lost with the scratch file; only their
  labels and intent survived. Each asserts the same property the label names.

The twin is driven in-process here rather than through a subprocess, so this module
needs no live server and no port.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import telemetry_simulator as sim
from ingest_engine import CockpitStateEngine, ConnectionManager, create_app

pytestmark = pytest.mark.ui_integration

TICKS = 22
SPIKE_AFTER = 10
APPROVE_TICK = 13
SEND_TIMEOUT_SECONDS = 0.2
PRUNE_SETTLE_SECONDS = 0.4
INGEST_LATENCY_BUDGET_SECONDS = 0.25

Check = Callable[[str, bool, object], None]


def build_payloads(ticks: int, spike_after: int) -> list[dict[str, Any]]:
    """Drive the twin in-process and collect the envelopes its stdout would carry."""

    async def collect() -> list[dict[str, Any]]:
        generator = sim.TelemetryGenerator(tick_seconds=0.001)
        payloads: list[dict[str, Any]] = []
        async for metrics in generator.generate_tick():
            if generator.tick_index == spike_after:
                await generator.trigger_spike()
            payloads.append(
                {
                    "metrics": metrics.model_dump(mode="json"),
                    "state": generator.state.model_dump(mode="json"),
                }
            )
            if generator.tick_index >= ticks:
                break
        return payloads

    return asyncio.run(collect())


class FakeSocket:
    """Stand-in for a WebSocket whose failure mode the test chooses."""

    def __init__(self, name: str, mode: str = "ok") -> None:
        self.name = name
        self.mode = mode
        self.sent: list[dict[str, Any]] = []
        self.accepted = False

    async def accept(self) -> None:
        """Record the handshake."""
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        """Behave as the test configured: succeed, drop, raise, or stall."""
        if self.mode == "disconnect":
            raise WebSocketDisconnect(code=1006)
        if self.mode == "runtime":
            raise RuntimeError("Unexpected ASGI message 'websocket.send'")
        if self.mode == "stall":
            await asyncio.sleep(60)
        self.sent.append(data)


def _exercise_stream(
    client: TestClient,
    manager: ConnectionManager,
    payloads: list[dict[str, Any]],
    check: Check,
) -> None:
    """The original session: connect, ping, forward ticks, decide, then prune."""
    with client.websocket_connect("/ws/v1/cockpit/stream") as websocket:
        sequences: list[int] = []

        def take() -> dict[str, Any]:
            frame = websocket.receive_json()
            sequences.append(frame["seq"])
            return frame

        first = take()
        check("snapshot frame delivered on connect", first["type"] == "cockpit_snapshot", first["type"])
        check("snapshot carries cockpit state", "recommendations" in first["payload"])
        check("subscriber registered", manager.client_count == 1, f"clients={manager.client_count}")

        websocket.send_text("ping")
        pong = take()
        check("bare ping answered", pong["type"] == "pong", pong["type"])
        websocket.send_json({"type": "ping"})
        check("json ping answered", take()["type"] == "pong")
        websocket.send_text("not-a-ping")
        websocket.send_json({"type": "hello"})

        triggered_frames = 0
        updated_frames = 0
        approved = False
        intervention_id: str | None = None
        for index, payload in enumerate(payloads, start=1):
            body = client.post("/api/v1/telemetry", json=payload).json()
            expected = (
                1 + (1 if body["newly_generated"] else 0) + len(body["executed_interventions"])
            )
            frames = [take() for _ in range(expected)]
            if index == 1:
                tick = frames[0]
                check("telemetry_tick frame emitted", tick["type"] == "telemetry_tick", tick["type"])
                check(
                    "tick carries metrics + velocity",
                    tick["payload"]["metrics"]["calls_waiting"]
                    == payload["metrics"]["calls_waiting"]
                    and "backlog_velocity_per_tick" in tick["payload"]["velocity"],
                )
                check("tick carries twin state", "is_spike_active" in tick["payload"]["state"])
            for frame in frames:
                if frame["type"] == "intervention_triggered":
                    triggered_frames += 1
                    if intervention_id is None:
                        intervention_id = frame["payload"]["id"]
                        check(
                            "triggered frame carries recommendation schema",
                            "reasoning_trace" in frame["payload"],
                        )
                elif frame["type"] == "intervention_updated":
                    updated_frames += 1
            if intervention_id and not approved and index == APPROVE_TICK:
                decision = client.post(
                    "/api/v1/cockpit/approve",
                    json={
                        "intervention_id": intervention_id,
                        "decision": "approve",
                        "manager_id": "MGR-07",
                    },
                )
                approved = True
                check("approve returns 200", decision.status_code == 200, str(decision.status_code))
                update = take()
                updated_frames += 1
                check(
                    "intervention_updated after decision",
                    update["type"] == "intervention_updated",
                    update["type"],
                )
                check(
                    "update carries APPROVED status",
                    update["payload"]["intervention"]["status"] == "APPROVED",
                )

        check(
            "frames are strictly sequenced",
            sequences == sorted(sequences)
            and len(sequences) == len(set(sequences))
            and sequences[0] == 1,
            f"seq={sequences[:6]}...n={len(sequences)}",
        )
        check(
            "intervention_triggered broadcast fired",
            triggered_frames >= 1,
            f"count={triggered_frames}",
        )
        check(
            "intervention_updated broadcast fired for EXECUTED",
            updated_frames >= 2,
            f"count={updated_frames}",
        )

    time.sleep(PRUNE_SETTLE_SECONDS)
    check("subscriber pruned after disconnect", manager.client_count == 0, f"clients={manager.client_count}")

    response = client.post("/api/v1/telemetry", json=payloads[0])
    check(
        "ingest unaffected with zero subscribers",
        response.status_code == 200,
        str(response.status_code),
    )


def test_stream_lifecycle(check: Check) -> None:
    """Snapshot, ping/pong, tick frames, a live decision, and subscriber pruning."""
    manager = ConnectionManager()
    payloads = build_payloads(TICKS, SPIKE_AFTER)
    with TestClient(create_app(CockpitStateEngine(), manager)) as client:
        _exercise_stream(client, manager, payloads, check)


def test_stalled_subscriber_does_not_delay_ingest(check: Check) -> None:
    """A subscriber that stops reading must not sit in front of the ingest response."""
    manager = ConnectionManager()
    payloads = build_payloads(2, 0)
    with TestClient(create_app(CockpitStateEngine(), manager)) as client:
        manager._connections.add(FakeSocket("stalled-subscriber", "stall"))
        started = time.monotonic()
        response = client.post("/api/v1/telemetry", json=payloads[0])
        elapsed = time.monotonic() - started
        check("ingest returns while a subscriber is stalled", response.status_code == 200)
        check(
            "ingest latency unaffected",
            elapsed < INGEST_LATENCY_BUDGET_SECONDS,
            f"{elapsed * 1000:.1f}ms",
        )
        check(
            "rejected payload still 422",
            client.post("/api/v1/telemetry", json={"metrics": {}}).status_code == 422,
        )


def test_dead_peer_is_pruned(check: Check) -> None:
    """A peer that drops mid-transmission is removed and the fan-out continues."""
    manager = ConnectionManager(send_timeout=SEND_TIMEOUT_SECONDS)
    healthy = FakeSocket("healthy")
    dropping = FakeSocket("dropping", "disconnect")
    raising = FakeSocket("raising", "runtime")

    async def exercise() -> int:
        await manager.connect(healthy)
        await manager.connect(dropping)
        await manager.connect(raising)
        return await manager.broadcast("telemetry_tick", {"calls_waiting": 10})

    delivered = asyncio.run(exercise())
    check("fan-out survives a mid-transmission drop", delivered == 1, f"delivered={delivered}")
    check("dead peers pruned", manager.client_count == 1, f"clients={manager.client_count}")
    check("healthy peer received the frame", len(healthy.sent) == 1)


def test_stalled_peer_is_pruned_within_send_timeout(check: Check) -> None:
    """A peer that stops draining is pruned instead of hanging the writer."""
    manager = ConnectionManager(send_timeout=SEND_TIMEOUT_SECONDS)
    healthy = FakeSocket("healthy")
    stalled = FakeSocket("stalled", "stall")

    async def exercise() -> tuple[int, float]:
        await manager.connect(healthy)
        await manager.connect(stalled)
        started = time.monotonic()
        delivered = await manager.broadcast("telemetry_tick", {"calls_waiting": 10})
        return delivered, time.monotonic() - started

    delivered, elapsed = asyncio.run(exercise())
    check("stalled peer pruned within send_timeout", manager.client_count == 1, f"clients={manager.client_count}")
    check(
        "broadcast bounded by send_timeout",
        elapsed < SEND_TIMEOUT_SECONDS * 3,
        f"{elapsed * 1000:.0f}ms",
    )
    check("healthy peer still served", delivered == 1 and len(healthy.sent) == 1)


def test_dispatch_never_touches_a_socket(check: Check) -> None:
    """Dispatch must return immediately even with a stalled peer registered."""
    manager = ConnectionManager(send_timeout=SEND_TIMEOUT_SECONDS)
    stalled = FakeSocket("stalled", "stall")

    async def exercise() -> float:
        await manager.connect(stalled)
        started = time.monotonic()
        for _ in range(50):
            manager.dispatch("telemetry_tick", {"calls_waiting": 1})
        elapsed = time.monotonic() - started
        await manager.shutdown()
        return elapsed

    elapsed = asyncio.run(exercise())
    check("50 dispatches to a stalled peer return immediately", elapsed < 0.05, f"{elapsed * 1000:.2f}ms")
    check("outbox accepted every frame", manager.dropped_frames == 0, f"dropped={manager.dropped_frames}")


def test_backpressure_sheds_oldest(check: Check) -> None:
    """Overflow drops the oldest frame so the freshest state always survives.

    The assertion reads the outbox rather than a socket: with four synchronous
    dispatches the writer never gets a turn, so the queue itself is the observable.
    """
    manager = ConnectionManager(outbox_limit=2, send_timeout=SEND_TIMEOUT_SECONDS)

    async def exercise() -> list[str]:
        for index in range(4):
            manager.dispatch("telemetry_tick", {"marker": "fresh" if index == 3 else f"old-{index}"})
        outbox = manager._outbox
        assert outbox is not None
        retained: list[str] = []
        while not outbox.empty():
            _, _, payload = outbox.get_nowait()
            outbox.task_done()
            retained.append(str(payload["marker"]))
        await manager.shutdown()
        return retained

    retained = asyncio.run(exercise())
    check("overflow counted", manager.dropped_frames == 2, f"dropped={manager.dropped_frames}")
    check(
        "freshest frame retained",
        bool(retained) and retained[-1] == "fresh",
        f"retained={retained}",
    )


def test_lifespan_cancels_the_writer(check: Check) -> None:
    """The application lifespan cancels the drain task instead of orphaning it."""
    manager = ConnectionManager()
    payloads = build_payloads(2, 0)
    with TestClient(create_app(CockpitStateEngine(), manager)) as client:
        client.post("/api/v1/telemetry", json=payloads[0])
        writer = manager._writer
        check("writer started by the ingest route", writer is not None and not writer.done())
    check("writer finished on shutdown", writer is not None and writer.done())
    check("outbox unbound after shutdown", manager._outbox is None and manager._writer is None)
    asyncio.run(manager.shutdown())
    check("shutdown is idempotent", True)
