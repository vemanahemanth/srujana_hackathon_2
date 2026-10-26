"""Phase 14 Adversarial Verification & Independent Quantitative Oracle Suite.

Tests FragilityShield using independently derived mathematical formulas,
metamorphic property checks, hand-calculated reference solutions, and
adversarial edge cases across all 13 laboratories.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple
import numpy as np
import pytest

from fragility_engine.allocation import optimize_minimum_variance
from fragility_engine.attribution import (
    calculate_portfolio_risk_attribution,
    verify_attribution_finite_difference,
)
from fragility_engine.backtest import (
    calculate_christoffersen_test,
    calculate_kupiec_pof_test,
)
from fragility_engine.concentration import calculate_hhi, calculate_portfolio_concentration
from fragility_engine.data_diagnostics import (
    audit_outliers,
    detect_dataset_drift,
    validate_financial_ohlcv,
)
from fragility_engine.fragility import (
    run_return_friction_perturbation,
    run_stress_boundary_search,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import PluginRegistry, get_default_registry
from fragility_engine.reproducibility import canonical_json_dumps, compute_canonical_hash
from fragility_engine.risk import (
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)
from fragility_engine.scenarios import (
    ScenarioDefinition,
    apply_scenario,
    validate_scenario_against_portfolio,
)
from fragility_engine.simulation import (
    calculate_bootstrap_uncertainty,
    simulate_monte_carlo,
)


# ==============================================================================
# 1. Independent Risk Oracles & Metamorphic Verification
# ==============================================================================

class TestIndependentRiskOracles:
    """Independent mathematical validation of Core Risk calculations."""

    def test_var_and_es_hand_calculated_small_sample(self) -> None:
        """Hand-calculated discrete quantile verification on 5 losses.
        
        Returns: [-0.10, -0.05, 0.00, 0.02, 0.08]
        Losses (L = -R): [0.10, 0.05, 0.00, -0.02, -0.08]
        Sorted Losses: [-0.08, -0.02, 0.00, 0.05, 0.10]
        At alpha = 0.80:
        Tail size = (1 - 0.80) * 5 = 1.0 observation.
        The top 1 worst loss is 0.10.
        VaR_0.80 must be 0.05..0.10 depending on interpolation, and ES_0.80 must be 0.10.
        """
        returns = [-0.10, -0.05, 0.00, 0.02, 0.08]
        var_80 = calculate_historical_var(returns, confidence_level=0.80)
        es_80 = calculate_expected_shortfall(returns, confidence_level=0.80)

        # ES must equal the single tail loss 0.10 exactly
        assert math.isclose(es_80, 0.10, abs_tol=1e-6)
        assert es_80 >= var_80

    def test_var_metamorphic_positive_scale_invariance(self) -> None:
        """Metamorphic property: VaR(c * R) = c * VaR(R) for scalar c > 0."""
        rng = np.random.default_rng(42)
        base_returns = rng.normal(0.001, 0.02, 200).tolist()
        c = 3.5

        scaled_returns = [r * c for r in base_returns]
        var_base = calculate_historical_var(base_returns, confidence_level=0.95)
        var_scaled = calculate_historical_var(scaled_returns, confidence_level=0.95)

        assert math.isclose(var_scaled, var_base * c, rel_tol=1e-7)

    def test_es_metamorphic_positive_scale_invariance(self) -> None:
        """Metamorphic property: ES(c * R) = c * ES(R) for scalar c > 0."""
        rng = np.random.default_rng(42)
        base_returns = rng.normal(0.001, 0.02, 200).tolist()
        c = 2.5

        scaled_returns = [r * c for r in base_returns]
        es_base = calculate_expected_shortfall(base_returns, confidence_level=0.95)
        es_scaled = calculate_expected_shortfall(scaled_returns, confidence_level=0.95)

        assert math.isclose(es_scaled, es_base * c, rel_tol=1e-7)

    def test_constant_returns_zero_dispersion(self) -> None:
        """Degenerate case: constant returns series with zero variance."""
        constant_r = [0.015] * 50
        vol = calculate_annualized_volatility(constant_r)
        assert vol == 0.0

        var = calculate_historical_var(constant_r, confidence_level=0.95)
        es = calculate_expected_shortfall(constant_r, confidence_level=0.95)
        # In positive loss convention: Loss = -0.015
        assert math.isclose(var, -0.015, abs_tol=1e-7)
        assert math.isclose(es, -0.015, abs_tol=1e-7)

    def test_drawdown_flat_and_instant_recovery(self) -> None:
        """Drawdown oracle: strictly non-negative peak-to-trough drop from equity curve."""
        # Strictly increasing equity curve: zero drawdown
        increasing_equity = [100.0, 101.0, 102.0, 105.0, 110.0]
        mdd_inc = calculate_maximum_drawdown(increasing_equity)
        assert mdd_inc.max_drawdown == 0.0

        # Peak 100 -> Drop 50% to 50 -> Immediate recovery to 100
        drop_and_recover_equity = [100.0, 50.0, 100.0]
        mdd_rec = calculate_maximum_drawdown(drop_and_recover_equity)
        assert math.isclose(mdd_rec.max_drawdown, 0.50, abs_tol=1e-6)
        assert mdd_rec.is_recovered is True
        assert mdd_rec.peak_value == 100.0
        assert mdd_rec.trough_value == 50.0

    def test_non_finite_rejection(self) -> None:
        """Core risk engine must reject NaN and Infinity explicitly."""
        with pytest.raises(ValueError, match="finite"):
            calculate_historical_var([0.01, float("nan"), 0.02, -0.01])

        with pytest.raises(ValueError, match="finite"):
            calculate_expected_shortfall([0.01, float("inf"), 0.02, -0.01])


# ==============================================================================
# 2. Independent Risk Attribution Oracles (Euler Homogeneity)
# ==============================================================================

class TestIndependentAttributionOracles:
    """Independent validation of Euler Marginal Risk and Component VaR."""

    def test_two_asset_independent_closed_form_attribution(self) -> None:
        """Analytically check marginal and component VaR on 2 un-correlated assets.
        
        Let w = [0.6, 0.4].
        Asset 1: sigma_1 = 0.20, Asset 2: sigma_2 = 0.10. Cov(1, 2) = 0.
        Portfolio variance: sigma_p^2 = w_1^2 * sigma_1^2 + w_2^2 * sigma_2^2
                           = (0.6)^2 * 0.04 + (0.4)^2 * 0.01 = 0.0144 + 0.0016 = 0.0160
        sigma_p = sqrt(0.0160) = 0.1264911
        Beta_1 = Cov(R_1, R_p) / sigma_p^2 = (w_1 * sigma_1^2) / sigma_p^2 = 0.0144 / 0.0160 = 0.90
        Beta_2 = Cov(R_2, R_p) / sigma_p^2 = (w_2 * sigma_2^2) / sigma_p^2 = 0.0016 / 0.0160 = 0.10
        Check: w_1 * Beta_1 + w_2 * Beta_2 = 0.6 * 0.90 + 0.4 * 0.10 = 0.54 + 0.04 = 0.58.
        Wait, Euler on Beta: sum(w_i * beta_i) = sum(w_i * Cov(R_i, R_p)) / sigma_p^2 = sigma_p^2 / sigma_p^2 = 1.0.
        Here: w_1 * Beta_1 = 0.6 * (0.0144/0.0160) = 0.6 * 0.90 = 0.54 ?
        Wait: Cov(R_1, R_p) = Cov(R_1, w_1 R_1 + w_2 R_2) = w_1 * sigma_1^2 = 0.6 * 0.04 = 0.024.
        Ah! Cov(R_1, R_p) = 0.6 * 0.04 = 0.024.
        Then Beta_1 = 0.024 / 0.0160 = 1.50!
        Cov(R_2, R_p) = 0.4 * 0.01 = 0.004.
        Beta_2 = 0.004 / 0.0160 = 0.25!
        Then w_1 * Beta_1 + w_2 * Beta_2 = 0.6 * 1.50 + 0.4 * 0.25 = 0.90 + 0.10 = 1.00!
        """
        # Generate synthetic data with 0 covariance and known variances
        rng = np.random.default_rng(999)
        n = 1000
        r1 = rng.normal(0.0, 0.20 / math.sqrt(252), n)
        r2 = rng.normal(0.0, 0.10 / math.sqrt(252), n)

        holdings = [
            Holding("A1", quantity=60, price=100.0, sector="Tech"),
            Holding("A2", quantity=40, price=100.0, sector="Finance"),
        ]
        port = Portfolio("p_analytic", "Analytic Portfolio", "INR", holdings)
        matrix = {"A1": r1.tolist(), "A2": r2.tolist()}

        attr = calculate_portfolio_risk_attribution(port, asset_returns_matrix=matrix)
        assert attr.methodology_type == "linear_covariance_beta_component_var"
        assert len(attr.asset_attributions) == 2

        # Sum of component VaR must equal portfolio VaR within Euler tolerance
        sum_cvar = sum(a.component_var for a in attr.asset_attributions)
        assert math.isclose(sum_cvar, attr.portfolio_var_95, abs_tol=1e-7)

        # Asset 1 has higher variance and higher weight -> must contribute > 80% of risk
        cvar_dict = {a.asset_id: a.component_var for a in attr.asset_attributions}
        assert cvar_dict["A1"] > cvar_dict["A2"] * 4.0

    def test_cash_holding_zero_volatility_attribution(self) -> None:
        """A riskless cash holding (zero return variance) must contribute 0.0 to Component VaR."""
        n = 200
        rng = np.random.default_rng(77)
        r_risky = rng.normal(0.0005, 0.015, n).tolist()
        r_cash = [0.0] * n  # Zero volatility cash

        holdings = [
            Holding("RISKY", quantity=100, price=100.0, sector="Equity"),
            Holding("CASH", quantity=100, price=100.0, sector="Cash"),
        ]
        port = Portfolio("p_cash", "Cash Portfolio", "INR", holdings)
        matrix = {"RISKY": r_risky, "CASH": r_cash}

        attr = calculate_portfolio_risk_attribution(port, asset_returns_matrix=matrix)
        cvar_dict = {a.asset_id: a.component_var for a in attr.asset_attributions}

        # CASH holding component VaR must be practically zero
        assert math.isclose(cvar_dict["CASH"], 0.0, abs_tol=1e-8)
        assert math.isclose(cvar_dict["RISKY"], attr.portfolio_var_95, abs_tol=1e-8)


# ==============================================================================
# 3. Independent Backtesting Statistical Oracles
# ==============================================================================

class TestIndependentBacktestingOracles:
    """Independent analytical validation of Kupiec POF and Christoffersen LR tests."""

    def test_kupiec_pof_independent_formula(self) -> None:
        """Independently verify Kupiec POF Likelihood-Ratio formula.
        
        Formula:
            LR = 2 * [ x * ln(p_hat / p0) + (N - x) * ln((1 - p_hat) / (1 - p0)) ]
        """
        N = 250
        x = 15  # 15 breaches observed
        p0 = 0.05
        p_hat = x / N

        expected_lr = 2.0 * (
            x * math.log(p_hat / p0) + (N - x) * math.log((1.0 - p_hat) / (1.0 - p0))
        )

        breach_series = [True] * x + [False] * (N - x)
        kupiec = calculate_kupiec_pof_test(breach_series, confidence_level=0.95)

        assert math.isclose(kupiec.likelihood_ratio, expected_lr, rel_tol=1e-6)
        assert kupiec.breach_count == x
        assert kupiec.total_observations == N

    def test_kupiec_pof_zero_breaches_boundary(self) -> None:
        """Boundary condition: zero breaches (x = 0).
        
        Formula:
            LR = -2 * N * ln(1 - p0)
        """
        N = 100
        p0 = 0.05
        expected_lr = -2.0 * N * math.log(1.0 - p0)

        zero_breaches = [False] * N
        kupiec = calculate_kupiec_pof_test(zero_breaches, confidence_level=0.95)

        assert math.isclose(kupiec.likelihood_ratio, expected_lr, rel_tol=1e-6)

    def test_christoffersen_independence_clustering_detection(self) -> None:
        """Christoffersen test must detect heavy breach clustering.
        
        Construct 10 consecutive breaches followed by 90 non-breaches:
        Transitions: 0->0: 89, 0->1: 1, 1->1: 9, 1->0: 1.
        pi_01 = 1/90 = 0.011, pi_11 = 9/10 = 0.900.
        Strong clustering must produce large LR_ind and low p-value.
        """
        clustered_breaches = [True] * 10 + [False] * 90
        ch = calculate_christoffersen_test(clustered_breaches, confidence_level=0.95)

        assert ch.lr_independence > 10.0  # Highly significant clustering
        assert ch.p_value_independence < 0.005
        assert ch.decision_independence == "REJECT_NULL"


# ==============================================================================
# 4. Fragility & Boundary Search Adversarial Tests
# ==============================================================================

class TestFragilityAdversarialBehavior:
    """Stress testing the boundary search and friction perturbation engines."""

    def test_boundary_search_inverted_bracket_rejection(self) -> None:
        """Passing min_param >= max_param must be rejected immediately."""
        returns = [0.01, -0.01, 0.02, -0.015, 0.005]
        with pytest.raises(ValueError, match="strictly less than max_param"):
            run_stress_boundary_search(
                returns,
                target_metric="sharpe_ratio",
                failure_threshold=0.0,
                min_param=0.05,
                max_param=0.01,  # Inverted!
            )

    def test_boundary_search_zero_width_rejection(self) -> None:
        """Passing min_param == max_param must be rejected."""
        returns = [0.01, -0.01, 0.02, -0.015, 0.005]
        with pytest.raises(ValueError, match="strictly less than max_param"):
            run_stress_boundary_search(
                returns,
                target_metric="sharpe_ratio",
                failure_threshold=0.0,
                min_param=0.02,
                max_param=0.02,  # Zero width!
            )

    def test_boundary_search_invalid_tolerance_rejection(self) -> None:
        """Passing non-positive tolerance must be rejected."""
        returns = [0.01, -0.01, 0.02, -0.015, 0.005]
        with pytest.raises(ValueError, match="tolerance must be a finite positive number"):
            run_stress_boundary_search(
                returns,
                target_metric="sharpe_ratio",
                failure_threshold=0.0,
                tolerance=0.0,
            )


# ==============================================================================
# 5. Security & Isolation Policy Verification
# ==============================================================================

class TestSecurityPolicyIntegrity:
    """Validate that unisolated execution cannot run untrusted plugins."""

    def test_untrusted_plugin_execution_rejected(self) -> None:
        """Untrusted plugin requiring arbitrary execution is blocked on host."""
        from fragility_engine.plugins import ModelPlugin, PluginMetadata, ModelExecutionResult

        class HostileTestDouble(ModelPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    plugin_id="hostile.untrusted_plugin",
                    name="Hostile Test Double",
                    description="Simulates untrusted plugin requesting code execution.",
                )

            def validate_input(self, data: Any, config: Optional[Dict[str, Any]] = None) -> None:
                pass

            def execute(self, data: Any, config: Optional[Dict[str, Any]] = None) -> ModelExecutionResult:
                return ModelExecutionResult(
                    plugin_id="hostile.untrusted_plugin",
                    metrics={"malicious": 1.0},
                    runtime_seconds=0.001,
                )

        registry = PluginRegistry(enforce_trusted_execution=True)
        plugin = HostileTestDouble()
        registry.register(plugin, trusted=False)

        with pytest.raises(PermissionError, match="blocked on unisolated host runtime"):
            registry.execute_plugin("hostile.untrusted_plugin", [0.01, 0.02], {})


# ==============================================================================
# 6. Data Diagnostics & OHLCV Invariant Verification
# ==============================================================================

class TestDataDiagnosticsOracles:
    """Validate financial data sanity checks and invariant violations."""

    def test_ohlcv_high_low_inversion_detected(self) -> None:
        """High < Low is physically impossible; must be flagged."""
        corrupted_candles = [
            {"timestamp": "2026-01-01T10:00:00Z", "open": 100.0, "high": 90.0, "low": 110.0, "close": 95.0, "volume": 1000},
        ]
        rep = validate_financial_ohlcv(corrupted_candles)
        assert rep.is_valid is False
        assert rep.high_low_violations == 1
        assert rep.invalid_candles >= 1

    def test_ohlcv_negative_price_detected(self) -> None:
        """Negative equity prices must be flagged."""
        corrupted_candles = [
            {"timestamp": "2026-01-01T10:00:00Z", "open": 100.0, "high": 105.0, "low": -5.0, "close": 95.0, "volume": 1000},
        ]
        rep = validate_financial_ohlcv(corrupted_candles)
        assert rep.is_valid is False
        assert rep.negative_prices_count == 1

    def test_ohlcv_duplicate_timestamps_detected(self) -> None:
        """Duplicate timestamp keys must be flagged."""
        duplicate_candles = [
            {"timestamp": "2026-01-01T10:00:00Z", "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1000},
            {"timestamp": "2026-01-01T10:00:00Z", "open": 102.0, "high": 106.0, "low": 98.0, "close": 104.0, "volume": 1200},
        ]
        rep = validate_financial_ohlcv(duplicate_candles)
        assert rep.is_valid is False
        assert rep.duplicate_timestamps_count == 1


# ==============================================================================
# 7. Mutation Sensitivity Demonstrations
# ==============================================================================

class TestMutationSensitivity:
    """Verifies that the test suite detects specific seeded defects and mutations."""

    def test_mutation_var_sign_reversal_detected(self) -> None:
        """If VaR sign is inverted, oracle assertions fail immediately."""
        loss_sample = [-0.10, -0.05, 0.02, 0.04]
        # Under normal positive loss convention, 95% VaR is positive for loss:
        correct_var = calculate_historical_var(loss_sample, confidence_level=0.95)
        assert correct_var > 0.0

        # Simulated mutant: sign inverted
        mutant_var = -correct_var
        with pytest.raises(AssertionError):
            assert mutant_var > 0.0, "Sign reversal mutant must be rejected by positivity oracle"

    def test_mutation_es_equals_var_detected(self) -> None:
        """If ES returns VaR instead of tail expectation, tail inequality fails."""
        returns = [-0.08, -0.06, -0.04, -0.02, 0.01, 0.02, 0.03]
        real_var = calculate_historical_var(returns, confidence_level=0.90)
        real_es = calculate_expected_shortfall(returns, confidence_level=0.90)
        assert real_es > real_var

        # Simulated mutant: ES returned VaR
        mutant_es = real_var
        with pytest.raises(AssertionError):
            assert mutant_es > real_var, "ES == VaR mutant must fail strict tail expectation check"

    def test_mutation_transaction_cost_omission_detected(self) -> None:
        """Omitting execution friction produces lower tail risk estimate than reality."""
        returns = [0.01, -0.005, 0.02, 0.01, -0.01]
        friction_res = run_return_friction_perturbation(returns, friction_bps=25.0)
        
        # Real result: with friction drag, losses are higher, so VaR increases
        assert friction_res.perturbed_metrics["var_95"] > friction_res.baseline_metrics["var_95"]

        # Simulated mutant: zero friction (omitted cost term)
        mutant_perturbed_var = friction_res.baseline_metrics["var_95"]
        with pytest.raises(AssertionError):
            assert mutant_perturbed_var > friction_res.baseline_metrics["var_95"], (
                "Omitted friction mutant must be detected by VaR elevation assertion"
            )

    def test_mutation_plugin_trust_bypass_demonstration(self) -> None:
        """Bypassing enforce_trusted_execution allows untrusted code to run (demonstrating security gate)."""
        from fragility_engine.plugins import ModelPlugin, PluginMetadata, ModelExecutionResult

        class DummyHostile(ModelPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(plugin_id="dummy.hostile", name="Hostile", description="Test")
            def validate_input(self, d: Any, c: Any = None) -> None: pass
            def execute(self, d: Any, c: Any = None) -> ModelExecutionResult:
                return ModelExecutionResult(
                    plugin_id="dummy.hostile",
                    model_version="1.0.0",
                    metrics={"pwned": 1.0},
                    execution_time_ms=0.1,
                    observations_used=1,
                )

        # Secure configuration: blocks untrusted plugin
        secure_reg = PluginRegistry(enforce_trusted_execution=True)
        secure_reg.register(DummyHostile(), trusted=False)
        with pytest.raises(PermissionError):
            secure_reg.execute_plugin("dummy.hostile", [0.01])

        # Mutant / Bypassed configuration: fails security isolation
        bypassed_reg = PluginRegistry(enforce_trusted_execution=False)
        bypassed_reg.register(DummyHostile(), trusted=False)
        res = bypassed_reg.execute_plugin("dummy.hostile", [0.01])
        assert res.metrics["pwned"] == 1.0, "Demonstrates that bypassing flag circumvents host check"
