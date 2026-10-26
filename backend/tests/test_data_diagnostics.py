"""Unit and statistical tests for the Data Diagnostics Engine.

Verifies:
1. Sample skewness and excess kurtosis calculations against known distributions.
2. Jarque-Bera test statistic computation and exact chi-square survival p-values.
3. Lag-1 autocorrelation detection.
4. Zero-return frequency detection.
5. Automated model suitability recommendation rules.
6. Input validation and edge-case error handling.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.data_diagnostics import (
    DataQualityReport,
    calculate_data_diagnostics,
)


def test_diagnostics_normal_series() -> None:
    """A standard Gaussian sample should have skewness near 0 and excess kurtosis near 0."""
    np.random.seed(42)
    # 500 draws from normal distribution
    normal_rets = np.random.normal(0.0005, 0.01, 500)
    diag = calculate_data_diagnostics(normal_rets)

    assert isinstance(diag, DataQualityReport)
    assert diag.observations_count == 500
    assert abs(diag.skewness) < 0.25
    assert abs(diag.excess_kurtosis) < 0.4
    assert diag.jarque_bera_stat >= 0.0
    assert 0.0 <= diag.jarque_bera_p_value <= 1.0
    # For standard Gaussian, p-value should not reject normality at 5%
    assert diag.is_normal_at_5pct is True
    assert abs(diag.autocorrelation_lag1) < 0.15
    assert "NORMAL" in diag.suitability_verdict


def test_diagnostics_heavy_tailed_series() -> None:
    """A heavy-tailed sample should show positive excess kurtosis and reject normality."""
    np.random.seed(42)
    # Student-t with 3 degrees of freedom creates pronounced fat tails
    t_rets = np.random.standard_t(df=3.0, size=500) * 0.01
    diag = calculate_data_diagnostics(t_rets)

    assert diag.excess_kurtosis > 1.0
    assert diag.jarque_bera_stat > 15.0
    assert diag.jarque_bera_p_value < 0.01
    assert diag.is_normal_at_5pct is False
    assert len(diag.warnings) > 0
    assert any("Student-t" in rec or "Historical Simulation" in rec for rec in diag.recommendations)


def test_diagnostics_autocorrelated_series() -> None:
    """An AR(1) process should be detected by lag-1 autocorrelation."""
    np.random.seed(42)
    rets = [0.0]
    for _ in range(300):
        next_ret = 0.5 * rets[-1] + float(np.random.normal(0.0, 0.01))
        rets.append(next_ret)

    diag = calculate_data_diagnostics(rets)
    assert diag.autocorrelation_lag1 > 0.35
    assert any("autocorrelation" in w.lower() for w in diag.warnings)


def test_diagnostics_zero_returns() -> None:
    """Detect flat prices / illiquid trading days."""
    rets = [0.0] * 20 + [0.01, -0.01, 0.02, -0.02] * 5
    diag = calculate_data_diagnostics(rets)

    assert math.isclose(diag.zero_returns_pct, 50.0, abs_tol=1e-1)


def test_diagnostics_validation_errors() -> None:
    """Test validation boundaries."""
    # Under minimum sample size
    with pytest.raises(ValueError, match="at least 8 observations"):
        calculate_data_diagnostics([0.01, -0.01, 0.02])

    # Non-finite values
    with pytest.raises(ValueError, match="non-finite values"):
        calculate_data_diagnostics([0.01, float("nan"), 0.02, -0.01, 0.03, -0.02, 0.01, 0.00])


def test_diagnostics_to_dict() -> None:
    """Verify JSON serialization contract."""
    np.random.seed(42)
    rets = np.random.normal(0.001, 0.015, 50).tolist()
    diag = calculate_data_diagnostics(rets)
    d = diag.to_dict()

    assert d["observations_count"] == 50
    assert "mean" in d
    assert "skewness" in d
    assert "excess_kurtosis" in d
    assert "jarque_bera_stat" in d
    assert "recommendations" in d
