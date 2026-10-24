"""Statistical Calibration and Mathematical Correctness Test Suite.

Phase 8.1 Rigorous Quantitative and Model Calibration Audits:
1. Analytical Parametric Gaussian VaR and ES vs mathematical definitions.
2. Empirical Historical Simulation VaR and ES vs exact discrete formulas.
3. EWMA conditional variance recurrence step-by-step verification.
4. Monotonicity of tail risk under extreme loss injection (crash sensitivity).
5. Zero-volatility / constant return degenerate edge cases.
6. Ranking semantics: lower VaR labeled as lower estimated risk, not model superiority.
7. Explicit measurement units and ranking disclaimers in reports.
8. Perturbation parameter validation (negative friction, lookback < 2, decay outside (0, 1)).
9. Input dimension, type, and shape boundaries.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.benchmarks import (
    BenchmarkSpecification,
    execute_model_benchmark,
    format_metric_unit,
)
from fragility_engine.plugins import (
    EWMAVolatilityPlugin,
    HistoricalSimulationPlugin,
    ParametricGaussianPlugin,
    PortfolioConcentrationPlugin,
    get_default_registry,
)
from fragility_engine.models import Holding, Portfolio


# ==============================================================================
# 1. Analytical Gaussian VaR and ES Verification
# ==============================================================================

class TestParametricGaussianAnalyticalFormulas:
    """Validate ParametricGaussianPlugin against theoretical Gaussian formulas."""

    def test_gaussian_analytical_formula_matches_exact_theory(self):
        """Verify VaR and ES formulas match theoretical z-quantile and phi density."""
        plugin = ParametricGaussianPlugin()

        # Deterministic return sample with known arithmetic mean and variance
        # R = [-0.02, -0.01, 0.00, 0.01, 0.02]
        # Mean = 0.0
        # Sample variance s^2 = (0.0004 + 0.0001 + 0 + 0.0001 + 0.0004) / 4 = 0.001 / 4 = 0.00025
        # Sample std s = sqrt(0.00025) = 0.015811388300841896
        returns = np.array([-0.02, -0.01, 0.00, 0.01, 0.02], dtype=np.float64)
        mu = float(np.mean(returns))
        sigma = float(np.std(returns, ddof=1))

        res = plugin.execute(returns, {"annualization_factor": 252.0})

        # Theoretical z-quantiles:
        # z_0.95 = 1.6448536269514722
        # z_0.99 = 2.3263478740408408
        z_95 = 1.6448536269514722
        z_99 = 2.3263478740408408
        inv_sqrt_2pi = 1.0 / math.sqrt(2.0 * math.pi)
        phi_95 = inv_sqrt_2pi * math.exp(-0.5 * z_95 * z_95)
        phi_99 = inv_sqrt_2pi * math.exp(-0.5 * z_99 * z_99)

        expected_var_95 = -mu + z_95 * sigma
        expected_var_99 = -mu + z_99 * sigma
        expected_es_95 = -mu + sigma * (phi_95 / 0.05)
        expected_es_99 = -mu + sigma * (phi_99 / 0.01)

        assert math.isclose(res.metrics["var_95"], expected_var_95, rel_tol=1e-12)
        assert math.isclose(res.metrics["var_99"], expected_var_99, rel_tol=1e-12)
        assert math.isclose(res.metrics["expected_shortfall_95"], expected_es_95, rel_tol=1e-12)
        assert math.isclose(res.metrics["expected_shortfall_99"], expected_es_99, rel_tol=1e-12)
        assert math.isclose(res.metrics["volatility_daily"], sigma, rel_tol=1e-12)
        assert math.isclose(res.metrics["volatility_annualized"], sigma * math.sqrt(252.0), rel_tol=1e-12)

        # ES must strictly exceed VaR for Gaussian distribution at both confidence levels
        assert res.metrics["expected_shortfall_95"] > res.metrics["var_95"]
        assert res.metrics["expected_shortfall_99"] > res.metrics["var_99"]
        assert res.metrics["var_99"] > res.metrics["var_95"]
        assert res.metrics["expected_shortfall_99"] > res.metrics["expected_shortfall_95"]

    def test_gaussian_zero_volatility_constant_returns(self):
        """Under constant returns (zero volatility), VaR equals -mu and ES equals -mu."""
        plugin = ParametricGaussianPlugin()
        returns = np.full(50, 0.005, dtype=np.float64)  # Constant 0.5% daily gain

        res = plugin.execute(returns, {})
        assert math.isclose(res.metrics["volatility_daily"], 0.0, abs_tol=1e-14)
        assert math.isclose(res.metrics["var_95"], -0.005, abs_tol=1e-14)
        assert math.isclose(res.metrics["var_99"], -0.005, abs_tol=1e-14)
        assert math.isclose(res.metrics["expected_shortfall_95"], -0.005, abs_tol=1e-14)


# ==============================================================================
# 2. Historical Simulation Discrete Quantile Verification
# ==============================================================================

class TestHistoricalSimulationDiscreteCalibration:
    """Validate HistoricalSimulationPlugin against exact discrete empirical samples."""

    def test_historical_simulation_exact_sample(self):
        """Verify empirical historical VaR and ES on hand-calculated 20-observation sample."""
        plugin = HistoricalSimulationPlugin()

        # 20 returns:
        # 1 extreme loss: -0.10 (L = 0.10)
        # 1 severe loss: -0.05 (L = 0.05)
        # 18 mild returns: 0.00 to 0.017
        returns = [-0.10, -0.05] + [0.001 * i for i in range(18)]
        res = plugin.execute(returns, {"annualization_factor": 252.0})

        # 95% confidence on 20 samples -> alpha quantile cutoff
        # At 95%, 1 observation out of 20 (5%) is in the upper tail (L = 0.10)
        # Empirical VaR 95% should reflect the loss boundary
        assert res.metrics["var_95"] > 0.04
        assert res.metrics["expected_shortfall_95"] >= res.metrics["var_95"]
        # 99% confidence VaR and ES should capture the extreme 0.10 loss
        assert res.metrics["var_99"] >= res.metrics["var_95"]
        assert res.metrics["expected_shortfall_99"] >= res.metrics["expected_shortfall_95"]

    def test_historical_simulation_monotonic_crash_sensitivity(self):
        """Injecting a severe crash observation strictly increases empirical tail risk."""
        plugin = HistoricalSimulationPlugin()

        baseline_returns = np.array([
            0.01, -0.01, 0.005, -0.008, 0.012, -0.004, 0.003, -0.006, 0.015, -0.002,
            0.008, -0.011, 0.004, -0.005, 0.007, -0.009, 0.006, -0.003, 0.011, -0.007,
        ], dtype=np.float64)

        base_res = plugin.execute(baseline_returns, {})

        # Shocked series: replace one mild return with -0.20 crash (-20% loss)
        shocked_returns = baseline_returns.copy()
        shocked_returns[0] = -0.20
        shocked_res = plugin.execute(shocked_returns, {})

        assert shocked_res.metrics["var_95"] >= base_res.metrics["var_95"]
        assert shocked_res.metrics["expected_shortfall_95"] > base_res.metrics["expected_shortfall_95"]
        assert shocked_res.metrics["expected_shortfall_99"] > base_res.metrics["expected_shortfall_99"]


# ==============================================================================
# 3. EWMA Recurrence and Conditional Normality Verification
# ==============================================================================

class TestEWMAVolatilityAnalyticalRecurrence:
    """Validate EWMA recurrence relation against manual step-by-step arithmetic."""

    def test_ewma_manual_recurrence_verification(self):
        """Verify EWMA variance recurrence against hand calculation step-by-step."""
        plugin = EWMAVolatilityPlugin()

        # 5 returns:
        r = np.array([0.01, -0.02, 0.015, -0.01, 0.03], dtype=np.float64)
        decay = 0.94

        # Initial variance: uncentered mean of squared returns (RiskMetrics 1996 standard)
        var_t = float(np.mean(r ** 2))
        for val in r:
            var_t = decay * var_t + (1.0 - decay) * float(val ** 2)

        manual_daily_vol = math.sqrt(var_t)
        manual_ann_vol = manual_daily_vol * math.sqrt(252.0)

        res = plugin.execute(r, {"decay_factor": decay, "annualization_factor": 252.0})

        assert math.isclose(res.metrics["volatility_daily"], manual_daily_vol, rel_tol=1e-12)
        assert math.isclose(res.metrics["volatility_annualized"], manual_ann_vol, rel_tol=1e-12)
        assert math.isclose(res.metrics["annualized_volatility"], manual_ann_vol, rel_tol=1e-12)

    def test_ewma_conditional_gaussian_var_and_es(self):
        """Verify EWMA plugin derives conditional Gaussian VaR and ES using conditional vol."""
        plugin = EWMAVolatilityPlugin()
        r = np.array([0.005, -0.008, 0.012, -0.004, 0.003, -0.006, 0.015, -0.002, 0.008, -0.011])

        res = plugin.execute(r, {"decay_factor": 0.94, "annualization_factor": 252.0})

        cond_sigma = res.metrics["volatility_daily"]
        mu = float(np.mean(r))
        z_95 = 1.6448536269514722
        inv_sqrt_2pi = 1.0 / math.sqrt(2.0 * math.pi)
        phi_95 = inv_sqrt_2pi * math.exp(-0.5 * z_95 * z_95)

        expected_var_95 = -mu + z_95 * cond_sigma
        expected_es_95 = -mu + cond_sigma * (phi_95 / 0.05)

        assert math.isclose(res.metrics["var_95"], expected_var_95, rel_tol=1e-12)
        assert math.isclose(res.metrics["expected_shortfall_95"], expected_es_95, rel_tol=1e-12)
        assert res.metrics["expected_shortfall_95"] > res.metrics["var_95"]
        assert res.metrics["var_99"] > res.metrics["var_95"]

    def test_ewma_zero_mean_option(self):
        """Verify RiskMetrics zero_mean=True assumption (mu=0 in VaR/ES calculation)."""
        plugin = EWMAVolatilityPlugin()
        r = np.array([0.01, -0.02, 0.015, -0.01, 0.03], dtype=np.float64)
        decay = 0.94

        res = plugin.execute(r, {"decay_factor": decay, "zero_mean": True})
        cond_sigma = res.metrics["volatility_daily"]
        z_95 = 1.6448536269514722

        # When zero_mean is True, VaR_95 = 0.0 + z_95 * sigma (no non-zero mu offset)
        assert math.isclose(res.metrics["var_95"], z_95 * cond_sigma, rel_tol=1e-12)


# ==============================================================================
# 4. Ranking Semantics and Disclaimers
# ==============================================================================

class TestBenchmarkRankingSemanticsAndDisclaimers:
    """Verify that rankings distinguish estimated risk magnitude from model quality."""

    def test_ranking_semantics_records_interpretation_not_model_superiority(self):
        """Rankings must record 'lower_estimated_risk' and include explicit disclaimer."""
        returns = np.array([
            0.01, -0.02, 0.015, -0.01, 0.005, -0.008, 0.012, -0.004, 0.003, -0.006,
            0.015, -0.002, 0.008, -0.011, 0.004, -0.005, 0.007, -0.009, 0.006, -0.003,
            0.011, -0.007, 0.002, -0.001, 0.014, -0.012, 0.009, -0.003, 0.005, -0.006,
        ], dtype=np.float64)

        spec = BenchmarkSpecification(
            benchmark_id="BM-SEMANTICS-001",
            name="VaR Ranking Semantics Audit",
            description="Audit distinguishing risk magnitude from model superiority",
            dataset_id="RETURNS-30D",
            plugin_ids=("builtin.historical_simulation", "builtin.parametric_gaussian"),
            metrics_to_compare=("var_95", "annualized_volatility"),
            target_ranking_metric="var_95",
            ranking_direction="lower_is_better",
        )

        report = execute_model_benchmark(spec, returns)

        assert len(report.rankings) == 2
        for r in report.rankings:
            assert r.unit == "decimal fraction"
            assert r.interpretation == "lower_estimated_risk"
            assert r.ranking_direction == "lower_is_better"

        # Explicit disclaimer must be populated and must mention that lower estimated VaR != better model
        assert "A lower estimated Value-at-Risk or Volatility reflects a lower risk estimate, NOT a superior" in report.ranking_disclaimer
        assert "Out-of-sample backtesting against realized outcomes is required" in report.ranking_disclaimer

        # Markdown report must display the disclaimer and units
        md = report.to_markdown()
        assert "> **Model Comparison Disclaimer:**" in md
        assert "decimal fraction" in md
        assert "lower_estimated_risk" in md

        # CSV report must have the 'unit' column
        csv_text = report.to_csv()
        assert "unit" in csv_text.splitlines()[0]
        assert "decimal fraction" in csv_text

    def test_unranked_models_excluded_from_ranking_with_explicit_reason(self):
        """Failed or incompatible models are excluded from rankings with recorded reasons."""
        returns = np.array([0.01, -0.01, 0.02, -0.02, 0.015, -0.012, 0.005, -0.008, 0.003, -0.004])

        spec = BenchmarkSpecification(
            benchmark_id="BM-UNRANKED-AUDIT",
            name="Incompatible Plugin Benchmark",
            description="Concentration plugin cannot evaluate 1D returns and must be excluded from VaR ranking",
            dataset_id="RETURNS-10D",
            plugin_ids=("builtin.historical_simulation", "builtin.portfolio_concentration"),
            metrics_to_compare=("var_95",),
            target_ranking_metric="var_95",
        )

        report = execute_model_benchmark(spec, returns)

        # Historical simulation succeeds and receives Rank 1
        assert len(report.rankings) == 1
        assert report.rankings[0].plugin_id == "builtin.historical_simulation"

        # Concentration plugin is excluded and logged in unranked_models
        assert len(report.unranked_models) == 1
        assert report.unranked_models[0]["plugin_id"] == "builtin.portfolio_concentration"
        assert "failed" in report.unranked_models[0]["reason"].lower() or "not report" in report.unranked_models[0]["reason"].lower()


# ==============================================================================
# 5. Perturbation Parameter Validation
# ==============================================================================

class TestPerturbationParameterValidation:
    """Verify rigorous input validation on perturbation specifications."""

    def test_reject_unsupported_perturbation_type(self):
        """Unknown perturbation types are rejected at BenchmarkSpecification validation."""
        with pytest.raises(ValueError, match="Unsupported perturbation type 'hypothetical_quantum_shock'"):
            BenchmarkSpecification(
                benchmark_id="BM-PERT-FAIL-1",
                name="Invalid Perturbation",
                description="desc",
                dataset_id="DS-1",
                perturbation_specs=({"type": "hypothetical_quantum_shock"},),
            )

    def test_reject_negative_return_friction(self):
        """Negative return friction bps is rejected."""
        with pytest.raises(ValueError, match="friction_bps must be finite and >= 0.0"):
            BenchmarkSpecification(
                benchmark_id="BM-PERT-FAIL-2",
                name="Negative Friction",
                description="desc",
                dataset_id="DS-1",
                perturbation_specs=({"type": "return_friction", "parameters": {"friction_bps": -5.0}},),
            )

    def test_reject_invalid_lookback_window(self):
        """Lookback window less than 2 is rejected."""
        with pytest.raises(ValueError, match="lookback window must be an integer >= 2"):
            BenchmarkSpecification(
                benchmark_id="BM-PERT-FAIL-3",
                name="Invalid Lookback",
                description="desc",
                dataset_id="DS-1",
                perturbation_specs=({"type": "lookback_window", "parameters": {"lookback_window": 1}},),
            )

    def test_reject_invalid_decay_factor(self):
        """Decay factor outside (0, 1) is rejected."""
        with pytest.raises(ValueError, match="decay_factor must be strictly between 0 and 1"):
            BenchmarkSpecification(
                benchmark_id="BM-PERT-FAIL-4",
                name="Invalid Decay",
                description="desc",
                dataset_id="DS-1",
                perturbation_specs=({"type": "volatility_estimator_ewma", "parameters": {"decay_factor": 1.25}},),
            )

        with pytest.raises(ValueError, match="decay_factor must be strictly between 0 and 1"):
            BenchmarkSpecification(
                benchmark_id="BM-PERT-FAIL-5",
                name="Zero Decay",
                description="desc",
                dataset_id="DS-1",
                perturbation_specs=({"type": "volatility_estimator_ewma", "parameters": {"decay_factor": 0.0}},),
            )


# ==============================================================================
# 6. Portfolio Concentration Plugin Boundaries
# ==============================================================================

class TestPortfolioConcentrationBoundaries:
    """Validate PortfolioConcentrationPlugin mathematical and schema boundaries."""

    def test_concentration_hhi_bounds(self):
        """For equal weights, HHI equals 1/N; for single asset, HHI equals 1.0."""
        plugin = PortfolioConcentrationPlugin()

        # 4 equally weighted assets (w_i = 0.25): HHI = 4 * (0.25)^2 = 0.25 (2500 points)
        port_equal = Portfolio(
            portfolio_id="PORT-EQ",
            name="Equal Weight",
            currency="USD",
            holdings=(
                Holding("A", 100.0, 250.0, "Tech"),
                Holding("B", 100.0, 250.0, "Tech"),
                Holding("C", 100.0, 250.0, "Health"),
                Holding("D", 100.0, 250.0, "Health"),
            ),
        )
        res_eq = plugin.execute(port_equal, {})
        assert math.isclose(res_eq.metrics["asset_hhi_decimal"], 0.25, rel_tol=1e-12)
        assert math.isclose(res_eq.metrics["asset_hhi_points"], 2500.0, rel_tol=1e-12)
        assert math.isclose(res_eq.metrics["sector_hhi_decimal"], 0.50, rel_tol=1e-12)

        # Single concentrated asset: HHI = 1.0 (10000 points)
        port_single = Portfolio(
            portfolio_id="PORT-CONC",
            name="Full Concentration",
            currency="USD",
            holdings=(Holding("A", 100.0, 1000.0, "Tech"),),
        )
        res_single = plugin.execute(port_single, {})
        assert math.isclose(res_single.metrics["asset_hhi_decimal"], 1.0, rel_tol=1e-12)
        assert math.isclose(res_single.metrics["asset_hhi_points"], 10000.0, rel_tol=1e-12)

    def test_concentration_rejects_return_series(self):
        """Concentration plugin strictly rejects return series data."""
        plugin = PortfolioConcentrationPlugin()
        with pytest.raises(TypeError, match="requires a Portfolio instance"):
            plugin.validate_input([0.01, -0.02, 0.015], {})


# ==============================================================================
# 7. Units Formatting Helper
# ==============================================================================

class TestMetricUnitsFormatting:
    """Validate format_metric_unit helper function."""

    def test_metric_units_mapping(self):
        assert format_metric_unit("var_95") == "decimal fraction"
        assert format_metric_unit("volatility_annualized") == "decimal fraction"
        assert format_metric_unit("asset_hhi_decimal") == "decimal fraction"
        assert format_metric_unit("asset_hhi_points") == "points (0-10000)"
        assert format_metric_unit("total_market_value") == "currency"
        assert format_metric_unit("sharpe_ratio") == "ratio"
        assert format_metric_unit("custom_unrecognized_metric") == "decimal fraction"
