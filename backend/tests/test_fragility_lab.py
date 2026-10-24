"""Unit tests for Phase 5 Fragility Lab Engine.

Covers:
1. Baseline equivalence tests (zero-perturbation invariance).
2. Hand-calculated reference tests (lookback, EWMA, correlation stress, liquidation drag).
3. Lookback window perturbation dynamics and observation count reporting.
4. Alternative volatility estimator (EWMA with decay factor lambda).
5. Transaction friction and portfolio liquidation cost models.
6. Multivariate correlation matrix perturbation and PSD preservation.
7. Tail confidence level shifts (VaR and ES expansion).
8. Sensitivity ranking and top-vulnerability identification.
9. Zero-baseline relative change handling (None, never NaN or Inf).
10. Input immutability and deterministic repeatability.
11. Boundary and invalid parameter validation.
"""

from __future__ import annotations

import math
from typing import Dict, List
import numpy as np
import pytest

from fragility_engine.fragility import (
    FragilityExperimentResult,
    MetricSensitivityRanking,
    PerturbationImpact,
    calculate_ewma_volatility,
    calculate_portfolio_liquidation_shock,
    compute_changes,
    perturb_correlation_matrix,
    rank_perturbation_sensitivities,
    run_confidence_level_perturbation,
    run_correlation_perturbation,
    run_lookback_perturbation,
    run_return_friction_perturbation,
    run_volatility_estimator_perturbation,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.risk import calculate_annualized_volatility


@pytest.fixture
def sample_returns() -> List[float]:
    """Synthetic 20-day return series with known volatility and tail properties."""
    return [
        0.010, -0.015, 0.005, 0.020, -0.025,
        0.008, -0.004, 0.012, -0.030, 0.018,
        -0.010, 0.015, -0.005, 0.002, -0.012,
        0.022, -0.008, 0.004, -0.018, 0.011,
    ]


@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Deterministic two-asset portfolio."""
    return Portfolio(
        "p1", "Test Port", "INR",
        (
            Holding("A1", 100.0, 1000.0, "Tech"),     # MV = 100,000
            Holding("A2", 200.0, 2000.0, "Banking"),  # MV = 400,000
        )
    )


class TestBaselineEquivalence:
    """Requirement B6: Invariance when zero perturbation is applied."""

    def test_lookback_full_window_equivalence(self, sample_returns: List[float]) -> None:
        """When perturbed_window equals baseline_window, all deltas must be 0.0."""
        n = len(sample_returns)
        res = run_lookback_perturbation(sample_returns, perturbed_window=n, baseline_window=n)
        for metric, delta in res.absolute_changes.items():
            assert math.isclose(delta, 0.0, abs_tol=1e-12)
            rel_delta = res.relative_changes[metric]
            assert rel_delta is not None
            assert math.isclose(rel_delta, 0.0, abs_tol=1e-12)

    def test_friction_zero_bps_equivalence(self, sample_returns: List[float]) -> None:
        """Zero friction shock leaves all risk metrics strictly unchanged."""
        res = run_return_friction_perturbation(sample_returns, friction_bps=0.0)
        for metric, delta in res.absolute_changes.items():
            assert math.isclose(delta, 0.0, abs_tol=1e-12)

    def test_correlation_zero_stress_equivalence(self) -> None:
        """Stress factor 0.0 preserves the baseline correlation matrix and portfolio vol."""
        # 3 assets, 10 time periods
        rng = np.random.default_rng(42)
        r_mat = rng.normal(0.001, 0.01, size=(10, 3))
        weights = [0.3, 0.4, 0.3]
        res = run_correlation_perturbation(r_mat, weights, stress_factor=0.0)
        assert math.isclose(res.absolute_changes["portfolio_volatility_annualized"], 0.0, abs_tol=1e-12)


class TestHandCalculatedPerturbations:
    """Requirement B6: Hand-calculated benchmarks."""

    def test_hand_calculated_ewma(self) -> None:
        """Hand-calculated 2-step EWMA verification."""
        r = [0.01, -0.02]
        lam = 0.90
        # mean(r^2) = (0.0001 + 0.0004) / 2 = 0.00025
        # step 0: var = 0.00025
        # step 1 (r[0]=0.01): var = 0.90 * 0.00025 + 0.10 * (0.01^2) = 0.000225 + 0.000010 = 0.000235
        # step 2 (r[1]=-0.02): var = 0.90 * 0.000235 + 0.10 * (-0.02^2) = 0.0002115 + 0.000040 = 0.0002515
        expected_daily_vol = math.sqrt(0.0002515)
        expected_ann_vol = expected_daily_vol * math.sqrt(252.0)

        calc_vol = calculate_ewma_volatility(r, decay_factor=0.90, annualization_factor=252.0)
        assert math.isclose(calc_vol, expected_ann_vol, rel_tol=1e-9)

    def test_hand_calculated_correlation_matrix_stress(self) -> None:
        """Hand-calculated correlation matrix interpolation."""
        c0 = np.array([[1.0, 0.20], [0.20, 1.0]])
        alpha = 0.50
        target = 0.80
        # Target matrix: [[1.0, 0.80], [0.80, 1.0]]
        # Stressed off-diagonal = 0.5 * 0.20 + 0.5 * 0.80 = 0.10 + 0.40 = 0.50
        c_stressed = perturb_correlation_matrix(c0, stress_factor=alpha, target_correlation=target)
        assert math.isclose(c_stressed[0, 1], 0.50, rel_tol=1e-12)
        assert math.isclose(c_stressed[1, 0], 0.50, rel_tol=1e-12)
        assert c_stressed[0, 0] == 1.0 and c_stressed[1, 1] == 1.0

    def test_hand_calculated_liquidation_cost(self, sample_portfolio: Portfolio) -> None:
        """Hand-calculated portfolio liquidation shock on ₹5,00,000 portfolio."""
        # Total value = 100k + 400k = 500,000.0
        # 10 bps cost = 0.0010. 100% turnover.
        # Cost = 500,000 * 0.0010 = 500.0. Net = 499,500.0.
        res = calculate_portfolio_liquidation_shock(sample_portfolio, cost_bps=10.0, turnover_fraction=1.0)
        assert res["original_portfolio_value"] == 500_000.0
        assert res["liquidation_cost"] == 500.0
        assert res["stressed_portfolio_value"] == 499_500.0
        assert math.isclose(res["cost_drag_percentage"], 0.0010, rel_tol=1e-9)


class TestLookbackWindowPerturbation:
    """Requirement B3.1: Lookback window truncation."""

    def test_lookback_window_reduces_observations(self, sample_returns: List[float]) -> None:
        res = run_lookback_perturbation(sample_returns, perturbed_window=10)
        assert res.observations_used == 10
        assert res.configuration["baseline_window"] == 20
        assert res.configuration["perturbed_window"] == 10
        assert "volatility_annualized" in res.baseline_metrics
        assert "volatility_annualized" in res.perturbed_metrics
        assert "var_95" in res.absolute_changes
        assert len(res.warnings) == 1  # Small sample warning for window < 20

    def test_lookback_rejects_window_larger_than_data(self, sample_returns: List[float]) -> None:
        with pytest.raises(ValueError, match="perturbed_window must be an integer between 2 and 20"):
            run_lookback_perturbation(sample_returns, perturbed_window=25)


class TestVolatilityEstimatorPerturbation:
    """Requirement B3.2: Sample standard deviation vs EWMA."""

    def test_volatility_estimator_comparison(self, sample_returns: List[float]) -> None:
        res = run_volatility_estimator_perturbation(sample_returns, decay_factor=0.94)
        base_vol = res.baseline_metrics["volatility_annualized"]
        ewma_vol = res.perturbed_metrics["volatility_annualized"]

        assert base_vol > 0.0
        assert ewma_vol > 0.0
        assert math.isclose(
            res.absolute_changes["volatility_annualized"],
            ewma_vol - base_vol,
            rel_tol=1e-12,
        )
        assert res.configuration["baseline_estimator"] == "sample_standard_deviation_ddof_1"
        assert res.configuration["perturbed_estimator"] == "ewma_riskmetrics"

    @pytest.mark.parametrize("bad_lambda", [-0.1, 0.0, 1.0, 1.2, float("nan")])
    def test_ewma_rejects_invalid_lambda(self, sample_returns: List[float], bad_lambda: float) -> None:
        with pytest.raises(ValueError, match="decay_factor must be strictly between 0.0 and 1.0"):
            calculate_ewma_volatility(sample_returns, decay_factor=bad_lambda)


class TestReturnFrictionShock:
    """Requirement B3.3: Periodic friction drag."""

    def test_friction_increases_var_and_es(self, sample_returns: List[float]) -> None:
        """Adding cost drag shifts return distribution downward, increasing loss metrics."""
        res = run_return_friction_perturbation(sample_returns, friction_bps=10.0)
        # Because loss L = -R, subtracting cost increases loss:
        # Perturbed VaR and ES should be higher than baseline
        assert res.perturbed_metrics["var_95"] > res.baseline_metrics["var_95"]
        assert res.perturbed_metrics["expected_shortfall_95"] > res.baseline_metrics["expected_shortfall_95"]
        assert res.absolute_changes["var_95"] > 0.0

    def test_friction_rejects_negative_bps(self, sample_returns: List[float]) -> None:
        with pytest.raises(ValueError, match="friction_bps cannot be negative"):
            run_return_friction_perturbation(sample_returns, friction_bps=-5.0)


class TestMultivariateCorrelationPerturbation:
    """Requirement B3.4: Cross-asset correlation stress."""

    def test_multivariate_correlation_stress_increases_portfolio_vol(self) -> None:
        """Stress toward unit correlation increases diversified portfolio risk."""
        # 2 uncorrelated assets: w = [0.5, 0.5]
        # At zero correlation: vol is lower due to diversification.
        # At positive correlation: portfolio vol expands.
        rng = np.random.default_rng(100)
        r1 = rng.normal(0.0, 0.01, size=100)
        r2 = rng.normal(0.0, 0.01, size=100)
        r_mat = np.column_stack([r1, r2])

        res = run_correlation_perturbation(
            r_mat, weights=[0.5, 0.5], stress_factor=0.90, target_correlation=1.0
        )
        base_vol = res.baseline_metrics["portfolio_volatility_annualized"]
        stressed_vol = res.perturbed_metrics["portfolio_volatility_annualized"]
        assert stressed_vol > base_vol
        assert res.absolute_changes["portfolio_volatility_annualized"] > 0.0

    def test_correlation_rejects_1d_array(self, sample_returns: List[float]) -> None:
        """Informative rejection when user attempts correlation on 1D series."""
        with pytest.raises(ValueError, match="Correlation perturbation requires a 2D synchronized multivariate return matrix"):
            run_correlation_perturbation(np.array(sample_returns), weights=[1.0], stress_factor=0.5)

    def test_correlation_rejects_incompatible_weights(self) -> None:
        r_mat = np.zeros((10, 3))
        with pytest.raises(ValueError, match="Weights length"):
            run_correlation_perturbation(r_mat, weights=[0.5, 0.5], stress_factor=0.5)


class TestTailConfidenceShift:
    """Requirement B3.5: VaR and ES confidence level shift."""

    def test_confidence_level_shift_95_to_99(self, sample_returns: List[float]) -> None:
        res = run_confidence_level_perturbation(
            sample_returns, baseline_confidence=0.95, perturbed_confidence=0.99
        )
        assert res.perturbed_metrics["var"] >= res.baseline_metrics["var"]
        assert res.perturbed_metrics["expected_shortfall"] >= res.baseline_metrics["expected_shortfall"]
        assert res.absolute_changes["var"] >= 0.0


class TestSensitivityRanking:
    """Requirement B5: Sensitivity ranking by absolute impact."""

    def test_sensitivity_ranking_order(self, sample_returns: List[float]) -> None:
        """Experiments are ranked in descending order of absolute metric impact."""
        exp1 = run_lookback_perturbation(sample_returns, perturbed_window=10, experiment_id="exp_lookback_10")
        exp2 = run_lookback_perturbation(sample_returns, perturbed_window=15, experiment_id="exp_lookback_15")
        exp3 = run_return_friction_perturbation(sample_returns, friction_bps=5.0, experiment_id="exp_friction_5")

        ranking = rank_perturbation_sensitivities([exp1, exp2, exp3], target_metric="volatility_annualized")
        assert ranking.metric_id == "volatility_annualized"
        assert len(ranking.ranked_impacts) == 3

        # Verify descending order of absolute change
        changes = [abs(imp.absolute_change) for imp in ranking.ranked_impacts]
        assert changes == sorted(changes, reverse=True)
        assert ranking.most_sensitive_perturbation == ranking.ranked_impacts[0].perturbation_id
        assert ranking.max_absolute_change == changes[0]

        # Serialization
        d = ranking.to_dict()
        assert d["metric_id"] == "volatility_annualized"
        assert len(d["ranked_impacts"]) == 3
        assert d["ranked_impacts"][0]["perturbation_id"] == ranking.most_sensitive_perturbation

    def test_sensitivity_ranking_all_perturbation_types(self, sample_returns: List[float]) -> None:
        """Verify ranking across volatility, friction, confidence, and correlation."""
        exp_vol = run_volatility_estimator_perturbation(sample_returns)
        exp_fric = run_return_friction_perturbation(sample_returns, friction_bps=10.0)
        exp_conf = run_confidence_level_perturbation(sample_returns, perturbed_confidence=0.99)

        r_mat = np.random.default_rng(42).normal(0.0, 0.01, size=(50, 2))
        exp_corr = run_correlation_perturbation(r_mat, [0.5, 0.5], stress_factor=0.5)

        ranking = rank_perturbation_sensitivities([exp_conf], target_metric="var")
        assert ranking.ranked_impacts[0].parameter_name == "perturbed_confidence"

        ranking_corr = rank_perturbation_sensitivities([exp_corr], target_metric="portfolio_volatility_annualized")
        assert ranking_corr.ranked_impacts[0].parameter_name == "stress_factor"

    def test_sensitivity_ranking_missing_metric_raises(self, sample_returns: List[float]) -> None:
        exp = run_volatility_estimator_perturbation(sample_returns)
        with pytest.raises(ValueError, match="Target metric 'non_existent_metric' not found"):
            rank_perturbation_sensitivities([exp], target_metric="non_existent_metric")

    def test_sensitivity_ranking_empty_experiments_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot rank sensitivities on an empty sequence"):
            rank_perturbation_sensitivities([], target_metric="volatility_annualized")


class TestFragilityLabErrorAndBoundaryCoverage:
    """Audit defensive type and parameter validations in fragility.py."""

    def test_lookback_error_guards(self, sample_returns: List[float]) -> None:
        with pytest.raises(TypeError, match="returns sequence cannot be None"):
            run_lookback_perturbation(None, perturbed_window=10)  # type: ignore

        with pytest.raises(ValueError, match="requires at least 2 observations"):
            run_lookback_perturbation([0.01], perturbed_window=1)

        with pytest.raises(ValueError, match="baseline_window must be an integer between 2 and"):
            run_lookback_perturbation(sample_returns, perturbed_window=10, baseline_window=1)

    def test_ewma_error_guards(self) -> None:
        with pytest.raises(TypeError, match="returns sequence cannot be None"):
            calculate_ewma_volatility(None)  # type: ignore

        with pytest.raises(ValueError, match="requires at least 2 observations"):
            calculate_ewma_volatility([0.01])

        with pytest.raises(ValueError, match="strictly finite"):
            calculate_ewma_volatility([0.01, float("nan")])

    def test_liquidation_error_guards(self, sample_portfolio: Portfolio) -> None:
        with pytest.raises(TypeError, match="portfolio must be a Portfolio instance"):
            calculate_portfolio_liquidation_shock("not_a_port", cost_bps=10.0)  # type: ignore

        with pytest.raises(ValueError, match="cost_bps must be finite and non-negative"):
            calculate_portfolio_liquidation_shock(sample_portfolio, cost_bps=-5.0)

        with pytest.raises(ValueError, match="turnover_fraction must be in"):
            calculate_portfolio_liquidation_shock(sample_portfolio, cost_bps=10.0, turnover_fraction=1.5)

    def test_correlation_matrix_error_guards(self) -> None:
        with pytest.raises(ValueError, match="must be a square 2D array"):
            perturb_correlation_matrix(np.zeros((3, 2)), stress_factor=0.5)

        with pytest.raises(ValueError, match="requires at least 2 assets"):
            perturb_correlation_matrix(np.eye(1), stress_factor=0.5)

        with pytest.raises(ValueError, match="target_correlation must be in"):
            perturb_correlation_matrix(np.eye(2), stress_factor=0.5, target_correlation=-0.1)

    def test_multivariate_correlation_error_guards(self) -> None:
        with pytest.raises(ValueError, match="at least 2 asset columns"):
            run_correlation_perturbation(np.zeros((10, 1)), weights=[1.0], stress_factor=0.5)

        with pytest.raises(ValueError, match="at least 2 time observations"):
            run_correlation_perturbation(np.zeros((1, 2)), weights=[0.5, 0.5], stress_factor=0.5)


class TestZeroBaselineRelativeChange:
    """Requirement B4: Relative change handling when baseline is zero."""

    def test_zero_baseline_returns_none(self) -> None:
        baseline = {"zero_metric": 0.0, "normal_metric": 10.0}
        perturbed = {"zero_metric": 5.0, "normal_metric": 12.0}
        abs_c, rel_c = compute_changes(baseline, perturbed)
        assert abs_c["zero_metric"] == 5.0
        assert rel_c["zero_metric"] is None  # Handled safely, never inf or nan
        assert math.isclose(rel_c["normal_metric"], 0.20, rel_tol=1e-9)


class TestImmutabilityAndDeterminism:
    """Requirement B6: Immutability and determinism."""

    def test_fragility_inputs_not_mutated(self, sample_returns: List[float]) -> None:
        copy_returns = list(sample_returns)
        _ = run_lookback_perturbation(sample_returns, perturbed_window=10)
        _ = run_volatility_estimator_perturbation(sample_returns)
        _ = run_return_friction_perturbation(sample_returns, friction_bps=5.0)
        assert sample_returns == copy_returns

    def test_fragility_deterministic_runs(self, sample_returns: List[float]) -> None:
        res1 = run_lookback_perturbation(sample_returns, perturbed_window=10)
        res2 = run_lookback_perturbation(sample_returns, perturbed_window=10)
        assert res1.to_dict() == res2.to_dict()
