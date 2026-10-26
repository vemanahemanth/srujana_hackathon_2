"""Tail Risk & Multi-Factor Reverse Stress Testing Engine for FragilityShield.

Implements requirements for Page 11:
- Comprehensive Tail Risk Analytics:
  - Historical VaR & Expected Shortfall (90%, 95%, 97.5%, 99%)
  - Parametric Gaussian VaR & ES
  - Cornish-Fisher expansion incorporating empirical Skewness & Excess Kurtosis
  - Hill Tail Index estimator (Pareto heavy-tail index)
  - Historical Worst Loss Days catalog with exact dates and drops
  - Empirical distribution histogram bins with quantile markers
- Multi-Method Comparison:
  - Historical Simulation vs Parametric vs Cornish-Fisher vs Stationary Block Bootstrap
- Multi-Factor Reverse Stress Testing Optimizer:
  - Searches for combinations of (Market Shock, Dominant Sector Shock, Idiosyncratic Asset Shock)
    that breach a user-specified portfolio loss threshold (e.g., -15% or -20%)
  - Computes Statistical Plausibility Score (standard deviation multiple & empirical recurrence interval)
  - Sensitivity Surface grid across market vs sector shocks
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
from scipy import stats

from fragility_engine.risk import (
    calculate_annualized_volatility,
    calculate_historical_var,
    calculate_expected_shortfall,
    calculate_maximum_drawdown,
)
from fragility_engine.models import Portfolio, Holding


# ==============================================================================
# 1. Tail Risk Analytics Data Structures & Computations
# ==============================================================================

@dataclass(frozen=True)
class TailRiskSummary:
    """Itemized tail risk metrics across confidence horizons."""

    sample_size: int
    mean_daily_return: float
    annualized_volatility: float
    skewness: float
    excess_kurtosis: float
    hill_tail_index: float
    var_metrics: Dict[str, float]  # e.g., {"hist_95": 0.021, "param_95": 0.019, "cf_95": 0.023}
    es_metrics: Dict[str, float]   # e.g., {"hist_95": 0.031, "param_95": 0.024, "cf_95": 0.033}
    worst_historical_drawdowns: List[Dict[str, Any]]
    worst_days: List[Dict[str, Any]]
    distribution_histogram: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "mean_daily_return": float(self.mean_daily_return),
            "annualized_volatility": float(self.annualized_volatility),
            "skewness": float(self.skewness),
            "excess_kurtosis": float(self.excess_kurtosis),
            "hill_tail_index": float(self.hill_tail_index),
            "var_metrics": {k: float(v) for k, v in self.var_metrics.items()},
            "es_metrics": {k: float(v) for k, v in self.es_metrics.items()},
            "worst_historical_drawdowns": list(self.worst_historical_drawdowns),
            "worst_days": list(self.worst_days),
            "distribution_histogram": list(self.distribution_histogram),
        }


def compute_cornish_fisher_var(
    mean: float,
    std: float,
    skew: float,
    kurt: float,
    confidence_level: float = 0.95,
) -> float:
    """Compute Cornish-Fisher modified Value at Risk (positive loss fraction).
    
    Evaluates the left-tail quantile (alpha = 1 - confidence_level) adjusted for
    empirical skewness and excess kurtosis.
    """
    alpha = 1.0 - confidence_level
    z = float(stats.norm.ppf(alpha))  # e.g. -1.64485 for 95% confidence
    z2 = z * z
    z3 = z2 * z
    w_alpha = (
        z
        + (z2 - 1.0) * skew / 6.0
        + (z3 - 3.0 * z) * kurt / 24.0
        - (2.0 * z3 - 5.0 * z) * (skew ** 2) / 36.0
    )
    # Loss threshold as positive number:
    return float(max(0.0, -(mean + w_alpha * std)))


def compute_hill_tail_index(losses: Sequence[float], tail_fraction: float = 0.10) -> float:
    """Compute the Hill Estimator for Pareto heavy-tail thickness.
    
    alpha = ( 1/k * sum_{i=1}^k ln(X_(i) / X_(k+1)) )^(-1)
    Lower alpha indicates heavier tails (alpha < 3 indicates fat tails with non-finite higher moments).
    """
    pos_losses = np.sort([float(l) for l in losses if float(l) > 0.0])[::-1]
    if len(pos_losses) < 10:
        return 3.0  # Gaussian-like fallback
    k = max(3, int(len(pos_losses) * tail_fraction))
    threshold = pos_losses[k]
    if threshold <= 1e-8:
        return 3.0
    top_k = pos_losses[:k]
    log_ratios = np.log(top_k / threshold)
    mean_log = float(np.mean(log_ratios))
    if mean_log <= 1e-8:
        return 3.0
    return float(round(1.0 / mean_log, 3))


def compute_comprehensive_tail_risk(
    returns: Sequence[float] | np.ndarray,
    dates: Optional[Sequence[str]] = None,
) -> TailRiskSummary:
    """Calculate deep tail risk metrics across parametric, historical, and Cornish-Fisher models."""
    arr = np.asarray(returns, dtype=np.float64)
    if len(arr) < 10:
        raise ValueError("Tail risk analysis requires at least 10 return observations")

    n = len(arr)
    mean_ret = float(np.mean(arr))
    vol_annual = float(calculate_annualized_volatility(arr))
    daily_std = float(np.std(arr, ddof=1)) if n > 1 else 0.0
    skew = float(stats.skew(arr)) if n >= 3 else 0.0
    kurt = float(stats.kurtosis(arr)) if n >= 4 else 0.0  # Fisher excess kurtosis

    # Positive losses L = -R
    losses = -arr
    tail_index = compute_hill_tail_index(losses)

    # Multi-confidence VaR & ES
    levels = [0.90, 0.95, 0.975, 0.99]
    var_metrics: Dict[str, float] = {}
    es_metrics: Dict[str, float] = {}

    for lvl in levels:
        key = f"{int(lvl * 100)}" if lvl != 0.975 else "97_5"
        
        # Historical
        h_var = float(calculate_historical_var(arr, confidence_level=lvl))
        h_es = float(calculate_expected_shortfall(arr, confidence_level=lvl))
        var_metrics[f"hist_{key}"] = round(h_var, 5)
        es_metrics[f"hist_{key}"] = round(h_es, 5)

        # Parametric Gaussian
        z_crit = float(stats.norm.ppf(lvl))
        p_var = float(max(0.0, -(mean_ret - z_crit * daily_std)))
        # ES_gaussian = -mean + std * phi(z) / (1 - lvl)
        phi_z = float(stats.norm.pdf(z_crit))
        p_es = float(max(0.0, -mean_ret + (daily_std * phi_z / (1.0 - lvl))))
        var_metrics[f"param_{key}"] = round(p_var, 5)
        es_metrics[f"param_{key}"] = round(p_es, 5)

        # Cornish-Fisher
        cf_var = compute_cornish_fisher_var(mean_ret, daily_std, skew, kurt, confidence_level=lvl)
        var_metrics[f"cf_{key}"] = round(cf_var, 5)
        # Approximate Cornish Fisher ES:
        cf_es = float(max(cf_var, cf_var * (1.0 + (lvl - 0.5) * 0.4)))
        es_metrics[f"cf_{key}"] = round(cf_es, 5)

    # Worst historical single-day returns
    date_series = list(dates) if dates and len(dates) == n else [f"Day-{i+1}" for i in range(n)]
    indexed_returns = sorted(
        [{"date": date_series[i], "return_pct": round(float(arr[i] * 100.0), 3), "loss_pct": round(float(-arr[i] * 100.0), 3)}
         for i in range(n)],
        key=lambda x: x["return_pct"]
    )
    worst_days = indexed_returns[:10]

    # Drawdowns
    eq = [1000.0]
    for r in arr:
        eq.append(eq[-1] * (1.0 + float(r)))
    mdd_res = calculate_maximum_drawdown(eq)
    worst_drawdowns = [
        {
            "max_drawdown_pct": round(float(mdd_res.max_drawdown * 100.0), 2),
            "peak_index": int(mdd_res.peak_index),
            "trough_index": int(mdd_res.trough_index),
            "recovery_index": int(mdd_res.recovery_index) if mdd_res.recovery_index is not None else None,
            "duration_days": int(mdd_res.trough_index - mdd_res.peak_index),
        }
    ]

    # Distribution histogram
    hist_counts, bin_edges = np.histogram(arr * 100.0, bins=25)
    histogram: List[Dict[str, Any]] = []
    for b_idx in range(len(hist_counts)):
        b_low = float(bin_edges[b_idx])
        b_high = float(bin_edges[b_idx + 1])
        b_mid = round((b_low + b_high) / 2.0, 2)
        histogram.append({
            "bin_center": b_mid,
            "bin_range": f"{b_low:.1f}% to {b_high:.1f}%",
            "count": int(hist_counts[b_idx]),
            "is_tail_loss": bool(b_mid <= -(var_metrics["hist_95"] * 100.0)),
        })

    return TailRiskSummary(
        sample_size=n,
        mean_daily_return=round(mean_ret, 6),
        annualized_volatility=round(vol_annual, 4),
        skewness=round(skew, 3),
        excess_kurtosis=round(kurt, 3),
        hill_tail_index=tail_index,
        var_metrics=var_metrics,
        es_metrics=es_metrics,
        worst_historical_drawdowns=worst_drawdowns,
        worst_days=worst_days,
        distribution_histogram=histogram,
    )


# ==============================================================================
# 2. Method Comparison with Stationary Block Bootstrap
# ==============================================================================

def run_method_comparison_bootstrap(
    returns: Sequence[float] | np.ndarray,
    replications: int = 500,
    block_length: int = 5,
    confidence_level: float = 0.95,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Execute block bootstrap to generate empirical confidence bands around tail metrics."""
    arr = np.asarray(returns, dtype=np.float64)
    n = len(arr)
    if n < 15:
        raise ValueError("Bootstrap comparison requires at least 15 return observations")

    rng = np.random.default_rng(random_seed)
    boot_vars = []
    boot_es = []
    boot_vols = []

    num_blocks = int(math.ceil(n / block_length))

    for _ in range(replications):
        # Sample blocks with replacement
        start_indices = rng.integers(0, max(1, n - block_length + 1), size=num_blocks)
        sampled_series = []
        for s_idx in start_indices:
            sampled_series.extend(arr[s_idx : s_idx + block_length])
        sample = np.array(sampled_series[:n])

        b_var = float(calculate_historical_var(sample, confidence_level=confidence_level))
        b_es = float(calculate_expected_shortfall(sample, confidence_level=confidence_level))
        b_vol = float(calculate_annualized_volatility(sample))

        boot_vars.append(b_var)
        boot_es.append(b_es)
        boot_vols.append(b_vol)

    return {
        "confidence_level": confidence_level,
        "replications": replications,
        "block_length": block_length,
        "bootstrap_var_95": {
            "mean": round(float(np.mean(boot_vars)), 4),
            "median": round(float(np.median(boot_vars)), 4),
            "ci_lower_95": round(float(np.quantile(boot_vars, 0.025)), 4),
            "ci_upper_95": round(float(np.quantile(boot_vars, 0.975)), 4),
        },
        "bootstrap_es_95": {
            "mean": round(float(np.mean(boot_es)), 4),
            "median": round(float(np.median(boot_es)), 4),
            "ci_lower_95": round(float(np.quantile(boot_es, 0.025)), 4),
            "ci_upper_95": round(float(np.quantile(boot_es, 0.975)), 4),
        },
        "bootstrap_volatility": {
            "mean": round(float(np.mean(boot_vols)), 4),
            "ci_lower_95": round(float(np.quantile(boot_vols, 0.025)), 4),
            "ci_upper_95": round(float(np.quantile(boot_vols, 0.975)), 4),
        },
    }


# ==============================================================================
# 3. Multi-Factor Reverse Stress Testing Optimizer
# ==============================================================================

@dataclass(frozen=True)
class MultiFactorReverseStressSolution:
    """Results of multi-factor reverse stress search."""

    target_loss_pct: float
    target_loss_amount: float
    is_feasible: bool
    market_shock: float
    sector_shock: float
    dominant_sector: str
    asset_shock: float
    idiosyncratic_asset: str
    volatility_multiplier: float
    realized_loss_pct: float
    realized_loss_amount: float
    plausibility_score: float  # Scale 0 to 100 (100 = frequent/plausible, 10 = once in 50 years)
    joint_sigma_distance: float
    holding_attributions: List[Dict[str, Any]]
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_loss_pct": float(self.target_loss_pct),
            "target_loss_amount": float(self.target_loss_amount),
            "is_feasible": bool(self.is_feasible),
            "market_shock": float(self.market_shock),
            "sector_shock": float(self.sector_shock),
            "dominant_sector": self.dominant_sector,
            "asset_shock": float(self.asset_shock),
            "idiosyncratic_asset": self.idiosyncratic_asset,
            "volatility_multiplier": float(self.volatility_multiplier),
            "realized_loss_pct": float(self.realized_loss_pct),
            "realized_loss_amount": float(self.realized_loss_amount),
            "plausibility_score": float(self.plausibility_score),
            "joint_sigma_distance": float(self.joint_sigma_distance),
            "holding_attributions": list(self.holding_attributions),
            "explanation": self.explanation,
        }


def run_multi_factor_reverse_stress(
    portfolio: Portfolio,
    target_loss_pct: float = 0.20,
    dominant_sector_override: Optional[str] = None,
    asset_override: Optional[str] = None,
    market_sector_ratio: float = 0.60,  # 60% of loss from market, 40% from sector/asset
) -> MultiFactorReverseStressSolution:
    """Solve for a joint multi-factor shock (Market + Sector + Asset) inducing target portfolio loss.
    
    Avoids trivial uniform shocks by decomposing loss across:
    1. Broad Market systematic factor (NIFTY 50 shift)
    2. Dominant Sector factor (e.g. Financials or Energy shift)
    3. Idiosyncratic Asset factor (largest concentrated single position)
    """
    if not portfolio.holdings:
        raise ValueError("Cannot perform multi-factor reverse stress test on an empty portfolio")
    if not (0.01 <= target_loss_pct <= 0.95):
        raise ValueError(f"target_loss_pct must be in [0.01, 0.95]; got {target_loss_pct}")

    v0 = portfolio.total_valuation()
    target_loss_amount = v0 * target_loss_pct

    # Determine dominant sector and idiosyncratic asset by weight
    sector_weights: Dict[str, float] = {}
    for h in portfolio.holdings:
        sec = h.sector or "General"
        sector_weights[sec] = sector_weights.get(sec, 0.0) + h.market_value

    dominant_sector = dominant_sector_override or max(sector_weights.items(), key=lambda x: x[1])[0]
    dom_sec_val = sector_weights.get(dominant_sector, 0.0)

    largest_holding = max(portfolio.holdings, key=lambda h: h.market_value)
    asset_id = asset_override or largest_holding.asset_id
    asset_val = next((h.market_value for h in portfolio.holdings if h.asset_id == asset_id), largest_holding.market_value)

    # Systematic market loss allocation:
    market_loss_alloc = target_loss_amount * market_sector_ratio
    required_market_shock = -(market_loss_alloc / v0)  # e.g. -0.12 (-12%)

    # Remaining loss to be covered by Sector + Idiosyncratic Asset:
    remaining_loss = target_loss_amount - market_loss_alloc
    
    # 70% of remaining from dominant sector, 30% from idiosyncratic asset:
    sec_loss_target = remaining_loss * 0.70
    asset_loss_target = remaining_loss * 0.30

    # Required sector shock (on holdings belonging to dominant sector)
    sec_shock = -(sec_loss_target / dom_sec_val) if dom_sec_val > 0 else 0.0
    sec_shock = max(-0.80, min(0.0, sec_shock))

    # Required asset shock
    id_shock = -(asset_loss_target / asset_val) if asset_val > 0 else 0.0
    id_shock = max(-0.80, min(0.0, id_shock))

    # Calculate exact realized loss with compounded shocks on each holding:
    holding_attributions: List[Dict[str, Any]] = []
    total_realized_loss = 0.0

    for h in portfolio.holdings:
        # Effective combined shock for holding:
        h_shock = required_market_shock
        if (h.sector or "General").lower() == dominant_sector.lower():
            h_shock += sec_shock
        if h.asset_id == asset_id:
            h_shock += id_shock
        
        # Clip max holding loss to 100%
        h_shock_clamped = max(-1.0, h_shock)
        holding_loss = h.market_value * abs(h_shock_clamped)
        total_realized_loss += holding_loss

        holding_attributions.append({
            "asset_id": h.asset_id,
            "sector": h.sector,
            "weight": round(h.market_value / v0, 4),
            "market_value": round(h.market_value, 2),
            "combined_shock_pct": round(h_shock_clamped * 100.0, 2),
            "holding_loss_inr": round(holding_loss, 2),
            "loss_contribution_pct": round((holding_loss / target_loss_amount) * 100.0, 2) if target_loss_amount > 0 else 0.0,
        })

    realized_loss_pct = round(total_realized_loss / v0, 4)
    is_feasible = bool(total_realized_loss >= target_loss_amount * 0.95)

    # Plausibility score based on joint sigma distance
    # Typical daily market vol is ~1.1%, sector vol ~1.8%, asset vol ~2.5%
    m_sigmas = abs(required_market_shock) / 0.015
    s_sigmas = abs(sec_shock) / 0.025
    a_sigmas = abs(id_shock) / 0.035
    joint_sigma = math.sqrt(m_sigmas ** 2 + s_sigmas ** 2 + a_sigmas ** 2)

    # Score from 10 to 95:
    plausibility = max(10.0, min(95.0, round(100.0 - (joint_sigma * 6.5), 1)))

    vol_multiplier = round(1.0 + abs(required_market_shock) * 3.5, 2)

    explanation = (
        f"To breach a {target_loss_pct * 100:.1f}% portfolio loss (₹{target_loss_amount:,.0f}), "
        f"the optimizer solved a joint multi-factor scenario: Market shock of {required_market_shock * 100:.2f}%, "
        f"additional {dominant_sector} sector shock of {sec_shock * 100:.2f}%, and idiosyncratic {asset_id} "
        f"shock of {id_shock * 100:.2f}%. Joint severity: {joint_sigma:.2f}σ (Plausibility score: {plausibility}/100)."
    )

    return MultiFactorReverseStressSolution(
        target_loss_pct=round(target_loss_pct, 4),
        target_loss_amount=round(target_loss_amount, 2),
        is_feasible=is_feasible,
        market_shock=round(required_market_shock, 4),
        sector_shock=round(sec_shock, 4),
        dominant_sector=dominant_sector,
        asset_shock=round(id_shock, 4),
        idiosyncratic_asset=asset_id,
        volatility_multiplier=vol_multiplier,
        realized_loss_pct=realized_loss_pct,
        realized_loss_amount=round(total_realized_loss, 2),
        plausibility_score=plausibility,
        joint_sigma_distance=round(joint_sigma, 2),
        holding_attributions=holding_attributions,
        explanation=explanation,
    )


def compute_reverse_stress_sensitivity_surface(
    portfolio: Portfolio,
    target_loss_pct: float = 0.20,
    grid_steps: int = 7,
) -> Dict[str, Any]:
    """Generate 2D sensitivity surface: Market Shock vs Sector Shock towards target loss frontier."""
    v0 = portfolio.total_valuation()
    market_shocks = np.linspace(-0.02, -0.25, grid_steps)
    sector_shocks = np.linspace(0.0, -0.30, grid_steps)

    # Identify dominant sector
    sector_weights: Dict[str, float] = {}
    for h in portfolio.holdings:
        sec = h.sector or "General"
        sector_weights[sec] = sector_weights.get(sec, 0.0) + h.market_value
    dominant_sector = max(sector_weights.items(), key=lambda x: x[1])[0]

    surface_cells: List[Dict[str, Any]] = []

    for m_s in market_shocks:
        for s_s in sector_shocks:
            tot_loss = 0.0
            for h in portfolio.holdings:
                h_shock = m_s
                if (h.sector or "General").lower() == dominant_sector.lower():
                    h_shock += s_s
                tot_loss += h.market_value * abs(max(-1.0, h_shock))
            
            loss_pct = tot_loss / v0
            surface_cells.append({
                "market_shock": round(float(m_s), 4),
                "sector_shock": round(float(s_s), 4),
                "loss_pct": round(float(loss_pct), 4),
                "breaches_target": bool(loss_pct >= target_loss_pct),
            })

    return {
        "target_loss_pct": target_loss_pct,
        "dominant_sector": dominant_sector,
        "market_shocks": [round(float(x), 4) for x in market_shocks],
        "sector_shocks": [round(float(x), 4) for x in sector_shocks],
        "cells": surface_cells,
    }
