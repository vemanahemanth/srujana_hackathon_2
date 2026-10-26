"""Automated Test Suite for Page 12: Integration & Plugin Studio.

Validates:
1. Live Connected Services Index:
   - Upstox V3 Market Data Feed
   - PostgreSQL Persistent Storage
   - Local Verified Market Catalog
   - Task Scheduler & Worker Daemon
2. Real Service Connectivity Testing Engine:
   - Upstox probe (token / fallback catalog)
   - PostgreSQL probe (live / in-memory ledger)
   - Local directory write & space verification
   - Webhook validation & format checks
3. Plugin Manifest Validation & Security Sandbox Boundaries:
   - Strict plugin_id regex validation
   - SemVer enforcement
   - Declarative capability isolation (ALLOWED_PLUGIN_CAPABILITIES)
   - Resource limit bounding (Memory <= 512MB, Timeout <= 30s, CPU <= 2.0)
   - Deterministic SHA-256 manifest contract digest
4. Custom Integration Registration & Persistence
5. Starlette REST API endpoints via TestClient
"""

import json
import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.plugin_studio import (
    get_connected_services_index,
    test_service_connectivity as probe_service_connectivity,
    validate_manifest_payload,
    register_custom_integration,
    list_all_integrations,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_connected_services_index():
    """Connected services index must return all 4 core platform dependencies with latencies."""
    services = get_connected_services_index()
    assert len(services) >= 4, "Must inspect Upstox, Postgres, Local Catalog, and Worker Daemon"
    
    ids = {s.service_id for s in services}
    assert "upstox_v3_market_data" in ids
    assert "postgresql_persistent_storage" in ids
    assert "local_data_catalog" in ids
    assert "isolated_worker_queue" in ids

    for s in services:
        assert s.latency_ms >= 0.0
        assert s.status in ("CONNECTED", "STANDBY", "DEGRADED", "DISCONNECTED")
        assert s.last_verified_at.endswith("Z")


def test_service_connectivity_probes():
    """Connectivity prober must execute real checks and report diagnostic information."""
    # 1. Local catalog probe
    res_catalog = probe_service_connectivity("local_data_catalog")
    assert res_catalog.success is True
    assert res_catalog.latency_ms >= 0.0
    assert "directory" in res_catalog.diagnostic_info

    # 2. Upstox probe
    res_upstox = probe_service_connectivity("upstox_v3_market_data")
    assert res_upstox.success is True
    assert res_upstox.latency_ms >= 0.0

    # 3. PostgreSQL probe
    res_pg = probe_service_connectivity("postgresql_persistent_storage")
    assert res_pg.success is True
    assert res_pg.latency_ms >= 0.0

    # 4. Invalid webhook
    res_webhook_bad = probe_service_connectivity("slack_alert_webhook", {"webhook_url": "ftp://bad-url"})
    assert res_webhook_bad.success is False
    assert res_webhook_bad.status_code == 400


def test_valid_plugin_manifest_validation():
    """Valid plugin manifest must be accepted and produce deterministic SHA-256 digest."""
    manifest = {
        "plugin_id": "quant_momentum_alpha",
        "name": "Cross-Sectional Momentum Alpha",
        "version": "1.2.0",
        "entry_point": "models.momentum:compute_alpha",
        "publisher": "Acme Capital",
        "description": "Computes 12-month minus 1-month cross-sectional price momentum.",
        "requested_capabilities": ["dataset:read", "result:return"],
        "resource_limits": {
            "max_memory_mb": 128,
            "timeout_seconds": 4.5,
            "max_cpu_cores": 1.0,
        },
    }

    result = validate_manifest_payload(manifest)
    assert result["is_valid"] is True
    assert len(result["errors"]) == 0
    summary = result["manifest_summary"]
    assert summary["plugin_id"] == "quant_momentum_alpha"
    assert len(summary["hash_digest"]) == 64  # SHA-256


def test_manifest_validation_rejects_unauthorized_capabilities():
    """Security boundary: Manifest requesting unauthorized capabilities must fail closed."""
    manifest = {
        "plugin_id": "malicious_network_scanner",
        "name": "Network Infiltrator",
        "version": "1.0.0",
        "entry_point": "exploit.py:run",
        "requested_capabilities": ["dataset:read", "raw_socket:unrestricted", "os:exec_root"],
    }

    result = validate_manifest_payload(manifest)
    assert result["is_valid"] is False
    assert any("Unauthorized capabilities" in err for err in result["errors"])


def test_manifest_validation_rejects_excessive_resource_limits():
    """Security boundary: Manifest requesting out-of-bounds resources must be rejected."""
    manifest = {
        "plugin_id": "greedy_plugin",
        "name": "Greedy Memory Consumer",
        "version": "1.0.0",
        "entry_point": "greedy.py:run",
        "requested_capabilities": ["dataset:read"],
        "resource_limits": {
            "max_memory_mb": 2048,  # > 512 MB ceiling
            "timeout_seconds": 120.0,  # > 30s ceiling
            "max_cpu_cores": 8.0,  # > 2.0 ceiling
        },
    }

    result = validate_manifest_payload(manifest)
    assert result["is_valid"] is False
    assert any("exceeds maximum permitted threshold" in err for err in result["errors"])


def test_manifest_validation_rejects_invalid_identifiers():
    """Manifest with malformed ID or missing name must fail validation."""
    manifest = {
        "plugin_id": "bad id with spaces and $ymbols",
        "name": "",
        "version": "not-semver",
        "entry_point": "",
    }

    result = validate_manifest_payload(manifest)
    assert result["is_valid"] is False
    assert len(result["errors"]) >= 3


def test_register_and_list_custom_integration():
    """Custom integrations can be registered and retrieved from active catalog."""
    custom_data = {
        "integration_id": "custom_internal_pricing_feed",
        "name": "Internal Proprietary Fixed Income Pricer",
        "category": "Market Data Feeds",
        "version": "0.9.1",
        "provider": "Proprietary Desk",
        "description": "Yield curve interpolation and OAS pricer.",
        "capabilities": ["dataset:read", "result:return"],
        "required_credentials": ["DESK_API_KEY"],
        "is_sandboxed": True,
        "documentation_url": "https://internal.firm.net/docs/pricer",
    }

    reg = register_custom_integration(custom_data)
    assert reg["integration_id"] == "custom_internal_pricing_feed"
    assert reg["status"] == "CONFIGURED"

    all_items = list_all_integrations()
    found = [it for it in all_items if it.get("integration_id") == "custom_internal_pricing_feed"]
    assert len(found) == 1


def test_api_plugins_connected_services(client):
    """GET /api/plugins/connected-services returns real connected dependencies."""
    resp = client.get("/api/plugins/connected-services")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["services"]) >= 4


def test_api_plugins_catalog(client):
    """GET /api/plugins/catalog returns full institutional catalog."""
    resp = client.get("/api/plugins/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] >= 8


def test_api_plugins_test_connectivity(client):
    """POST /api/plugins/test-connectivity probes live service."""
    resp = client.post("/api/plugins/test-connectivity", json={"service_id": "local_data_catalog"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["result"]["success"] is True
    assert data["result"]["latency_ms"] >= 0.0


def test_api_plugins_validate_manifest(client):
    """POST /api/plugins/validate-manifest validates JSON manifest payload."""
    valid_payload = {
        "plugin_id": "risk_var_plugin",
        "name": "Historical VaR Plug",
        "version": "2.0.0",
        "entry_point": "models.var:calc",
        "requested_capabilities": ["dataset:read", "result:return"],
    }
    resp = client.post("/api/plugins/validate-manifest", json=valid_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["validation"]["is_valid"] is True
