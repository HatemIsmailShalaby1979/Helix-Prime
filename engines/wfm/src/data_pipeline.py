"""
Data Pipeline for WFM Forecasting

This module handles data extraction, processing, and preparation for the WFM forecasting engine.
It integrates with various data sources and prepares data for analysis.

Key Features:
- Data extraction from multiple sources
- Data cleaning and validation
- Feature engineering
- Data quality checks
- Integration with other engines
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataPipeline:
    """
    Data pipeline for WFM forecasting with data quality assurance.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.quality_thresholds = {
            "missing_data_percentage": 0.05,  # 5% max missing data
            "outlier_percentage": 0.10,  # 10% max outliers
            "consistency_score": 0.80,  # 80% min consistency
        }

    def load_actuals_data(self) -> pd.DataFrame:
        """
        Load actuals data from CSV file.

        Returns:
            DataFrame with actuals data
        """
        try:
            actuals_path = self.data_dir / "actuals.csv"
            if actuals_path.exists():
                df = pd.read_csv(actuals_path)
                logger.info(f"Loaded {len(df)} rows from {actuals_path}")
                return df
            else:
                logger.warning(f"File {actuals_path} not found, creating sample data")
                return self._create_sample_actuals_data()
        except Exception as e:
            logger.error(f"Error loading actuals data: {e}")
            raise

    def _create_sample_actuals_data(self) -> pd.DataFrame:
        """Create sample actuals data for testing."""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=30, freq="H")

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

            # Generate Poisson-distributed calls
            calls.append(np.random.poisson(call_rate))

        df = pd.DataFrame(
            {
                "timestamp": dates,
                "calls": calls,
                "hour": [d.hour for d in dates],
                "day_of_week": [d.dayofweek for d in dates],
                "date": [d.date() for d in dates],
            }
        )

        # Save sample data
        df.to_csv(self.data_dir / "actuals.csv", index=False)
        logger.info(f"Created sample actuals data with {len(df)} rows")

        return df

    def load_intervals_data(self) -> pd.DataFrame:
        """
        Load intervals data from CSV file.

        Returns:
            DataFrame with intervals data
        """
        try:
            intervals_path = self.data_dir / "sample_intervals.csv"
            if intervals_path.exists():
                df = pd.read_csv(intervals_path)
                logger.info(f"Loaded {len(df)} rows from {intervals_path}")
                return df
            else:
                logger.warning(f"File {intervals_path} not found, creating sample data")
                return self._create_sample_intervals_data()
        except Exception as e:
            logger.error(f"Error loading intervals data: {e}")
            raise

    def _create_sample_intervals_data(self) -> pd.DataFrame:
        """Create sample intervals data for testing."""
        np.random.seed(42)

        # Generate scenarios for different parameter combinations
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

        df = pd.DataFrame(data)

        # Save sample data
        df.to_csv(self.data_dir / "sample_intervals.csv", index=False)
        logger.info(f"Created sample intervals data with {len(df)} rows")

        return df

    def validate_data_quality(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Validate data quality and return quality metrics.

        Args:
            df: DataFrame to validate

        Returns:
            Dictionary with quality metrics
        """
        quality_metrics = {}

        # Check for missing values
        missing_percentage = df.isnull().sum().sum() / (df.shape[0] * df.shape[1])
        quality_metrics["missing_data_percentage"] = missing_percentage
        quality_metrics["missing_data_pass"] = (
            missing_percentage <= self.quality_thresholds["missing_data_percentage"]
        )

        # Check for outliers (using IQR method)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        outlier_counts = {}
        for col in numeric_cols:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            outlier_mask = (df[col] < (Q1 - 1.5 * IQR)) | (df[col] > (Q3 + 1.5 * IQR))
            outlier_counts[col] = outlier_mask.sum()

        total_outliers = sum(outlier_counts.values())
        total_values = len(df) * len(numeric_cols)
        outlier_percentage = total_outliers / total_values if total_values > 0 else 0

        quality_metrics["outlier_percentage"] = outlier_percentage
        quality_metrics["outlier_pass"] = (
            outlier_percentage <= self.quality_thresholds["outlier_percentage"]
        )

        # Calculate consistency score (based on data patterns)
        consistency_score = self._calculate_consistency_score(df)
        quality_metrics["consistency_score"] = consistency_score
        quality_metrics["consistency_pass"] = (
            consistency_score >= self.quality_thresholds["consistency_score"]
        )

        # Overall quality score
        quality_metrics["overall_score"] = (
            quality_metrics["missing_data_pass"] * 0.3
            + quality_metrics["outlier_pass"] * 0.3
            + quality_metrics["consistency_pass"] * 0.4
        )

        quality_metrics["overall_pass"] = quality_metrics["overall_score"] >= 0.8

        return quality_metrics

    def _calculate_consistency_score(self, df: pd.DataFrame) -> float:
        """
        Calculate consistency score based on data patterns.

        Args:
            df: DataFrame to analyze

        Returns:
            Consistency score (0-1)
        """
        if df.empty:
            return 0.0

        scores = []

        # Check temporal consistency
        if "timestamp" in df.columns:
            time_diff = df["timestamp"].diff().dt.total_seconds().dropna()
            if len(time_diff) > 0:
                time_variance = (
                    time_diff.std() / time_diff.mean() if time_diff.mean() > 0 else 0
                )
                time_score = max(0, 1 - time_variance)
                scores.append(time_score)

        # Check value consistency
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if len(df[col]) > 1:
                # Calculate coefficient of variation
                cv = df[col].std() / df[col].mean() if df[col].mean() > 0 else 0
                col_score = max(0, 1 - min(cv, 1))
                scores.append(col_score)

        # Calculate overall consistency score
        if scores:
            consistency_score = sum(scores) / len(scores)
        else:
            consistency_score = 0.0

        return consistency_score

    def process_data_for_forecasting(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Process data for forecasting analysis.

        Args:
            df: Raw data DataFrame

        Returns:
            Dictionary with processed data and metadata
        """
        processed_data = {}

        # Basic statistics
        processed_data["basic_stats"] = {
            "total_records": len(df),
            "date_range": {
                "start": df["timestamp"].min() if "timestamp" in df.columns else None,
                "end": df["timestamp"].max() if "timestamp" in df.columns else None,
            },
            "numeric_columns": list(df.select_dtypes(include=[np.number]).columns),
        }

        # Time series features
        if "timestamp" in df.columns and "calls" in df.columns:
            df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
            df["day_of_week"] = pd.to_datetime(df["timestamp"]).dt.dayofweek
            df["date"] = pd.to_datetime(df["timestamp"]).dt.date

            # Aggregate by hour
            hourly_stats = (
                df.groupby("hour")["calls"].agg(["mean", "std", "count"]).round(2)
            )
            processed_data["hourly_stats"] = hourly_stats.to_dict("index")

            # Aggregate by day of week
            dow_stats = (
                df.groupby("day_of_week")["calls"]
                .agg(["mean", "std", "count"])
                .round(2)
            )
            processed_data["dow_stats"] = dow_stats.to_dict("index")

            # Aggregate by date
            daily_stats = (
                df.groupby("date")["calls"].agg(["sum", "mean", "std"]).round(2)
            )
            processed_data["daily_stats"] = daily_stats.to_dict("index")

        # Calculate forecasting parameters
        if "calls" in df.columns:
            total_calls = df["calls"].sum()
            total_hours = len(df)
            arrival_rate = total_calls / total_hours

            processed_data["forecasting_parameters"] = {
                "arrival_rate_per_hour": arrival_rate,
                "average_calls_per_period": total_calls
                / (total_hours / 24),  # Daily average
                "peak_hour_calls": df.groupby("hour")["calls"].max().to_dict(),
                "off_peak_calls": df.groupby("hour")["calls"].min().to_dict(),
            }

        return processed_data

    def run_quality_checks(self, df: pd.DataFrame) -> dict[str, Any]:
        """
        Run comprehensive quality checks.

        Args:
            df: DataFrame to check

        Returns:
            Dictionary with quality check results
        """
        quality_checks = {}

        # Check 1: Missing values
        missing_counts = df.isnull().sum()
        missing_details = missing_counts[missing_counts > 0].to_dict()
        quality_checks["missing_values"] = {
            "columns_with_missing": len(missing_details),
            "missing_details": missing_details,
            "total_missing": sum(missing_details.values()),
        }

        # Check 2: Data types
        type_mismatches = {}
        expected_types = {
            "timestamp": "datetime64[ns]",
            "calls": "int64",
            "hour": "int64",
            "day_of_week": "int64",
        }

        for col, expected_type in expected_types.items():
            if col in df.columns:
                actual_type = str(df[col].dtype)
                if expected_type not in actual_type:
                    type_mismatches[col] = {
                        "expected": expected_type,
                        "actual": actual_type,
                    }

        quality_checks["data_types"] = {
            "type_mismatches": type_mismatches,
            "total_mismatches": len(type_mismatches),
        }

        # Check 3: Value ranges
        range_issues = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            if col != "calls":  # Skip calls for range checks
                min_val = df[col].min()
                max_val = df[col].max()
                if min_val < 0 or max_val < 0:
                    range_issues[col] = {
                        "min": min_val,
                        "max": max_val,
                        "issue": "negative_values",
                    }

        quality_checks["value_ranges"] = {
            "range_issues": range_issues,
            "total_issues": len(range_issues),
        }

        # Check 4: Duplicate timestamps
        if "timestamp" in df.columns:
            duplicate_timestamps = df["timestamp"].duplicated().sum()
            quality_checks["timestamp_duplicates"] = {
                "duplicate_count": duplicate_timestamps,
                "has_duplicates": duplicate_timestamps > 0,
            }

        return quality_checks

    def generate_data_report(
        self, df: pd.DataFrame, quality_metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate comprehensive data report.

        Args:
            df: DataFrame to analyze
            quality_metrics: Quality metrics from validation

        Returns:
            Dictionary with data report
        """
        report = {
            "data_summary": {
                "total_records": len(df),
                "total_columns": len(df.columns),
                "column_names": list(df.columns),
                "data_types": {
                    col: str(dtype) for col, dtype in df.dtypes.to_dict().items()
                },
            },
            "quality_summary": quality_metrics,
            "processing_timestamp": datetime.now().isoformat(),
        }

        # Add forecasting readiness
        if "calls" in df.columns:
            report["forecasting_readiness"] = {
                "has_calls_data": True,
                "data_volume_sufficient": len(df) >= 100,  # Minimum 100 records
                "calls_range": {
                    "min": df["calls"].min(),
                    "max": df["calls"].max(),
                    "mean": df["calls"].mean(),
                    "std": df["calls"].std(),
                },
            }

        return report


def create_data_pipeline(data_dir: str = "data") -> DataPipeline:
    """
    Factory function to create data pipeline.

    Args:
        data_dir: Directory containing data files

    Returns:
        DataPipeline instance
    """
    return DataPipeline(data_dir)


if __name__ == "__main__":
    # Example usage
    print("=== WFM Data Pipeline ===")

    # Create pipeline
    pipeline = create_data_pipeline()

    # Load data
    print("Loading actuals data...")
    actuals_data = pipeline.load_actuals_data()

    print("Loading intervals data...")
    intervals_data = pipeline.load_intervals_data()

    # Validate data quality
    print("Validating data quality...")
    quality_metrics = pipeline.validate_data_quality(actuals_data)
    print(f"Quality score: {quality_metrics['overall_score']:.2%}")

    # Run quality checks
    print("Running quality checks...")
    quality_checks = pipeline.run_quality_checks(actuals_data)

    # Process data for forecasting
    print("Processing data for forecasting...")
    processed_data = pipeline.process_data_for_forecasting(actuals_data)

    # Generate data report
    print("Generating data report...")
    data_report = pipeline.generate_data_report(actuals_data, quality_metrics)

    print("\n=== Data Pipeline Complete ===")
    print(f"Records processed: {len(actuals_data)}")
    print(f"Quality score: {quality_metrics['overall_score']:.2%}")
    print(f"Columns: {len(actuals_data.columns)}")
    print(f"Data types: {data_report['data_summary']['data_types']}")
