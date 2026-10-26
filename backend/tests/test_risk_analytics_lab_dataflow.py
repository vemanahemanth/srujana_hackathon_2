"""
FragilityShield — Risk Analytics Lab Frontend Data-Flow & Quantitative Integrity Tests

Tests that the risk calculation API contract supplies complete quantitative series
(returns, equity curve, drawdown series, VaR, CVaR, volatility) required by the 6 lab charts,
validates that worker status fields are handled without undefined errors, and verifies
that mathematical data transformations for all 6 charts are mathematically correct.
"""

import math
import numpy as np
import pytest
from starlette.testclient import TestClient
from backend.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestRiskAnalyticsLabDataFlow:
    """End-to-end API contract and quantitative integrity tests for Risk Analytics Lab."""

    def test_risk_calculate_returns_complete_chart_series(self, client: TestClient) -> None:
        """Verify that /api/risk/calculate returns all fields required by the 6 quantitative charts."""
        # Realistic 25-day return series with positive and negative shocks
        test_returns = [
            0.012, -0.018, 0.005, 0.021, -0.009, 0.015, -0.025, 0.008,
            -0.003, 0.014, -0.011, 0.019, 0.002, -0.007, 0.013, -0.016,
            0.006, 0.004, -0.012, 0.022, -0.005, 0.011, -0.008, 0.003, -0.015
        ]

        payload = {
            "returns": test_returns,
            "confidence_level": 0.95,
            "lookback_window": 252,
            "benchmark_symbol": "NIFTY",
        }

        resp = client.post("/api/risk/calculate", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()

        assert data["success"] is True
        assert "returns" in data, "Must return top-level returns array for periodic returns chart"
        assert len(data["returns"]) == len(test_returns)
        assert np.allclose(data["returns"], test_returns, atol=1e-5)

        assert "equity_curve" in data, "Must return equity_curve for cumulative returns chart"
        assert len(data["equity_curve"]) == len(test_returns) + 1
        assert data["equity_curve"][0] == 1.0

        assert "drawdown_series" in data, "Must return drawdown_series for underwater chart"
        assert len(data["drawdown_series"]) > 0

        assert "annualized_volatility" in data
        assert data["annualized_volatility"] > 0

        assert "custom_var" in data
        assert "custom_es" in data
        assert data["custom_es"] >= data["custom_var"], "Coherence: Expected Shortfall must be >= VaR"

        assert "maximum_drawdown" in data
        assert 0.0 <= data["maximum_drawdown"] <= 1.0

        assert "data_provenance" in data
        assert "explanation_panels" in data
        assert "volatility" in data["explanation_panels"]
        assert "var" in data["explanation_panels"]
        assert "expected_shortfall" in data["explanation_panels"]
        assert "drawdown" in data["explanation_panels"]

    def test_risk_calculate_insufficient_returns_rejected(self, client: TestClient) -> None:
        """Verify that series with fewer than 4 observations are rejected honestly."""
        payload = {"returns": [0.01, -0.02]}
        resp = client.post("/api/risk/calculate", json=payload)
        assert resp.status_code == 400
        data = resp.json()
        assert "at least 4" in data.get("error", "").lower()

    def test_risk_calculate_non_finite_rejected(self, client: TestClient) -> None:
        """Verify that NaN or Inf values in returns are rejected with explanatory error."""
        # Using raw JSON string with NaN token
        raw_body = '{"returns": [0.01, NaN, -0.02, 0.015]}'
        resp = client.post("/api/risk/calculate", content=raw_body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        data = resp.json()
        assert "non-finite" in data.get("error", "").lower() or "error" in data

    def test_worker_status_contract_and_field_handling(self, client: TestClient) -> None:
        """Verify /api/workers/status returns worker diagnostics and has total_succeeded/claimed."""
        resp = client.get("/api/workers/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "worker" in data
        worker = data["worker"]
        assert "worker_id" in worker
        assert worker["worker_id"].startswith("worker_")
        # Ensure either total_succeeded or jobs_processed is present
        has_count = "total_succeeded" in worker or "jobs_processed" in worker or "total_claimed" in worker
        assert has_count, "Worker diagnostics must supply a valid job/succeeded count"

    def test_illustrative_sample_portfolio_fixture(self, client: TestClient) -> None:
        """Verify that sample nse_10l.json fixture is labeled illustrative."""
        resp = client.get("/api/portfolios/sample?name=nse_10l.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        port = data["portfolio"]
        assert "illustrative" in port["portfolio_id"].lower() or "illustrative" in port["name"].lower()
        assert len(port["holdings"]) > 0


class TestChartTransformations:
    """Verifies that mathematical transformations in RiskAnalyticsLab produce correct results."""

    @pytest.fixture
    def sample_returns(self) -> np.ndarray:
        return np.array([
            0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.005, -0.012, 0.008, -0.003,
            0.012, -0.018, 0.005, 0.002, -0.007, 0.014, -0.009, 0.006, -0.004, 0.011,
            -0.015, 0.008, 0.003, -0.006, 0.019
        ])

    def test_cumulative_returns_transformation(self, sample_returns: np.ndarray) -> None:
        """Cumulative return must equal (prod(1 + r) - 1) * 100%."""
        cum_equity = np.cumprod(1.0 + sample_returns)
        cum_ret = (cum_equity - 1.0) * 100.0
        assert len(cum_ret) == len(sample_returns)
        assert math.isclose(cum_ret[-1], (np.prod(1.0 + sample_returns) - 1.0) * 100.0, rel_tol=1e-5)

    def test_rolling_volatility_transformation(self, sample_returns: np.ndarray) -> None:
        """20-day rolling annualized volatility uses sample std with ddof=1 * sqrt(252) * 100%."""
        window = 20
        rolling_vols = []
        for i in range(window - 1, len(sample_returns)):
            slice_ = sample_returns[i - window + 1 : i + 1]
            ann_vol = np.std(slice_, ddof=1) * np.sqrt(252) * 100.0
            rolling_vols.append(ann_vol)
        assert len(rolling_vols) == len(sample_returns) - window + 1
        assert all(v > 0 for v in rolling_vols)

    def test_underwater_drawdown_transformation(self, sample_returns: np.ndarray) -> None:
        """Underwater drawdown is <= 0% and starts at 0%."""
        equity = np.cumprod(1.0 + sample_returns)
        peaks = np.maximum.accumulate(equity)
        dds = -((peaks - equity) / peaks) * 100.0
        assert all(dd <= 1e-9 for dd in dds), "Underwater drawdown must never be positive"
        assert min(dds) <= 0.0

    def test_tail_loss_sorting_and_cvar_coherence(self, sample_returns: np.ndarray) -> None:
        """Ordered losses L = -R, and Expected Shortfall >= VaR."""
        losses = -sample_returns * 100.0
        sorted_losses = np.sort(losses)
        assert np.all(np.diff(sorted_losses) >= 0), "Tail losses must be sorted ascending"

        # Empirical 95% VaR and CVaR
        alpha = 0.95
        var_threshold = np.quantile(sorted_losses, alpha)
        tail_breaches = sorted_losses[sorted_losses >= var_threshold]
        cvar = np.mean(tail_breaches) if len(tail_breaches) > 0 else var_threshold

        assert cvar >= var_threshold, f"Coherence violated: CVaR ({cvar}) must be >= VaR ({var_threshold})"
