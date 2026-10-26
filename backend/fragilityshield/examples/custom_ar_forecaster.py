"""Example 2: Custom Autoregressive Return Forecaster."""
import math
from typing import Any, Dict, Sequence
from fragilityshield.contracts import ForecastingModel, ForecastOutput, IntParam, FloatParam


class CustomARForecaster(ForecastingModel):
    """Autoregressive AR(1) multi-step return forecaster with analytic confidence intervals."""

    def __init__(self) -> None:
        super().__init__(
            model_id="custom.ar_forecaster",
            name="Custom Autoregressive Return Forecaster",
            version="1.0.0",
            author="quant_researcher",
            description="First-order autoregressive model forecasting future expected returns and expanding uncertainty intervals.",
            parameters=[
                IntParam("horizon", default=5, description="Forecast steps horizon", min_value=1, max_value=60),
                FloatParam("mean_reversion_speed", default=0.15, description="Speed of reversion to historical mean", min_value=0.01, max_value=0.99),
            ],
        )

    def generate_forecast(self, series: Sequence[float], horizon: int, parameters: Dict[str, Any]) -> ForecastOutput:
        n = len(series)
        mean_val = sum(series) / n
        variance = sum((x - mean_val) ** 2 for x in series) / (n - 1)
        sigma = math.sqrt(max(1e-8, variance))

        phi = 1.0 - float(parameters.get("mean_reversion_speed", 0.15))
        last_val = series[-1]

        forecast = []
        lower_ci = []
        upper_ci = []

        curr = last_val
        for h in range(1, horizon + 1):
            curr = mean_val + phi * (curr - mean_val)
            h_sigma = sigma * math.sqrt(h)
            forecast.append(float(curr))
            lower_ci.append(float(curr - 1.96 * h_sigma))
            upper_ci.append(float(curr + 1.96 * h_sigma))

        return ForecastOutput(
            forecast=tuple(forecast),
            lower_ci=tuple(lower_ci),
            upper_ci=tuple(upper_ci),
            horizon=horizon,
            metrics={"historical_mean": float(mean_val), "historical_volatility": float(sigma)},
            metadata={"model_family": "autoregressive_linear"},
        )
