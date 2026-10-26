"""Comprehensive test suite for Page 06: Fragility Assumption Matrix (/assumptions).

Tests:
1. 2D Sensitivity Matrix execution across configurable dimensions.
2. Conclusion rule breach evaluation (k/N ratio and percentage).
3. Full multi-assumption fragility audit battery and ranking.
4. Assumption catalogue formal specifications and failure regimes.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestPage06FragilityAssumptionMatrix:
    """Test suite for Page 06 Fragility Assumption Matrix backend services."""

    def test_sensitivity_matrix_computation(self, client: TestClient):
        returns = [
            0.012, -0.015, 0.008, -0.022, 0.019, -0.004, 0.007, -0.011,
            0.014, -0.018, 0.025, -0.031, 0.009, -0.006, 0.013, -0.016,
            0.021, -0.009, 0.004, -0.007, 0.015, -0.012, 0.008, -0.019
        ]
        payload = {
            "returns": returns,
            "target_metric": "var_95",
            "row_dim": "lookback_window",
            "row_values": [10, 20],
            "col_dim": "confidence_level",
            "col_values": [0.90, 0.95, 0.99],
        }
        resp = client.post("/api/fragility/matrix", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["cells"]) == 6
        assert data["baseline_value"] > 0
        assert data["diagnostics"]["completed_runs"] == 6
        assert data["diagnostics"]["min_value"] <= data["diagnostics"]["max_value"]
        assert data["diagnostics"]["absolute_sensitivity_range"] >= 0

        # Verify each cell structure
        for cell in data["cells"]:
            assert "row_value" in cell
            assert "col_value" in cell
            assert cell["status"] == "completed"
            assert cell["value"] is not None

    def test_sensitivity_matrix_conclusion_rule(self, client: TestClient):
        returns = [
            0.01, -0.02, 0.015, -0.03, 0.02, -0.04, 0.01, -0.015,
            0.02, -0.025, 0.005, -0.018, 0.012, -0.022, 0.008, -0.016,
            0.014, -0.028, 0.009, -0.012, 0.018, -0.024
        ]
        payload = {
            "returns": returns,
            "target_metric": "var_95",
            "row_dim": "lookback_window",
            "row_values": [10, 20],
            "col_dim": "confidence_level",
            "col_values": [0.90, 0.95, 0.99],
            "conclusion_threshold": 0.025,
            "conclusion_operator": ">",
        }
        resp = client.post("/api/fragility/matrix", json=payload)
        assert resp.status_code == 200
        diag = resp.json()["diagnostics"]
        assert diag["conclusion_threshold"] == 0.025
        assert diag["conclusion_operator"] == ">"
        assert diag["conclusion_breaches"] >= 0
        assert "/" in diag["conclusion_change_ratio"]

    def test_fragility_audit_comprehensive(self, client: TestClient):
        returns = [
            0.01, -0.012, 0.015, -0.02, 0.008, -0.005, 0.014, -0.018,
            0.022, -0.009, 0.011, -0.016, 0.007, -0.013, 0.019, -0.025,
            0.016, -0.008, 0.004, -0.011, 0.015, -0.017, 0.006, -0.014
        ]
        payload = {
            "returns": returns,
            "target_metric": "volatility_annualized",
            "conclusion_threshold": 0.20,
            "conclusion_operator": ">",
        }
        resp = client.post("/api/fragility/audit", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "audit_report" in data
        assert len(data["audit_report"]["experiments"]) >= 4
        assert "sensitivity_ranking" in data["audit_report"]
        assert data["summary"]["total_tested"] >= 4

    def test_assumption_catalogue_completeness(self, client: TestClient):
        resp = client.get("/api/assumptions/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["assumptions"]) >= 3

        # Check required fields for quantitative model assumptions
        first = data["assumptions"][0]
        assert "model_id" in first
        assert "model_name" in first
        assert "mathematical_formulation" in first
        assert "distributional_assumption" in first
        assert "temporal_assumption" in first
        assert "sample_size_precondition" in first
        assert len(first["known_failure_regimes"]) > 0
        assert len(first["fragility_attack_vulnerabilities"]) > 0
