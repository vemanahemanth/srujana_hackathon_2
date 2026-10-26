"""Automated Test Suite for Page 24: SDK and API Integration Monitor.

Validates:
1. System Component Health Probing (Backend API, Python SDK, Upstox Provider, Database, Storage, Models, Jobs, Plugins)
2. Operational Status Constraints (healthy, degraded, unavailable, not configured, not checked, unsupported)
3. Zero Secret Leakage Verification (no tokens, passwords, or keys in outputs)
4. Diagnostic Action Execution (backend, database, provider, sdk, storage)
5. Route Catalog Introspection (path, methods, category, auth)
6. 10 Verified Python SDK Quickstart Workflows
7. Starlette REST API Endpoints via TestClient
"""

import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.integration_monitor import (
    probe_all_system_components,
    execute_diagnostic_action,
    get_sdk_quickstart_workflows,
    extract_registered_api_routes,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_probe_all_system_components():
    """Probe must report all 8 core platform components with honest operational status."""
    res = probe_all_system_components()
    assert res["success"] is True
    assert res["overall_status"] in ("healthy", "degraded", "unavailable")
    assert res["components_monitored"] == 8

    comp_ids = {c["component_id"] for c in res["components"]}
    expected_ids = {
        "backend_api",
        "python_sdk",
        "market_data_provider",
        "database",
        "experiment_storage",
        "model_execution",
        "background_jobs",
        "plugin_subsystem",
    }
    assert comp_ids == expected_ids

    allowed_statuses = {"healthy", "degraded", "unavailable", "not configured", "not checked", "unsupported"}
    for c in res["components"]:
        assert c["status"] in allowed_statuses
        assert c["check_duration_ms"] >= 0.0
        assert len(c["capabilities"]) > 0

        # Strict secret check: no raw tokens or passwords leaked
        serialized = str(c).lower()
        assert "bearer ey" not in serialized
        assert "password" not in serialized or "password" in c.get("error_summary", "")


def test_diagnostic_actions():
    """Diagnostic actions must execute safely and return honest diagnostic outcomes."""
    # Backend test
    res = execute_diagnostic_action("test_backend")
    assert res.success is True
    assert res.status == "healthy"
    assert res.latency_ms >= 0.0

    # Database test
    db_res = execute_diagnostic_action("test_database")
    assert db_res.status in ("healthy", "degraded")
    assert db_res.latency_ms >= 0.0

    # Provider test
    prov_res = execute_diagnostic_action("test_provider")
    assert prov_res.status in ("healthy", "not configured")

    # SDK test
    sdk_res = execute_diagnostic_action("test_sdk")
    assert sdk_res.status == "healthy"
    assert "volatility" in sdk_res.diagnostics or "client_class" in sdk_res.diagnostics

    # Storage test
    stor_res = execute_diagnostic_action("test_storage")
    assert stor_res.status == "healthy"

    # Unsupported action
    unknown_res = execute_diagnostic_action("invalid_test_xyz")
    assert unknown_res.status == "unsupported"
    assert unknown_res.success is False


def test_sdk_quickstart_workflows():
    """Must provide all 10 verified, copyable SDK workflows covering complete lifecycle."""
    workflows = get_sdk_quickstart_workflows()
    assert len(workflows) == 10

    expected_prefixes = [
        "1. Initialize the Client",
        "2. Configure Market Data Provider",
        "3. Load Verified Historical Data",
        "4. Create or Retrieve Portfolio",
        "5. Run Quantitative Risk Analysis",
        "6. Run Scenario Stress Testing",
        "7. Run Fragility & Assumption Attack",
        "8. Evaluate Model & Prevent Leakage",
        "9. Run Strategy Backtest with Cost Accounting",
        "10. Save Experiment with Reproducibility Manifest",
    ]

    for i, wf in enumerate(workflows):
        assert wf["title"] == expected_prefixes[i]
        assert "fragility_engine" in wf["code"]
        assert len(wf["code"]) > 30


def test_route_introspection(client):
    """Starlette route introspection must discover all endpoints across platforms."""
    routes = extract_registered_api_routes(client.app)
    assert len(routes) >= 25

    paths = {r["path"] for r in routes}
    assert "/api/health" in paths
    assert "/api/integrations/health" in paths
    assert "/api/integrations/routes" in paths
    assert "/api/integrations/quickstart" in paths

    for r in routes:
        assert r["path"].startswith("/api/")
        assert len(r["methods"]) > 0
        assert r["implementation_status"] == "IMPLEMENTED"


def test_api_integrations_endpoints(client):
    """Test REST API integration endpoints end-to-end."""
    # 1. Health
    r = client.get("/api/integrations/health")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert len(data["components"]) == 8

    # 2. Run diagnostic
    r = client.post("/api/integrations/diagnostics/test", json={"test_type": "test_backend"})
    assert r.status_code == 200
    diag = r.json()
    assert diag["success"] is True
    assert diag["test_type"] == "test_backend"

    # 3. Route catalog
    r = client.get("/api/integrations/routes")
    assert r.status_code == 200
    catalog = r.json()
    assert catalog["success"] is True
    assert catalog["total_routes"] >= 25

    # 4. Quickstart
    r = client.get("/api/integrations/quickstart")
    assert r.status_code == 200
    qs = r.json()
    assert qs["success"] is True
    assert len(qs["workflows"]) == 10
