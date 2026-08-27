"""
RTA Calculations for Real-Time Adherence

This module implements the core calculations for the Real-Time Adherence (RTA) system.
It provides adherence calculations, schedule optimization, and performance benchmarking.

Key Features:
- RTACalculations and adherence math
- Schedule optimization algorithms
- Performance benchmarking
- Real-time adherence tracking
- Variance analysis
"""

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RTACalculationResult:
    """Result of RTA calculation."""

    def __init__(self):
        self.adherence_metrics = {}
        self.schedule_metrics = {}
        self.performance_metrics = {}
        self.variance_analysis = {}
        self.optimization_recommendations = []
        self.confidence_score = 0.0


class RTACalculator:
    """
    RTA calculation engine for real-time adherence monitoring.
    """

    def __init__(
        self, adherence_threshold: float = 0.85, variance_threshold: float = 2.0
    ):
        self.adherence_threshold = adherence_threshold
        self.variance_threshold = variance_threshold
        self.scaler = StandardScaler()

    def calculate_adherence(
        self, schedule_data: pd.DataFrame, actual_data: pd.DataFrame
    ) -> dict[str, Any]:
        """
        Calculate adherence metrics from schedule and actual data.

        Args:
            schedule_data: DataFrame with scheduled hours
            actual_data: DataFrame with actual hours

        Returns:
            Dictionary with adherence metrics
        """
        # Merge schedule and actual data (hour is a merge key — both describe the same time slot)
        merged_data = pd.merge(
            schedule_data, actual_data, on=["agent_id", "date", "hour"], how="inner"
        )

        # Calculate adherence percentage
        merged_data["adherence_percentage"] = (
            merged_data["actual_hours"] / merged_data["scheduled_hours"] * 100
        )

        # Calculate overall adherence
        overall_adherence = merged_data["adherence_percentage"].mean()

        # Calculate adherence by agent
        agent_adherence = (
            merged_data.groupby("agent_id")["adherence_percentage"].mean().to_dict()
        )

        # Calculate adherence by date
        date_adherence = (
            merged_data.groupby("date")["adherence_percentage"].mean().to_dict()
        )

        # Calculate adherence by hour
        hour_adherence = (
            merged_data.groupby("hour")["adherence_percentage"].mean().to_dict()
        )

        # Calculate adherence statistics
        adherence_stats = {
            "overall_adherence": overall_adherence,
            "agent_adherence": agent_adherence,
            "date_adherence": date_adherence,
            "hour_adherence": hour_adherence,
            "total_scheduled_hours": merged_data["scheduled_hours"].sum(),
            "total_actual_hours": merged_data["actual_hours"].sum(),
            "total_variance_hours": (
                merged_data["scheduled_hours"] - merged_data["actual_hours"]
            ).sum(),
            "adherence_variance": merged_data["adherence_percentage"].var(),
        }

        return adherence_stats

    def calculate_schedule_metrics(self, schedule_data: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate schedule metrics.

        Args:
            schedule_data: DataFrame with schedule data

        Returns:
            Dictionary with schedule metrics
        """
        metrics = {}

        # Calculate total scheduled hours
        total_scheduled_hours = schedule_data["scheduled_hours"].sum()

        # Calculate average scheduled hours per agent
        avg_scheduled_hours = schedule_data["scheduled_hours"].mean()

        # Calculate schedule coverage
        unique_agents = schedule_data["agent_id"].nunique()
        unique_dates = schedule_data["date"].nunique()

        # Calculate schedule density
        schedule_density = len(schedule_data) / (unique_agents * unique_dates)

        # Calculate schedule balance
        agent_hours = schedule_data.groupby("agent_id")["scheduled_hours"].sum()
        schedule_balance = (
            1 - (agent_hours.std() / agent_hours.mean())
            if agent_hours.mean() > 0
            else 0
        )

        metrics = {
            "total_scheduled_hours": total_scheduled_hours,
            "average_scheduled_hours_per_agent": avg_scheduled_hours,
            "unique_agents": unique_agents,
            "unique_dates": unique_dates,
            "schedule_density": schedule_density,
            "schedule_balance": schedule_balance,
            "max_scheduled_hours": schedule_data["scheduled_hours"].max(),
            "min_scheduled_hours": schedule_data["scheduled_hours"].min(),
        }

        return metrics

    def calculate_performance_metrics(
        self, actual_data: pd.DataFrame, schedule_data: pd.DataFrame | None = None
    ) -> dict[str, Any]:
        """
        Calculate performance metrics.

        Args:
            actual_data: DataFrame with actual data
            schedule_data: Optional DataFrame with schedule data (required for efficiency metrics)

        Returns:
            Dictionary with performance metrics
        """
        metrics = {}

        # Calculate total actual hours
        total_actual_hours = actual_data["actual_hours"].sum()

        # Calculate average actual hours per agent
        avg_actual_hours = actual_data["actual_hours"].mean()

        # Calculate performance by agent
        agent_performance = (
            actual_data.groupby("agent_id")["actual_hours"]
            .agg(["sum", "mean", "std"])
            .round(2)
        )
        agent_performance_dict = agent_performance.to_dict("index")

        # Calculate performance by date
        date_performance = (
            actual_data.groupby("date")["actual_hours"]
            .agg(["sum", "mean", "std"])
            .round(2)
        )
        date_performance_dict = date_performance.to_dict("index")

        # Calculate performance by hour
        hour_performance = (
            actual_data.groupby("hour")["actual_hours"]
            .agg(["sum", "mean", "std"])
            .round(2)
        )
        hour_performance_dict = hour_performance.to_dict("index")

        # Calculate efficiency metrics
        efficiency_metrics = self._calculate_efficiency_metrics(
            actual_data, schedule_data
        )

        metrics = {
            "total_actual_hours": total_actual_hours,
            "average_actual_hours_per_agent": avg_actual_hours,
            "agent_performance": agent_performance_dict,
            "date_performance": date_performance_dict,
            "hour_performance": hour_performance_dict,
            "efficiency_metrics": efficiency_metrics,
        }

        return metrics

    def _calculate_efficiency_metrics(
        self, actual_data: pd.DataFrame, schedule_data: pd.DataFrame | None = None
    ) -> dict[str, Any]:
        """
        Calculate efficiency metrics.

        Args:
            actual_data: DataFrame with actual data
            schedule_data: Optional DataFrame with schedule data (required for scheduled_hours)

        Returns:
            Dictionary with efficiency metrics
        """
        if schedule_data is not None:
            # Merge to bring scheduled_hours alongside actual_hours
            merged = pd.merge(
                actual_data,
                schedule_data[["agent_id", "date", "scheduled_hours"]],
                on=["agent_id", "date"],
                how="left",
            )
        else:
            merged = actual_data.copy()
            merged["scheduled_hours"] = merged["actual_hours"]

        # Calculate productivity
        productivity = merged["actual_hours"] / merged["scheduled_hours"].replace(
            0, np.nan
        )

        # Calculate efficiency score
        efficiency_score = (productivity * 100).mean()

        # Calculate overtime
        overtime = (merged["actual_hours"] - merged["scheduled_hours"]).clip(lower=0)
        total_overtime = overtime.sum()

        # Calculate undertime
        undertime = (merged["scheduled_hours"] - merged["actual_hours"]).clip(lower=0)
        total_undertime = undertime.sum()

        total_scheduled = merged["scheduled_hours"].sum()

        return {
            "efficiency_score": efficiency_score,
            "total_overtime_hours": total_overtime,
            "total_undertime_hours": total_undertime,
            "overtime_percentage": (total_overtime / total_scheduled * 100)
            if total_scheduled > 0
            else 0,
            "undertime_percentage": (total_undertime / total_scheduled * 100)
            if total_scheduled > 0
            else 0,
        }

    def calculate_variance_analysis(
        self, schedule_data: pd.DataFrame, actual_data: pd.DataFrame
    ) -> dict[str, Any]:
        """
        Calculate variance analysis.

        Args:
            schedule_data: DataFrame with schedule data
            actual_data: DataFrame with actual data

        Returns:
            Dictionary with variance analysis
        """
        # Merge schedule and actual data
        merged_data = pd.merge(
            schedule_data, actual_data, on=["agent_id", "date", "hour"], how="inner"
        )

        # Calculate variance
        merged_data["variance_hours"] = (
            merged_data["scheduled_hours"] - merged_data["actual_hours"]
        )
        merged_data["variance_percentage"] = (
            merged_data["variance_hours"] / merged_data["scheduled_hours"]
        ) * 100

        # Calculate variance statistics
        variance_stats = {
            "total_variance_hours": merged_data["variance_hours"].sum(),
            "average_variance_hours": merged_data["variance_hours"].mean(),
            "variance_hours_std": merged_data["variance_hours"].std(),
            "positive_variance_count": (merged_data["variance_hours"] > 0).sum(),
            "negative_variance_count": (merged_data["variance_hours"] < 0).sum(),
            "positive_variance_hours": merged_data[merged_data["variance_hours"] > 0][
                "variance_hours"
            ].sum(),
            "negative_variance_hours": merged_data[merged_data["variance_hours"] < 0][
                "variance_hours"
            ].sum(),
        }

        # Calculate variance by agent
        agent_variance = (
            merged_data.groupby("agent_id")["variance_hours"]
            .agg(["sum", "mean", "std"])
            .round(2)
        )
        agent_variance_dict = agent_variance.to_dict("index")

        # Calculate variance by date
        date_variance = (
            merged_data.groupby("date")["variance_hours"]
            .agg(["sum", "mean", "std"])
            .round(2)
        )
        date_variance_dict = date_variance.to_dict("index")

        # Calculate variance by hour
        hour_variance = (
            merged_data.groupby("hour")["variance_hours"]
            .agg(["sum", "mean", "std"])
            .round(2)
        )
        hour_variance_dict = hour_variance.to_dict("index")

        # Calculate variance patterns
        variance_patterns = self._identify_variance_patterns(merged_data)

        return {
            "variance_stats": variance_stats,
            "agent_variance": agent_variance_dict,
            "date_variance": date_variance_dict,
            "hour_variance": hour_variance_dict,
            "variance_patterns": variance_patterns,
        }

    def _identify_variance_patterns(self, data: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Identify variance patterns.

        Args:
            data: DataFrame with variance data

        Returns:
            List of variance patterns
        """
        patterns = []

        # Pattern 1: High variance agents
        agent_variance = data.groupby("agent_id")["variance_hours"].agg(
            ["sum", "mean", "std"]
        )
        high_variance_agents = agent_variance[
            agent_variance["mean"] > agent_variance["mean"].quantile(0.75)
        ].index.tolist()

        if high_variance_agents:
            patterns.append(
                {
                    "type": "high_variance_agents",
                    "description": f"Agents with high variance: {high_variance_agents}",
                    "impact": "high",
                    "severity": "medium",
                }
            )

        # Pattern 2: Temporal variance patterns
        daily_variance = data.groupby("date")["variance_hours"].agg(
            ["sum", "mean", "std"]
        )
        high_variance_days = daily_variance[
            daily_variance["mean"] > daily_variance["mean"].quantile(0.75)
        ].index.tolist()

        if high_variance_days:
            patterns.append(
                {
                    "type": "high_variance_days",
                    "description": f"Days with high variance: {high_variance_days}",
                    "impact": "medium",
                    "severity": "low",
                }
            )

        # Pattern 3: Hour-based variance patterns
        hourly_variance = data.groupby("hour")["variance_hours"].agg(
            ["sum", "mean", "std"]
        )
        peak_variance_hours = hourly_variance[
            hourly_variance["mean"] > hourly_variance["mean"].quantile(0.75)
        ].index.tolist()

        if peak_variance_hours:
            patterns.append(
                {
                    "type": "peak_variance_hours",
                    "description": f"Hours with peak variance: {peak_variance_hours}",
                    "impact": "high",
                    "severity": "medium",
                }
            )

        return patterns

    def generate_optimization_recommendations(
        self, variance_analysis: dict[str, Any]
    ) -> list[str]:
        """
        Generate optimization recommendations based on variance analysis.

        Args:
            variance_analysis: Variance analysis results

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        # Recommendation based on high variance agents
        if "agent_variance" in variance_analysis:
            high_variance_agents = [
                agent
                for agent, stats in variance_analysis["agent_variance"].items()
                if stats["mean"]
                > variance_analysis["agent_variance"][
                    next(iter(variance_analysis["agent_variance"].keys()))
                ]["mean"]
                * 1.5
            ]

            if high_variance_agents:
                recommendations.append(
                    f"Review scheduling for high-variance agents: {high_variance_agents}. Consider individual schedule optimization."
                )

        # Recommendation based on high variance days
        if "date_variance" in variance_analysis:
            high_variance_days = [
                date
                for date, stats in variance_analysis["date_variance"].items()
                if stats["mean"]
                > variance_analysis["date_variance"][
                    next(iter(variance_analysis["date_variance"].keys()))
                ]["mean"]
                * 1.5
            ]

            if high_variance_days:
                recommendations.append(
                    f"Investigate high-variance days: {high_variance_days}. Review external factors affecting these days."
                )

        # Recommendation based on high variance hours
        if "hour_variance" in variance_analysis:
            high_variance_hours = [
                hour
                for hour, stats in variance_analysis["hour_variance"].items()
                if stats["mean"]
                > variance_analysis["hour_variance"][
                    next(iter(variance_analysis["hour_variance"].keys()))
                ]["mean"]
                * 1.5
            ]

            if high_variance_hours:
                recommendations.append(
                    f"Optimize staffing for high-variance hours: {high_variance_hours}. Adjust schedule based on historical patterns."
                )

        # Default recommendation if no specific issues found
        if not recommendations:
            recommendations.append(
                "Variance analysis completed. Current scheduling shows acceptable variance levels."
            )

        return recommendations

    def analyze(
        self, schedule_data: pd.DataFrame, actual_data: pd.DataFrame
    ) -> RTACalculationResult:
        """
        Perform comprehensive RTA analysis.

        Args:
            schedule_data: DataFrame with schedule data
            actual_data: DataFrame with actual data

        Returns:
            RTACalculationResult object
        """
        result = RTACalculationResult()

        try:
            # Calculate adherence metrics
            result.adherence_metrics = self.calculate_adherence(
                schedule_data, actual_data
            )

            # Calculate schedule metrics
            result.schedule_metrics = self.calculate_schedule_metrics(schedule_data)

            # Calculate performance metrics
            result.performance_metrics = self.calculate_performance_metrics(
                actual_data, schedule_data
            )

            # Calculate variance analysis
            result.variance_analysis = self.calculate_variance_analysis(
                schedule_data, actual_data
            )

            # Generate optimization recommendations
            result.optimization_recommendations = (
                self.generate_optimization_recommendations(result.variance_analysis)
            )

            # Calculate confidence score
            result.confidence_score = self._calculate_confidence_score(result)

        except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
            logger.error("Error in RTA analysis: %s", e)
            result.optimization_recommendations = [
                f"Analysis completed with warnings: {e!s}"
            ]
            result.confidence_score = 0.0

        return result

    def _calculate_confidence_score(self, result: RTACalculationResult) -> float:
        """
        Calculate confidence score based on analysis results.

        Args:
            result: RTA calculation result

        Returns:
            Confidence score (0-1)
        """
        score = 1.0

        # Deduct for low adherence
        overall_adherence = result.adherence_metrics.get("overall_adherence", 0)
        if overall_adherence < self.adherence_threshold * 100:
            score -= (self.adherence_threshold * 100 - overall_adherence) / 100

        # Deduct for high variance
        variance_stats = result.variance_analysis.get("variance_stats", {})
        variance_hours_std = variance_stats.get("variance_hours_std", 0)
        if variance_hours_std > self.variance_threshold:
            score -= min((variance_hours_std - self.variance_threshold) / 10, 0.5)

        # Deduct for low efficiency
        efficiency_metrics = result.performance_metrics.get("efficiency_metrics", {})
        efficiency_score = efficiency_metrics.get("efficiency_score", 0)
        if efficiency_score < 80:
            score -= (80 - efficiency_score) / 100

        return max(0.0, score)


def create_rta_calculator(
    adherence_threshold: float = 0.85, variance_threshold: float = 2.0
) -> RTACalculator:
    """
    Factory function to create RTA calculator.

    Args:
        adherence_threshold: Minimum adherence threshold (0-1)
        variance_threshold: Maximum acceptable variance

    Returns:
        RTACalculator instance
    """
    return RTACalculator(adherence_threshold, variance_threshold)


if __name__ == "__main__":
    # Example usage
    print("=== RTA Calculator ===")

    # Create sample data
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    agents = [f"Agent_{i}" for i in range(1, 11)]

    # Generate schedule data
    schedule_data = []
    for date in dates:
        for agent in agents:
            scheduled_hours = np.random.uniform(6, 10)
            schedule_data.append(
                {"agent_id": agent, "date": date, "scheduled_hours": scheduled_hours}
            )

    schedule_df = pd.DataFrame(schedule_data)

    # Generate actual data (with some variance)
    actual_data = []
    for _, row in schedule_df.iterrows():
        # Add some variance to scheduled hours
        variance = np.random.normal(0, 1)
        actual_hours = max(0, row["scheduled_hours"] + variance)

        actual_data.append(
            {
                "agent_id": row["agent_id"],
                "date": row["date"],
                "actual_hours": actual_hours,
            }
        )

    actual_df = pd.DataFrame(actual_data)

    # Create RTA calculator
    calculator = create_rta_calculator()

    # Perform analysis
    print("Performing RTA analysis...")
    result = calculator.analyze(schedule_df, actual_df)

    print("\n=== RTA Analysis Results ===")
    print(
        f"Overall Adherence: {result.adherence_metrics.get('overall_adherence', 0):.1f}%"
    )
    print(f"Schedule Balance: {result.schedule_metrics.get('schedule_balance', 0):.2f}")
    print(
        f"Efficiency Score: {result.performance_metrics.get('efficiency_metrics', {}).get('efficiency_score', 0):.1f}%"
    )
    print(
        f"Variance Hours: {result.variance_analysis.get('variance_stats', {}).get('total_variance_hours', 0):.1f}"
    )
    print(f"Confidence Score: {result.confidence_score:.2f}")

    print("\n=== Optimization Recommendations ===")
    for i, recommendation in enumerate(result.optimization_recommendations, 1):
        print(f"{i}. {recommendation}")
