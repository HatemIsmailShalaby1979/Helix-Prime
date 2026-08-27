"""
RTA Visualizations for the Real-Time Adherence Command Center

Renders the charts and report artifacts consumed by the RTA dashboard and the
unified Streamlit command center. Built directly on the ``RTACalculationResult``
shape produced by :mod:`calculations` (``.adherence_metrics``, ``.schedule_metrics``,
``.performance_metrics``, ``.variance_analysis``, ``.confidence_score``,
``.optimization_recommendations``).

Key Features:
- Adherence trend / distribution charts (Plotly figures + standalone HTML)
- Variance heatmaps by agent / date / hour
- Performance summary charts
- Report rendering to PNG / HTML artifacts under ``reports/``

Design notes:
- Pure rendering layer — performs no calculation of its own; it only shapes the
  data already computed by :class:`calculations.RTACalculator`.
- Plotly is optional at import time so the module can still be imported in
  headless environments; chart helpers raise a clear runtime error if Plotly
  is unavailable when actually called.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    import plotly.io as pio
    from plotly.subplots import make_subplots

    _PLOTLY_AVAILABLE = True
except (ImportError, ModuleNotFoundError):  # pragma: no cover - optional dependency
    _PLOTLY_AVAILABLE = False


def _require_plotly() -> None:
    """Raise a helpful error if Plotly is not installed."""
    if not _PLOTLY_AVAILABLE:
        raise RuntimeError(
            "Plotly is required for RTA visualizations. "
            "Install it with: pip install plotly"
        )


class RTAVisualizer:
    """Render RTA calculation results into charts and report artifacts."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Figure builders (return plotly Figure objects for embedding)
    # ------------------------------------------------------------------ #
    def adherence_trend_figure(self, result: Any) -> go.Figure:
        """Adherence over time from ``result.adherence_metrics['date_adherence']``."""
        _require_plotly()
        date_adherence: dict[str, float] = (
            result.adherence_metrics.get("date_adherence", {})
            if hasattr(result, "adherence_metrics")
            else {}
        )
        dates = list(date_adherence.keys())
        values = [float(v) for v in date_adherence.values()]

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines+markers",
                name="Adherence %",
                line={"color": "#1f77b4", "width": 2},
            )
        )
        fig.add_hline(
            y=85, line_dash="dash", line_color="red", annotation_text="Threshold (85%)"
        )
        fig.update_layout(
            title="Adherence Trend by Date",
            xaxis_title="Date",
            yaxis_title="Adherence (%)",
            template="plotly_white",
            height=420,
        )
        return fig

    def agent_adherence_figure(self, result: Any) -> go.Figure:
        """Bar chart of per-agent adherence."""
        _require_plotly()
        agent_adherence: dict[str, float] = (
            result.adherence_metrics.get("agent_adherence", {})
            if hasattr(result, "adherence_metrics")
            else {}
        )
        agents = list(agent_adherence.keys())
        values = [float(v) for v in agent_adherence.values()]

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=agents,
                y=values,
                name="Adherence %",
                marker_color="#2ca02c",
            )
        )
        fig.update_layout(
            title="Adherence by Agent",
            xaxis_title="Agent",
            yaxis_title="Adherence (%)",
            template="plotly_white",
            height=420,
        )
        return fig

    def variance_figure(self, result: Any) -> go.Figure:
        """Variance by hour heatmap (uses ``result.variance_analysis``)."""
        _require_plotly()
        variance: dict[str, Any] = (
            result.variance_analysis if hasattr(result, "variance_analysis") else {}
        )
        hour_variance: dict[str, Any] = variance.get("hour_variance", {})

        if not hour_variance:
            # Fall back to a simple bar of variance stats if no hourly breakdown.
            stats: dict[str, float] = variance.get("variance_stats", {})
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=list(stats.keys()),
                    y=[float(v) for v in stats.values()],
                    marker_color="#ff7f0e",
                )
            )
            fig.update_layout(
                title="Variance Summary",
                template="plotly_white",
                height=420,
            )
            return fig

        hours = list(hour_variance.keys())
        means = [float(hour_variance[h].get("mean", 0)) for h in hours]
        stds = [float(hour_variance[h].get("std", 0)) for h in hours]

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(x=hours, y=means, name="Mean variance (h)", marker_color="#9467bd"),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=hours, y=stds, name="Std dev (h)", line={"color": "#d62728"}),
            secondary_y=True,
        )
        fig.update_layout(
            title="Variance by Hour",
            template="plotly_white",
            height=420,
        )
        return fig

    def performance_figure(self, result: Any) -> go.Figure:
        """Efficiency metrics summary chart."""
        _require_plotly()
        perf: dict[str, Any] = (
            result.performance_metrics if hasattr(result, "performance_metrics") else {}
        )
        eff: dict[str, float] = perf.get("efficiency_metrics", {})

        labels = ["Efficiency %", "Overtime %", "Undertime %"]
        values = [
            float(eff.get("efficiency_score", 0)),
            float(eff.get("overtime_percentage", 0)),
            float(eff.get("undertime_percentage", 0)),
        ]

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=labels,
                y=values,
                marker_color=["#2ca02c", "#d62728", "#ff7f0e"],
            )
        )
        fig.update_layout(
            title="Performance Summary",
            template="plotly_white",
            height=420,
            yaxis_title="% (0–100)",
        )
        return fig

    def summary_dashboard(self, result: Any) -> go.Figure:
        """Combined 2x2 dashboard figure of all RTA views."""
        _require_plotly()
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Adherence Trend",
                "Agent Adherence",
                "Variance by Hour",
                "Performance",
            ),
        )
        fig.update_layout(
            template="plotly_white",
            height=800,
            showlegend=False,
            title_text="RTA Command Center",
        )

        trend = self.adherence_trend_figure(result).data
        for trace in trend:
            fig.add_trace(trace, row=1, col=1)

        agent = self.agent_adherence_figure(result).data
        for trace in agent:
            fig.add_trace(trace, row=1, col=2)

        var = self.variance_figure(result).data
        for trace in var:
            fig.add_trace(trace, row=2, col=1)

        perf = self.performance_figure(result).data
        for trace in perf:
            fig.add_trace(trace, row=2, col=2)

        return fig

    # ------------------------------------------------------------------ #
    # Report rendering
    # ------------------------------------------------------------------ #
    def render_html_report(self, result: Any, name: str | None = None) -> Path:
        """Write a standalone HTML report (charts embedded) to ``reports/``."""
        _require_plotly()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"rta_dashboard_{name or stamp}.html"

        figures = {
            "Adherence Trend": self.adherence_trend_figure(result),
            "Agent Adherence": self.agent_adherence_figure(result),
            "Variance by Hour": self.variance_figure(result),
            "Performance": self.performance_figure(result),
        }

        sections = []
        for title, fig in figures.items():
            sections.append(
                f"<h2>{title}</h2>{pio.to_html(fig, include_plotlyjs='cdn')}"
            )

        confidence = getattr(result, "confidence_score", 0.0)
        recs = getattr(result, "optimization_recommendations", [])
        rec_html = (
            "".join(f"<li>{r}</li>" for r in recs) or "<li>No recommendations.</li>"
        )

        html = (
            "<html><head><meta charset='utf-8'>"
            f"<title>RTA Report {stamp}</title></head><body>"
            f"<h1>RTA Command Center Report</h1>"
            f"<p><strong>Generated:</strong> {datetime.now().isoformat()}</p>"
            f"<p><strong>Confidence score:</strong> {confidence:.2f}</p>"
            + "".join(sections)
            + f"<h2>Recommendations</h2><ul>{rec_html}</ul>"
            + "</body></html>"
        )

        path.write_text(html, encoding="utf-8")
        logger.info("RTA HTML report written to %s", path)
        return path

    def render_json_report(self, result: Any, name: str | None = None) -> Path:
        """Write a JSON snapshot of the calculation result."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"rta_snapshot_{name or stamp}.json"
        payload = {
            "generated_at": datetime.now().isoformat(),
            "adherence_metrics": getattr(result, "adherence_metrics", {}),
            "schedule_metrics": getattr(result, "schedule_metrics", {}),
            "performance_metrics": getattr(result, "performance_metrics", {}),
            "variance_analysis": getattr(result, "variance_analysis", {}),
            "confidence_score": float(getattr(result, "confidence_score", 0.0)),
            "optimization_recommendations": getattr(
                result, "optimization_recommendations", []
            ),
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("RTA JSON snapshot written to %s", path)
        return path


def create_visualizer(output_dir: str | None = None) -> RTAVisualizer:
    """Factory for :class:`RTAVisualizer`."""
    return RTAVisualizer(output_dir=output_dir)


if __name__ == "__main__":
    # Smoke test: build a calculator, run analysis, render artifacts.
    from calculations import create_rta_calculator

    print("=== RTA Visualizations smoke test ===")
    calc = create_rta_calculator()
    schedule_df = pd.DataFrame(
        [
            {
                "agent_id": f"A{i}",
                "date": f"2024-01-{d:02d}",
                "scheduled_hours": 8.0,
                "hour": 9,
            }
            for i in range(1, 6)
            for d in range(1, 11)
        ]
    )
    actual_df = schedule_df.copy()
    actual_df["actual_hours"] = actual_df["scheduled_hours"] * 0.92

    result = calc.analyze(schedule_df, actual_df)
    viz = create_visualizer()
    html_path = viz.render_html_report(result)
    json_path = viz.render_json_report(result)
    print(f"HTML report : {html_path}")
    print(f"JSON report : {json_path}")
    print(f"Confidence  : {result.confidence_score:.2f}")
