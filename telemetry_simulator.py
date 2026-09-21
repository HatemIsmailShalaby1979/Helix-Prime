"""Deterministic Operations Twin for a simulated 500-agent contact center.

Emits a reproducible Poisson-driven telemetry stream (:class:`QueueMetrics`) on a
fixed 2-second wall-clock cadence, backed by Erlang C queueing mathematics, and
exposes a programmatic :meth:`TelemetryGenerator.trigger_spike` control that
forces an unexpected volume surge for downstream SLA-safeguard testing.

Time model
    one tick = 2.0 s wall clock = 300 s of simulated operations (the WFM
    interval), so a 10-tick spike represents a 50-minute event.

Load model
    offered_load (Erlangs) = forecast_arrivals * AHT / interval_seconds
    capacity     (Erlangs) = active_agents - aux_agents

    The Erlang math consumes the forecast (a smooth seasonal + noise curve, the
    same object a real WFM engine sizes against), while the count the payload
    reports is a Poisson draw around it. Feeding raw interval noise into the
    Erlang math would make the normal state flicker between regimes: at an 82%
    service level the staffed margin is only ~2% of load, and a single sigma of
    interval noise is larger than that margin.

Queue model
    The backlog is a single fluid queue that never falls below the Erlang C
    equilibrium (the stochastic floor the randomness of arrivals guarantees) and
    accumulates whenever offered load exceeds capacity::

        floor   = C * rho / (1 - rho)                    # C = Erlang C, rho = load / capacity
        backlog = max((backlog + net_volume) * survival, floor)
        net_volume = (offered_load - capacity) * interval / AHT
        survival   = exp(-interval / patience)            # exponential abandonment

    Wait tail scale = max(AHT / (capacity - load), AHT * backlog / capacity) while
    under capacity, and AHT * backlog / capacity while over it -- so a large
    backlog keeps holding the service level down until it actually drains. SLA
    and longest wait are then read off that same exponential tail
    (P(W > t) = C * exp(-t / scale)), which makes degradation continuous across
    the capacity boundary instead of a step change, and lets the backlog
    mean-revert after a surge instead of latching.

Determinism
    A seeded ``random.Random`` owns every draw and the simulated clock advances
    from a fixed epoch, so identical (seed, tick_count) inputs reproduce a
    byte-identical stream.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Final

from pydantic import BaseModel, ConfigDict, Field

TICK_SECONDS: Final[float] = 2.0
SIM_INTERVAL_SECONDS: Final[float] = 300.0
AVG_HANDLE_TIME_SECONDS: Final[float] = 300.0
SLA_TARGET_SECONDS: Final[float] = 20.0
CENTER_HEADCOUNT: Final[int] = 500
BASE_AUX_AGENTS: Final[int] = 72
AUX_FLOOR_AGENTS: Final[int] = 24
BASE_ARRIVALS_PER_INTERVAL: Final[float] = 413.5
STAFFING_DRIFT_SIGMA: Final[float] = 0.8
AUX_DRIFT_SIGMA: Final[float] = 0.8
FORECAST_NOISE_SIGMA: Final[float] = 0.004
SEASONAL_AMPLITUDE: Final[float] = 0.006
SEASONAL_PERIOD_TICKS: Final[int] = 24
QUEUE_JITTER_SIGMA: Final[float] = 0.10
MAX_FLOOR_UTILISATION: Final[float] = 0.99
ABANDONMENT_PATIENCE_SECONDS: Final[float] = 900.0
ABANDONMENT_SURVIVAL_RATE: Final[float] = math.exp(
    -SIM_INTERVAL_SECONDS / ABANDONMENT_PATIENCE_SECONDS
)
SPIKE_DURATION_TICKS: Final[int] = 10
SPIKE_PEAK_MULTIPLIER: Final[float] = 1.8
SPIKE_INITIAL_SHOCK: Final[float] = 0.10
SPIKE_CURVE_GAMMA: Final[float] = 2.2
SPIKE_RECOVERY_TICKS: Final[int] = 4
SPIKE_RECOVERY_DECAY: Final[float] = 0.9
MAX_QUEUE_LENGTH: Final[int] = 2500
MAX_LONGEST_WAIT_SECONDS: Final[float] = 1800.0
DEFAULT_SEED: Final[int] = 20260105
SIMULATION_EPOCH: Final[datetime] = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)


class QueueMetrics(BaseModel):
    """One telemetry sample for the simulated inbound queue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    calls_waiting: int = Field(ge=0)
    longest_wait_time: float = Field(ge=0.0)
    sla_percentage: float = Field(ge=0.0, le=100.0)
    active_agents: int = Field(ge=0)
    aux_agents: int = Field(ge=0)


class SimulationState(BaseModel):
    """Control-plane view of the twin, readable between ticks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_spike_active: bool
    current_interval_volume: int = Field(ge=0)


def _erlang_c(offered_load: float, servers: int) -> float:
    """Return the Erlang C probability of waiting, computed by the stable 1/B recursion."""
    if servers <= 0:
        return 1.0
    if offered_load <= 0.0:
        return 0.0
    if offered_load >= servers:
        return 1.0
    inverse_blocking = 1.0
    for server in range(1, servers + 1):
        inverse_blocking = 1.0 + inverse_blocking * server / offered_load
    blocking = 1.0 / inverse_blocking
    utilisation = offered_load / servers
    return blocking / (1.0 - utilisation * (1.0 - blocking))


def _sample_poisson(rng: random.Random, mean: float) -> int:
    """Draw a Poisson variate: exact Knuth for small means, normal approximation above."""
    if mean <= 0.0:
        return 0
    if mean < 30.0:
        threshold = math.exp(-mean)
        product = 1.0
        count = 0
        while True:
            product *= rng.random()
            if product <= threshold:
                return count
            count += 1
    return max(0, round(rng.gauss(mean, math.sqrt(mean))))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class TelemetryGenerator:
    """Deterministic operations twin for a 500-agent contact center."""

    def __init__(
        self,
        *,
        seed: int = DEFAULT_SEED,
        tick_seconds: float = TICK_SECONDS,
        start_time: datetime = SIMULATION_EPOCH,
    ) -> None:
        if tick_seconds <= 0.0:
            raise ValueError("tick_seconds must be positive")
        if start_time.tzinfo is None:
            raise ValueError("start_time must be timezone-aware")
        self.tick_seconds = tick_seconds
        self._rng = random.Random(seed)
        self._clock = start_time
        self._tick_index = 0
        self._backlog = 0.0
        self._equilibrium_floor = 0.0
        self._spike_triggered = False
        self._spike_ticks_elapsed = 0
        self._state = SimulationState(is_spike_active=False, current_interval_volume=0)

    @property
    def state(self) -> SimulationState:
        """Latest control-plane snapshot (spike flag + offered volume)."""
        return self._state

    @property
    def tick_index(self) -> int:
        """Number of ticks emitted so far."""
        return self._tick_index

    @property
    def simulated_clock(self) -> datetime:
        """Simulated wall clock at the most recent tick."""
        return self._clock

    async def trigger_spike(self) -> None:
        """Arm the volume surge; degradation unfolds over the next 10 ticks."""
        if self._spike_triggered:
            return
        self._spike_triggered = True
        self._spike_ticks_elapsed = 0
        self._state = self._state.model_copy(update={"is_spike_active": True})
        await asyncio.sleep(0)

    async def generate_tick(self) -> AsyncIterator[QueueMetrics]:
        """Yield one :class:`QueueMetrics` sample every ``tick_seconds`` of wall clock."""
        while True:
            started = time.monotonic()
            yield self._advance()
            await asyncio.sleep(max(0.0, self.tick_seconds - (time.monotonic() - started)))

    def _advance(self) -> QueueMetrics:
        self._tick_index += 1
        self._clock += timedelta(seconds=SIM_INTERVAL_SECONDS)
        multiplier, spike_active = self._next_volume_multiplier()
        intensity = _clamp((multiplier - 1.0) / (SPIKE_PEAK_MULTIPLIER - 1.0), 0.0, 1.0)
        active_agents, aux_agents = self._next_staffing(intensity)
        staffed_agents = max(1, active_agents - aux_agents)
        forecast_volume = self._forecast_volume(multiplier)
        volume = _sample_poisson(self._rng, forecast_volume)
        offered_load = forecast_volume * AVG_HANDLE_TIME_SECONDS / SIM_INTERVAL_SECONDS
        calls_waiting, longest_wait, sla = self._derive_queue(offered_load, staffed_agents)
        self._state = SimulationState(
            is_spike_active=spike_active, current_interval_volume=volume
        )
        return QueueMetrics(
            timestamp=self._clock,
            calls_waiting=calls_waiting,
            longest_wait_time=round(longest_wait, 1),
            sla_percentage=round(sla, 2),
            active_agents=active_agents,
            aux_agents=aux_agents,
        )

    def _forecast_volume(self, multiplier: float) -> float:
        """Smooth forecast arrivals for this interval: seasonality + forecast error."""
        seasonal = 1.0 + SEASONAL_AMPLITUDE * math.sin(
            2.0 * math.pi * self._tick_index / SEASONAL_PERIOD_TICKS
        )
        error = math.exp(self._rng.gauss(0.0, FORECAST_NOISE_SIGMA))
        return BASE_ARRIVALS_PER_INTERVAL * multiplier * seasonal * error

    def _next_volume_multiplier(self) -> tuple[float, bool]:
        """Return (volume multiplier, spike flag): shock + exponential ramp, then decay."""
        if not self._spike_triggered:
            return 1.0, False
        span = SPIKE_PEAK_MULTIPLIER - 1.0
        if self._spike_ticks_elapsed < SPIKE_DURATION_TICKS:
            self._spike_ticks_elapsed += 1
            progress = self._spike_ticks_elapsed / SPIKE_DURATION_TICKS
            curve = (math.exp(SPIKE_CURVE_GAMMA * progress) - 1.0) / (
                math.exp(SPIKE_CURVE_GAMMA) - 1.0
            )
            ramp = SPIKE_INITIAL_SHOCK + (1.0 - SPIKE_INITIAL_SHOCK) * curve
            return 1.0 + span * ramp, True
        recovery = self._spike_ticks_elapsed - SPIKE_DURATION_TICKS
        if recovery < SPIKE_RECOVERY_TICKS:
            self._spike_ticks_elapsed += 1
            return 1.0 + span * math.exp(-SPIKE_RECOVERY_DECAY * (recovery + 1)), True
        return 1.0, False

    def _next_staffing(self, intensity: float) -> tuple[int, int]:
        """Return (active_agents, aux_agents); supervisors drain AUX as the surge builds."""
        active_agents = _clamp(
            round(CENTER_HEADCOUNT + self._rng.gauss(0.0, STAFFING_DRIFT_SIGMA)),
            1,
            CENTER_HEADCOUNT,
        )
        target_aux = BASE_AUX_AGENTS - (BASE_AUX_AGENTS - AUX_FLOOR_AGENTS) * intensity
        aux_agents = round(target_aux + self._rng.gauss(0.0, AUX_DRIFT_SIGMA))
        return active_agents, int(_clamp(aux_agents, 0, active_agents - 1))

    def _derive_queue(
        self, offered_load: float, staffed_agents: int
    ) -> tuple[int, float, float]:
        """Return (calls_waiting, longest_wait_seconds, sla_percentage) for one interval."""
        capacity = float(staffed_agents)
        probability_of_waiting = _erlang_c(offered_load, staffed_agents)
        if offered_load < capacity:
            utilisation = min(offered_load / capacity, MAX_FLOOR_UTILISATION)
            self._equilibrium_floor = (
                probability_of_waiting
                * utilisation
                / (1.0 - utilisation)
                * math.exp(self._rng.gauss(0.0, QUEUE_JITTER_SIGMA))
            )
        net_volume = (
            (offered_load - capacity) * SIM_INTERVAL_SECONDS / AVG_HANDLE_TIME_SECONDS
        )
        backlog = (self._backlog + net_volume) * ABANDONMENT_SURVIVAL_RATE
        backlog = min(max(backlog, self._equilibrium_floor), MAX_QUEUE_LENGTH)
        self._backlog = backlog
        backlog_scale = AVG_HANDLE_TIME_SECONDS * max(backlog, 1.0) / capacity
        if offered_load < capacity:
            wait_scale = max(
                AVG_HANDLE_TIME_SECONDS / (capacity - offered_load), backlog_scale
            )
        else:
            wait_scale = backlog_scale
        sla = (1.0 - probability_of_waiting * math.exp(-SLA_TARGET_SECONDS / wait_scale)) * 100.0
        longest_wait = wait_scale * math.log(max(probability_of_waiting * backlog, 1.0))
        return (
            round(backlog),
            min(longest_wait, MAX_LONGEST_WAIT_SECONDS),
            _clamp(sla, 0.0, 100.0),
        )


async def _run(tick_count: int, spike_after: int, seed: int, tick_seconds: float) -> None:
    generator = TelemetryGenerator(seed=seed, tick_seconds=tick_seconds)
    async for metrics in generator.generate_tick():
        if generator.tick_index == spike_after:
            await generator.trigger_spike()
            print(
                f"[twin] volume spike armed at {metrics.timestamp.isoformat()}",
                file=sys.stderr,
            )
        print(metrics.model_dump_json())
        if generator.tick_index >= tick_count:
            break


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ticks", type=int, default=30, help="ticks to emit before exiting")
    parser.add_argument("--spike-after", type=int, default=8, help="tick index that arms the spike")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed")
    parser.add_argument(
        "--tick-seconds", type=float, default=TICK_SECONDS, help="wall-clock cadence"
    )
    args = parser.parse_args()
    if args.ticks < 1:
        parser.error("--ticks must be >= 1")
    if not 0 <= args.spike_after <= args.ticks:
        parser.error("--spike-after must fall within [0, --ticks]")
    asyncio.run(_run(args.ticks, args.spike_after, args.seed, args.tick_seconds))


if __name__ == "__main__":
    main()
