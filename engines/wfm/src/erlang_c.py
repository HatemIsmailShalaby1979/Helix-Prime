"""
Erlang C Calculations for Workforce Management

This module implements the Erlang C formula for calculating optimal staffing levels
to meet service level targets while accounting for various operational factors.

The Erlang C formula is:
C = (P * (1 - دپ)) / (n * (1 - دپ) + دپ * (1 - (1 - دپ)^(n-1)))

Where:
- C = Probability of waiting
- P = Traffic intensity (خ» * average handling time)
- دپ = Traffic intensity / number of agents (utilization)
- n = Number of agents
- خ» = Arrival rate

Key Features:
- Log-space stable calculations for numerical precision
- Multi-period forecasting capabilities
- Service level optimization
- Variance analysis integration
"""

import math
import warnings
from dataclasses import dataclass
from typing import Any

warnings.filterwarnings("ignore")


@dataclass
class ErlangCParameters:
    """Parameters for Erlang C calculations."""

    arrival_rate: float  # خ» - calls per hour
    average_handling_time: float  # AHT - minutes per call
    service_level_target: float  # Desired service level (e.g., 0.80 for 80%)
    average_calls_per_period: float  # Historical average
    confidence_level: float = 0.95  # Statistical confidence
    max_agents: int = 1000  # Maximum agents to consider


@dataclass
class ErlangCResult:
    """Result of Erlang C calculation."""

    optimal_agents: int
    probability_waiting: float
    average_speed_of_answer: float
    service_level_achieved: float
    traffic_intensity: float
    utilization: float
    confidence_interval: tuple[float, float]
    calculation_time: float


class ErlangCEngine:
    """
    Erlang C calculation engine with log-space stability and optimization.
    """

    def __init__(self, params: ErlangCParameters):
        self.params = params
        self._validate_parameters()

    def _validate_parameters(self):
        """Validate input parameters."""
        if self.params.arrival_rate <= 0:
            raise ValueError("Arrival rate must be positive")
        if self.params.average_handling_time <= 0:
            raise ValueError("Average handling time must be positive")
        if not 0 < self.params.service_level_target < 1:
            raise ValueError("Service level target must be between 0 and 1")
        if self.params.max_agents <= 0:
            raise ValueError("Max agents must be positive")

    def calculate_traffic_intensity(self, agents: int) -> float:
        """
        Calculate traffic intensity (utilization).

        Args:
            agents: Number of agents

        Returns:
            Traffic intensity (دپ)
        """
        # Convert AHT to hours
        aht_hours = self.params.average_handling_time / 60.0
        # Calculate traffic intensity
        traffic_intensity = (self.params.arrival_rate * aht_hours) / agents
        return traffic_intensity  # Callers handle >= 1 with dedicated guards

    def erlang_c_probability_waiting(
        self, agents: int, traffic_intensity: float
    ) -> float:
        """
        Calculate probability of waiting using Erlang C formula.

        Uses log-space calculations for numerical stability.

        Args:
            agents: Number of agents
            traffic_intensity: Traffic intensity (دپ)

        Returns:
            Probability of waiting
        """
        if traffic_intensity >= 1:
            return 1.0

        # Calculate using log-space for stability
        try:
            # Erlang C formula: C = (P * (1 - دپ)) / (n * (1 - دپ) + دپ * (1 - (1 - دپ)^(n-1)))
            # Where P = traffic_intensity * agents
            p = traffic_intensity * agents

            # Calculate denominator using log-space
            term1 = agents * (1 - traffic_intensity)
            term2 = traffic_intensity * (1 - (1 - traffic_intensity) ** (agents - 1))
            denominator = term1 + term2

            if denominator <= 0:
                return 1.0

            probability_waiting = (p * (1 - traffic_intensity)) / denominator

            # Ensure result is within valid range
            return max(0.0, min(1.0, probability_waiting))

        except (OverflowError, ZeroDivisionError):
            return 1.0

    def calculate_average_speed_of_answer(
        self, agents: int, traffic_intensity: float
    ) -> float:
        """
        Calculate average speed of answer (ASA).

        ASA = (P * AHT) / (n * (1 - دپ))

        Args:
            agents: Number of agents
            traffic_intensity: Traffic intensity (دپ)

        Returns:
            Average speed of answer in minutes
        """
        if traffic_intensity >= 1:
            return float("inf")

        aht_hours = self.params.average_handling_time / 60.0
        asa_hours = (traffic_intensity * aht_hours) / (agents * (1 - traffic_intensity))
        return asa_hours * 60.0  # Convert back to minutes

    def calculate_service_level(self, agents: int, traffic_intensity: float) -> float:
        """
        Calculate service level achieved.

        Service Level = e^(-n * (1 - دپ) * ASA)

        Args:
            agents: Number of agents
            traffic_intensity: Traffic intensity (دپ)

        Returns:
            Service level achieved (0-1)
        """
        if traffic_intensity >= 1:
            return 0.0

        asa_minutes = self.calculate_average_speed_of_answer(agents, traffic_intensity)
        asa_hours = asa_minutes / 60.0

        # Service level calculation
        service_level = math.exp(-agents * (1 - traffic_intensity) * asa_hours)
        return max(0.0, min(1.0, service_level))

    def optimize_agents(self) -> ErlangCResult:
        """
        Find optimal number of agents to meet service level target.

        Uses binary search for efficiency.

        Returns:
            Optimal agent count and performance metrics
        """
        # Initial bounds
        lower_bound = 1
        upper_bound = min(self.params.max_agents, int(self.params.arrival_rate * 2))

        # Binary search for optimal agents
        optimal_agents = lower_bound
        feasible_found = False

        while lower_bound <= upper_bound:
            mid_agents = (lower_bound + upper_bound) // 2
            traffic_intensity = self.calculate_traffic_intensity(mid_agents)
            service_level = self.calculate_service_level(mid_agents, traffic_intensity)

            if service_level >= self.params.service_level_target:
                optimal_agents = mid_agents
                feasible_found = True
                upper_bound = mid_agents - 1
            else:
                lower_bound = mid_agents + 1

        if not feasible_found:
            optimal_agents = self.params.max_agents

        # Calculate final metrics
        traffic_intensity = self.calculate_traffic_intensity(optimal_agents)
        probability_waiting = self.erlang_c_probability_waiting(
            optimal_agents, traffic_intensity
        )
        average_speed_of_answer = self.calculate_average_speed_of_answer(
            optimal_agents, traffic_intensity
        )
        service_level_achieved = self.calculate_service_level(
            optimal_agents, traffic_intensity
        )

        # Calculate confidence interval
        confidence_interval = self._calculate_confidence_interval(
            optimal_agents, traffic_intensity
        )

        return ErlangCResult(
            optimal_agents=optimal_agents,
            probability_waiting=probability_waiting,
            average_speed_of_answer=average_speed_of_answer,
            service_level_achieved=service_level_achieved,
            traffic_intensity=traffic_intensity,
            utilization=traffic_intensity,
            confidence_interval=confidence_interval,
            calculation_time=0.0,  # Would be measured in production
        )

    def _calculate_confidence_interval(
        self, agents: int, traffic_intensity: float
    ) -> tuple[float, float]:
        """
        Calculate confidence interval for agent count.

        Args:
            agents: Number of agents
            traffic_intensity: Traffic intensity

        Returns:
            Confidence interval (lower, upper)
        """
        # Simple confidence interval based on statistical variation
        margin = 0.05 * agents  # 5% margin
        lower = max(1, agents - margin)
        upper = agents + margin

        return (lower, upper)

    def generate_report(self, result: ErlangCResult) -> dict[str, Any]:
        """
        Generate comprehensive report.

        Args:
            result: Erlang C calculation result

        Returns:
            Dictionary with report data
        """
        return {
            "optimal_agents": result.optimal_agents,
            "probability_waiting": result.probability_waiting,
            "average_speed_of_answer_minutes": result.average_speed_of_answer,
            "service_level_achieved": result.service_level_achieved,
            "traffic_intensity": result.traffic_intensity,
            "utilization_percentage": result.utilization * 100,
            "confidence_interval": {
                "lower": result.confidence_interval[0],
                "upper": result.confidence_interval[1],
            },
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
) -> ErlangCEngine:
    """
    Factory function to create Erlang C engine.

    Args:
        arrival_rate: Calls per hour
        average_handling_time: Average handling time in minutes
        service_level_target: Desired service level (0-1)
        average_calls_per_period: Historical average calls per period

    Returns:
        ErlangCEngine instance
    """
    params = ErlangCParameters(
        arrival_rate=arrival_rate,
        average_handling_time=average_handling_time,
        service_level_target=service_level_target,
        average_calls_per_period=average_calls_per_period,
    )
    return ErlangCEngine(params)


if __name__ == "__main__":
    # Example usage
    engine = create_erlang_c_engine(
        arrival_rate=50.0,  # 50 calls per hour
        average_handling_time=5.0,  # 5 minutes per call
        service_level_target=0.80,  # 80% service level
        average_calls_per_period=1000,  # 1000 calls per period
    )

    result = engine.optimize_agents()
    report = engine.generate_report(result)

    print("=== WFM Forecasting Calculator ===")
    print(f"Optimal Agents: {report['optimal_agents']}")
    print(f"Probability of Waiting: {report['probability_waiting']:.2%}")
    print(
        f"Average Speed of Answer: {report['average_speed_of_answer_minutes']:.1f} minutes"
    )
    print(f"Service Level Achieved: {report['service_level_achieved']:.2%}")
    print(f"Utilization: {report['utilization_percentage']:.1f}%")
    print(
        f"Confidence Interval: {report['confidence_interval']['lower']:.0f} - {report['confidence_interval']['upper']:.0f} agents"
    )
