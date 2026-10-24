"""Tests for Phase 8.2: Forecast Timing, Look-Ahead Invariance, VaR Backtesting & Statistical Validation.

Deterministic, pure-Python tests covering:
- VaR forecast validation and temporal integrity
- Loss convention (L = -R) and breach indicator logic
- Exact Kupiec POF unconditional coverage test (including zero-breach & all-breach boundaries)
- Christoffersen independence and conditional coverage test
- EWMA conditional variance causal recurrence and future observation invariance
- Rolling walk-forward backtesting across models
- Benchmark evaluation_mode contract and reporting
"""

import math
import numpy as np
import pytest

from fragility_engine.backtest import (
    BacktestReport,
    ChristoffersenTestResult,
    KupiecTestResult,
    VaRBreachEvaluation,
    VaRForecast,
    backtest_model_rolling,
    calculate_christoffersen_test,
    calculate_kupiec_pof_test,
    evaluate_var_breaches,
)
from fragility_engine.benchmarks import (
    BenchmarkReport,
    BenchmarkSpecification,
    execute_model_benchmark,
)
from fragility_engine.fragility import (
    calculate_ewma_conditional_variances,
    calculate_ewma_volatility,
)
from fragility_engine.plugins import get_default_registry


# ==============================================================================
# 1. VaR Forecast and Contract Validation Tests
# ==============================================================================

def test_var_forecast_validation():
    """Verify VaRForecast enforces temporal ordering, positive horizon, and valid bounds."""
    # Valid forecast
    fc = VaRForecast(
        forecast_id="FC-0001",
        origin_index=0,
        target_index=1,
        confidence_level=0.95,
        var_estimate=0.025,
        horizon=1,
        model_id="builtin.parametric_gaussian",
    )
    assert fc.origin_index == 0
    assert fc.target_index == 1
    assert fc.horizon == 1
    assert fc.confidence_level == 0.95

    # Target index <= origin index must raise ValueError (look-ahead or backward forecast)
    with pytest.raises(ValueError, match="target_index.*must be strictly greater than origin_index"):
        VaRForecast(
            forecast_id="FC-BAD1",
            origin_index=5,
            target_index=4,
            confidence_level=0.95,
            var_estimate=0.025,
        )

    with pytest.raises(ValueError, match="target_index.*must be strictly greater than origin_index"):
        VaRForecast(
            forecast_id="FC-BAD2",
            origin_index=5,
            target_index=5,
            confidence_level=0.95,
            var_estimate=0.025,
        )

    # Invalid horizon
    with pytest.raises(ValueError, match="horizon must be an integer >= 1"):
        VaRForecast(
            forecast_id="FC-BAD3",
            origin_index=0,
            target_index=1,
            confidence_level=0.95,
            var_estimate=0.025,
            horizon=0,
        )

    # Invalid confidence level
    with pytest.raises(ValueError, match="confidence_level must be in"):
        VaRForecast(
            forecast_id="FC-BAD4",
            origin_index=0,
            target_index=1,
            confidence_level=1.0,
            var_estimate=0.025,
        )

    # Non-finite VaR estimate
    with pytest.raises(ValueError, match="var_estimate must be a finite float"):
        VaRForecast(
            forecast_id="FC-BAD5",
            origin_index=0,
            target_index=1,
            confidence_level=0.95,
            var_estimate=float("nan"),
        )


# ==============================================================================
# 2. Loss Convention and Breach Evaluation Tests
# ==============================================================================

def test_evaluate_var_breaches_loss_convention():
    """Verify loss convention L_{t+1} = -R_{t+1} and strict inequality breach indicator."""
    forecasts = [
        VaRForecast("FC-1", 0, 1, 0.95, 0.020, 1, model_id="model_a"),
        VaRForecast("FC-2", 1, 2, 0.95, 0.025, 1, model_id="model_a"),
        VaRForecast("FC-3", 2, 3, 0.95, 0.030, 1, model_id="model_a"),
        VaRForecast("FC-4", 3, 4, 0.95, 0.020, 1, model_id="model_a"),
    ]

    # Realized returns array:
    # index 0: 0.000 (origin 0)
    # index 1: -0.025 => L = +0.025 > 0.020 => BREACH (1)
    # index 2: -0.025 => L = +0.025 == 0.025 => NO BREACH (0) (strict inequality)
    # index 3: +0.010 => L = -0.010 < 0.030 => NO BREACH (0)
    # index 4: -0.035 => L = +0.035 > 0.020 => BREACH (1)
    realized_returns = np.array([0.000, -0.025, -0.025, 0.010, -0.035])

    eval_results = evaluate_var_breaches(forecasts, realized_returns)

    assert len(eval_results) == 4
    assert [b.is_breach for b in eval_results] == [True, False, False, True]
    assert [b.realized_loss for b in eval_results] == [0.025, 0.025, -0.010, 0.035]
    assert eval_results[0].loss_exceedance == pytest.approx(0.005)
    assert eval_results[1].loss_exceedance == pytest.approx(0.0)


def test_evaluate_var_breaches_bounds_checking():
    """Verify evaluation detects target_index exceeding realized return bounds."""
    forecasts = [
        VaRForecast("FC-1", 0, 5, 0.95, 0.020, 5, model_id="model_a"),
    ]
    # Length of array is only 4 (valid indices 0..3)
    realized_returns = np.array([0.01, -0.02, 0.015, -0.01])

    with pytest.raises(ValueError, match="targets index 5, but realized_returns has length 4"):
        evaluate_var_breaches(forecasts, realized_returns)


# ==============================================================================
# 3. Kupiec Unconditional Coverage POF Test Tests
# ==============================================================================

def test_kupiec_pof_exact_hand_calculation():
    """Verify Kupiec POF calculation against exact analytical formulas."""
    # Scenario: N = 100, alpha = 0.95 => p0 = 0.05.
    # Exactly 5 breaches observed => p_hat = 0.05.
    # LR_POF = 2 * [5 * ln(0.05/0.05) + 95 * ln(0.95/0.95)] = 0.0.
    # Survival p-value = erfc(0) = 1.0.
    breaches_perfect = [1] * 5 + [0] * 95
    res_perfect = calculate_kupiec_pof_test(
        breaches=breaches_perfect,
        confidence_level=0.95,
    )
    assert res_perfect.total_observations == 100
    assert res_perfect.breach_count == 5
    assert math.isclose(res_perfect.observed_rate, 0.05, abs_tol=1e-7)
    assert math.isclose(res_perfect.likelihood_ratio, 0.0, abs_tol=1e-7)
    assert math.isclose(res_perfect.p_value, 1.0, abs_tol=1e-7)
    assert res_perfect.decision == "ACCEPT_NULL"
    assert res_perfect.is_calibrated

    # Scenario: N = 250, alpha = 0.95 => p0 = 0.05, expected = 12.5.
    # Observed x = 30 breaches => p_hat = 0.12.
    # LR_POF = 2 * [30 * ln(0.12/0.05) + 220 * ln(0.88/0.95)]
    expected_lr = 2.0 * (30 * math.log(0.12 / 0.05) + 220 * math.log(0.88 / 0.95))
    breaches_miscalibrated = [1] * 30 + [0] * 220
    res_miscalibrated = calculate_kupiec_pof_test(
        breaches=breaches_miscalibrated,
        confidence_level=0.95,
    )
    assert math.isclose(res_miscalibrated.likelihood_ratio, expected_lr, rel_tol=1e-5)
    assert res_miscalibrated.p_value < 0.001
    assert res_miscalibrated.decision == "REJECT_NULL"
    assert not res_miscalibrated.is_calibrated


def test_kupiec_edge_cases_zero_and_all_breaches():
    """Verify Kupiec handles x = 0 and x = N without log(0) or division-by-zero errors."""
    N = 100
    p0 = 0.05

    # When x = 0: LR = -2 * N * ln(1 - p0)
    expected_lr_zero = -2.0 * N * math.log(1.0 - p0)
    res_zero = calculate_kupiec_pof_test(
        breaches=[0] * N,
        confidence_level=0.95,
    )
    assert math.isclose(res_zero.likelihood_ratio, expected_lr_zero, rel_tol=1e-7)
    assert math.isfinite(res_zero.likelihood_ratio)
    assert math.isfinite(res_zero.p_value)

    # When x = N: LR = -2 * N * ln(p0)
    expected_lr_all = -2.0 * N * math.log(p0)
    res_all = calculate_kupiec_pof_test(
        breaches=[1] * N,
        confidence_level=0.95,
    )
    assert math.isclose(res_all.likelihood_ratio, expected_lr_all, rel_tol=1e-7)
    assert math.isfinite(res_all.likelihood_ratio)
    assert res_all.p_value < 1e-10
    assert res_all.decision == "REJECT_NULL"


def test_kupiec_validation_and_warnings():
    """Verify validation boundaries and sample-size warnings."""
    # Empty breaches
    with pytest.raises(ValueError, match="breaches sequence cannot be empty"):
        calculate_kupiec_pof_test([], 0.95)

    # Invalid confidence level
    with pytest.raises(ValueError, match="confidence_level must be in"):
        calculate_kupiec_pof_test([0, 1], 1.0)

    # Warning for small sample (< 30)
    res_small = calculate_kupiec_pof_test([0] * 19 + [1], 0.95)
    assert any("smaller than recommended minimum (N>=30)" in w for w in res_small.warnings)

    # Warning for modest sample (< 250)
    res_modest = calculate_kupiec_pof_test([0] * 95 + [1] * 5, 0.95)
    assert any("smaller than standard Basel 250-day window" in w for w in res_modest.warnings)


# ==============================================================================
# 4. Christoffersen Independence & Conditional Coverage Tests
# ==============================================================================

def test_christoffersen_independence_and_cc():
    """Verify Christoffersen independence and conditional coverage calculations."""
    indicators = [
        1, 1, 0, 0, 0, 0, 0, 0, 0, 0,
        1, 1, 0, 0, 0, 0, 0, 0, 0, 0,
        1, 1, 0, 0, 0, 0, 0, 0, 0, 0,
        1, 1, 0, 0, 0, 0, 0, 0, 0, 0,
        1, 1, 0, 0, 0, 0, 0, 0, 0, 0,
    ]  # N = 50, 10 breaches, 5 transitions of 1->1
    res = calculate_christoffersen_test(
        breaches=indicators,
        confidence_level=0.90,  # nominal p0 = 0.10
    )
    assert res.contingency_matrix["n11"] == 5
    assert res.lr_conditional_coverage >= res.lr_independence
    assert math.isfinite(res.p_value_independence)
    assert math.isfinite(res.p_value_conditional_coverage)

    # Zero breaches
    res_zero = calculate_christoffersen_test([0] * 50, 0.95)
    assert res_zero.lr_independence == 0.0
    assert res_zero.p_value_independence == 1.0


# ==============================================================================
# 5. EWMA Conditional Variance Causal Recurrence & Future Invariance
# ==============================================================================

def test_ewma_future_observation_invariance():
    """Prove that calculating EWMA conditional variance up to time t is invariant to future data."""
    np.random.seed(42)
    history_20 = np.random.normal(0, 0.01, size=20)
    initial_var = 0.0001

    vars_20 = calculate_ewma_conditional_variances(
        history_20, decay_factor=0.94, initial_variance=initial_var
    )
    assert len(vars_20) == 20

    # Append 10 future returns: scenario A
    future_a = np.array([0.05, -0.04, 0.03, -0.02, 0.01, -0.03, 0.04, -0.05, 0.02, -0.01])
    full_a = np.concatenate([history_20, future_a])
    vars_full_a = calculate_ewma_conditional_variances(
        full_a, decay_factor=0.94, initial_variance=initial_var
    )

    # Append completely different 10 future returns: scenario B
    future_b = np.array([-0.10, -0.15, 0.12, -0.08, 0.09, -0.11, 0.14, -0.12, 0.07, -0.09])
    full_b = np.concatenate([history_20, future_b])
    vars_full_b = calculate_ewma_conditional_variances(
        full_b, decay_factor=0.94, initial_variance=initial_var
    )

    # CRITICAL INVARIANCE PROPERTY:
    # First 20 conditional variances MUST BE BITWISE IDENTICAL between scenario A and B
    np.testing.assert_allclose(vars_full_a[:20], vars_20, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(vars_full_b[:20], vars_20, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(vars_full_a[:20], vars_full_b[:20], rtol=1e-12, atol=1e-12)


def test_ewma_step_by_step_recurrence_hand_calculation():
    """Verify step-by-step recurrence sigma_t^2 = lambda * sigma_{t-1}^2 + (1-lambda) * r_t^2."""
    returns = np.array([0.01, -0.02, 0.015])
    decay = 0.90
    initial_var = 0.0004

    # Hand calculation:
    # var_0 = 0.90 * 0.0004 + 0.10 * (0.01)^2 = 0.00036 + 0.00001 = 0.00037
    # var_1 = 0.90 * 0.00037 + 0.10 * (-0.02)^2 = 0.000333 + 0.00004 = 0.000373
    # var_2 = 0.90 * 0.000373 + 0.10 * (0.015)^2 = 0.0003357 + 0.0000225 = 0.0003582
    expected_vars = np.array([0.00037, 0.000373, 0.0003582])

    calculated_vars = calculate_ewma_conditional_variances(
        returns, decay_factor=decay, initial_variance=initial_var
    )
    np.testing.assert_allclose(calculated_vars, expected_vars, rtol=1e-7, atol=1e-7)


def test_calculate_ewma_volatility_causal_option():
    """Verify calculate_ewma_volatility accepts initial_variance and rejects invalid inputs."""
    r = np.array([0.01, -0.02, 0.015, -0.01])
    vol_causal = calculate_ewma_volatility(r, decay_factor=0.94, initial_variance=0.0002)
    assert vol_causal > 0.0
    assert math.isfinite(vol_causal)

    # Invalid initial_variance
    with pytest.raises(ValueError, match="initial_variance must be strictly positive and finite"):
        calculate_ewma_volatility(r, decay_factor=0.94, initial_variance=-0.001)


# ==============================================================================
# 6. Rolling Walk-Forward Backtest Across Models
# ==============================================================================

def test_backtest_model_rolling_walk_forward():
    """Verify rolling walk-forward backtest produces genuine temporal forecasts without look-ahead."""
    np.random.seed(12345)
    daily_returns = np.random.normal(0.0005, 0.015, size=50)

    # Run rolling backtest for parametric Gaussian model with lookback=30 days
    report_gaussian = backtest_model_rolling(
        model="builtin.parametric_gaussian",
        returns=daily_returns,
        estimation_window=30,
        confidence_level=0.95,
    )

    # Out of 50 observations with estimation_window=30:
    # Origin t ranges from 29 to 48 => 20 forecasts
    assert report_gaussian.evaluation_sample_size == 20
    assert report_gaussian.estimation_window == 30
    assert report_gaussian.confidence_level == 0.95
    assert report_gaussian.model_id == "builtin.parametric_gaussian"

    # Verify temporal ordering: each forecast origin_index strictly precedes target_index
    for eval_item in report_gaussian.breach_evaluations:
        assert eval_item.forecast.origin_index < eval_item.forecast.target_index
        assert eval_item.forecast.target_index == eval_item.forecast.origin_index + 1

    # Verify markdown generation
    md = report_gaussian.to_markdown()
    assert "# FragilityShield — Out-of-Sample VaR Backtest Report" in md
    assert "builtin.parametric_gaussian" in md
    assert "Kupiec Unconditional Coverage Test" in md
    assert "Christoffersen Independence & Conditional Coverage Test" in md

    # Verify JSON roundtrip
    json_str = report_gaussian.to_json()
    roundtrip = BacktestReport.from_json(json_str)
    assert roundtrip.evaluation_sample_size == 20
    assert roundtrip.model_id == "builtin.parametric_gaussian"
    assert roundtrip.manifest["model_id"] == "builtin.parametric_gaussian"


def test_backtest_model_rolling_future_invariance():
    """Prove that modifying day 48 does NOT affect rolling forecasts produced on days 29-45."""
    np.random.seed(999)
    base_returns = np.random.normal(0.0002, 0.012, size=50)

    # Scenario 1: standard returns
    report_1 = backtest_model_rolling(
        model="builtin.historical_simulation",
        returns=base_returns,
        estimation_window=25,
        confidence_level=0.95,
    )

    # Scenario 2: mutate the LAST 3 days (indices 47, 48, 49) heavily
    mutated_returns = base_returns.copy()
    mutated_returns[47:] = np.array([-0.08, 0.09, -0.07])

    report_2 = backtest_model_rolling(
        model="builtin.historical_simulation",
        returns=mutated_returns,
        estimation_window=25,
        confidence_level=0.95,
    )

    # Forecasts produced for origins 24 up to 45 MUST BE EXACTLY IDENTICAL
    # because they only consume returns up to that origin!
    fc_1_early = [b.forecast.var_estimate for b in report_1.breach_evaluations if b.forecast.origin_index <= 45]
    fc_2_early = [b.forecast.var_estimate for b in report_2.breach_evaluations if b.forecast.origin_index <= 45]

    assert len(fc_1_early) > 0
    assert len(fc_1_early) == len(fc_2_early)
    for v1, v2 in zip(fc_1_early, fc_2_early):
        assert math.isclose(v1, v2, abs_tol=1e-12)


# ==============================================================================
# 7. Benchmark Specification evaluation_mode Contract Tests
# ==============================================================================

def test_benchmark_specification_evaluation_mode():
    """Verify BenchmarkSpecification enforces and serializes evaluation_mode."""
    spec = BenchmarkSpecification(
        benchmark_id="bench_eval_test",
        name="Eval Mode Test",
        description="Testing evaluation_mode contract",
        dataset_id="test_ds",
        plugin_ids=("builtin.parametric_gaussian",),
        metrics_to_compare=("var_95",),
        evaluation_mode="in_sample_descriptive",
    )
    assert spec.evaluation_mode == "in_sample_descriptive"
    as_dict = spec.to_dict()
    assert as_dict["evaluation_mode"] == "in_sample_descriptive"

    # Supports out_of_sample_walk_forward
    spec_oos = BenchmarkSpecification(
        benchmark_id="bench_eval_oos",
        name="Eval OOS Test",
        description="Testing out-of-sample mode",
        dataset_id="test_ds",
        plugin_ids=("builtin.parametric_gaussian",),
        metrics_to_compare=("var_95",),
        evaluation_mode="out_of_sample_walk_forward",
    )
    assert spec_oos.evaluation_mode == "out_of_sample_walk_forward"

    # Rejects invalid mode
    with pytest.raises(ValueError, match="evaluation_mode must be 'in_sample_descriptive'"):
        BenchmarkSpecification(
            benchmark_id="bench_invalid_mode",
            name="Invalid Mode Test",
            description="Testing invalid mode",
            dataset_id="test_ds",
            plugin_ids=("builtin.parametric_gaussian",),
            metrics_to_compare=("var_95",),
            evaluation_mode="future_forecast",
        )


def test_benchmark_report_evaluation_mode_markdown_and_json():
    """Verify BenchmarkReport records evaluation_mode in Markdown and JSON roundtrips."""
    spec = BenchmarkSpecification(
        benchmark_id="bench_mode_report",
        name="Report Eval Mode Test",
        description="Testing benchmark report evaluation mode",
        dataset_id="test_ds",
        plugin_ids=("builtin.parametric_gaussian", "builtin.historical_simulation"),
        metrics_to_compare=("var_95",),
        evaluation_mode="in_sample_descriptive",
    )

    dataset = [0.01, -0.015, 0.02, -0.005, 0.012, -0.02, 0.008, -0.011, 0.014, -0.009]

    report = execute_model_benchmark(spec, dataset)
    assert report.evaluation_mode == "in_sample_descriptive"

    md = report.to_markdown()
    assert "**Evaluation Mode:** `in_sample_descriptive`" in md

    # Roundtrip via JSON
    json_str = report.to_json()
    loaded = BenchmarkReport.from_json(json_str)
    assert loaded.evaluation_mode == "in_sample_descriptive"


# ==============================================================================
# 8. Backtest Edge Cases & Branch Coverage
# ==============================================================================

def test_var_forecast_non_finite_es():
    """Verify non-finite expected_shortfall_estimate raises ValueError."""
    with pytest.raises(ValueError, match="expected_shortfall_estimate must be finite"):
        VaRForecast(
            forecast_id="FC-ES-NAN",
            origin_index=0,
            target_index=1,
            confidence_level=0.95,
            var_estimate=0.02,
            expected_shortfall_estimate=float("nan"),
        )


def test_kupiec_significance_level_validation():
    """Verify significance_level bounds validation in Kupiec test."""
    with pytest.raises(ValueError, match="significance_level must be in"):
        calculate_kupiec_pof_test([0, 1], confidence_level=0.95, significance_level=0.0)

    with pytest.raises(ValueError, match="significance_level must be in"):
        calculate_kupiec_pof_test([0, 1], confidence_level=0.95, significance_level=1.0)


def test_christoffersen_empty_and_significance_validation():
    """Verify empty breaches and significance level validation in Christoffersen."""
    with pytest.raises(ValueError, match="Christoffersen test requires at least 2 consecutive observations"):
        calculate_christoffersen_test([], confidence_level=0.95)

    with pytest.raises(ValueError, match="significance_level must be in"):
        calculate_christoffersen_test([0, 1], confidence_level=0.95, significance_level=-0.05)


def test_backtest_model_rolling_plugin_instance_and_step_size():
    """Verify backtest_model_rolling works with plugin instance, step_size > 1, and ES extraction."""
    from fragility_engine.plugins import ParametricGaussianPlugin

    plugin = ParametricGaussianPlugin()
    np.random.seed(777)
    rets = np.random.normal(0.0003, 0.01, size=40)

    report = backtest_model_rolling(
        model=plugin,
        returns=rets,
        estimation_window=20,
        confidence_level=0.95,
        step_size=2,
        es_metric_key="expected_shortfall_95",
        backtest_id="CUSTOM-BT-ID",
    )

    assert report.backtest_id == "CUSTOM-BT-ID"
    assert report.model_id == "builtin.parametric_gaussian"
    # Origin t runs from 19 to 38 step 2: 19, 21, 23, 25, 27, 29, 31, 33, 35, 37 => 10 points
    assert report.evaluation_sample_size == 10
    # Every evaluation forecast should have an ES estimate
    for b in report.breach_evaluations:
        assert b.forecast.expected_shortfall_estimate is not None
        assert b.forecast.expected_shortfall_estimate > 0.0

    md = report.to_markdown()
    assert "CUSTOM-BT-ID" in md
    assert "Diagnostic Warnings" in md or "Methodological Limitations" in md


def test_backtest_model_rolling_validation_errors():
    """Verify backtest_model_rolling input validation."""
    rets = [0.01] * 20

    # Insufficient returns length
    with pytest.raises(ValueError, match="Backtest requires returns length >= estimation_window"):
        backtest_model_rolling("builtin.parametric_gaussian", rets, estimation_window=18)

    # estimation_window < 10
    with pytest.raises(ValueError, match="estimation_window must be >= 10"):
        backtest_model_rolling("builtin.parametric_gaussian", [0.01] * 30, estimation_window=5)

    # step_size < 1
    with pytest.raises(ValueError, match="step_size must be >= 1"):
        backtest_model_rolling("builtin.parametric_gaussian", [0.01] * 30, estimation_window=15, step_size=0)

    # confidence_level invalid
    with pytest.raises(ValueError, match="confidence_level must be in"):
        backtest_model_rolling("builtin.parametric_gaussian", [0.01] * 30, estimation_window=15, confidence_level=1.5)

    # Invalid model type
    with pytest.raises(TypeError, match="model must be str or ModelPlugin"):
        backtest_model_rolling(12345, [0.01] * 30, estimation_window=15)

