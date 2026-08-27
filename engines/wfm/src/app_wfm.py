"""
WFM Forecasting Calculator - Main Application

This is the main application file for the Workforce Management Forecasting Calculator.
It provides a user interface for running Erlang C calculations and generating reports.

Key Features:
- Interactive command-line interface
- Data import/export capabilities
- Report generation
- Result visualization
- Integration with other Helix engines
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from erlang_c import create_erlang_c_engine

# Set up matplotlib for better visualizations
plt.style.use("seaborn-v0_8")
sns.set_palette("husl")


class WFMForecastingApp:
    """
    Main application class for WFM Forecasting Calculator.
    """

    def __init__(self):
        self.data_dir = Path("data")
        self.output_dir = Path("output")
        self.setup_directories()
        self.results_history = []

    def setup_directories(self):
        """Create necessary directories if they don't exist."""
        self.data_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

    def load_sample_data(self) -> dict[str, pd.DataFrame]:
        """
        Load sample data for demonstration.

        Returns:
            Dictionary with loaded dataframes
        """
        data = {}

        # Load actuals data
        actuals_path = self.data_dir / "actuals.csv"
        if actuals_path.exists():
            data["actuals"] = pd.read_csv(actuals_path, parse_dates=["timestamp"])
        else:
            # Create sample data if file doesn't exist
            data["actuals"] = self._create_sample_actuals_data()
            data["actuals"].to_csv(actuals_path, index=False)

        # Load sample intervals data
        intervals_path = self.data_dir / "sample_intervals.csv"
        if intervals_path.exists():
            data["intervals"] = pd.read_csv(intervals_path)
        else:
            # Create sample data if file doesn't exist
            data["intervals"] = self._create_sample_intervals_data()
            data["intervals"].to_csv(intervals_path, index=False)

        return data

    def _create_sample_actuals_data(self) -> pd.DataFrame:
        """Create sample actuals data."""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=30, freq="h")

        # Generate realistic call patterns
        base_calls = 50
        hourly_variation = np.random.normal(0, 10, len(dates))
        peak_hours = [9, 10, 11, 14, 15, 16]  # Business hours

        calls = []
        for i, date in enumerate(dates):
            hour = date.hour
            call_rate = base_calls

            # Add peak hour effects
            if hour in peak_hours:
                call_rate *= 1.5

            # Add random variation
            call_rate += hourly_variation[i]

            # Ensure minimum calls
            call_rate = max(20, call_rate)

            # Generate Poisson-distributed calls for this period
            calls.append(int(np.random.poisson(call_rate)))

        return pd.DataFrame(
            {
                "timestamp": dates,
                "calls": calls,
                "hour": [d.hour for d in dates],
                "day_of_week": [d.dayofweek for d in dates],
            }
        )

    def _create_sample_intervals_data(self) -> pd.DataFrame:
        """Create sample intervals data."""
        np.random.seed(42)

        # Generate service level targets for different scenarios
        scenarios = [
            {"target": 0.80, "weight": 0.4},
            {"target": 0.85, "weight": 0.3},
            {"target": 0.90, "weight": 0.3},
        ]

        data = []
        for scenario in scenarios:
            for i in range(100):
                # Generate random parameters
                arrival_rate = np.random.uniform(30, 80)
                aht = np.random.uniform(3, 8)

                data.append(
                    {
                        "scenario": f"Scenario_{i}",
                        "arrival_rate": arrival_rate,
                        "average_handling_time": aht,
                        "service_level_target": scenario["target"],
                        "weight": scenario["weight"],
                    }
                )

        return pd.DataFrame(data)

    def run_forecasting_analysis(self, data: dict[str, pd.DataFrame]) -> dict[str, Any]:
        """
        Run comprehensive forecasting analysis.

        Args:
            data: Dictionary with loaded data

        Returns:
            Dictionary with analysis results
        """
        results = {}

        # Calculate historical metrics from actuals data
        actuals = data["actuals"].copy()
        # Ensure timestamp is datetime type
        actuals["timestamp"] = pd.to_datetime(actuals["timestamp"])

        # Calculate arrival rate (calls per hour)
        total_calls = actuals["calls"].sum()
        total_hours = len(actuals)
        arrival_rate = total_calls / total_hours

        # Calculate average handling time (assuming 5 minutes per call)
        average_handling_time = 5.0

        # Calculate average calls per period (daily)
        daily_calls = actuals.groupby(actuals["timestamp"].dt.date)["calls"].sum()
        average_calls_per_period = daily_calls.mean()

        # Create Erlang C engine
        engine = create_erlang_c_engine(
            arrival_rate=arrival_rate,
            average_handling_time=average_handling_time,
            service_level_target=0.80,
            average_calls_per_period=average_calls_per_period,
        )

        # Run optimization
        result = engine.optimize_agents()

        # Generate report
        report = engine.generate_report(result)

        results["main_forecast"] = report

        # Run scenario analysis
        scenarios = self._run_scenario_analysis(data["intervals"])
        results["scenarios"] = scenarios

        # Generate variance analysis
        variance_analysis = self._perform_variance_analysis(actuals)
        results["variance_analysis"] = variance_analysis

        # Store results
        self.results_history.append(
            {"timestamp": datetime.now().isoformat(), "results": results}
        )

        return results

    def _run_scenario_analysis(self, scenarios: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Run scenario analysis for different parameter combinations.

        Args:
            scenarios: DataFrame with scenario parameters

        Returns:
            List of scenario results
        """
        scenario_results = []

        for _, scenario in scenarios.iterrows():
            # Create Erlang C engine for this scenario
            engine = create_erlang_c_engine(
                arrival_rate=scenario["arrival_rate"],
                average_handling_time=scenario["average_handling_time"],
                service_level_target=scenario["service_level_target"],
                average_calls_per_period=1000,
            )

            # Run optimization
            result = engine.optimize_agents()

            # Generate report
            report = engine.generate_report(result)

            scenario_results.append(
                {
                    "scenario": scenario["scenario"],
                    "parameters": {
                        "arrival_rate": scenario["arrival_rate"],
                        "average_handling_time": scenario["average_handling_time"],
                        "service_level_target": scenario["service_level_target"],
                    },
                    "results": report,
                    "weight": scenario["weight"],
                }
            )

        return scenario_results

    def _perform_variance_analysis(self, actuals: pd.DataFrame) -> dict[str, Any]:
        """
        Perform variance analysis on actual data.

        Args:
            actuals: DataFrame with actual call data

        Returns:
            Dictionary with variance analysis results
        """
        # Calculate key metrics
        hourly_agg = actuals.groupby("hour").agg({"calls": ["mean", "std", "count"]})
        # Flatten multi-level columns for pandas 3.x compatibility
        hourly_agg.columns = [
            "-".join(col).strip("-") for col in hourly_agg.columns.values
        ]
        hourly_stats = hourly_agg.to_dict()

        # Calculate variance
        variance_analysis = {
            "hourly_variance": hourly_stats,
            "peak_hours": self._identify_peak_hours(actuals),
            "trend_analysis": self._analyze_trends(actuals),
            "forecast_accuracy": self._calculate_forecast_accuracy(actuals),
        }

        return variance_analysis

    def _identify_peak_hours(self, actuals: pd.DataFrame) -> list[int]:
        """Identify peak calling hours."""
        hourly_calls = actuals.groupby("hour")["calls"].mean()
        threshold = hourly_calls.mean() + hourly_calls.std()

        peak_hours = hourly_calls[hourly_calls > threshold].index.tolist()
        return peak_hours

    def _analyze_trends(self, actuals: pd.DataFrame) -> dict[str, Any]:
        """Analyze calling trends over time."""
        # Simple trend analysis
        daily_calls = actuals.groupby(actuals["timestamp"].dt.date)["calls"].sum()

        # Calculate trend slope
        x = np.arange(len(daily_calls))
        y = daily_calls.values

        if len(x) > 1:
            slope = np.polyfit(x, y, 1)[0]
            trend = (
                "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"
            )
        else:
            trend = "insufficient_data"

        return {
            "trend": trend,
            "daily_average": daily_calls.mean(),
            "daily_std": daily_calls.std(),
            "growth_rate": slope / daily_calls.mean() if daily_calls.mean() > 0 else 0,
        }

    def _calculate_forecast_accuracy(self, actuals: pd.DataFrame) -> dict[str, float]:
        """Calculate forecast accuracy metrics."""
        # Simple accuracy calculation
        hourly_calls = actuals.groupby("hour")["calls"].mean()

        # Calculate MAE (Mean Absolute Error)
        mae = hourly_calls.std()

        # Calculate MAPE (Mean Absolute Percentage Error)
        mape = (mae / hourly_calls.mean()) * 100

        return {
            "mae": mae,
            "mape_percent": mape,
            "forecast_confidence": max(0, 100 - mape),
        }

    def generate_visualizations(self, results: dict[str, Any]) -> dict[str, str]:
        """
        Generate visualizations from results.

        Args:
            results: Dictionary with analysis results

        Returns:
            Dictionary with visualization file paths
        """
        visualizations = {}

        # Create main forecast visualization
        if "main_forecast" in results:
            viz_path = self._create_forecast_visualization(results["main_forecast"])
            visualizations["main_forecast"] = viz_path

        # Create scenario comparison visualization
        if "scenarios" in results:
            viz_path = self._create_scenario_visualization(results["scenarios"])
            visualizations["scenario_comparison"] = viz_path

        return visualizations

    def _create_forecast_visualization(self, forecast: dict[str, Any]) -> str:
        """Create forecast visualization."""
        _fig, axes = plt.subplots(2, 2, figsize=(12, 10))

        # Plot 1: Agent count vs service level
        agents_range = range(1, 101)
        service_levels = []
        probabilities = []

        for agents in agents_range:
            engine = create_erlang_c_engine(
                arrival_rate=forecast["parameters"]["arrival_rate"],
                average_handling_time=forecast["parameters"][
                    "average_handling_time_minutes"
                ],
                service_level_target=forecast["parameters"]["service_level_target"],
                average_calls_per_period=1000,
            )

            result = engine.optimize_agents()
            service_levels.append(result.service_level_achieved)
            probabilities.append(result.probability_waiting)

        axes[0, 0].plot(agents_range, service_levels, "b-", label="Service Level")
        axes[0, 0].axhline(
            y=forecast["parameters"]["service_level_target"],
            color="r",
            linestyle="--",
            label="Target",
        )
        axes[0, 0].set_xlabel("Number of Agents")
        axes[0, 0].set_ylabel("Service Level")
        axes[0, 0].set_title("Service Level vs Agent Count")
        axes[0, 0].legend()
        axes[0, 0].grid(True)

        # Plot 2: Probability of waiting
        axes[0, 1].plot(agents_range, probabilities, "g-", label="Probability Waiting")
        axes[0, 1].set_xlabel("Number of Agents")
        axes[0, 1].set_ylabel("Probability of Waiting")
        axes[0, 1].set_title("Probability of Waiting vs Agent Count")
        axes[0, 1].legend()
        axes[0, 1].grid(True)

        # Plot 3: Utilization
        utilizations = []
        for agents in agents_range:
            engine = create_erlang_c_engine(
                arrival_rate=forecast["parameters"]["arrival_rate"],
                average_handling_time=forecast["parameters"][
                    "average_handling_time_minutes"
                ],
                service_level_target=forecast["parameters"]["service_level_target"],
                average_calls_per_period=1000,
            )

            result = engine.optimize_agents()
            utilizations.append(result.utilization * 100)

        axes[1, 0].plot(agents_range, utilizations, "r-", label="Utilization")
        axes[1, 0].set_xlabel("Number of Agents")
        axes[1, 0].set_ylabel("Utilization (%)")
        axes[1, 0].set_title("Utilization vs Agent Count")
        axes[1, 0].legend()
        axes[1, 0].grid(True)

        # Plot 4: Optimal point
        optimal_agents = forecast["optimal_agents"]
        axes[1, 1].scatter(
            optimal_agents,
            forecast["service_level_achieved"],
            color="red",
            s=200,
            label="Optimal Point",
        )
        axes[1, 1].plot(agents_range, service_levels, "b-", alpha=0.5)
        axes[1, 1].axhline(
            y=forecast["parameters"]["service_level_target"], color="r", linestyle="--"
        )
        axes[1, 1].set_xlabel("Number of Agents")
        axes[1, 1].set_ylabel("Service Level")
        axes[1, 1].set_title("Optimal Point Highlight")
        axes[1, 1].legend()
        axes[1, 1].grid(True)

        plt.tight_layout()

        # Save visualization
        viz_path = (
            self.output_dir
            / f"forecast_visualization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        plt.savefig(viz_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(viz_path)

    def _create_scenario_visualization(self, scenarios: list[dict[str, Any]]) -> str:
        """Create scenario comparison visualization."""
        _fig, axes = plt.subplots(2, 2, figsize=(12, 10))

        # Extract data
        agent_counts = []
        service_levels = []
        weights = []

        for scenario in scenarios:
            agent_counts.append(scenario["results"]["optimal_agents"])
            service_levels.append(scenario["results"]["service_level_achieved"])
            weights.append(scenario["weight"])

        # Plot 1: Scenario comparison by agent count
        axes[0, 0].scatter(
            agent_counts, service_levels, c=weights, cmap="viridis", s=100
        )
        axes[0, 0].set_xlabel("Number of Agents")
        axes[0, 0].set_ylabel("Service Level")
        axes[0, 0].set_title("Scenario Comparison: Service Level vs Agent Count")
        axes[0, 0].grid(True)

        # Plot 2: Scenario comparison by weight
        axes[0, 1].scatter(
            agent_counts, weights, c=service_levels, cmap="plasma", s=100
        )
        axes[0, 1].set_xlabel("Number of Agents")
        axes[0, 1].set_ylabel("Weight")
        axes[0, 1].set_title("Scenario Comparison: Weight vs Agent Count")
        axes[0, 1].grid(True)

        # Plot 3: Service level distribution
        axes[1, 0].hist(
            service_levels, bins=10, alpha=0.7, color="skyblue", edgecolor="black"
        )
        axes[1, 0].set_xlabel("Service Level")
        axes[1, 0].set_ylabel("Frequency")
        axes[1, 0].set_title("Service Level Distribution")
        axes[1, 0].grid(True)

        # Plot 4: Agent count distribution
        axes[1, 1].hist(
            agent_counts, bins=10, alpha=0.7, color="lightgreen", edgecolor="black"
        )
        axes[1, 1].set_xlabel("Number of Agents")
        axes[1, 1].set_ylabel("Frequency")
        axes[1, 1].set_title("Agent Count Distribution")
        axes[1, 1].grid(True)

        plt.tight_layout()

        # Save visualization
        viz_path = (
            self.output_dir
            / f"scenario_visualization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        plt.savefig(viz_path, dpi=300, bbox_inches="tight")
        plt.close()

        return str(viz_path)

    def export_results(self, results: dict[str, Any]) -> dict[str, str]:
        """
        Export results to various formats.

        Args:
            results: Dictionary with analysis results

        Returns:
            Dictionary with export file paths
        """
        exports = {}

        # Export to JSON
        json_path = (
            self.output_dir / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(json_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        exports["json"] = str(json_path)

        # Export to CSV (if applicable)
        if "scenarios" in results:
            scenarios_df = pd.DataFrame(
                [
                    {
                        "scenario": s["scenario"],
                        "optimal_agents": s["results"]["optimal_agents"],
                        "service_level": s["results"]["service_level_achieved"],
                        "probability_waiting": s["results"]["probability_waiting"],
                        "weight": s["weight"],
                    }
                    for s in results["scenarios"]
                ]
            )

            csv_path = (
                self.output_dir
                / f"scenarios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            scenarios_df.to_csv(csv_path, index=False)
            exports["csv"] = str(csv_path)

        return exports

    def run(self) -> dict[str, Any]:
        """
        Run the complete WFM forecasting analysis.

        Returns:
            Dictionary with analysis results
        """
        print("=== WFM Forecasting Calculator ===")

        # Load sample data
        print("Loading sample data...")
        data = self.load_sample_data()

        # Run forecasting analysis
        print("Running forecasting analysis...")
        results = self.run_forecasting_analysis(data)

        # Generate visualizations
        print("Generating visualizations...")
        visualizations = self.generate_visualizations(results)

        # Export results
        print("Exporting results...")
        exports = self.export_results(results)

        # Print summary
        print("\n=== Analysis Summary ===")
        main_forecast = results["main_forecast"]
        print(f"Optimal Agents: {main_forecast['optimal_agents']}")
        print(f"Service Level Achieved: {main_forecast['service_level_achieved']:.2%}")
        print(f"Utilization: {main_forecast['utilization_percentage']:.2f}%")
        print(f"Probability of Waiting: {main_forecast['probability_waiting']:.2%}")

        print(f"\nScenarios Analyzed: {len(results['scenarios'])}")
        print(
            f"Variance Analysis: {results['variance_analysis']['trend_analysis']['trend']}"
        )

        print("\nVisualizations Generated:")
        for viz_name, viz_path in visualizations.items():
            print(f"  {viz_name}: {viz_path}")

        print("\nExports Created:")
        for export_type, export_path in exports.items():
            print(f"  {export_type}: {export_path}")

        return {
            "results": results,
            "visualizations": visualizations,
            "exports": exports,
            "timestamp": datetime.now().isoformat(),
        }


def main():
    """Main application entry point."""
    print("=== WFM Forecasting Calculator ===")
    print("Initializing application...")

    app = WFMForecastingApp()

    print("Running complete analysis...")
    analysis_results = app.run()

    print("\n=== Analysis Complete ===")
    main_forecast = analysis_results["results"]["main_forecast"]
    print(f"Main optimal agents: {main_forecast['optimal_agents']}")
    print(f"Main service level: {main_forecast['service_level_achieved']:.2%}")
    print(f"Main probability of waiting: {main_forecast['probability_waiting']:.2%}")
    print(f"Visualizations generated: {len(analysis_results['visualizations'])}")
    print(f"Exports created: {len(analysis_results['exports'])}")


if __name__ == "__main__":
    main()
