"""003 Sprint 5 Job Orchestration Leases & Tenant-Isolated Artifacts

Revision ID: 003_sprint5_jobs_and_artifacts
Revises: 002_model_registry_enhancements
Create Date: 2026-10-25 12:50:00.000000

Sprint 5 Enhancements:
1. Adds worker leasing, heartbeats, attempts, and timeout tracking columns to `jobs`.
2. Creates `artifacts` table protected by forced Row-Level Security (RLS) for experiment evidence.
3. Configures composite claiming indexes for PostgreSQL `FOR UPDATE SKIP LOCKED`.
4. Grants least-privilege DML access to `fragility_app_user`.
"""

from typing import Sequence, Union
from alembic import op

revision: str = "003_sprint5_jobs_and_artifacts"
down_revision: Union[str, Sequence[str], None] = "002_model_registry_enhancements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enhance jobs table with worker leasing, heartbeat and retry columns
    op.execute("""
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64);
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 3;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 60.0;
    ALTER TABLE jobs ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;

    CREATE INDEX IF NOT EXISTS idx_jobs_claiming ON jobs(status, priority DESC, created_at ASC);
    CREATE INDEX IF NOT EXISTS idx_jobs_lease_expiry ON jobs(status, lease_expires_at);
    """)

    # 2. Create artifacts table
    op.execute("""
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id VARCHAR(64) NOT NULL,
        tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
        job_id VARCHAR(64),
        experiment_id VARCHAR(64),
        logical_type VARCHAR(64) NOT NULL,
        storage_key VARCHAR(255) NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        size_bytes BIGINT NOT NULL,
        media_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream',
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMPTZ,
        PRIMARY KEY (tenant_id, artifact_id)
    );

    CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(tenant_id, job_id);
    CREATE INDEX IF NOT EXISTS idx_artifacts_exp ON artifacts(tenant_id, experiment_id);
    CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(content_hash);
    """)

    # 3. Enforce Row-Level Security on artifacts table
    op.execute("""
    ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
    ALTER TABLE artifacts FORCE ROW LEVEL SECURITY;

    DO $$
    BEGIN
        IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'fragility_app_user') THEN
            -- Base permissive policy
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies 
                WHERE tablename = 'artifacts' AND policyname = 'base_permissive_artifacts'
            ) THEN
                CREATE POLICY base_permissive_artifacts ON artifacts
                    AS PERMISSIVE FOR ALL TO fragility_app_user
                    USING (true) WITH CHECK (true);
            END IF;

            -- Restrictive tenant isolation policy
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies 
                WHERE tablename = 'artifacts' AND policyname = 'tenant_isolation_artifacts'
            ) THEN
                CREATE POLICY tenant_isolation_artifacts ON artifacts
                    AS RESTRICTIVE FOR ALL TO fragility_app_user
                    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
                    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
            END IF;

            GRANT SELECT, INSERT, UPDATE, DELETE ON artifacts TO fragility_app_user;
        END IF;
    END
    $$;
    """)


def downgrade() -> None:
    # 1. Drop artifacts table and policies
    op.execute("""
    DROP TABLE IF EXISTS artifacts CASCADE;
    """)

    # 2. Drop added jobs columns and indexes
    op.execute("""
    DROP INDEX IF EXISTS idx_jobs_lease_expiry;
    DROP INDEX IF EXISTS idx_jobs_claiming;

    ALTER TABLE jobs DROP COLUMN IF EXISTS cancelled_at;
    ALTER TABLE jobs DROP COLUMN IF EXISTS timeout_seconds;
    ALTER TABLE jobs DROP COLUMN IF EXISTS priority;
    ALTER TABLE jobs DROP COLUMN IF EXISTS max_attempts;
    ALTER TABLE jobs DROP COLUMN IF EXISTS attempt_count;
    ALTER TABLE jobs DROP COLUMN IF EXISTS lease_expires_at;
    ALTER TABLE jobs DROP COLUMN IF EXISTS claimed_at;
    ALTER TABLE jobs DROP COLUMN IF EXISTS worker_id;
    """)
