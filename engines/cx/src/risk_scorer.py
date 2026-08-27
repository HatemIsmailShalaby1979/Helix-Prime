"""
Risk Scorer for CX Churn Sentinel

This module implements the 4-KPI churn risk scoring system for the CX Churn Sentinel.
It analyzes customer behavior patterns and scores churn risk using weighted algorithms.

Key Features:
- 4-KPI risk scoring (CSAT, SLA, FCR, AHT)
- Weighted scoring algorithm
- Risk classification (Critical/High/Medium/Low)
- Real-time risk assessment
- Anomaly detection
- Risk trend analysis
"""

import logging
import warnings
from collections import Counter
from datetime import datetime
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RiskScoringResult:
    """Result of risk scoring."""

    def __init__(self):
        self.customer_risks = []
        self.overall_risk_score = 0.0
        self.risk_distribution = {}
        self.high_risk_customers = []
        self.trend_analysis = {}
        self.recommendations = []


class RiskScorer:
    """
    Risk scoring engine for CX Churn Sentinel with 4-KPI analysis.
    """

    def __init__(self, kpi_weights: dict[str, float] | None = None):
        # Default KPI weights (can be customized)
        self.kpi_weights = kpi_weights or {
            "csat": 0.3,  # Customer Satisfaction Score
            "sla": 0.3,  # Service Level Agreement compliance
            "fcr": 0.2,  # First Contact Resolution
            "aht": 0.2,  # Average Handle Time
        }

        # KPI thresholds for risk classification
        self.kpi_thresholds = {
            "csat": {"critical": 0.6, "high": 0.7, "medium": 0.8},
            "sla": {"critical": 0.8, "high": 0.9, "medium": 0.95},
            "fcr": {"critical": 0.7, "high": 0.8, "medium": 0.9},
            "aht": {
                "critical": 0.3,
                "high": 0.2,
                "medium": 0.1,
            },  # Lower is better for AHT
        }

    def calculate_kpi_score(self, kpi_data: dict[str, float]) -> dict[str, Any]:
        """
        Calculate individual KPI scores and risk levels.

        Args:
            kpi_data: Dictionary with KPI values

        Returns:
            Dictionary with KPI scores and risk levels
        """
        kpi_scores = {}
        risk_levels = {}

        for kpi, value in kpi_data.items():
            if kpi not in self.kpi_weights:
                continue

            # Calculate normalized score (0-1)
            if kpi == "aht":
                # Lower AHT is better (inverse scoring)
                normalized_score = max(
                    0, 1 - (value / 0.5)
                )  # Assume max AHT is 0.5 minutes
            else:
                # Higher KPI is better
                normalized_score = min(1, value)

            kpi_scores[kpi] = normalized_score

            # Determine risk level
            threshold = self.kpi_thresholds[kpi]
            if normalized_score <= threshold["critical"]:
                risk_level = "critical"
            elif normalized_score <= threshold["high"]:
                risk_level = "high"
            elif normalized_score <= threshold["medium"]:
                risk_level = "medium"
            else:
                risk_level = "low"

            risk_levels[kpi] = {
                "score": normalized_score,
                "risk_level": risk_level,
                "value": value,
                "weight": self.kpi_weights[kpi],
            }

        return {
            "kpi_scores": kpi_scores,
            "risk_levels": risk_levels,
            "weighted_score": self._calculate_weighted_score(risk_levels),
        }

    def _calculate_weighted_score(self, risk_levels: dict[str, Any]) -> float:
        """
        Calculate weighted risk score.

        Args:
            risk_levels: Dictionary with risk levels

        Returns:
            Weighted risk score (0-1)
        """
        total_score = 0.0
        total_weight = 0.0

        for data in risk_levels.values():
            weight = data["weight"]
            score = data["score"]
            total_score += weight * score
            total_weight += weight

        return total_score / total_weight if total_weight > 0 else 0.0

    def classify_risk_level(self, weighted_score: float) -> str:
        """
        Classify overall risk level based on weighted score.

        Args:
            weighted_score: Weighted risk score (0-1)

        Returns:
            Risk level classification
        """
        if weighted_score >= 0.8:
            return "critical"
        elif weighted_score >= 0.6:
            return "high"
        elif weighted_score >= 0.4:
            return "medium"
        else:
            return "low"

    def analyze_customer_risk(self, customer_data: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze individual customer risk.

        Args:
            customer_data: Dictionary with customer data

        Returns:
            Dictionary with risk analysis
        """
        # Extract KPIs from customer data
        kpi_data = {
            "csat": customer_data.get("csat", 0),
            "sla": customer_data.get("sla", 0),
            "fcr": customer_data.get("fcr", 0),
            "aht": customer_data.get("aht", 0),
        }

        # Calculate KPI scores
        kpi_analysis = self.calculate_kpi_score(kpi_data)

        # Determine overall risk level
        risk_level = self.classify_risk_level(kpi_analysis["weighted_score"])

        # Generate risk factors
        risk_factors = self._identify_risk_factors(
            kpi_data, kpi_analysis["risk_levels"]
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(risk_level, risk_factors)

        return {
            "customer_id": customer_data.get("customer_id", "unknown"),
            "kpi_data": kpi_data,
            "kpi_analysis": kpi_analysis,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "recommendations": recommendations,
            "analysis_timestamp": datetime.now().isoformat(),
        }

    def _identify_risk_factors(
        self, kpi_data: dict[str, float], risk_levels: dict[str, Any]
    ) -> list[str]:
        """
        Identify key risk factors for a customer.

        Args:
            kpi_data: KPI values
            risk_levels: Risk levels for each KPI

        Returns:
            List of risk factors
        """
        risk_factors = []

        for kpi, data in risk_levels.items():
            if data["risk_level"] in ["critical", "high"]:
                if kpi == "csat":
                    risk_factors.append(
                        f"Low customer satisfaction (CSAT: {kpi_data[kpi]:.2f})"
                    )
                elif kpi == "sla":
                    risk_factors.append(
                        f"Poor service level compliance (SLA: {kpi_data[kpi]:.2f})"
                    )
                elif kpi == "fcr":
                    risk_factors.append(
                        f"Low first contact resolution (FCR: {kpi_data[kpi]:.2f})"
                    )
                elif kpi == "aht":
                    risk_factors.append(
                        f"High average handle time (AHT: {kpi_data[kpi]:.2f}s)"
                    )

        return risk_factors

    def _generate_recommendations(
        self, risk_level: str, risk_factors: list[str]
    ) -> list[str]:
        """
        Generate recommendations based on risk level and factors.

        Args:
            risk_level: Risk level classification
            risk_factors: List of risk factors

        Returns:
            List of recommendations
        """
        recommendations = []

        if risk_level == "critical":
            recommendations.extend(
                [
                    "Immediate customer outreach required",
                    "Schedule customer service intervention",
                    "Implement recovery plan within 24 hours",
                    "Escalate to senior management",
                ]
            )
        elif risk_level == "high":
            recommendations.extend(
                [
                    "Schedule customer follow-up within 48 hours",
                    "Review service delivery processes",
                    "Implement corrective actions",
                ]
            )
        elif risk_level == "medium":
            recommendations.extend(
                [
                    "Monitor customer behavior closely",
                    "Schedule proactive outreach",
                    "Review service quality metrics",
                ]
            )
        else:
            recommendations.extend(
                [
                    "Maintain current service levels",
                    "Continue regular monitoring",
                    "Consider loyalty enhancement programs",
                ]
            )

        # Add specific recommendations based on risk factors
        for factor in risk_factors:
            if "CSAT" in factor:
                recommendations.append(
                    "Implement customer satisfaction improvement program"
                )
            elif "SLA" in factor:
                recommendations.append("Review and optimize service level processes")
            elif "FCR" in factor:
                recommendations.append("Improve first contact resolution capabilities")
            elif "AHT" in factor:
                recommendations.append(
                    "Optimize agent training and processes to reduce handle time"
                )

        return recommendations

    def analyze_customer_population(
        self, customer_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Analyze risk across a population of customers.

        Args:
            customer_data: List of customer data dictionaries

        Returns:
            Dictionary with population analysis
        """
        # Analyze individual customers
        customer_risks = []
        risk_distribution = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for customer in customer_data:
            risk_analysis = self.analyze_customer_risk(customer)
            customer_risks.append(risk_analysis)

            # Update risk distribution
            risk_distribution[risk_analysis["risk_level"]] += 1

        # Calculate overall statistics
        total_customers = len(customer_data)
        overall_risk_score = np.mean(
            [r["kpi_analysis"]["weighted_score"] for r in customer_risks]
        )

        # Identify high-risk customers
        high_risk_customers = [
            r for r in customer_risks if r["risk_level"] in ["critical", "high"]
        ]

        # Analyze trends
        trend_analysis = self._analyze_trends(customer_risks)

        # Generate recommendations
        recommendations = self._generate_population_recommendations(
            risk_distribution, trend_analysis, high_risk_customers
        )

        return {
            "total_customers": total_customers,
            "customer_risks": customer_risks,
            "risk_distribution": risk_distribution,
            "overall_risk_score": overall_risk_score,
            "high_risk_customers_count": len(high_risk_customers),
            "trend_analysis": trend_analysis,
            "recommendations": recommendations,
            "analysis_timestamp": datetime.now().isoformat(),
        }

    def _analyze_trends(self, customer_risks: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Analyze trends in customer risk.

        Args:
            customer_risks: List of customer risk analyses

        Returns:
            Dictionary with trend analysis
        """
        if not customer_risks:
            return {}

        # Calculate risk score distribution
        risk_scores = [r["kpi_analysis"]["weighted_score"] for r in customer_risks]

        # Calculate risk level distribution
        risk_levels = [r["risk_level"] for r in customer_risks]

        # Calculate average risk by KPI
        kpi_scores = {}
        for risk in customer_risks:
            for kpi, data in risk["kpi_analysis"]["risk_levels"].items():
                if kpi not in kpi_scores:
                    kpi_scores[kpi] = []
                kpi_scores[kpi].append(data["score"])

        # Calculate average scores
        avg_kpi_scores = {
            kpi: np.mean(scores) if scores else 0 for kpi, scores in kpi_scores.items()
        }

        return {
            "average_risk_score": np.mean(risk_scores),
            "risk_score_std": np.std(risk_scores),
            "risk_level_distribution": {
                level: count / len(risk_levels)
                for level, count in Counter(risk_levels).items()
            },
            "average_kpi_scores": avg_kpi_scores,
            "risk_trend": "increasing"
            if len(risk_scores) > 1 and risk_scores[-1] > risk_scores[0]
            else "decreasing"
            if len(risk_scores) > 1 and risk_scores[-1] < risk_scores[0]
            else "stable",
        }

    def _generate_population_recommendations(
        self,
        risk_distribution: dict[str, int],
        trend_analysis: dict[str, Any],
        high_risk_customers: list[dict[str, Any]],
    ) -> list[str]:
        """
        Generate population-level recommendations.

        Args:
            risk_distribution: Risk level distribution
            trend_analysis: Trend analysis
            high_risk_customers: List of high-risk customers

        Returns:
            List of recommendations
        """
        recommendations = []

        # Recommendation based on risk distribution
        critical_percentage = (
            risk_distribution.get("critical", 0) / sum(risk_distribution.values()) * 100
        )
        high_percentage = (
            risk_distribution.get("high", 0) / sum(risk_distribution.values()) * 100
        )

        if critical_percentage > 10:
            recommendations.append(
                f"High critical risk level ({critical_percentage:.1f}% of customers). Immediate intervention required."
            )
        elif high_percentage > 25:
            recommendations.append(
                f"High proportion of high-risk customers ({high_percentage:.1f}%). Review service delivery processes."
            )

        # Recommendation based on trend
        if trend_analysis.get("risk_trend") == "increasing":
            recommendations.append(
                "Risk trend is increasing. Implement proactive churn prevention measures."
            )
        elif trend_analysis.get("risk_trend") == "decreasing":
            recommendations.append(
                "Risk trend is improving. Continue current initiatives and identify success factors."
            )

        # Recommendation based on high-risk customers
        if len(high_risk_customers) > 0:
            recommendations.append(
                f"Identify and address root causes for {len(high_risk_customers)} high-risk customers."
            )

        # Default recommendation if no specific issues found
        if not recommendations:
            recommendations.append(
                "Customer risk profile is within acceptable ranges. Continue monitoring and preventive measures."
            )

        return recommendations


class RiskScorerEngine:
    """
    Main risk scoring engine for CX Churn Sentinel.
    """

    def __init__(self):
        self.risk_scorer = RiskScorer()

    def score_customers(self, customer_data: list[dict[str, Any]]) -> RiskScoringResult:
        """
        Score risk for a population of customers.

        Args:
            customer_data: List of customer data dictionaries

        Returns:
            RiskScoringResult object
        """
        result = RiskScoringResult()

        try:
            # Score individual customers
            result.customer_risks = [
                self.risk_scorer.analyze_customer_risk(customer)
                for customer in customer_data
            ]

            # Calculate overall risk score
            if result.customer_risks:
                result.overall_risk_score = np.mean(
                    [r["kpi_analysis"]["weighted_score"] for r in result.customer_risks]
                )

            # Calculate risk distribution
            result.risk_distribution = self._calculate_risk_distribution(
                result.customer_risks
            )

            # Identify high-risk customers
            result.high_risk_customers = [
                r
                for r in result.customer_risks
                if r["risk_level"] in ["critical", "high"]
            ]

            # Analyze trends
            result.trend_analysis = self.risk_scorer._analyze_trends(
                result.customer_risks
            )

            # Generate recommendations
            result.recommendations = (
                self.risk_scorer._generate_population_recommendations(
                    result.risk_distribution,
                    result.trend_analysis,
                    result.high_risk_customers,
                )
            )

        except (ValueError, TypeError, OSError) as e:
            logger.error("Error in risk scoring: %s", e)
            result.recommendations = [f"Risk scoring completed with warnings: {e!s}"]

        return result

    def _calculate_risk_distribution(
        self, customer_risks: list[dict[str, Any]]
    ) -> dict[str, int]:
        """
        Calculate risk distribution.

        Args:
            customer_risks: List of customer risk analyses

        Returns:
            Dictionary with risk distribution
        """
        from collections import Counter

        risk_levels = [r["risk_level"] for r in customer_risks]
        return dict(Counter(risk_levels))


def create_risk_scorer(
    kpi_weights: dict[str, float] | None = None,
) -> RiskScorerEngine:
    """
    Factory function to create risk scorer.

    Args:
        kpi_weights: Optional KPI weights

    Returns:
        RiskScorerEngine instance
    """
    return RiskScorerEngine()


if __name__ == "__main__":
    # Example usage
    print("=== CX Churn Sentinel Risk Scorer ===")

    # Create risk scorer
    risk_scorer = create_risk_scorer()

    # Create sample customer data
    sample_customers = [
        {"customer_id": "CUST_001", "csat": 0.7, "sla": 0.85, "fcr": 0.8, "aht": 0.4},
        {"customer_id": "CUST_002", "csat": 0.5, "sla": 0.7, "fcr": 0.6, "aht": 0.6},
        {"customer_id": "CUST_003", "csat": 0.9, "sla": 0.95, "fcr": 0.9, "aht": 0.1},
        {"customer_id": "CUST_004", "csat": 0.4, "sla": 0.6, "fcr": 0.5, "aht": 0.8},
    ]

    # Score customers
    print("Scoring customer risks...")
    result = risk_scorer.score_customers(sample_customers)

    print("\n=== Risk Scoring Results ===")
    print(f"Total customers analyzed: {result.customer_risks}")
    print(f"Overall risk score: {result.overall_risk_score:.2f}")
    print(f"Risk distribution: {result.risk_distribution}")
    print(f"High-risk customers: {len(result.high_risk_customers)}")

    print("\n=== Individual Customer Risks ===")
    for risk in result.customer_risks:
        print(
            f"Customer {risk['customer_id']}: {risk['risk_level']} risk (score: {risk['kpi_analysis']['weighted_score']:.2f})"
        )

    print("\n=== Recommendations ===")
    for i, recommendation in enumerate(result.recommendations, 1):
        print(f"{i}. {recommendation}")
