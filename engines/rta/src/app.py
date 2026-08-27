"""
RTA Command Center - Main Application

This is the main application file for the Real-Time Adherence (RTA) Command Center.
It provides a comprehensive interface for monitoring, analyzing, and optimizing agent adherence.

Key Features:
- Real-time adherence monitoring
- Interactive dashboards
- Schedule optimization
- Performance analytics
- Alert management
- Historical analysis
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from calculations import create_rta_calculator
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialize RTA calculator
rta_calculator = create_rta_calculator()

# Global data storage
adherence_data = {}
schedule_data = {}
performance_data = {}


# Sample data generation function
def generate_sample_data():
    """Generate sample data for demonstration."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    agents = [f"Agent_{i}" for i in range(1, 11)]

    # Generate schedule data
    schedule_data = []
    for date in dates:
        for agent in agents:
            scheduled_hours = np.random.uniform(6, 10)
            schedule_data.append(
                {
                    "agent_id": agent,
                    "date": date,
                    "scheduled_hours": scheduled_hours,
                    "hour": date.hour if hasattr(date, "hour") else 9,
                }
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
                "hour": row["hour"],
            }
        )

    actual_df = pd.DataFrame(actual_data)

    return schedule_df, actual_df


# Initialize sample data
schedule_data, actual_data = generate_sample_data()

# Perform RTA analysis
rta_result = rta_calculator.analyze(schedule_data, actual_data)


@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template(
        "dashboard.html",
        adherence_metrics=rta_result.adherence_metrics,
        schedule_metrics=rta_result.schedule_metrics,
        performance_metrics=rta_result.performance_metrics,
        variance_analysis=rta_result.variance_analysis,
        confidence_score=rta_result.confidence_score,
        recommendations=rta_result.optimization_recommendations,
    )


@app.route("/api/adherence")
def get_adherence_data():
    """Get adherence data for API."""
    return jsonify(rta_result.adherence_metrics)


@app.route("/api/schedule")
def get_schedule_data():
    """Get schedule data for API."""
    return jsonify(rta_result.schedule_metrics)


@app.route("/api/performance")
def get_performance_data():
    """Get performance data for API."""
    return jsonify(rta_result.performance_metrics)


@app.route("/api/variance")
def get_variance_data():
    """Get variance data for API."""
    return jsonify(rta_result.variance_analysis)


@app.route("/api/recommendations")
def get_recommendations():
    """Get optimization recommendations."""
    return jsonify(rta_result.optimization_recommendations)


@app.route("/api/confidence")
def get_confidence_score():
    """Get confidence score."""
    return jsonify({"confidence_score": rta_result.confidence_score})


@app.route("/api/update-data", methods=["POST"])
def update_data():
    """Update data with new information."""
    global schedule_data, actual_data, rta_result

    try:
        # Get new data from request
        new_schedule = request.json.get("schedule_data", {})
        new_actual = request.json.get("actual_data", {})

        # Convert to DataFrames
        new_schedule_df = pd.DataFrame(new_schedule)
        new_actual_df = pd.DataFrame(new_actual)

        # Update global data
        schedule_data = pd.concat([schedule_data, new_schedule_df], ignore_index=True)
        actual_data = pd.concat([actual_data, new_actual_df], ignore_index=True)

        # Perform RTA analysis
        rta_result = rta_calculator.analyze(schedule_data, actual_data)

        return jsonify(
            {
                "status": "success",
                "message": "Data updated successfully",
                "adherence_score": rta_result.adherence_metrics.get(
                    "overall_adherence", 0
                ),
            }
        )

    except (KeyError, TypeError, ValueError, pd.errors.EmptyDataError) as e:
        logger.error("Error updating data: %s", e)
        return jsonify(
            {"status": "error", "message": f"Error updating data: {e!s}"}
        ), 500


@app.route("/api/generate-report", methods=["POST"])
def generate_report():
    """Generate comprehensive report."""
    try:
        # Generate report data
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "adherence_metrics": rta_result.adherence_metrics,
            "schedule_metrics": rta_result.schedule_metrics,
            "performance_metrics": rta_result.performance_metrics,
            "variance_analysis": rta_result.variance_analysis,
            "recommendations": rta_result.optimization_recommendations,
            "confidence_score": rta_result.confidence_score,
        }

        # Save report to file
        report_path = (
            Path("reports")
            / f"rta_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report_path.parent.mkdir(exist_ok=True)

        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)

        return jsonify(
            {
                "status": "success",
                "message": "Report generated successfully",
                "report_path": str(report_path),
            }
        )

    except (OSError, TypeError, ValueError) as e:
        logger.error("Error generating report: %s", e)
        return jsonify(
            {"status": "error", "message": f"Error generating report: {e!s}"}
        ), 500


@app.route("/api/health")
def health_check():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "data_points": len(schedule_data),
        }
    )


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify(
        {"error": "Not found", "message": "The requested resource was not found"}
    ), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify(
        {
            "error": "Internal server error",
            "message": "An internal server error occurred",
        }
    ), 500


def create_app():
    """Create and configure the Flask application."""
    return app


if __name__ == "__main__":
    print("=== RTA Command Center ===")
    print("Starting RTA Command Center server...")
    print(f"Initial data points: {len(schedule_data)}")
    print(
        f"Overall adherence: {rta_result.adherence_metrics.get('overall_adherence', 0):.1f}%"
    )
    print(f"Confidence score: {rta_result.confidence_score:.2f}")

    # Run the application
    app.run(host="0.0.0.0", port=5000, debug=True)
