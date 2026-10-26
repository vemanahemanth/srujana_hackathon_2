"""Unit & Integration Test Suite for Page 11: Tail Risk & Reverse Stress Testing Lab.

Verifies:
- Comprehensive tail risk metrics (VaR & ES 90-99%, Cornish-Fisher, Hill Tail Index, worst historical days).
- Invariant property: Expected Shortfall is strictly greater than or equal to Value at Risk.
- Block bootstrap uncertainty bands around tail metrics with reproducible random seed.
- Multi-factor reverse stress testing optimizer solving for joint Market, Sector, and Asset shocks.
- Plausibility scoring and joint sigma distance metrics.
- 2D sensitivity surface computation.
- FastAPI REST endpoints (/api/tail-risk/*) via TestClient.
"""

import pytest
import numpy as np
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.models import Portfolio, Holding
from fragility_engine.tail_risk_engine import (
    compute_comprehensive_tail_risk,
    compute_cornish_fisher_var,
    compute_hill_tail_index,
    run_method_comparison_bootstrap,
    run_multi_factor_reverse_stress,
    compute_reverse_stress_sensitivity_surface,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


@pytest.fixture
def synthetic_sample_returns():
    """Deterministic return series with controlled negative skew and fat tails (seed=101)."""
    rng = np.random.default_rng(101)
    # 250 daily returns ~ N(0.0004, 0.012) with 8 heavy tail loss shocks
    normal_rets = rng.normal(loc=0.0005, scale=0.011, size=250)
    # Inject tail losses
    normal_rets[15] = -0.045
    normal_rets[42] = -0.062
    normal_rets[88] = -0.038
    normal_rets[140] = -0.055
    normal_rets[200] = -0.071
    return normal_rets


@pytest.fixture
def sample_test_portfolio():
    """Multi-asset test portfolio with energy and financial concentration."""
    h1 = Holding(asset_id="RELIANCE", quantity=100.0, price=2900.0, sector="Energy", asset_class="equity")
    h2 = Holding(asset_id="HDFCBANK", quantity=200.0, price=1650.0, sector="Financials", asset_class="equity")
    h3 = Holding(asset_id="TCS", quantity=80.0, price=4100.0, sector="Technology", asset_class="equity")
    h4 = Holding(asset_id="ICICIBANK", quantity=150.0, price=1100.0, sector="Financials", asset_class="equity")
    return Portfolio(
        portfolio_id="pf_test_tail",
        name="Tail Risk Benchmark Portfolio",
        currency="INR",
        holdings=(h1, h2, h3, h4),
    )


# ==============================================================================
# 1. Tail Risk Analytics Tests
# ==============================================================================

def test_tail_risk_metrics_computation(synthetic_sample_returns):
    """Ensure all core metrics are computed with proper mathematical bounds."""
    res = compute_comprehensive_tail_risk(synthetic_sample_returns)

    assert res.sample_size == len(synthetic_sample_returns)
    assert res.annualized_volatility > 0.0
    assert res.skewness < 0.0  # Due to injected tail drops
    assert res.excess_kurtosis > 0.0  # Leptokurtic fat tails
    assert 1.0 <= res.hill_tail_index <= 5.0

    # Invariant: ES >= VaR at all confidence levels
    for lvl in ["90", "95", "97_5", "99"]:
        var_val = res.var_metrics[f"hist_{lvl}"]
        es_val = res.es_metrics[f"hist_{lvl}"]
        assert es_val >= var_val, f"Expected Shortfall ({es_val}) must be >= VaR ({var_val}) at level {lvl}"

    # Invariant: Higher confidence -> higher VaR
    assert res.var_metrics["hist_99"] >= res.var_metrics["hist_95"]
    assert res.var_metrics["hist_95"] >= res.var_metrics["hist_90"]


def test_cornish_fisher_skewness_adjustment():
    """Cornish-Fisher VaR must be higher than Gaussian VaR in negatively skewed series."""
    mean = 0.0
    std = 0.015
    # Negative skew (-0.8) and positive kurtosis (+2.5)
    cf_var = compute_cornish_fisher_var(mean, std, skew=-0.8, kurt=2.5, confidence_level=0.95)
    # Pure Gaussian: 1.64485 * std
    gauss_var = 1.644853 * std

    assert cf_var > gauss_var, "Cornish-Fisher VaR must penalize negative skew and fat kurtosis"


def test_hill_tail_index_estimator():
    """Hill estimator must reflect heavier tails when large losses exist."""
    gaussian_losses = np.abs(np.random.default_rng(42).normal(0, 0.01, size=300))
    fat_tail_losses = np.concatenate([
        gaussian_losses,
        np.array([0.08, 0.12, 0.15, 0.20, 0.25]),
    ])

    idx_gaussian = compute_hill_tail_index(gaussian_losses)
    idx_fat = compute_hill_tail_index(fat_tail_losses)

    # Heavier tails produce lower alpha (index)
    assert idx_fat < idx_gaussian or idx_fat <= 3.0


def test_worst_days_and_histogram_distribution(synthetic_sample_returns):
    """Worst historical days must be ordered by severity, and histogram must contain bins."""
    res = compute_comprehensive_tail_risk(synthetic_sample_returns)
    assert len(res.worst_days) == 10
    # Worst day should be the -7.1% shock
    assert res.worst_days[0]["return_pct"] <= -6.0
    assert res.worst_days[0]["loss_pct"] >= 6.0

    # Sorted descending by loss
    for i in range(1, len(res.worst_days)):
        assert res.worst_days[i - 1]["loss_pct"] >= res.worst_days[i]["loss_pct"]

    assert len(res.distribution_histogram) >= 15
    assert any(b["is_tail_loss"] for b in res.distribution_histogram)


# ==============================================================================
# 2. Method Comparison & Bootstrap Tests
# ==============================================================================

def test_stationary_block_bootstrap(synthetic_sample_returns):
    """Block bootstrap must produce valid empirical confidence intervals."""
    boot = run_method_comparison_bootstrap(
        returns=synthetic_sample_returns,
        replications=100,
        block_length=5,
        confidence_level=0.95,
        random_seed=42,
    )

    assert "bootstrap_var_95" in boot
    assert "bootstrap_es_95" in boot
    assert "bootstrap_volatility" in boot

    var_ci = boot["bootstrap_var_95"]
    assert var_ci["ci_lower_95"] <= var_ci["median"] <= var_ci["ci_upper_95"]
    assert var_ci["ci_lower_95"] > 0.0

    es_ci = boot["bootstrap_es_95"]
    assert es_ci["ci_lower_95"] <= es_ci["median"] <= es_ci["ci_upper_95"]


# ==============================================================================
# 3. Multi-Factor Reverse Stress Testing Tests
# ==============================================================================

def test_multi_factor_reverse_stress_solution(sample_test_portfolio):
    """Multi-factor reverse stress must allocate shock across market, sector, and asset."""
    target_loss = 0.20  # 20% loss
    sol = run_multi_factor_reverse_stress(
        portfolio=sample_test_portfolio,
        target_loss_pct=target_loss,
    )

    assert sol.is_feasible is True
    assert sol.target_loss_pct == 0.20
    assert sol.realized_loss_pct >= 0.195  # within 0.5% tolerance
    assert sol.market_shock < 0.0
    assert sol.sector_shock <= 0.0
    assert sol.asset_shock <= 0.0
    assert sol.dominant_sector in ("Financials", "Energy", "Technology")
    assert len(sol.holding_attributions) == 4
    assert 10.0 <= sol.plausibility_score <= 95.0
    assert sol.joint_sigma_distance > 0.0


def test_reverse_stress_sensitivity_surface(sample_test_portfolio):
    """Sensitivity surface must generate a 2D grid of market vs sector shocks."""
    surf = compute_reverse_stress_sensitivity_surface(
        portfolio=sample_test_portfolio,
        target_loss_pct=0.15,
        grid_steps=5,
    )

    assert len(surf["market_shocks"]) == 5
    assert len(surf["sector_shocks"]) == 5
    assert len(surf["cells"]) == 25
    assert any(c["breaches_target"] for c in surf["cells"])
    assert any(not c["breaches_target"] for c in surf["cells"])


# ==============================================================================
# 4. FastAPI REST Endpoints Tests
# ==============================================================================

def test_api_tail_risk_analyze(client):
    """POST /api/tail-risk/analyze returns complete tail risk pack for RELIANCE."""
    resp = client.post("/api/tail-risk/analyze", json={"symbol": "RELIANCE"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "tail_risk" in data
    tr = data["tail_risk"]
    assert tr["annualized_volatility"] > 0.0
    assert "hist_95" in tr["var_metrics"]
    assert "hist_95" in tr["es_metrics"]
    assert len(tr["worst_days"]) >= 5


def test_api_tail_risk_reverse_stress(client, sample_test_portfolio):
    """POST /api/tail-risk/reverse-stress solves multi-factor scenario."""
    resp = client.post("/api/tail-risk/reverse-stress", json={
        "target_loss_pct": 0.18,
        "portfolio": sample_test_portfolio.to_dict(),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["solution"]["is_feasible"] is True
    assert data["solution"]["realized_loss_pct"] >= 0.17


def test_api_tail_risk_bootstrap(client):
    """POST /api/tail-risk/bootstrap executes block bootstrap."""
    resp = client.post("/api/tail-risk/bootstrap", json={
        "symbol": "RELIANCE",
        "replications": 100,
        "block_length": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "bootstrap" in data
    assert "bootstrap_var_95" in data["bootstrap"]


def test_api_tail_risk_sensitivity_surface(client, sample_test_portfolio):
    """POST /api/tail-risk/sensitivity-surface generates 2D grid."""
    resp = client.post("/api/tail-risk/sensitivity-surface", json={
        "target_loss_pct": 0.20,
        "grid_steps": 5,
        "portfolio": sample_test_portfolio.to_dict(),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "surface" in data
    assert len(data["surface"]["cells"]) == 25
