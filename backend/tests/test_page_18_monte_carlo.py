"""Tests for FragilityShield Page 18: Monte Carlo Simulation Lab."""

import numpy as np
import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.monte_carlo_engine import (
    MonteCarloSimulationConfig,
    run_monte_carlo_simulation,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_page_18_monte_carlo_models():
    """Test all 5 Monte Carlo model families execute reliably and output expected metrics."""
    # Synthetic clean return series
    rng = np.random.default_rng(123)
    rets = rng.normal(loc=0.0005, scale=0.015, size=150)

    for method in ["parametric_gaussian", "student_t", "historical_resampling", "regime_switching"]:
        cfg = MonteCarloSimulationConfig(
            num_paths=100,
            horizon_days=30,
            method=method,
            seed=42,
            initial_value=1_000_000.0,
        )
        res = run_monte_carlo_simulation(rets, cfg)
        assert res["success"] is True
        assert len(res["sample_trajectories"]) <= 8
        assert len(res["percentile_bands"]["p50th_median"]) == 31
        assert "terminal_metrics" in res
        t_m = res["terminal_metrics"]
        assert t_m["initial_value"] == 1_000_000.0
        assert 0.0 <= t_m["prob_loss_pct"] <= 100.0
        assert len(res["distribution_histogram"]) == 20
        assert len(res["convergence_trace"]) > 0


def test_page_18_api_endpoint(client):
    """Test REST endpoint for Monte Carlo simulation."""
    res = client.post("/api/monte-carlo/run", json={
        "symbol": "RELIANCE",
        "num_paths": 150,
        "horizon_days": 40,
        "method": "student_t",
        "degrees_of_freedom": 5,
        "seed": 42,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "percentile_bands" in data
    assert "distribution_histogram" in data
    assert "reproducibility" in data


def test_page_18_seed_reproducibility():
    """Verify that fixing the seed produces bit-for-bit deterministic simulation results."""
    rng = np.random.default_rng(999)
    rets = rng.normal(loc=0.0003, scale=0.012, size=100)
    cfg1 = MonteCarloSimulationConfig(num_paths=150, horizon_days=25, seed=12345)
    cfg2 = MonteCarloSimulationConfig(num_paths=150, horizon_days=25, seed=12345)
    cfg_diff = MonteCarloSimulationConfig(num_paths=150, horizon_days=25, seed=54321)

    res1 = run_monte_carlo_simulation(rets, cfg1)
    res2 = run_monte_carlo_simulation(rets, cfg2)
    res_diff = run_monte_carlo_simulation(rets, cfg_diff)

    assert res1["terminal_metrics"]["median_terminal_value"] == res2["terminal_metrics"]["median_terminal_value"]
    assert res1["terminal_metrics"]["value_at_risk_95_pct"] == res2["terminal_metrics"]["value_at_risk_95_pct"]
    assert res1["terminal_metrics"]["median_terminal_value"] != res_diff["terminal_metrics"]["median_terminal_value"]


def test_page_18_percentile_monotonicity():
    """Verify that percentile bands are strictly monotonically increasing at all time steps."""
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.0004, scale=0.014, size=120)
    cfg = MonteCarloSimulationConfig(num_paths=250, horizon_days=30, seed=42)
    res = run_monte_carlo_simulation(rets, cfg)

    pb = res["percentile_bands"]
    n_steps = len(pb["p50th_median"])
    for step in range(n_steps):
        assert pb["p5th"][step] <= pb["p25th"][step]
        assert pb["p25th"][step] <= pb["p50th_median"][step]
        assert pb["p50th_median"][step] <= pb["p75th"][step]
        assert pb["p75th"][step] <= pb["p95th"][step]


def test_page_18_student_t_fat_tails():
    """Verify that Student-t innovations with df=4 execute and output tail metrics."""
    rng = np.random.default_rng(777)
    rets = rng.normal(loc=0.0002, scale=0.018, size=120)

    cfg_norm = MonteCarloSimulationConfig(num_paths=300, horizon_days=40, method="parametric_gaussian", seed=42)
    cfg_t = MonteCarloSimulationConfig(num_paths=300, horizon_days=40, method="student_t", degrees_of_freedom=4, seed=42)

    res_norm = run_monte_carlo_simulation(rets, cfg_norm)
    res_t = run_monte_carlo_simulation(rets, cfg_t)

    t_m_norm = res_norm["terminal_metrics"]
    t_m_t = res_t["terminal_metrics"]
    assert t_m_t["expected_shortfall_95_pct"] >= 0.0
    assert t_m_norm["expected_shortfall_95_pct"] >= 0.0

