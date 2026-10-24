"""FragilityShield — Fragility Lab Engine (Phase 5).

This module implements the Fragility Lab, a deterministic risk and model
robustness testing laboratory.

Core Purpose:
- Evaluate how sensitive quantitative risk estimates and model conclusions
  are to changes in underlying assumptions, sample lookback windows,
  volatility estimators, transaction frictions, and correlation structures.
- Identify which assumptions have the greatest impact on reported portfolio risk.
- Ensure transparent sensitivity rankings without arbitrary synthetic scoring.
- Uphold strict financial integrity: never fabricate missing timestamps,
  trade history, or multivariate returns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np

from fragility_engine.models import Portfolio
from fragility_engine.risk import (
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)


@dataclass(frozen=True)
class PerturbationImpact:
    """Quantitative impact of a single parameter perturbation on a specific metric.

    Attributes:
        perturbation_id: Identifier of the perturbation model.
        perturbation_name: Descriptive name.
        parameter_name: Perturbed parameter identifier.
        parameter_value: Value of the parameter in this run.
        baseline_value: Metric value under baseline assumptions.
        perturbed_value: Metric value under perturbed assumptions.
        absolute_change: M1 - M0.
        relative_change: (M1 - M0) / abs(M0) when M0 != 0, else None.
        warning: Optional diagnostic warning.
    """

    perturbation_id: str
    perturbation_name: str
    parameter_name: str
    parameter_value: Any
    baseline_value: float
    perturbed_value: float
    absolute_change: float
    relative_change: Optional[float]
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert impact to dictionary."""
        return {
            "perturbation_id": self.perturbation_id,
            "perturbation_name": self.perturbation_name,
            "parameter_name": self.parameter_name,
            "parameter_value": self.parameter_value,
            "baseline_value": self.baseline_value,
            "perturbed_value": self.perturbed_value,
            "absolute_change": self.absolute_change,
            "relative_change": self.relative_change,
            "warning": self.warning,
        }


@dataclass(frozen=True)
class FragilityExperimentResult:
    """Structured result of a single fragility perturbation experiment.

    Attributes:
        experiment_id: Unique identifier of this experiment run.
        perturbation_id: Stable identifier of the perturbation in the registry.
        perturbation_name: Human-readable perturbation name.
        description: Methodological description of what was challenged.
        configuration: Parameters used for baseline and perturbed evaluations.
        baseline_metrics: Mapping of metric identifier to baseline value.
        perturbed_metrics: Mapping of metric identifier to perturbed value.
        absolute_changes: Mapping of metric identifier to (perturbed - baseline).
        relative_changes: Mapping of metric identifier to relative change.
        observations_used: Number of observations utilized in the perturbed evaluation.
        warnings: List of diagnostic caveats.
        limitations: Explicit statement of assumptions and data boundaries.
        metadata: Additional contextual metadata.
    """

    experiment_id: str
    perturbation_id: str
    perturbation_name: str
    description: str
    configuration: Mapping[str, Any]
    baseline_metrics: Mapping[str, float]
    perturbed_metrics: Mapping[str, float]
    absolute_changes: Mapping[str, float]
    relative_changes: Mapping[str, Optional[float]]
    observations_used: int
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    limitations: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert experiment result to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "perturbation_id": self.perturbation_id,
            "perturbation_name": self.perturbation_name,
            "description": self.description,
            "configuration": dict(self.configuration),
            "baseline_metrics": dict(self.baseline_metrics),
            "perturbed_metrics": dict(self.perturbed_metrics),
            "absolute_changes": dict(self.absolute_changes),
            "relative_changes": dict(self.relative_changes),
            "observations_used": self.observations_used,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MetricSensitivityRanking:
    """Ordered ranking of perturbation impacts for a designated metric.

    Attributes:
        metric_id: Identifier of the metric being ranked.
        baseline_value: Baseline value of the metric.
        ranked_impacts: Tuple of PerturbationImpact sorted by descending absolute impact.
        most_sensitive_perturbation: Perturbation with the largest absolute impact, or None.
        max_absolute_change: Largest absolute change observed across perturbations.
        max_relative_change: Largest relative change observed, or None.
    """

    metric_id: str
    baseline_value: float
    ranked_impacts: Tuple[PerturbationImpact, ...]
    most_sensitive_perturbation: Optional[str]
    max_absolute_change: float
    max_relative_change: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert ranking to dictionary."""
        return {
            "metric_id": self.metric_id,
            "baseline_value": self.baseline_value,
            "ranked_impacts": [imp.to_dict() for imp in self.ranked_impacts],
            "most_sensitive_perturbation": self.most_sensitive_perturbation,
            "max_absolute_change": self.max_absolute_change,
            "max_relative_change": self.max_relative_change,
        }


# ==============================================================================
# Helper Functions for Comparison
# ==============================================================================

def compute_changes(
    baseline: Mapping[str, float],
    perturbed: Mapping[str, float],
) -> Tuple[Dict[str, float], Dict[str, Optional[float]]]:
    """Calculate absolute and relative changes between baseline and perturbed metrics.

    Formulas:
        delta = M1 - M0
        relative_delta = (M1 - M0) / abs(M0)  if M0 != 0 else None

    Args:
        baseline: Mapping of metric identifier to baseline numeric value.
        perturbed: Mapping of metric identifier to perturbed numeric value.

    Returns:
        Tuple of (absolute_changes, relative_changes).
    """
    abs_changes: Dict[str, float] = {}
    rel_changes: Dict[str, Optional[float]] = {}

    for metric, m0 in baseline.items():
        if metric in perturbed:
            m1 = perturbed[metric]
            delta = m1 - m0
            abs_changes[metric] = delta
            if abs(m0) > 1e-15 and math.isfinite(m0):
                rel_changes[metric] = delta / abs(m0)
            else:
                rel_changes[metric] = None

    return abs_changes, rel_changes


def _compute_core_metrics(
    returns: Sequence[float] | np.ndarray,
    annualization_factor: float = 252.0,
) -> Dict[str, float]:
    """Helper to compute standard risk metrics from returns array."""
    rep = calculate_risk_report(returns, annualization_factor=annualization_factor)
    metrics = {
        "volatility_daily": rep.volatility_daily,
        "volatility_annualized": rep.volatility_annualized,
        "var_95": rep.var_95,
        "var_99": rep.var_99,
        "expected_shortfall_95": rep.expected_shortfall_95,
        "expected_shortfall_99": rep.expected_shortfall_99,
    }
    if rep.drawdown is not None:
        metrics["max_drawdown"] = rep.drawdown.max_drawdown
    return metrics


# ==============================================================================
# 1. Lookback Window Perturbation
# ==============================================================================

def run_lookback_perturbation(
    returns: Sequence[float] | np.ndarray,
    perturbed_window: int,
    baseline_window: Optional[int] = None,
    annualization_factor: float = 252.0,
    experiment_id: str = "exp_lookback_window",
) -> FragilityExperimentResult:
    """Evaluate how risk estimates change when the sample lookback window is altered.

    Args:
        returns: Full chronological sequence of historical returns.
        perturbed_window: Number of recent observations to use in perturbed run (>= 2).
        baseline_window: Optional number of recent observations for baseline (defaults to all).
        annualization_factor: Annualization factor (default 252.0).
        experiment_id: Identifier for this experiment run.

    Returns:
        FragilityExperimentResult detailing baseline vs perturbed metrics.
    """
    if returns is None:
        raise TypeError("returns sequence cannot be None")
    arr = np.asarray(returns, dtype=np.float64)
    total_obs = len(arr)

    if total_obs < 2:
        raise ValueError(f"Lookback perturbation requires at least 2 observations; got {total_obs}")

    b_win = total_obs if baseline_window is None else baseline_window
    if not isinstance(b_win, int) or b_win < 2 or b_win > total_obs:
        raise ValueError(f"baseline_window must be an integer between 2 and {total_obs}; got {baseline_window}")

    if not isinstance(perturbed_window, int) or perturbed_window < 2 or perturbed_window > total_obs:
        raise ValueError(f"perturbed_window must be an integer between 2 and {total_obs}; got {perturbed_window}")

    # Chronologically take recent observations
    baseline_sample = arr[-b_win:]
    perturbed_sample = arr[-perturbed_window:]

    baseline_metrics = _compute_core_metrics(baseline_sample, annualization_factor)
    perturbed_metrics = _compute_core_metrics(perturbed_sample, annualization_factor)

    abs_changes, rel_changes = compute_changes(baseline_metrics, perturbed_metrics)

    warnings: List[str] = []
    if perturbed_window < 20:
        warnings.append(f"Perturbed window ({perturbed_window}) is small; tail quantile estimates have high variance.")

    limitations = (
        "Lookback perturbation assumes returns are identically distributed within the selected window.",
        "Does not interpolate missing dates or reconstruct intraday data.",
    )

    config = {
        "baseline_window": b_win,
        "perturbed_window": perturbed_window,
        "total_available_observations": total_obs,
        "annualization_factor": annualization_factor,
    }

    return FragilityExperimentResult(
        experiment_id=experiment_id,
        perturbation_id="lookback_window",
        perturbation_name="Lookback Window Perturbation",
        description=f"Assesses risk sensitivity to truncating sample lookback from {b_win} to {perturbed_window} observations.",
        configuration=config,
        baseline_metrics=baseline_metrics,
        perturbed_metrics=perturbed_metrics,
        absolute_changes=abs_changes,
        relative_changes=rel_changes,
        observations_used=perturbed_window,
        warnings=tuple(warnings),
        limitations=limitations,
    )


# ==============================================================================
# 2. Alternative Volatility Estimator (EWMA)
# ==============================================================================

def calculate_ewma_volatility(
    returns: Sequence[float] | np.ndarray,
    decay_factor: float = 0.94,
    annualization_factor: float = 252.0,
) -> float:
    """Calculate annualized Exponentially Weighted Moving Average (EWMA) volatility.

    Formula (RiskMetrics standard):
        sigma_t^2 = lambda * sigma_{t-1}^2 + (1 - lambda) * r_t^2
        sigma_annual = sqrt(sigma_T^2) * sqrt(annualization_factor)

    Initialization:
        sigma_0^2 = sum(r_i^2) / N  (uncentered sample variance)

    Args:
        returns: Sequence of periodic returns.
        decay_factor: Lambda parameter in range (0.0, 1.0), standard default 0.94.
        annualization_factor: Annualization multiplier (default 252.0).

    Returns:
        Annualized EWMA volatility as a float.
    """
    if returns is None:
        raise TypeError("returns sequence cannot be None")
    arr = np.asarray(returns, dtype=np.float64)
    if len(arr) < 2:
        raise ValueError(f"EWMA volatility requires at least 2 observations; got {len(arr)}")

    if not isinstance(decay_factor, (int, float)) or isinstance(decay_factor, bool):
        raise ValueError(f"decay_factor must be a float between 0.0 and 1.0; got {decay_factor!r}")
    lam = float(decay_factor)
    if not math.isfinite(lam) or lam <= 0.0 or lam >= 1.0:
        raise ValueError(f"decay_factor must be strictly between 0.0 and 1.0; got {decay_factor!r}")

    # Check finite
    if not np.all(np.isfinite(arr)):
        raise ValueError("Returns must contain strictly finite values")

    # Initial variance estimate
    var_t = float(np.mean(arr ** 2))
    for r in arr:
        var_t = lam * var_t + (1.0 - lam) * float(r ** 2)

    daily_vol = math.sqrt(var_t)
    return daily_vol * math.sqrt(annualization_factor)


def run_volatility_estimator_perturbation(
    returns: Sequence[float] | np.ndarray,
    decay_factor: float = 0.94,
    annualization_factor: float = 252.0,
    experiment_id: str = "exp_volatility_estimator",
) -> FragilityExperimentResult:
    """Compare baseline sample standard deviation against EWMA volatility.

    Args:
        returns: Sequence of periodic returns.
        decay_factor: Exponential decay parameter lambda (default 0.94).
        annualization_factor: Annualization factor (default 252.0).
        experiment_id: Unique experiment run identifier.

    Returns:
        FragilityExperimentResult comparing standard sample vol vs EWMA vol.
    """
    arr = np.asarray(returns, dtype=np.float64)
    baseline_vol = calculate_annualized_volatility(arr, annualization_factor=annualization_factor, ddof=1)
    ewma_vol = calculate_ewma_volatility(arr, decay_factor=decay_factor, annualization_factor=annualization_factor)

    baseline_metrics = {"volatility_annualized": baseline_vol}
    perturbed_metrics = {"volatility_annualized": ewma_vol}

    abs_changes, rel_changes = compute_changes(baseline_metrics, perturbed_metrics)

    config = {
        "decay_factor": decay_factor,
        "annualization_factor": annualization_factor,
        "baseline_estimator": "sample_standard_deviation_ddof_1",
        "perturbed_estimator": "ewma_riskmetrics",
    }

    limitations = (
        "EWMA places higher weight on recent shocks and assumes zero-mean returns.",
        "Annualization assumes independent and identically distributed returns.",
    )

    return FragilityExperimentResult(
        experiment_id=experiment_id,
        perturbation_id="volatility_estimator_ewma",
        perturbation_name="Alternative Volatility Estimator (EWMA)",
        description=f"Compares sample standard deviation (ddof=1) against EWMA (lambda={decay_factor}).",
        configuration=config,
        baseline_metrics=baseline_metrics,
        perturbed_metrics=perturbed_metrics,
        absolute_changes=abs_changes,
        relative_changes=rel_changes,
        observations_used=len(arr),
        warnings=(),
        limitations=limitations,
    )


# ==============================================================================
# 3. Transaction Cost & Friction Shock
# ==============================================================================

def run_return_friction_perturbation(
    returns: Sequence[float] | np.ndarray,
    friction_bps: float,
    annualization_factor: float = 252.0,
    experiment_id: str = "exp_return_friction",
) -> FragilityExperimentResult:
    """Assess risk metric sensitivity when periodic returns are shocked by trading friction.

    Formula:
        r_t' = r_t - (friction_bps / 10,000)

    Args:
        returns: Sequence of simple returns.
        friction_bps: Periodic friction in basis points (e.g. 5.0 for 5 bps per period).
        annualization_factor: Annualization factor (default 252.0).
        experiment_id: Unique experiment run identifier.

    Returns:
        FragilityExperimentResult detailing the impact of periodic friction drag.
    """
    arr = np.asarray(returns, dtype=np.float64)
    if not isinstance(friction_bps, (int, float)) or isinstance(friction_bps, bool) or not math.isfinite(friction_bps):
        raise ValueError(f"friction_bps must be a finite float; got {friction_bps!r}")
    if friction_bps < 0.0:
        raise ValueError(f"friction_bps cannot be negative; got {friction_bps}")

    cost_decimal = friction_bps / 10000.0
    perturbed_returns = arr - cost_decimal

    baseline_metrics = _compute_core_metrics(arr, annualization_factor)
    perturbed_metrics = _compute_core_metrics(perturbed_returns, annualization_factor)

    abs_changes, rel_changes = compute_changes(baseline_metrics, perturbed_metrics)

    config = {
        "friction_bps": friction_bps,
        "cost_decimal": cost_decimal,
        "annualization_factor": annualization_factor,
    }

    limitations = (
        "Applies constant friction per period across the return series.",
        "Static snapshot data has no historical trade order log; dynamic turnover reconstruction is deferred.",
    )

    return FragilityExperimentResult(
        experiment_id=experiment_id,
        perturbation_id="return_friction_shock",
        perturbation_name="Transaction Friction Drag Shock",
        description=f"Applies {friction_bps:.2f} bps periodic cost drag to returns, assessing tail risk sensitivity.",
        configuration=config,
        baseline_metrics=baseline_metrics,
        perturbed_metrics=perturbed_metrics,
        absolute_changes=abs_changes,
        relative_changes=rel_changes,
        observations_used=len(arr),
        warnings=(),
        limitations=limitations,
    )


def calculate_portfolio_liquidation_shock(
    portfolio: Portfolio,
    cost_bps: float,
    turnover_fraction: float = 1.0,
) -> Dict[str, float]:
    """Calculate monetary and percentage cost shock under portfolio liquidation/rebalancing.

    Since the portfolio domain represents a static snapshot without historical trade logs,
    this function models an instantaneous liquidation or rebalancing turnover friction.

    Formula:
        cost = total_value * turnover_fraction * (cost_bps / 10,000)
        net_value = total_value - cost

    Args:
        portfolio: Valid Portfolio instance.
        cost_bps: Execution and slippage cost in basis points (e.g. 25.0 bps).
        turnover_fraction: Portfolio fraction turned over, in range [0.0, 1.0] (default 1.0).

    Returns:
        Dictionary with original_value, liquidation_cost, net_value, and cost_drag_pct.
    """
    if not isinstance(portfolio, Portfolio):
        raise TypeError(f"portfolio must be a Portfolio instance; got {type(portfolio)}")
    if cost_bps < 0.0 or not math.isfinite(cost_bps):
        raise ValueError(f"cost_bps must be finite and non-negative; got {cost_bps}")
    if turnover_fraction < 0.0 or turnover_fraction > 1.0 or not math.isfinite(turnover_fraction):
        raise ValueError(f"turnover_fraction must be in [0.0, 1.0]; got {turnover_fraction}")

    tot = portfolio.total_value
    cost_ratio = (cost_bps / 10000.0) * turnover_fraction
    cost_amount = tot * cost_ratio
    net_value = tot - cost_amount

    return {
        "original_portfolio_value": tot,
        "cost_bps": cost_bps,
        "turnover_fraction": turnover_fraction,
        "liquidation_cost": cost_amount,
        "stressed_portfolio_value": net_value,
        "cost_drag_percentage": cost_ratio,
    }


# ==============================================================================
# 4. Correlation Perturbation (Multivariate)
# ==============================================================================

def perturb_correlation_matrix(
    correlation_matrix: np.ndarray,
    stress_factor: float,
    target_correlation: float = 1.0,
) -> np.ndarray:
    """Perturb an empirical correlation matrix toward a uniform target correlation.

    Formula:
        C_target = (1 - rho_target) * I_K + rho_target * J_K
        C_stressed = (1 - alpha) * C_0 + alpha * C_target

    Properties preserved:
        - Symmetric: C = C^T
        - Unit diagonal: C_{ii} = 1.0
        - Positive semidefinite (when rho_target >= 0 and C_0 is PSD)

    Args:
        correlation_matrix: 2D symmetric NumPy array of shape (K, K) with unit diagonal.
        stress_factor: Alpha interpolation parameter in [0.0, 1.0].
        target_correlation: Uniform pairwise correlation target in [0.0, 1.0] (default 1.0).

    Returns:
        Stressed correlation matrix of shape (K, K).
    """
    c = np.asarray(correlation_matrix, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValueError(f"correlation_matrix must be a square 2D array; got shape {c.shape}")

    k = c.shape[0]
    if k < 2:
        raise ValueError("Correlation perturbation requires at least 2 assets")

    if not math.isfinite(stress_factor) or stress_factor < 0.0 or stress_factor > 1.0:
        raise ValueError(f"stress_factor must be in [0.0, 1.0]; got {stress_factor}")

    if not math.isfinite(target_correlation) or target_correlation < 0.0 or target_correlation > 1.0:
        raise ValueError(f"target_correlation must be in [0.0, 1.0]; got {target_correlation}")

    # Build target correlation matrix with 1 on diagonal and target_correlation off-diagonal
    c_target = np.full((k, k), target_correlation, dtype=np.float64)
    np.fill_diagonal(c_target, 1.0)

    c_stressed = (1.0 - stress_factor) * c + stress_factor * c_target
    np.fill_diagonal(c_stressed, 1.0)
    # Ensure numerical symmetry
    c_stressed = 0.5 * (c_stressed + c_stressed.T)
    return c_stressed


def run_correlation_perturbation(
    multivariate_returns: np.ndarray,
    weights: Sequence[float],
    stress_factor: float,
    target_correlation: float = 0.80,
    annualization_factor: float = 252.0,
    experiment_id: str = "exp_correlation_stress",
) -> FragilityExperimentResult:
    """Assess portfolio volatility sensitivity to cross-asset correlation shocks.

    Args:
        multivariate_returns: 2D array of asset returns of shape (T, K) with K >= 2, T >= 2.
        weights: Sequence of portfolio weights summing to ~1.0 of length K.
        stress_factor: Degree of correlation stress in [0.0, 1.0].
        target_correlation: High-correlation crisis target (default 0.80).
        annualization_factor: Annualization multiplier (default 252.0).
        experiment_id: Unique experiment run identifier.

    Returns:
        FragilityExperimentResult reporting baseline vs stressed portfolio volatility.
    """
    r_mat = np.asarray(multivariate_returns, dtype=np.float64)
    if r_mat.ndim != 2:
        raise ValueError(
            "Correlation perturbation requires a 2D synchronized multivariate return matrix (shape T x K). "
            "A static portfolio snapshot has no multivariate return history."
        )

    t_obs, k_assets = r_mat.shape
    if k_assets < 2:
        raise ValueError("Multivariate return matrix must have at least 2 asset columns")
    if t_obs < 2:
        raise ValueError("Multivariate return matrix must have at least 2 time observations")

    w = np.asarray(weights, dtype=np.float64)
    if len(w) != k_assets:
        raise ValueError(f"Weights length ({len(w)}) must match asset count ({k_assets})")

    # Baseline asset volatilities and correlation
    asset_vols = np.std(r_mat, axis=0, ddof=1)
    d_mat = np.diag(asset_vols)

    c_0 = np.corrcoef(r_mat, rowvar=False)
    np.fill_diagonal(c_0, 1.0)

    # Baseline portfolio variance: w^T * (D * C_0 * D) * w
    cov_0 = d_mat @ c_0 @ d_mat
    var_port_0 = float(w @ cov_0 @ w)
    baseline_vol = math.sqrt(max(0.0, var_port_0)) * math.sqrt(annualization_factor)

    # Stressed correlation matrix
    c_stressed = perturb_correlation_matrix(c_0, stress_factor, target_correlation)
    cov_stressed = d_mat @ c_stressed @ d_mat
    var_port_stressed = float(w @ cov_stressed @ w)
    stressed_vol = math.sqrt(max(0.0, var_port_stressed)) * math.sqrt(annualization_factor)

    baseline_metrics = {"portfolio_volatility_annualized": baseline_vol}
    perturbed_metrics = {"portfolio_volatility_annualized": stressed_vol}

    abs_changes, rel_changes = compute_changes(baseline_metrics, perturbed_metrics)

    config = {
        "stress_factor": stress_factor,
        "target_correlation": target_correlation,
        "asset_count": k_assets,
        "observations": t_obs,
    }

    limitations = (
        "Requires synchronized multivariate return histories for all constituent assets.",
        "Uniform correlation stress models systemic co-movement during market liquidity contraction.",
    )

    return FragilityExperimentResult(
        experiment_id=experiment_id,
        perturbation_id="correlation_stress",
        perturbation_name="Multivariate Correlation Stress",
        description=f"Perturbs empirical correlation matrix by factor {stress_factor:.2f} toward {target_correlation:.2f}.",
        configuration=config,
        baseline_metrics=baseline_metrics,
        perturbed_metrics=perturbed_metrics,
        absolute_changes=abs_changes,
        relative_changes=rel_changes,
        observations_used=t_obs,
        warnings=(),
        limitations=limitations,
    )


# ==============================================================================
# 5. Tail Confidence Level Perturbation
# ==============================================================================

def run_confidence_level_perturbation(
    returns: Sequence[float] | np.ndarray,
    perturbed_confidence: float = 0.99,
    baseline_confidence: float = 0.95,
    experiment_id: str = "exp_confidence_level",
) -> FragilityExperimentResult:
    """Assess tail risk sensitivity when confidence level is perturbed (e.g. 95% vs 99%).

    Args:
        returns: Sequence of returns.
        perturbed_confidence: Stressed confidence level in (0.0, 1.0).
        baseline_confidence: Baseline confidence level in (0.0, 1.0) (default 0.95).
        experiment_id: Unique experiment run identifier.

    Returns:
        FragilityExperimentResult with VaR and Expected Shortfall changes.
    """
    arr = np.asarray(returns, dtype=np.float64)
    var_base = calculate_historical_var(arr, confidence_level=baseline_confidence)
    es_base = calculate_expected_shortfall(arr, confidence_level=baseline_confidence)

    var_pert = calculate_historical_var(arr, confidence_level=perturbed_confidence)
    es_pert = calculate_expected_shortfall(arr, confidence_level=perturbed_confidence)

    baseline_metrics = {
        "var": var_base,
        "expected_shortfall": es_base,
    }
    perturbed_metrics = {
        "var": var_pert,
        "expected_shortfall": es_pert,
    }

    abs_changes, rel_changes = compute_changes(baseline_metrics, perturbed_metrics)

    config = {
        "baseline_confidence": baseline_confidence,
        "perturbed_confidence": perturbed_confidence,
    }

    limitations = (
        "Higher confidence percentiles (e.g. 99%+) require larger historical samples for statistical stability.",
    )

    return FragilityExperimentResult(
        experiment_id=experiment_id,
        perturbation_id="tail_confidence_level",
        perturbation_name="Tail Confidence Level Shift",
        description=f"Evaluates tail risk expansion from {baseline_confidence:.1%} to {perturbed_confidence:.1%} confidence.",
        configuration=config,
        baseline_metrics=baseline_metrics,
        perturbed_metrics=perturbed_metrics,
        absolute_changes=abs_changes,
        relative_changes=rel_changes,
        observations_used=len(arr),
        warnings=(),
        limitations=limitations,
    )


# ==============================================================================
# 6. Sensitivity Ranking & Fragility Audit
# ==============================================================================

def rank_perturbation_sensitivities(
    experiments: Sequence[FragilityExperimentResult],
    target_metric: str,
) -> MetricSensitivityRanking:
    """Rank fragility experiments by absolute impact on a designated risk metric.

    Args:
        experiments: Sequence of executed FragilityExperimentResult instances.
        target_metric: Metric identifier to rank by (e.g. 'volatility_annualized', 'var_95').

    Returns:
        MetricSensitivityRanking with ordered impacts and identified top sensitivity.

    Raises:
        ValueError: If experiments is empty or target_metric is missing in all experiments.
    """
    if not experiments:
        raise ValueError("Cannot rank sensitivities on an empty sequence of experiments")

    impacts: List[PerturbationImpact] = []
    baseline_val: Optional[float] = None

    for exp in experiments:
        if target_metric in exp.baseline_metrics and target_metric in exp.perturbed_metrics:
            m0 = exp.baseline_metrics[target_metric]
            m1 = exp.perturbed_metrics[target_metric]
            delta = exp.absolute_changes.get(target_metric, m1 - m0)
            rel_delta = exp.relative_changes.get(target_metric)

            if baseline_val is None:
                baseline_val = m0

            # Derive primary parameter
            param_name = "configuration"
            param_val = str(exp.configuration)
            if "perturbed_window" in exp.configuration:
                param_name = "perturbed_window"
                param_val = exp.configuration["perturbed_window"]
            elif "decay_factor" in exp.configuration:
                param_name = "decay_factor"
                param_val = exp.configuration["decay_factor"]
            elif "friction_bps" in exp.configuration:
                param_name = "friction_bps"
                param_val = exp.configuration["friction_bps"]
            elif "stress_factor" in exp.configuration:
                param_name = "stress_factor"
                param_val = exp.configuration["stress_factor"]
            elif "perturbed_confidence" in exp.configuration:
                param_name = "perturbed_confidence"
                param_val = exp.configuration["perturbed_confidence"]

            warning = exp.warnings[0] if exp.warnings else None

            impacts.append(
                PerturbationImpact(
                    perturbation_id=exp.perturbation_id,
                    perturbation_name=exp.perturbation_name,
                    parameter_name=param_name,
                    parameter_value=param_val,
                    baseline_value=m0,
                    perturbed_value=m1,
                    absolute_change=delta,
                    relative_change=rel_delta,
                    warning=warning,
                )
            )

    if not impacts or baseline_val is None:
        raise ValueError(f"Target metric '{target_metric}' not found in any provided experiment results")

    # Sort descending by absolute impact |delta|
    sorted_impacts = sorted(impacts, key=lambda imp: abs(imp.absolute_change), reverse=True)
    most_sensitive = sorted_impacts[0].perturbation_id if sorted_impacts else None
    max_abs = abs(sorted_impacts[0].absolute_change) if sorted_impacts else 0.0
    max_rel = sorted_impacts[0].relative_change if sorted_impacts else None

    return MetricSensitivityRanking(
        metric_id=target_metric,
        baseline_value=baseline_val,
        ranked_impacts=tuple(sorted_impacts),
        most_sensitive_perturbation=most_sensitive,
        max_absolute_change=max_abs,
        max_relative_change=max_rel,
    )
