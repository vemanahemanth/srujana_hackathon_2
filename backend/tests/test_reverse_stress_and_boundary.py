"""Tests for Reverse Stress Testing and Break-Even Stress-Boundary Search (Blueprint §5-§8)."""

import pytest
import numpy as np

from fragility_engine.models import Holding, Portfolio
from fragility_engine.scenarios import ReverseStressResult, run_reverse_stress_test
from fragility_engine.fragility import StressBoundaryResult, run_stress_boundary_search


@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Creates a sample multi-asset portfolio with sector distribution."""
    h1 = Holding(asset_id="INFY", quantity=100.0, price=1500.0, sector="Technology")     # 150,000 (30%)
    h2 = Holding(asset_id="TCS", quantity=50.0, price=3000.0, sector="Technology")       # 150,000 (30%)
    h3 = Holding(asset_id="HDFCBANK", quantity=100.0, price=1500.0, sector="Financials") # 150,000 (30%)
    h4 = Holding(asset_id="ITC", quantity=125.0, price=400.0, sector="FMCG")             #  50,000 (10%)
    # Total valuation: 500,000
    return Portfolio(portfolio_id="p_test", name="Diversified NSE Portfolio", currency="INR", holdings=[h1, h2, h3, h4])


def test_reverse_stress_market_uniform(sample_portfolio: Portfolio) -> None:
    # 20% target loss across the whole market
    res = run_reverse_stress_test(sample_portfolio, target_loss_pct=0.20, shock_target="market")
    assert res.feasible is True
    assert pytest.approx(res.required_shock_pct, abs=1e-6) == -0.20
    assert pytest.approx(res.target_loss_amount, abs=1e-2) == 100000.0
    assert pytest.approx(res.realized_loss_amount, abs=1e-2) == 100000.0
    assert pytest.approx(res.stressed_portfolio_value, abs=1e-2) == 400000.0
    assert res.impacted_holdings_count == 4
    # Check holding attribution sums to total realized loss
    assert pytest.approx(sum(res.holding_contributions.values()), abs=1e-2) == 100000.0


def test_reverse_stress_sector_feasible(sample_portfolio: Portfolio) -> None:
    # Technology is 60% of portfolio (300k / 500k).
    # Target loss: 15% (75k).
    # Required shock on Tech: -15% / 60% = -25%
    res = run_reverse_stress_test(
        sample_portfolio,
        target_loss_pct=0.15,
        shock_target="sector",
        target_identifier="Technology",
    )
    assert res.feasible is True
    assert pytest.approx(res.required_shock_pct, abs=1e-6) == -0.25
    assert pytest.approx(res.realized_loss_amount, abs=1e-2) == 75000.0
    assert pytest.approx(res.stressed_portfolio_value, abs=1e-2) == 425000.0
    assert res.impacted_holdings_count == 2
    assert "INFY" in res.holding_contributions
    assert "TCS" in res.holding_contributions


def test_reverse_stress_sector_infeasible_overflow(sample_portfolio: Portfolio) -> None:
    # FMCG is only 10% of portfolio (50k / 500k).
    # Target loss: 20% (100k).
    # Infeasible because 100% loss in FMCG only gives 10% loss.
    res = run_reverse_stress_test(
        sample_portfolio,
        target_loss_pct=0.20,
        shock_target="sector",
        target_identifier="FMCG",
    )
    assert res.feasible is False
    assert res.required_shock_pct < -1.0
    # Realized loss is max possible from this sector (50k)
    assert pytest.approx(res.realized_loss_amount, abs=1e-2) == 50000.0
    assert "infeasible" in res.explanation.lower()


def test_reverse_stress_asset_targeted(sample_portfolio: Portfolio) -> None:
    # INFY is 30% of portfolio (150k / 500k).
    # Target loss: 10% (50k).
    # Required shock on INFY: -10% / 30% = -33.333%
    res = run_reverse_stress_test(
        sample_portfolio,
        target_loss_pct=0.10,
        shock_target="asset",
        target_identifier="INFY",
    )
    assert res.feasible is True
    assert pytest.approx(res.required_shock_pct, abs=1e-4) == -1.0 / 3.0
    assert pytest.approx(res.realized_loss_amount, abs=1e-2) == 50000.0
    assert res.impacted_holdings_count == 1
    assert pytest.approx(res.holding_contributions["INFY"], abs=1e-2) == 50000.0


def test_reverse_stress_validation_errors(sample_portfolio: Portfolio) -> None:
    with pytest.raises(ValueError, match="target_loss_pct must be in"):
        run_reverse_stress_test(sample_portfolio, target_loss_pct=1.5)

    with pytest.raises(ValueError, match="target_loss_pct must be in"):
        run_reverse_stress_test(sample_portfolio, target_loss_pct=0.0)

    with pytest.raises(ValueError, match="target_identifier"):
        run_reverse_stress_test(sample_portfolio, target_loss_pct=0.10, shock_target="sector", target_identifier=None)


def test_stress_boundary_search_friction_breakeven() -> None:
    # Positive daily mean of 0.001 (10 bps daily, approx 25.2% annualized)
    np.random.seed(42)
    daily_returns = np.random.normal(0.001, 0.015, size=500)

    # Search for break-even transaction friction where Sharpe ratio drops to 0.0
    res = run_stress_boundary_search(
        returns=daily_returns,
        target_metric="sharpe_ratio",
        failure_threshold=0.0,
        attack_type="transaction_friction",
        min_param=0.0,
        max_param=0.005,  # up to 50 bps daily
        tolerance=1e-5,
    )

    assert res.converged is True
    assert res.boundary_parameter_value is not None
    # For Sharpe = 0, mean(r - c) = 0 => c = mean(r)
    expected_c = float(np.mean(daily_returns))
    assert pytest.approx(res.boundary_parameter_value, abs=1e-4) == expected_c
    assert pytest.approx(res.final_metric_value, abs=5e-3) == 0.0
    assert "Break-even boundary discovered" in res.explanation


def test_stress_boundary_search_already_failing() -> None:
    # Negative mean returns
    daily_returns = np.array([-0.005, -0.002, -0.008, -0.001, -0.004])

    res = run_stress_boundary_search(
        returns=daily_returns,
        target_metric="sharpe_ratio",
        failure_threshold=0.0,
        attack_type="transaction_friction",
        min_param=0.0,
        max_param=0.01,
    )
    assert res.boundary_parameter_value == 0.0
    assert "already fails acceptance threshold" in res.explanation
