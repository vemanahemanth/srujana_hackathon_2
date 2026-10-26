"""Unit and API integration tests for ML Forecasting and ML Robustness Labs."""

import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_run_ml_forecasting(client):
    resp = client.post("/api/ml/forecast-run", json={
        "symbol": "RELIANCE",
        "model_id": "linear_regression",
        "forecast_horizon": 1,
        "train_ratio": 0.70,
        "lags": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["symbol"] == "RELIANCE"
    assert data["model_id"] == "linear_regression"
    assert "metrics" in data
    assert "rmse" in data["metrics"]
    assert "directional_accuracy_pct" in data["metrics"]
    assert "chronological_split" in data
    assert data["chronological_split"]["leakage_verified"] is True
    assert len(data["forecast_points"]) > 0


def test_api_run_ml_robustness(client):
    resp = client.post("/api/ml/robustness-run", json={
        "symbol": "RELIANCE",
        "model_id": "linear_regression",
        "noise_levels": [0.01, 0.05, 0.10],
        "missing_rates": [0.05, 0.10],
        "seed": 42,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["symbol"] == "RELIANCE"
    assert "baseline_value" in data
    assert "attacks" in data
    assert len(data["attacks"]) == 5  # 3 noise + 2 missing
    assert "verdict" in data
