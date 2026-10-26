"""Tests for FragilityEngine Allocation & Comparison Lab."""

import pytest
import numpy as np

from fragility_engine.allocation import (
    create_equal_weighted_portfolio,
    adjust_portfolio_weights,
    calculate_turnover,
    calculate_transaction_cost,
    optimize_minimum_variance,
    compare_allocations,
)
from fragility_engine.models import Holding, Portfolio


@pytest.fixture
def sample_portfolio() -> Portfolio:
    h1 = Holding(asset_id="NSE:HDFCBANK", quantity=100.0, price=1500.0, sector="Banking")
    h2 = Holding(asset_id="NSE:TCS", quantity=50.0, price=3000.0, sector="Information Technology")
    h3 = Holding(asset_id="NSE:RELIANCE", quantity=80.0, price=2500.0, sector="Energy")
    # Values: 150,000 + 150,000 + 200,000 = 500,000
    return Portfolio(
        portfolio_id="test_port",
        name="Test Portfolio",
        currency="INR",
        holdings=(h1, h2, h3),
    )


def test_create_equal_weighted_portfolio(sample_portfolio):
    eq_port = create_equal_weighted_portfolio(sample_portfolio)
    assert eq_port.portfolio_id == "test_port_equal_weight"
    assert len(eq_port.holdings) == 3
    assert pytest.approx(eq_port.total_value, rel=1e-5) == sample_portfolio.total_value

    weights = eq_port.weights
    for w in weights.values():
        assert pytest.approx(w, rel=1e-4) == 1.0 / 3.0


def test_adjust_portfolio_weights(sample_portfolio):
    targets = {
        "NSE:HDFCBANK": 0.50,
        "NSE:TCS": 0.30,
        "NSE:RELIANCE": 0.20,
    }
    adj_port = adjust_portfolio_weights(sample_portfolio, targets)
    assert pytest.approx(adj_port.total_value, rel=1e-4) == sample_portfolio.total_value
    assert pytest.approx(adj_port.weights["NSE:HDFCBANK"], rel=1e-3) == 0.50
    assert pytest.approx(adj_port.weights["NSE:TCS"], rel=1e-3) == 0.30
    assert pytest.approx(adj_port.weights["NSE:RELIANCE"], rel=1e-3) == 0.20


def test_turnover_and_transaction_costs():
    old_w = {"A": 0.5, "B": 0.5}
    new_w = {"A": 0.7, "B": 0.3}
    # Turnover = 0.5 * (|0.7-0.5| + |0.3-0.5|) = 0.5 * (0.2 + 0.2) = 0.20
    turnover = calculate_turnover(old_w, new_w)
    assert pytest.approx(turnover, abs=1e-6) == 0.20

    # Traded volume = 2 * 0.20 * 1,000,000 = 400,000. 10 bps = 400,000 * 0.0010 = 40.0
    cost = calculate_transaction_cost(1_000_000.0, turnover, transaction_cost_bps=10.0)
    assert pytest.approx(cost, abs=1e-4) == 400.0


def test_minimum_variance_optimization():
    # 2 assets with correlation 0.0: asset 1 has sigma=0.10, asset 2 has sigma=0.20
    # Covariance: [[0.01, 0.0], [0.0, 0.04]]
    # Optimal unconstrained minimum variance weights:
    # w1 = (1/0.01) / (1/0.01 + 1/0.04) = 100 / 125 = 0.80
    # w2 = 0.20
    cov = np.array([[0.01, 0.0], [0.0, 0.04]])
    asset_ids = ["A1", "A2"]

    weights, diag = optimize_minimum_variance(cov, asset_ids, min_weight=0.0, max_weight=1.0)
    assert diag.success is True
    assert pytest.approx(weights["A1"], abs=1e-3) == 0.80
    assert pytest.approx(weights["A2"], abs=1e-3) == 0.20
    assert pytest.approx(sum(weights.values()), abs=1e-6) == 1.0


def test_compare_allocations(sample_portfolio):
    targets = {"NSE:HDFCBANK": 0.40, "NSE:TCS": 0.40, "NSE:RELIANCE": 0.20}
    adj_port = adjust_portfolio_weights(sample_portfolio, targets)

    np.random.seed(42)
    fake_returns = np.random.normal(0.0005, 0.01, size=(50, 3))

    rep = compare_allocations(sample_portfolio, adj_port, asset_returns_matrix=fake_returns)
    assert rep.turnover > 0.0
    assert rep.original_hhi > 0.0
    assert rep.adjusted_hhi > 0.0
    assert rep.original_volatility is not None
    assert rep.adjusted_volatility is not None
    d = rep.to_dict()
    assert "turnover" in d
    assert "estimated_transaction_cost_inr" in d
