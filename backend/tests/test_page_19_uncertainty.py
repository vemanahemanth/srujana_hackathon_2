"""Tests for FragilityShield Page 19: Bootstrap & Uncertainty Lab."""

import numpy as np
import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.uncertainty_engine import (
    BootstrapLabConfig,
    run_bootstrap_uncertainty_analysis,
    compute_block_length_sensitivity_scan,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_page_19_resampling_schemes():
    """Test all 4 resampling schemes and multiple confidence interval types."""
    rng = np.random.default_rng(42)
    rets = rng.normal(loc=0.0008, scale=0.018, size=120)

    for method in ["moving_block_bootstrap", "iid_bootstrap", "circular_block_bootstrap", "stationary_bootstrap"]:
        cfg = BootstrapLabConfig(
            metric="sharpe_ratio",
            resampling_method=method,
            num_resamples=100,
            confidence_level=0.95,
            block_length=5,
            seed=42,
        )
        res = run_bootstrap_uncertainty_analysis(rets, cfg)
        assert res["success"] is True
        assert "point_estimate" in res
        u = res["uncertainty_metrics"]
        assert "percentile_interval" in u
        assert "basic_interval" in u
        assert "normal_approx_interval" in u
        assert u["percentile_interval"]["lower"] <= u["percentile_interval"]["upper"]
        assert len(res["distribution_histogram"]) == 25


def test_page_19_block_length_sensitivity():
    """Test sensitivity scan across block lengths."""
    rng = np.random.default_rng(99)
    rets = rng.normal(loc=0.0004, scale=0.015, size=100)

    scan = compute_block_length_sensitivity_scan(
        returns=rets,
        metric="sharpe_ratio",
        block_lengths=[1, 5, 10],
        num_resamples=50,
    )
    assert len(scan) == 3
    assert scan[0]["block_length"] == 1
    assert scan[1]["block_length"] == 5
    assert scan[2]["block_length"] == 10
    assert all("ci_width" in item for item in scan)


def test_page_19_api_endpoints(client):
    """Test REST endpoints for Bootstrap & Uncertainty Lab."""
    # 1. Bootstrap
    res_b = client.post("/api/uncertainty/bootstrap", json={
        "symbol": "RELIANCE",
        "metric": "sharpe_ratio",
        "resampling_method": "moving_block_bootstrap",
        "num_resamples": 80,
        "block_length": 5,
    })
    assert res_b.status_code == 200
    data = res_b.json()
    assert data["success"] is True
    assert "uncertainty_metrics" in data

    # 2. Block sensitivity
    res_s = client.post("/api/uncertainty/block-sensitivity", json={
        "symbol": "RELIANCE",
        "metric": "sharpe_ratio",
        "resampling_method": "moving_block_bootstrap",
    })
    assert res_s.status_code == 200
    assert len(res_s.json()["sensitivity_scan"]) >= 3
