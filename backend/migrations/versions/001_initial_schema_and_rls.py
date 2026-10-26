"""001 Initial Schema and Row-Level Security

Revision ID: 001_initial_schema_and_rls
Revises: None
Create Date: 2026-10-25 12:30:00.000000

Establishes:
1. Core platform identity tables: tenants, users, tenant_memberships.
2. Nine tenant-owned relational tables: portfolios, datasets, projects, models,
   experiment_runs, plugin_registrations, plugin_executions, jobs, audit_events.
3. Forced Row-Level Security (RLS) across all 9 tenant tables.
4. Restrictive tenant-isolation policies combined with base permissive policies.
5. Least-privilege DML grants for runtime role `fragility_app_user`.
"""

from typing import Sequence, Union
from alembic import op

revision: str = "001_initial_schema_and_rls"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = (
    "portfolios",
    "datasets",
    "projects",
    "models",
    "experiment_runs",
    "plugin_registrations",
    "plugin_executions",
    "jobs",
    "audit_events",
)


def upgrade() -> None:
    # 1. Core Tables
    op.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        tier VARCHAR(32) NOT NULL DEFAULT 'research',
        max_portfolios INTEGER NOT NULL DEFAULT 50,
        max_datasets_mb INTEGER NOT NULL DEFAULT 500,
        allow_untrusted_plugins BOOLEAN NOT NULL DEFAULT FALSE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS users (
        user_id VARCHAR(64) PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(255) DEFAULT '',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tenant_memberships (
        membership_id VARCHAR(64) PRIMARY KEY,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        role VARCHAR(32) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_tenant_user UNIQUE(tenant_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS idx_memberships_tenant ON tenant_memberships(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_memberships_user ON tenant_memberships(user_id);
    """)

    # 2. Nine Tenant-Owned Tables
    op.execute("""
    CREATE TABLE IF NOT EXISTS portfolios (
        portfolio_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        currency VARCHAR(8) NOT NULL DEFAULT 'INR',
        holdings_json JSONB NOT NULL,
        created_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, portfolio_id)
    );

    CREATE TABLE IF NOT EXISTS datasets (
        dataset_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        source_type VARCHAR(64) NOT NULL,
        provenance_json JSONB NOT NULL,
        fingerprint VARCHAR(64) NOT NULL,
        row_count INTEGER NOT NULL,
        created_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, dataset_id)
    );

    CREATE TABLE IF NOT EXISTS projects (
        project_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        manifest_json JSONB NOT NULL,
        created_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, project_id)
    );

    CREATE TABLE IF NOT EXISTS models (
        model_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        family VARCHAR(64) NOT NULL,
        parameters_json JSONB NOT NULL,
        created_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, model_id)
    );

    CREATE TABLE IF NOT EXISTS experiment_runs (
        run_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        experiment_id VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'completed',
        spec_json JSONB NOT NULL,
        result_json JSONB NOT NULL,
        dataset_hash VARCHAR(64) NOT NULL,
        created_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, run_id)
    );

    CREATE TABLE IF NOT EXISTS plugin_registrations (
        plugin_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        version VARCHAR(32) NOT NULL,
        manifest_json JSONB NOT NULL,
        is_trusted BOOLEAN NOT NULL DEFAULT FALSE,
        registered_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, plugin_id)
    );

    CREATE TABLE IF NOT EXISTS plugin_executions (
        execution_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        plugin_id VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        resource_limits_json JSONB NOT NULL,
        execution_time_ms DOUBLE PRECISION,
        metrics_json JSONB,
        error_message TEXT,
        executed_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, execution_id)
    );

    CREATE TABLE IF NOT EXISTS jobs (
        job_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        job_type VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
        payload_json JSONB NOT NULL,
        result_json JSONB,
        error_message TEXT,
        created_by VARCHAR(64) NOT NULL REFERENCES users(user_id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, job_id)
    );

    CREATE TABLE IF NOT EXISTS audit_events (
        event_id VARCHAR(64) PRIMARY KEY,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        action VARCHAR(64) NOT NULL,
        resource_type VARCHAR(64) NOT NULL,
        resource_id VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        ip_address VARCHAR(45) NOT NULL DEFAULT '127.0.0.1',
        details_json JSONB NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_events(tenant_id, timestamp);
    """)

    # 3. Enable & Force Row-Level Security on all 9 tenant tables
    for tbl in TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")

    # 4. Create Base Permissive and Restrictive Tenant Isolation Policies
    policy_ddl = """
    CREATE POLICY base_permissive_portfolios ON portfolios
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_portfolios ON portfolios
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_datasets ON datasets
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_datasets ON datasets
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_projects ON projects
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_projects ON projects
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_models ON models
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_models ON models
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_experiments ON experiment_runs
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_experiments ON experiment_runs
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_plugins ON plugin_registrations
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_plugins ON plugin_registrations
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_executions ON plugin_executions
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_executions ON plugin_executions
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_jobs ON jobs
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_jobs ON jobs
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));

    CREATE POLICY base_permissive_audit ON audit_events
        AS PERMISSIVE FOR ALL TO fragility_app_user
        USING (true) WITH CHECK (true);
    CREATE POLICY tenant_isolation_audit ON audit_events
        AS RESTRICTIVE FOR ALL TO fragility_app_user
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
    """
    op.execute(policy_ddl)

    # 5. Ensure fragility_app_user role exists and has least-privilege DML grants
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'fragility_app_user') THEN
            CREATE ROLE fragility_app_user WITH LOGIN PASSWORD 'change_this_in_production_secrets_manager';
        END IF;
        EXECUTE format('GRANT CONNECT ON DATABASE %I TO fragility_app_user', current_database());
    END
    $$;

    ALTER ROLE fragility_app_user NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
    GRANT USAGE ON SCHEMA public TO fragility_app_user;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fragility_app_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fragility_app_user;
    """)


def downgrade() -> None:
    """Safe teardown of tables in reverse dependency order."""
    tables_in_drop_order = [
        "audit_events",
        "jobs",
        "plugin_executions",
        "plugin_registrations",
        "experiment_runs",
        "models",
        "projects",
        "datasets",
        "portfolios",
        "tenant_memberships",
        "users",
        "tenants",
    ]
    for tbl in tables_in_drop_order:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
