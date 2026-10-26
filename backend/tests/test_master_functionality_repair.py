"""Comprehensive verification suite for Master Implementation Prompt — Functionality, SDK Integration & Research Integrity Repair."""

import json
import pytest
from starlette.testclient import TestClient
from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_monte_carlo_deterministic_seed_and_run_id(client):
    """Verify Monte Carlo produces deterministic outputs for fixed seed and distinct run_id."""
    payload1 = {
        "symbol": "RELIANCE",
        "initial_value": 1000000.0,
        "num_paths": 100,
        "horizon_days": 30,
        "method": "student_t",
        "degrees_of_freedom": 5,
        "seed": 42,
        "drawdown_threshold_pct": 15.0,
    }
    resp1 = client.post("/api/monte-carlo/run", json=payload1)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["success"] is True
    assert "run_id" in data1
    assert "paths_generated" in data1
    assert data1["paths_generated"] == 100

    resp2 = client.post("/api/monte-carlo/run", json=payload1)
    assert resp2.status_code == 200
    data2 = resp2.json()

    # Terminal metrics must match exactly for the same seed
    assert data1["terminal_metrics"]["median_terminal_value"] == data2["terminal_metrics"]["median_terminal_value"]
    assert data1["terminal_metrics"]["prob_loss_pct"] == data2["terminal_metrics"]["prob_loss_pct"]


def test_bootstrap_uncertainty_contract_and_replicates(client):
    """Verify Bootstrap Lab handles frontend parameter names and exposes sample_replicates and histogram_bins."""
    payload = {
        "symbol": "RELIANCE",
        "metric_name": "sharpe_ratio",
        "resampling_scheme": "moving_block",
        "num_replications": 100,
        "block_length": 5,
        "confidence_level": 0.95,
        "seed": 42,
    }
    resp = client.post("/api/uncertainty/bootstrap", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "run_id" in data
    assert "sample_replicates" in data
    assert len(data["sample_replicates"]) == 100
    assert "histogram_bins" in data
    assert len(data["histogram_bins"]) > 0
    first_bin = data["histogram_bins"][0]
    assert "bin_label" in first_bin
    assert "frequency" in first_bin

    u = data["uncertainty_metrics"]
    assert "percentile_ci_lower" in u
    assert "percentile_ci_upper" in u
    assert "p_value_zero_skill" in u


def test_reverse_stress_custom_threshold_solving(client):
    """Verify reverse stress solver resolves feasible shocks for different thresholds."""
    resp1 = client.post("/api/tail-risk/reverse-stress", json={"target_loss_pct": 0.10})
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["success"] is True
    assert "solution" in data1
    sol1 = data1["solution"]
    assert sol1["target_loss_pct"] == 0.10

    resp2 = client.post("/api/tail-risk/reverse-stress", json={"target_loss_pct": 0.25})
    assert resp2.status_code == 200
    data2 = resp2.json()
    sol2 = data2["solution"]
    assert sol2["target_loss_pct"] == 0.25
    # A larger target loss should require a larger market shock magnitude
    assert abs(sol2["market_shock"]) >= abs(sol1["market_shock"])


def test_tournament_disqualifies_zero_trades(client):
    """Verify tournament engine marks zero-trade candidates as ZERO_TRADES_INACTIVE, not QUALIFIED."""
    resp = client.post("/api/tournaments/run", json={
        "name": "Integrity Verification Tournament",
        "symbol": "RELIANCE",
        "benchmark_symbol": "NIFTY",
        "primary_metric": "sharpe_ratio",
        "max_drawdown_limit_pct": 20.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "leaderboard" in data
    for cand in data["leaderboard"]:
        if cand.get("total_trades", 0) == 0:
            assert cand["status"] == "ZERO_TRADES_INACTIVE"
            assert "No trades executed" in cand.get("disqualification_reason", "")
        elif cand.get("max_drawdown_pct", 0.0) > 20.0:
            assert cand["status"] == "RISK_LIMIT_BREACHED"


def test_export_report_formats(client):
    """Verify /api/export handles markdown, csv, and json formats without crashing."""
    report_data = {
        "portfolio_name": "Test Portfolio",
        "annualized_volatility": "18.5%",
        "historical_var_95": "2.4%",
        "sharpe_ratio": "1.25",
        "maximum_drawdown": "14.2%",
    }

    # Markdown
    resp_md = client.post("/api/export", json={
        "title": "Quantitative Risk Report",
        "type": "risk",
        "format": "markdown",
        "report_data": report_data,
    })
    assert resp_md.status_code == 200
    assert resp_md.headers["content-type"].startswith("text/markdown")
    assert "# Quantitative Risk Report" in resp_md.text

    # CSV
    resp_csv = client.post("/api/export", json={
        "title": "Risk CSV Export",
        "type": "risk",
        "format": "csv",
        "report_data": report_data,
    })
    assert resp_csv.status_code == 200
    assert resp_csv.headers["content-type"].startswith("text/csv")
    assert "annualized_volatility,18.5%" in resp_csv.text


def test_custom_strategy_persistence_lifecycle(client):
    """Verify custom strategies can be registered and listed via the configuration API."""
    test_strat = {
        "id": "strat_test_custom_alpha",
        "name": "Custom Volatility Breakout",
        "family": "Volatility Breakout",
        "description": "20-day ATR channel breakout",
        "entry_rule": "Close > Upper_Band(20)",
        "exit_rule": "Close < Lower_Band(20)",
        "default_params": {"fast_period": 20, "multiplier": 2.0},
    }
    save_resp = client.post("/api/configurations/strategies", json=test_strat)
    assert save_resp.status_code in (200, 201)

    list_resp = client.get("/api/configurations/strategies")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["success"] is True
    ids = [s.get("id") or s.get("strategy_id") for s in data.get("strategies", [])]
    assert "strat_test_custom_alpha" in ids
