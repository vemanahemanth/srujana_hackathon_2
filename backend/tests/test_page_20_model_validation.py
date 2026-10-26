"""Tests for FragilityShield Page 20: Model Validation Lab."""

import pytest
from starlette.testclient import TestClient

from app import create_application


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_page_20_valid_model_validation(client):
    """Test valid model validation execution on genuine Upstox catalog data."""
    res = client.post("/api/models/validate", json={
        "model_id": "builtin.parametric_gaussian",
        "symbol": "RELIANCE",
        "train_ratio": 0.70,
        "val_ratio": 0.15,
        "task_type": "risk_model",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    report = data["validation_report"]
    assert "run_id" in report
    assert "test_metrics" in report
    assert "kupiec_test_passed" in report["test_metrics"]
    assert "benchmarks" in report
    assert "leakage_checks" in report
    assert report["sample_size"] >= 15


def test_page_20_invalid_dataset_rejection(client):
    """Test rejection when dataset does not exist or violates strict real-data policy."""
    res = client.post("/api/models/validate", json={
        "model_id": "builtin.parametric_gaussian",
        "symbol": "NON_EXISTENT_TICKER_XYZ",
    })
    assert res.status_code == 400
    assert "validation failed" in res.json()["error"].lower()


def test_page_20_temporal_leakage_protection(client):
    """Test that temporal split enforces strict chronological ordering and partition bounds."""
    res = client.post("/api/models/validate", json={
        "model_id": "builtin.historical_simulation",
        "symbol": "RELIANCE",
        "train_ratio": 0.60,
    })
    assert res.status_code == 200
    checks = res.json()["validation_report"]["leakage_checks"]
    assert "PASSED" in checks["chronological_ordering"]
    assert "Train:" in checks["split_boundaries"] and "Test:" in checks["split_boundaries"]
    assert "PASSED" in checks["future_lookahead"]


def test_page_20_historical_and_ewma_validation(client):
    """Test model validation on non-parametric historical simulation and EWMA models."""
    # Historical Simulation
    res_hist = client.post("/api/models/validate", json={
        "model_id": "builtin.historical_simulation",
        "symbol": "RELIANCE",
        "train_ratio": 0.70,
        "val_ratio": 0.15,
    })
    assert res_hist.status_code == 200
    data_hist = res_hist.json()["validation_report"]
    assert "Empirical" in data_hist["model_name"]
    assert data_hist["test_metrics"]["var_threshold"] > 0

    # EWMA Volatility
    res_ewma = client.post("/api/models/validate", json={
        "model_id": "builtin.ewma",
        "symbol": "RELIANCE",
        "train_ratio": 0.70,
        "val_ratio": 0.15,
    })
    assert res_ewma.status_code == 200
    data_ewma = res_ewma.json()["validation_report"]
    assert "EWMA" in data_ewma["model_name"]
    assert data_ewma["test_metrics"]["var_threshold"] > 0


def test_page_20_benchmark_and_noise_robustness(client):
    """Test benchmark comparisons and adversarial noise injection degradation metrics."""
    res = client.post("/api/models/validate", json={
        "model_id": "builtin.parametric_gaussian",
        "symbol": "RELIANCE",
        "train_ratio": 0.70,
    })
    assert res.status_code == 200
    rep = res.json()["validation_report"]
    assert "benchmarks" in rep
    assert "naive_persistence_rmse" in rep["benchmarks"]
    assert "relative_skill_pct" in rep["benchmarks"]
    assert "robustness" in rep
    assert "noise_injection_degradation_pct" in rep["robustness"]
    assert rep["robustness"]["determinism_verified"] is True


def test_page_20_invalid_split_boundary_rejection(client):
    """Test rejection when train_ratio leaves insufficient sample size for test partition."""
    res = client.post("/api/models/validate", json={
        "model_id": "builtin.parametric_gaussian",
        "symbol": "RELIANCE",
        "train_ratio": 0.98,
        "val_ratio": 0.01,
    })
    assert res.status_code == 400
    assert "insufficient" in res.json()["error"].lower()


def test_page_20_runs_history_and_retrieval(client):
    """Test listing model validation runs history and ensuring persisted records are retrievable."""
    res = client.get("/api/models/runs")
    assert res.status_code == 200
    data = res.json()
    assert "runs" in data
    assert "count" in data
    assert data["count"] >= 1

