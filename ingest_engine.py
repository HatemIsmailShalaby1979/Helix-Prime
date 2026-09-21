"""Helix Ops Cockpit ingestion point and real-time intervention engine.

Receives `QueueMetrics` telemetry from the operations twin, tracks backlog
velocity over a rolling window, raises metacognitive intervention
recommendations when a service-level breach is projected, and holds those
recommendations behind a human-in-the-loop approval gate.

Velocity
    `backlog_velocity_per_tick` is the ordinary-least-squares slope of
    calls_waiting against time across the retained window, rescaled onto the
    interval grid::

        beta = sum((t - t_bar) * (Lq - Lq_bar)) / sum((t - t_bar) ** 2)
        velocity_per_tick = beta * median(delta_t)

    OLS is used rather than a single delta because one interval of arrival noise
    swamps the real trend. `instant_backlog_velocity_per_tick` reports the raw
    last-delta reading alongside it.

Projection
    The SLA gradient against backlog is estimated from the same window
    (m = dSLA / dLq), then::

        projected_sla = clamp(current_sla + m * velocity_per_tick * horizon)
        projected_sla_drop = clamp(current_sla - projected_sla, 0, 100)

    If the gradient is undefined or non-negative while the backlog is still
    growing, a conservative fallback sensitivity is applied so a rising backlog
    always projects a drop.

Trigger and de-duplication
    An intervention is raised when sla_percentage < 50.0 or
    backlog_velocity_per_tick > 15.0. At most one PENDING recommendation exists
    at a time (enforced by a single pending pointer, not a scan), and a short
    cooldown follows every human decision so a rejection does not re-fire on the
    next tick.

Intervention
    Damage = service level already lost against the 80/20 goal plus the projected
    drop, and the action ladder escalates on it from the cheapest lever upward:
    REBALANCING_SKILLS, PULL_AUX_TO_CALLS (only while auxiliary headroom exists),
    OPEN_VOLUNTARY_OVERTIME, REROUTE_LOW_PRIORITY_QUEUES. Financial exposure is
    the penalty avoided: $50 per projected breaching call, scaled by how far the
    worst wait overshoots the target (capped at 5x).

State machine
    PENDING -> APPROVED | REJECTED on a manager decision. APPROVED -> EXECUTED
    when the control loop dispatches the action on the next ingested tick. Every
    other edge is refused. All timestamps live on the telemetry clock so the
    audit trail shares one timebase.

Streaming
    `ws /ws/v1/cockpit/stream` subscribes a cockpit client to live state so it
    never has to poll. A new subscriber gets a full `cockpit_snapshot` frame on
    connect, then `telemetry_tick`, `intervention_triggered` and
    `intervention_updated` frames as the REST routes mutate state. Every frame is
    `{type, seq, timestamp, payload}`; `seq` lets a client detect the gap left by
    a shed frame. Frames are queued onto a bounded outbox and drained by a
    background writer, so no HTTP request ever waits on a socket: a subscriber
    that stops reading is pruned rather than allowed to stall the ingest path.
    The writer is cancelled on application shutdown, so a stopped server leaves
    no orphan task behind.
    Clients may send `ping` (bare or `{"type": "ping"}`) to probe liveness.

The engine is in-memory and single-process; `asyncio.Lock` serialises mutation
on the event loop. Bind defaults to 0.0.0.0:8000 per the cockpit deployment
spec, which is a deliberate departure from the repository's loopback default --
override with --host when running on an untrusted network.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from enum import Enum
from itertools import pairwise
from typing import Any, Final, Literal

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

WINDOW_SIZE: Final[int] = 10
SLA_TRIGGER_PERCENTAGE: Final[float] = 50.0
BACKLOG_VELOCITY_TRIGGER: Final[float] = 15.0
PROJECTION_HORIZON_TICKS: Final[int] = 3
PROJECTION_FALLBACK_SENSITIVITY: Final[float] = 0.35
SLA_TARGET_PERCENTAGE: Final[float] = 80.0
AUX_DROP_THRESHOLD: Final[float] = 20.0
OVERTIME_DROP_THRESHOLD: Final[float] = 40.0
SEVERE_DROP_THRESHOLD: Final[float] = 65.0
AUX_FLOOR_AGENTS: Final[int] = 24
SLA_TARGET_SECONDS: Final[float] = 20.0
SLA_PENALTY_PER_CALL_USD: Final[float] = 50.0
MAX_SEVERITY_MULTIPLIER: Final[float] = 5.0
POST_DECISION_COOLDOWN_TICKS: Final[int] = 2
EVENT_LOG_LIMIT: Final[int] = 500
SEND_TIMEOUT_SECONDS: Final[float] = 1.0
OUTBOX_LIMIT: Final[int] = 256


class InterventionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


class ProposedAction(str, Enum):
    PULL_AUX_TO_CALLS = "PULL_AUX_TO_CALLS"
    OPEN_VOLUNTARY_OVERTIME = "OPEN_VOLUNTARY_OVERTIME"
    REROUTE_LOW_PRIORITY_QUEUES = "REROUTE_LOW_PRIORITY_QUEUES"
    REBALANCING_SKILLS = "REBALANCING_SKILLS"


class StreamMessageType(str, Enum):
    SNAPSHOT = "cockpit_snapshot"
    TELEMETRY_TICK = "telemetry_tick"
    INTERVENTION_TRIGGERED = "intervention_triggered"
    INTERVENTION_UPDATED = "intervention_updated"
    PONG = "pong"


OutboxFrame = tuple[WebSocket | None, StreamMessageType, dict[str, Any]]


class QueueMetrics(BaseModel):
    """Telemetry sample as emitted by the operations twin."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: float
    calls_waiting: int = Field(ge=0)
    longest_wait_time: float = Field(ge=0.0)
    sla_percentage: float = Field(ge=0.0, le=100.0)
    active_agents: int = Field(ge=0)
    aux_agents: int = Field(ge=0)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: object) -> object:
        """Accept epoch seconds or the ISO-8601 string the twin writes to stdout."""
        if isinstance(value, str):
            text = value.strip()
            if text.endswith(("Z", "z")):
                text = f"{text[:-1]}+00:00"
            return datetime.fromisoformat(text).timestamp()
        return value


class SimulationState(BaseModel):
    """Control-plane state published alongside each telemetry sample."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_spike_active: bool
    current_interval_volume: float = Field(ge=0.0)


class IngestPayload(BaseModel):
    """One tick of twin output: metrics plus the control-plane state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metrics: QueueMetrics
    state: SimulationState


class InterventionRecommendation(BaseModel):
    """A proposed operational action awaiting or holding a human decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    timestamp: float
    trigger_condition: str
    current_sla: float = Field(ge=0.0, le=100.0)
    projected_sla_drop: float = Field(ge=0.0, le=100.0)
    proposed_action: ProposedAction
    reasoning_trace: str
    estimated_financial_saving_usd: float = Field(ge=0.0)
    status: InterventionStatus


class ApprovalRequest(BaseModel):
    """A manager decision on one recommendation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intervention_id: str = Field(min_length=1)
    decision: Literal["approve", "reject"]
    manager_id: str = Field(min_length=1)


class InterventionEvent(BaseModel):
    """Append-only audit record for one state transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: float
    intervention_id: str
    from_status: InterventionStatus | None
    to_status: InterventionStatus
    actor: str
    note: str


class VelocityReading(BaseModel):
    """Backlog velocity estimators for the current window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backlog_velocity_per_tick: float
    backlog_velocity_per_second: float
    instant_backlog_velocity_per_tick: float
    samples: int
    median_interval_seconds: float


class IngestResponse(BaseModel):
    """Result of accepting one telemetry tick."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    tick_timestamp: float
    window_samples: int
    velocity: VelocityReading
    trigger_condition: str | None
    newly_generated: InterventionRecommendation | None
    executed_interventions: list[str]
    pending_interventions: list[InterventionRecommendation]


class CockpitStateResponse(BaseModel):
    """Full ops summary for the cockpit surface."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: float
    window_samples: int
    latest_metrics: QueueMetrics | None
    latest_state: SimulationState | None
    velocity: VelocityReading
    projected_sla: float | None
    trigger_condition: str | None
    pending_interventions: list[InterventionRecommendation]
    active_interventions: list[InterventionRecommendation]
    recommendations: list[InterventionRecommendation]
    event_log: list[InterventionEvent]


class ApprovalResponse(BaseModel):
    """Result of a manager decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intervention: InterventionRecommendation
    previous_status: InterventionStatus
    execution_trace: InterventionEvent


class UnknownInterventionError(LookupError):
    """Raised when a decision references an unknown recommendation id."""


class InvalidTransitionError(RuntimeError):
    """Raised when a decision targets an already-resolved recommendation."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _ols_slope(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Return the least-squares slope of y against x, or None when undefined."""
    count = len(xs)
    if count < 2:
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    variance = sum((x - mean_x) ** 2 for x in xs)
    if variance <= 0.0:
        return None
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return covariance / variance


class CockpitStateEngine:
    """Rolling-window anomaly detector and intervention state machine."""

    def __init__(self, *, window_size: int = WINDOW_SIZE) -> None:
        if window_size < 2:
            raise ValueError("window_size must be >= 2")
        self._window: deque[QueueMetrics] = deque(maxlen=window_size)
        self._latest_state: SimulationState | None = None
        self._recommendations: dict[str, InterventionRecommendation] = {}
        self._order: list[str] = []
        self._events: deque[InterventionEvent] = deque(maxlen=EVENT_LOG_LIMIT)
        self._pending_id: str | None = None
        self._cooldown_ticks = 0
        self._clock_value = 0.0
        self._lock = asyncio.Lock()

    @property
    def pending_count(self) -> int:
        return 1 if self._pending_id is not None else 0

    def recommendation(self, intervention_id: str) -> InterventionRecommendation | None:
        """Read one recommendation by id; a pure lookup, so it needs no lock."""
        return self._recommendations.get(intervention_id)

    async def ingest(self, payload: IngestPayload) -> IngestResponse:
        """Accept one tick, advance the state machine, and evaluate the trigger."""
        async with self._lock:
            metrics = payload.metrics
            self._clock_value = metrics.timestamp
            self._window.append(metrics)
            self._latest_state = payload.state

            executed = self._dispatch_approved()
            velocity = self._velocity()
            projected_sla, drop = self._project(velocity, metrics)
            trigger = self._trigger_condition(metrics, velocity)
            generated: InterventionRecommendation | None = None
            if trigger is not None and self._pending_id is None and self._cooldown_ticks == 0:
                generated = self._generate(trigger, metrics, velocity, projected_sla, drop)
            if self._cooldown_ticks > 0:
                self._cooldown_ticks -= 1
            return IngestResponse(
                accepted=True,
                tick_timestamp=metrics.timestamp,
                window_samples=len(self._window),
                velocity=velocity,
                trigger_condition=trigger,
                newly_generated=generated,
                executed_interventions=executed,
                pending_interventions=self._pending(),
            )

    async def decide(self, request: ApprovalRequest) -> ApprovalResponse:
        """Transition a PENDING recommendation to APPROVED or REJECTED."""
        async with self._lock:
            current = self._recommendations.get(request.intervention_id)
            if current is None:
                raise UnknownInterventionError(request.intervention_id)
            if current.status is not InterventionStatus.PENDING:
                raise InvalidTransitionError(
                    f"intervention {current.id} is {current.status.value}, not PENDING"
                )
            target = (
                InterventionStatus.APPROVED
                if request.decision == "approve"
                else InterventionStatus.REJECTED
            )
            updated = current.model_copy(update={"status": target})
            self._recommendations[updated.id] = updated
            self._pending_id = None
            self._cooldown_ticks = POST_DECISION_COOLDOWN_TICKS
            outcome = (
                "released for execution"
                if target is InterventionStatus.APPROVED
                else "declined"
            )
            event = InterventionEvent(
                timestamp=self._clock_value,
                intervention_id=updated.id,
                from_status=current.status,
                to_status=target,
                actor=request.manager_id,
                note=(
                    f"manager {request.manager_id} {request.decision}d "
                    f"{updated.proposed_action.value}; "
                    f"${updated.estimated_financial_saving_usd:,.2f} exposure "
                    f"{outcome}"
                ),
            )
            self._events.append(event)
            return ApprovalResponse(
                intervention=updated, previous_status=current.status, execution_trace=event
            )

    async def snapshot(self) -> CockpitStateResponse:
        """Return the full cockpit view: window, velocity, recommendations, audit log."""
        async with self._lock:
            metrics = self._window[-1] if self._window else None
            velocity = self._velocity()
            projected_sla: float | None = None
            trigger: str | None = None
            if metrics is not None:
                projected_sla, _ = self._project(velocity, metrics)
                trigger = self._trigger_condition(metrics, velocity)
            recommendations = [self._recommendations[key] for key in self._order]
            active = [
                item
                for item in recommendations
                if item.status in (InterventionStatus.PENDING, InterventionStatus.APPROVED)
            ]
            return CockpitStateResponse(
                generated_at=self._clock_value,
                window_samples=len(self._window),
                latest_metrics=metrics,
                latest_state=self._latest_state,
                velocity=velocity,
                projected_sla=projected_sla,
                trigger_condition=trigger,
                pending_interventions=self._pending(),
                active_interventions=active,
                recommendations=recommendations,
                event_log=list(self._events),
            )

    def _dispatch_approved(self) -> list[str]:
        """Advance APPROVED recommendations to EXECUTED on the tick that follows."""
        executed: list[str] = []
        for key in self._order:
            current = self._recommendations[key]
            if current.status is not InterventionStatus.APPROVED:
                continue
            updated = current.model_copy(update={"status": InterventionStatus.EXECUTED})
            self._recommendations[updated.id] = updated
            executed.append(updated.id)
            self._events.append(
                InterventionEvent(
                    timestamp=self._clock_value,
                    intervention_id=updated.id,
                    from_status=InterventionStatus.APPROVED,
                    to_status=InterventionStatus.EXECUTED,
                    actor="control_loop",
                    note=f"dispatched {updated.proposed_action.value} to the operations twin",
                )
            )
        return executed

    def _velocity(self) -> VelocityReading:
        """Compute windowed and instantaneous backlog velocity for the retained ticks."""
        samples = list(self._window)
        if len(samples) < 2:
            return VelocityReading(
                backlog_velocity_per_tick=0.0,
                backlog_velocity_per_second=0.0,
                instant_backlog_velocity_per_tick=0.0,
                samples=len(samples),
                median_interval_seconds=0.0,
            )
        stamps = [sample.timestamp for sample in samples]
        backlog = [float(sample.calls_waiting) for sample in samples]
        gaps = [
            later - earlier for earlier, later in pairwise(stamps) if later - earlier > 0.0
        ]
        median_gap = statistics.median(gaps) if gaps else 0.0
        slope = _ols_slope(stamps, backlog)
        if slope is None:
            slope = (backlog[-1] - backlog[0]) / (len(backlog) - 1)
            per_second = slope / median_gap if median_gap > 0.0 else 0.0
            return VelocityReading(
                backlog_velocity_per_tick=slope,
                backlog_velocity_per_second=per_second,
                instant_backlog_velocity_per_tick=slope,
                samples=len(samples),
                median_interval_seconds=median_gap,
            )
        last_gap = stamps[-1] - stamps[-2]
        instant = (
            (backlog[-1] - backlog[-2]) / last_gap * median_gap
            if last_gap > 0.0 and median_gap > 0.0
            else 0.0
        )
        return VelocityReading(
            backlog_velocity_per_tick=slope * median_gap,
            backlog_velocity_per_second=slope,
            instant_backlog_velocity_per_tick=instant,
            samples=len(samples),
            median_interval_seconds=median_gap,
        )

    def _project(self, velocity: VelocityReading, metrics: QueueMetrics) -> tuple[float, float]:
        """Return (projected_sla, projected_sla_drop) over the intervention horizon."""
        samples = list(self._window)
        gradient = _ols_slope(
            [float(sample.calls_waiting) for sample in samples],
            [sample.sla_percentage for sample in samples],
        )
        if gradient is None or gradient >= 0.0:
            gradient = (
                -PROJECTION_FALLBACK_SENSITIVITY
                if velocity.backlog_velocity_per_tick > 0.0
                else 0.0
            )
        delta_backlog = velocity.backlog_velocity_per_tick * PROJECTION_HORIZON_TICKS
        projected = _clamp(metrics.sla_percentage + gradient * delta_backlog, 0.0, 100.0)
        return projected, _clamp(metrics.sla_percentage - projected, 0.0, 100.0)

    @staticmethod
    def _trigger_condition(metrics: QueueMetrics, velocity: VelocityReading) -> str | None:
        """Return the human-readable trigger that fired, or None."""
        reasons: list[str] = []
        if metrics.sla_percentage < SLA_TRIGGER_PERCENTAGE:
            reasons.append(
                f"sla_breach:{metrics.sla_percentage:.2f}%<{SLA_TRIGGER_PERCENTAGE:.1f}%"
            )
        if velocity.backlog_velocity_per_tick > BACKLOG_VELOCITY_TRIGGER:
            reasons.append(
                f"backlog_velocity:{velocity.backlog_velocity_per_tick:.2f}"
                f"calls/tick>{BACKLOG_VELOCITY_TRIGGER:.1f}"
            )
        return " AND ".join(reasons) if reasons else None

    def _generate(
        self,
        trigger: str,
        metrics: QueueMetrics,
        velocity: VelocityReading,
        projected_sla: float,
        drop: float,
    ) -> InterventionRecommendation:
        """Build, record and raise one PENDING intervention recommendation."""
        realized_deficit = max(0.0, SLA_TARGET_PERCENTAGE - metrics.sla_percentage)
        damage = _clamp(realized_deficit + drop, 0.0, 100.0)
        action = self._select_action(damage, metrics)
        saving = self._financial_exposure(metrics, projected_sla)
        wait_severity = _clamp(
            metrics.longest_wait_time / SLA_TARGET_SECONDS, 1.0, MAX_SEVERITY_MULTIPLIER
        )
        breaching = metrics.calls_waiting * (1.0 - projected_sla / 100.0)
        recommendation = InterventionRecommendation(
            id=str(uuid.uuid4()),
            timestamp=metrics.timestamp,
            trigger_condition=trigger,
            current_sla=round(metrics.sla_percentage, 2),
            projected_sla_drop=round(drop, 2),
            proposed_action=action,
            reasoning_trace=(
                f"trigger={trigger}. Backlog {metrics.calls_waiting} calls moving "
                f"{velocity.backlog_velocity_per_tick:+.2f} calls/tick "
                f"(instant {velocity.instant_backlog_velocity_per_tick:+.2f}) over "
                f"{velocity.samples} ticks; SLA {metrics.sla_percentage:.2f}% projects to "
                f"{projected_sla:.2f}% within {PROJECTION_HORIZON_TICKS} intervals "
                f"({drop:.2f}pt drop). Service damage {damage:.1f}pt = {realized_deficit:.1f}pt "
                f"already lost against the {SLA_TARGET_PERCENTAGE:.0f}% goal + {drop:.1f}pt "
                f"projected. {breaching:.0f} of {metrics.calls_waiting} waiting calls are "
                f"projected to breach the {SLA_TARGET_SECONDS:.0f}s target; worst wait "
                f"{metrics.longest_wait_time:.1f}s is {wait_severity:.1f}x target, so "
                f"${SLA_PENALTY_PER_CALL_USD:,.0f}/call penalty exposure is "
                f"${saving:,.2f}. Recommending {action.value}: {self._action_rationale(action)}"
            ),
            estimated_financial_saving_usd=saving,
            status=InterventionStatus.PENDING,
        )
        self._recommendations[recommendation.id] = recommendation
        self._order.append(recommendation.id)
        self._pending_id = recommendation.id
        self._events.append(
            InterventionEvent(
                timestamp=metrics.timestamp,
                intervention_id=recommendation.id,
                from_status=None,
                to_status=InterventionStatus.PENDING,
                actor="metacognition_engine",
                note=f"raised {action.value} on {trigger}",
            )
        )
        return recommendation

    @staticmethod
    def _select_action(damage: float, metrics: QueueMetrics) -> ProposedAction:
        """Escalate through the action ladder by total service damage, cheapest lever first."""
        if damage >= SEVERE_DROP_THRESHOLD:
            return ProposedAction.REROUTE_LOW_PRIORITY_QUEUES
        if damage >= OVERTIME_DROP_THRESHOLD:
            return ProposedAction.OPEN_VOLUNTARY_OVERTIME
        if damage >= AUX_DROP_THRESHOLD and metrics.aux_agents > AUX_FLOOR_AGENTS:
            return ProposedAction.PULL_AUX_TO_CALLS
        return ProposedAction.REBALANCING_SKILLS

    @staticmethod
    def _action_rationale(action: ProposedAction) -> str:
        return {
            ProposedAction.PULL_AUX_TO_CALLS: (
                "auxiliary headcount can be absorbed with no overtime cost"
            ),
            ProposedAction.OPEN_VOLUNTARY_OVERTIME: (
                "in-seat capacity is insufficient, so paid capacity is the cheapest lever"
            ),
            ProposedAction.REROUTE_LOW_PRIORITY_QUEUES: (
                "damage is severe enough to protect the priority queue by shedding load"
            ),
            ProposedAction.REBALANCING_SKILLS: (
                "the shortfall is marginal, so skill rebalancing is proportionate"
            ),
        }[action]

    @staticmethod
    def _financial_exposure(metrics: QueueMetrics, projected_sla: float) -> float:
        """Penalty exposure avoided: $50 per breaching call, scaled by wait severity."""
        breaching = metrics.calls_waiting * (1.0 - projected_sla / 100.0)
        severity = _clamp(
            metrics.longest_wait_time / SLA_TARGET_SECONDS, 1.0, MAX_SEVERITY_MULTIPLIER
        )
        return round(breaching * SLA_PENALTY_PER_CALL_USD * severity, 2)

    def _pending(self) -> list[InterventionRecommendation]:
        if self._pending_id is None:
            return []
        return [self._recommendations[self._pending_id]]


def _is_ping(raw: str) -> bool:
    """Accept a bare `ping` or a JSON frame typed `ping`; ignore every other frame."""
    text = raw.strip()
    if not text:
        return False
    if text.lower() == "ping":
        return True
    try:
        frame = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(frame, dict) and frame.get("type") == "ping"


class ConnectionManager:
    """Fan-out hub for cockpit stream subscribers.

    Mutation needs no lock: the event loop is single-threaded and `broadcast`
    iterates a snapshot of the connection set, so a subscriber connecting or
    dropping mid-fan-out cannot corrupt the iteration.

    No request path ever awaits a socket. `dispatch` only enqueues onto a bounded
    outbox drained by a background writer, so a stalled subscriber cannot delay
    the ingest response or the OLS velocity computation behind it. A subscriber
    that cannot keep up has its oldest frames shed, and one that does not drain
    within `send_timeout` is pruned from the pool.

    The writer is also the only coroutine that ever writes to a socket, including
    per-subscriber frames such as the connect snapshot, so a fan-out can never
    interleave with a handshake reply on the same peer.

    The hub is loop-agnostic: an `asyncio.Queue` binds to the loop that first
    awaited it, so the outbox and its drain task are rebuilt whenever a new loop
    drives the manager. The module-level instance therefore survives test clients,
    worker threads, or a restarted server without inheriting a dead queue.
    """

    def __init__(
        self,
        *,
        outbox_limit: int = OUTBOX_LIMIT,
        send_timeout: float = SEND_TIMEOUT_SECONDS,
    ) -> None:
        if outbox_limit < 1:
            raise ValueError("outbox_limit must be >= 1")
        self._connections: set[WebSocket] = set()
        self._outbox: asyncio.Queue[OutboxFrame] | None = None
        self._writer: asyncio.Task[None] | None = None
        self._writer_loop: asyncio.AbstractEventLoop | None = None
        self._sequence = 0
        self._dropped = 0
        self._outbox_limit = outbox_limit
        self._send_timeout = send_timeout

    @property
    def client_count(self) -> int:
        """Live subscribers currently registered for fan-out."""
        return len(self._connections)

    @property
    def dropped_frames(self) -> int:
        """Frames shed under backpressure since start."""
        return self._dropped

    async def connect(self, websocket: WebSocket) -> None:
        """Complete the handshake and register the socket for fan-out."""
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Drop a socket; idempotent, so pruning a dead peer twice is harmless."""
        self._connections.discard(websocket)

    async def shutdown(self) -> None:
        """Cancel the drain task and unbind the outbox, leaving no orphan task.

        Called from the application lifespan so a stopped server tears its writer
        down deterministically instead of leaving a pending task for the garbage
        collector to destroy mid-await.
        """
        writer, self._writer = self._writer, None
        self._writer_loop = None
        self._outbox = None
        if writer is None or writer.done():
            return
        writer.cancel()
        with suppress(asyncio.CancelledError, RuntimeError):
            await writer

    async def broadcast(self, message_type: str, payload: dict[str, Any]) -> int:
        """Send one envelope to every live subscriber and prune the dead ones.

        A peer that disconnects mid-transmission, a socket already closed
        underneath us, or a peer that stops draining is removed from the pool and
        the fan-out continues. Nothing escapes to the caller, so one bad
        subscriber can never abort a tick.
        """
        envelope = self._next_envelope(message_type, payload)
        delivered = 0
        for websocket in list(self._connections):
            if await self._transmit(websocket, envelope):
                delivered += 1
        return delivered

    def dispatch(self, message_type: StreamMessageType, payload: dict[str, Any]) -> None:
        """Queue a fan-out without touching a socket; safe to call from any route."""
        self._enqueue(None, message_type, payload)

    def dispatch_to(
        self, websocket: WebSocket, message_type: StreamMessageType, payload: dict[str, Any]
    ) -> None:
        """Queue one frame for one subscriber, serialised with fan-out on the writer."""
        self._enqueue(websocket, message_type, payload)

    def _enqueue(
        self,
        target: WebSocket | None,
        message_type: StreamMessageType,
        payload: dict[str, Any],
    ) -> None:
        """Enqueue without awaiting a socket, shedding the oldest frame when full."""
        outbox = self._ensure_writer()
        if outbox is None:
            self._dropped += 1
            return
        frame: OutboxFrame = (target, message_type, payload)
        try:
            outbox.put_nowait(frame)
            return
        except asyncio.QueueFull:
            self._dropped += 1
        try:
            outbox.get_nowait()
            outbox.task_done()
            outbox.put_nowait(frame)
        except (asyncio.QueueEmpty, asyncio.QueueFull):
            self._dropped += 1

    def _ensure_writer(self) -> asyncio.Queue[OutboxFrame] | None:
        """Return the outbox bound to the running loop, rebinding it if needed.

        Returns `None` when called outside a running loop, in which case the
        frame is counted as dropped rather than raised at the caller.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        if (
            self._outbox is None
            or self._writer_loop is not loop
            or self._writer is None
            or self._writer.done()
        ):
            self._outbox = asyncio.Queue(maxsize=self._outbox_limit)
            self._writer_loop = loop
            self._writer = loop.create_task(self._run_writer(self._outbox))
        return self._outbox

    def _next_envelope(self, message_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._sequence += 1
        return {
            "type": (
                message_type.value
                if isinstance(message_type, StreamMessageType)
                else str(message_type)
            ),
            "seq": self._sequence,
            "timestamp": time.time(),
            "payload": payload,
        }

    async def _transmit(self, websocket: WebSocket, envelope: dict[str, Any]) -> bool:
        """Write one envelope to one socket, pruning it on any failure."""
        try:
            await asyncio.wait_for(
                websocket.send_json(envelope), timeout=self._send_timeout
            )
        except Exception:
            self.disconnect(websocket)
            return False
        return True

    async def _run_writer(self, outbox: asyncio.Queue[OutboxFrame]) -> None:
        """Drain one outbox, one frame at a time, for as long as it is alive.

        A frame that fails to serialise is counted and discarded; the drain loop
        itself never dies with an unretrieved exception.
        """
        while True:
            target, message_type, payload = await outbox.get()
            try:
                if target is None:
                    await self.broadcast(message_type, payload)
                else:
                    await self._transmit(target, self._next_envelope(message_type, payload))
            except asyncio.CancelledError:
                raise
            except Exception:
                self._dropped += 1
            finally:
                outbox.task_done()


def create_app(
    engine: CockpitStateEngine | None = None, manager: ConnectionManager | None = None
) -> FastAPI:
    """Build the cockpit REST application around one engine instance."""
    state_engine = engine or CockpitStateEngine()
    stream_manager = manager or ConnectionManager()

    @asynccontextmanager
    async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await stream_manager.shutdown()

    application = FastAPI(
        title="Helix Ops Cockpit Ingest Engine",
        version="1.0.0",
        description=__doc__.splitlines()[0],
        lifespan=_lifespan,
    )

    @application.exception_handler(UnknownInterventionError)
    async def _unknown(_: Request, exc: UnknownInterventionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": f"unknown intervention id {exc.args[0]!r}"},
        )

    @application.exception_handler(InvalidTransitionError)
    async def _invalid(_: Request, exc: InvalidTransitionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)}
        )

    @application.get("/healthz", response_model=dict[str, str])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/v1/telemetry", response_model=IngestResponse)
    async def ingest(payload: IngestPayload) -> IngestResponse:
        result = await state_engine.ingest(payload)
        stream_manager.dispatch(
            StreamMessageType.TELEMETRY_TICK,
            {
                "metrics": payload.metrics.model_dump(mode="json"),
                "state": payload.state.model_dump(mode="json"),
                "velocity": result.velocity.model_dump(mode="json"),
                "trigger_condition": result.trigger_condition,
                "window_samples": result.window_samples,
                "pending_interventions": [
                    item.model_dump(mode="json") for item in result.pending_interventions
                ],
            },
        )
        if result.newly_generated is not None:
            stream_manager.dispatch(
                StreamMessageType.INTERVENTION_TRIGGERED,
                result.newly_generated.model_dump(mode="json"),
            )
        for executed_id in result.executed_interventions:
            executed = state_engine.recommendation(executed_id)
            stream_manager.dispatch(
                StreamMessageType.INTERVENTION_UPDATED,
                {
                    "intervention": executed.model_dump(mode="json") if executed else None,
                    "intervention_id": executed_id,
                    "previous_status": InterventionStatus.APPROVED.value,
                    "execution_trace": None,
                },
            )
        return result

    @application.get("/api/v1/cockpit/state", response_model=CockpitStateResponse)
    async def cockpit_state() -> CockpitStateResponse:
        return await state_engine.snapshot()

    @application.post("/api/v1/cockpit/approve", response_model=ApprovalResponse)
    async def approve(request: ApprovalRequest) -> ApprovalResponse:
        result = await state_engine.decide(request)
        stream_manager.dispatch(
            StreamMessageType.INTERVENTION_UPDATED,
            {
                "intervention": result.intervention.model_dump(mode="json"),
                "intervention_id": result.intervention.id,
                "previous_status": result.previous_status.value,
                "execution_trace": result.execution_trace.model_dump(mode="json"),
            },
        )
        return result

    @application.websocket("/ws/v1/cockpit/stream")
    async def cockpit_stream(websocket: WebSocket) -> None:
        try:
            snapshot = await state_engine.snapshot()
            await stream_manager.connect(websocket)
            stream_manager.dispatch_to(
                websocket, StreamMessageType.SNAPSHOT, snapshot.model_dump(mode="json")
            )
            while True:
                raw = await websocket.receive_text()
                if _is_ping(raw):
                    stream_manager.dispatch_to(
                        websocket,
                        StreamMessageType.PONG,
                        {"clients": stream_manager.client_count},
                    )
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            stream_manager.disconnect(websocket)

    return application


manager = ConnectionManager()
app = create_app(manager=manager)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0", help="bind address")
    parser.add_argument("--port", type=int, default=8000, help="bind port")
    parser.add_argument("--log-level", default="info", help="uvicorn log level")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
