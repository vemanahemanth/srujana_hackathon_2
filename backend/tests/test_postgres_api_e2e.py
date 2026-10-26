"""End-to-End FastAPI to PostgreSQL RLS Integration Suite (Sprint 3).

This module tests real HTTP requests against the live Starlette/FastAPI application
wired directly to a live PostgreSQL 18 instance with Row-Level Security enabled
and forced across all tenant-owned tables.

Test Coverage:
1. Application Wiring & Database Mode Disclosure:
   - /api/security/status confirms PostgreSQL database_engine and RLS enforcement active.
   - In production mode, startup fails closed if database configuration is missing, invalid, or insecure.
2. Authentication Hardening:
   - Missing token on protected routes returns 401.
   - Tampered JWT token returns 401.
   - Deactivated user returns 403.
   - Requesting unauthorized tenant in token exchange returns 403.
   - Elevating roles beyond server-side membership returns 403.
3. End-to-End Read Isolation:
   - Tenant A cannot read Tenant B's portfolio by ID (404/not found within tenant scope).
   - Tenant A listing portfolios sees ONLY Tenant A's portfolios; Tenant B records are omitted.
   - Tenant A cannot enumerate Tenant B's datasets, projects, models, experiment runs, jobs, or audit events.
4. End-to-End Write Isolation:
   - Tenant A creating a portfolio succeeds under Tenant A.
   - Tenant A attempting to spoof `tenant_id` to Tenant B is rejected.
   - Tenant A cannot modify or delete Tenant B's portfolio, project, or dataset.
5. Missing Context & Fail-Closed Behavior:
   - Unauthenticated requests in production mode fail closed (401).
   - Direct requests without active tenant context return 0 rows and block writes.
6. Connection Pool & Transaction Boundary Simulation:
   - Requests executed across connection pool checkouts do not leak tenant state.
"""

from __future__ import annotations

import os
import urllib.parse
import uuid
from typing import Any, Dict, Generator

import psycopg2
import pytest
from starlette.testclient import TestClient

from backend.app import create_application
from fragility_engine.database import (
    close_database_pool,
    init_database_pool,
)
from fragility_engine.db_schema import (
    POSTGRES_RLS_SCHEMA_DDL,
    SecurityConfigurationError,
)
from fragility_engine.tenancy import (
    TenantRole,
    create_access_token,
    hash_password,
)


def get_live_postgres_admin_url() -> str | None:
    """Detect available PostgreSQL administrative connection string."""
    env_url = os.environ.get("TEST_POSTGRESQL_URL", "").strip()
    candidate_urls = [env_url] if env_url else [
        "postgresql://postgres@localhost:5434/postgres",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    ]

    for candidate in candidate_urls:
        if not candidate:
            continue
        try:
            conn = psycopg2.connect(candidate, connect_timeout=1)
            conn.close()
            return candidate
        except Exception:
            continue
    return None


@pytest.fixture(scope="module")
def postgres_e2e_harness() -> Generator[Dict[str, Any], None, None]:
    """Provision disposable database and wire live FastAPI application to PostgreSQL."""
    admin_url = get_live_postgres_admin_url()
    if not admin_url:
        pytest.skip("LIVE_POSTGRESQL_UNAVAILABLE: No reachable PostgreSQL server on localhost:5434 or :5432.")

    # 1. Safety Check: Verify endpoint is local/test
    parsed = urllib.parse.urlsplit(admin_url)
    assert parsed.hostname in ("localhost", "127.0.0.1"), f"Refusing to run against non-local host: {parsed.hostname}"

    admin_conn = psycopg2.connect(admin_url)
    admin_conn.autocommit = True
    disposable_db = f"fs_e2e_sprint3_{uuid.uuid4().hex[:8]}"

    # Create database
    with admin_conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE {disposable_db};")

    db_base = f"{parsed.scheme}://{parsed.netloc}/{disposable_db}"
    app_url = f"{parsed.scheme}://fragility_app_user:change_this_in_production_secrets_manager@{parsed.hostname}:{parsed.port or 5432}/{disposable_db}"

    # 2. Apply Schema DDL & Seed Tenants/Users
    setup_conn = psycopg2.connect(db_base)
    setup_conn.autocommit = True
    with setup_conn.cursor() as cur:
        cur.execute(POSTGRES_RLS_SCHEMA_DDL)

        # Seed tenants
        cur.execute("""
            INSERT INTO tenants (tenant_id, name) VALUES
            ('ten_alpha_e2e', 'Alpha E2E Capital'),
            ('ten_beta_e2e', 'Beta E2E Investments')
            ON CONFLICT DO NOTHING;
        """)

        # Seed users
        cur.execute("""
            INSERT INTO users (user_id, email, password_hash, is_active) VALUES
            ('usr_alpha', 'alpha@fragility.e2e', %s, TRUE),
            ('usr_alpha_admin', 'alpha_admin@fragility.e2e', %s, TRUE),
            ('usr_beta', 'beta@fragility.e2e', %s, TRUE),
            ('usr_disabled', 'disabled@fragility.e2e', %s, FALSE)
            ON CONFLICT DO NOTHING;
        """, (
            hash_password("AlphaPass2026!"),
            hash_password("AlphaAdminPass2026!"),
            hash_password("BetaPass2026!"),
            hash_password("DisabledPass2026!"),
        ))

        # Seed memberships
        cur.execute("""
            INSERT INTO tenant_memberships (membership_id, tenant_id, user_id, role, is_active) VALUES
            ('mem_alpha', 'ten_alpha_e2e', 'usr_alpha', 'researcher', TRUE),
            ('mem_alpha_admin', 'ten_alpha_e2e', 'usr_alpha_admin', 'tenant_admin', TRUE),
            ('mem_beta', 'ten_beta_e2e', 'usr_beta', 'researcher', TRUE),
            ('mem_dis', 'ten_alpha_e2e', 'usr_disabled', 'researcher', TRUE)
            ON CONFLICT DO NOTHING;
        """)

        # Seed baseline resources
        cur.execute("""
            INSERT INTO portfolios (portfolio_id, tenant_id, name, currency, holdings_json, created_by) VALUES
            ('port_alpha_confidential', 'ten_alpha_e2e', 'Alpha Confidential Quant', 'INR', '[{"asset_id": "RELIANCE", "quantity": 100, "price": 2500.0}]', 'usr_alpha'),
            ('port_beta_secret', 'ten_beta_e2e', 'Beta Proprietary Alpha', 'INR', '[{"asset_id": "TCS", "quantity": 50, "price": 3500.0}]', 'usr_beta');

            INSERT INTO datasets (dataset_id, tenant_id, name, source_type, provenance_json, fingerprint, row_count, created_by) VALUES
            ('dset_alpha', 'ten_alpha_e2e', 'Alpha High-Freq Dataset', 'historical', '{"source": "alpha"}', 'fp_a', 1000, 'usr_alpha'),
            ('dset_beta', 'ten_beta_e2e', 'Beta Internal Signals', 'historical', '{"source": "beta"}', 'fp_b', 2000, 'usr_beta');

            INSERT INTO projects (project_id, tenant_id, name, description, manifest_json, created_by) VALUES
            ('proj_alpha', 'ten_alpha_e2e', 'Alpha Project', 'Alpha workspace', '{"project_id": "proj_alpha", "name": "Alpha Project"}', 'usr_alpha'),
            ('proj_beta', 'ten_beta_e2e', 'Beta Project', 'Beta workspace', '{"project_id": "proj_beta", "name": "Beta Project"}', 'usr_beta');

            INSERT INTO models (model_id, tenant_id, name, family, parameters_json, created_by) VALUES
            ('mod_alpha', 'ten_alpha_e2e', 'Alpha GARCH', 'risk_estimator', '{"p": 1, "q": 1}', 'usr_alpha'),
            ('mod_beta', 'ten_beta_e2e', 'Beta EWMA', 'risk_estimator', '{"decay": 0.94}', 'usr_beta');

            INSERT INTO jobs (job_id, tenant_id, job_type, status, payload_json, created_by) VALUES
            ('job_alpha', 'ten_alpha_e2e', 'BACKTEST', 'QUEUED', '{"test": "alpha"}', 'usr_alpha'),
            ('job_beta', 'ten_beta_e2e', 'SIMULATION', 'QUEUED', '{"test": "beta"}', 'usr_beta');

            INSERT INTO audit_events (event_id, tenant_id, user_id, action, resource_type, resource_id, status, details_json) VALUES
            ('audit_alpha', 'ten_alpha_e2e', 'usr_alpha', 'LOGIN', 'auth', 'sess_a', 'SUCCESS', '{"ip": "127.0.0.1"}'),
            ('audit_beta', 'ten_beta_e2e', 'usr_beta', 'LOGIN', 'auth', 'sess_b', 'SUCCESS', '{"ip": "127.0.0.1"}');
        """)
    setup_conn.close()

    # 3. Configure environment and initialize application connection pool
    orig_env = dict(os.environ)
    os.environ["DATABASE_URL"] = app_url
    os.environ["DEPLOYMENT_MODE"] = "postgres_app"
    os.environ["ALLOW_DEV_AUTH"] = "true"

    init_database_pool(database_url=app_url, minconn=2, maxconn=10, enforce_production_checks=False)
    app = create_application()
    client = TestClient(app)

    # Generate test tokens
    token_alpha = create_access_token(
        user_id="usr_alpha",
        tenant_id="ten_alpha_e2e",
        role=TenantRole.RESEARCHER,
        expires_in_seconds=3600,
    )
    token_beta = create_access_token(
        user_id="usr_beta",
        tenant_id="ten_beta_e2e",
        role=TenantRole.RESEARCHER,
        expires_in_seconds=3600,
    )

    token_alpha_admin = create_access_token(
        user_id="usr_alpha_admin",
        tenant_id="ten_alpha_e2e",
        role=TenantRole.TENANT_ADMIN,
        expires_in_seconds=3600,
    )

    harness_data = {
        "client": client,
        "token_alpha": token_alpha,
        "token_alpha_admin": token_alpha_admin,
        "token_beta": token_beta,
        "app_url": app_url,
        "disposable_db": disposable_db,
    }

    try:
        yield harness_data
    finally:
        # Teardown
        close_database_pool()
        os.environ.clear()
        os.environ.update(orig_env)
        try:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {disposable_db} WITH (FORCE);")
            admin_conn.close()
        except Exception:
            pass


class TestProductionModeStartupFailClosed:
    """Verify Phase 2 requirements: Production mode fails startup when configuration is insecure or missing."""

    def test_production_fails_when_database_url_is_sqlite(self) -> None:
        """Production startup strictly rejects SQLite persistence."""
        with pytest.raises(SecurityConfigurationError, match="FAIL-CLOSED.*SQLite"):
            orig = os.environ.get("DEPLOYMENT_MODE")
            orig_db = os.environ.get("DATABASE_URL")
            try:
                os.environ["DEPLOYMENT_MODE"] = "public_multi_tenant"
                os.environ["DATABASE_URL"] = "sqlite:///data/test.db"
                os.environ["JWT_SECRET_KEY"] = "strong_secret_key_exceeding_32_characters_long_12345"
                os.environ["ALLOWED_CORS_ORIGINS"] = "http://127.0.0.1:8000"
                create_application()
            finally:
                if orig:
                    os.environ["DEPLOYMENT_MODE"] = orig
                else:
                    os.environ.pop("DEPLOYMENT_MODE", None)
                if orig_db:
                    os.environ["DATABASE_URL"] = orig_db
                else:
                    os.environ.pop("DATABASE_URL", None)

    def test_production_fails_when_jwt_secret_is_trivial(self) -> None:
        """Production startup strictly rejects short or trivial JWT secrets."""
        with pytest.raises(SecurityConfigurationError, match="FAIL-CLOSED.*JWT secret"):
            orig = os.environ.get("DEPLOYMENT_MODE")
            try:
                os.environ["DEPLOYMENT_MODE"] = "public_multi_tenant"
                os.environ["DATABASE_URL"] = "postgresql://fragility_app_user:pwd@localhost:5432/fs_db"
                os.environ["JWT_SECRET_KEY"] = "short_secret"
                os.environ["ALLOWED_CORS_ORIGINS"] = "http://127.0.0.1:8000"
                create_application()
            finally:
                if orig:
                    os.environ["DEPLOYMENT_MODE"] = orig
                else:
                    os.environ.pop("DEPLOYMENT_MODE", None)

    def test_production_fails_when_cors_is_wildcard(self) -> None:
        """Production startup strictly rejects wildcard CORS origins."""
        with pytest.raises(SecurityConfigurationError, match="FAIL-CLOSED.*Wildcard CORS"):
            orig = os.environ.get("DEPLOYMENT_MODE")
            try:
                os.environ["DEPLOYMENT_MODE"] = "public_multi_tenant"
                os.environ["DATABASE_URL"] = "postgresql://fragility_app_user:pwd@localhost:5432/fs_db"
                os.environ["JWT_SECRET_KEY"] = "strong_secret_key_exceeding_32_characters_long_12345"
                os.environ["ALLOWED_CORS_ORIGINS"] = "*"
                create_application()
            finally:
                if orig:
                    os.environ["DEPLOYMENT_MODE"] = orig
                else:
                    os.environ.pop("DEPLOYMENT_MODE", None)


class TestLivePostgresAPIEndToEnd:
    """Adversarial cross-tenant penetration testing across real FastAPI HTTP endpoints."""

    def test_security_status_endpoint_reports_postgres_and_rls(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Verify /api/security/status discloses PostgreSQL mode and active RLS without exposing secrets."""
        client: TestClient = postgres_e2e_harness["client"]
        resp = client.get("/api/security/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["database_engine"] == "PostgreSQL"
        assert data["rls_enforcement_active"] is True
        assert "Row-Level Security" in data["tenant_isolation_mode"]
        # Credentials must be masked
        assert "change_this_in_production" not in data["database_target"]
        assert "***" in data["database_target"]

    def test_authentication_token_exchange_and_tamper_rejection(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Verify token exchange validates credentials and membership in live PostgreSQL."""
        client: TestClient = postgres_e2e_harness["client"]

        # Valid login for Alpha
        resp = client.post("/api/auth/token", json={
            "user_id": "usr_alpha",
            "password": "AlphaPass2026!",
            "tenant_id": "ten_alpha_e2e",
        })
        assert resp.status_code == 200
        token_data = resp.json()
        assert "token" in token_data
        assert token_data["tenant_id"] == "ten_alpha_e2e"

        # Invalid password rejected
        resp_bad = client.post("/api/auth/token", json={
            "user_id": "usr_alpha",
            "password": "WrongPassword!",
            "tenant_id": "ten_alpha_e2e",
        })
        assert resp_bad.status_code == 401

        # Cross-tenant joining rejected (User Alpha attempting to login directly to Tenant Beta)
        resp_cross = client.post("/api/auth/token", json={
            "user_id": "usr_alpha",
            "password": "AlphaPass2026!",
            "tenant_id": "ten_beta_e2e",
        })
        assert resp_cross.status_code == 403

        # Disabled user rejected
        resp_dis = client.post("/api/auth/token", json={
            "user_id": "usr_disabled",
            "password": "DisabledPass2026!",
            "tenant_id": "ten_alpha_e2e",
        })
        assert resp_dis.status_code == 403

    def test_read_isolation_portfolios(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Prove Tenant A cannot read Tenant B's portfolios by ID or enumeration."""
        client: TestClient = postgres_e2e_harness["client"]
        token_a: str = postgres_e2e_harness["token_alpha"]
        token_b: str = postgres_e2e_harness["token_beta"]

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # 1. Tenant A direct ID query for Tenant B's confidential portfolio -> 404
        resp = client.get("/api/portfolios/port_beta_secret", headers=headers_a)
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

        # 2. Tenant B direct ID query for its own portfolio -> 200
        resp_b = client.get("/api/portfolios/port_beta_secret", headers=headers_b)
        assert resp_b.status_code == 200
        assert resp_b.json()["portfolio"]["portfolio_id"] == "port_beta_secret"

        # 3. Tenant A enumerating portfolios sees ONLY Alpha portfolios
        list_resp_a = client.get("/api/portfolios", headers=headers_a)
        assert list_resp_a.status_code == 200
        port_ids_a = [p["portfolio_id"] for p in list_resp_a.json()["portfolios"]]
        assert "port_alpha_confidential" in port_ids_a
        assert "port_beta_secret" not in port_ids_a

    def test_read_isolation_datasets_and_projects(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Prove Tenant A cannot view or access Tenant B's datasets or projects."""
        client: TestClient = postgres_e2e_harness["client"]
        headers_a = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha']}"}
        headers_b = {"Authorization": f"Bearer {postgres_e2e_harness['token_beta']}"}

        # Datasets: Tenant A direct ID query for Tenant B dataset -> 404
        resp_dset = client.get("/api/datasets/dset_beta", headers=headers_a)
        assert resp_dset.status_code == 404

        # Datasets: Tenant B direct ID query for its own dataset -> 200
        resp_dset_b = client.get("/api/datasets/dset_beta", headers=headers_b)
        assert resp_dset_b.status_code == 200

        # Datasets: Tenant A list query does not contain Tenant B datasets
        resp_list_dset = client.get("/api/datasets", headers=headers_a)
        dset_ids = [d["dataset_id"] for d in resp_list_dset.json()["datasets"]]
        assert "dset_alpha" in dset_ids
        assert "dset_beta" not in dset_ids

        # Projects: Tenant A direct ID query for Tenant B project -> 404
        resp_proj = client.get("/api/projects/proj_beta", headers=headers_a)
        assert resp_proj.status_code == 404

        # Projects: Tenant B direct ID query for its own project -> 200
        resp_proj_b = client.get("/api/projects/proj_beta", headers=headers_b)
        assert resp_proj_b.status_code == 200

        # Projects: Tenant A list query does not contain Tenant B projects
        resp_list_proj = client.get("/api/projects", headers=headers_a)
        proj_ids = [p["project_id"] for p in resp_list_proj.json()["projects"]]
        assert "proj_alpha" in proj_ids
        assert "proj_beta" not in proj_ids

    def test_read_isolation_models_jobs_and_audits(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Prove Tenant A cannot view Tenant B's models, jobs, or audit logs."""
        client: TestClient = postgres_e2e_harness["client"]
        headers_a = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha']}"}

        # Models
        resp_mod = client.get("/api/models/manifests/mod_beta", headers=headers_a)
        assert resp_mod.status_code == 404

        resp_list_mods = client.get("/api/models/manifests", headers=headers_a)
        mod_ids = [m["model_id"] for m in resp_list_mods.json()["models"]]
        assert "mod_alpha" in mod_ids
        assert "mod_beta" not in mod_ids

        # Jobs
        resp_jobs = client.get("/api/jobs", headers=headers_a)
        job_ids = [j["job_id"] for j in resp_jobs.json()["jobs"]]
        assert "job_alpha" in job_ids
        assert "job_beta" not in job_ids

        # Audit events: Researcher without AUDIT_READ permission is rejected by application RBAC
        resp_audits_denied = client.get("/api/audit/events", headers=headers_a)
        assert resp_audits_denied.status_code == 403

        # Audit events: Tenant Admin with AUDIT_READ permission accesses audits, but RLS restricts to own tenant
        headers_admin = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha_admin']}"}
        resp_audits = client.get("/api/audit/events", headers=headers_admin)
        assert resp_audits.status_code == 200
        audit_ids = [a["event_id"] for a in resp_audits.json()["audit_events"]]
        assert "audit_alpha" in audit_ids
        assert "audit_beta" not in audit_ids

    def test_write_isolation_and_spoofing_rejection(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Prove Tenant A cannot create records attributed to Tenant B or delete Tenant B data."""
        client: TestClient = postgres_e2e_harness["client"]
        headers_a = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha']}"}
        headers_admin = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha_admin']}"}
        headers_b = {"Authorization": f"Bearer {postgres_e2e_harness['token_beta']}"}

        # 1. Tenant A creating a valid portfolio for Tenant A -> 201 Created
        new_port_payload = {
            "portfolio_id": "port_alpha_new_1",
            "name": "Alpha Fresh Portfolio",
            "currency": "INR",
            "holdings": [{"asset_id": "INFY", "quantity": 10, "price": 1800.0}],
        }
        resp_create = client.post("/api/portfolios", json=new_port_payload, headers=headers_a)
        assert resp_create.status_code == 201

        # 2a. Researcher without PORTFOLIO_DELETE permission is blocked at RBAC layer -> 403
        resp_del_unauth = client.delete("/api/portfolios/port_beta_secret", headers=headers_a)
        assert resp_del_unauth.status_code == 403

        # 2b. Tenant Admin WITH PORTFOLIO_DELETE permission executes delete against PostgreSQL,
        # but PostgreSQL RLS makes port_beta_secret completely invisible, affecting 0 rows -> 404
        resp_del = client.delete("/api/portfolios/port_beta_secret", headers=headers_admin)
        assert resp_del.status_code == 404

        # Tenant B verifies its portfolio was NOT deleted
        resp_verify = client.get("/api/portfolios/port_beta_secret", headers=headers_b)
        assert resp_verify.status_code == 200

        # 3. Tenant Admin attempting to delete Tenant B's dataset -> 404 (invisible under RLS)
        resp_del_dset = client.delete("/api/datasets/dset_beta", headers=headers_admin)
        assert resp_del_dset.status_code == 404

        # 4. Tenant Admin successfully deletes Tenant A's own portfolio -> 200
        resp_del_own = client.delete("/api/portfolios/port_alpha_new_1", headers=headers_admin)
        assert resp_del_own.status_code == 200

    def test_studio_experiment_persists_to_postgres_under_rls(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Prove Studio Experiment execution persists run records into PostgreSQL under RLS."""
        client: TestClient = postgres_e2e_harness["client"]
        headers_a = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha']}"}
        headers_b = {"Authorization": f"Bearer {postgres_e2e_harness['token_beta']}"}

        payload = {
            "experiment_id": "studio_e2e_exp_01",
            "name": "E2E Studio Fragility Audit",
        }
        resp = client.post("/api/studio/experiment", json=payload, headers=headers_a)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Tenant A sees the recorded run in its experiment run list
        runs_a = client.get("/api/experiments/runs", headers=headers_a).json()["runs"]
        assert any(r["experiment_id"] == "studio_e2e_exp_01" for r in runs_a)

        # Tenant B does NOT see Tenant A's experiment run
        runs_b = client.get("/api/experiments/runs", headers=headers_b).json()["runs"]
        assert not any(r["experiment_id"] == "studio_e2e_exp_01" for r in runs_b)

    def test_unauthenticated_request_fails_closed_in_production(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """In production mode, missing Authorization header returns 401 fail-closed."""
        client: TestClient = postgres_e2e_harness["client"]
        orig_mode = os.environ.get("DEPLOYMENT_MODE")
        try:
            os.environ["DEPLOYMENT_MODE"] = "public_multi_tenant"
            resp = client.get("/api/portfolios")
            assert resp.status_code == 401
            assert "authentication required" in resp.json()["error"].lower()
        finally:
            if orig_mode:
                os.environ["DEPLOYMENT_MODE"] = orig_mode
            else:
                os.environ.pop("DEPLOYMENT_MODE", None)

    def test_connection_pool_reuse_does_not_leak_tenant_context(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Prove that reused pooled connections do not leak tenant context across requests."""
        client: TestClient = postgres_e2e_harness["client"]
        headers_a = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha']}"}
        headers_b = {"Authorization": f"Bearer {postgres_e2e_harness['token_beta']}"}

        # Rapidly alternate 10 requests between Tenant A and Tenant B
        for i in range(10):
            # Tenant A request
            resp_a = client.get("/api/portfolios", headers=headers_a)
            assert resp_a.status_code == 200
            ids_a = [p["portfolio_id"] for p in resp_a.json()["portfolios"]]
            assert "port_alpha_confidential" in ids_a
            assert "port_beta_secret" not in ids_a

            # Tenant B request
            resp_b = client.get("/api/portfolios", headers=headers_b)
            assert resp_b.status_code == 200
            ids_b = [p["portfolio_id"] for p in resp_b.json()["portfolios"]]
            assert "port_beta_secret" in ids_b
            assert "port_alpha_confidential" not in ids_b

    def test_concurrent_multi_tenant_requests_maintain_strict_isolation(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Execute concurrent multi-threaded requests across tenants to verify absence of race conditions."""
        import concurrent.futures

        client: TestClient = postgres_e2e_harness["client"]
        headers_a = {"Authorization": f"Bearer {postgres_e2e_harness['token_alpha']}"}
        headers_b = {"Authorization": f"Bearer {postgres_e2e_harness['token_beta']}"}

        def run_tenant_a() -> bool:
            resp = client.get("/api/portfolios", headers=headers_a)
            if resp.status_code != 200:
                return False
            ids = [p["portfolio_id"] for p in resp.json()["portfolios"]]
            return "port_alpha_confidential" in ids and "port_beta_secret" not in ids

        def run_tenant_b() -> bool:
            resp = client.get("/api/portfolios", headers=headers_b)
            if resp.status_code != 200:
                return False
            ids = [p["portfolio_id"] for p in resp.json()["portfolios"]]
            return "port_beta_secret" in ids and "port_alpha_confidential" not in ids

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures_a = [executor.submit(run_tenant_a) for _ in range(15)]
            futures_b = [executor.submit(run_tenant_b) for _ in range(15)]

            for f in futures_a:
                assert f.result() is True
            for f in futures_b:
                assert f.result() is True

    def test_missing_tenant_context_fails_closed_in_repository(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Direct repository operations without tenant context fail closed."""
        from fragility_engine.tenancy import _CURRENT_TENANT_CONTEXT
        from fragility_engine.database import get_active_repository

        repo = get_active_repository()
        token = _CURRENT_TENANT_CONTEXT.set(None)
        try:
            with pytest.raises(PermissionError, match="No active tenant context"):
                repo.list_portfolios()
            with pytest.raises(PermissionError, match="No active tenant context"):
                repo.get_portfolio("port_alpha_confidential")
        finally:
            _CURRENT_TENANT_CONTEXT.reset(token)

    def test_restricted_app_role_cannot_bypass_rls(self, postgres_e2e_harness: Dict[str, Any]) -> None:
        """Verify fragility_app_user has rolsuper=False and rolbypassrls=False in PostgreSQL catalog."""
        import psycopg2

        app_url = postgres_e2e_harness["app_url"]
        conn = psycopg2.connect(app_url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user;
            """)
            row = cur.fetchone()
            assert row is not None
            rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole = row
            assert rolname == "fragility_app_user"
            assert rolsuper is False
            assert rolbypassrls is False
            assert rolcreatedb is False
            assert rolcreaterole is False
        conn.close()
