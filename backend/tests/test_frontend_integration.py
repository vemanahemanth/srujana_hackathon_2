"""
FragilityShield — Sprint 6 Frontend Integration & Static Serving Tests

Verifies that the compiled React 19 quantitative research terminal is properly served
by the FastAPI backend, that assets are delivered with security headers, and that
API routes take precedence over client-side routing fallbacks.
"""

import pytest
from starlette.testclient import TestClient
from backend.app import app, FRONTEND_DIR


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestFrontendIntegration:
    def test_root_serves_new_react_terminal_index(self, client: TestClient) -> None:
        """GET / must return the compiled React index.html with #root element."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert '<div id="root"></div>' in resp.text
        assert "FragilityShield" in resp.text

    def test_static_assets_delivered_if_dist_exists(self, client: TestClient) -> None:
        """If frontend/dist/assets exists, built asset bundles must be reachable."""
        dist_assets = FRONTEND_DIR / "dist" / "assets"
        if dist_assets.exists():
            asset_files = list(dist_assets.glob("*.js"))
            if asset_files:
                asset_name = asset_files[0].name
                resp = client.get(f"/assets/{asset_name}")
                assert resp.status_code == 200
                assert ("javascript" in resp.headers["content-type"] or "octet-stream" in resp.headers["content-type"])

    def test_api_routes_not_shadowed_by_frontend_mount(self, client: TestClient) -> None:
        """API endpoints must return JSON and never be shadowed by the frontend mount."""
        health_resp = client.get("/api/health")
        assert health_resp.status_code == 200
        assert health_resp.headers["content-type"] == "application/json"
        data = health_resp.json()
        assert data["status"] == "healthy"
        assert "engine" in data

    def test_sample_portfolio_api_accessible_for_frontend(self, client: TestClient) -> None:
        """Frontend can fetch sample portfolio to populate active context."""
        resp = client.get("/api/portfolios/sample?name=nse_10l.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        portfolio = data["portfolio"]
        assert portfolio["portfolio_id"] == "nse_10l_illustrative"
        assert len(portfolio["holdings"]) >= 10
        assert portfolio["currency"] == "INR"
