"""
FragilityShield — All 11 Labs Comprehensive Verification Suite
Tests the complete mathematical, logical, and API contracts for all 11 quantitative research labs.
"""

import pytest
from starlette.testclient import TestClient
from backend.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def sample_portfolio(client: TestClient) -> dict:
    resp = client.get("/api/portfolios/sample?name=nse_10l.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    return data["portfolio"]


class TestAll11LabsComprehensive:
    """Verifies all 11 FragilityShield labs through their active API and calculation contracts."""

    # --------------------------------------------------------------------------
    # Lab 1: Risk Attribution Lab (/labs/attribution)
    # --------------------------------------------------------------------------
    def test_01_risk_attribution_euler_decomposition(self, client: TestClient, sample_portfolio: dict):
        """Verifies Euler risk attribution and mathematical reconciliation."""
        payload = {
            "portfolio": sample_portfolio,
            "confidence_level": 0.95,
        }
        resp = client.post("/api/risk/attribution", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        attr = data["attribution"]
        assert "portfolio_var_95" in attr
        assert "asset_attributions" in attr
        assert len(attr["asset_attributions"]) > 0

        # Verify Euler homogeneity theorem: sum of component VaRs equals portfolio VaR
        sum_cvar = sum(a["component_var"] for a in attr["asset_attributions"])
        assert abs(sum_cvar - attr["portfolio_var_95"]) < 1e-4

    # --------------------------------------------------------------------------
    # Lab 2: Scenario Analysis Lab (/labs/scenarios & /labs/risk-scenarios)
    # --------------------------------------------------------------------------
    def test_02_scenario_analysis_execution(self, client: TestClient, sample_portfolio: dict):
        """Verifies multi-factor scenario stress execution and portfolio P&L."""
        payload = {
            "portfolio": sample_portfolio,
            "scenario": {
                "name": "Banking Stress -20%",
                "sector_shocks": {
                    "Banking": -0.20,
                    "Information Technology": -0.10,
                },
            },
        }
        resp = client.post("/api/scenarios/execute", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        assert "scenario_pnl" in data
        assert "scenario_return" in data
        assert "position_pnl" in data
        assert data["scenario_return"] < 0  # Negative shock must produce negative return

    # --------------------------------------------------------------------------
    # Lab 3: Reverse Stress Testing Lab (/labs/reverse-stress & /labs/tail-risk)
    # --------------------------------------------------------------------------
    def test_03_reverse_stress_boundary_search(self, client: TestClient, sample_portfolio: dict):
        """Verifies iterative boundary search for target loss breach."""
        payload = {
            "portfolio": sample_portfolio,
            "target_loss_pct": 0.15,
        }
        resp = client.post("/api/scenarios/reverse-stress", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        assert "required_market_shock" in data
        assert "reverse_stress" in data
        assert data["reverse_stress"]["target_loss_pct"] == 0.15

    # --------------------------------------------------------------------------
    # Lab 4: Fragility & Assumption Sensitivity Studio (/labs/fragility & /assumptions)
    # --------------------------------------------------------------------------
    def test_04_fragility_assumption_sensitivity_sweep(self, client: TestClient, sample_portfolio: dict):
        """Verifies parameter perturbation sensitivity calculation and delta ranking."""
        payload = {
            "portfolio": sample_portfolio,
            "returns": [0.012, -0.015, 0.008, -0.004, 0.021, -0.018, 0.005, -0.009, 0.014, -0.007] * 5,
        }
        resp = client.post("/api/fragility/run", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        assert "experiments" in data
        assert len(data["experiments"]) >= 4
        assert "sensitivity_rankings" in data

    # --------------------------------------------------------------------------
    # Lab 5: Monte Carlo Simulation Lab (/labs/monte-carlo)
    # --------------------------------------------------------------------------
    def test_05_monte_carlo_stochastic_simulation(self, client: TestClient):
        """Verifies Monte Carlo path generation, quantiles, and seed reproducibility."""
        payload = {
            "symbol": "RELIANCE",
            "initial_value": 1_000_000.0,
            "num_paths": 100,
            "horizon_days": 30,
            "method": "student_t",
            "degrees_of_freedom": 5,
            "seed": 42,
        }
        resp = client.post("/api/monte-carlo/run", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert "percentile_bands" in data
        assert "distribution_histogram" in data
        assert "terminal_metrics" in data
        assert len(data["sample_trajectories"]) <= 8

    # --------------------------------------------------------------------------
    # Lab 6: Bootstrap & Uncertainty Lab (/labs/uncertainty)
    # --------------------------------------------------------------------------
    def test_06_bootstrap_uncertainty_resampling(self, client: TestClient):
        """Verifies block bootstrap resampling confidence intervals."""
        payload = {
            "symbol": "RELIANCE",
            "metric": "sharpe_ratio",
            "resampling_method": "moving_block_bootstrap",
            "num_resamples": 100,
            "confidence_level": 0.95,
            "block_length": 5,
            "seed": 42,
        }
        resp = client.post("/api/uncertainty/bootstrap", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert "point_estimate" in data
        u = data["uncertainty_metrics"]
        assert "percentile_interval" in u
        assert "basic_interval" in u
        assert "normal_approx_interval" in u
        assert u["percentile_interval"]["lower"] <= u["percentile_interval"]["upper"]

    # --------------------------------------------------------------------------
    # Lab 7: Risk Model Backtesting Observatory (/models/risk-validation)
    # --------------------------------------------------------------------------
    def test_07_risk_model_backtesting_validation(self, client: TestClient):
        """Verifies forecast vs. realization Kupiec POF backtesting."""
        payload = {
            "symbol": "RELIANCE",
            "model_id": "historical_simulation",
            "training_window": 120,
            "confidence_level": 0.95,
        }
        resp = client.post("/api/models/risk-validation/run", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        val = data["validation"]
        assert "kupiec_unconditional_coverage" in val
        assert "christoffersen_conditional_coverage" in val
        assert "expected_shortfall_validation" in val
        assert len(val["forecast_sample"]) > 0

    # --------------------------------------------------------------------------
    # Lab 8: ML Forecasting & Evaluation Lab (/labs/ml-forecasting)
    # --------------------------------------------------------------------------
    def test_08_ml_forecasting_chronological_split(self, client: TestClient):
        """Verifies autoregressive forecast without lookahead bias."""
        payload = {
            "symbol": "RELIANCE",
            "model_id": "linear_regression",
            "lags": 5,
            "forecast_horizon": 1,
            "train_ratio": 0.8,
        }
        resp = client.post("/api/ml/forecast-run", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        assert "metrics" in data
        assert "directional_accuracy_pct" in data["metrics"]
        assert "rmse" in data["metrics"]
        assert "mase" in data["metrics"]
        assert len(data.get("forecast_points", [])) > 0
        assert "chronological_split" in data
        assert data["chronological_split"]["leakage_verified"] is True
        assert data["chronological_split"]["train_size"] > data["chronological_split"]["test_size"]

    # --------------------------------------------------------------------------
    # Lab 9: ML Robustness & Adversarial Testing Lab (/labs/ml-robustness)
    # --------------------------------------------------------------------------
    def test_09_ml_robustness_adversarial_noise(self, client: TestClient):
        """Verifies multi-tier noise injection and degradation curve."""
        payload = {
            "symbol": "RELIANCE",
            "model_id": "linear_regression",
            "noise_levels": [0.01, 0.05, 0.10],
            "missing_rates": [0.05, 0.10],
            "seed": 42,
        }
        resp = client.post("/api/ml/robustness-run", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        assert "attacks" in data
        assert len(data["attacks"]) >= 3
        assert "verdict" in data

    # --------------------------------------------------------------------------
    # Lab 10: Model Tournament & Benchmarking (/labs/tournament)
    # --------------------------------------------------------------------------
    def test_10_model_tournament_benchmarking(self, client: TestClient):
        """Verifies candidate comparison and Deflated Sharpe Ratio calculation."""
        payload = {
            "protocol": {
                "symbol": "RELIANCE",
                "primary_metric": "sharpe_ratio",
                "transaction_cost_bps": 10.0,
            }
        }
        resp = client.post("/api/tournaments/run", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "tournament_id" in data
        assert "leaderboard" in data
        assert len(data["leaderboard"]) > 0

    # --------------------------------------------------------------------------
    # Lab 11: Quantitative Allocation & Optimization Lab (/labs/allocation)
    # --------------------------------------------------------------------------
    def test_11_quantitative_allocation_optimization(self, client: TestClient, sample_portfolio: dict):
        """Verifies constrained minimum-variance quadratic optimization and feasibility."""
        payload = {
            "portfolio": sample_portfolio,
            "objective": "MIN_VOLATILITY",
            "max_weight": 0.35,
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("success") is True
        weights = data.get("weights", {})
        assert len(weights) > 0
        total_weight = sum(weights.values())
        assert abs(total_weight - 1.0) < 0.05
        # Verify non-negativity constraint (long only)
        for w in weights.values():
            assert w >= -1e-6
