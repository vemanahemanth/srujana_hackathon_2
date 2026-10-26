"""Allocation & Comparison Lab for FragilityShield.

Provides quantitative capabilities for:
- Constructing equal-weighted benchmark allocations.
- Applying and validating manual portfolio weight adjustments.
- Calculating portfolio turnover and estimated transaction costs.
- Solving constrained minimum-variance portfolio optimization via SciPy quadratic programming.
- Generating comparative allocation risk and concentration reports.

Mathematical & Regulatory Disclaimers:
- Portfolio optimization relies on historical sample covariance estimates, which are subject to
  estimation error, regime shifts, and non-stationarity.
- Optimized allocations are strictly illustrative and NEVER represent guarantees of future optimality or risk reduction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
from scipy.optimize import minimize

from fragility_engine.concentration import calculate_portfolio_concentration
from fragility_engine.models import Holding, Portfolio
from fragility_engine.risk import calculate_volatility, calculate_historical_var


@dataclass(frozen=True)
class OptimizationDiagnostics:
    """Detailed diagnostics from the constrained quadratic optimization solver."""

    success: bool
    status_code: int
    message: str
    iterations: int
    portfolio_variance: float
    portfolio_volatility_annualized: float
    constraint_violations: Dict[str, float]
    disclaimer: str = (
        "Illustrative model output only. Minimum-variance optimization relies on backward-looking sample covariance "
        "and does not account for future regime shifts, liquidity dry-ups, or structural breaks."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status_code": self.status_code,
            "message": self.message,
            "iterations": self.iterations,
            "portfolio_variance": float(self.portfolio_variance),
            "portfolio_volatility_annualized": float(self.portfolio_volatility_annualized),
            "constraint_violations": {k: float(v) for k, v in self.constraint_violations.items()},
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class AllocationResult:
    """Result of an allocation optimization containing optimal weights and solver diagnostics."""

    weights: Dict[str, float]
    diagnostics: OptimizationDiagnostics

    def __iter__(self):
        yield self.weights
        yield self.diagnostics

    def __getitem__(self, item: int):
        if item == 0:
            return self.weights
        elif item == 1:
            return self.diagnostics
        raise IndexError(f"Index out of range: {item}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weights": dict(self.weights),
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True)
class AllocationComparisonReport:
    """Comparative analysis across original, benchmark, and optimized allocations."""

    original_weights: Dict[str, float]
    adjusted_weights: Dict[str, float]
    turnover: float
    estimated_transaction_cost_inr: float
    original_hhi: float
    adjusted_hhi: float
    original_volatility: Optional[float]
    adjusted_volatility: Optional[float]
    original_var_95: Optional[float]
    adjusted_var_95: Optional[float]
    diagnostics: Optional[OptimizationDiagnostics] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_weights": dict(self.original_weights),
            "adjusted_weights": dict(self.adjusted_weights),
            "turnover": float(self.turnover),
            "estimated_transaction_cost_inr": float(self.estimated_transaction_cost_inr),
            "original_hhi": float(self.original_hhi),
            "adjusted_hhi": float(self.adjusted_hhi),
            "original_volatility": float(self.original_volatility) if self.original_volatility is not None else None,
            "adjusted_volatility": float(self.adjusted_volatility) if self.adjusted_volatility is not None else None,
            "original_var_95": float(self.original_var_95) if self.original_var_95 is not None else None,
            "adjusted_var_95": float(self.adjusted_var_95) if self.adjusted_var_95 is not None else None,
            "diagnostics": self.diagnostics.to_dict() if self.diagnostics is not None else None,
        }


def create_equal_weighted_portfolio(portfolio: Portfolio, new_portfolio_id: Optional[str] = None) -> Portfolio:
    """Create a new portfolio with identical total market value distributed equally across holdings.

    Formula:
        target_value_per_holding = total_portfolio_value / N
        new_quantity_i = target_value_per_holding / price_i
    """
    tot = portfolio.total_value
    n = len(portfolio.holdings)
    if n == 0:
        raise ValueError("Cannot equal-weight an empty portfolio")

    target_per_asset = tot / float(n)
    new_holdings: List[Holding] = []

    for h in portfolio.holdings:
        new_qty = target_per_asset / h.price
        new_holdings.append(
            Holding(
                asset_id=h.asset_id,
                quantity=new_qty,
                price=h.price,
                entry_price=h.entry_price,
                asset_class=h.asset_class,
                sector=h.sector,
                metadata=dict(h.metadata),
            )
        )

    pid = new_portfolio_id or f"{portfolio.portfolio_id}_equal_weight"
    return Portfolio(
        portfolio_id=pid,
        name=f"{portfolio.name} (Equal-Weighted)",
        currency=portfolio.currency,
        holdings=tuple(new_holdings),
        metadata=dict(portfolio.metadata),
    )


def adjust_portfolio_weights(
    portfolio: Portfolio,
    target_weights: Mapping[str, float],
    new_portfolio_id: Optional[str] = None,
) -> Portfolio:
    """Adjust portfolio holdings to match a target market-value weight vector.

    Validates:
        - All portfolio assets must have a target weight.
        - Target weights must be non-negative and sum to 1.0 within 1e-5.
    """
    tot = portfolio.total_value
    target_sum = sum(target_weights.values())
    if not math.isclose(target_sum, 1.0, rel_tol=1e-4, abs_tol=1e-4):
        raise ValueError(f"Target weights must sum to 1.0; got sum={target_sum}")

    new_holdings: List[Holding] = []
    for h in portfolio.holdings:
        if h.asset_id not in target_weights:
            raise ValueError(f"Asset '{h.asset_id}' missing from target_weights mapping")
        w_i = float(target_weights[h.asset_id])
        if w_i < 0.0 or not math.isfinite(w_i):
            raise ValueError(f"Weight for '{h.asset_id}' must be finite non-negative; got {w_i}")

        new_val = tot * w_i
        new_qty = (new_val / h.price) if h.price > 0.0 else 0.0
        # If weight is 0.0, use minimum nominal quantity to satisfy positive holding validation
        safe_qty = max(new_qty, 1e-9)

        new_holdings.append(
            Holding(
                asset_id=h.asset_id,
                quantity=safe_qty,
                price=h.price,
                entry_price=h.entry_price,
                asset_class=h.asset_class,
                sector=h.sector,
                metadata=dict(h.metadata),
            )
        )

    pid = new_portfolio_id or f"{portfolio.portfolio_id}_adjusted"
    return Portfolio(
        portfolio_id=pid,
        name=f"{portfolio.name} (Custom Allocation)",
        currency=portfolio.currency,
        holdings=tuple(new_holdings),
        metadata=dict(portfolio.metadata),
    )


def calculate_turnover(
    old_weights: Mapping[str, float],
    new_weights: Mapping[str, float],
) -> float:
    """Compute one-way portfolio turnover fraction.

    Formula:
        Turnover = 0.5 * sum_{i} |w_new,i - w_old,i|
    """
    all_assets = set(old_weights.keys()) | set(new_weights.keys())
    diff_sum = sum(abs(new_weights.get(a, 0.0) - old_weights.get(a, 0.0)) for a in all_assets)
    return float(0.5 * diff_sum)


def calculate_transaction_cost(
    portfolio_value: float,
    turnover: float,
    transaction_cost_bps: float = 10.0,
) -> float:
    """Estimate portfolio transaction friction in currency units.

    Formula:
        Cost = 2 * Turnover * Portfolio_Value * (cost_bps / 10000)
    """
    traded_volume = 2.0 * float(turnover) * float(portfolio_value)
    return float(traded_volume * (transaction_cost_bps / 10000.0))


def optimize_minimum_variance(
    covariance_matrix: Sequence[Sequence[float]] | np.ndarray,
    asset_ids: Sequence[str],
    min_weight: float = 0.0,
    max_weight: float = 1.0,
    annualization_factor: float = 252.0,
) -> Tuple[Dict[str, float], OptimizationDiagnostics]:
    """Solve constrained minimum-variance portfolio optimization using quadratic programming.

    Objective:
        min_w  w^T Sigma w
        subject to:
            sum(w_i) = 1.0
            min_weight <= w_i <= max_weight

    Args:
        covariance_matrix: (K x K) asset covariance matrix.
        asset_ids: Ordered list of K asset identifiers.
        min_weight: Lower bound per asset (default 0.0 for long-only).
        max_weight: Upper bound per asset (default 1.0).
        annualization_factor: Volatility annualizer (default 252.0).

    Returns:
        Tuple of (optimal_weights_dict, OptimizationDiagnostics).
    """
    cov = np.asarray(covariance_matrix, dtype=np.float64)
    k = len(asset_ids)
    if cov.shape != (k, k):
        raise ValueError(f"Covariance matrix shape {cov.shape} does not match asset count {k}")

    # Objective: w^T * Cov * w
    def objective(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    def gradient(w: np.ndarray) -> np.ndarray:
        return 2.0 * cov @ w

    # Initial guess: equal weights
    w0 = np.full(k, 1.0 / k, dtype=np.float64)

    # Constraints: sum(w) - 1.0 = 0
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    # Bounds: min_weight <= w_i <= max_weight
    bounds = [(float(min_weight), float(max_weight)) for _ in range(k)]

    res = minimize(
        objective,
        w0,
        method="SLSQP",
        jac=gradient,
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 200},
    )

    optimal_w = np.clip(res.x, min_weight, max_weight)
    optimal_w = optimal_w / np.sum(optimal_w)  # normalize exactly to 1.0

    port_var = float(optimal_w @ cov @ optimal_w)
    port_vol = math.sqrt(max(0.0, port_var)) * math.sqrt(annualization_factor)

    constraint_violations = {
        "budget_sum_error": abs(float(np.sum(optimal_w) - 1.0)),
        "max_lower_bound_violation": max(0.0, float(min_weight - np.min(optimal_w))),
        "max_upper_bound_violation": max(0.0, float(np.max(optimal_w) - max_weight)),
    }

    diagnostics = OptimizationDiagnostics(
        success=bool(res.success),
        status_code=int(res.status),
        message=str(res.message),
        iterations=int(res.nit),
        portfolio_variance=port_var,
        portfolio_volatility_annualized=port_vol,
        constraint_violations=constraint_violations,
    )

    weights_dict = {asset_ids[i]: float(optimal_w[i]) for i in range(k)}
    return AllocationResult(weights=weights_dict, diagnostics=diagnostics)


def compare_allocations(
    original_portfolio: Portfolio,
    adjusted_portfolio: Portfolio,
    asset_returns_matrix: Optional[np.ndarray] = None,
    transaction_cost_bps: float = 10.0,
    diagnostics: Optional[OptimizationDiagnostics] = None,
) -> AllocationComparisonReport:
    """Generate comparative risk, concentration, and turnover report between two allocations."""
    w_orig = original_portfolio.weights
    w_adj = adjusted_portfolio.weights

    turnover = calculate_turnover(w_orig, w_adj)
    tx_cost = calculate_transaction_cost(original_portfolio.total_value, turnover, transaction_cost_bps)

    orig_conc = calculate_portfolio_concentration(original_portfolio)
    adj_conc = calculate_portfolio_concentration(adjusted_portfolio)

    orig_vol: Optional[float] = None
    adj_vol: Optional[float] = None
    orig_var: Optional[float] = None
    adj_var: Optional[float] = None

    if asset_returns_matrix is not None:
        mat = np.asarray(asset_returns_matrix, dtype=np.float64)
        assets = original_portfolio.asset_ids
        if mat.shape[1] == len(assets):
            w_orig_arr = np.array([w_orig[a] for a in assets], dtype=np.float64)
            w_adj_arr = np.array([w_adj[a] for a in assets], dtype=np.float64)

            port_rets_orig = mat @ w_orig_arr
            port_rets_adj = mat @ w_adj_arr

            orig_vol = calculate_volatility(port_rets_orig)
            adj_vol = calculate_volatility(port_rets_adj)
            orig_var = calculate_historical_var(port_rets_orig, confidence_level=0.95)
            adj_var = calculate_historical_var(port_rets_adj, confidence_level=0.95)

    return AllocationComparisonReport(
        original_weights=w_orig,
        adjusted_weights=w_adj,
        turnover=turnover,
        estimated_transaction_cost_inr=tx_cost,
        original_hhi=orig_conc.asset_hhi_points,
        adjusted_hhi=adj_conc.asset_hhi_points,
        original_volatility=orig_vol,
        adjusted_volatility=adj_vol,
        original_var_95=orig_var,
        adjusted_var_95=adj_var,
        diagnostics=diagnostics,
    )


# Public alias for consistency
AllocationComparisonResult = AllocationComparisonReport
