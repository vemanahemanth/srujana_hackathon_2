"""FragilityShield — Page 19: Bootstrap & Uncertainty Lab Engine.

Provides statistical uncertainty quantification for financial metrics via IID, Moving-Block,
Circular-Block, and Stationary Bootstrap resampling methods, block-length sensitivity,
confidence intervals, and subperiod stability analysis.
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

from fragility_engine.risk import calculate_expected_shortfall, calculate_historical_var
from fragility_engine.reproducibility import compute_canonical_hash


@dataclass
class BootstrapLabConfig:
    """Configuration for statistical uncertainty estimation."""

    symbol: str = "RELIANCE"
    metric: str = "sharpe_ratio"  # 'sharpe_ratio', 'annualized_return', 'annualized_volatility', 'var_95', 'expected_shortfall_95', 'max_drawdown'
    resampling_method: str = "moving_block_bootstrap"  # 'moving_block_bootstrap', 'iid_bootstrap', 'circular_block_bootstrap', 'stationary_bootstrap'
    num_resamples: int = 400
    confidence_level: float = 0.95
    block_length: int = 5
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "metric": self.metric,
            "resampling_method": self.resampling_method,
            "num_resamples": self.num_resamples,
            "confidence_level": self.confidence_level,
            "block_length": self.block_length,
            "seed": self.seed,
        }


def compute_target_statistic(returns_arr: np.ndarray, metric: str) -> float:
    """Compute financial target metric on given return vector."""
    n = len(returns_arr)
    if n < 2:
        return 0.0

    ann_factor = 252.0
    metric_clean = metric.strip().lower()

    if metric_clean == "annualized_return":
        # Cumulative compounded return annualized
        compounded = float(np.prod(1.0 + returns_arr))
        return (compounded ** (ann_factor / n) - 1.0) if compounded > 0 else -1.0

    elif metric_clean == "annualized_volatility":
        std = float(np.std(returns_arr, ddof=1))
        return std * math.sqrt(ann_factor)

    elif metric_clean == "sharpe_ratio":
        std = float(np.std(returns_arr, ddof=1))
        daily_rf = 0.065 / ann_factor
        excess = returns_arr - daily_rf
        return (float(np.mean(excess)) / std * math.sqrt(ann_factor)) if std > 1e-6 else 0.0

    elif metric_clean == "var_95":
        # Positive loss convention: Loss = -Return
        losses = -returns_arr
        return float(np.percentile(losses, 95.0))

    elif metric_clean == "expected_shortfall_95":
        losses = -returns_arr
        var95 = float(np.percentile(losses, 95.0))
        tail = losses[losses >= var95]
        return float(np.mean(tail)) if len(tail) > 0 else var95

    elif metric_clean == "max_drawdown":
        wealth = np.cumprod(1.0 + np.clip(returns_arr, -0.99, 5.0))
        peak = np.maximum.accumulate(wealth)
        dd = (wealth - peak) / peak
        return float(abs(np.min(dd)))

    else:
        # Default mean return
        return float(np.mean(returns_arr)) * ann_factor


def resample_series(
    arr: np.ndarray,
    method: str,
    block_len: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate a single bootstrap resample of length N under specified sampling scheme."""
    n = len(arr)
    method_clean = method.strip().lower()
    if not method_clean.endswith("_bootstrap"):
        method_clean = f"{method_clean}_bootstrap"

    if method_clean == "iid_bootstrap":
        return rng.choice(arr, size=n, replace=True)

    elif method_clean == "moving_block_bootstrap":
        # Overlapping blocks: index 0 to n - block_len
        b = max(1, min(block_len, n))
        num_blocks = math.ceil(n / b)
        max_start = n - b
        starts = rng.integers(0, max_start + 1, size=num_blocks)
        resampled_blocks = [arr[s : s + b] for s in starts]
        concat = np.concatenate(resampled_blocks)
        return concat[:n]

    elif method_clean == "circular_block_bootstrap":
        # Periodic wraparound blocks: every index 0 to n-1 is a valid start
        b = max(1, min(block_len, n))
        num_blocks = math.ceil(n / b)
        extended = np.concatenate([arr, arr[:b]])
        starts = rng.integers(0, n, size=num_blocks)
        resampled_blocks = [extended[s : s + b] for s in starts]
        concat = np.concatenate(resampled_blocks)
        return concat[:n]

    elif method_clean == "stationary_bootstrap":
        # Politis & Romano (1994): Geometric block length with mean b (p = 1/b)
        b = max(1, min(block_len, n))
        p = 1.0 / b
        resampled = np.empty(n, dtype=arr.dtype)
        curr_idx = rng.integers(0, n)
        for i in range(n):
            resampled[i] = arr[curr_idx]
            # Transition: with probability p start new block; with 1-p continue (wrapped)
            if rng.random() < p:
                curr_idx = rng.integers(0, n)
            else:
                curr_idx = (curr_idx + 1) % n
        return resampled

    else:
        raise ValueError(f"Unknown bootstrap method '{method}'.")


def run_bootstrap_uncertainty_analysis(
    returns: Sequence[float],
    config: BootstrapLabConfig,
) -> Dict[str, Any]:
    """Execute rigorous statistical uncertainty analysis matching Page 19 specification."""
    t0 = time.perf_counter()
    arr = np.asarray(returns, dtype=np.float64)
    n = len(arr)
    if n < 10:
        raise ValueError(f"Bootstrap requires at least 10 return observations; got {n}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Return series contains invalid non-finite numbers (NaN/Inf).")

    num_b = max(50, min(config.num_resamples, 2000))
    alpha = 1.0 - config.confidence_level
    rng = np.random.default_rng(config.seed)

    # 1. Point estimate on original historical sample
    point_est = compute_target_statistic(arr, config.metric)

    # 2. Resampling loop
    boot_stats = np.empty(num_b, dtype=np.float64)
    running_se_trace = []
    trace_checkpoints = np.linspace(25, num_b, min(12, num_b // 20), dtype=int)

    for i in range(num_b):
        resampled = resample_series(arr, config.resampling_method, config.block_length, rng)
        boot_stats[i] = compute_target_statistic(resampled, config.metric)
        if (i + 1) in trace_checkpoints:
            sub = boot_stats[: i + 1]
            running_se_trace.append({
                "resample_iteration": i + 1,
                "running_standard_error": round(float(np.std(sub, ddof=1)), 5),
                "running_mean": round(float(np.mean(sub)), 5),
            })

    # 3. Confidence Intervals
    boot_se = float(np.std(boot_stats, ddof=1))
    boot_mean = float(np.mean(boot_stats))

    # A. Percentile Interval
    pct_lower = float(np.percentile(boot_stats, (alpha / 2.0) * 100.0))
    pct_upper = float(np.percentile(boot_stats, (1.0 - alpha / 2.0) * 100.0))

    # B. Basic / Empirical Interval: [2*theta - q(1-alpha/2), 2*theta - q(alpha/2)]
    basic_lower = 2.0 * point_est - pct_upper
    basic_upper = 2.0 * point_est - pct_lower

    # C. Studentized / Normal Interval: theta +/- z * SE
    z_crit = float(stats.norm.ppf(1.0 - alpha / 2.0))
    norm_lower = point_est - z_crit * boot_se
    norm_upper = point_est + z_crit * boot_se

    # 4. Bootstrap Distribution Histogram
    hist_counts, bin_edges = np.histogram(boot_stats, bins=25)
    hist_bins = []
    for b_i in range(len(hist_counts)):
        hist_bins.append({
            "bin_start": round(float(bin_edges[b_i]), 4),
            "bin_end": round(float(bin_edges[b_i + 1]), 4),
            "bin_mid": round(float((bin_edges[b_i] + bin_edges[b_i + 1]) / 2.0), 4),
            "count": int(hist_counts[b_i]),
            "density_pct": round(float(hist_counts[b_i] / num_b) * 100.0, 2),
        })

    # 5. Method descriptions & warnings
    method_descriptions = {
        "iid_bootstrap": "Efron's independent random resampling with replacement (assumes IID observations; destroys temporal dependence).",
        "moving_block_bootstrap": "Overlapping block resampling of length b preserving local serial dependence, autocorrelation, and volatility clusters.",
        "circular_block_bootstrap": "Periodic wraparound block resampling ensuring equal probability of inclusion for every historical session.",
        "stationary_bootstrap": "Politis & Romano (1994) geometric random block resampling ensuring stationary pseudo-time series.",
    }

    warnings = []
    if config.resampling_method == "iid_bootstrap" and config.metric in ("sharpe_ratio", "max_drawdown"):
        warnings.append("CAUTION: IID bootstrap destroys return autocorrelation and volatility clustering, which artificially compresses drawdown and volatility uncertainty.")
    if config.block_length == 1 and config.resampling_method != "iid_bootstrap":
        warnings.append("Block length = 1 is mathematically identical to IID sampling. Consider block length 5 to 20 for dependent financial returns.")

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    p_val_zero = float(np.mean(boot_stats <= 0.0))
    formatted_hist_bins = [
        {
            "bin_label": f"{b['bin_mid']:.3f}",
            "bin_start": b["bin_start"],
            "bin_end": b["bin_end"],
            "bin_mid": b["bin_mid"],
            "frequency": b["count"],
            "count": b["count"],
            "density_pct": b["density_pct"],
        }
        for b in hist_bins
    ]

    return {
        "success": True,
        "config": config.to_dict(),
        "method_description": method_descriptions.get(config.resampling_method, "Resampling procedure."),
        "execution_time_ms": round(elapsed_ms, 2),
        "point_estimate": round(point_est, 5),
        "sample_replicates": [round(float(x), 5) for x in boot_stats],
        "histogram_bins": formatted_hist_bins,
        "distribution_histogram": formatted_hist_bins,
        "uncertainty_metrics": {
            "point_estimate": round(point_est, 5),
            "bootstrap_mean": round(boot_mean, 5),
            "bootstrap_bias": round(boot_mean - point_est, 5),
            "standard_error": round(boot_se, 5),
            "confidence_level": config.confidence_level,
            "percentile_ci_lower": round(pct_lower, 5),
            "percentile_ci_upper": round(pct_upper, 5),
            "basic_ci_lower": round(basic_lower, 5),
            "basic_ci_upper": round(basic_upper, 5),
            "normal_ci_lower": round(norm_lower, 5),
            "normal_ci_upper": round(norm_upper, 5),
            "p_value_zero_skill": round(p_val_zero, 4),
            "percentile_interval": {"lower": round(pct_lower, 5), "upper": round(pct_upper, 5), "width": round(pct_upper - pct_lower, 5)},
            "basic_interval": {"lower": round(basic_lower, 5), "upper": round(basic_upper, 5), "width": round(basic_upper - basic_lower, 5)},
            "normal_approx_interval": {"lower": round(norm_lower, 5), "upper": round(norm_upper, 5), "width": round(norm_upper - norm_lower, 5)},
        },
        "convergence_trace": running_se_trace,
        "warnings": warnings,
        "reproducibility": {
            "seed": config.seed,
            "fingerprint": compute_canonical_hash({
                "config": config.to_dict(),
                "point_est": point_est,
                "boot_se": boot_se,
            }),
            "disclosure": "Bootstrap confidence intervals quantify estimation variance in the historical sample. They do not predict future non-stationary structural shifts.",
        },
    }


def compute_block_length_sensitivity_scan(
    returns: Sequence[float],
    metric: str = "sharpe_ratio",
    resampling_method: str = "moving_block_bootstrap",
    block_lengths: Sequence[int] = (1, 3, 5, 10, 20, 40),
    num_resamples: int = 250,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Scan confidence interval width across different block lengths to evaluate sensitivity to temporal dependence."""
    arr = np.asarray(returns, dtype=np.float64)
    results = []

    for b in block_lengths:
        cfg = BootstrapLabConfig(
            metric=metric,
            resampling_method=resampling_method,
            block_length=b,
            num_resamples=num_resamples,
            seed=seed,
        )
        res = run_bootstrap_uncertainty_analysis(arr, cfg)
        u = res["uncertainty_metrics"]
        results.append({
            "block_length": b,
            "point_estimate": res["point_estimate"],
            "standard_error": u["standard_error"],
            "ci_lower": u["percentile_interval"]["lower"],
            "ci_upper": u["percentile_interval"]["upper"],
            "ci_width": u["percentile_interval"]["width"],
        })

    return results
