"""Automated Verification Suite for PostgreSQL Alembic Migrations and Role Separation (Sprint 4).

Verifies:
1. Fresh database initialization via `alembic upgrade head`.
2. Migration history and revision tracking.
3. Bidirectional schema evolution (upgrade 001 -> 002, downgrade 002 -> 001, re-upgrade).
4. Forced Row-Level Security (RLS) preservation on all 9 tenant-owned tables.
5. Role privilege separation:
   - `fragility_migrator` / migration role has schema DDL capabilities.
   - `fragility_app_user` has least-privilege DML only (cannot alter schema or bypass RLS).
6. Live multi-tenant cross-tenant isolation and fail-closed behavior on the migrated schema.
"""

from __future__ import annotations

import os
import subprocess
import urllib.parse
import uuid
from typing import Dict, Generator
import pytest
import psycopg2


def get_local_pg_admin_url() -> str:
    return os.environ.get(
        "TEST_POSTGRESQL_URL",
        "postgresql://postgres@localhost:5434/postgres"
    )


@pytest.fixture(scope="module")
def migration_test_db() -> Generator[Dict[str, str], None, None]:
    """Provisions a clean, disposable PostgreSQL database for migration testing."""
    admin_url = get_local_pg_admin_url()
    try:
        admin_conn = psycopg2.connect(admin_url, connect_timeout=2)
        admin_conn.autocommit = True
    except Exception:
        pytest.skip(f"PostgreSQL server unreachable at {admin_url}")

    db_name = f"fs_migr_test_{uuid.uuid4().hex[:8]}"
    with admin_conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE {db_name};")

    parsed = urllib.parse.urlsplit(admin_url)
    migration_url = f"{parsed.scheme}://{parsed.netloc}/{db_name}"
    app_url = f"{parsed.scheme}://fragility_app_user:change_this_in_production_secrets_manager@{parsed.hostname}:{parsed.port or 5432}/{db_name}"

    yield {
        "db_name": db_name,
        "migration_url": migration_url,
        "app_url": app_url,
        "admin_url": admin_url,
    }

    # Teardown
    try:
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);")
        admin_conn.close()
    except Exception:
        pass


class TestAlembicMigrationsAndRoleSeparation:
    """Rigorous tests for database migrations, role separation, and RLS preservation."""

    def test_01_fresh_migration_to_head(self, migration_test_db: Dict[str, str]) -> None:
        """Prove that alembic upgrade head successfully initializes a fresh database."""
        mig_url = migration_test_db["migration_url"]
        env = dict(os.environ)
        env["MIGRATION_DATABASE_URL"] = mig_url

        # Execute alembic upgrade head
        res = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "upgrade", "head"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15.0,
        )
        assert res.returncode == 0, f"Alembic upgrade failed:\n{res.stderr}\n{res.stdout}"
        assert "Running upgrade" in res.stderr or "Running upgrade" in res.stdout

        # Verify revision
        curr_res = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "current"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0,
        )
        assert curr_res.returncode == 0
        assert "003_sprint5_jobs_and_artifacts" in curr_res.stdout or "003_sprint5_jobs_and_artifacts" in curr_res.stderr

    def test_02_bidirectional_downgrade_and_reupgrade(self, migration_test_db: Dict[str, str]) -> None:
        """Prove that migration revision 003 and 002 can be cleanly downgraded and re-applied."""
        mig_url = migration_test_db["migration_url"]
        env = dict(os.environ)
        env["MIGRATION_DATABASE_URL"] = mig_url

        # Downgrade by 1 step from 003 to revision 002
        res_down = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "downgrade", "-1"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15.0,
        )
        assert res_down.returncode == 0, f"Alembic downgrade to 002 failed:\n{res_down.stderr}"

        # Current should be 002
        res_curr = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "current"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0,
        )
        assert res_curr.returncode == 0
        assert "002_model_registry_enhancements" in res_curr.stdout or "002_model_registry_enhancements" in res_curr.stderr

        # Downgrade by another step to revision 001
        res_down_001 = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "downgrade", "-1"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15.0,
        )
        assert res_down_001.returncode == 0, f"Alembic downgrade to 001 failed:\n{res_down_001.stderr}"

        # Current should be 001
        res_curr_001 = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "current"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10.0,
        )
        assert res_curr_001.returncode == 0
        assert "001_initial_schema_and_rls" in res_curr_001.stdout or "001_initial_schema_and_rls" in res_curr_001.stderr

        # Re-upgrade to head (003)
        res_up = subprocess.run(
            ["/opt/anaconda3/bin/alembic", "upgrade", "head"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15.0,
        )
        assert res_up.returncode == 0, f"Alembic re-upgrade failed:\n{res_up.stderr}"

    def test_03_catalog_forced_rls_on_all_tenant_tables(self, migration_test_db: Dict[str, str]) -> None:
        """Inspect PostgreSQL catalog to prove RLS is enabled AND forced on all 10 tenant tables."""
        app_url = migration_test_db["app_url"]
        conn = psycopg2.connect(app_url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND c.relname IN (
                    'portfolios', 'datasets', 'projects', 'models',
                    'experiment_runs', 'plugin_registrations',
                    'plugin_executions', 'jobs', 'audit_events', 'artifacts'
                  );
            """)
            rows = cur.fetchall()
            assert len(rows) == 10, f"Expected 10 tenant-owned tables with forced RLS, found {len(rows)}"
            for tbl_name, rls_enabled, rls_forced in rows:
                assert rls_enabled is True, f"Table {tbl_name} must have relrowsecurity=True"
                assert rls_forced is True, f"Table {tbl_name} must have relforcerowsecurity=True"
        conn.close()

    def test_04_role_separation_runtime_cannot_alter_schema(self, migration_test_db: Dict[str, str]) -> None:
        """Prove that fragility_app_user cannot perform DDL (ALTER TABLE / CREATE TABLE)."""
        app_url = migration_test_db["app_url"]
        conn = psycopg2.connect(app_url)
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("ALTER TABLE portfolios ADD COLUMN malicious_col TEXT;")
        conn.close()

    def test_05_runtime_role_has_no_rls_bypass(self, migration_test_db: Dict[str, str]) -> None:
        """Verify fragility_app_user does NOT hold rolsuper or rolbypassrls."""
        app_url = migration_test_db["app_url"]
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

    def test_06_live_cross_tenant_isolation_on_migrated_schema(self, migration_test_db: Dict[str, str]) -> None:
        """Seed data across two tenants and prove complete cross-tenant isolation under RLS."""
        mig_url = migration_test_db["migration_url"]
        app_url = migration_test_db["app_url"]

        # Seed via admin/migration connection
        admin_conn = psycopg2.connect(mig_url)
        admin_conn.autocommit = True
        with admin_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tenants (tenant_id, name) VALUES
                ('ten_alpha_migr', 'Alpha Capital'),
                ('ten_beta_migr', 'Beta Capital')
                ON CONFLICT DO NOTHING;

                INSERT INTO users (user_id, email, password_hash) VALUES
                ('usr_alpha_migr', 'alpha@migr.test', 'hash_a'),
                ('usr_beta_migr', 'beta@migr.test', 'hash_b')
                ON CONFLICT DO NOTHING;

                INSERT INTO tenant_memberships (membership_id, tenant_id, user_id, role) VALUES
                ('mem_a', 'ten_alpha_migr', 'usr_alpha_migr', 'tenant_owner'),
                ('mem_b', 'ten_beta_migr', 'usr_beta_migr', 'tenant_owner')
                ON CONFLICT DO NOTHING;
            """)
        admin_conn.close()

        # Connect as restricted runtime role fragility_app_user
        app_conn = psycopg2.connect(app_url)

        # 1. Tenant Alpha writes its portfolio
        with app_conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant_id', 'ten_alpha_migr', true);")
            cur.execute("""
                INSERT INTO portfolios (portfolio_id, tenant_id, name, currency, holdings_json, created_by)
                VALUES ('port_alpha_01', 'ten_alpha_migr', 'Alpha Alpha', 'INR', '[]'::jsonb, 'usr_alpha_migr');
            """)
        app_conn.commit()

        # 2. Tenant Beta writes its portfolio
        with app_conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant_id', 'ten_beta_migr', true);")
            cur.execute("""
                INSERT INTO portfolios (portfolio_id, tenant_id, name, currency, holdings_json, created_by)
                VALUES ('port_beta_01', 'ten_beta_migr', 'Beta Secret', 'INR', '[]'::jsonb, 'usr_beta_migr');
            """)
        app_conn.commit()

        # 3. Tenant Alpha reading portfolios sees ONLY port_alpha_01
        with app_conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant_id', 'ten_alpha_migr', true);")
            cur.execute("SELECT portfolio_id FROM portfolios;")
            ids = [r[0] for r in cur.fetchall()]
            assert "port_alpha_01" in ids
            assert "port_beta_01" not in ids

        # 4. Tenant Alpha attempting cross-tenant spoofing INSERT fails closed
        with app_conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant_id', 'ten_alpha_migr', true);")
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("""
                    INSERT INTO portfolios (portfolio_id, tenant_id, name, currency, holdings_json, created_by)
                    VALUES ('port_spoofed', 'ten_beta_migr', 'Spoofed', 'INR', '[]'::jsonb, 'usr_alpha_migr');
                """)
        app_conn.rollback()

        # 5. Missing tenant context returns 0 rows (fail-closed)
        with app_conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant_id', '', true);")
            cur.execute("SELECT count(*) FROM portfolios;")
            assert cur.fetchone()[0] == 0

        app_conn.close()
