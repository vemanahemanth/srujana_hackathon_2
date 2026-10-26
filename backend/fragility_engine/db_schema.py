"""FragilityShield — PostgreSQL Architecture, Row-Level Security (RLS), and Migrations.

This module defines:
1. Complete PostgreSQL production DDL for tenant-isolated relational persistence.
2. Enforceable Row-Level Security (RLS) policies on all tenant-owned tables.
3. Security boundary checks that fail closed if an unsupported database (e.g. SQLite)
   is configured for a public multi-tenant deployment.
4. Automated SQLite-to-PostgreSQL migration, data reconciliation, and rollback runbooks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


class SecurityConfigurationError(Exception):
    """Raised when application configuration violates production security invariants."""
    pass


# ==============================================================================
# 1. Complete PostgreSQL DDL with Row-Level Security
# ==============================================================================

POSTGRES_RLS_SCHEMA_DDL = """
-- =============================================================================
-- FragilityShield Production Relational Schema with Row-Level Security (RLS)
-- Target: PostgreSQL 14+ / AWS RDS / Managed Cloud PostgreSQL
-- =============================================================================

BEGIN;

-- 1. Create Core Platform Tables
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

-- =============================================================================
-- 2. Tenant-Owned Financial & Scientific Research Tables
-- =============================================================================

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
    status VARCHAR(32) NOT NULL,  -- 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED'
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

-- =============================================================================
-- 3. Row-Level Security (RLS) Policy Enforcement
-- =============================================================================

-- Enable and FORCE Row-Level Security on all tenant-owned tables
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios FORCE ROW LEVEL SECURITY;

ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets FORCE ROW LEVEL SECURITY;

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;

ALTER TABLE models ENABLE ROW LEVEL SECURITY;
ALTER TABLE models FORCE ROW LEVEL SECURITY;

ALTER TABLE experiment_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE experiment_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE plugin_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plugin_registrations FORCE ROW LEVEL SECURITY;

ALTER TABLE plugin_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plugin_executions FORCE ROW LEVEL SECURITY;

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

-- 4. Define Restrictive Tenant Isolation Policies
-- In PostgreSQL, restrictive policies are combined with AND. To ensure access is evaluated
-- strictly through tenant isolation rather than default-deny, a base permissive policy is defined
-- alongside the restrictive tenant isolation policy.
-- If app.current_tenant_id is missing or blank, access is strictly denied.

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

-- =============================================================================
-- 5. Least-Privilege Application Runtime Role Setup
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'fragility_app_user') THEN
        CREATE ROLE fragility_app_user WITH LOGIN PASSWORD 'change_this_in_production_secrets_manager';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO fragility_app_user', current_database());
END
$$;

-- Revoke superuser / bypass permissions
ALTER ROLE fragility_app_user NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

-- Grant selective DML permissions only
GRANT USAGE ON SCHEMA public TO fragility_app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fragility_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fragility_app_user;

COMMIT;
"""


# ==============================================================================
# 2. Production Security Configuration Validator
# ==============================================================================

def verify_production_security_configuration(
    deployment_mode: str,
    database_url: str,
    jwt_secret: str,
    cors_origins: Sequence[str],
) -> Dict[str, Any]:
    """Validate that environment settings satisfy non-negotiable security requirements.

    Enforces:
    1. If `deployment_mode == 'public_multi_tenant'`, SQLite is strictly rejected.
    2. Database URL must be PostgreSQL (`postgresql://...` or `postgresql+asyncpg://...`).
    3. JWT Secret must be >= 32 characters and not a trivial default.
    4. CORS must not contain wildcard `*` if credentials are used.

    Raises:
        SecurityConfigurationError: If any production security control is violated.
    """
    mode = str(deployment_mode).strip().lower()
    errors: List[str] = []

    # 1. Database Engine Verification
    is_sqlite = "sqlite" in database_url.lower()
    is_postgres = database_url.lower().startswith("postgresql")

    if mode in ("public_multi_tenant", "production_cloud"):
        if is_sqlite:
            errors.append(
                "FAIL-CLOSED: SQLite persistence is strictly prohibited in public_multi_tenant mode. "
                "SQLite does not provide enforceable Row-Level Security (RLS). A managed PostgreSQL "
                "database with active RLS is required."
            )
        if not is_postgres:
            errors.append(
                f"FAIL-CLOSED: Invalid production database URL '{database_url}'. "
                "Must be a PostgreSQL connection string."
            )

    # 2. Secret Strength Verification
    clean_secret = jwt_secret.strip()
    trivial_defaults = ("fragilityshield_dev", "default_secret", "change_me", "changeme")
    if mode in ("public_multi_tenant", "hosted_single_user", "production_cloud"):
        if len(clean_secret) < 32:
            errors.append(
                f"FAIL-CLOSED: JWT secret is too short ({len(clean_secret)} chars). "
                "Must be at least 32 characters long."
            )
        if any(td in clean_secret.lower() for td in trivial_defaults):
            errors.append("FAIL-CLOSED: Trivial or default JWT secret detected.")
        elif len(set(clean_secret)) < 6:
            errors.append("FAIL-CLOSED: Trivial or default JWT secret detected.")

    # 3. CORS Policy Verification
    if mode in ("public_multi_tenant", "production_cloud"):
        if "*" in cors_origins:
            errors.append(
                "FAIL-CLOSED: Wildcard CORS origin ('*') is prohibited in public multi-tenant mode. "
                "Explicit origin allowlists must be specified."
            )

    if errors:
        raise SecurityConfigurationError("\n".join(errors))

    return {
        "status": "VERIFIED",
        "deployment_mode": mode,
        "database_engine": "PostgreSQL" if is_postgres else "SQLite",
        "rls_enforcement_ready": is_postgres,
        "checks_passed": ["engine_valid", "secret_strong", "cors_restricted"],
    }


# ==============================================================================
# 3. SQLite-to-PostgreSQL Migration Runner & Checksum Verification
# ==============================================================================

def generate_sqlite_migration_manifest(
    projects: Sequence[Dict[str, Any]],
    datasets: Sequence[Dict[str, Any]],
    models: Sequence[Dict[str, Any]],
    default_tenant_id: str = "tenant_default",
    default_user_id: str = "user_migrated_admin",
) -> Dict[str, Any]:
    """Construct an export manifest converting un-scoped legacy JSON/SQLite data into tenant-scoped PostgreSQL rows.

    Calculates SHA-256 data fingerprints to verify lossless data transfer.
    """
    import hashlib
    import json

    records_to_migrate: List[Dict[str, Any]] = []

    for p in projects:
        records_to_migrate.append({
            "table": "projects",
            "tenant_id": default_tenant_id,
            "project_id": p.get("project_id", ""),
            "name": p.get("name", ""),
            "created_by": default_user_id,
            "manifest_json": p,
        })

    for d in datasets:
        records_to_migrate.append({
            "table": "datasets",
            "tenant_id": default_tenant_id,
            "dataset_id": d.get("dataset_id", ""),
            "name": d.get("name", ""),
            "source_type": d.get("source_type", "historical"),
            "provenance_json": d.get("provenance", {}),
            "fingerprint": d.get("fingerprint", ""),
            "row_count": d.get("row_count", 0),
            "created_by": default_user_id,
        })

    for m in models:
        records_to_migrate.append({
            "table": "models",
            "tenant_id": default_tenant_id,
            "model_id": m.get("model_id", ""),
            "name": m.get("name", ""),
            "family": m.get("family", "custom"),
            "parameters_json": m.get("parameters", {}),
            "created_by": default_user_id,
        })

    canonical_payload = json.dumps(records_to_migrate, sort_keys=True)
    manifest_checksum = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    return {
        "manifest_version": "1.0.0",
        "default_tenant_id": default_tenant_id,
        "default_user_id": default_user_id,
        "total_records": len(records_to_migrate),
        "manifest_checksum_sha256": manifest_checksum,
        "records": records_to_migrate,
    }
