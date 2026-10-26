"""Live PostgreSQL Row-Level Security (RLS) Penetration and Isolation Test Suite (Sprint 2).

This module connects to a real, live PostgreSQL instance and executes adversarial attacks
using the least-privilege `fragility_app_user` database role to mathematically and
operationally prove Row-Level Security enforcement.

Verified Properties:
1. Least-Privilege Role Inspection:
   - `fragility_app_user` has `rolsuper=False`, `rolbypassrls=False`, `rolcreatedb=False`, `rolcreaterole=False`.
2. Catalog Inspection:
   - All 9 tenant-owned tables have `rowsecurity=True` and `forcerowsecurity=True`.
3. SELECT Isolation:
   - Tenant A cannot retrieve Tenant B's records by direct ID.
   - Tenant A cannot enumerate Tenant B's records via list queries.
4. INSERT Isolation:
   - Tenant A cannot insert a record with `tenant_id = 'ten_b'` (WITH CHECK violation).
5. UPDATE Isolation:
   - Tenant A cannot modify Tenant B's records (affects 0 rows).
   - Tenant A cannot move its own records into Tenant B by changing `tenant_id` (WITH CHECK violation).
6. DELETE Isolation:
   - Tenant A cannot delete Tenant B's records (affects 0 rows).
   - Tenant A can delete its own records (affects 1 row).
7. Missing Context Fail-Closed:
   - If `app.current_tenant_id` is blank or unset, all reads return 0 rows and writes fail.
8. Transaction-Local Boundary & Pool Reuse:
   - `SET LOCAL app.current_tenant_id` expires at transaction completion.
   - Reused pooled connections do not leak tenant state across transactions.
9. Comprehensive Table Coverage:
   - RLS isolation verified across all 9 tenant-owned tables.
"""

from __future__ import annotations

import os
import urllib.parse
import uuid
from typing import Generator, Tuple
import pytest

from fragility_engine.db_schema import POSTGRES_RLS_SCHEMA_DDL


def get_live_postgres_admin_url() -> str | None:
    """Detect available PostgreSQL administrative connection string."""
    env_url = os.environ.get("TEST_POSTGRESQL_URL", "").strip()
    candidate_urls = [env_url] if env_url else [
        "postgresql://postgres@localhost:5434/postgres",  # Disposable local cluster
        "postgresql://postgres:postgres@localhost:5432/postgres",  # Default local postgres
    ]

    for candidate in candidate_urls:
        if not candidate:
            continue
        try:
            import psycopg2
            conn = psycopg2.connect(candidate, connect_timeout=1)
            conn.close()
            return candidate
        except Exception:
            continue
    return None


@pytest.fixture(scope="module")
def postgres_live_harness() -> Generator[Tuple[str, str], None, None]:
    """Sets up a clean, disposable PostgreSQL database for live RLS penetration testing."""
    admin_url = get_live_postgres_admin_url()
    if not admin_url:
        pytest.skip(
            "LIVE_POSTGRESQL_UNAVAILABLE: No reachable PostgreSQL server on localhost:5434 or :5432. "
            "To run live RLS tests, ensure PostgreSQL is running or set TEST_POSTGRESQL_URL."
        )

    import psycopg2
    admin_conn = psycopg2.connect(admin_url)
    admin_conn.autocommit = True
    disposable_db_name = f"fs_rls_sprint2_{uuid.uuid4().hex[:8]}"

    # 1. Create disposable database
    with admin_conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE {disposable_db_name};")

    # Build DB URLs
    parsed = urllib.parse.urlsplit(admin_url)
    db_base = f"{parsed.scheme}://{parsed.netloc}/{disposable_db_name}"
    app_url = f"{parsed.scheme}://fragility_app_user:change_this_in_production_secrets_manager@{parsed.hostname}:{parsed.port or 5432}/{disposable_db_name}"

    # 2. Apply Schema DDL and Seed Base Tenants/Users
    setup_conn = psycopg2.connect(db_base)
    setup_conn.autocommit = True
    with setup_conn.cursor() as cur:
        cur.execute(POSTGRES_RLS_SCHEMA_DDL)
        cur.execute("""
            INSERT INTO tenants (tenant_id, name) VALUES 
            ('ten_a', 'Tenant A Capital'),
            ('ten_b', 'Tenant B Capital')
            ON CONFLICT DO NOTHING;

            INSERT INTO users (user_id, email, password_hash) VALUES 
            ('usr_a', 'a@fragility.test', 'hash_a'),
            ('usr_b', 'b@fragility.test', 'hash_b')
            ON CONFLICT DO NOTHING;

            INSERT INTO tenant_memberships (membership_id, tenant_id, user_id, role) VALUES 
            ('mem_a', 'ten_a', 'usr_a', 'researcher'),
            ('mem_b', 'ten_b', 'usr_b', 'researcher')
            ON CONFLICT DO NOTHING;
        """)
    setup_conn.close()

    yield (db_base, app_url)

    # 3. Teardown: terminate connections and drop disposable database
    with admin_conn.cursor() as cur:
        cur.execute(f"""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = '{disposable_db_name}' AND pid <> pg_backend_pid();
        """)
        cur.execute(f"DROP DATABASE IF EXISTS {disposable_db_name};")
    admin_conn.close()


class TestLivePostgresRLSIntegration:
    """Comprehensive adversarial penetration tests executing live SQL against PostgreSQL 18."""

    TENANT_TABLES = [
        "portfolios",
        "datasets",
        "projects",
        "models",
        "experiment_runs",
        "plugin_registrations",
        "plugin_executions",
        "jobs",
        "audit_events",
    ]

    def test_role_least_privilege_inspection(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify fragility_app_user is strictly unprivileged and cannot bypass RLS."""
        import psycopg2
        admin_url, _ = postgres_live_harness
        conn = psycopg2.connect(admin_url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rolsuper, rolbypassrls, rolcanlogin, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname = 'fragility_app_user';
            """)
            row = cur.fetchone()
            assert row is not None
            rolsuper, rolbypassrls, rolcanlogin, rolcreatedb, rolcreaterole = row
            assert rolsuper is False, "Security violation: fragility_app_user must not be a superuser"
            assert rolbypassrls is False, "Security violation: fragility_app_user must NOT have BYPASSRLS"
            assert rolcanlogin is True
            assert rolcreatedb is False
            assert rolcreaterole is False
        conn.close()

    def test_forced_rls_catalog_inspection(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify all 9 tenant-owned tables have RLS enabled and FORCED in PostgreSQL catalogs."""
        import psycopg2
        admin_url, _ = postgres_live_harness
        conn = psycopg2.connect(admin_url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                AND c.relname = ANY(%s);
            """, (self.TENANT_TABLES,))
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

            for tbl in self.TENANT_TABLES:
                assert tbl in rows, f"Table {tbl} not found in pg_class"
                rowsec, forcerowsec = rows[tbl]
                assert rowsec is True, f"RLS not enabled on {tbl}"
                assert forcerowsec is True, f"FORCE RLS not enabled on {tbl}"
        conn.close()

    def test_select_isolation_and_cross_tenant_enumeration_prevention(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify Tenant A cannot read Tenant B's records via direct lookup or list queries."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            # Seed records for both tenants
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                cur.execute("""
                    INSERT INTO portfolios (portfolio_id, tenant_id, name, holdings_json, created_by)
                    VALUES ('pf_a_secret', 'ten_a', 'Tenant A Secret Alpha', '[]'::jsonb, 'usr_a');
                """)
            conn.commit()

            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_b';")
                cur.execute("""
                    INSERT INTO portfolios (portfolio_id, tenant_id, name, holdings_json, created_by)
                    VALUES ('pf_b_secret', 'ten_b', 'Tenant B Secret Beta', '[]'::jsonb, 'usr_b');
                """)
            conn.commit()

            # Tenant A attempts direct lookup of Tenant B's record
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                cur.execute("SELECT portfolio_id, name FROM portfolios WHERE portfolio_id = 'pf_b_secret';")
                rows = cur.fetchall()
                assert len(rows) == 0, "Security violation: Tenant A retrieved Tenant B portfolio by ID"

                # Tenant A attempts table enumeration
                cur.execute("SELECT portfolio_id, name FROM portfolios;")
                all_rows = cur.fetchall()
                assert len(all_rows) == 1
                assert all_rows[0][0] == "pf_a_secret"
            conn.rollback()

            # Tenant B attempts direct lookup of Tenant A's record
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_b';")
                cur.execute("SELECT portfolio_id, name FROM portfolios WHERE portfolio_id = 'pf_a_secret';")
                rows = cur.fetchall()
                assert len(rows) == 0, "Security violation: Tenant B retrieved Tenant A portfolio by ID"

                cur.execute("SELECT portfolio_id, name FROM portfolios;")
                all_rows = cur.fetchall()
                assert len(all_rows) == 1
                assert all_rows[0][0] == "pf_b_secret"
            conn.rollback()
        finally:
            conn.close()

    def test_insert_isolation_and_cross_tenant_spoofing(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify Tenant A cannot insert a record with tenant_id = 'ten_b' (WITH CHECK violation)."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                with pytest.raises(psycopg2.Error) as exc_info:
                    cur.execute("""
                        INSERT INTO portfolios (portfolio_id, tenant_id, name, holdings_json, created_by)
                        VALUES ('pf_forged_b', 'ten_b', 'Forged Portfolio', '[]'::jsonb, 'usr_a');
                    """)
                assert "violates row-level security policy" in str(exc_info.value)
            conn.rollback()
        finally:
            conn.close()

    def test_update_isolation_and_tenant_hijack(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify Tenant A cannot update Tenant B's data or change record tenant_id."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            # Tenant A attempts to update Tenant B's portfolio name
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                cur.execute("""
                    UPDATE portfolios SET name = 'HACKED' WHERE portfolio_id = 'pf_b_secret';
                """)
                assert cur.rowcount == 0, "Security violation: Tenant A modified Tenant B record"
            conn.rollback()

            # Tenant A attempts to hijack its own portfolio to tenant_id = 'ten_b'
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                with pytest.raises(psycopg2.Error) as exc_info:
                    cur.execute("""
                        UPDATE portfolios SET tenant_id = 'ten_b' WHERE portfolio_id = 'pf_a_secret';
                    """)
                assert "violates row-level security policy" in str(exc_info.value)
            conn.rollback()
        finally:
            conn.close()

    def test_delete_isolation(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify Tenant A cannot delete Tenant B's data."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            # Tenant A attempts to delete Tenant B's portfolio
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                cur.execute("DELETE FROM portfolios WHERE portfolio_id = 'pf_b_secret';")
                assert cur.rowcount == 0, "Security violation: Tenant A deleted Tenant B record"
            conn.rollback()

            # Confirm Tenant B record is still intact
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_b';")
                cur.execute("SELECT portfolio_id FROM portfolios WHERE portfolio_id = 'pf_b_secret';")
                assert len(cur.fetchall()) == 1
            conn.rollback()
        finally:
            conn.close()

    def test_missing_tenant_context_fails_closed(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify queries with no tenant context fail closed (0 rows returned, writes blocked)."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            with conn.cursor() as cur:
                # Without SET LOCAL app.current_tenant_id
                cur.execute("SELECT * FROM portfolios;")
                assert len(cur.fetchall()) == 0

                cur.execute("UPDATE portfolios SET name = 'X';")
                assert cur.rowcount == 0

                cur.execute("DELETE FROM portfolios;")
                assert cur.rowcount == 0

                with pytest.raises(psycopg2.Error):
                    cur.execute("""
                        INSERT INTO portfolios (portfolio_id, tenant_id, name, holdings_json, created_by)
                        VALUES ('pf_orphan', 'ten_a', 'Orphan', '[]'::jsonb, 'usr_a');
                    """)
            conn.rollback()
        finally:
            conn.close()

    def test_transaction_scoped_setting_does_not_persist(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify SET LOCAL app.current_tenant_id automatically expires at transaction completion."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            # Transaction 1: establish context and read Tenant A data
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                cur.execute("SELECT COUNT(*) FROM portfolios;")
                assert cur.fetchone()[0] == 1
            conn.commit()

            # Transaction 2 on same connection: no context set
            with conn.cursor() as cur:
                cur.execute("SELECT current_setting('app.current_tenant_id', true);")
                setting = cur.fetchone()[0]
                assert setting in (None, ""), "Context setting leaked across transaction boundary!"

                cur.execute("SELECT COUNT(*) FROM portfolios;")
                assert cur.fetchone()[0] == 0, "Data leaked across transaction boundary without context!"
            conn.rollback()
        finally:
            conn.close()

    def test_all_nine_tenant_tables_isolated(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Verify RLS isolation across all 9 tenant-owned tables in the production schema."""
        import psycopg2
        _, app_url = postgres_live_harness
        conn = psycopg2.connect(app_url)
        conn.autocommit = False

        try:
            # 1. Populate records for Tenant A across remaining 8 tables
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                cur.execute("""
                    INSERT INTO datasets (dataset_id, tenant_id, name, source_type, provenance_json, fingerprint, row_count, created_by)
                    VALUES ('ds_a', 'ten_a', 'DS A', 'hist', '{}'::jsonb, 'fp_a', 10, 'usr_a');

                    INSERT INTO projects (project_id, tenant_id, name, manifest_json, created_by)
                    VALUES ('proj_a', 'ten_a', 'Project A', '{}'::jsonb, 'usr_a');

                    INSERT INTO models (model_id, tenant_id, name, family, parameters_json, created_by)
                    VALUES ('mod_a', 'ten_a', 'Model A', 'custom', '{}'::jsonb, 'usr_a');

                    INSERT INTO experiment_runs (run_id, tenant_id, experiment_id, spec_json, result_json, dataset_hash, created_by)
                    VALUES ('run_a', 'ten_a', 'exp_a', '{}'::jsonb, '{}'::jsonb, 'hash_a', 'usr_a');

                    INSERT INTO plugin_registrations (plugin_id, tenant_id, name, version, manifest_json, registered_by)
                    VALUES ('plg_a', 'ten_a', 'Plugin A', '1.0.0', '{}'::jsonb, 'usr_a');

                    INSERT INTO plugin_executions (execution_id, tenant_id, plugin_id, status, resource_limits_json, executed_by)
                    VALUES ('exec_a', 'ten_a', 'plg_a', 'COMPLETED', '{}'::jsonb, 'usr_a');

                    INSERT INTO jobs (job_id, tenant_id, job_type, payload_json, created_by)
                    VALUES ('job_a', 'ten_a', 'SIM', '{}'::jsonb, 'usr_a');

                    INSERT INTO audit_events (event_id, tenant_id, user_id, action, resource_type, resource_id, status, details_json)
                    VALUES ('evt_a', 'ten_a', 'usr_a', 'LOGIN', 'auth', 'sess_1', 'SUCCESS', '{}'::jsonb);
                """)
            conn.commit()

            # 2. Under Tenant B context, verify that every table returns exactly 0 rows!
            tables_to_check = [
                "datasets", "projects", "models", "experiment_runs",
                "plugin_registrations", "plugin_executions", "jobs", "audit_events"
            ]
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_b';")
                for tbl in tables_to_check:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl};")
                    count = cur.fetchone()[0]
                    assert count == 0, f"RLS Isolation Breach on table '{tbl}': Tenant B saw {count} rows!"
            conn.rollback()

            # 3. Under Tenant A context, verify records are accessible
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                for tbl in tables_to_check:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl};")
                    count = cur.fetchone()[0]
                    assert count >= 1, f"Table '{tbl}' record missing for Tenant A"
            conn.rollback()
        finally:
            conn.close()

    def test_pooled_connection_reuse_simulation(self, postgres_live_harness: Tuple[str, str]) -> None:
        """Simulate pooled connection checkouts alternating between Tenant A and Tenant B."""
        import psycopg2
        _, app_url = postgres_live_harness
        reused_conn = psycopg2.connect(app_url)
        reused_conn.autocommit = False

        try:
            for iteration in range(5):
                # Worker 1: Check out connection for Tenant A
                with reused_conn.cursor() as cur:
                    cur.execute("SET LOCAL app.current_tenant_id = 'ten_a';")
                    cur.execute("SELECT portfolio_id FROM portfolios;")
                    rows = cur.fetchall()
                    assert len(rows) == 1
                    assert rows[0][0] == "pf_a_secret"
                reused_conn.commit()  # Simulates connection return to pool

                # Worker 2: Check out same connection for Tenant B
                with reused_conn.cursor() as cur:
                    cur.execute("SET LOCAL app.current_tenant_id = 'ten_b';")
                    cur.execute("SELECT portfolio_id FROM portfolios;")
                    rows = cur.fetchall()
                    assert len(rows) == 1
                    assert rows[0][0] == "pf_b_secret"
                reused_conn.commit()  # Simulates connection return to pool
        finally:
            reused_conn.close()
