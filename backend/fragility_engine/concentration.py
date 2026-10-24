"""Portfolio allocation and concentration analytics for FragilityShield.

Calculates market-value weights, sector breakdowns, and Herfindahl-Hirschman Indices (HHI).

Methodology & Disclaimers:
- Weights are market-value proportions: w_i = market_value_i / total_market_value.
- Decimal HHI is computed as sum(w_i ** 2) on [0.0, 1.0].
- Conventional HHI points are scaled as decimal_hhi * 10,000 on [0.0, 10,000].
  (e.g. Antitrust reference: < 1500 diversified, 1500 - 2500 moderate, > 2500 concentrated).
- HHI is strictly a bucket concentration indicator; it does not capture asset correlations,
  systematic beta, liquidity risks, or tail-risk dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Sequence, Tuple, Union

from fragility_engine.models import Portfolio


@dataclass(frozen=True)
class ConcentrationAnalysis:
    """Comprehensive portfolio allocation and concentration report.

    Attributes:
        total_market_value: Aggregate unrounded market value of all holdings.
        asset_weights: Mapping of asset_id to its proportion of portfolio market value.
        sector_market_values: Aggregate market value by sector.
        sector_weights: Proportion of portfolio market value by sector.
        asset_hhi_decimal: Decimal asset-level HHI in range (0.0, 1.0].
        asset_hhi_points: Conventional asset-level HHI points in range (0.0, 10000.0].
        sector_hhi_decimal: Decimal sector-level HHI in range (0.0, 1.0].
        sector_hhi_points: Conventional sector-level HHI points in range (0.0, 10000.0].
        methodology: Formal methodology statement.
        disclaimer: Clear statement on metric limitations.
    """

    total_market_value: float
    asset_weights: Dict[str, float]
    sector_market_values: Dict[str, float]
    sector_weights: Dict[str, float]
    asset_hhi_decimal: float
    asset_hhi_points: float
    sector_hhi_decimal: float
    sector_hhi_points: float
    methodology: str = (
        "Market-value weighted sum of squared proportions: HHI = sum(w_i^2). "
        "Expressed in decimal (0-1) and conventional points (0-10,000)."
    )
    disclaimer: str = (
        "HHI indicates weight concentration across buckets. It does not measure "
        "inter-asset correlation, volatility, liquidity, or tail risk."
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert analysis to a serializable dictionary."""
        return {
            "total_market_value": self.total_market_value,
            "asset_weights": dict(self.asset_weights),
            "sector_market_values": dict(self.sector_market_values),
            "sector_weights": dict(self.sector_weights),
            "asset_hhi_decimal": self.asset_hhi_decimal,
            "asset_hhi_points": self.asset_hhi_points,
            "sector_hhi_decimal": self.sector_hhi_decimal,
            "sector_hhi_points": self.sector_hhi_points,
            "methodology": self.methodology,
            "disclaimer": self.disclaimer,
        }


def calculate_hhi(weights: Union[Sequence[float], Dict[str, float]]) -> Tuple[float, float]:
    """Compute decimal HHI and conventional HHI points from weights.

    Formula:
        decimal_hhi = sum(w_i ** 2)
        points_hhi = decimal_hhi * 10,000.0

    Args:
        weights: A sequence of weights or a mapping of identifier -> weight.

    Returns:
        A tuple of (decimal_hhi, points_hhi).

    Raises:
        ValueError: If weights is empty, contains non-finite values, or sums to <= 0.
    """
    if isinstance(weights, dict):
        w_list = list(weights.values())
    else:
        w_list = list(weights)

    if not w_list:
        raise ValueError("Cannot calculate HHI on an empty set of weights")

    for idx, w in enumerate(w_list):
        if not math.isfinite(w):
            raise ValueError(f"Weight at index {idx} must be finite; got {w!r}")
        if w < 0.0:
            raise ValueError(f"Weight at index {idx} cannot be negative; got {w!r}")

    sum_w = sum(w_list)
    if sum_w <= 0.0:
        raise ValueError(f"Sum of weights must be positive; got {sum_w}")

    # Normalize weights to strictly sum to 1.0 if not already normalized
    if not math.isclose(sum_w, 1.0, rel_tol=1e-5, abs_tol=1e-5):
        w_norm = [w / sum_w for w in w_list]
    else:
        w_norm = w_list

    decimal_hhi = sum(w ** 2 for w in w_norm)
    points_hhi = decimal_hhi * 10000.0

    return decimal_hhi, points_hhi


def calculate_sector_allocations(
    portfolio: Portfolio,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Compute aggregate market values and weights by sector.

    Args:
        portfolio: Validated Portfolio instance.

    Returns:
        Tuple of (sector_market_values, sector_weights).

    Raises:
        ValueError: If portfolio total value is not strictly positive.
    """
    tot = portfolio.total_value
    if tot <= 0.0:
        raise ValueError(f"Portfolio total value must be positive; got {tot}")

    sector_values: Dict[str, float] = {}
    for h in portfolio.holdings:
        sec = h.sector.strip() if h.sector and h.sector.strip() else "Unclassified"
        sector_values[sec] = sector_values.get(sec, 0.0) + h.market_value

    sector_weights = {sec: val / tot for sec, val in sector_values.items()}
    return sector_values, sector_weights


def calculate_portfolio_concentration(portfolio: Portfolio) -> ConcentrationAnalysis:
    """Perform complete portfolio valuation, allocation, and HHI concentration analysis.

    Args:
        portfolio: Validated Portfolio instance.

    Returns:
        A ConcentrationAnalysis instance.

    Raises:
        ValueError: If portfolio total value is not positive or contains no holdings.
    """
    if not isinstance(portfolio, Portfolio):
        raise TypeError(f"portfolio must be a Portfolio instance; got {type(portfolio)}")

    tot_val = portfolio.total_value
    if tot_val <= 0.0:
        raise ValueError(f"Cannot analyze concentration of a non-positive portfolio (value={tot_val})")

    asset_weights = portfolio.weights
    asset_hhi_dec, asset_hhi_pts = calculate_hhi(asset_weights)

    sector_values, sector_weights = calculate_sector_allocations(portfolio)
    sector_hhi_dec, sector_hhi_pts = calculate_hhi(sector_weights)

    return ConcentrationAnalysis(
        total_market_value=tot_val,
        asset_weights=asset_weights,
        sector_market_values=sector_values,
        sector_weights=sector_weights,
        asset_hhi_decimal=asset_hhi_dec,
        asset_hhi_points=asset_hhi_pts,
        sector_hhi_decimal=sector_hhi_dec,
        sector_hhi_points=sector_hhi_pts,
    )
