"""
Dashboard Feed for CX Churn Sentinel

Shapes the outputs of :mod:`risk_scorer` and :mod:`kpi_aggregator` into the
canonical payload consumed by the unified Streamlit dashboard's CX section.

Key Features:
- Builds the dashboard payload from a ``RiskScoringResult`` (+ optional
  ``KPIAggregator`` report) without re-running any computation
- Provides ``to_json()`` / ``to_dict()`` for direct ingestion over the Flask API
- Health/summary endpoint helpers (``/api/engines`` style)
- Local-first caching of the last payload to ``reports/cx_feed_<ts>.json``

Design notes:
- This is a *shaping* layer only — it reads the result objects' attributes and
  serializes them. It performs no scoring or aggregation of its own.
- The schema is stable and documented inline so the dashboard can rely on it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REPORT_DIR = Path("reports")


class DashboardFeed:
    """Build the CX dashboard payload from engine results."""

    def __init__(self, report_dir: str | None = None):
        self.report_dir = Path(report_dir) if report_dir else DEFAULT_REPORT_DIR
        self._last_payload: dict[str, Any] | None = None

    # ------------------------------------------------------------------ #
    # Payload construction
    # ------------------------------------------------------------------ #
    def build(
        self,
        risk_result: Any,
        kpi_report: dict[str, Any] | None = None,
        source: str = "cx_churn_sentinel",
    ) -> dict[str, Any]:
        """
        Build the canonical dashboard payload.

        Args:
            risk_result: ``RiskScoringResult`` from :mod:`risk_scorer`.
            kpi_report: optional output of ``KPIAggregator.generate_kpi_report``.
            source: engine identifier shown in the dashboard header.

        Returns:
            Payload dict with the stable schema documented below.
        """
        risk_distribution = getattr(risk_result, "risk_distribution", {}) or {}
        total = sum(int(v) for v in risk_distribution.values()) or 1

        payload: dict[str, Any] = {
            "engine": source,
            "generated_at": datetime.now().isoformat(),
            "status": "active",
            "summary": {
                "total_customers": len(
                    getattr(risk_result, "customer_risks", []) or []
                ),
                "overall_risk_score": round(
                    float(getattr(risk_result, "overall_risk_score", 0.0)), 3
                ),
                "high_risk_customers": len(
                    getattr(risk_result, "high_risk_customers", []) or []
                ),
                "risk_coverage": 1.0
                if getattr(risk_result, "customer_risks", None)
                else 0.0,
            },
            "risk_distribution": {
                level: {
                    "count": int(count),
                    "percentage": round(int(count) / total * 100, 1),
                }
                for level, count in risk_distribution.items()
            },
            "trend_analysis": getattr(risk_result, "trend_analysis", {}) or {},
            "recommendations": getattr(risk_result, "recommendations", []) or [],
            "kpi_quality": None,
            "high_risk_customers": self._trim_high_risk(risk_result),
        }

        if kpi_report:
            payload["kpi_quality"] = {
                "overall_quality_score": round(
                    float(
                        kpi_report.get("quality_report", {}).get(
                            "overall_quality_score", 0.0
                        )
                    ),
                    3,
                ),
                "quality_pass": bool(
                    kpi_report.get("quality_report", {}).get("quality_pass", False)
                ),
                "insights": kpi_report.get("insights", []),
            }
            payload["weighted_scores"] = kpi_report.get("aggregated_scores", {}).get(
                "weighted_scores", {}
            )

        self._last_payload = payload
        return payload

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def to_json(
        self,
        risk_result: Any,
        kpi_report: dict[str, Any] | None = None,
        indent: int = 2,
    ) -> str:
        """Return the payload as a JSON string."""
        return json.dumps(
            self.build(risk_result, kpi_report), indent=indent, default=str
        )

    def to_dict(self) -> dict[str, Any] | None:
        """Return the most recently built payload (or ``None``)."""
        return self._last_payload

    def write(
        self,
        risk_result: Any,
        kpi_report: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> Path:
        """Build the payload and persist it under ``reports/``."""
        payload = self.build(risk_result, kpi_report)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.report_dir / f"cx_feed_{name or stamp}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("CX dashboard feed written to %s", path)
        return path

    # ------------------------------------------------------------------ #
    # Lightweight summary (for `/api/engines` style endpoints)
    # ------------------------------------------------------------------ #
    def status_summary(self, risk_result: Any) -> dict[str, Any]:
        """Minimal status block suitable for the unified engines endpoint."""
        return {
            "engine": "cx_churn_sentinel",
            "status": "active",
            "overall_risk_score": round(
                float(getattr(risk_result, "overall_risk_score", 0.0)), 3
            ),
            "high_risk_count": len(
                getattr(risk_result, "high_risk_customers", []) or []
            ),
            "generated_at": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _trim_high_risk(risk_result: Any, limit: int = 50) -> list:
        """Return a trimmed view of high-risk customers for the dashboard."""
        high_risk = getattr(risk_result, "high_risk_customers", []) or []
        trimmed = []
        for item in high_risk[:limit]:
            trimmed.append(
                {
                    "customer_id": item.get("customer_id"),
                    "risk_level": item.get("risk_level"),
                    "weighted_score": round(
                        float(item.get("kpi_analysis", {}).get("weighted_score", 0.0)),
                        3,
                    ),
                    "risk_factors": item.get("risk_factors", []),
                }
            )
        return trimmed


def create_dashboard_feed(report_dir: str | None = None) -> DashboardFeed:
    """Factory for :class:`DashboardFeed`."""
    return DashboardFeed(report_dir=report_dir)


if __name__ == "__main__":
    print("=== CX Churn Sentinel — Dashboard Feed ===")
    feed = create_dashboard_feed()

    class _MockResult:
        customer_risks = [
            {
                "customer_id": "CUST_001",
                "risk_level": "high",
                "kpi_analysis": {"weighted_score": 0.72},
                "risk_factors": ["Low CSAT"],
                "recommendations": [],
            }
        ]
        overall_risk_score = 0.72
        risk_distribution = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        high_risk_customers = customer_risks
        trend_analysis = {"risk_trend": "stable"}
        recommendations = ["Monitor closely."]

    payload = feed.build(_MockResult())
    print(json.dumps(payload["summary"], indent=2))
    print("Risk distribution:", payload["risk_distribution"])
    print("Status summary:", feed.status_summary(_MockResult()))
