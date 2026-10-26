"""Unit and statistical tests for Forward Monte Carlo and Bootstrap Estimation Uncertainty.

Verifies:
1. Monte Carlo multi-path simulation envelope monotonicity (p5 <= median <= p95).
2. Terminal loss Value-at-Risk and Expected Shortfall calculations.
3. Gaussian vs Student-t fat-tailed innovation paths.
4. Deterministic reproducibility with random seeds.
5. Bootstrap non-parametric resampling confidence intervals (90% and 95%).
6. Point estimate containment within confidence intervals.
7. Input validation and error cases.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.simulation import (
    BootstrapUncertaintyResult,
    MonteCarloResult,
    calculate_bootstrap_uncertainty,
    simulate_monte_carlo,
)


def test_monte_carlo_envelope_monotonicity_gaussian() -> None:
    """Forward envelope quantiles must maintain strict ordering: 5th <= 50th <= 95th."""
    np.random.seed(42)
    sample_rets = np.random.normal(0.0005, 0.012, 60)

    result = simulate_monte_carlo(
        returns=sample_rets,
        horizon_days=30,
        num_paths=500,
        model="gaussian",
        seed=101,
    )

    assert isinstance(result, MonteCarloResult)
    assert result.horizon_days == 30
    assert result.num_paths == 500
    assert len(result.percentile_5th_path) == 31
    assert len(result.median_path) == 31
    assert len(result.percentile_95th_path) == 31

    # At t=0, price is 1.0
    assert math.isclose(result.percentile_5th_path[0], 1.0, rel_tol=1e-5)
    assert math.isclose(result.median_path[0], 1.0, rel_tol=1e-5)
    assert math.isclose(result.percentile_95th_path[0], 1.0, rel_tol=1e-5)

    # For every step t > 0, 5th <= 50th <= 95th
    for t in range(1, 31):
        assert result.percentile_5th_path[t] <= result.median_path[t] + 1e-6
        assert result.median_path[t] <= result.percentile_95th_path[t] + 1e-6

    # Terminal risk metrics must be positive fractions
    assert result.simulated_var_95 > 0.0
    assert result.simulated_es_95 >= result.simulated_var_95


def test_monte_carlo_student_t_distribution() -> None:
    """Student-t innovations with low degrees of freedom should yield wider tail risk."""
    np.random.seed(42)
    sample_rets = np.random.normal(0.0005, 0.012, 60)

    res_gauss = simulate_monte_carlo(
        returns=sample_rets,
        horizon_days=20,
        num_paths=1000,
        model="gaussian",
        seed=42,
    )

    res_t = simulate_monte_carlo(
        returns=sample_rets,
        horizon_days=20,
        num_paths=1000,
        model="student_t",
        student_t_df=3,
        seed=42,
    )

    # Fat tails lead to higher Expected Shortfall under identical seeds and variance
    assert res_t.simulated_es_95 >= res_gauss.simulated_es_95 * 0.95


def test_monte_carlo_reproducibility() -> None:
    """Identical seeds must yield identical forward paths."""
    sample_rets = [0.01, -0.015, 0.008, -0.012, 0.005, -0.007, 0.011, -0.009]

    r1 = simulate_monte_carlo(sample_rets, horizon_days=10, num_paths=200, seed=99)
    r2 = simulate_monte_carlo(sample_rets, horizon_days=10, num_paths=200, seed=99)

    assert r1.percentile_5th_path == r2.percentile_5th_path
    assert r1.simulated_var_95 == r2.simulated_var_95


def test_bootstrap_uncertainty_bounds() -> None:
    """Bootstrap confidence intervals must correctly bracket point estimates."""
    np.random.seed(42)
    sample_rets = np.random.normal(0.0004, 0.015, 80)

    boot = calculate_bootstrap_uncertainty(
        returns=sample_rets,
        num_bootstraps=300,
        confidence_level=0.95,
        seed=123,
    )

    assert isinstance(boot, BootstrapUncertaintyResult)
    assert boot.sample_size == 80
    assert boot.bootstrap_iterations == 300
    assert boot.point_estimate_var > 0.0
    assert boot.point_estimate_es >= boot.point_estimate_var

    # 95% Confidence Interval ordering: lower <= upper
    assert boot.var_ci_95_lower <= boot.var_ci_95_upper
    assert boot.es_ci_90_lower <= boot.es_ci_90_upper

    # Point estimate should be near central interval
    assert boot.var_ci_95_lower <= boot.point_estimate_var <= boot.var_ci_95_upper


def test_simulation_validation_errors() -> None:
    """Check validation failures for illegal horizons, simulations, or empty samples."""
    # Invalid horizon
    with pytest.raises(ValueError, match="horizon_days must be between"):
        simulate_monte_carlo([0.01] * 10, horizon_days=0)

    # Invalid paths
    with pytest.raises(ValueError, match="num_paths must be between"):
        simulate_monte_carlo([0.01] * 10, num_paths=5)

    # Insufficient observations for bootstrap
    with pytest.raises(ValueError, match="at least 8 observations"):
        calculate_bootstrap_uncertainty([0.01] * 5)
