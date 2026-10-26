"""Phase 15 — Targeted Remediation and Mathematical Edge Case Verification Suite.

This test module implements independent reference oracles, mathematical edge cases,
statistical validation boundary conditions, and interface verification required by Phase 15.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence
import numpy as np
import pytest

from fragility_engine.risk import (
    calculate_historical_var,
    calculate_expected_shortfall,
    calculate_maximum_drawdown,
    calculate_annualized_volatility,
    _validate_returns,
)
from fragility_engine.attribution import (
    calculate_portfolio_risk_attribution,
)
from fragility_engine.backtest import (
    calculate_kupiec_pof_test,
    calculate_christoffersen_test,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import PluginRegistry, ModelPlugin, PluginMetadata, ModelExecutionResult


# ==============================================================================
# 1. Independent Risk Oracles: Tied Values & Quantile Interpolation
# ==============================================================================

class TestRiskEngineOraclesAndTiedValues:
    """Independent mathematical verification for VaR, ES, and boundary conventions."""

    def test_tied_values_at_quantile_boundary(self) -> None:
        """Hand-computable sample with tied values across quantile and tail boundaries.
        
        Returns: R = [-0.04, -0.02, -0.02, -0.02, 0.01, 0.03] (N=6)
        Losses:  L = [-0.03, -0.01, +0.02, +0.02, +0.02, +0.04]
        Sorted Losses:
          L_{(1)} = -0.03
          L_{(2)} = -0.01
          L_{(3)} = +0.02
          L_{(4)} = +0.02
          L_{(5)} = +0.02
          L_{(6)} = +0.04

        For confidence alpha = 0.50 (tail prob = 0.50, tail size w = 3.0):
          The 3 worst losses are L_{(4)}=0.02, L_{(5)}=0.02, L_{(6)}=0.04.
          Expected Shortfall = (0.02 + 0.02 + 0.04) / 3 = 0.08 / 3 = 0.026666666...
          VaR_0.50 (linear interpolation) = 0.5 * (L_{(3)} + L_{(4)}) = 0.02.
        """
        returns = [-0.04, -0.02, -0.02, -0.02, 0.01, 0.03]
        
        var_50 = calculate_historical_var(returns, confidence_level=0.50, method="linear")
        assert math.isclose(var_50, 0.02, abs_tol=1e-10)

        es_50 = calculate_expected_shortfall(returns, confidence_level=0.50)
        expected_es = (0.02 + 0.02 + 0.04) / 3.0
        assert math.isclose(es_50, expected_es, rel_tol=1e-7)
        assert es_50 > var_50

    def test_fractional_tail_weight_calculation(self) -> None:
        """Test fractional tail size w = n * (1 - alpha) where w is non-integer.
        
        Sample: N = 5
        Returns: [-0.05, -0.03, -0.01, 0.02, 0.04]
        Losses:  [-0.04, -0.02, +0.01, +0.03, +0.05]
        Sorted:  L_{(1)}=-0.04, L_{(2)}=-0.02, L_{(3)}=0.01, L_{(4)}=0.03, L_{(5)}=0.05
        
        Let alpha = 0.70. Tail prob = 0.30.
        Tail size w = 5 * 0.30 = 1.5.
        k = floor(1.5) = 1, frac = 0.5.
        Tail includes:
          - k=1 worst loss: L_{(5)} = 0.05 (weight 1.0)
          - frac=0.5 of next worst loss: L_{(4)} = 0.03 (weight 0.5)
        Sum = 1.0 * 0.05 + 0.5 * 0.03 = 0.05 + 0.015 = 0.065.
        ES = Sum / w = 0.065 / 1.5 = 0.043333333333333335.
        """
        returns = [-0.05, -0.03, -0.01, 0.02, 0.04]
        es_70 = calculate_expected_shortfall(returns, confidence_level=0.70)
        expected_es = 0.065 / 1.5
        assert math.isclose(es_70, expected_es, rel_tol=1e-7)

    def test_all_positive_returns_negative_var_and_es(self) -> None:
        """When all returns are positive (strictly profitable), losses are strictly negative.
        
        R = [0.01, 0.02, 0.03, 0.04, 0.05]
        Losses = [-0.05, -0.04, -0.03, -0.02, -0.01]
        VaR and ES must both be negative (indicating guaranteed profit, zero tail loss).
        Coherence ES >= VaR must still hold (e.g. -0.01 >= -0.012).
        """
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        var = calculate_historical_var(returns, confidence_level=0.95)
        es = calculate_expected_shortfall(returns, confidence_level=0.95)

        assert var < 0.0
        assert es < 0.0
        assert es >= var

    def test_all_negative_returns_positive_var_and_es(self) -> None:
        """When all returns are negative, losses are strictly positive."""
        returns = [-0.05, -0.04, -0.03, -0.02, -0.01]
        var = calculate_historical_var(returns, confidence_level=0.95)
        es = calculate_expected_shortfall(returns, confidence_level=0.95)

        assert var > 0.0
        assert es > 0.0
        assert es >= var

    def test_confidence_level_extreme_boundaries(self) -> None:
        """Test confidence levels very close to 1.0 and 0.0."""
        returns = [-0.05, -0.02, 0.01, 0.03]

        # Near 1.0: tail size w < 1.0 -> ES evaluates to maximum observed loss (0.05)
        es_near_one = calculate_expected_shortfall(returns, confidence_level=0.99999)
        assert math.isclose(es_near_one, 0.05, abs_tol=1e-6)

        # Near 0.0: tail covers virtually all observations -> ES evaluates to mean loss
        losses = [-r for r in returns]
        mean_loss = sum(losses) / len(losses)
        es_near_zero = calculate_expected_shortfall(returns, confidence_level=0.00001)
        assert math.isclose(es_near_zero, mean_loss, abs_tol=1e-4)

    def test_invalid_sample_size_rejection(self) -> None:
        """Empty sequence and singleton sequence must raise ValueError."""
        with pytest.raises(ValueError, match="at least 2 return observations"):
            calculate_historical_var([])

        with pytest.raises(ValueError, match="at least 2 return observations"):
            calculate_historical_var([0.05])

        with pytest.raises(TypeError, match="cannot be None"):
            calculate_historical_var(None)  # type: ignore

    def test_lookback_perturbation_strictly_evaluates_recent_window(self) -> None:
        """Lookback window perturbation must strictly select recent observations, not oldest.
        
        Regime shift:
        Oldest 80 periods: calm low volatility (~1% annualized).
        Most recent 20 periods: extreme volatility (~60% annualized).
        Total 100 periods.
        Perturbed window of 20 must capture the high volatility regime (vol > 0.30).
        If an implementation erroneously slices the oldest 20 periods (arr[:20]),
        it would evaluate the calm regime (vol < 0.05), failing this test.
        """
        from fragility_engine.fragility import run_lookback_perturbation
        
        calm_regime = [0.0005, -0.0005] * 40  # 80 days
        volatile_regime = [0.04, -0.04] * 10   # 20 days
        series = calm_regime + volatile_regime

        res = run_lookback_perturbation(series, perturbed_window=20)
        # Perturbed window must capture the recent 20-day volatile regime
        assert res.perturbed_metrics["volatility_annualized"] > 0.30

    def test_boundary_search_unbracketed_failure_returns_not_converged(self) -> None:
        """When the search bracket [min_param, max_param] cannot trigger failure, converged must be False."""
        from fragility_engine.fragility import run_stress_boundary_search
        
        # High positive returns: mean 5% daily
        daily_returns = [0.05, 0.04, 0.06, 0.05, 0.04]
        # Search friction up to only 0.001 (10 bps). Sharpe ratio will stay way above -10.0!
        res = run_stress_boundary_search(
            returns=daily_returns,
            target_metric="sharpe_ratio",
            failure_threshold=-10.0,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.001,
        )
        assert res.converged is False
        assert res.boundary_parameter_value is None
        assert "unbracketed" in res.explanation.lower()


# ==============================================================================
# 2. Independent Attribution Oracles: Three-Asset & Correlated Portfolios
# ==============================================================================

class TestAttributionOraclesThreeAsset:
    """Independent validation of Euler Marginal and Component Risk."""

    def test_three_asset_correlated_independent_oracle(self) -> None:
        """Independently calculate component VaR for a 3-asset portfolio with known covariance.
        
        Weights: w = [0.5, 0.3, 0.2]
        Asset 1: Tech, Asset 2: Finance, Asset 3: Energy
        Independently compute:
          sigma_p^2 = w^T Sigma w
          beta_i = (Sigma w)_i / sigma_p^2
          Check: sum(w_i * beta_i) == 1.0
        """
        w = np.array([0.5, 0.3, 0.2], dtype=np.float64)
        cov = np.array([
            [0.040, 0.010, 0.005],
            [0.010, 0.025, 0.008],
            [0.005, 0.008, 0.030],
        ], dtype=np.float64)

        port_var = float(w @ cov @ w)
        cov_with_p = cov @ w
        expected_betas = cov_with_p / port_var
        assert math.isclose(float(np.sum(w * expected_betas)), 1.0, abs_tol=1e-12)

        # Simulate returns with this covariance matrix
        rng = np.random.default_rng(12345)
        n = 2000
        returns_matrix = rng.multivariate_normal(mean=[0.0, 0.0, 0.0], cov=cov / 252.0, size=n)

        holdings = [
            Holding("T1", quantity=50, price=100.0, sector="Tech"),
            Holding("F1", quantity=30, price=100.0, sector="Finance"),
            Holding("E1", quantity=20, price=100.0, sector="Energy"),
        ]
        portfolio = Portfolio("p3", "Three Asset Portfolio", "USD", holdings)
        data = {
            "T1": returns_matrix[:, 0].tolist(),
            "F1": returns_matrix[:, 1].tolist(),
            "E1": returns_matrix[:, 2].tolist(),
        }

        rep = calculate_portfolio_risk_attribution(portfolio, asset_returns_matrix=data)

        # Verify methodology declaration
        assert rep.methodology_type == "linear_covariance_beta_component_var"
        assert len(rep.limitations) > 0
        assert "linear covariance" in rep.limitations[0] or "approximation" in rep.limitations[0]

        # Verify Euler sum
        beta_sum = sum(a.weight * a.beta_to_portfolio for a in rep.asset_attributions)
        assert math.isclose(beta_sum, 1.0, abs_tol=1e-4)

        component_sum = sum(a.component_var for a in rep.asset_attributions)
        assert math.isclose(component_sum, rep.portfolio_var_95, rel_tol=1e-4)

    def test_attribution_with_zero_volatility_cash_asset(self) -> None:
        """Portfolio with 80% risky stock and 20% cash (zero returns).
        
        Cash beta must be 0.0, Cash component risk must be 0.0.
        All 100% of risk is attributed to the risky stock.
        """
        n = 500
        rng = np.random.default_rng(42)
        r_stock = rng.normal(0.001, 0.02, n)
        r_cash = [0.0] * n

        holdings = [
            Holding("STOCK", quantity=80, price=100.0, sector="Equity"),
            Holding("CASH", quantity=20, price=100.0, sector="Cash"),
        ]
        portfolio = Portfolio("p_cash", "Stock and Cash", "INR", holdings)
        data = {"STOCK": r_stock.tolist(), "CASH": r_cash}

        rep = calculate_portfolio_risk_attribution(portfolio, asset_returns_matrix=data)
        
        cash_attr = next(a for a in rep.asset_attributions if a.asset_id == "CASH")
        stock_attr = next(a for a in rep.asset_attributions if a.asset_id == "STOCK")

        assert math.isclose(cash_attr.beta_to_portfolio, 0.0, abs_tol=1e-9)
        assert math.isclose(cash_attr.component_var, 0.0, abs_tol=1e-9)
        assert math.isclose(cash_attr.percentage_risk_contribution, 0.0, abs_tol=1e-9)
        assert math.isclose(stock_attr.percentage_risk_contribution, 100.0, rel_tol=1e-5)


# ==============================================================================
# 3. Statistical Validation: Boundary Cases & Sample-Size Clarification
# ==============================================================================

class TestStatisticalValidationBoundaries:
    """Rigorous tests for Kupiec and Christoffersen edge cases."""

    def test_kupiec_pof_all_breaches_boundary(self) -> None:
        """All observations are breaches: x = n (e.g. 10 out of 10).
        
        Formula: LR = -2 * n * ln(p0)
        For n = 10, p0 = 0.05:
          LR = -20 * ln(0.05) = -20 * (-2.995732) = 59.9146
        """
        all_breaches = [True] * 10
        res = calculate_kupiec_pof_test(all_breaches, confidence_level=0.95)
        
        expected_lr = -20.0 * math.log(0.05)
        assert math.isclose(res.likelihood_ratio, expected_lr, rel_tol=1e-5)
        assert res.decision == "REJECT_NULL"

    def test_kupiec_pof_sample_size_warning_clarification(self) -> None:
        """Verify that sample size warning is present when N < 250, but does not alter math."""
        small_sample = [False] * 20
        res = calculate_kupiec_pof_test(small_sample, confidence_level=0.95)
        
        # Verify warning is explicitly documented
        assert len(res.warnings) >= 1
        assert any("N=20" in w for w in res.warnings)
        
        # Mathematical likelihood ratio is still calculated correctly
        expected_lr = -40.0 * math.log(0.95)
        assert math.isclose(res.likelihood_ratio, expected_lr, rel_tol=1e-6)

    def test_christoffersen_alternating_breaches(self) -> None:
        """Alternating breaches: [0, 1, 0, 1, 0, 1, ...]
        
        Transitions: 0->1 and 1->0 only. Zero 0->0 and zero 1->1 transitions.
        This exhibits negative autocorrelation (anti-clustering).
        """
        alternating = [False, True] * 20  # 40 observations
        ch = calculate_christoffersen_test(alternating, confidence_level=0.95)

        assert ch.contingency_matrix["n00"] == 0
        assert ch.contingency_matrix["n11"] == 0
        assert ch.contingency_matrix["n01"] > 0
        assert ch.contingency_matrix["n10"] > 0
        # Anti-clustering should also lead to rejection of independence
        assert ch.lr_independence > 5.0
        assert ch.decision_independence == "REJECT_NULL"


# ==============================================================================
# 4. Security Boundary & Sandbox Distinction
# ==============================================================================

class TestSecurityBoundaryPolicyDistinction:
    """Verify that trusted execution policy is verified, but not misidentified as OS sandbox."""

    def test_plugin_isolation_metadata_discloses_lack_of_containerization(self) -> None:
        """get_isolation_status() must explicitly declare in-process model without OS container."""
        from fragility_engine.plugins import get_default_registry
        registry = get_default_registry()
        # Built-in is trusted
        status_builtin = registry.get_isolation_status("builtin.historical_simulation")
        assert status_builtin["host_execution_model"] == "in_process"
        assert status_builtin["os_isolation_active"] is False

    def test_untrusted_plugin_is_blocked_on_host(self) -> None:
        """Untrusted plugin registration is rejected by execute_plugin."""
        class MockUntrusted(ModelPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(plugin_id="test.untrusted", name="Untrusted", description="Test")
            def validate_input(self, d: Any, c: Any = None) -> None: pass
            def execute(self, d: Any, c: Any = None) -> ModelExecutionResult:
                return ModelExecutionResult(
                    plugin_id="test.untrusted",
                    model_version="1.0",
                    metrics={"dummy": 0.0},
                    execution_time_ms=0.0,
                    observations_used=1,
                )

        registry = PluginRegistry(enforce_trusted_execution=True)
        registry.register(MockUntrusted(), trusted=False)

        with pytest.raises(PermissionError, match="blocked on unisolated host runtime"):
            registry.execute_plugin("test.untrusted", [0.01, 0.02])
