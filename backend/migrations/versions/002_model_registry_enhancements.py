"""002 Model Registry Enhancements and Query Acceleration

Revision ID: 002_model_registry_enhancements
Revises: 001_initial_schema_and_rls
Create Date: 2026-10-25 12:35:00.000000

Demonstrates incremental schema evolution:
1. Adds query acceleration composite indexes for tenant-scoped lookups.
2. Adds tags_json metadata columns to models and projects.
3. Preserves forced Row-Level Security (RLS) across altered tables.
"""

from typing import Sequence, Union
from alembic import op

revision: str = "002_model_registry_enhancements"
down_revision: Union[str, Sequence[str], None] = "001_initial_schema_and_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add metadata columns
    op.execute("""
    ALTER TABLE models ADD COLUMN IF NOT EXISTS tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE projects ADD COLUMN IF NOT EXISTS tags_json JSONB NOT NULL DEFAULT '[]'::jsonb;
    """)

    # 2. Add query acceleration indexes
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_experiment_runs_lookup ON experiment_runs(tenant_id, experiment_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_models_family ON models(tenant_id, family);
    CREATE INDEX IF NOT EXISTS idx_jobs_tenant_status ON jobs(tenant_id, status);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS idx_jobs_tenant_status;
    DROP INDEX IF EXISTS idx_models_family;
    DROP INDEX IF EXISTS idx_experiment_runs_lookup;
    ALTER TABLE projects DROP COLUMN IF EXISTS tags_json;
    ALTER TABLE models DROP COLUMN IF EXISTS tags_json;
    """)
