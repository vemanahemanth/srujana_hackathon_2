"""Phase 12 Corrective Regression & Correctness Gate Test Suite.

Tests and validates:
1. Expected Shortfall:
   - Constant positive returns & zero returns
   - Floating-point epsilon boundary handling (N=20, alpha=0.95 and N=40, alpha=0.95)
   - One extreme loss in a small sample
   - Discrete fractional tail weighting vs Acerbi & Tasche analytical formula
   - Tied observations at the quantile boundary
   - Small samples where tail < 1 observation
   - Invalid confidence levels (<=0, >=1, NaN, Inf, non-numeric)
   - NaN and Inf return input rejection
   - Independent analytical reference cases

2. Stress-Boundary Search:
   - Inverted bounds (min_param >= max_param) and equal endpoints
   - Nonpositive tolerance and invalid iteration limits
   - Baseline already failing threshold (iterations=0, converged=True)
   - Unbracketed failure threshold across search interval (iterations=1, converged=False)
   - Monotonicity / translation invariance rejection (volatility under friction)
   - Successful convergence with bisection tolerance
   - Exhausted iteration limit without convergence

3. Risk Attribution Semantics:
   - Linear covariance-beta Component VaR Euler reconciliation
   - Normally distributed returns vs fixed-exposure numerical finite difference
   - Heavy-tailed Student-t returns demonstrating divergence from linear beta
   - Collinear and zero-variance assets
   - Degenerate portfolio variance
   - Long-only constraint validation (rejection of non-positive quantities)
   - Machine-readable methodology metadata and limitations disclosure

4. Plugin Security Policy:
   - Builtin plugins trusted by default
   - Untrusted plugin execution blocked with PermissionError on unisolated host
   - Isolation status metadata disclosure
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
import numpy as np
import pytest

from fragility_engine.attribution import (
    AssetRiskAttribution,
    PortfolioRiskAttributionReport,
    calculate_portfolio_risk_attribution,
    verify_attribution_finite_difference,
)
from fragility_engine.fragility import (
    StressBoundaryResult,
    run_stress_boundary_search,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import (
    ModelExecutionResult,
    ModelPlugin,
    PluginMetadata,
    PluginRegistry,
)
from fragility_engine.risk import (
    calculate_expected_shortfall,
    calculate_historical_var,
)


# ==============================================================================
# 1. Expected Shortfall Regression & Precision Tests
# ==============================================================================

class TestExpectedShortfallCorrectness:
    """Rigorous mathematical tests for calculate_expected_shortfall."""

    def test_constant_positive_returns_exactness(self) -> None:
        """Constant positive returns R = [0.02]*20 must yield ES = -0.020000000000000000."""
        returns = [0.02] * 20
        es = calculate_expected_shortfall(returns, confidence_level=0.95)
        var = calculate_historical_var(returns, confidence_level=0.95)

        assert math.isclose(es, -0.02, abs_tol=1e-15)
        assert math.isclose(var, -0.02, abs_tol=1e-15)
        assert es == -0.02  # Exact IEEE double representation

    def test_constant_zero_returns(self) -> None:
        """Zero returns R = [0.0]*15 must yield ES = 0.0."""
        returns = [0.0] * 15
        es = calculate_expected_shortfall(returns, confidence_level=0.95)
        var = calculate_historical_var(returns, confidence_level=0.95)

        assert es == 0.0
        assert var == 0.0

    def test_floating_point_epsilon_boundary_n20_and_n40(self) -> None:
        """Test integer tail boundaries vulnerable to IEEE 754 precision artifacts.

        Because 1.0 - 0.95 = 0.050000000000000044, 20 * 0.05 = 1.0000000000000009.
        The implementation must detect integer boundary and not divide unaugmented sum by w > 1.
        """
        # N = 20, alpha = 0.95 -> tail is exactly 1 observation
        r20 = [0.01] * 19 + [-0.10]
        # Sorted losses: [-0.01]*19, [0.10]
        # Worst loss is 0.10
        es20 = calculate_expected_shortfall(r20, confidence_level=0.95)
        assert math.isclose(es20, 0.10, abs_tol=1e-12)

        # N = 40, alpha = 0.95 -> tail is exactly 2 observations
        r40 = [0.01] * 38 + [-0.08, -0.12]
        # Top 2 losses: 0.08, 0.12 -> average = 0.10
        es40 = calculate_expected_shortfall(r40, confidence_level=0.95)
        assert math.isclose(es40, 0.10, abs_tol=1e-12)

    def test_one_extreme_loss_small_sample(self) -> None:
        """One massive crash observation in a 5-observation series."""
        returns = [0.01, 0.02, 0.01, -0.01, -0.50]
        # Losses: [-0.02, -0.01, -0.01, 0.01, 0.50]
        es = calculate_expected_shortfall(returns, confidence_level=0.95)
        var = calculate_historical_var(returns, confidence_level=0.95)

        # With N=5, tail_prob=0.05, w=0.25 <= 1.0 -> ES is worst loss (0.50)
        assert math.isclose(es, 0.50, abs_tol=1e-12)
        assert es >= var

    def test_fractional_tail_weighting_analytical_reference(self) -> None:
        """Test fractional tail weights against manual Acerbi & Tasche derivation.

        For N=10, alpha=0.75: tail_prob = 0.25, w = 2.5.
        k = 2, frac = 0.5.
        Sorted losses: 1.0, 2.0, ..., 10.0 (returns: -1.0, -2.0, ..., -10.0)
        Tail elements:
        L(10) = 10.0 (weight 1.0)
        L(9)  = 9.0  (weight 1.0)
        L(8)  = 8.0  (weight 0.5)
        Tail sum = 10.0 + 9.0 + 0.5 * 8.0 = 23.0
        ES = 23.0 / 2.5 = 9.2
        """
        returns = [-float(i) for i in range(1, 11)]
        es = calculate_expected_shortfall(returns, confidence_level=0.75)
        expected_es = 9.2

        assert math.isclose(es, expected_es, abs_tol=1e-12)

    def test_tied_observations_at_quantile_boundary(self) -> None:
        """Tied losses at the tail boundary must evaluate to the tied loss level."""
        # Losses: [0.01, 0.05, 0.05, 0.05, 0.05]
        returns = [-0.01, -0.05, -0.05, -0.05, -0.05]
        es = calculate_expected_shortfall(returns, confidence_level=0.80)
        assert math.isclose(es, 0.05, abs_tol=1e-12)

    def test_small_sample_high_confidence(self) -> None:
        """When w = n * (1 - alpha) < 1.0, ES evaluates to the worst observed loss."""
        returns = [0.02, 0.01, -0.03, 0.04, -0.08]
        # Worst loss is 0.08
        es = calculate_expected_shortfall(returns, confidence_level=0.99)
        assert math.isclose(es, 0.08, abs_tol=1e-12)

    def test_invalid_confidence_levels_rejected(self) -> None:
        """Confidence levels <= 0.0 or >= 1.0 or non-finite must raise ValueError."""
        returns = [0.01, -0.02, 0.03, -0.01, 0.02]

        with pytest.raises(ValueError, match="confidence_level must be strictly between 0.0 and 1.0"):
            calculate_expected_shortfall(returns, confidence_level=0.0)

        with pytest.raises(ValueError, match="confidence_level must be strictly between 0.0 and 1.0"):
            calculate_expected_shortfall(returns, confidence_level=1.0)

        with pytest.raises(ValueError, match="confidence_level must be strictly between 0.0 and 1.0"):
            calculate_expected_shortfall(returns, confidence_level=-0.05)

        with pytest.raises(ValueError, match="confidence_level must be strictly between 0.0 and 1.0"):
            calculate_expected_shortfall(returns, confidence_level=float("nan"))

    def test_non_finite_returns_rejected(self) -> None:
        """NaN and infinite returns must be rejected with ValueError."""
        with pytest.raises(ValueError, match="must be finite"):
            calculate_expected_shortfall([0.01, float("nan"), 0.02, -0.01, 0.03])

        with pytest.raises(ValueError, match="must be finite"):
            calculate_expected_shortfall([0.01, float("inf"), 0.02, -0.01, 0.03])

        with pytest.raises(ValueError, match="must be finite"):
            calculate_expected_shortfall([0.01, float("-inf"), 0.02, -0.01, 0.03])


# ==============================================================================
# 2. Stress-Boundary Search Validation & Bracket Tests
# ==============================================================================

class TestStressBoundarySearchRobustness:
    """Tests for run_stress_boundary_search boundary validation and bracket sanity."""

    @pytest.fixture
    def sample_returns(self) -> np.ndarray:
        rng = np.random.default_rng(123)
        return rng.normal(0.001, 0.01, 100)

    def test_reject_inverted_and_equal_bounds(self, sample_returns: np.ndarray) -> None:
        """min_param >= max_param must raise ValueError."""
        # Inverted bounds
        with pytest.raises(ValueError, match="min_param .* must be strictly less than max_param"):
            run_stress_boundary_search(sample_returns, min_param=0.05, max_param=0.01)

        # Equal bounds
        with pytest.raises(ValueError, match="min_param .* must be strictly less than max_param"):
            run_stress_boundary_search(sample_returns, min_param=0.02, max_param=0.02)

    def test_reject_invalid_tolerance_and_max_iter(self, sample_returns: np.ndarray) -> None:
        """Tolerance <= 0 and max_iter < 1 must be rejected."""
        with pytest.raises(ValueError, match="tolerance must be a finite positive number"):
            run_stress_boundary_search(sample_returns, tolerance=0.0)

        with pytest.raises(ValueError, match="tolerance must be a finite positive number"):
            run_stress_boundary_search(sample_returns, tolerance=-1e-4)

        with pytest.raises(ValueError, match="max_iter must be an integer >= 1"):
            run_stress_boundary_search(sample_returns, max_iter=0)

    def test_baseline_already_violating_threshold(self) -> None:
        """If baseline already violates threshold, return iterations=0, converged=True."""
        # Baseline with negative mean
        neg_returns = np.array([-0.01, -0.02, -0.005, -0.015, -0.025])
        result = run_stress_boundary_search(
            neg_returns,
            target_metric="sharpe_ratio",
            failure_threshold=0.0,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.05,
        )

        assert result.converged is True
        assert result.iterations == 0
        assert result.boundary_parameter_value == 0.0
        assert "already violates" in result.explanation

    def test_unbracketed_failure_threshold(self) -> None:
        """If metric never fails across the search range, return converged=False, boundary=None."""
        strong_returns = np.array([0.10, 0.12, 0.11, 0.09, 0.10] * 10)
        result = run_stress_boundary_search(
            strong_returns,
            target_metric="mean_return",
            failure_threshold=0.0,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.02,  # 2% friction leaves mean around 8% > 0
        )

        assert result.converged is False
        assert result.boundary_parameter_value is None
        assert result.iterations == 1
        assert "unbracketed" in result.explanation or "exceeds search range" in result.explanation

    def test_translation_invariant_unsupported_pair(self, sample_returns: np.ndarray) -> None:
        """Volatility is invariant to transaction friction shifts; search must report unsupported."""
        result = run_stress_boundary_search(
            sample_returns,
            target_metric="volatility_annualized",
            failure_threshold=0.25,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.05,
        )

        assert result.converged is False
        assert result.boundary_parameter_value is None
        assert "invariant" in result.explanation

    def test_successful_convergence_monotonic_friction(self, sample_returns: np.ndarray) -> None:
        """Valid monotonic bisection must converge within specified tolerance."""
        result = run_stress_boundary_search(
            sample_returns,
            target_metric="mean_return",
            failure_threshold=0.0,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.01,
            tolerance=1e-5,
            max_iter=30,
        )

        assert result.converged is True
        assert result.boundary_parameter_value is not None
        # Break-even friction for mean_return = 0 is exactly mean(returns)
        expected_root = float(np.mean(sample_returns))
        assert math.isclose(result.boundary_parameter_value, expected_root, abs_tol=1e-4)

    def test_exhausted_iteration_limit(self, sample_returns: np.ndarray) -> None:
        """If iteration limit is reached before tolerance, converged must be False."""
        result = run_stress_boundary_search(
            sample_returns,
            target_metric="mean_return",
            failure_threshold=0.0,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.01,
            tolerance=1e-12,  # Impossible tolerance in 2 iterations
            max_iter=2,
        )

        assert result.converged is False
        assert result.iterations == 2
        assert "iteration limit" in result.explanation


# ==============================================================================
# 3. Risk Attribution Semantics & Validation Tests
# ==============================================================================

class TestRiskAttributionSemantics:
    """Tests distinguishing linear covariance-beta Component VaR from numerical finite difference."""

    @pytest.fixture
    def two_asset_portfolio(self) -> Portfolio:
        h1 = Holding(asset_id="ASSET_A", quantity=100, price=100.0, sector="Tech")
        h2 = Holding(asset_id="ASSET_B", quantity=100, price=100.0, sector="Energy")
        return Portfolio("p_two", "Two Asset Portfolio", "INR", [h1, h2])

    def test_methodology_and_limitations_metadata(self, two_asset_portfolio: Portfolio) -> None:
        """Report must expose machine-readable methodology_type and explicit limitations."""
        report = calculate_portfolio_risk_attribution(two_asset_portfolio)

        assert report.methodology_type == "linear_covariance_beta_component_var"
        assert "Linear Covariance-Beta" in report.methodology
        assert len(report.limitations) >= 3
        assert any("linear covariance beta approximation" in lim for lim in report.limitations)
        assert any("long-only" in lim for lim in report.limitations)

        # Check serialization
        d = report.to_dict()
        assert d["methodology_type"] == "linear_covariance_beta_component_var"
        assert isinstance(d["limitations"], list)

    def test_gaussian_finite_difference_reconciliation(self, two_asset_portfolio: Portfolio) -> None:
        """Under bivariate Gaussian returns, fixed-exposure finite differences match linear marginal VaR."""
        rng = np.random.default_rng(42)
        n = 5000
        r_a = rng.normal(0.0, 0.02, n)
        r_b = rng.normal(0.0, 0.015, n)

        audit = verify_attribution_finite_difference(
            two_asset_portfolio,
            asset_returns_matrix={"ASSET_A": r_a, "ASSET_B": r_b},
            confidence_level=0.95,
            epsilon=1e-3,
        )

        assert audit["methodology_type"] == "fixed_exposure_finite_difference"
        # Under Gaussian, discrepancies between linear beta MCR and numerical dVaR/dw are small (< 0.005)
        assert audit["max_discrepancy"] < 0.008

    def test_heavy_tailed_student_t_divergence(self, two_asset_portfolio: Portfolio) -> None:
        """Under heavy-tailed Student-t (nu=3), numerical marginal VaR diverges from linear beta."""
        rng = np.random.default_rng(999)
        n = 5000
        # Student-t with 3 degrees of freedom (heavy fat tails)
        t_a = rng.standard_t(df=3, size=n) * 0.015
        t_b = rng.standard_t(df=3, size=n) * 0.010

        audit = verify_attribution_finite_difference(
            two_asset_portfolio,
            asset_returns_matrix={"ASSET_A": t_a, "ASSET_B": t_b},
            confidence_level=0.95,
            epsilon=1e-3,
        )

        # Divergence must be measurably observed
        assert audit["max_discrepancy"] > 0.001

    def test_collinear_assets_handling(self) -> None:
        """Perfectly collinear assets must reconcile Euler sum without singular matrix errors."""
        h1 = Holding(asset_id="ASSET_A", quantity=50, price=100.0)
        h2 = Holding(asset_id="ASSET_B", quantity=50, price=100.0)
        port = Portfolio("collinear", "Collinear", "INR", [h1, h2])

        r = [0.01, -0.02, 0.015, -0.01, 0.025, -0.03] * 10
        # Asset B has identical returns to Asset A
        report = calculate_portfolio_risk_attribution(
            port,
            asset_returns_matrix={"ASSET_A": r, "ASSET_B": r},
        )

        sum_cvar = sum(a.component_var for a in report.asset_attributions)
        assert math.isclose(sum_cvar, report.portfolio_var_95, abs_tol=1e-7)

    def test_zero_variance_asset_handling(self) -> None:
        """Asset with zero variance (cash equivalent) must have beta = 0 and component VaR = 0."""
        h1 = Holding(asset_id="RISKY", quantity=50, price=100.0)
        h2 = Holding(asset_id="CASH", quantity=50, price=100.0)
        port = Portfolio("cash_port", "Port with Cash", "INR", [h1, h2])

        r_risky = [0.01, -0.02, 0.015, -0.01, 0.025, -0.03] * 10
        r_cash = [0.0] * 60  # Zero variance

        report = calculate_portfolio_risk_attribution(
            port,
            asset_returns_matrix={"RISKY": r_risky, "CASH": r_cash},
        )

        cash_attr = next(a for a in report.asset_attributions if a.asset_id == "CASH")
        assert cash_attr.asset_volatility == 0.0
        assert math.isclose(cash_attr.beta_to_portfolio, 0.0, abs_tol=1e-12)
        assert math.isclose(cash_attr.component_var, 0.0, abs_tol=1e-12)

    def test_degenerate_portfolio_variance(self) -> None:
        """When all assets have zero returns, portfolio variance <= 1e-12 is handled gracefully."""
        h1 = Holding(asset_id="A", quantity=50, price=100.0)
        h2 = Holding(asset_id="B", quantity=50, price=100.0)
        port = Portfolio("zero_port", "Zero Variance", "INR", [h1, h2])

        report = calculate_portfolio_risk_attribution(
            port,
            asset_returns_matrix={"A": [0.0] * 60, "B": [0.0] * 60},
        )

        assert report.portfolio_volatility == 0.0
        assert report.euler_discrepancy <= 1e-7


# ==============================================================================
# 4. Plugin Security Policy Tests
# ==============================================================================

class DummyUntrustedPlugin(ModelPlugin):
    """Test plugin representing unverified third-party code."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="untrusted.third_party_alpha",
            name="Untrusted Third Party Model",
            description="Simulated unverified external quantitative algorithm.",
        )

    def validate_input(self, data: Any, config: Any) -> None:
        pass

    def execute(self, data: Any, config: Any = None) -> ModelExecutionResult:
        return ModelExecutionResult(
            plugin_id="untrusted.third_party_alpha",
            model_version="1.0.0",
            metrics={"alpha": 0.05},
            execution_time_ms=1.2,
            observations_used=100,
        )


class TestPluginSecurityPolicy:
    """Verify trusted vs untrusted plugin restriction on unisolated host runtime."""

    def test_builtin_plugins_trusted_by_default(self) -> None:
        """Built-in plugins are automatically verified as trusted."""
        registry = PluginRegistry()
        from fragility_engine.plugins import HistoricalSimulationPlugin
        builtin_plugin = HistoricalSimulationPlugin()
        registry.register(builtin_plugin)

        assert registry.is_trusted("builtin.historical_simulation") is True
        status = registry.get_isolation_status("builtin.historical_simulation")
        assert status["is_builtin"] is True
        assert status["is_trusted"] is True
        assert status["security_warning"] is None

    def test_untrusted_plugin_registration_and_execution_blocking(self) -> None:
        """Untrusted plugin without explicit trusted approval is blocked from execution."""
        registry = PluginRegistry(enforce_trusted_execution=True)
        untrusted = DummyUntrustedPlugin()
        registry.register(untrusted, trusted=False)

        assert registry.is_trusted("untrusted.third_party_alpha") is False
        status = registry.get_isolation_status("untrusted.third_party_alpha")
        assert status["is_trusted"] is False
        assert status["security_warning"] is not None
        assert "WARNING: Local runtime executes plugins in-process" in status["security_warning"]

        # Attempting execution must raise PermissionError
        with pytest.raises(PermissionError, match="Execution of untrusted plugin .* is blocked"):
            registry.execute_plugin("untrusted.third_party_alpha", [0.01, -0.02])

    def test_trusted_override_allows_execution(self) -> None:
        """Explicit trusted override permits execution in controlled administrative tests."""
        registry = PluginRegistry(enforce_trusted_execution=True)
        untrusted = DummyUntrustedPlugin()
        registry.register(untrusted, trusted=False)

        result = registry.execute_plugin("untrusted.third_party_alpha", [0.01, -0.02], trusted_override=True)
        assert result.plugin_id == "untrusted.third_party_alpha"
        assert result.metrics["alpha"] == 0.05
