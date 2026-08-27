"""
Variance Engine for WFM Forecasting

This module implements variance analysis and statistical testing for WFM forecasting.
It identifies patterns, detects anomalies, and provides insights for forecast improvement.

Key Features:
- Statistical variance analysis
- Anomaly detection
- Pattern recognition
- Forecast accuracy assessment
- Root cause analysis
"""

import logging
import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VarianceAnalysisResult:
    """Result of variance analysis."""

    def __init__(self):
        self.variance_metrics = {}
        self.anomalies = []
        self.patterns = []
        self.forecast_accuracy = {}
        self.recommendations = []
        self.confidence_score = 0.0


class VarianceEngine:
    """
    Variance analysis engine for WFM forecasting with statistical testing.
    """

    def __init__(self, variance_threshold: float = 2.0, anomaly_threshold: float = 3.0):
        self.variance_threshold = variance_threshold
        self.anomaly_threshold = anomaly_threshold
        self.scaler = StandardScaler()

    def calculate_variance_metrics(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate comprehensive variance metrics.

        Args:
            data: DataFrame with time series data

        Returns:
            Dictionary with variance metrics
        """
        metrics = {}

        if "calls" not in data.columns:
            return metrics

        # Basic statistics
        calls_series = data["calls"]
        metrics["basic_stats"] = {
            "mean": calls_series.mean(),
            "median": calls_series.median(),
            "std": calls_series.std(),
            "min": calls_series.min(),
            "max": calls_series.max(),
            "range": calls_series.max() - calls_series.min(),
            "coefficient_of_variation": calls_series.std() / calls_series.mean()
            if calls_series.mean() > 0
            else 0,
        }

        # Variance decomposition
        metrics["variance_decomposition"] = self._variance_decomposition(calls_series)

        # Seasonal variance
        metrics["seasonal_variance"] = self._calculate_seasonal_variance(data)

        # Trend variance
        metrics["trend_variance"] = self._calculate_trend_variance(data)

        # Residual variance
        metrics["residual_variance"] = self._calculate_residual_variance(data)

        # Volatility clustering
        metrics["volatility_clustering"] = self._calculate_volatility_clustering(
            calls_series
        )

        return metrics

    def _variance_decomposition(self, series: pd.Series) -> dict[str, float]:
        """
        Decompose variance into components.

        Args:
            series: Time series data

        Returns:
            Dictionary with variance components
        """
        # Calculate rolling statistics
        window = min(7, len(series) // 4)  # Adaptive window size
        if window < 3:
            return {
                "total_variance": series.var(),
                "trend_variance": 0,
                "seasonal_variance": 0,
                "residual_variance": series.var(),
            }

        # Rolling mean and std
        rolling_mean = series.rolling(window=window, center=True).mean()

        # Remove trend (using rolling mean)
        detrended = series - rolling_mean

        # Calculate variance components
        total_variance = series.var()
        trend_variance = rolling_mean.var()
        seasonal_variance = detrended.var()

        return {
            "total_variance": total_variance,
            "trend_variance": trend_variance,
            "seasonal_variance": seasonal_variance,
            "residual_variance": seasonal_variance,  # Simplified
            "trend_variance_percentage": (trend_variance / total_variance * 100)
            if total_variance > 0
            else 0,
            "seasonal_variance_percentage": (seasonal_variance / total_variance * 100)
            if total_variance > 0
            else 0,
        }

    def _calculate_seasonal_variance(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate seasonal variance patterns.

        Args:
            data: DataFrame with time series data

        Returns:
            Dictionary with seasonal variance analysis
        """
        if "hour" not in data.columns or "calls" not in data.columns:
            return {}

        # Group by hour and calculate variance
        hourly_stats = data.groupby("hour")["calls"].agg(["mean", "std", "count"])

        # Calculate seasonal variance
        seasonal_variance = hourly_stats["std"] ** 2

        # Identify peak and off-peak hours
        peak_hours = hourly_stats[
            hourly_stats["std"] > hourly_stats["std"].quantile(0.75)
        ].index.tolist()
        off_peak_hours = hourly_stats[
            hourly_stats["std"] < hourly_stats["std"].quantile(0.25)
        ].index.tolist()

        return {
            "hourly_variance": seasonal_variance.to_dict(),
            "peak_hours": peak_hours,
            "off_peak_hours": off_peak_hours,
            "overall_seasonal_variance": seasonal_variance.mean(),
            "seasonal_coefficient": seasonal_variance.std() / seasonal_variance.mean()
            if seasonal_variance.mean() > 0
            else 0,
        }

    def _calculate_trend_variance(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate trend variance over time.

        Args:
            data: DataFrame with time series data

        Returns:
            Dictionary with trend variance analysis
        """
        if "date" not in data.columns or "calls" not in data.columns:
            return {}

        # Aggregate by date
        daily_stats = data.groupby("date")["calls"].agg(["mean", "std", "count"])

        # Calculate trend using linear regression
        x = np.arange(len(daily_stats))
        y = daily_stats["mean"].values

        if len(x) > 1:
            slope, intercept, r_value, p_value, _std_err = stats.linregress(x, y)

            # Calculate trend variance
            predicted = slope * x + intercept
            residuals = y - predicted
            trend_variance = np.var(residuals)

            return {
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_value**2,
                "p_value": p_value,
                "trend_variance": trend_variance,
                "trend_significance": p_value < 0.05,
                "trend_strength": abs(r_value),
            }

        return {
            "slope": 0,
            "intercept": daily_stats["mean"].mean(),
            "r_squared": 0,
            "p_value": 1.0,
            "trend_variance": 0,
            "trend_significance": False,
            "trend_strength": 0,
        }

    def _calculate_residual_variance(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Calculate residual variance after removing trend and seasonality.

        Args:
            data: DataFrame with time series data

        Returns:
            Dictionary with residual variance analysis
        """
        if "calls" not in data.columns:
            return {}

        # Simple residual calculation (difference from moving average)
        window = min(5, len(data) // 10)
        if window < 2:
            return {"residual_variance": data["calls"].var(), "residual_mean": 0}

        # Calculate moving average
        moving_avg = data["calls"].rolling(window=window, center=True).mean()

        # Calculate residuals
        residuals = data["calls"] - moving_avg

        # Remove NaN values
        residuals = residuals.dropna()

        return {
            "residual_variance": residuals.var(),
            "residual_mean": residuals.mean(),
            "residual_std": residuals.std(),
            "residual_skewness": stats.skew(residuals) if len(residuals) > 2 else 0,
            "residual_kurtosis": stats.kurtosis(residuals) if len(residuals) > 2 else 0,
        }

    def _calculate_volatility_clustering(self, series: pd.Series) -> dict[str, Any]:
        """
        Calculate volatility clustering using rolling standard deviation.

        Args:
            series: Time series data

        Returns:
            Dictionary with volatility clustering analysis
        """
        # Calculate rolling standard deviation
        window = min(7, len(series) // 4)
        if window < 2:
            return {"volatility_clustering": 0, "high_volatility_periods": []}

        rolling_std = series.rolling(window=window).std()

        # Identify high volatility periods
        volatility_threshold = rolling_std.quantile(0.75)
        high_volatility_mask = rolling_std > volatility_threshold
        high_volatility_periods = high_volatility_mask[
            high_volatility_mask
        ].index.tolist()

        # Calculate volatility clustering index
        volatility_clustering = (
            (len(high_volatility_periods) / len(rolling_std.dropna()) * 100)
            if len(rolling_std.dropna()) > 0
            else 0
        )

        return {
            "volatility_clustering_percentage": volatility_clustering,
            "high_volatility_periods": high_volatility_periods,
            "volatility_std": rolling_std.std(),
            "volatility_mean": rolling_std.mean(),
        }

    def detect_anomalies(self, data: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Detect anomalies using statistical methods.

        Args:
            data: DataFrame with time series data

        Returns:
            List of detected anomalies
        """
        anomalies = []

        if "calls" not in data.columns:
            return anomalies

        calls_series = data["calls"]

        # Method 1: Z-score anomaly detection
        z_scores = np.abs(stats.zscore(calls_series.dropna()))
        anomaly_indices = np.where(z_scores > self.anomaly_threshold)[0]

        for idx in anomaly_indices:
            if idx < len(calls_series):
                anomalies.append(
                    {
                        "type": "z_score",
                        "index": idx,
                        "value": calls_series.iloc[idx],
                        "z_score": z_scores[idx],
                        "severity": "high" if z_scores[idx] > 4 else "medium",
                        "timestamp": data.index[idx]
                        if hasattr(data.index, "__getitem__")
                        else idx,
                    }
                )

        # Method 2: IQR-based anomaly detection
        Q1 = calls_series.quantile(0.25)
        Q3 = calls_series.quantile(0.75)
        IQR = Q3 - Q1

        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        iqr_anomalies = calls_series[
            (calls_series < lower_bound) | (calls_series > upper_bound)
        ]

        for idx, value in iqr_anomalies.items():
            anomalies.append(
                {
                    "type": "iqr",
                    "index": idx,
                    "value": value,
                    "lower_bound": lower_bound,
                    "upper_bound": upper_bound,
                    "severity": "high"
                    if value < lower_bound * 0.5 or value > upper_bound * 1.5
                    else "medium",
                    "timestamp": data.index[idx]
                    if hasattr(data.index, "__getitem__")
                    else idx,
                }
            )

        # Method 3: Rolling window anomaly detection
        window = min(5, len(calls_series) // 10)
        if window >= 2:
            rolling_mean = calls_series.rolling(window=window).mean()
            rolling_std = calls_series.rolling(window=window).std()

            # Remove NaN values
            rolling_mean = rolling_mean.dropna()
            rolling_std = rolling_std.dropna()

            # Calculate anomaly scores
            anomaly_scores = np.abs(
                (calls_series.loc[rolling_mean.index] - rolling_mean) / rolling_std
            )

            rolling_anomalies = anomaly_scores[anomaly_scores > self.anomaly_threshold]

            for idx, score in rolling_anomalies.items():
                anomalies.append(
                    {
                        "type": "rolling_window",
                        "index": idx,
                        "value": calls_series.loc[idx],
                        "anomaly_score": score,
                        "severity": "high" if score > 4 else "medium",
                        "timestamp": data.index[idx]
                        if hasattr(data.index, "__getitem__")
                        else idx,
                    }
                )

        # Remove duplicates and sort by severity
        unique_anomalies = []
        seen_indices = set()

        for anomaly in sorted(
            anomalies,
            key=lambda x: x.get("z_score", x.get("anomaly_score", 0)),
            reverse=True,
        ):
            if anomaly["index"] not in seen_indices:
                seen_indices.add(anomaly["index"])
                unique_anomalies.append(anomaly)

        return unique_anomalies

    def identify_patterns(self, data: pd.DataFrame) -> list[dict[str, Any]]:
        """
        Identify patterns in the data.

        Args:
            data: DataFrame with time series data

        Returns:
            List of identified patterns
        """
        patterns = []

        if "calls" not in data.columns:
            return patterns

        calls_series = data["calls"]

        # Pattern 1: Daily seasonality
        if "hour" in data.columns:
            hourly_avg = data.groupby("hour")["calls"].mean()
            peak_hours = hourly_avg.nlargest(3).index.tolist()

            patterns.append(
                {
                    "type": "daily_seasonality",
                    "description": f"Peak calling hours: {peak_hours}",
                    "strength": "strong" if len(peak_hours) > 0 else "weak",
                    "impact": "high" if len(peak_hours) > 2 else "medium",
                }
            )

        # Pattern 2: Weekly seasonality
        if "day_of_week" in data.columns:
            dow_avg = data.groupby("day_of_week")["calls"].mean()
            peak_days = dow_avg.nlargest(2).index.tolist()

            patterns.append(
                {
                    "type": "weekly_seasonality",
                    "description": f"Peak days: {peak_days}",
                    "strength": "strong" if len(peak_days) > 0 else "weak",
                    "impact": "medium",
                }
            )

        # Pattern 3: Trend analysis
        if "date" in data.columns:
            daily_stats = data.groupby("date")["calls"].agg(["mean", "std"])

            # Check for increasing/decreasing trend
            x = np.arange(len(daily_stats))
            y = daily_stats["mean"].values

            if len(x) > 1:
                slope, _intercept, r_value, _p_value, _ = stats.linregress(x, y)

                if abs(r_value) > 0.7:
                    trend_direction = "increasing" if slope > 0 else "decreasing"
                    patterns.append(
                        {
                            "type": "trend",
                            "description": f"Strong {trend_direction} trend (Rآ² = {r_value**2:.2f})",
                            "strength": "strong",
                            "impact": "high",
                        }
                    )

        # Pattern 4: Volatility patterns
        volatility = calls_series.rolling(window=min(5, len(calls_series) // 10)).std()
        high_volatility_ratio = (volatility > volatility.quantile(0.75)).sum() / len(
            volatility
        )

        if high_volatility_ratio > 0.3:
            patterns.append(
                {
                    "type": "volatility_clustering",
                    "description": f"High volatility periods: {high_volatility_ratio:.1%} of time",
                    "strength": "moderate" if high_volatility_ratio > 0.5 else "weak",
                    "impact": "medium",
                }
            )

        return patterns

    def calculate_forecast_accuracy(
        self, actuals: pd.Series, forecasts: pd.Series
    ) -> dict[str, Any]:
        """
        Calculate forecast accuracy metrics.

        Args:
            actuals: Actual values
            forecasts: Forecasted values

        Returns:
            Dictionary with accuracy metrics
        """
        # Align series
        aligned_data = pd.DataFrame(
            {"actuals": actuals, "forecasts": forecasts}
        ).dropna()

        if len(aligned_data) == 0:
            return {"mae": 0, "mape": 0, "rmse": 0, "r_squared": 0, "accuracy_score": 0}

        actuals_clean = aligned_data["actuals"]
        forecasts_clean = aligned_data["forecasts"]

        # Calculate metrics
        mae = np.mean(np.abs(actuals_clean - forecasts_clean))

        # MAPE (Mean Absolute Percentage Error)
        mape = np.mean(np.abs((actuals_clean - forecasts_clean) / actuals_clean)) * 100

        # RMSE (Root Mean Squared Error)
        rmse = np.sqrt(np.mean((actuals_clean - forecasts_clean) ** 2))

        # R-squared
        if len(actuals_clean) > 1:
            r_squared = 1 - (
                np.sum((actuals_clean - forecasts_clean) ** 2)
                / np.sum((actuals_clean - actuals_clean.mean()) ** 2)
            )
        else:
            r_squared = 0

        # Accuracy score (inverse of error)
        accuracy_score = max(0, 100 - (mape + rmse))

        return {
            "mae": mae,
            "mape_percent": mape,
            "rmse": rmse,
            "r_squared": r_squared,
            "accuracy_score": accuracy_score,
            "sample_size": len(aligned_data),
        }

    def generate_recommendations(
        self,
        variance_metrics: dict[str, Any],
        anomalies: list[dict[str, Any]],
        patterns: list[dict[str, Any]],
    ) -> list[str]:
        """
        Generate recommendations based on analysis results.

        Args:
            variance_metrics: Variance metrics
            anomalies: Detected anomalies
            patterns: Identified patterns

        Returns:
            List of recommendations
        """
        recommendations = []

        # Recommendation based on variance
        if (
            variance_metrics.get("variance_decomposition", {}).get(
                "trend_variance_percentage", 0
            )
            > 50
        ):
            recommendations.append(
                "High trend variance detected. Consider implementing trend-adjusted forecasting methods."
            )

        if (
            variance_metrics.get("seasonal_variance", {}).get(
                "overall_seasonal_variance", 0
            )
            > 100
        ):
            recommendations.append(
                "High seasonal variance. Implement seasonal adjustment in forecasting models."
            )

        # Recommendation based on anomalies
        high_severity_anomalies = [a for a in anomalies if a.get("severity") == "high"]
        if high_severity_anomalies:
            recommendations.append(
                f"Detected {len(high_severity_anomalies)} high-severity anomalies. Investigate root causes and implement monitoring."
            )

        # Recommendation based on patterns
        for pattern in patterns:
            if (
                pattern["type"] == "daily_seasonality"
                and pattern["strength"] == "strong"
            ):
                recommendations.append(
                    "Strong daily seasonality detected. Optimize staffing based on hourly patterns."
                )
                break

        # Recommendation based on volatility
        if (
            variance_metrics.get("volatility_clustering", {}).get(
                "volatility_clustering_percentage", 0
            )
            > 30
        ):
            recommendations.append(
                "High volatility clustering detected. Implement dynamic forecasting with confidence intervals."
            )

        # Default recommendation if no specific issues found
        if not recommendations:
            recommendations.append(
                "Variance analysis completed. Current forecasting model shows acceptable performance."
            )

        return recommendations

    def analyze(self, data: pd.DataFrame) -> VarianceAnalysisResult:
        """
        Perform comprehensive variance analysis.

        Args:
            data: DataFrame with time series data

        Returns:
            VarianceAnalysisResult object
        """
        result = VarianceAnalysisResult()

        try:
            # Calculate variance metrics
            result.variance_metrics = self.calculate_variance_metrics(data)

            # Detect anomalies
            result.anomalies = self.detect_anomalies(data)

            # Identify patterns
            result.patterns = self.identify_patterns(data)

            # Calculate forecast accuracy (if forecast data available)
            if "forecasts" in data.columns:
                result.forecast_accuracy = self.calculate_forecast_accuracy(
                    data["calls"], data["forecasts"]
                )

            # Generate recommendations
            result.recommendations = self.generate_recommendations(
                result.variance_metrics, result.anomalies, result.patterns
            )

            # Calculate confidence score
            result.confidence_score = self._calculate_confidence_score(result)

        except (ValueError, TypeError, OSError) as e:
            logger.error("Error in variance analysis: %s", e)
            result.recommendations = [f"Analysis completed with warnings: {e!s}"]
            result.confidence_score = 0.0

        return result

    def _calculate_confidence_score(self, result: VarianceAnalysisResult) -> float:
        """
        Calculate confidence score based on analysis results.

        Args:
            result: Variance analysis result

        Returns:
            Confidence score (0-1)
        """
        score = 1.0

        # Deduct for anomalies
        high_severity_anomalies = len(
            [a for a in result.anomalies if a.get("severity") == "high"]
        )
        score -= min(high_severity_anomalies * 0.1, 0.5)

        # Deduct for weak patterns
        weak_patterns = len([p for p in result.patterns if p.get("strength") == "weak"])
        score -= min(weak_patterns * 0.05, 0.2)

        # Deduct for low forecast accuracy
        if result.forecast_accuracy:
            accuracy = result.forecast_accuracy.get("accuracy_score", 0)
            score -= (1 - accuracy / 100) * 0.3

        return max(0.0, score)
