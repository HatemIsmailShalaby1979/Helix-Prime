"""Erlang C calculations for workforce management.

Textbook Erlang C for an M/M/N queue, computed on the numerically stable
Erlang B recursion. The probability of waiting, the average speed of answer
and the service level all follow from one quantity, the probability that an
arrival finds every agent busy.

Conventions and units
---------------------
- ``arrival_rate`` is calls per hour.
- ``average_handling_time`` is minutes per call, talk plus wrap-up.
- The offered load is ``A = arrival_rate * average_handling_time / 60`` in
  Erlangs: the mean number of agents busy at any moment in an infinite-staff
  system.
- ``target_answer_time`` is seconds. The service level is the share of calls
  answered within that threshold; the default of 20 seconds is the classic
  80/20 rule. The engine is given no threshold only if a caller constructs
  ``ErlangCParameters`` directly with a non-positive value, which validation
  refuses.

Formulas
--------
Erlang B blocking probability, by the forward recursion (no factorials, so
large agent counts cannot overflow)::

    B(0, A) = 1
    B(n, A) = A * B(n-1, A) / (n + A * B(n-1, A))

Erlang C probability of waiting, for ``0 < A < N``::

    C(N, A) = N * B(N, A) / (N - A * (1 - B(N, A)))

Average speed of answer, in the time unit of AHT::

    ASA = C * AHT / (N - A)

Service level, the share answered within ``t`` seconds::

    SL(t) = 1 - C * exp(-(N - A) * t / AHT_seconds)

Boundary behaviour is explicit: ``A >= N`` is an unstable queue — the
probability of waiting is 1, the average speed of answer is infinite and the
service level is 0. ``A <= 0`` returns a probability of waiting of 0.

Provenance
----------
The formulation follows ``shared_utils/erlang_c.py`` in
https://github.com/HatemIsmailShalaby1979/wfm-forecasting-calculator (the
owner's reference implementation, factorial closed form), re-expressed here on
the Erlang B recursion so large agent counts cannot overflow, and integrated
with this repository's parameter/result contracts. The reference's self-test
values — C(10, 8.5) = 0.5299, SL(12, 8.5, t=20 s, AHT=180 s) = 86.70%,
ASA(12, 8.5, 180 s) = 10.09 s, occupancy(8.5, 12) = 70.83%,
required_agents(100 calls, 180 s AHT, 30 min interval, 80/20) = 14 — are
pinned in ``tests/test_wfm_erlang_c.py``.

Removed with this rewrite, by design:

- The former ``confidence_interval`` result field was a flat band of
  ``0.05 * agents`` either side of the optimum with no statistical content.
  It is removed rather than relabelled; no sampling distribution exists to
  put an interval on.
- The former ``confidence_level`` parameter was never read by any
  calculation and is removed.
- The former ``calculate_traffic_intensity`` method returned per-agent
  utilisation; that value is now ``ErlangCResult.utilization``, and
  ``ErlangCResult.traffic_intensity`` carries the offered load in Erlangs,
  which is what the name means in the literature.
"""

import math
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_TARGET_ANSWER_TIME_SECONDS = 20.0


@dataclass
class ErlangCParameters:
    """Parameters for Erlang C calculations."""

    arrival_rate: float  # calls per hour
    average_handling_time: float  # minutes per call, talk plus wrap-up
    service_level_target: float  # share answered within target_answer_time, e.g. 0.80
    average_calls_per_period: float  # historical average, echoed in reports
    target_answer_time: float = DEFAULT_TARGET_ANSWER_TIME_SECONDS  # seconds
    max_agents: int = 1000  # upper bound of the staffing search


@dataclass
class ErlangCResult:
    """Result of an Erlang C staffing optimization."""

    optimal_agents: int
    probability_waiting: float
    average_speed_of_answer: float  # minutes; inf when the queue is unstable
    service_level_achieved: float  # share answered within target_answer_time
    traffic_intensity: float  # offered load A in Erlangs
    utilization: float  # A / N
    calculation_time: float  # wall-clock seconds, measured


class ErlangCEngine:
    """Erlang C staffing engine on the stable Erlang B recursion."""

    def __init__(self, params: ErlangCParameters) -> None:
        self.params = params
        self._validate_parameters()

    def _validate_parameters(self) -> None:
        """Validate input parameters."""
        if self.params.arrival_rate <= 0:
            raise ValueError("Arrival rate must be positive")
        if self.params.average_handling_time <= 0:
            raise ValueError("Average handling time must be positive")
        if not 0 < self.params.service_level_target < 1:
            raise ValueError("Service level target must be between 0 and 1")
        if self.params.average_calls_per_period <= 0:
            raise ValueError("Average calls per period must be positive")
        if self.params.target_answer_time <= 0:
            raise ValueError("Target answer time must be positive")
        if self.params.max_agents <= 0:
            raise ValueError("Max agents must be positive")

    def offered_load(self) -> float:
        """Return the offered load A in Erlangs.

        A = arrival_rate [calls/hour] * average_handling_time [minutes] / 60.
        """
        return self.params.arrival_rate * (self.params.average_handling_time / 60.0)

    @staticmethod
    def erlang_b_blocking(agents: int, offered_load: float) -> float:
        """Return the Erlang B blocking probability B(N, A).

        Forward recursion on the standard recurrence; O(N) float operations
        with no factorials, so agent counts in the thousands are safe.

        Args:
            agents: Number of agents N (>= 1).
            offered_load: Offered traffic A in Erlangs (>= 0).

        Returns:
            Blocking probability B(N, A) in [0, 1].
        """
        if agents <= 0:
            raise ValueError("Agents must be positive")
        if offered_load < 0:
            raise ValueError("Offered load must be non-negative")
        blocking = 1.0
        for n in range(1, agents + 1):
            blocking = offered_load * blocking / (n + offered_load * blocking)
        return blocking

    @staticmethod
    def erlang_c_probability_waiting(agents: int, offered_load: float) -> float:
        """Return the Erlang C probability that an arrival waits.

        Args:
            agents: Number of agents N (>= 1).
            offered_load: Offered traffic A in Erlangs (>= 0).

        Returns:
            Probability of waiting in [0, 1]. 1.0 when ``A >= N`` (unstable
            queue, infinite wait), 0.0 when ``A <= 0``.
        """
        if agents <= 0:
            raise ValueError("Agents must be positive")
        if offered_load < 0:
            raise ValueError("Offered load must be non-negative")
        if offered_load == 0:
            return 0.0
        if offered_load >= agents:
            return 1.0
        blocking = ErlangCEngine.erlang_b_blocking(agents, offered_load)
        denominator = agents - offered_load * (1.0 - blocking)
        probability = agents * blocking / denominator
        return max(0.0, min(1.0, probability))

    @staticmethod
    def calculate_average_speed_of_answer(
        agents: int, offered_load: float, average_handling_time_minutes: float
    ) -> float:
        """Return the average speed of answer in minutes.

        ASA = C * AHT / (N - A). Infinite when ``A >= N``.

        Args:
            agents: Number of agents N.
            offered_load: Offered traffic A in Erlangs.
            average_handling_time_minutes: AHT in minutes.

        Returns:
            Average speed of answer in minutes.
        """
        if average_handling_time_minutes <= 0:
            raise ValueError("Average handling time must be positive")
        if offered_load >= agents:
            return float("inf")
        probability_waiting = ErlangCEngine.erlang_c_probability_waiting(agents, offered_load)
        return probability_waiting * average_handling_time_minutes / (agents - offered_load)

    @staticmethod
    def calculate_service_level(
        agents: int,
        offered_load: float,
        target_answer_time_seconds: float,
        average_handling_time_minutes: float,
    ) -> float:
        """Return the share of calls answered within the target time.

        SL(t) = 1 - C * exp(-(N - A) * t / AHT_seconds).

        Args:
            agents: Number of agents N.
            offered_load: Offered traffic A in Erlangs.
            target_answer_time_seconds: Answer threshold t in seconds.
            average_handling_time_minutes: AHT in minutes.

        Returns:
            Service level in [0, 1]; 0.0 when ``A >= N``.
        """
        if target_answer_time_seconds <= 0:
            raise ValueError("Target answer time must be positive")
        if average_handling_time_minutes <= 0:
            raise ValueError("Average handling time must be positive")
        if offered_load >= agents:
            return 0.0
        probability_waiting = ErlangCEngine.erlang_c_probability_waiting(agents, offered_load)
        if probability_waiting == 0.0:
            return 1.0
        aht_seconds = average_handling_time_minutes * 60.0
        decay = math.exp(-(agents - offered_load) * target_answer_time_seconds / aht_seconds)
        service_level = 1.0 - probability_waiting * decay
        return max(0.0, min(1.0, service_level))

    def optimize_agents(self) -> ErlangCResult:
        """Find the smallest agent count meeting the service level target.

        Binary search over ``[1, max_agents]``; the service level is
        non-decreasing in the agent count for fixed offered load. When even
        ``max_agents`` cannot reach the target — including the unstable case
        ``A >= max_agents`` — the result reports ``max_agents`` with the
        service level actually achieved, so a shortfall is visible in the
        output rather than papered over.

        Returns:
            ErlangCResult with the searched optimum and its metrics.
        """
        started = time.perf_counter()
        offered_load = self.offered_load()
        lower_bound = 1
        upper_bound = self.params.max_agents
        optimal_agents: int | None = None

        while lower_bound <= upper_bound:
            mid_agents = (lower_bound + upper_bound) // 2
            service_level = self.calculate_service_level(
                mid_agents,
                offered_load,
                self.params.target_answer_time,
                self.params.average_handling_time,
            )
            if service_level >= self.params.service_level_target:
                optimal_agents = mid_agents
                upper_bound = mid_agents - 1
            else:
                lower_bound = mid_agents + 1

        if optimal_agents is None:
            optimal_agents = self.params.max_agents

        probability_waiting = self.erlang_c_probability_waiting(optimal_agents, offered_load)
        average_speed_of_answer = self.calculate_average_speed_of_answer(
            optimal_agents, offered_load, self.params.average_handling_time
        )
        service_level_achieved = self.calculate_service_level(
            optimal_agents,
            offered_load,
            self.params.target_answer_time,
            self.params.average_handling_time,
        )

        return ErlangCResult(
            optimal_agents=optimal_agents,
            probability_waiting=probability_waiting,
            average_speed_of_answer=average_speed_of_answer,
            service_level_achieved=service_level_achieved,
            traffic_intensity=offered_load,
            utilization=offered_load / optimal_agents,
            calculation_time=time.perf_counter() - started,
        )

    def generate_report(self, result: ErlangCResult) -> dict[str, Any]:
        """Generate a report dictionary from a result.

        Args:
            result: Erlang C calculation result.

        Returns:
            Dictionary with report data.
        """
        return {
            "optimal_agents": result.optimal_agents,
            "probability_waiting": result.probability_waiting,
            "average_speed_of_answer_minutes": result.average_speed_of_answer,
            "service_level_achieved": result.service_level_achieved,
            "target_answer_time_seconds": self.params.target_answer_time,
            "traffic_intensity_erlangs": result.traffic_intensity,
            "utilization_percentage": result.utilization * 100,
            "parameters": {
                "arrival_rate": self.params.arrival_rate,
                "average_handling_time_minutes": self.params.average_handling_time,
                "service_level_target": self.params.service_level_target,
                "average_calls_per_period": self.params.average_calls_per_period,
            },
        }


def create_erlang_c_engine(
    arrival_rate: float,
    average_handling_time: float,
    service_level_target: float,
    average_calls_per_period: float,
    *,
    target_answer_time: float = DEFAULT_TARGET_ANSWER_TIME_SECONDS,
) -> ErlangCEngine:
    """Factory function to create an Erlang C engine.

    Args:
        arrival_rate: Calls per hour.
        average_handling_time: Average handling time in minutes.
        service_level_target: Desired service level (0-1), the share answered
            within ``target_answer_time``.
        average_calls_per_period: Historical average calls per period.
        target_answer_time: Answer threshold in seconds; default 20 s.

    Returns:
        ErlangCEngine instance.
    """
    params = ErlangCParameters(
        arrival_rate=arrival_rate,
        average_handling_time=average_handling_time,
        service_level_target=service_level_target,
        average_calls_per_period=average_calls_per_period,
        target_answer_time=target_answer_time,
    )
    return ErlangCEngine(params)


if __name__ == "__main__":
    engine = create_erlang_c_engine(
        arrival_rate=50.0,
        average_handling_time=5.0,
        service_level_target=0.80,
        average_calls_per_period=1000,
    )

    result = engine.optimize_agents()
    report = engine.generate_report(result)

    print("=== WFM Forecasting Calculator ===")
    print(f"Optimal Agents: {report['optimal_agents']}")
    print(f"Probability of Waiting: {report['probability_waiting']:.2%}")
    print(f"Average Speed of Answer: {report['average_speed_of_answer_minutes']:.2f} minutes")
    print(
        f"Service Level within {report['target_answer_time_seconds']:.0f} s: "
        f"{report['service_level_achieved']:.2%}"
    )
    print(f"Utilization: {report['utilization_percentage']:.1f}%")
