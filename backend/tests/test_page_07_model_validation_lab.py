"""Comprehensive test suite for Page 07: Model Testing & Validation Lab (/models).

Tests:
1. Model Registry and benchmark model plugin discovery.
2. Leak-free chronological split and model evaluation.
3. Kupiec POF empirical coverage hypothesis testing.
4. Baseline persistence benchmarking and noise injection robustness.
5. Persistent validation execution runs history.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestPage07ModelValidationLab:
    """Test suite for Page 07 Model Testing & Validation Lab backend services."""

    def test_model_registry_discovery(self, client: TestClient):
        resp = client.get("/api/benchmarks/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["models"]) >= 3

        # Check native models
        plugin_ids = [m["plugin_id"] for m in data["models"]]
        assert any("parametric" in p for p in plugin_ids)
        assert any("historical" in p for p in plugin_ids)
        assert any("ewma" in p for p in plugin_ids)

    def test_model_validation_leak_free_execution(self, client: TestClient):
        returns = [
            0.012, -0.015, 0.008, -0.022, 0.019, -0.004, 0.007, -0.011,
            0.014, -0.018, 0.025, -0.031, 0.009, -0.006, 0.013, -0.016,
            0.021, -0.009, 0.004, -0.007, 0.015, -0.012, 0.008, -0.019,
            0.011, -0.014, 0.022, -0.028, 0.005, -0.009, 0.017, -0.013
        ]
        payload = {
            "model_id": "builtin.parametric_gaussian",
            "returns": returns,
            "train_ratio": 0.70,
            "val_ratio": 0.15,
            "task_type": "risk_model",
        }
        resp = client.post("/api/models/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        rep = data["validation_report"]
        assert rep["model_id"] == "builtin.parametric_gaussian"
        assert rep["train_size"] > 0
        assert rep["test_size"] > 0

        # Verify zero-leakage checks
        assert "PASSED" in rep["leakage_checks"]["chronological_ordering"]
        assert "PASSED" in rep["leakage_checks"]["future_lookahead"]

        # Verify Kupiec coverage test metrics
        test_m = rep["test_metrics"]
        assert test_m["var_threshold"] > 0
        assert test_m["expected_breach_rate"] == 5.0
        assert "kupiec_test_passed" in test_m
        assert test_m["kupiec_lr_statistic"] >= 0

        # Verify baseline persistence comparison
        bench = rep["benchmarks"]
        assert bench["naive_persistence_rmse"] > 0
        assert "relative_skill_pct" in bench

    def test_model_validation_adversarial_robustness(self, client: TestClient):
        returns = [
            0.01, -0.02, 0.015, -0.005, 0.02, -0.03, 0.01, 0.005,
            -0.015, 0.02, -0.01, 0.008, -0.025, 0.012, 0.004, -0.008,
            0.018, -0.012, 0.006, -0.004, 0.015, -0.01, 0.005, -0.015,
            0.02, -0.01, 0.008, -0.025, 0.012, 0.004, -0.008, 0.018
        ]
        payload = {
            "model_id": "builtin.historical_simulation",
            "returns": returns,
            "train_ratio": 0.70,
            "val_ratio": 0.15,
        }
        resp = client.post("/api/models/validate", json=payload)
        assert resp.status_code == 200
        rob = resp.json()["validation_report"]["robustness"]
        assert "noise_injection_degradation_pct" in rob
        assert rob["bull_days_count"] + rob["bear_days_count"] == resp.json()["validation_report"]["test_size"]
        assert rob["determinism_verified"] is True

    def test_model_validation_runs_history(self, client: TestClient):
        resp = client.get("/api/models/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1
        first_run = data["runs"][0]
        assert "run_id" in first_run
        assert "model_name" in first_run
        assert "validation_status" in first_run
