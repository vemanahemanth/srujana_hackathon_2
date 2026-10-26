# Sprint 5 Discovery & Test Baseline Report
## Isolated Experiment Workers, Asynchronous Execution, Secure Artifact Storage & Reproducibility

**Date:** 2026-10-25  
**Baseline Git Commit:** `74ef3fe7ad6f9ef681e8eab66cf0c080438637f7`  
**Test Baseline Status:** **685 passed, 0 failed, 1 warning in 6.11s**  

---

### 1. Existing Architecture & Source Files

FragilityShield is an assumption-aware financial risk, scenario analysis, and model-validation laboratory. The repository consists of a FastAPI backend with PostgreSQL multi-tenant isolation, forced Row-Level Security (RLS), and a Vanilla JavaScript frontend.

Key inspected source components:
- [`backend/app.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py): Application entry point, HTTP routing, tenant context extraction, RBAC authorization, custom model execution routes (`/api/models/execute`, `/api/models/jobs/{id}`, `/api/models/jobs/{id}/cancel`).
- [`backend/fragility_engine/database.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/database.py): Dual-mode repository (`PostgresTenantRepository` vs `MemoryTenantRepository`), database connection pool (`psycopg2.pool.ThreadedConnectionPool`), transaction-local `SET LOCAL app.current_tenant_id` context.
- [`backend/fragility_engine/db_schema.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/db_schema.py): Core schema definitions, 12 tables, forced RLS policies on 9 tenant tables (`portfolios`, `datasets`, `projects`, `models`, `experiment_runs`, `plugin_registrations`, `plugin_executions`, `jobs`, `audit_events`).
- [`backend/fragility_engine/tenancy.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/tenancy.py): JWT validation, RBAC permissions (`RISK_EXECUTE`, `DATASET_WRITE`, etc.), membership checks.
- [`backend/fragility_engine/model_sandbox.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/model_sandbox.py): Contract validation for 5 financial model categories (`ALLOCATION`, `FORECASTING`, `RISK_ESTIMATION`, `TRADING_STRATEGY`, `SCENARIO_RESPONSE`), finite float checks (rejecting NaN/Inf), fail-closed sandbox adapter.
- [`backend/fragility_engine/reproducibility.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/reproducibility.py): `canonical_json_dumps`, cryptographic SHA-256 fingerprinting, invariant checks.
- [`backend/fragility_engine/projects.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/projects.py): `ArtifactEntity`, `ProjectCatalog`.
- [`backend/migrations/`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/migrations/): Alembic migration revisions (`001_initial_schema_and_rls`, `002_model_registry_enhancements`).

---

### 2. Existing Job & Artifact Lifecycle

#### Current Job Table Schema (`jobs`):
```sql
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
```

#### Identified Gaps in Current Job Model:
1. **Lack of Concurrency-Safe Claiming**: No `claimed_by` (worker ID), `lease_expires_at`, or `claimed_at` columns.
2. **Missing Attempt Tracking & Retries**: No `attempt_count` or `max_attempts` tracking.
3. **Missing Lifecycle States**: Current status transitions are limited (`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`). Need formal support for `CLAIMED`, `TIMED_OUT`, `CANCEL_REQUESTED`.
4. **Execution Boundary**: When `/api/models/execute` is called in `TRUSTED_LOCAL_RESEARCH` mode, it executes synchronously in the HTTP request handler thread, violating the core principle that model execution must be an isolated asynchronous experiment.

#### Identified Gaps in Artifact Storage:
1. **No First-Class Artifact Table**: Artifacts are represented in memory or as loose filesystem files without a dedicated PostgreSQL table enforcing Row-Level Security.
2. **Missing Storage Abstraction**: No unified `ArtifactStorage` adapter with pluggable local filesystem and S3/object-storage backends.
3. **No Secure Download Authorization**: No authorized endpoints for downloading artifacts with short-lived tokens, size limits, streaming, and content-type validation.

---

### 3. Existing Security Controls & Policies

1. **Transaction-Local PostgreSQL RLS**: Every query sets `app.current_tenant_id` within a transaction. Blank or missing context strictly denies access (`NULLIF(..., '')`).
2. **Dual Database Roles**: `fragility_migrator` (DDL owner) vs `fragility_app_user` (restricted DML runtime role without superuser or `BYPASSRLS`).
3. **Fail-Closed Container Sandbox**: If no running container runtime is detected, untrusted model execution throws `SandboxSecurityError` (HTTP 503) rather than falling back to host execution.
4. **Numerical Validation**: Rejects `NaN`, `+Inf`, `-Inf` and verifies mathematical constraints (e.g., portfolio weights sum to 1.0, non-negative risk metrics).

---

### 4. Baseline Test Results

Command:
```bash
PYTHONPATH=.:backend /opt/anaconda3/bin/pytest backend/tests -q
```
Result:
```
685 passed, 1 warning in 6.11s
```
Zero failures, zero regressions from Sprint 4.

---

### 5. Architectural Decisions for Sprint 5

1. **PostgreSQL-Backed Job Queue with `FOR UPDATE SKIP LOCKED`**:
   - Rather than introducing Celery/Redis dependencies immediately (which would complicate local single-user research and lightweight deployment), implement an enterprise-grade PostgreSQL queue adapter leveraging transaction-level row locking (`FOR UPDATE SKIP LOCKED`), worker lease expiry, and heartbeats.
   - For environments running in `local_research` mode with SQLite/Memory repository, provide an in-memory queue adapter sharing the exact same worker interface.
2. **Alembic Schema Migration (`003_sprint5_jobs_and_artifacts.py`)**:
   - Enhance `jobs` table with `worker_id`, `claimed_at`, `lease_expires_at`, `attempt_count`, `max_attempts`, `priority`, `cancelled_at`, `timeout_seconds`.
   - Create `artifacts` table with `tenant_id`, `artifact_id`, `job_id`, `experiment_id`, `logical_type`, `storage_key`, `content_hash` (SHA-256), `size_bytes`, `media_type`, `created_at`, `expires_at`.
   - Enforce `ENABLE ROW LEVEL SECURITY; FORCE ROW LEVEL SECURITY;` on `artifacts`.
   - Add grants for `fragility_app_user`.
3. **Tenant-Safe Artifact Storage Service**:
   - Pluggable `ArtifactStorage` interface with `LocalFilesystemArtifactStorage` (chrooted, path-traversal resistant, streaming, SHA-256 checksumming) and `S3CompatibleArtifactStorage`.
   - API endpoints:
     - `GET /api/artifacts/{id}/download`: Streams authorized artifact binary.
     - `GET /api/artifacts/{id}/metadata`: Retrieves artifact metadata and verified hash.
4. **Worker Daemon & Execution Engine**:
   - Background worker process (`FragilityExperimentWorker`) that polls/claims jobs using `FOR UPDATE SKIP LOCKED`.
   - Heartbeat loop extending leases during long-running tasks.
   - Automatic lease recovery: orphaned jobs whose workers crashed or failed to heartbeat are re-queued or marked `TIMED_OUT`.
   - Worker diagnostics endpoint: `/api/workers/status` (authorized for admin/operators).
5. **Versioned Reproducibility Manifest**:
   - Integration of `reproducibility.py` manifests into job completion payloads, recording input dataset hashes, parameter fingerprints, software environment hashes, and output hashes.
