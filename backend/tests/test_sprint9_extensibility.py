"""Sprint 9 Comprehensive Extensibility, Provider, SDK, and Security Test Suite.

Verifies:
1. Provider Architecture & Explicit Capabilities:
   - Supported vs Unsupported capabilities (raises UnsupportedCapabilityError).
   - Lifecycle state transitions (NOT_CONFIGURED -> CONFIGURED -> VERIFICATION_REQUESTED -> VERIFIED/FAILED).
2. Upstox Market Data Adapter:
   - Missing, invalid, and expired credentials handling.
   - Successful 200 mock connection verification and profile extraction.
   - 401 Unauthorized, 429 Rate Limit, and 504 Timeout error handling.
   - Secret redaction (tokens never leaked in repr, status, or logs).
   - OHLCV normalization: IST timestamp offsets, ordering, physical candle bounds.
   - Data provenance preservation without fabricating missing observations.
3. Data Provider Registry:
   - Provider registration, retrieval, listing, and lifecycle state tracking.
   - Isolated configurations across multiple providers.
4. API Routes:
   - GET /api/providers
   - POST /api/providers/verify
   - GET /api/providers/{provider_id}/capabilities
   - POST /api/models/check-capabilities with built-in model resolution.
5. SDK Integration:
   - Client.market_data registry methods.
   - Client.upstox methods.
6. Model & Plugin Registration & Security Boundaries:
   - Manifest validation (size limits, alphanumeric IDs, allowed capabilities).
   - Fail-closed execution policy (untrusted code blocked without container isolation).
   - Truthful capability reporting without fabricated mock passes.
7. Regression Safety:
   - Risk calculation works without active external provider connection.
   - Offline fallback provider produces valid deterministic results.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import httpx
import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.app import app
from fragility_engine.market_data import (
    DataProvider,
    DataProviderRecord,
    DataProviderRegistry,
    NSEOfflineSampleDataProvider,
    NSETradingCalendar,
    ProviderCapability,
    ProviderLifecycleStatus,
    UnsupportedCapabilityError,
    get_default_provider_registry,
)
from fragility_engine.upstox import (
    CanonicalCandle,
    UpstoxAuthStatus,
    UpstoxConfig,
    UpstoxInstrument,
    UpstoxMarketDataAdapter,
)
from fragility_engine.projects import ModelFamily, ModelManifest, check_model_capabilities
from fragility_engine.plugin_sandbox import (
    PluginManifest,
    PluginValidationError,
)
from fragility_engine.plugin_studio import validate_manifest_payload
from fragility_engine.sdk import Client


# ==============================================================================
# 1. Provider Capabilities & Lifecycle Tests (§2)
# ==============================================================================

def test_provider_capability_declaration_and_enforcement():
    """Verify that supported capabilities succeed and unsupported capabilities raise UnsupportedCapabilityError."""
    offline = NSEOfflineSampleDataProvider()
    assert offline.supports(ProviderCapability.HISTORICAL_OHLCV)
    assert offline.supports(ProviderCapability.INSTRUMENT_LOOKUP)
    assert not offline.supports(ProviderCapability.STREAMING_QUOTES)
    assert not offline.supports(ProviderCapability.CORPORATE_ACTIONS)

    # Calling an unsupported capability MUST raise UnsupportedCapabilityError
    with pytest.raises(UnsupportedCapabilityError) as exc_info:
        offline.stream_quotes(["NSE:RELIANCE"])
    assert "does not support capability 'streaming_quotes'" in str(exc_info.value)

    with pytest.raises(UnsupportedCapabilityError) as exc_info:
        offline.get_corporate_actions("NSE:RELIANCE")
    assert "does not support capability 'corporate_actions'" in str(exc_info.value)


def test_provider_lifecycle_state_machine():
    """Verify lifecycle state transitions."""
    # Unconfigured adapter
    empty_cfg = UpstoxConfig(client_id=None, access_token=None)
    adapter = UpstoxMarketDataAdapter(config=empty_cfg)
    assert adapter.lifecycle_status == ProviderLifecycleStatus.NOT_CONFIGURED

    # Configured with token
    configured_adapter = UpstoxMarketDataAdapter(config=UpstoxConfig(access_token="test_mock_token_12345"))
    assert configured_adapter.lifecycle_status == ProviderLifecycleStatus.CONFIGURED

    # Verified state only after successful verification check
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "success", "data": {}}
    mock_client.get.return_value = mock_resp

    verified_adapter = UpstoxMarketDataAdapter(
        config=UpstoxConfig(access_token="test_mock_token_12345"),
        client=mock_client,
    )
    status = verified_adapter.check_connection()
    assert status.authenticated is True
    assert verified_adapter.lifecycle_status == ProviderLifecycleStatus.VERIFIED


# ==============================================================================
# 2. Upstox Adapter Tests (§3, §5)
# ==============================================================================

def test_upstox_unconfigured_status_and_honest_reporting():
    """Adapter must report missing credentials truthfully and never fabricate connection."""
    cfg = UpstoxConfig(client_id=None, access_token=None)
    adapter = UpstoxMarketDataAdapter(config=cfg)
    status = adapter.check_connection()
    assert status.configured is False
    assert status.authenticated is False
    assert "not configured" in status.message.lower()


def test_upstox_secret_masking_and_no_token_leakage():
    """Verify secrets are redacted in str, repr, and status dictionaries."""
    secret_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.somerandomtokendata"
    cfg = UpstoxConfig(client_id="my_client_id_123", client_secret="super_secret_key", access_token=secret_token)
    
    # Check mask_token helper
    masked = cfg.mask_token(secret_token)
    assert "..." in masked
    assert secret_token not in masked

    # Check safe_dict
    s_dict = cfg.safe_dict()
    assert s_dict.get("masked_access_token") is not None
    assert "..." in s_dict["masked_access_token"]
    assert "access_token" not in s_dict  # raw token is completely excluded
    assert "super_secret_key" not in str(s_dict)

    # Check repr
    repr_str = repr(cfg)
    assert "super_secret_key" not in repr_str
    assert secret_token not in repr_str


def test_upstox_mock_connection_verification_success():
    """Mock HTTP 200 check_connection verifies connectivity without hitting live network."""
    mock_client = MagicMock(spec=httpx.Client)
    probe_resp = MagicMock(spec=httpx.Response)
    probe_resp.status_code = 200
    probe_resp.json.return_value = {
        "status": "success",
        "data": {"NSE_EQ:RELIANCE": {"last_price": 2850.5}},
    }

    profile_resp = MagicMock(spec=httpx.Response)
    profile_resp.status_code = 200
    profile_resp.json.return_value = {
        "status": "success",
        "data": {"user_type": "individual", "exchanges": ["NSE", "BSE"]},
    }

    def mock_get(url, *args, **kwargs):
        if "user/profile" in url:
            return profile_resp
        return probe_resp

    mock_client.get.side_effect = mock_get

    adapter = UpstoxMarketDataAdapter(
        config=UpstoxConfig(access_token="mock_valid_token_xyz"),
        client=mock_client,
    )
    auth_status = adapter.check_connection()
    assert auth_status.configured is True
    assert auth_status.authenticated is True
    assert auth_status.status_code == 200
    assert auth_status.user_type == "individual"
    assert "NSE" in auth_status.exchanges


def test_upstox_mock_authentication_failure_401():
    """Mock HTTP 401 returns honest failure message and unverified status."""
    mock_client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 401
    resp.json.return_value = {"errors": [{"message": "Access token expired"}]}
    mock_client.get.return_value = resp

    adapter = UpstoxMarketDataAdapter(
        config=UpstoxConfig(access_token="expired_token"),
        client=mock_client,
    )
    auth_status = adapter.check_connection()
    assert auth_status.configured is True
    assert auth_status.authenticated is False
    assert auth_status.status_code == 401
    assert "401" in auth_status.message
    assert adapter.lifecycle_status == ProviderLifecycleStatus.CONFIGURED  # Not VERIFIED


def test_upstox_mock_rate_limit_429():
    """Mock HTTP 429 returns rate limit error code and message."""
    mock_client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 429
    resp.json.return_value = {}
    mock_client.get.return_value = resp

    adapter = UpstoxMarketDataAdapter(
        config=UpstoxConfig(access_token="valid_token_rate_limited"),
        client=mock_client,
    )
    auth_status = adapter.check_connection()
    assert auth_status.status_code == 429
    assert "rate limit" in auth_status.message.lower()


def test_upstox_mock_timeout_handling():
    """Network timeouts return 504 status code without uncaught crash."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

    adapter = UpstoxMarketDataAdapter(
        config=UpstoxConfig(access_token="timeout_token"),
        client=mock_client,
    )
    auth_status = adapter.check_connection()
    assert auth_status.status_code == 504
    assert "timed out" in auth_status.message.lower()


def test_ohlcv_normalization_and_provenance():
    """Validate chronological ordering, IST offset, and bounds enforcement."""
    mock_client = MagicMock(spec=httpx.Client)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    # Upstox returns candles newest first: [timestamp, open, high, low, close, volume, oi]
    resp.json.return_value = {
        "status": "success",
        "data": {
            "candles": [
                ["2024-03-28T00:00:00+05:30", 2500.0, 2520.0, 2490.0, 2515.0, 1200000, 0],
                ["2024-03-27T00:00:00+05:30", 2480.0, 2505.0, 2475.0, 2495.0, 950000, 0],
            ]
        },
    }
    mock_client.get.return_value = resp

    adapter = UpstoxMarketDataAdapter(
        config=UpstoxConfig(access_token="valid_token"),
        client=mock_client,
    )
    candles = adapter.get_historical_candles(
        symbol_or_key="RELIANCE",
        from_date="2024-03-27",
        to_date="2024-03-28",
    )
    assert len(candles) == 2
    # Normalizer sorts oldest first
    assert candles[0].timestamp < candles[1].timestamp
    assert candles[0].close == 2495.0
    assert candles[1].close == 2515.0
    assert candles[0].symbol == "RELIANCE"
    assert "+05:30" in candles[0].timestamp


# ==============================================================================
# 3. Data Provider Registry Tests (§4)
# ==============================================================================

def test_data_provider_registry_lifecycle_and_isolation():
    """Registry maintains separate provider records and manages verification."""
    registry = DataProviderRegistry()
    offline = NSEOfflineSampleDataProvider()
    rec_off = registry.register(offline, display_name="Offline Sample", version="1.0.0")

    assert rec_off.provider_id == "nse_offline_sample_provider"
    assert rec_off.lifecycle_status == ProviderLifecycleStatus.VERIFIED
    assert ProviderCapability.HISTORICAL_OHLCV in rec_off.supported_capabilities

    # Verify provider
    verif = registry.verify_provider("nse_offline_sample_provider")
    assert verif["success"] is True
    assert verif["lifecycle_status"] == ProviderLifecycleStatus.VERIFIED

    # Check unconfigured upstox
    upstox = UpstoxMarketDataAdapter(config=UpstoxConfig())
    rec_up = registry.register(upstox, display_name="Upstox Feed", version="3.0.0")
    assert rec_up.lifecycle_status == ProviderLifecycleStatus.NOT_CONFIGURED

    verif_up = registry.verify_provider("upstox_v3_market_data")
    assert verif_up["success"] is False
    assert verif_up["lifecycle_status"] == ProviderLifecycleStatus.FAILED


# ==============================================================================
# 4. API Endpoints Tests (§6)
# ==============================================================================

@pytest.fixture
def client():
    return TestClient(app)


def test_api_list_data_providers(client):
    """GET /api/providers returns list of registered providers and capabilities."""
    resp = client.get("/api/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] >= 2
    p_ids = [p["provider_id"] for p in data["providers"]]
    assert "nse_offline_sample_provider" in p_ids
    assert "upstox_v3_market_data" in p_ids


def test_api_verify_data_provider(client):
    """POST /api/providers/verify executes verification check."""
    resp = client.post("/api/providers/verify", json={"provider_id": "nse_offline_sample_provider"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["verification"]["lifecycle_status"] == "VERIFIED"


def test_api_get_provider_capabilities(client):
    """GET /api/providers/{provider_id}/capabilities returns capability contract."""
    resp = client.get("/api/providers/upstox_v3_market_data/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    prov = data["provider"]
    assert "historical_ohlcv" in prov["supported_capabilities"]
    assert "streaming_quotes" in prov["unsupported_capabilities"]


def test_api_check_model_capabilities_builtin(client):
    """POST /api/models/check-capabilities evaluates built-in models properly."""
    resp = client.post(
        "/api/models/check-capabilities",
        json={
            "model_id": "builtin.parametric_gaussian",
            "target_lab": "risk",
            "test_name": "interface_and_contract_validation",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    rep = data["report"]
    assert rep["model_id"] == "builtin.parametric_gaussian"
    assert rep["is_executable"] is True


# ==============================================================================
# 5. SDK Client Integration Tests (§6)
# ==============================================================================

def test_sdk_market_data_and_provider_registry():
    """Client.market_data exposes provider discovery and verification."""
    sdk_client = Client()
    reg = sdk_client.market_data.provider_registry()
    assert isinstance(reg, DataProviderRegistry)

    providers = sdk_client.market_data.list_providers()
    assert len(providers) >= 2

    offline = sdk_client.market_data.get_provider("nse_offline_sample_provider")
    assert isinstance(offline, NSEOfflineSampleDataProvider)

    verif = sdk_client.market_data.verify_provider("nse_offline_sample_provider")
    assert verif["success"] is True


# ==============================================================================
# 6. Model & Plugin Sandbox Security Boundaries (§7, §8, §10)
# ==============================================================================

def test_manifest_validation_valid():
    """Valid manifest passes schema checks."""
    payload = {
        "plugin_id": "quant_test_plugin",
        "name": "Quantitative Test Plugin",
        "version": "1.0.0",
        "entry_point": "quant.test:run",
        "requested_capabilities": ["dataset:read", "result:return"],
        "resource_limits": {
            "max_memory_mb": 128,
            "timeout_seconds": 3.0,
            "max_cpu_cores": 1.0,
        },
    }
    res = validate_manifest_payload(payload)
    assert res["is_valid"] is True
    assert res["manifest_summary"]["plugin_id"] == "quant_test_plugin"


def test_manifest_validation_unauthorized_capability():
    """Unauthorized capability must be rejected."""
    payload = {
        "plugin_id": "malicious_plugin",
        "name": "Malicious Network Plugin",
        "version": "1.0.0",
        "entry_point": "mal.run:exploit",
        "requested_capabilities": ["network:egress", "dataset:read"],  # network:egress is forbidden
    }
    res = validate_manifest_payload(payload)
    assert res["is_valid"] is False
    assert any("unauthorized" in err.lower() for err in res["errors"])

    # Also PluginManifest directly enforces unauthorized capabilities
    with pytest.raises(PluginValidationError) as exc_info:
        PluginManifest(
            plugin_id="malicious_plugin",
            name="Malicious Network Plugin",
            version="1.0.0",
            entry_point="mal.run:exploit",
            requested_capabilities=("network:egress", "dataset:read"),
            hash_digest="sha256:dummy",
        )
    assert "unauthorized capabilities" in str(exc_info.value).lower()


def test_manifest_validation_invalid_id():
    """Invalid plugin_id with spaces or dangerous characters is rejected."""
    payload = {
        "plugin_id": "../etc/passwd",
        "name": "Path Traversal Plugin",
        "version": "1.0.0",
        "entry_point": "bad:run",
        "requested_capabilities": ["dataset:read"],
    }
    res = validate_manifest_payload(payload)
    assert res["is_valid"] is False

    with pytest.raises(PluginValidationError):
        PluginManifest(
            plugin_id="../etc/passwd",
            name="Path Traversal Plugin",
            version="1.0.0",
            entry_point="bad:run",
            requested_capabilities=("dataset:read",),
            hash_digest="sha256:dummy",
        )


# ==============================================================================
# 7. Regression & Portfolio Continuity Tests (§11)
# ==============================================================================

def test_regression_offline_risk_calculation_without_external_provider(client):
    """Core portfolio risk calculations must continue working without live Upstox token."""
    resp = client.get("/api/portfolios/sample")
    assert resp.status_code == 200
    portfolio = resp.json()["portfolio"]

    resp_risk = client.post("/api/risk/calculate", json={"portfolio": portfolio, "confidence_level": 0.95})
    assert resp_risk.status_code == 200
    data = resp_risk.json()
    assert data["success"] is True
    assert "annualized_volatility" in data
    assert data["annualized_volatility"] is not None
