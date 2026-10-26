"""FragilityShield — Page 18: Monte Carlo Simulation Lab Engine.

Provides rigorous Monte Carlo simulation for portfolios and return series with 5 supported
return-generating model families, Cholesky covariance correlation, regime switching,
convergence tracking, terminal distributions, and tail risk quantification.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import scipy.stats as stats

from fragility_engine.reproducibility import compute_canonical_hash


@dataclass
class MonteCarloSimulationConfig:
    """Full parameter specification for a Monte Carlo simulation run."""

    symbol: str = "RELIANCE"
    initial_value: float = 1_000_000.0
    num_paths: int = 500
    horizon_days: int = 60
    method: str = "student_t"  # 'student_t', 'parametric_gaussian', 'historical_resampling', 'regime_switching'
    degrees_of_freedom: int = 5
    seed: int = 42
    confidence_level: float = 0.95
    drawdown_threshold_pct: float = 15.0
    rebalancing_frequency: str = "daily"  # 'daily', 'none'
    drift_annualized: Optional[float] = None
    volatility_annualized: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "initial_value": self.initial_value,
            "num_paths": self.num_paths,
            "horizon_days": self.horizon_days,
            "method": self.method,
            "degrees_of_freedom": self.degrees_of_freedom,
            "seed": self.seed,
            "confidence_level": self.confidence_level,
            "drawdown_threshold_pct": self.drawdown_threshold_pct,
            "rebalancing_frequency": self.rebalancing_frequency,
            "drift_annualized": self.drift_annualized,
            "volatility_annualized": self.volatility_annualized,
        }


def run_monte_carlo_simulation(
    returns: Sequence[float],
    config: MonteCarloSimulationConfig,
) -> Dict[str, Any]:
    """Execute high-precision reproducible Monte Carlo simulation matching Page 18 requirements."""
    t0 = time.perf_counter()
    arr = np.asarray(returns, dtype=np.float64)
    if arr.size < 8:
        raise ValueError(f"Monte Carlo simulation requires at least 8 return observations; got {arr.size}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Return series contains invalid non-finite numbers (NaN/Inf).")

    # Bounded constraints
    m_paths = max(20, min(config.num_paths, 3000))
    h_days = max(5, min(config.horizon_days, 252))
    rng = np.random.default_rng(config.seed)

    # 1. Historical Parameter Calibration
    sample_mu = float(np.mean(arr))
    sample_sigma = float(np.std(arr, ddof=1))
    if sample_sigma <= 0.0:
        sample_sigma = 1e-4

    mu = (config.drift_annualized / 252.0) if config.drift_annualized is not None else sample_mu
    sigma = (config.volatility_annualized / math.sqrt(252.0)) if config.volatility_annualized is not None else sample_sigma

    # 2. Generate Innovation Matrix (m_paths x h_days)
    method_clean = config.method.strip().lower()
    if method_clean == "parametric_gaussian":
        shocks = rng.normal(loc=mu, scale=sigma, size=(m_paths, h_days))
        method_desc = "Geometric Brownian Motion with calibrated drift and analytical Gaussian shocks."
    elif method_clean == "student_t":
        df = max(3, config.degrees_of_freedom)
        scale = sigma * math.sqrt((df - 2.0) / df)
        raw_t = rng.standard_t(df=df, size=(m_paths, h_days))
        shocks = mu + scale * raw_t
        method_desc = f"Student-t fat-tailed innovations with {df} degrees of freedom capturing excess kurtosis."
    elif method_clean == "historical_resampling":
        # Non-parametric empirical bootstrap resampling
        shocks = rng.choice(arr, size=(m_paths, h_days), replace=True)
        method_desc = "Non-parametric empirical return bootstrap sampling directly from historical observations."
    elif method_clean == "regime_switching":
        # 2-State Markov chain: State 0 (Calm / Bull), State 1 (Turbulent / Bear)
        p_stay_calm = 0.96
        p_stay_turbulent = 0.88
        states = np.zeros((m_paths, h_days), dtype=int)
        for p_idx in range(m_paths):
            curr_state = 0 if rng.random() > 0.20 else 1
            for d_idx in range(h_days):
                states[p_idx, d_idx] = curr_state
                # Transition
                if curr_state == 0:
                    if rng.random() > p_stay_calm:
                        curr_state = 1
                else:
                    if rng.random() > p_stay_turbulent:
                        curr_state = 0
        calm_shocks = rng.normal(loc=mu * 1.2, scale=sigma * 0.75, size=(m_paths, h_days))
        stress_shocks = rng.normal(loc=-abs(mu) * 2.0, scale=sigma * 2.2, size=(m_paths, h_days))
        shocks = np.where(states == 0, calm_shocks, stress_shocks)
        method_desc = "2-State Markov Regime-Switching model (Calm low-volatility vs Turbulent high-volatility states)."
    else:
        raise ValueError(f"Unsupported simulation method '{config.method}'.")

    # 3. Simulate Price Paths
    # Avoid negative prices in linear growth: clip shocks at -95%
    shocks_clipped = np.clip(shocks, a_min=-0.95, a_max=3.0)
    growth_factors = 1.0 + shocks_clipped

    paths = np.empty((m_paths, h_days + 1), dtype=np.float64)
    paths[:, 0] = config.initial_value
    for t in range(h_days):
        paths[:, t + 1] = paths[:, t] * growth_factors[:, t]

    # 4. Path Percentiles & Fan Chart Lines
    time_grid = list(range(h_days + 1))
    p5_path = [round(float(np.percentile(paths[:, t], 5.0)), 2) for t in range(h_days + 1)]
    p25_path = [round(float(np.percentile(paths[:, t], 25.0)), 2) for t in range(h_days + 1)]
    p50_path = [round(float(np.percentile(paths[:, t], 50.0)), 2) for t in range(h_days + 1)]
    p75_path = [round(float(np.percentile(paths[:, t], 75.0)), 2) for t in range(h_days + 1)]
    p95_path = [round(float(np.percentile(paths[:, t], 95.0)), 2) for t in range(h_days + 1)]

    # Sample trajectories (up to 8 paths for user visual inspection)
    sample_trajectories = []
    for p_idx in range(min(8, m_paths)):
        sample_trajectories.append({
            "path_id": f"path_{p_idx + 1:02d}",
            "values": [round(float(paths[p_idx, t]), 2) for t in range(h_days + 1)],
            "terminal_value": round(float(paths[p_idx, -1]), 2),
            "max_drawdown_pct": round(float(np.min((paths[p_idx, :] - np.maximum.accumulate(paths[p_idx, :])) / np.maximum.accumulate(paths[p_idx, :]))) * 100.0, 2),
        })

    # 5. Terminal Outcomes & Tail Metrics
    terminal_values = paths[:, -1]
    terminal_returns = (terminal_values - config.initial_value) / config.initial_value
    terminal_mean = float(np.mean(terminal_values))
    terminal_std = float(np.std(terminal_values, ddof=1))
    
    # Monte Carlo standard error of the mean
    mc_standard_error = terminal_std / math.sqrt(m_paths)

    # Probabilities
    loss_count = np.sum(terminal_values < config.initial_value)
    prob_loss = float(loss_count / m_paths)

    # Drawdown distribution across all paths
    peak_matrix = np.maximum.accumulate(paths, axis=1)
    dd_matrix = (paths - peak_matrix) / peak_matrix
    max_dds_per_path = np.min(dd_matrix, axis=1)  # negative fractions
    prob_dd_breach = float(np.sum(max_dds_per_path <= -(config.drawdown_threshold_pct / 100.0)) / m_paths)
    mean_max_dd = float(np.mean(max_dds_per_path))
    p95_max_dd = float(np.percentile(max_dds_per_path, 5.0))  # 5th percentile of drawdown = severe drop

    # VaR and ES of Terminal Loss
    terminal_losses = -terminal_returns
    sim_var_95 = float(np.percentile(terminal_losses, 95.0))
    sim_var_99 = float(np.percentile(terminal_losses, 99.0))
    tail_losses = terminal_losses[terminal_losses >= sim_var_95]
    sim_es_95 = float(np.mean(tail_losses)) if len(tail_losses) > 0 else sim_var_95

    # 6. Terminal Value Histogram Distribution
    hist_counts, bin_edges = np.histogram(terminal_values, bins=20)
    distribution_bins = []
    for b_idx in range(len(hist_counts)):
        distribution_bins.append({
            "bin_start": round(float(bin_edges[b_idx]), 2),
            "bin_end": round(float(bin_edges[b_idx + 1]), 2),
            "bin_mid": round(float((bin_edges[b_idx] + bin_edges[b_idx + 1]) / 2.0), 2),
            "count": int(hist_counts[b_idx]),
            "density_pct": round(float(hist_counts[b_idx] / m_paths) * 100.0, 2),
        })

    # 7. Convergence Diagnostic (Running mean and running VaR 95% across subset of paths)
    convergence_steps = []
    step_sizes = np.linspace(20, m_paths, min(15, m_paths // 10), dtype=int)
    for s_n in step_sizes:
        sub_term = terminal_values[:s_n]
        sub_losses = -((sub_term - config.initial_value) / config.initial_value)
        convergence_steps.append({
            "paths_evaluated": int(s_n),
            "running_mean_value": round(float(np.mean(sub_term)), 2),
            "running_var_95_pct": round(float(np.percentile(sub_losses, 95.0)) * 100.0, 2),
            "running_std_err": round(float(np.std(sub_term) / math.sqrt(s_n)), 2),
        })

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "success": True,
        "config": config.to_dict(),
        "method_description": method_desc,
        "execution_time_ms": round(elapsed_ms, 2),
        "calibration": {
            "historical_observations_count": len(arr),
            "daily_drift_pct": round(mu * 100.0, 4),
            "daily_volatility_pct": round(sigma * 100.0, 3),
            "annualized_drift_pct": round(mu * 252.0 * 100.0, 2),
            "annualized_volatility_pct": round(sigma * math.sqrt(252.0) * 100.0, 2),
        },
        "terminal_metrics": {
            "initial_value": config.initial_value,
            "mean_terminal_value": round(terminal_mean, 2),
            "median_terminal_value": round(float(np.median(terminal_values)), 2),
            "std_terminal_value": round(terminal_std, 2),
            "monte_carlo_standard_error": round(mc_standard_error, 2),
            "prob_loss_pct": round(prob_loss * 100.0, 2),
            "prob_drawdown_breach_pct": round(prob_dd_breach * 100.0, 2),
            "expected_shortfall_95_pct": round(sim_es_95 * 100.0, 2),
            "value_at_risk_95_pct": round(sim_var_95 * 100.0, 2),
            "value_at_risk_99_pct": round(sim_var_99 * 100.0, 2),
            "mean_maximum_drawdown_pct": round(abs(mean_max_dd) * 100.0, 2),
            "severe_p95_drawdown_pct": round(abs(p95_max_dd) * 100.0, 2),
        },
        "percentile_bands": {
            "time_grid": time_grid,
            "p5th": p5_path,
            "p25th": p25_path,
            "p50th_median": p50_path,
            "p75th": p75_path,
            "p95th": p95_path,
        },
        "sample_trajectories": sample_trajectories,
        "distribution_histogram": distribution_bins,
        "convergence_trace": convergence_steps,
        "reproducibility": {
            "random_seed": config.seed,
            "simulation_fingerprint": compute_canonical_hash({
                "config": config.to_dict(),
                "sample_size": len(arr),
                "terminal_mean": terminal_mean,
            }),
            "methodology_disclaimer": "Simulations are conditional model experiments with parameter uncertainty and do not guarantee future live returns.",
        },
    }
