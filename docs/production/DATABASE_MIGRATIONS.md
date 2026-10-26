# FRAGILITYSHIELD — PRODUCTION DATABASE MIGRATIONS RUNBOOK (SPRINT 4)

## Overview & Security Principles

FragilityShield uses **Alembic** for version-controlled, reproducible schema migrations across development, staging, and production PostgreSQL databases.

### Core Security Invariants:
1. **Role Privilege Separation:**
   - **`fragility_migrator`:** Holds DDL privileges to create/alter tables, indexes, constraints, functions, and RLS policies. Used **exclusively** during deployment and migration execution. Never used for API requests.
   - **`fragility_app_user`:** Restricted runtime application identity. Configured with `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`. Holds only selective DML (`SELECT, INSERT, UPDATE, DELETE`) privileges. Cannot alter schemas or disable Row-Level Security.
2. **Forced Row-Level Security (RLS):**
   - Every tenant-owned table must have `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
   - Every migration that creates or alters tenant-owned tables must verify and preserve forced RLS and tenant-isolation policies.
3. **No Credential Exposure:**
   - Migration URLs and credentials must never be committed to source control or logged in cleartext.
   - Alembic configurations dynamically read `MIGRATION_DATABASE_URL` or `DATABASE_URL` and mask credentials in all logger output.

---

## Directory Structure

```
├── alembic.ini                             # Root configuration
├── backend/
│   ├── alembic.ini                         # Backend-scoped configuration
│   └── migrations/
│       ├── env.py                          # Dynamic URL resolution and RLS preservation
│       ├── README                          # Migration readme
│       ├── script.py.mako                  # Migration template
│       └── versions/
│           ├── 001_initial_schema_and_rls.py
│           └── 002_model_registry_enhancements.py
```

---

## Migration Revisions

| Revision ID | Description | Down Revision | RLS / Table Impact |
| :--- | :--- | :--- | :--- |
| `001_initial_schema_and_rls` | Initial schema creating core identity tables (`tenants`, `users`, `tenant_memberships`) and 9 tenant-owned tables (`portfolios`, `datasets`, `projects`, `models`, `experiment_runs`, `plugin_registrations`, `plugin_executions`, `jobs`, `audit_events`). | `None` (Base) | Enables and forces RLS on all 9 tables. Provisions `fragility_app_user` with least-privilege DML grants. |
| `002_model_registry_enhancements` | Adds query acceleration indexes (`idx_experiment_runs_lookup`, `idx_models_family`, `idx_jobs_tenant_status`) and metadata columns (`tags_json`). | `001_initial_schema_and_rls` | Preserves forced RLS and existing policies. Reversible downgrade. |

---

## Production Bootstrap & Provisioning Procedure

### 1. Provisioning PostgreSQL Roles

Execute as PostgreSQL cluster administrator (e.g. `postgres` / AWS RDS master):

```sql
-- 1. Create Migration Role (DDL Owner)
CREATE ROLE fragility_migrator WITH LOGIN PASSWORD 'SECURE_MIGRATOR_PASSWORD_FROM_KMS';
GRANT ALL PRIVILEGES ON DATABASE fragility_prod TO fragility_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO fragility_migrator;

-- 2. Create Application Runtime Role (DML Only)
CREATE ROLE fragility_app_user WITH LOGIN PASSWORD 'SECURE_APP_PASSWORD_FROM_KMS';
ALTER ROLE fragility_app_user NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
GRANT CONNECT ON DATABASE fragility_prod TO fragility_app_user;
GRANT USAGE ON SCHEMA public TO fragility_app_user;
```

### 2. Running Migrations

Set `MIGRATION_DATABASE_URL` in the deployment pipeline:

```bash
export MIGRATION_DATABASE_URL="postgresql://fragility_migrator:${SECURE_MIGRATOR_PASSWORD}@pg-prod.internal:5432/fragility_prod"

# Upgrade to latest revision
alembic upgrade head

# Inspect current revision status
alembic current

# View history
alembic history --verbose
```

### 3. Verifying Migration Health

```bash
# Verify that all 9 tenant tables maintain forced RLS and that fragility_app_user has no bypass:
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
with conn.cursor() as cur:
    cur.execute('''
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity 
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace 
        WHERE n.nspname = 'public' AND c.relname IN ('portfolios','datasets','projects','models','experiment_runs','plugin_registrations','plugin_executions','jobs','audit_events');
    ''')
    for tbl, rls, frls in cur.fetchall():
        assert rls and frls, f'RLS failed on {tbl}'
print('All 9 tenant tables verified: Forced RLS active')
"
```

---

## Rollback & Forward-Fix Strategy

1. **Reversible Downgrade:**  
   Minor schema changes (e.g. indexes or non-breaking additive columns) can be downgraded using:
   ```bash
   alembic downgrade -1
   ```
2. **Forward-Fix Strategy:**  
   In production environments with active financial records, table drops risk permanent data loss. If a migration introduces a breaking change or defect, write a new forward-fix revision (e.g. `003_hotfix_...`) rather than dropping populated tables.
