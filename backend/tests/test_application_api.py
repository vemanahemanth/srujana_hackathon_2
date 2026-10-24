"""Automated API & Integration Tests for FragilityShield Phase 9.

Tests:
1. Application initialization & route registration
2. System health & capability discovery (`/api/health`)
3. Portfolio loading, validation, and concentration endpoints (`/api/portfolios/*`)
4. Risk engine calculation integration (`/api/risk/calculate`)
5. Scenario stress testing integration (`/api/scenarios/execute`)
6. Fragility assumption perturbation & sensitivity ranking (`/api/fragility/run`)
7. Model benchmarking execution and disclaimers (`/api/benchmarks/*`)
8. Out-of-sample walk-forward VaR backtesting (`/api/backtest/run`)
9. Experiment Studio and multi-format exports (`/api/studio/*`, `/api/export`)
10. Security checks: path traversal defense, non-finite values rejection, error envelopes
"""

import json
import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. System Health & Discovery Tests
# ==============================================================================

def test_api_health(client):
    """Verify /api/health returns operational status and registered subsystems."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "healthy"
    assert "version" in data
    assert "Phase 9" in data["phase"]
    assert len(data["registered_models"]) >= 4
    assert "nse_10l.json" in data["sample_portfolios"]
    assert "banking_minus_20_it_minus_10" in data["preset_scenarios"]


# ==============================================================================
# 2. Portfolio Loading & Validation Tests
# ==============================================================================

def test_api_load_sample_portfolio_json(client):
    """Verify loading the bundled ₹10L NSE JSON portfolio."""
    resp = client.get("/api/portfolios/sample?id=nse_10l.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    port = data["portfolio"]
    assert port["portfolio_id"] == "nse_10l_illustrative"
    assert port["currency"] == "INR"
    assert port["total_value"] == 1000000.0
    assert len(port["holdings"]) == 10

    conc = data["concentration"]
    assert conc["asset_hhi_points"] > 0
    assert conc["sector_hhi_points"] > 0


def test_api_load_sample_portfolio_csv(client):
    """Verify loading the bundled ₹10L NSE CSV portfolio."""
    resp = client.get("/api/portfolios/sample?id=nse_10l.csv")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    port = data["portfolio"]
    assert port["total_value"] == 1000000.0
    assert len(port["holdings"]) == 10


def test_api_load_sample_portfolio_path_traversal_rejection(client):
    """Verify path traversal attempts are rejected safely."""
    resp = client.get("/api/portfolios/sample?id=../../etc/passwd")
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Unsafe filename" in data["error"] or "validation_error" in data["type"]


def test_api_validate_portfolio_json_payload(client):
    """Verify validation of uploaded JSON portfolio structure."""
    payload = {
        "format": "json",
        "content": json.dumps({
            "portfolio_id": "test_port",
            "currency": "INR",
            "holdings": [
                {"asset_id": "RELIANCE", "quantity": 10, "price": 2500.0, "sector": "Energy"},
                {"asset_id": "TCS", "quantity": 5, "price": 3500.0, "sector": "Information Technology"},
            ]
        })
    }
    resp = client.post("/api/portfolios/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["portfolio"]["total_value"] == (10 * 2500.0 + 5 * 3500.0)
    assert len(data["portfolio"]["holdings"]) == 2


def test_api_validate_portfolio_invalid_negative_price(client):
    """Verify rejection of holdings with invalid prices."""
    payload = {
        "format": "json",
        "content": json.dumps({
            "portfolio_id": "bad_port",
            "currency": "INR",
            "holdings": [{"asset_id": "RELIANCE", "quantity": 10, "price": -50.0}]
        })
    }
    resp = client.post("/api/portfolios/validate", json=payload)
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "positive" in data["error"].lower()


def test_api_calculate_concentration(client):
    """Verify standalone concentration endpoint."""
    payload = {
        "portfolio": {
            "portfolio_id": "conc_test",
            "currency": "INR",
            "holdings": [
                {"asset_id": "A1", "quantity": 10, "price": 100.0, "sector": "Tech"},
                {"asset_id": "A2", "quantity": 10, "price": 100.0, "sector": "Tech"},
            ]
        }
    }
    resp = client.post("/api/portfolios/concentration", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # Two equal holdings => HHI asset points = 5000
    assert data["concentration"]["asset_hhi_points"] == 5000
    # Both in same sector => HHI sector points = 10000
    assert data["concentration"]["sector_hhi_points"] == 10000


# ==============================================================================
# 3. Risk Calculation Engine Integration Tests
# ==============================================================================

def test_api_calculate_risk_defaults(client):
    """Verify /api/risk/calculate with default returns series."""
    resp = client.post("/api/risk/calculate", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    report = data["report"]
    assert report["volatility_annualized"] > 0.0
    assert report["var_95"] > 0.0
    assert report["expected_shortfall_95"] >= report["var_95"]
    assert "equity_curve" in data
    assert len(data["equity_curve"]) > 10
    assert "explanation_panels" in data
    assert "Acerbi & Tasche" in data["explanation_panels"]["expected_shortfall"]["coherence"]


def test_api_calculate_risk_custom_confidence(client):
    """Verify /api/risk/calculate with explicit 99% confidence."""
    payload = {
        "confidence_level": 0.99,
        "returns": [-0.01, 0.015, -0.02, 0.01, -0.03, 0.025, -0.005, 0.012, -0.018, 0.02],
    }
    resp = client.post("/api/risk/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["confidence_level"] == 0.99
    assert data["custom_var"] > 0.0


def test_api_calculate_risk_non_finite_rejection(client):
    """Verify rejection of non-finite returns (NaN or Inf)."""
    payload_str = '{"returns": [-0.01, 0.02, 1e9999, 0.015]}'
    resp = client.post("/api/risk/calculate", content=payload_str, headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "non-finite" in data["error"]


# ==============================================================================
# 4. Scenario Stress Lab Integration Tests
# ==============================================================================

def test_api_execute_preset_scenario(client):
    """Verify executing the standard Banking -20% & IT -10% preset scenario."""
    # First get sample portfolio
    sample_res = client.get("/api/portfolios/sample?id=nse_10l.json")
    port = sample_res.json()["portfolio"]

    payload = {
        "portfolio": port,
        "preset_id": "banking_minus_20_it_minus_10",
    }
    resp = client.post("/api/scenarios/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    sc = data["scenario_result"]
    assert sc["original_portfolio_value"] == 1000000.0
    assert sc["stressed_portfolio_value"] == 920000.0
    assert sc["loss_magnitude"] == 80000.0
    assert sc["scenario_return"] == pytest.approx(-0.08)
    assert len(sc["sector_results"]) == 6
    assert "HYPOTHETICAL STRESS SCENARIO ONLY" in data["disclaimer"]


def test_api_execute_custom_scenario(client):
    """Verify executing a custom sector shock scenario."""
    sample_res = client.get("/api/portfolios/sample?id=nse_10l.json")
    port = sample_res.json()["portfolio"]

    payload = {
        "portfolio": port,
        "name": "Custom Energy Shock",
        "sector_shocks": {"Energy": -0.30},
    }
    resp = client.post("/api/scenarios/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    sc = data["scenario_result"]
    # Energy in 10L portfolio is ₹1,50,000. -30% shock is -₹45,000 P&L
    assert sc["loss_magnitude"] == pytest.approx(45000.0)


# ==============================================================================
# 5. Fragility Lab (Central Differentiator) Tests
# ==============================================================================

def test_api_run_fragility_audit(client):
    """Verify assumption perturbation attacks and sensitivity tornado ranking."""
    sample_res = client.get("/api/portfolios/sample?id=nse_10l.json")
    port = sample_res.json()["portfolio"]

    payload = {
        "portfolio": port,
        "friction_bps": 10.0,
        "decay_factor": 0.94,
    }
    resp = client.post("/api/fragility/run", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["experiments"]) >= 4
    assert "volatility_annualized" in data["sensitivity_rankings"]
    assert "var_95" in data["sensitivity_rankings"]
    assert data["liquidation_shock"] is not None
    assert data["liquidation_shock"]["liquidation_cost"] > 0.0
    assert "FRAGILITY DISCOVERY" in data["differentiator_notice"]


# ==============================================================================
# 6. Model Benchmarking Integration Tests
# ==============================================================================

def test_api_list_benchmark_models(client):
    """Verify listing registered model plugins."""
    resp = client.get("/api/benchmarks/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    plugin_ids = [m["plugin_id"] for m in data["models"]]
    assert "builtin.parametric_gaussian" in plugin_ids
    assert "builtin.historical_simulation" in plugin_ids
    assert "builtin.ewma" in plugin_ids


def test_api_execute_benchmark(client):
    """Verify executing comparative model benchmark with rankings and disclaimers."""
    payload = {
        "benchmark_id": "test_bench_api",
        "name": "API Benchmark Test",
        "plugin_ids": ["builtin.parametric_gaussian", "builtin.historical_simulation", "builtin.ewma"],
        "metrics_to_compare": ["var_95", "volatility_annualized"],
        "target_ranking_metric": "var_95",
        "ranking_direction": "lower_is_better",
    }
    resp = client.post("/api/benchmarks/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    report = data["report"]
    assert report["evaluation_mode"] == "in_sample_descriptive"
    assert len(report["rankings"]) == 3
    assert "RANKING DISCLAIMER" in report["ranking_disclaimer"]
    assert "input_fingerprint" in report
    assert "output_fingerprint" in report


# ==============================================================================
# 7. Out-of-Sample VaR Backtesting Integration Tests
# ==============================================================================

def test_api_run_backtest(client):
    """Verify rolling walk-forward out-of-sample backtest with Kupiec and Christoffersen."""
    payload = {
        "model_id": "builtin.parametric_gaussian",
        "estimation_window": 40,
        "confidence_level": 0.95,
    }
    resp = client.post("/api/backtest/run", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    report = data["report"]
    assert report["model_id"] == "builtin.parametric_gaussian"
    assert "kupiec_test" in report
    assert "christoffersen_test" in report
    assert report["evaluation_sample_size"] > 20
    assert len(report["breach_evaluations"]) == report["evaluation_sample_size"]
    assert "Kupiec Unconditional Coverage Test" in data["markdown_preview"]


# ==============================================================================
# 8. Studio Experiment & Multi-Format Exports Tests
# ==============================================================================

def test_api_studio_catalog_and_experiment(client):
    """Verify Studio catalog retrieval and experiment execution."""
    catalog_resp = client.get("/api/studio/catalog")
    assert catalog_resp.status_code == 200
    assert catalog_resp.json()["success"] is True

    exp_resp = client.post("/api/studio/experiment", json={"experiment_id": "test_exp_api"})
    assert exp_resp.status_code == 200
    exp_data = exp_resp.json()
    assert exp_data["success"] is True
    assert exp_data["report"]["status"] in ("completed", "completed_with_warnings")


def test_api_export_benchmark_markdown_and_json(client):
    """Verify exporting benchmark report as Markdown and JSON."""
    bench_payload = {
        "benchmark_id": "test_export_bench",
        "plugin_ids": ["builtin.parametric_gaussian", "builtin.historical_simulation"],
        "metrics_to_compare": ["var_95"],
    }
    bench_resp = client.post("/api/benchmarks/execute", json=bench_payload)
    report_data = bench_resp.json()["report"]

    # Export as Markdown
    exp_md_resp = client.post("/api/export", json={"type": "benchmark", "format": "markdown", "report_data": report_data})
    assert exp_md_resp.status_code == 200
    assert "# FragilityShield — Model Benchmark Report" in exp_md_resp.text

    # Export as JSON
    exp_json_resp = client.post("/api/export", json={"type": "benchmark", "format": "json", "report_data": report_data})
    assert exp_json_resp.status_code == 200
    assert json.loads(exp_json_resp.text)["benchmark_id"] == "test_export_bench"
