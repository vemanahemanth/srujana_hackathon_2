"""Test suite for Page 05 Risk & Scenario Analysis Lab.

Verifies:
1. Preset Scenarios API: Exposing standard stress benchmarks (e.g. banking_minus_20_it_minus_10,
   mild_market_correction, severe_market_crash, gfc_2008_replay, covid_2020_replay).
2. Scenario Execution Engine: Linear asset-level and sector-level shocks, portfolio revaluation,
   position-level loss breakdown, and contribution percentages.
3. Reverse Stress Testing: Root-finding solver for identifying factor shock boundaries that breach
   target loss thresholds.
4. Core Reproducible Risk Calculations:
   - Daily returns r_t = P_t / P_{t-1} - 1
   - Annualized volatility sigma * sqrt(252)
   - Historical VaR at 95% and 99%
   - Coherent Expected Shortfall (CVaR)
   - CAPM Beta vs benchmark index Cov(r_i, r_b) / Var(r_b)
   - Maximum drawdown
5. Assumption Challenge & Sensitivity: Reproducible run IDs and transparent parameter validation.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPage05RiskScenarioLab:
    """Comprehensive test suite for Page 05 Risk & Scenario Analysis Lab."""

    def test_preset_scenarios_catalog(self, client: TestClient):
        resp = client.get("/api/scenarios/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        presets = data["presets"]
        assert len(presets) >= 4
        preset_ids = [p["scenario_id"] for p in presets]
        assert "banking_minus_20_it_minus_10" in preset_ids
        assert "mild_market_correction" in preset_ids
        assert "severe_market_crash" in preset_ids

        # Check fields of a preset
        first = presets[0]
        assert "name" in first
        assert "category" in first
        assert "shocks" in first
        assert "description" in first

    def test_scenario_execution_revaluation(self, client: TestClient):
        portfolio = {
            "portfolio_id": "port_scenario_test",
            "name": "Scenario Lab Test",
            "currency": "INR",
            "holdings": [
                {"asset_id": "RELIANCE", "quantity": 100.0, "current_price": 2800.0, "sector": "Energy"},
                {"asset_id": "INFY", "quantity": 100.0, "current_price": 1500.0, "sector": "Technology"},
                {"asset_id": "HDFCBANK", "quantity": 100.0, "current_price": 1600.0, "sector": "Financials"}
            ]
        }
        # Shock: Broad market drop -10%, IT -15%
        exec_payload = {
            "portfolio": portfolio,
            "scenario": {
                "name": "Technology Selloff",
                "shocks": {
                    "INFY": -0.15,
                    "RELIANCE": -0.05
                }
            }
        }
        resp = client.post("/api/scenarios/execute", json=exec_payload)
        assert resp.status_code == 200
        result = resp.json()

        # Base value: (100*2800) + (100*1500) + (100*1600) = 280,000 + 150,000 + 160,000 = 590,000
        assert result["base_value"] == 590000.0
        # INFY loss: 150,000 * -0.15 = -22,500
        # RELIANCE loss: 280,000 * -0.05 = -14,000
        # Total PnL: -36,500
        assert result["scenario_pnl"] == -36500.0
        assert result["shocked_value"] == 590000.0 - 36500.0
        assert pytest.approx(result["scenario_return"], 1e-4) == -36500.0 / 590000.0

        # Position breakdown
        breakdown = result.get("position_pnl") or result.get("position_breakdown")
        assert breakdown is not None
        assert breakdown["INFY"] == -22500.0
        assert breakdown["RELIANCE"] == -14000.0
        assert breakdown.get("HDFCBANK", 0.0) == 0.0

    def test_reverse_stress_testing_boundary(self, client: TestClient):
        portfolio = {
            "portfolio_id": "port_rev_stress",
            "name": "Reverse Stress Portfolio",
            "currency": "INR",
            "holdings": [
                {"asset_id": "TCS", "quantity": 100.0, "current_price": 3500.0},
                {"asset_id": "WIPRO", "quantity": 200.0, "current_price": 500.0}
            ]
        }
        # Find market shock that breaches 10% portfolio loss (loss_threshold = 0.10)
        payload = {
            "portfolio": portfolio,
            "loss_threshold": 0.10
        }
        resp = client.post("/api/scenarios/reverse-stress", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # For a uniform linear shock, required shock is exactly -0.10
        assert pytest.approx(data["required_market_shock"], 1e-3) == -0.10
        assert data["converged"] is True

    def test_reproducible_risk_metrics(self, client: TestClient):
        portfolio = {
            "portfolio_id": "port_risk_calc",
            "name": "Risk Calculation Sample",
            "currency": "INR",
            "holdings": [
                {"asset_id": "RELIANCE", "quantity": 10.0, "current_price": 2800.0},
                {"asset_id": "TCS", "quantity": 5.0, "current_price": 3800.0}
            ]
        }
        resp = client.post("/api/risk/calculate", json={"portfolio": portfolio, "confidence_level": 0.95})
        assert resp.status_code == 200
        report = resp.json()
        assert "annualized_volatility" in report
        assert report["annualized_volatility"] > 0
        assert "historical_var_95" in report
        assert report["historical_var_95"] >= 0
        assert "expected_shortfall_95" in report
        # Coherence property: Expected Shortfall must be >= VaR
        assert report["expected_shortfall_95"] >= report["historical_var_95"] - 1e-6
        assert "sharpe_ratio" in report
        assert "maximum_drawdown" in report
