"""Example 3: Custom Sortino Downside Risk Metric."""
import math
from typing import Any, Dict, Sequence
from fragilityshield.contracts import CustomMetric, MetricOutput, FloatParam


class CustomSortinoRatioMetric(CustomMetric):
    """Calculates Sortino Ratio penalizing only downside deviation below the MAR threshold."""

    def __init__(self) -> None:
        super().__init__(
            model_id="custom.sortino_ratio",
            name="Custom Sortino Ratio Metric",
            version="1.0.0",
            author="quant_researcher",
            description="Evaluates the return per unit of downside risk below the minimum acceptable return (MAR).",
            parameters=[
                FloatParam("mar", default=0.0, description="Minimum Acceptable Return benchmark (daily MAR)", min_value=-0.05, max_value=0.05),
                FloatParam("risk_free_rate", default=0.065, description="Annualized risk-free rate", min_value=0.0, max_value=0.20),
            ],
        )

    def evaluate_metric(self, data: Any, parameters: Dict[str, Any]) -> MetricOutput:
        mar = float(parameters.get("mar", 0.0))
        rf_daily = float(parameters.get("risk_free_rate", 0.065)) / 252.0

        if isinstance(data, dict) and "returns" in data:
            returns = [float(x) for x in data["returns"]]
        else:
            returns = [float(x) for x in data]

        if not returns:
            raise ValueError("Empty return series provided to Sortino metric.")

        n = len(returns)
        mean_ret = sum(returns) / n
        excess_mean = mean_ret - rf_daily

        downside_diffs = [min(0.0, r - mar) ** 2 for r in returns]
        downside_dev = math.sqrt(sum(downside_diffs) / n)

        if downside_dev < 1e-8:
            sortino = 10.0 if excess_mean > 0 else 0.0
        else:
            sortino = (excess_mean / downside_dev) * math.sqrt(252)

        return MetricOutput(
            metric_name="sortino_ratio",
            value=float(sortino),
            unit="ratio",
            display_name="Annualized Sortino Ratio",
            interpretation="Higher is better; penalizes exclusively negative deviations below MAR.",
            details={
                "downside_deviation": float(downside_dev * math.sqrt(252)),
                "daily_downside_dev": float(downside_dev),
                "mar_used": mar,
                "annualized_mean_return": float(mean_ret * 252),
            },
        )
