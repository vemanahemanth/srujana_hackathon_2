"""Example 1: Custom EWMA Risk Model."""
import math
from typing import Any, Dict, Sequence
from fragilityshield.contracts import RiskModel, RiskMetricsOutput, FloatParam


class CustomEWMARiskModel(RiskModel):
    """Computes Exponentially Weighted Moving Average (EWMA) VaR and Expected Shortfall."""

    def __init__(self, version: str = "1.0.0") -> None:
        super().__init__(
            model_id="custom.ewma_risk",
            name="Custom RiskMetrics EWMA Risk Model",
            version=version,
            author="quant_researcher",
            description="Dynamic EWMA variance model with configurable decay factor lambda and Gaussian tail estimation.",
            parameters=[
                FloatParam("decay_factor", default=0.94, description="EWMA lambda decay factor", min_value=0.80, max_value=0.99),
                FloatParam("confidence_level", default=0.95, description="VaR confidence level", min_value=0.80, max_value=0.999),
            ],
        )

    def calculate_risk(self, returns: Sequence[float], parameters: Dict[str, Any]) -> RiskMetricsOutput:
        lam = float(parameters.get("decay_factor", 0.94))
        conf = float(parameters.get("confidence_level", 0.95))

        variance = float(returns[0]) ** 2
        for r in returns[1:]:
            variance = lam * variance + (1.0 - lam) * (float(r) ** 2)

        daily_vol = math.sqrt(max(1e-8, variance))
        ann_vol = daily_vol * math.sqrt(252)

        # Standard normal inverse quantile
        if conf >= 0.99:
            z = 2.3263
            z_es = 2.665
        else:
            z = 1.6449
            z_es = 2.0627

        var_val = z * daily_vol
        es_val = z_es * daily_vol

        return RiskMetricsOutput(
            var_95=float(var_val),
            expected_shortfall_95=float(es_val),
            annualized_volatility=float(ann_vol),
            var_99=float(2.3263 * daily_vol),
            expected_shortfall_99=float(2.665 * daily_vol),
            metrics={
                "daily_volatility": float(daily_vol),
                "annualized_volatility": float(ann_vol),
                "var_95": float(var_val),
                "expected_shortfall_95": float(es_val),
                "variance": float(variance),
            },
            metadata={"decay_factor_used": lam, "sample_size": len(returns)},
        )
