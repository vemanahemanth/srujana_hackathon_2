"""Unit and mathematical reference tests for the FragilityShield risk engine.

Verifies:
- Annualized historical volatility against hand-calculated analytical benchmarks and ddof conventions.
- Historical Value at Risk (VaR) at 95% and 99% with explicit empirical quantile interpolation.
- Expected Shortfall (CVaR) with manually identified tail subsets and coherence guarantee (ES >= VaR).
- Tied observations and small sample behavior.
- Maximum drawdown, peak-to-trough duration, and recovery duration on recovered and unrecovered curves.
- Input immutability and error boundary enforcement.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.risk import (
    DrawdownResult,
    RiskMetricsReport,
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_parametric_es,
    calculate_parametric_var,
    calculate_risk_report,
)


# ============================================================================
# 1. Annualized Historical Volatility Tests
# ============================================================================

class TestAnnualizedVolatility:
    """Test suite for annualized volatility calculations."""

    def test_hand_calculated_volatility_reference(self) -> None:
        """Verify annualized volatility against a hand-calculated reference.

        Analytical setup:
            Returns: R = [-0.01, 0.02, 0.01, -0.02]
            N = 4, mean = 0.0
            Squared deviations: [0.0001, 0.0004, 0.0001, 0.0004] -> sum = 0.0010
            With ddof=1:
                variance = 0.0010 / (4 - 1) = 0.0010 / 3 = 1/3000
                daily_std = sqrt(1/3000)
                annual_vol (252 days) = sqrt(252 / 3000) = sqrt(0.084) = 0.2898275349237888...
        """
        returns = [-0.01, 0.02, 0.01, -0.02]
        vol = calculate_annualized_volatility(returns, annualization_factor=252.0, ddof=1)
        expected = math.sqrt(252.0 * 0.0010 / 3.0)
        assert math.isclose(vol, expected, rel_tol=1e-9)
        assert math.isclose(vol, 0.2898275349237888, rel_tol=1e-9)

    def test_ddof_zero_population_volatility(self) -> None:
        """Verify ddof=0 calculates population standard deviation without Bessel's correction.

        Setup:
            Returns: R = [-0.01, 0.02, 0.01, -0.02]
            With ddof=0:
                variance = 0.0010 / 4 = 0.00025
                annual_vol (252 days) = sqrt(252 * 0.00025) = sqrt(0.063) = 0.2509980079602226...
        """
        returns = [-0.01, 0.02, 0.01, -0.02]
        vol_pop = calculate_annualized_volatility(returns, annualization_factor=252.0, ddof=0)
        expected = math.sqrt(252.0 * 0.00025)
        assert math.isclose(vol_pop, expected, rel_tol=1e-9)
        assert math.isclose(vol_pop, 0.2509980079602226, rel_tol=1e-9)

    def test_constant_returns_yield_zero_volatility(self) -> None:
        """Verify identical returns have zero standard deviation."""
        returns = [0.005, 0.005, 0.005, 0.005, 0.005]
        vol = calculate_annualized_volatility(returns)
        assert math.isclose(vol, 0.0, abs_tol=1e-12)

    def test_custom_annualization_factor(self) -> None:
        """Verify custom annualization factor (e.g. 12.0 for monthly returns)."""
        returns = [0.02, -0.01, 0.03, -0.02]
        vol_monthly = calculate_annualized_volatility(returns, annualization_factor=12.0, ddof=1)
        daily_std = float(np.std(returns, ddof=1))
        assert math.isclose(vol_monthly, daily_std * math.sqrt(12.0), rel_tol=1e-9)

    def test_reject_invalid_annualization_factor(self) -> None:
        """Verify non-positive and non-finite annualization factors are rejected."""
        returns = [0.01, -0.01, 0.02]
        with pytest.raises(ValueError, match="annualization_factor must be positive"):
            calculate_annualized_volatility(returns, annualization_factor=0.0)
        with pytest.raises(ValueError, match="annualization_factor must be positive"):
            calculate_annualized_volatility(returns, annualization_factor=-252.0)
        with pytest.raises(ValueError, match="annualization_factor must be positive"):
            calculate_annualized_volatility(returns, annualization_factor=float("nan"))

    def test_reject_invalid_ddof(self) -> None:
        """Verify negative ddof or N <= ddof is rejected."""
        returns = [0.01, -0.01]
        with pytest.raises(ValueError, match="ddof must be a non-negative integer"):
            calculate_annualized_volatility(returns, ddof=-1)
        with pytest.raises(ValueError, match="Sample size N=2 must be strictly greater than ddof=2"):
            calculate_annualized_volatility(returns, ddof=2)

    @pytest.mark.parametrize("insufficient", [[], [0.01]])
    def test_reject_insufficient_samples(self, insufficient: list[float]) -> None:
        """Verify fewer than 2 return observations raises ValueError."""
        with pytest.raises(ValueError, match="at least 2 return observations"):
            calculate_annualized_volatility(insufficient)

    def test_reject_non_finite_returns(self) -> None:
        """Verify NaN, Inf, and None returns are rejected."""
        with pytest.raises(ValueError, match="must be finite"):
            calculate_annualized_volatility([0.01, float("nan"), 0.02])
        with pytest.raises(ValueError, match="must be finite"):
            calculate_annualized_volatility([0.01, float("inf"), 0.02])
        with pytest.raises(ValueError, match="is None"):
            calculate_annualized_volatility([0.01, None, 0.02])  # type: ignore

    def test_input_immutability(self) -> None:
        """Verify input sequence is not mutated in-place."""
        returns_list = [0.02, -0.01, 0.03, -0.02]
        copy_list = list(returns_list)
        _ = calculate_annualized_volatility(returns_list)
        assert returns_list == copy_list

        returns_arr = np.array([0.02, -0.01, 0.03, -0.02])
        copy_arr = returns_arr.copy()
        _ = calculate_annualized_volatility(returns_arr)
        np.testing.assert_array_equal(returns_arr, copy_arr)


# ============================================================================
# 2. Historical Value at Risk (VaR) Tests
# ============================================================================

class TestHistoricalVaR:
    """Test suite for Historical Value at Risk."""

    def test_hand_calculated_var_reference(self) -> None:
        """Verify historical VaR against hand-calculated quantile references.

        Analytical setup:
            Returns R = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04] (10 obs)
            Losses L = -R:
                [-0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04, 0.05]
            Quantile at alpha=0.90 (linear interpolation, index = 0.90 * 9 = 8.1):
                L[8] = 0.04, L[9] = 0.05 -> 0.04 + 0.1 * (0.05 - 0.04) = 0.041
            Quantile at alpha=0.80 (index = 0.80 * 9 = 7.2):
                L[7] = 0.03, L[8] = 0.04 -> 0.03 + 0.2 * (0.04 - 0.03) = 0.032
        """
        returns = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04]
        var_90 = calculate_historical_var(returns, confidence_level=0.90, method="linear")
        var_80 = calculate_historical_var(returns, confidence_level=0.80, method="linear")

        assert math.isclose(var_90, 0.041, rel_tol=1e-9)
        assert math.isclose(var_80, 0.032, rel_tol=1e-9)

    def test_twenty_observation_var_95(self) -> None:
        """Verify 95% VaR on 20 linearly spaced losses [0.01, ..., 0.20].

        Setup:
            Losses: 0.01 to 0.20 in increments of 0.01 (Returns = -Losses)
            N = 20. At 0.95: index = 0.95 * 19 = 18.05
            L[18] = 0.19, L[19] = 0.20 -> 0.19 + 0.05 * 0.01 = 0.1905
        """
        losses = np.linspace(0.01, 0.20, 20)
        returns = -losses
        var_95 = calculate_historical_var(returns, confidence_level=0.95, method="linear")
        assert math.isclose(var_95, 0.1905, rel_tol=1e-9)

    def test_all_positive_returns_yield_negative_var(self) -> None:
        """Verify strictly positive returns result in a negative loss (gain)."""
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        var_95 = calculate_historical_var(returns, confidence_level=0.95)
        # All returns are positive, so all losses are negative -> VaR < 0
        assert var_95 < 0.0

    def test_all_negative_returns_yield_positive_var(self) -> None:
        """Verify strictly negative returns result in positive loss VaR."""
        returns = [-0.05, -0.04, -0.03, -0.02, -0.01]
        var_95 = calculate_historical_var(returns, confidence_level=0.95)
        assert var_95 > 0.0

    def test_tied_observations_in_var(self) -> None:
        """Verify VaR handles tied observations correctly."""
        returns = [-0.02, -0.02, -0.02, 0.01, 0.01]
        var_80 = calculate_historical_var(returns, confidence_level=0.80)
        assert math.isclose(var_80, 0.02, rel_tol=1e-9)

    @pytest.mark.parametrize("invalid_conf", [0.0, 1.0, -0.05, 1.05, float("nan"), "0.95"])
    def test_reject_invalid_confidence_level(self, invalid_conf: float) -> None:
        """Verify confidence level must be strictly between 0 and 1."""
        returns = [0.01, -0.02, 0.03]
        with pytest.raises(ValueError, match="confidence_level must be strictly between"):
            calculate_historical_var(returns, confidence_level=invalid_conf)  # type: ignore

    def test_reject_invalid_quantile_method(self) -> None:
        """Verify unsupported quantile interpolation methods are rejected."""
        returns = [0.01, -0.02, 0.03]
        with pytest.raises(ValueError, match="method must be one of"):
            calculate_historical_var(returns, confidence_level=0.95, method="unsupported_method")


# ============================================================================
# 3. Expected Shortfall (CVaR) Tests
# ============================================================================

class TestExpectedShortfall:
    """Test suite for Historical Expected Shortfall."""

    def test_hand_calculated_es_reference(self) -> None:
        """Verify ES against hand-calculated tail mean references.

        Analytical setup:
            Returns R = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04]
            Losses L = [-0.04, ..., 0.03, 0.04, 0.05]
            At alpha=0.80:
                VaR_0.80 = 0.032
                Tail losses >= 0.032: [0.04, 0.05]
                ES_0.80 = (0.04 + 0.05) / 2 = 0.045
            At alpha=0.90:
                VaR_0.90 = 0.041
                Tail losses >= 0.041: [0.05]
                ES_0.90 = 0.05
        """
        returns = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.00, 0.01, 0.02, 0.03, 0.04]
        es_80 = calculate_expected_shortfall(returns, confidence_level=0.80)
        es_90 = calculate_expected_shortfall(returns, confidence_level=0.90)

        assert math.isclose(es_80, 0.045, rel_tol=1e-9)
        assert math.isclose(es_90, 0.050, rel_tol=1e-9)

    def test_coherence_guarantee_es_greater_equal_var(self) -> None:
        """Verify ES is strictly greater than or equal to VaR across diverse samples."""
        np.random.seed(42)
        for _ in range(10):
            sample = np.random.normal(loc=0.0005, scale=0.015, size=50)
            for conf in (0.90, 0.95, 0.99):
                var = calculate_historical_var(sample, confidence_level=conf)
                es = calculate_expected_shortfall(sample, confidence_level=conf)
                assert es >= (var - 1e-12), f"ES={es} < VaR={var} at conf={conf}"

    def test_tied_tail_observations_in_es(self) -> None:
        """Verify ES when multiple tail losses are identical."""
        # Losses: [0.0, 0.01, 0.03, 0.03, 0.03] -> Returns = -Losses
        returns = [0.0, -0.01, -0.03, -0.03, -0.03]
        es_80 = calculate_expected_shortfall(returns, confidence_level=0.80)
        var_80 = calculate_historical_var(returns, confidence_level=0.80)
        assert math.isclose(var_80, 0.03, rel_tol=1e-9)
        assert math.isclose(es_80, 0.03, rel_tol=1e-9)

    def test_small_sample_es(self) -> None:
        """Verify ES on a 5-observation dataset."""
        returns = [-0.10, -0.05, 0.0, 0.02, 0.05]
        # Losses: [-0.05, -0.02, 0.0, 0.05, 0.10]
        # At 0.80, index = 0.8 * 4 = 3.2 -> VaR = 0.05 + 0.2 * (0.10 - 0.05) = 0.06
        # Tail losses >= 0.06: [0.10] -> ES = 0.10
        es = calculate_expected_shortfall(returns, confidence_level=0.80)
        assert math.isclose(es, 0.10, rel_tol=1e-9)


# ============================================================================
# 4. Maximum Drawdown & Duration Tests
# ============================================================================

class TestMaximumDrawdown:
    """Test suite for Maximum Drawdown, peak-to-trough, and recovery durations."""

    def test_hand_calculated_unrecovered_drawdown(self) -> None:
        """Verify maximum drawdown on a known unrecovered equity curve.

        Analytical setup:
            Equity: V = [100.0, 120.0, 90.0, 110.0, 130.0, 80.0, 100.0]
            Running peaks:
                t=0: 100, DD = 0.0
                t=1: 120, DD = 0.0
                t=2: 120, DD = (120 - 90)/120 = 25%
                t=3: 120, DD = (120 - 110)/120 = 8.33%
                t=4: 130, DD = 0.0  <- Global peak
                t=5: 130, DD = (130 - 80)/130 = 50/130 ~= 38.4615% <- Max Drawdown
                t=6: 130, DD = (130 - 100)/130 = 30/130 ~= 23.08%
            Expected:
                MDD = 50.0 / 130.0 = 0.38461538461538464
                Peak value = 130.0 at index 4
                Trough value = 80.0 at index 5
                Peak-to-trough duration = 5 - 4 = 1 interval
                Recovery: unrecovered (series ends at 100.0 < 130.0)
                is_recovered = False, recovery_index = None, recovery_duration = None
        """
        equity = [100.0, 120.0, 90.0, 110.0, 130.0, 80.0, 100.0]
        res = calculate_maximum_drawdown(equity)

        assert isinstance(res, DrawdownResult)
        assert math.isclose(res.max_drawdown, 50.0 / 130.0, rel_tol=1e-9)
        assert math.isclose(res.peak_value, 130.0)
        assert math.isclose(res.trough_value, 80.0)
        assert res.peak_index == 4
        assert res.trough_index == 5
        assert res.peak_to_trough_duration == 1
        assert res.is_recovered is False
        assert res.recovery_index is None
        assert res.recovery_duration is None
        assert res.total_drawdown_duration is None

    def test_hand_calculated_recovered_drawdown(self) -> None:
        """Verify maximum drawdown and recovery metrics on a fully recovered curve.

        Analytical setup:
            Equity: V = [100.0, 120.0, 90.0, 100.0, 125.0]
            t=0: 100, peak 100
            t=1: 120, peak 120
            t=2: 90,  peak 120, DD = (120 - 90)/120 = 0.25 (25%) <- Max Drawdown
            t=3: 100, peak 120, DD = 16.67%
            t=4: 125, peak 125, DD = 0.0 (recovers peak 120 at index 4)

            Expected:
                MDD = 0.25 (25%)
                Peak index = 1 (120.0)
                Trough index = 2 (90.0)
                Peak-to-trough duration = 2 - 1 = 1 interval
                Recovery index = 4 (125.0 >= 120.0)
                is_recovered = True
                recovery_duration = 4 - 2 = 2 intervals (trough to recovery)
                total_drawdown_duration = 4 - 1 = 3 intervals (peak to recovery)
        """
        equity = [100.0, 120.0, 90.0, 100.0, 125.0]
        res = calculate_maximum_drawdown(equity)

        assert math.isclose(res.max_drawdown, 0.25, rel_tol=1e-9)
        assert math.isclose(res.peak_value, 120.0)
        assert math.isclose(res.trough_value, 90.0)
        assert res.peak_index == 1
        assert res.trough_index == 2
        assert res.peak_to_trough_duration == 1
        assert res.is_recovered is True
        assert res.recovery_index == 4
        assert res.recovery_duration == 2
        assert res.total_drawdown_duration == 3

    def test_strictly_increasing_equity_curve(self) -> None:
        """Verify monotonically increasing curve has zero drawdown and duration."""
        equity = [100.0, 105.0, 110.0, 115.0, 120.0]
        res = calculate_maximum_drawdown(equity)
        assert math.isclose(res.max_drawdown, 0.0, abs_tol=1e-12)
        assert res.peak_to_trough_duration == 0
        assert res.is_recovered is True

    def test_reject_invalid_equity_curves(self) -> None:
        """Verify non-positive, NaN, Inf, and insufficient observations are rejected."""
        with pytest.raises(ValueError, match="at least 2 equity observations"):
            calculate_maximum_drawdown([100.0])
        with pytest.raises(ValueError, match="must be strictly positive"):
            calculate_maximum_drawdown([100.0, 0.0, 90.0])
        with pytest.raises(ValueError, match="must be strictly positive"):
            calculate_maximum_drawdown([100.0, -50.0, 90.0])
        with pytest.raises(ValueError, match="must be finite"):
            calculate_maximum_drawdown([100.0, float("nan"), 90.0])

    def test_drawdown_result_serialization(self) -> None:
        """Verify DrawdownResult to_dict roundtrip."""
        equity = [100.0, 120.0, 90.0, 100.0, 125.0]
        res = calculate_maximum_drawdown(equity)
        d = res.to_dict()
        assert d["max_drawdown"] == 0.25
        assert d["is_recovered"] is True
        assert d["recovery_duration"] == 2
        assert len(d["drawdown_series"]) == len(equity)

    def test_drawdown_partial_rebound_is_not_recovered(self) -> None:
        """Verify a partial rebound below the peak does NOT count as a recovery."""
        # Peak 130 at idx 0, drops to 80 at idx 1 (MDD = 50/130), rebounds to 110 at idx 2 (< 130)
        equity = [130.0, 80.0, 110.0]
        res = calculate_maximum_drawdown(equity)
        assert math.isclose(res.max_drawdown, 50.0 / 130.0)
        assert res.peak_index == 0
        assert res.trough_index == 1
        assert res.is_recovered is False
        assert res.recovery_index is None
        assert res.recovery_duration is None

    def test_drawdown_equal_peaks_selection(self) -> None:
        """Verify when consecutive equal peaks occur, the latest peak before descent is selected."""
        # Peaks at idx 1 and idx 2 both equal 120. Descent occurs from idx 2 to idx 3 (90)
        equity = [100.0, 120.0, 120.0, 90.0]
        res = calculate_maximum_drawdown(equity)
        assert math.isclose(res.max_drawdown, (120.0 - 90.0) / 120.0)
        assert res.peak_index == 2  # Latest peak before descent
        assert res.trough_index == 3
        assert res.peak_to_trough_duration == 1

    def test_drawdown_tied_troughs_deterministic(self) -> None:
        """Verify when multiple troughs have identical max drawdown, earliest trough is chosen."""
        # Trough 80 occurs at idx 1 and idx 3
        equity = [100.0, 80.0, 90.0, 80.0, 100.0]
        res = calculate_maximum_drawdown(equity)
        assert math.isclose(res.max_drawdown, 0.20)
        assert res.trough_index == 1  # Earliest trough


# ============================================================================
# Regression Tests for Issue A & B
# ============================================================================

class TestRiskEngineIssueRegressions:
    """Explicit regression tests for Issue A (ES consistency) and Issue B (Drawdown)."""

    def test_es_acerbi_tasche_fractional_tail_weight(self) -> None:
        """Verify Acerbi-Tasche discrete ES with fractional tail mass.

        Setup:
            Losses: [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10] (10 obs)
            Returns: -Losses
            alpha = 0.85 -> tail mass w = 10 * 0.15 = 1.5 observations
            k = floor(1.5) = 1, frac = 0.5
            Top loss L[9] = 0.10 (weight 1.0)
            Second loss L[8] = 0.09 (weight 0.5)
            ES = (1.0 * 0.10 + 0.5 * 0.09) / 1.5 = (0.10 + 0.045) / 1.5 = 0.145 / 1.5 = 0.09666666666666668
        """
        losses = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10])
        returns = -losses
        es = calculate_expected_shortfall(returns, confidence_level=0.85)
        expected = (0.10 + 0.5 * 0.09) / 1.5
        assert math.isclose(es, expected, rel_tol=1e-9)

    def test_es_with_heavy_ties_preserves_expected_value(self) -> None:
        """Verify ES when 80% of observations are tied at the loss threshold."""
        losses = np.array([0.01, 0.02, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05])
        returns = -losses
        es_50 = calculate_expected_shortfall(returns, confidence_level=0.50)
        assert math.isclose(es_50, 0.05, rel_tol=1e-9)


# ============================================================================
# 5. Consolidated Risk Report Tests
# ============================================================================

class TestRiskReport:
    """Test suite for calculate_risk_report function."""

    def test_risk_report_on_synthetic_data(self) -> None:
        """Verify complete risk report generation and warnings."""
        np.random.seed(123)
        returns = np.random.normal(loc=0.0004, scale=0.012, size=150)
        report = calculate_risk_report(returns)

        assert isinstance(report, RiskMetricsReport)
        assert report.observations_count == 150
        assert report.volatility_annualized > 0.0
        assert report.var_99 >= report.var_95
        assert report.expected_shortfall_95 >= report.var_95
        assert report.expected_shortfall_99 >= report.var_99
        assert report.drawdown is not None
        assert report.drawdown.max_drawdown >= 0.0
        assert len(report.warnings) == 0  # 150 obs is >= 100, no small sample warning

    def test_risk_report_small_sample_warnings(self) -> None:
        """Verify appropriate diagnostic warnings for small sample sizes."""
        returns = [0.01, -0.02, 0.015, -0.01, 0.02]  # N=5 < 20
        report = calculate_risk_report(returns)
        assert len(report.warnings) == 2
        assert "small for 95% VaR" in report.warnings[0]
        assert "insufficient for reliable 99% VaR/ES" in report.warnings[1]


# ============================================================================
# 6. Parametric VaR, Parametric ES, and Quantile Interpolation Conformance
# ============================================================================

class TestParametricRiskAndQuantileConventions:
    """Rigorous mathematical tests for Parametric VaR/ES and Quantile conventions."""

    def test_ten_losses_quantile_interpolation_discrepancy(self) -> None:
        """Verify the exact mathematical behavior of NumPy quantile methods on ten losses.

        Analytical setup:
            Losses L = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
            Returns R = -L
            alpha = 0.90 -> continuous quantile index q = 0.90 * (10 - 1) = 8.1
            linear: L[8] + 0.1 * (L[9] - L[8]) = 0.09 + 0.1 * 0.01 = 0.0910
            lower: floor(8.1) = 8 -> L[8] = 0.0900
            higher: ceil(8.1) = 9 -> L[9] = 0.1000
            nearest: round(8.1) = 8 -> L[8] = 0.0900
            midpoint: 0.5 * (L[8] + L[9]) = 0.0950
        """
        losses = np.linspace(0.01, 0.10, 10)
        returns = -losses

        # 1. Linear interpolation (default)
        var_linear = calculate_historical_var(returns, confidence_level=0.90, method="linear")
        assert math.isclose(var_linear, 0.0910, rel_tol=1e-9)

        # 2. Lower bound method
        var_lower = calculate_historical_var(returns, confidence_level=0.90, method="lower")
        assert math.isclose(var_lower, 0.0900, rel_tol=1e-9)

        # 3. Higher bound method
        var_higher = calculate_historical_var(returns, confidence_level=0.90, method="higher")
        assert math.isclose(var_higher, 0.1000, rel_tol=1e-9)

        # 4. Nearest rank method
        var_nearest = calculate_historical_var(returns, confidence_level=0.90, method="nearest")
        assert math.isclose(var_nearest, 0.0900, rel_tol=1e-9)

        # 5. Midpoint method
        var_midpoint = calculate_historical_var(returns, confidence_level=0.90, method="midpoint")
        assert math.isclose(var_midpoint, 0.0950, rel_tol=1e-9)

    def test_parametric_var_zero_mean_analytical(self) -> None:
        """Verify parametric VaR for zero-mean symmetric returns against hand calculation.

        Setup:
            Returns R = [-0.02, -0.01, 0.01, 0.02] (N=4, mean = 0.0)
            Sum of squared deviations: 0.0004 + 0.0001 + 0.0001 + 0.0004 = 0.0010
            With ddof=1: variance = 0.0010 / 3 = 1/3000 -> std = sqrt(1/3000) ~= 0.018257418583505537
            Standard normal 95% quantile z_0.95 = 1.6448536269514722
            Under positive loss convention and mu=0:
                VaR_0.95 = -mu + z_0.95 * sigma = 1.6448536269514722 * sqrt(1/3000) ~= 0.030030777178082987
        """
        returns = [-0.02, -0.01, 0.01, 0.02]
        var_95 = calculate_parametric_var(returns, confidence_level=0.95, assume_zero_mean=True, ddof=1)
        sigma = math.sqrt(0.0010 / 3.0)
        z_95 = 1.6448536269514722
        expected_var = z_95 * sigma

        assert math.isclose(var_95, expected_var, rel_tol=1e-6)
        assert math.isclose(var_95, 0.03003078, rel_tol=1e-5)

    def test_parametric_var_nonzero_mean_and_mean_toggle(self) -> None:
        """Verify nonzero mean shift in parametric VaR and effect of assume_zero_mean toggle.

        Setup:
            Returns R = [0.00, 0.01, 0.02, 0.03, 0.04] (N=5, mean mu = 0.02)
            Squared deviations: (0-0.02)^2 + (0.01-0.02)^2 + (0.02-0.02)^2 + (0.03-0.02)^2 + (0.04-0.02)^2
                               = 0.0004 + 0.0001 + 0.0000 + 0.0001 + 0.0004 = 0.0010
            With ddof=1: variance = 0.0010 / 4 = 0.00025 -> sigma = sqrt(0.00025) = 0.015811388300841896
            z_0.95 = 1.6448536269514722
            With empirical mean:
                VaR_0.95 = -0.02 + 1.6448536269514722 * 0.015811388300841896 = 0.006007559132517658
            With assume_zero_mean=True:
                VaR_0.95 = 0.0 + 1.6448536269514722 * 0.015811388300841896 = 0.026007559132517658
        """
        returns = [0.00, 0.01, 0.02, 0.03, 0.04]
        var_empirical_mean = calculate_parametric_var(returns, confidence_level=0.95, assume_zero_mean=False, ddof=1)
        var_zero_mean = calculate_parametric_var(returns, confidence_level=0.95, assume_zero_mean=True, ddof=1)

        sigma = math.sqrt(0.00025)
        z_95 = 1.6448536269514722
        expected_empirical = -0.02 + z_95 * sigma
        expected_zero = 0.0 + z_95 * sigma

        assert math.isclose(var_empirical_mean, expected_empirical, rel_tol=1e-6)
        assert math.isclose(var_zero_mean, expected_zero, rel_tol=1e-6)
        assert math.isclose(var_zero_mean - var_empirical_mean, 0.02, rel_tol=1e-6)

    def test_parametric_var_population_vs_sample_std(self) -> None:
        """Verify ddof=0 (population) vs ddof=1 (sample) standard deviation conventions."""
        returns = [-0.01, 0.00, 0.01]
        # N=3, mean=0. Sum sq diffs = 0.0001 + 0 + 0.0001 = 0.0002
        # ddof=1: var = 0.0002 / 2 = 0.0001 -> sigma = 0.01
        # ddof=0: var = 0.0002 / 3 -> sigma = sqrt(0.0002 / 3)
        z_95 = 1.6448536269514722
        var_sample = calculate_parametric_var(returns, confidence_level=0.95, ddof=1)
        var_pop = calculate_parametric_var(returns, confidence_level=0.95, ddof=0)

        assert math.isclose(var_sample, z_95 * 0.01, rel_tol=1e-6)
        assert math.isclose(var_pop, z_95 * math.sqrt(0.0002 / 3.0), rel_tol=1e-6)
        assert var_sample > var_pop

    def test_parametric_var_constant_returns(self) -> None:
        """Verify constant returns produce zero volatility and VaR = -mu."""
        returns = [0.03, 0.03, 0.03, 0.03]
        var = calculate_parametric_var(returns, confidence_level=0.95, assume_zero_mean=False)
        assert math.isclose(var, -0.03, abs_tol=1e-12)

    def test_parametric_es_analytical_closed_form(self) -> None:
        """Verify parametric expected shortfall satisfies ES = -mu + sigma * phi(z_alpha) / (1 - alpha).

        Setup:
            Returns R = [-0.02, -0.01, 0.01, 0.02] (mean mu = 0.0, sigma = sqrt(1/3000))
            alpha = 0.95, z_0.95 = 1.6448536269514722
            phi(z_0.95) = (1 / sqrt(2*pi)) * exp(-0.5 * 1.6448536269514722^2) ~= 0.10313564037803023
            tail_density_factor = phi(z_0.95) / (1 - 0.95) = 0.10313564037803023 / 0.05 ~= 2.0627128075606046
            ES_0.95 = 0.0 + 2.0627128075606046 * sqrt(1/3000) ~= 0.03765987787363412
        """
        returns = [-0.02, -0.01, 0.01, 0.02]
        es_95 = calculate_parametric_es(returns, confidence_level=0.95, assume_zero_mean=True, ddof=1)
        var_95 = calculate_parametric_var(returns, confidence_level=0.95, assume_zero_mean=True, ddof=1)

        sigma = math.sqrt(0.0010 / 3.0)
        z_95 = 1.6448536269514722
        phi_z = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z_95**2)
        expected_es = sigma * (phi_z / 0.05)

        assert math.isclose(es_95, expected_es, rel_tol=1e-6)
        assert es_95 > var_95
        assert math.isclose(es_95, 0.0376598, rel_tol=1e-5)

    def test_parametric_rejects_invalid_inputs(self) -> None:
        """Verify boundary validations for parametric calculations."""
        # Confidence boundaries
        with pytest.raises(ValueError, match="confidence_level must be strictly between"):
            calculate_parametric_var([0.01, 0.02], confidence_level=0.0)
        with pytest.raises(ValueError, match="confidence_level must be strictly between"):
            calculate_parametric_var([0.01, 0.02], confidence_level=1.0)
        with pytest.raises(ValueError, match="confidence_level must be strictly between"):
            calculate_parametric_es([0.01, 0.02], confidence_level=-0.1)

        # Insufficient observations vs ddof
        with pytest.raises(ValueError, match="must be strictly greater than ddof"):
            calculate_parametric_var([0.01, 0.02], ddof=2)
        with pytest.raises(ValueError, match="at least 2 return observations"):
            calculate_parametric_var([0.01], ddof=1)

        # Non-finite values
        with pytest.raises(ValueError, match="must be finite"):
            calculate_parametric_var([0.01, float("nan"), -0.02])
        with pytest.raises(ValueError, match="must be finite"):
            calculate_parametric_es([0.01, float("inf"), -0.02])


