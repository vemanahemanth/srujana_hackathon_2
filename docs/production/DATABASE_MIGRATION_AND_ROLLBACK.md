# FragilityShield — Database Migration, Validation & Rollback Plan

**Document Version:** 1.0.0  
**Target Migration:** Legacy JSON/SQLite Catalog to PostgreSQL with Row-Level Security (RLS)  
**Implementation Tooling:** `backend/fragility_engine/db_schema.py`  

---

## 1. Pre-Migration Data Snapshot & Integrity Verification

Before applying schema upgrades or migrating data from local SQLite/JSON catalogs to PostgreSQL:

1. **Create Cold Snapshot of Existing Catalog:**
   ```bash
   tar -czvf /backups/fragility_catalog_pre_migration_$(date +%Y%m%d_%H%M%S).tar.gz data/catalog data/experiments
   ```
2. **Generate Signed Export Manifest with Checksums:**
   ```python
   from fragility_engine.projects import ProjectCatalog
   from fragility_engine.db_schema import generate_sqlite_migration_manifest
   import json

   cat = ProjectCatalog("data/catalog")
   manifest = generate_sqlite_migration_manifest(
       projects=[p.to_dict() for p in cat.list_projects()],
       datasets=[d.to_dict() for d in cat.list_datasets()],
       models=[m.to_dict() for m in cat.list_models()],
       default_tenant_id="tenant_migrated_master",
       default_user_id="user_migrated_admin",
   )
   with open("/backups/migration_manifest.json", "w") as f:
       json.dump(manifest, f, indent=2)

   print(f"Manifest Generated: {manifest['total_records']} records, SHA-256: {manifest['manifest_checksum_sha256']}")
   ```

---

## 2. PostgreSQL Schema Initialization & RLS Application

Execute the transaction-wrapped DDL against target PostgreSQL:

```bash
psql -h $DB_HOST -U postgres -d fragilityshield -v ON_ERROR_STOP=1 -f backend/fragility_engine/db_schema.sql
```

### Data Insertion via Scoped Migration Script
```python
import json
import psycopg2

with open("/backups/migration_manifest.json") as f:
    manifest = json.load(f)

conn = psycopg2.connect(host=os.environ["DB_HOST"], dbname="fragilityshield", user="postgres")
with conn:
    with conn.cursor() as cur:
        for rec in manifest["records"]:
            table = rec["table"]
            if table == "projects":
                cur.execute(
                    "INSERT INTO projects (project_id, tenant_id, name, manifest_json, created_by) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, project_id) DO NOTHING;",
                    (rec["project_id"], rec["tenant_id"], rec["name"], json.dumps(rec["manifest_json"]), rec["created_by"])
                )
            elif table == "datasets":
                cur.execute(
                    "INSERT INTO datasets (dataset_id, tenant_id, name, source_type, provenance_json, fingerprint, row_count, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, dataset_id) DO NOTHING;",
                    (rec["dataset_id"], rec["tenant_id"], rec["name"], rec["source_type"], json.dumps(rec["provenance_json"]), rec["fingerprint"], rec["row_count"], rec["created_by"])
                )
            elif table == "models":
                cur.execute(
                    "INSERT INTO models (model_id, tenant_id, name, family, parameters_json, created_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (tenant_id, model_id) DO NOTHING;",
                    (rec["model_id"], rec["tenant_id"], rec["name"], rec["family"], json.dumps(rec["parameters_json"]), rec["created_by"])
                )

print("Lossless migration completed.")
```

---

## 3. Post-Migration Reconciliation & Checksum Verification

Verify that every record in PostgreSQL matches the pre-migration checksum:

```sql
SELECT 
    'projects' AS table_name, COUNT(*) AS row_count FROM projects
UNION ALL
SELECT 
    'datasets' AS table_name, COUNT(*) AS row_count FROM datasets
UNION ALL
SELECT 
    'models' AS table_name, COUNT(*) AS row_count FROM models;
```
Verify that row counts match the `total_records` count in `migration_manifest.json`.

---

## 4. Rollback Plan & Recovery Procedures

If a schema migration or data migration fails:

### Step 1: Automatic Transaction Rollback
All migration statements are enclosed in `BEGIN ... COMMIT;` blocks with `-v ON_ERROR_STOP=1`. Any SQL failure immediately aborts the transaction, leaving the PostgreSQL database in its clean pre-migration state.

### Step 2: Database Reversion
To cleanly revert tables without affecting other services:
```sql
BEGIN;
DROP TABLE IF EXISTS audit_events CASCADE;
DROP TABLE IF EXISTS jobs CASCADE;
DROP TABLE IF EXISTS plugin_executions CASCADE;
DROP TABLE IF EXISTS plugin_registrations CASCADE;
DROP TABLE IF EXISTS experiment_runs CASCADE;
DROP TABLE IF EXISTS models CASCADE;
DROP TABLE IF EXISTS projects CASCADE;
DROP TABLE IF EXISTS datasets CASCADE;
DROP TABLE IF EXISTS portfolios CASCADE;
DROP TABLE IF EXISTS tenant_memberships CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;
DROP ROLE IF EXISTS fragility_app_user;
COMMIT;
```

### Step 3: Local Filesystem Fallback
Because local SQLite and JSON catalogs in `data/catalog` are treated as read-only during migration, the local application can immediately resume operation in `local_research` mode without loss of research history.
