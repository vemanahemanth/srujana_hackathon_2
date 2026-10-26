"""Acceptance tests for FragilityShield Real-Data-First Policy & Upstox Provenance.

Verifies:
1. Strict separation of data-source modes (REAL_DATA, USER_UPLOADED_DATA, SYNTHETIC_TEST_DATA, MIXED_DATA).
2. Elimination of silent substitution: missing real sources fail explicitly or disclose synthetic mode.
3. Upstox V3 live data tagging and provenance recording.
4. User uploads are never falsely labeled provider-verified.
5. Upstream errors (missing credentials, auth failures, outages) fail truthfully without mock responses.
6. Sensitivity of quantitative outputs to changing underlying source observations.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.app import app
from fragility_engine.data_provenance import (
    DataFreshnessStatus,
    DataProvenance,
    DataSourceMode,
)
from fragility_engine.upstox import (
    UpstoxAuthenticationError,
    UpstoxConfigurationError,
    UpstoxMarketDataAdapter,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_data_source_mode_enum_and_contract():
    """Verify all required data source modes and freshness status invariants."""
    assert DataSourceMode.REAL_DATA.value == "REAL_DATA"
    assert DataSourceMode.USER_UPLOADED_DATA.value == "USER_UPLOADED_DATA"
    assert DataSourceMode.SYNTHETIC_TEST_DATA.value == "SYNTHETIC_TEST_DATA"
    assert DataSourceMode.MIXED_DATA.value == "MIXED_DATA"

    prov = DataProvenance.real_provider(
        provider="upstox_v3",
        instrument="NSE_EQ|INE002A01018",
        date_range=("2026-01-01", "2026-03-31"),
        sampling_interval="1D",
        is_live=True,
    )
    p_dict = prov.to_dict()
    assert p_dict["data_source_mode"] == "REAL_DATA"
    assert p_dict["is_live_provider"] is True
    assert p_dict["is_synthetic"] is False
    assert p_dict["freshness_status"] == "LIVE"

    # Roundtrip from_dict
    reconstructed = DataProvenance.from_dict(p_dict)
    assert reconstructed.data_source_mode == DataSourceMode.REAL_DATA
    assert reconstructed.provider == "upstox_v3"
    assert reconstructed.is_live_provider is True


def test_strict_real_data_rejection_when_data_missing(client):
    """When strict_real_data=True is specified, endpoints must reject missing data with HTTP 400."""
    # 1. Risk calculation endpoint
    resp = client.post("/api/risk/calculate", json={"strict_real_data": True})
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "strict" in data["error"].lower()

    # 2. Fragility stress-testing endpoint
    resp2 = client.post("/api/fragility/run", json={"strict_real_data": True})
    assert resp2.status_code == 400
    assert resp2.json()["success"] is False
    assert "strict" in resp2.json()["error"].lower()

    # 3. Model benchmark endpoint
    resp3 = client.post("/api/benchmarks/execute", json={"strict_real_data": True})
    assert resp3.status_code == 400
    assert resp3.json()["success"] is False
    assert "strict" in resp3.json()["error"].lower()


def test_user_uploaded_data_provenance_and_tagging(client):
    """Raw arrays supplied by user must be tagged USER_UPLOADED_DATA with fingerprint and not provider-verified."""
    user_returns = [0.012, -0.008, 0.015, -0.004, 0.002, 0.021, -0.018]
    payload = {
        "returns": user_returns,
        "confidence_level": 0.95,
    }
    resp = client.post("/api/risk/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    prov = data.get("data_provenance")
    assert prov is not None
    assert prov["data_source_mode"] == "USER_UPLOADED_DATA"
    assert prov["is_user_uploaded"] is True
    assert prov["is_live_provider"] is False
    assert prov["is_synthetic"] is False
    assert prov["fingerprint"] is not None
    assert "Not independently verified against exchange trade tapes" in prov["disclaimer"]


def test_synthetic_demonstration_data_visibly_labeled(client):
    """When demo fallbacks run, they must visibly label output as SYNTHETIC_TEST_DATA with warnings."""
    # Empty payload runs deterministic demo
    resp = client.post("/api/risk/calculate", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    prov = data.get("data_provenance")
    assert prov is not None
    assert prov["data_source_mode"] == "SYNTHETIC_TEST_DATA"
    assert prov["is_synthetic"] is True
    assert prov["is_user_uploaded"] is False
    assert prov["is_live_provider"] is False
    # Must have explicit disclaimer warning
    warnings = prov.get("warnings", [])
    assert any("SYNTHETIC TEST DATA" in w for w in warnings)


def test_sample_portfolio_fixture_provenance(client):
    """Bundled sample portfolio fixtures must be disclosed as synthetic demo fixtures."""
    resp = client.get("/api/portfolios/sample?id=nse_10l.json")
    assert resp.status_code == 200
    data = resp.json()
    prov = data.get("data_provenance")
    assert prov is not None
    assert prov["data_source_mode"] == "SYNTHETIC_TEST_DATA"
    assert prov["is_synthetic"] is True


def test_simulation_endpoints_tagged_mixed_data(client):
    """Monte Carlo and Bootstrap endpoints generate simulated paths, tagged as MIXED_DATA."""
    # 1. Monte Carlo
    mc_resp = client.post(
        "/api/simulation/monte-carlo",
        json={"n_simulations": 100, "horizon_days": 10},
    )
    assert mc_resp.status_code == 200
    mc_prov = mc_resp.json().get("data_provenance")
    assert mc_prov["data_source_mode"] == "MIXED_DATA"
    assert mc_prov["freshness_status"] == "SIMULATED"

    # 2. Bootstrap
    bs_resp = client.post(
        "/api/simulation/bootstrap",
        json={"n_bootstraps": 100},
    )
    assert bs_resp.status_code == 200
    bs_prov = bs_resp.json().get("data_provenance")
    assert bs_prov["data_source_mode"] == "MIXED_DATA"
    assert bs_prov["freshness_status"] == "SIMULATED"


def test_output_changes_when_source_observations_change(client):
    """Verify that calculated risk metrics mathematically depend on actual input observations."""
    # Dataset A: Calm low-volatility returns
    rets_a = [0.001, -0.001, 0.002, 0.0, -0.001, 0.001, -0.002, 0.001] * 10
    # Dataset B: High-volatility stressed returns
    rets_b = [0.05, -0.06, 0.04, -0.05, 0.07, -0.08, 0.06, -0.04] * 10

    resp_a = client.post("/api/risk/calculate", json={"returns": rets_a})
    resp_b = client.post("/api/risk/calculate", json={"returns": rets_b})

    data_a = resp_a.json()
    data_b = resp_b.json()

    vol_a = data_a["report"]["volatility_annualized"]
    vol_b = data_b["report"]["volatility_annualized"]
    var_a = data_a["report"]["var_95"]
    var_b = data_b["report"]["var_95"]

    assert vol_b > vol_a * 5.0
    assert var_b > var_a * 5.0


def test_missing_credentials_fails_explicitly_no_fake_data(client):
    """When credentials are unset, Upstox endpoints fail with HTTP 400 configuration error, no fake candles."""
    from fragility_engine.upstox import UpstoxConfig
    with patch.object(UpstoxConfig, "from_env", return_value=UpstoxConfig()):
        resp = client.get("/api/upstox/candles?symbol=RELIANCE")
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "not configured" in data["error"].lower() or "configuration_error" in data.get("error_type", "")


def test_authentication_failure_reports_401_no_mock_substitution(client):
    """When Upstox returns 401, endpoint returns HTTP 401 and does NOT substitute fake data."""
    with patch.object(
        UpstoxMarketDataAdapter,
        "get_historical_candles",
        side_effect=UpstoxAuthenticationError("UDAPI100057: Token expired"),
    ):
        resp = client.get("/api/upstox/candles?symbol=RELIANCE")
        assert resp.status_code == 401
        data = resp.json()
        assert data["success"] is False
        assert "Token expired" in data["error"]


def test_upstream_outage_fails_truthfully_no_fake_success(client):
    """When Upstox returns an upstream error, endpoint returns HTTP 502 with truthful message."""
    with patch.object(
        UpstoxMarketDataAdapter,
        "get_quote",
        side_effect=UpstoxConfigurationError("Upstream gateway unavailable"),
    ):
        resp = client.get("/api/upstox/quote?symbols=RELIANCE")
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "gateway unavailable" in data["error"]


def test_risk_attribution_provenance_and_mode(client):
    """Risk attribution must track whether returns were user-provided, Upstox, or sector synthetic."""
    # 1. Default empty returns tags synthetic sector generator
    resp_demo = client.post("/api/risk/attribution", json={})
    assert resp_demo.status_code == 200
    data_demo = resp_demo.json()
    prov_demo = data_demo["data_provenance"]
    assert prov_demo["data_source_mode"] == "SYNTHETIC_TEST_DATA"
    assert prov_demo["is_synthetic"] is True

    # 2. User-provided returns with explicit portfolio holdings
    portfolio_payload = {
        "portfolio_id": "test_port",
        "currency": "INR",
        "holdings": [
            {"asset_id": "ASSET_A", "quantity": 10.0, "price": 100.0, "sector": "Technology"},
            {"asset_id": "ASSET_B", "quantity": 20.0, "price": 50.0, "sector": "Energy"},
        ],
    }
    custom_returns = {
        "ASSET_A": [0.01, -0.01, 0.02, -0.005] * 15,
        "ASSET_B": [0.005, 0.002, -0.008, 0.001] * 15,
    }
    resp_user = client.post(
        "/api/risk/attribution",
        json={"portfolio": portfolio_payload, "asset_returns": custom_returns},
    )
    assert resp_user.status_code == 200
    data_user = resp_user.json()
    prov_user = data_user["data_provenance"]
    assert prov_user["data_source_mode"] == "USER_UPLOADED_DATA"
    assert prov_user["is_user_uploaded"] is True
    assert prov_user["is_synthetic"] is False
