"""
KPI Aggregator for CX Churn Sentinel

This module handles KPI aggregation, normalization, and decay for the CX Churn Sentinel.
It processes customer interaction data and generates weighted KPI scores.

Key Features:
- KPI normalization and decay
- Multi-period aggregation
- Quality assurance checks
- Weighted scoring
- Anomaly detection
"""

import logging
import warnings
from datetime import datetime
from typing import Any

import numpy as np
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KPIAggregator:
    """
    KPI aggregator for CX Churn Sentinel with normalization and decay.
    """

    def __init__(self, decay_factor: float = 0.9, quality_threshold: float = 0.8):
        self.decay_factor = decay_factor
        self.quality_threshold = quality_threshold
        self.scaler = StandardScaler()

    def normalize_kpi_values(self, kpi_data: dict[str, list[float]]) -> dict[str, Any]:
        """
        Normalize KPI values across time periods.

        Args:
            kpi_data: Dictionary with KPI time series data

        Returns:
            Dictionary with normalized KPI values
        """
        normalized_data = {}

        for kpi, values in kpi_data.items():
            if not values:
                continue

            # Convert to numpy array
            values_array = np.array(values)

            # Handle different KPI types
            if kpi == "aht":
                # Lower AHT is better (inverse normalization)
                normalized = 1 - (values_array / np.max(values_array))
            else:
                # Higher KPI is better (direct normalization)
                normalized = values_array / np.max(values_array)

            normalized_data[kpi] = {
                "original_values": values,
                "normalized_values": normalized.tolist(),
                "mean": float(np.mean(normalized)),
                "std": float(np.std(normalized)),
                "min": float(np.min(normalized)),
                "max": float(np.max(normalized)),
            }

        return normalized_data

    def apply_decay(
        self, time_series_data: dict[str, list[float]]
    ) -> dict[str, list[float]]:
        """
        Apply exponential decay to time series data.

        Args:
            time_series_data: Dictionary with time series data

        Returns:
            Dictionary with decayed values
        """
        decayed_data = {}

        for kpi, values in time_series_data.items():
            if len(values) < 2:
                decayed_data[kpi] = values
                continue

            # Apply exponential decay
            decayed_values = []
            for i, value in enumerate(values):
                weight = self.decay_factor ** (len(values) - i - 1)
                decayed_values.append(value * weight)

            decayed_data[kpi] = decayed_values

        return decayed_data

    def aggregate_kpi_scores(
        self, kpi_data: dict[str, list[float]], weights: dict[str, float]
    ) -> dict[str, Any]:
        """
        Aggregate KPI scores with weights.

        Args:
            kpi_data: Dictionary with KPI time series data
            weights: Dictionary with KPI weights

        Returns:
            Dictionary with aggregated scores
        """
        # Normalize data
        normalized_data = self.normalize_kpi_values(kpi_data)

        # Apply decay
        decayed_data = self.apply_decay(kpi_data)

        # Calculate weighted scores
        weighted_scores = {}
        for kpi, weight in weights.items():
            if kpi in decayed_data:
                # Use the most recent value
                latest_value = decayed_data[kpi][-1]
                weighted_scores[kpi] = latest_value * weight

        # Calculate total score
        total_score = sum(weighted_scores.values())

        return {
            "weighted_scores": weighted_scores,
            "total_score": total_score,
            "normalized_data": normalized_data,
            "decayed_data": decayed_data,
        }

    def calculate_quality_score(
        self, kpi_data: dict[str, list[float]]
    ) -> dict[str, Any]:
        """
        Calculate data quality score.

        Args:
            kpi_data: Dictionary with KPI time series data

        Returns:
            Dictionary with quality scores
        """
        quality_metrics = {}

        for kpi, values in kpi_data.items():
            if not values:
                quality_metrics[kpi] = {"score": 0, "issues": ["no_data"]}
                continue

            # Calculate completeness score
            completeness_score = 1.0  # Assume data is complete

            # Calculate consistency score
            if len(values) > 1:
                cv = np.std(values) / np.mean(values) if np.mean(values) > 0 else 0
                consistency_score = max(0, 1 - min(cv, 1))
            else:
                consistency_score = 0.0

            # Calculate accuracy score (simplified)
            accuracy_score = 1.0  # Assume data is accurate

            # Calculate overall quality score
            overall_score = (
                completeness_score + consistency_score + accuracy_score
            ) / 3

            quality_metrics[kpi] = {
                "completeness_score": completeness_score,
                "consistency_score": consistency_score,
                "accuracy_score": accuracy_score,
                "overall_score": overall_score,
                "data_points": len(values),
                "issues": self._identify_quality_issues(values),
            }

        # Calculate overall quality score
        overall_quality = np.mean(
            [m["overall_score"] for m in quality_metrics.values()]
        )

        return {
            "quality_metrics": quality_metrics,
            "overall_quality_score": overall_quality,
            "quality_pass": overall_quality >= self.quality_threshold,
        }

    def _identify_quality_issues(self, values: list[float]) -> list[str]:
        """
        Identify quality issues in data.

        Args:
            values: List of values

        Returns:
            List of quality issues
        """
        issues = []

        if not values:
            issues.append("no_data")
            return issues

        # Check for outliers
        if len(values) > 1:
            q1 = np.percentile(values, 25)
            q3 = np.percentile(values, 75)
            iqr = q3 - q1

            outliers = values[(values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)]
            if len(outliers) > 0:
                issues.append(f"contains_{len(outliers)}_outliers")

        # Check for missing values
        if any(np.isnan(v) for v in values):
            issues.append("contains_missing_values")

        # Check for extreme values
        if len(values) > 0:
            mean_val = np.mean(values)
            std_val = np.std(values)
            if std_val > 0:
                z_scores = np.abs((values - mean_val) / std_val)
                extreme_values = values[z_scores > 3]
                if len(extreme_values) > 0:
                    issues.append(f"contains_{len(extreme_values)}_extreme_values")

        return issues

    def generate_kpi_report(
        self, kpi_data: dict[str, list[float]], weights: dict[str, float]
    ) -> dict[str, Any]:
        """
        Generate comprehensive KPI report.

        Args:
            kpi_data: Dictionary with KPI time series data
            weights: Dictionary with KPI weights

        Returns:
            Dictionary with KPI report
        """
        # Aggregate KPI scores
        aggregated = self.aggregate_kpi_scores(kpi_data, weights)

        # Calculate quality scores
        quality_report = self.calculate_quality_score(kpi_data)

        # Generate insights
        insights = self._generate_kpi_insights(aggregated, quality_report)

        return {
            "aggregated_scores": aggregated,
            "quality_report": quality_report,
            "insights": insights,
            "report_timestamp": datetime.now().isoformat(),
        }

    def _generate_kpi_insights(
        self, aggregated: dict[str, Any], quality_report: dict[str, Any]
    ) -> list[str]:
        """
        Generate insights from KPI data.

        Args:
            aggregated: Aggregated KPI scores
            quality_report: Quality report

        Returns:
            List of insights
        """
        insights = []

        # Insight based on overall quality
        if quality_report["overall_quality_score"] < 0.8:
            insights.append(
                "Data quality is below threshold. Consider improving data collection processes."
            )

        # Insight based on weighted scores
        if aggregated["total_score"] > 0.8:
            insights.append(
                "Overall KPI performance is excellent. Maintain current service levels."
            )
        elif aggregated["total_score"] < 0.5:
            insights.append(
                "Overall KPI performance is poor. Immediate action required to improve service quality."
            )

        # Insight based on individual KPIs
        for kpi, score in aggregated["weighted_scores"].items():
            if score > 0.8:
                insights.append(f"{kpi.upper()} performance is excellent.")
            elif score < 0.4:
                insights.append(f"{kpi.upper()} performance needs improvement.")

        # Default insight if no specific issues found
        if not insights:
            insights.append(
                "KPI performance is within acceptable ranges. Continue monitoring and preventive measures."
            )

        return insights


def create_kpi_aggregator(
    decay_factor: float = 0.9, quality_threshold: float = 0.8
) -> KPIAggregator:
    """
    Factory function to create KPI aggregator.

    Args:
        decay_factor: Exponential decay factor
        quality_threshold: Minimum quality threshold

    Returns:
        KPIAggregator instance
    """
    return KPIAggregator(decay_factor, quality_threshold)


if __name__ == "__main__":
    # Example usage
    print("=== KPI Aggregator ===")

    # Create KPI aggregator
    aggregator = create_kpi_aggregator()

    # Create sample KPI data
    sample_kpi_data = {
        "csat": [0.8, 0.85, 0.9, 0.75, 0.88],
        "sla": [0.9, 0.92, 0.88, 0.95, 0.91],
        "fcr": [0.85, 0.87, 0.83, 0.89, 0.86],
        "aht": [0.3, 0.25, 0.35, 0.2, 0.4],
    }

    # Create sample weights
    sample_weights = {"csat": 0.3, "sla": 0.3, "fcr": 0.2, "aht": 0.2}

    # Generate KPI report
    print("Generating KPI report...")
    report = aggregator.generate_kpi_report(sample_kpi_data, sample_weights)

    print("\n=== KPI Aggregator Results ===")
    print(
        f"Overall quality score: {report['quality_report']['overall_quality_score']:.2f}"
    )
    print(f"Quality pass: {report['quality_report']['quality_pass']}")
    print(f"Total weighted score: {report['aggregated_scores']['total_score']:.2f}")

    print("\n=== Weighted Scores ===")
    for kpi, score in report["aggregated_scores"]["weighted_scores"].items():
        print(f"{kpi}: {score:.2f}")

    print("\n=== Insights ===")
    for i, insight in enumerate(report["insights"], 1):
        print(f"{i}. {insight}")
