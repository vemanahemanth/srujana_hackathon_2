"""Example 5: Custom Momentum Trend-Following Strategy."""
import math
from typing import Any, Dict
from fragilityshield.contracts import TradingStrategy, StrategySignalsOutput, IntParam


class CustomMomentumStrategy(TradingStrategy):
    """Dual moving-average crossover trend-following allocation strategy."""

    def __init__(self) -> None:
        super().__init__(
            model_id="custom.momentum_crossover",
            name="Dual Moving Average Momentum Strategy",
            version="1.0.0",
            author="quant_researcher",
            description="Generates asset weights based on short vs long term moving average price momentum crossovers.",
            parameters=[
                IntParam("fast_window", default=10, description="Fast moving average period", min_value=2, max_value=50),
                IntParam("slow_window", default=30, description="Slow moving average period", min_value=10, max_value=200),
            ],
        )

    def generate_signals(self, market_data: Dict[str, Any], parameters: Dict[str, Any]) -> StrategySignalsOutput:
        fast_w = int(parameters.get("fast_window", 10))
        slow_w = int(parameters.get("slow_window", 30))

        # Expected market_data: { asset_id: [prices...] }
        scores = {}
        for asset, prices in market_data.items():
            if isinstance(prices, (list, tuple)) and len(prices) >= slow_w:
                fast_ma = sum(prices[-fast_w:]) / fast_w
                slow_ma = sum(prices[-slow_w:]) / slow_w
                score = (fast_ma - slow_ma) / max(1e-8, slow_ma)
                scores[asset] = score
            else:
                scores[asset] = 0.0

        # Positive momentum gets allocated
        pos_scores = {a: max(0.0, sc) for a, sc in scores.items()}
        total_pos = sum(pos_scores.values())

        if total_pos > 1e-8:
            weights = {a: sc / total_pos for a, sc in pos_scores.items()}
        else:
            n = len(market_data) or 1
            weights = {a: 1.0 / n for a in market_data}

        return StrategySignalsOutput(
            target_weights=weights,
            signals=scores,
            turnover=0.15,
            expected_return=0.125,
            expected_volatility=0.18,
            metadata={"fast_window": fast_w, "slow_window": slow_w, "assets_evaluated": len(market_data)},
        )
