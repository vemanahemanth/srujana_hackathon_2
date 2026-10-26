"""Simulation and Uncertainty Engine for FragilityShield.

Implements:
1. Monte Carlo Path Simulation (Geometric Brownian Motion & Student-t fat-tailed innovations)
   revealing potential multi-period portfolio growth and drawdown paths.
2. Non-parametric Bootstrap Resampling quantifying the statistical uncertainty and confidence
   intervals of Value-at-Risk and Expected Shortfall estimates.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import scipy.stats as stats

from fragility_engine.risk import calculate_expected_shortfall, calculate_historical_var


@dataclass(frozen=True)
class MonteCarloResult:
    """Consolidated results of a multi-path Monte Carlo forward simulation."""

    model: str
    horizon_days: int
    num_paths: int
    initial_value: float
    time_grid: Tuple[int, ...]
    percentile_5th_path: Tuple[float, ...]
    median_path: Tuple[float, ...]
    percentile_95th_path: Tuple[float, ...]
    terminal_mean: float
    terminal_std: float
    simulated_var_95: float
    simulated_var_99: float
    simulated_es_95: float
    execution_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert simulation result to a serializable dictionary."""
        return {
            "model": self.model,
            "horizon_days": int(self.horizon_days),
            "num_paths": int(self.num_paths),
            "initial_value": float(self.initial_value),
            "time_grid": list(self.time_grid),
            "percentile_5th_path": [round(x, 4) for x in self.percentile_5th_path],
            "median_path": [round(x, 4) for x in self.median_path],
            "percentile_95th_path": [round(x, 4) for x in self.percentile_95th_path],
            "envelope_5th": [round(x, 4) for x in self.percentile_5th_path],
            "envelope_50th": [round(x, 4) for x in self.median_path],
            "envelope_95th": [round(x, 4) for x in self.percentile_95th_path],
            "terminal_mean": float(self.terminal_mean),
            "terminal_std": float(self.terminal_std),
            "simulated_var_95": float(self.simulated_var_95),
            "simulated_var_99": float(self.simulated_var_99),
            "simulated_es_95": float(self.simulated_es_95),
            "terminal_var_95": float(self.simulated_var_95),
            "terminal_var_99": float(self.simulated_var_99),
            "terminal_es_95": float(self.simulated_es_95),
            "execution_time_ms": float(self.execution_time_ms),
        }


@dataclass(frozen=True)
class BootstrapUncertaintyResult:
    """Bootstrap estimation uncertainty and confidence intervals for risk estimates."""

    confidence_level: float
    bootstrap_iterations: int
    sample_size: int
    point_estimate_var: float
    var_ci_90_lower: float
    var_ci_90_upper: float
    var_ci_95_lower: float
    var_ci_95_upper: float
    point_estimate_es: float
    es_ci_90_lower: float
    es_ci_90_upper: float
    uncertainty_interpretation: str
    execution_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert uncertainty metrics to serializable dictionary."""
        return {
            "confidence_level": float(self.confidence_level),
            "bootstrap_iterations": int(self.bootstrap_iterations),
            "sample_size": int(self.sample_size),
            "point_estimate_var": float(self.point_estimate_var),
            "point_var_estimate": float(self.point_estimate_var),
            "var_ci_90_lower": float(self.var_ci_90_lower),
            "var_ci_90_upper": float(self.var_ci_90_upper),
            "var_ci_95_lower": float(self.var_ci_95_lower),
            "var_ci_95_upper": float(self.var_ci_95_upper),
            "var_standard_error": float(abs(self.var_ci_95_upper - self.var_ci_95_lower) / (2 * 1.96)),
            "point_estimate_es": float(self.point_estimate_es),
            "point_es_estimate": float(self.point_estimate_es),
            "es_ci_90_lower": float(self.es_ci_90_lower),
            "es_ci_90_upper": float(self.es_ci_90_upper),
            "es_ci_95_lower": float(self.es_ci_90_lower),
            "es_ci_95_upper": float(self.es_ci_90_upper),
            "es_standard_error": float(abs(self.es_ci_90_upper - self.es_ci_90_lower) / (2 * 1.645)),
            "uncertainty_interpretation": self.uncertainty_interpretation,
            "execution_time_ms": float(self.execution_time_ms),
        }


def simulate_monte_carlo(
    returns: Sequence[float],
    num_paths: int = 250,
    horizon_days: int = 30,
    model: str = "gaussian",
    student_t_df: int = 5,
    seed: Optional[int] = 42,
) -> MonteCarloResult:
    """Execute multi-path Monte Carlo forward simulation from historical return parameters.

    Args:
        returns: Historical return series to calibrate drift and volatility.
        num_paths: Number of simulation trajectories (default 250).
        horizon_days: Forward projection horizon in business days (default 30).
        model: Simulation model: 'gaussian' or 'student_t'.
        student_t_df: Degrees of freedom if model is 'student_t' (default 5).
        seed: Random seed for deterministic reproducibility.

    Returns:
        MonteCarloResult with envelope paths and terminal risk statistics.
    """
    t0 = time.perf_counter()
    arr = np.asarray(returns, dtype=np.float64)
    if arr.size < 4:
        raise ValueError(f"Simulation requires at least 4 return observations; got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Return series contains non-finite values (NaN or Inf)")

    if num_paths < 10 or num_paths > 2000:
        raise ValueError(f"num_paths must be between 10 and 2000; got {num_paths}")
    if horizon_days < 1 or horizon_days > 252:
        raise ValueError(f"horizon_days must be between 1 and 252; got {horizon_days}")

    model_clean = model.strip().lower()
    if model_clean not in ("gaussian", "student_t"):
        raise ValueError(f"model must be 'gaussian' or 'student_t'; got '{model}'")

    rng = np.random.default_rng(seed)
    mu = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1))
    if sigma <= 0.0:
        sigma = 1e-4

    # Generate innovations: matrix of shape (num_paths, horizon_days)
    if model_clean == "gaussian":
        shocks = rng.normal(loc=mu, scale=sigma, size=(num_paths, horizon_days))
    else:
        # Standardized Student-t with variance sigma^2: scale = sigma * sqrt((df-2)/df)
        df = max(3, student_t_df)
        scale = sigma * math.sqrt((df - 2.0) / df)
        raw_t = rng.standard_t(df=df, size=(num_paths, horizon_days))
        shocks = mu + scale * raw_t

    # Build simulated cumulative price paths starting from 1.0
    # Price path P_t = P_0 * prod_{s=1}^t (1 + r_s)
    # Clip shocks to avoid bankruptcies in linear approximation: 1 + r > 0.01
    shocks_clipped = np.clip(shocks, a_min=-0.95, a_max=2.0)
    growth_factors = 1.0 + shocks_clipped
    paths = np.empty((num_paths, horizon_days + 1), dtype=np.float64)
    paths[:, 0] = 1.0
    for t in range(horizon_days):
        paths[:, t + 1] = paths[:, t] * growth_factors[:, t]

    # Calculate percentile paths across time
    time_grid = tuple(range(horizon_days + 1))
    p5_path = tuple(float(np.percentile(paths[:, t], 5.0)) for t in range(horizon_days + 1))
    p50_path = tuple(float(np.percentile(paths[:, t], 50.0)) for t in range(horizon_days + 1))
    p95_path = tuple(float(np.percentile(paths[:, t], 95.0)) for t in range(horizon_days + 1))

    # Terminal statistics
    terminal_prices = paths[:, -1]
    terminal_returns = (terminal_prices - 1.0)
    # In positive loss convention: Loss = -Terminal_Return
    terminal_losses = -terminal_returns
    sim_var_95 = float(np.percentile(terminal_losses, 95.0))
    sim_var_99 = float(np.percentile(terminal_losses, 99.0))
    # Expected shortfall of terminal losses above 95%
    tail_losses = terminal_losses[terminal_losses >= sim_var_95]
    sim_es_95 = float(np.mean(tail_losses)) if len(tail_losses) > 0 else sim_var_95

    t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return MonteCarloResult(
        model=model_clean,
        horizon_days=horizon_days,
        num_paths=num_paths,
        initial_value=1.0,
        time_grid=time_grid,
        percentile_5th_path=p5_path,
        median_path=p50_path,
        percentile_95th_path=p95_path,
        terminal_mean=float(np.mean(terminal_prices)),
        terminal_std=float(np.std(terminal_prices)),
        simulated_var_95=sim_var_95,
        simulated_var_99=sim_var_99,
        simulated_es_95=sim_es_95,
        execution_time_ms=t_elapsed_ms,
    )


def calculate_bootstrap_uncertainty(
    returns: Sequence[float],
    confidence_level: float = 0.95,
    num_bootstraps: int = 300,
    seed: Optional[int] = 42,
) -> BootstrapUncertaintyResult:
    """Compute empirical bootstrap confidence intervals for VaR and Expected Shortfall.

    Args:
        returns: Historical return series.
        confidence_level: Target risk quantile level (e.g. 0.95).
        num_bootstraps: Number of bootstrap resamples (default 300).
        seed: Random seed for deterministic reproducibility.

    Returns:
        BootstrapUncertaintyResult detailing point estimates and confidence intervals.
    """
    t0 = time.perf_counter()
    arr = np.asarray(returns, dtype=np.float64)
    n = len(arr)
    if n < 8:
        raise ValueError(f"Bootstrap uncertainty requires at least 8 observations; got {n}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Return series contains non-finite values (NaN or Inf)")

    if num_bootstraps < 50 or num_bootstraps > 2000:
        raise ValueError(f"num_bootstraps must be between 50 and 2000; got {num_bootstraps}")

    # Baseline point estimates on original sample
    point_var = calculate_historical_var(arr, confidence_level=confidence_level)
    point_es = calculate_expected_shortfall(arr, confidence_level=confidence_level)

    rng = np.random.default_rng(seed)
    bootstrap_vars = np.empty(num_bootstraps, dtype=np.float64)
    bootstrap_esses = np.empty(num_bootstraps, dtype=np.float64)

    for i in range(num_bootstraps):
        resampled = rng.choice(arr, size=n, replace=True)
        bootstrap_vars[i] = calculate_historical_var(resampled, confidence_level=confidence_level)
        bootstrap_esses[i] = calculate_expected_shortfall(resampled, confidence_level=confidence_level)

    # Calculate confidence interval percentiles
    var_90_lower = float(np.percentile(bootstrap_vars, 5.0))
    var_90_upper = float(np.percentile(bootstrap_vars, 95.0))
    var_95_lower = float(np.percentile(bootstrap_vars, 2.5))
    var_95_upper = float(np.percentile(bootstrap_vars, 97.5))

    es_90_lower = float(np.percentile(bootstrap_esses, 5.0))
    es_90_upper = float(np.percentile(bootstrap_esses, 95.0))

    t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

    interpretation = (
        f"Point estimate VaR is {point_var*100:.2f}%. Due to sample size N={n}, "
        f"the 90% bootstrap confidence band spans [{var_90_lower*100:.2f}%, {var_90_upper*100:.2f}%]. "
        f"Static point estimates hide this estimation variance."
    )

    return BootstrapUncertaintyResult(
        confidence_level=confidence_level,
        bootstrap_iterations=num_bootstraps,
        sample_size=n,
        point_estimate_var=point_var,
        var_ci_90_lower=var_90_lower,
        var_ci_90_upper=var_90_upper,
        var_ci_95_lower=var_95_lower,
        var_ci_95_upper=var_95_upper,
        point_estimate_es=point_es,
        es_ci_90_lower=es_90_lower,
        es_ci_90_upper=es_90_upper,
        uncertainty_interpretation=interpretation,
        execution_time_ms=t_elapsed_ms,
    )
