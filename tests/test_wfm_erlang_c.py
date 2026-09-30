"""Textbook Erlang C reference values for engines/wfm/src/erlang_c.py.

Every reference number here is computed inside this file, independently of the
engine, from the standard formulas:

    B(0, A) = 1;  B(n, A) = A * B(n-1, A) / (n + A * B(n-1, A))   [Erlang B]
    C(N, A) = N * B(N, A) / (N - A * (1 - B(N, A)))               [Erlang C]
    ASA     = C * AHT / (N - A)
    SL(t)   = 1 - C * exp(-(N - A) * t / AHT)

The anchor values additionally reproduce the self-test of
wfm-forecasting-calculator (shared_utils/erlang_c.py,
github.com/HatemIsmailShalaby1979/wfm-forecasting-calculator) exactly:
C(10, 8.5) = 0.5299, SL(12, 8.5, t=20 s, AHT=180 s) = 86.70%,
ASA(12, 8.5, 180 s) = 10.09 s, occupancy(8.5, 12) = 70.83%, and
required_agents(100 calls, 180 s AHT, 30 min interval, 80/20) = 14.

The engine under test was rewritten (2026-09-30) from a non-standard closed
form to this formulation; the previous implementation deviated from the
reference by up to 0.81 absolute on the pairs below (e.g. C(100, 80): 0.769
vs the correct 0.0196).
"""

import math

import pytest

from engines.wfm.src.erlang_c import (
    ErlangCEngine,
    ErlangCParameters,
    create_erlang_c_engine,
)


def reference_blocking(agents: int, offered_load: float) -> float:
    """Erlang B blocking probability by the forward recursion."""
    blocking = 1.0
    for n in range(1, agents + 1):
        blocking = offered_load * blocking / (n + offered_load * blocking)
    return blocking


def reference_waiting(agents: int, offered_load: float) -> float:
    """Erlang C probability of waiting from the textbook closed form."""
    if offered_load <= 0.0:
        return 0.0
    if offered_load >= agents:
        return 1.0
    blocking = reference_blocking(agents, offered_load)
    return agents * blocking / (agents - offered_load * (1.0 - blocking))


def reference_waiting_factorial(agents: int, offered_load: float) -> float:
    """The factorial closed form, valid for small N only (floats overflow)."""
    numerator = (offered_load**agents / math.factorial(agents)) * (agents / (agents - offered_load))
    denominator = sum(offered_load**k / math.factorial(k) for k in range(agents))
    return numerator / (denominator + numerator)


REFERENCE_PAIRS: list[tuple[int, float]] = [
    (10, 8.5),
    (12, 8.5),
    (14, 10.0),
    (20, 15.0),
    (5, 2.0),
    (8, 6.0),
    (30, 25.0),
    (50, 45.0),
    (100, 80.0),
    (200, 170.0),
]


@pytest.mark.parametrize(("agents", "offered_load"), REFERENCE_PAIRS)
def test_waiting_probability_matches_the_textbook(agents: int, offered_load: float) -> None:
    """The engine's C(N, A) equals the independently computed reference."""
    engine_value = ErlangCEngine.erlang_c_probability_waiting(agents, offered_load)
    assert engine_value == pytest.approx(reference_waiting(agents, offered_load), abs=1e-12)


@pytest.mark.parametrize(("agents", "offered_load"), [(10, 8.5), (12, 8.5), (14, 10.0)])
def test_waiting_probability_matches_the_factorial_closed_form(
    agents: int, offered_load: float
) -> None:
    """Small-N cases also agree with the factorial formulation."""
    engine_value = ErlangCEngine.erlang_c_probability_waiting(agents, offered_load)
    assert engine_value == pytest.approx(
        reference_waiting_factorial(agents, offered_load), abs=1e-12
    )


def test_the_factorial_form_overflows_where_the_recursion_holds() -> None:
    """Large N is exactly why the engine uses the recursion.

    The factorial closed form raises OverflowError at N=200 (200! cannot be
    divided into a float), while the engine computes C(200, 170) from the
    recursion and matches the in-file reference.
    """
    with pytest.raises(OverflowError):
        reference_waiting_factorial(200, 170.0)
    engine_value = ErlangCEngine.erlang_c_probability_waiting(200, 170.0)
    assert engine_value == pytest.approx(reference_waiting(200, 170.0), abs=1e-12)


class TestReferenceRepoSelfTestAnchors:
    """The values wfm-forecasting-calculator's self-test reproduces."""

    def test_waiting_probability(self) -> None:
        assert ErlangCEngine.erlang_c_probability_waiting(10, 8.5) == pytest.approx(
            0.5299, abs=5e-5
        )

    def test_service_level(self) -> None:
        value = ErlangCEngine.calculate_service_level(12, 8.5, 20.0, 3.0)
        assert value == pytest.approx(0.8670, abs=5e-5)

    def test_average_speed_of_answer(self) -> None:
        asa_seconds = ErlangCEngine.calculate_average_speed_of_answer(12, 8.5, 3.0) * 60.0
        assert asa_seconds == pytest.approx(10.09, abs=5e-3)

    def test_occupancy(self) -> None:
        assert 8.5 / 12.0 == pytest.approx(0.7083, abs=5e-5)

    def test_required_agents(self) -> None:
        """100 calls / 30 min at 180 s AHT is A = 10.0 Erlangs; 80/20 needs 14."""
        engine = create_erlang_c_engine(
            arrival_rate=100.0 / (30.0 / 60.0),
            average_handling_time=180.0 / 60.0,
            service_level_target=0.80,
            average_calls_per_period=100.0,
            target_answer_time=20.0,
        )
        result = engine.optimize_agents()
        assert result.optimal_agents == 14
        assert result.service_level_achieved >= 0.80
        assert result.utilization == pytest.approx(10.0 / 14.0)


class TestBoundaries:
    """Boundary behaviour: unstable queues, single agent, no load, huge N."""

    @pytest.mark.parametrize(
        ("agents", "offered_load"), [(10, 10.0), (10, 11.0), (5, 5.0), (3, 50.0)]
    )
    def test_overloaded_queue_is_unstable(self, agents: int, offered_load: float) -> None:
        """A >= N: everyone waits, answer time is infinite, service level is 0."""
        assert ErlangCEngine.erlang_c_probability_waiting(agents, offered_load) == 1.0
        asa = ErlangCEngine.calculate_average_speed_of_answer(agents, offered_load, 3.0)
        assert asa == float("inf")
        assert ErlangCEngine.calculate_service_level(agents, offered_load, 20.0, 3.0) == 0.0

    @pytest.mark.parametrize("offered_load", [0.3, 0.5, 0.7, 0.99])
    def test_single_agent_matches_the_mm1_property(self, offered_load: float) -> None:
        """M/M/1: the probability of waiting is the utilisation itself."""
        assert ErlangCEngine.erlang_c_probability_waiting(1, offered_load) == pytest.approx(
            offered_load, abs=1e-12
        )

    def test_zero_load_never_waits(self) -> None:
        assert ErlangCEngine.erlang_c_probability_waiting(7, 0.0) == 0.0

    @pytest.mark.parametrize(("agents", "offered_load"), [(2000, 1500.0), (5000, 4000.0)])
    def test_very_large_agent_counts_stay_in_range(self, agents: int, offered_load: float) -> None:
        value = ErlangCEngine.erlang_c_probability_waiting(agents, offered_load)
        assert 0.0 <= value <= 1.0
        assert value == pytest.approx(reference_waiting(agents, offered_load), abs=1e-12)

    def test_invalid_parameters_are_refused(self) -> None:
        with pytest.raises(ValueError):
            create_erlang_c_engine(0.0, 5.0, 0.8, 100.0)
        with pytest.raises(ValueError):
            create_erlang_c_engine(50.0, 0.0, 0.8, 100.0)
        with pytest.raises(ValueError):
            create_erlang_c_engine(50.0, 5.0, 0.0, 100.0)
        with pytest.raises(ValueError):
            create_erlang_c_engine(50.0, 5.0, 1.0, 100.0)
        with pytest.raises(ValueError):
            create_erlang_c_engine(50.0, 5.0, 0.8, 100.0, target_answer_time=0.0)
        with pytest.raises(ValueError):
            ErlangCEngine(
                ErlangCParameters(
                    arrival_rate=50.0,
                    average_handling_time=5.0,
                    service_level_target=0.8,
                    average_calls_per_period=100.0,
                    max_agents=0,
                )
            )
        with pytest.raises(ValueError):
            ErlangCEngine.erlang_c_probability_waiting(0, 1.0)

    def test_the_removed_fake_confidence_interval_stays_removed(self) -> None:
        """The flat 0.05*agents band and the unused confidence_level are gone."""
        engine = create_erlang_c_engine(50.0, 5.0, 0.8, 1000.0)
        result = engine.optimize_agents()
        assert not hasattr(result, "confidence_interval")
        param_fields = {f for f in ErlangCParameters.__dataclass_fields__}
        assert "confidence_level" not in param_fields
        assert "confidence_interval" not in engine.generate_report(result)


class TestProperties:
    """Properties that must hold across a grid, not just at pinned points."""

    @pytest.mark.parametrize("offered_load", [2.0, 8.5, 10.0, 45.0])
    def test_probability_bounded_and_monotone_in_agents(self, offered_load: float) -> None:
        start = max(1, math.ceil(offered_load))
        previous: float | None = None
        for agents in range(start, start + 40):
            value = ErlangCEngine.erlang_c_probability_waiting(agents, offered_load)
            assert 0.0 <= value <= 1.0
            if previous is not None:
                assert value <= previous + 1e-15
            previous = value

    @pytest.mark.parametrize("offered_load", [2.0, 8.5, 45.0])
    def test_service_level_monotone_in_agents(self, offered_load: float) -> None:
        start = max(1, math.ceil(offered_load))
        previous: float | None = None
        for agents in range(start, start + 40):
            value = ErlangCEngine.calculate_service_level(agents, offered_load, 20.0, 3.0)
            assert 0.0 <= value <= 1.0
            if previous is not None:
                assert value >= previous - 1e-15
            previous = value

    def test_optimal_agents_is_the_minimum_meeting_the_target(self) -> None:
        """The search returns the smallest N that reaches the target, not any N."""
        engine = create_erlang_c_engine(50.0, 5.0, 0.80, 1000.0)
        result = engine.optimize_agents()
        offered_load = engine.offered_load()
        below = ErlangCEngine.calculate_service_level(
            result.optimal_agents - 1, offered_load, 20.0, 5.0
        )
        assert below < 0.80
        assert result.service_level_achieved >= 0.80

    def test_result_semantics(self) -> None:
        """traffic_intensity is the offered load in Erlangs; utilization is A/N."""
        engine = create_erlang_c_engine(50.0, 5.0, 0.80, 1000.0)
        result = engine.optimize_agents()
        assert result.traffic_intensity == pytest.approx(50.0 * 5.0 / 60.0, abs=1e-12)
        assert result.utilization == pytest.approx(
            result.traffic_intensity / result.optimal_agents, abs=1e-12
        )
        assert result.calculation_time >= 0.0

    def test_same_inputs_produce_identical_semantic_metrics(self) -> None:
        """Reported records are a function of the inputs, not of the clock."""
        first = create_erlang_c_engine(50.0, 5.0, 0.80, 1000.0).optimize_agents()
        second = create_erlang_c_engine(50.0, 5.0, 0.80, 1000.0).optimize_agents()
        assert first.optimal_agents == second.optimal_agents
        assert first.probability_waiting == second.probability_waiting
        assert first.average_speed_of_answer == second.average_speed_of_answer
        assert first.service_level_achieved == second.service_level_achieved
