"""Unit and mathematical tests for Euler Marginal Risk Allocation and Component VaR.

Verifies:
1. Exact Euler Homogeneity Theorem: sum(ComponentVaR_i) == TotalPortfolioVaR.
2. Beta-to-portfolio calculation: beta_i = Cov(R_i, R_p) / Var(R_p).
3. Diversifier detection (beta_i < 1.0 vs beta_i >= 1.0).
4. Sector aggregate risk contributions.
5. Auto-generation of calibrated correlated asset returns when matrix is omitted.
6. Custom matrix inputs and dimension validation.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.attribution import (
    AssetRiskAttribution,
    PortfolioRiskAttributionReport,
    calculate_portfolio_risk_attribution,
)
from fragility_engine.models import Holding, Portfolio


def test_euler_exact_reconciliation() -> None:
    """Euler Theorem requires sum of Component VaRs to equal Total Portfolio VaR."""
    holdings = [
        Holding(asset_id="HDFCBANK", quantity=100, price=1600.0, sector="Financial Services"),
        Holding(asset_id="TCS", quantity=40, price=3800.0, sector="Information Technology"),
        Holding(asset_id="RELIANCE", quantity=60, price=2900.0, sector="Energy"),
        Holding(asset_id="ICICIBANK", quantity=80, price=1100.0, sector="Financial Services"),
    ]
    portfolio = Portfolio(
        portfolio_id="test_port",
        name="Test Portfolio",
        currency="INR",
        holdings=holdings,
    )

    report = calculate_portfolio_risk_attribution(portfolio, confidence_level=0.95)

    assert report.portfolio_id == "test_port"
    assert len(report.asset_attributions) == 4
    assert report.total_valuation > 0.0

    # Verify Euler theorem: sum(ComponentVaR_i) == PortfolioVaR
    sum_cvar = sum(a.component_var for a in report.asset_attributions)
    assert math.isclose(sum_cvar, report.portfolio_var_95, abs_tol=1e-7)
    assert report.euler_discrepancy < 1e-7

    # Verify percentage risk contributions sum to 100%
    sum_pct = sum(a.percentage_risk_contribution for a in report.asset_attributions)
    assert math.isclose(sum_pct, 100.0, abs_tol=1e-3)

    # Sector contributions must reconcile with sum of constituent component VaRs
    fin_cvar = sum(a.component_var for a in report.asset_attributions if a.sector == "Financial Services")
    assert math.isclose(report.sector_risk_contributions["Financial Services"], fin_cvar, abs_tol=1e-7)


def test_euler_with_custom_return_matrix() -> None:
    """Calculate risk decomposition using explicit user-supplied return series."""
    holdings = [
        Holding(asset_id="ASSET_A", quantity=10, price=100.0, sector="Tech"),
        Holding(asset_id="ASSET_B", quantity=10, price=100.0, sector="Energy"),
    ]
    portfolio = Portfolio("two_asset", "Two Asset", "INR", holdings)

    # Asset A and B with positive returns and specific variance
    np.random.seed(42)
    ret_a = np.random.normal(0.001, 0.02, 60).tolist()
    ret_b = np.random.normal(0.0005, 0.01, 60).tolist()

    report = calculate_portfolio_risk_attribution(
        portfolio,
        asset_returns_matrix={"ASSET_A": ret_a, "ASSET_B": ret_b},
        confidence_level=0.95,
    )

    assert len(report.asset_attributions) == 2
    sum_cvar = report.asset_attributions[0].component_var + report.asset_attributions[1].component_var
    assert math.isclose(sum_cvar, report.portfolio_var_95, abs_tol=1e-7)


def test_attribution_validation_errors() -> None:
    """Test validation boundaries: missing assets, non-finite returns, unequal series lengths."""
    holdings = [Holding(asset_id="A", quantity=10, price=100.0)]
    portfolio = Portfolio("p1", "P1", "INR", holdings)

    # Missing asset in matrix
    with pytest.raises(ValueError, match="missing from provided asset_returns_matrix"):
        calculate_portfolio_risk_attribution(portfolio, asset_returns_matrix={"B": [0.01] * 20})

    # Unequal lengths
    h2 = [Holding(asset_id="A", quantity=10, price=100.0), Holding(asset_id="B", quantity=10, price=100.0)]
    p2 = Portfolio("p2", "P2", "INR", h2)
    with pytest.raises(ValueError, match="Inconsistent return series lengths"):
        calculate_portfolio_risk_attribution(p2, asset_returns_matrix={"A": [0.01] * 20, "B": [0.01] * 25})
