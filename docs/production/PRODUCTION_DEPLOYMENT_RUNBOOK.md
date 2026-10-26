# FragilityShield — Production Deployment Runbook

**Document Version:** 1.0.0  
**Target Environments:**  
1. Local Research / Intranet Workstation (Single-User SQLite)  
2. Hosted Single-User (AppSail / Reverse Proxy Gateway)  
3. Public Multi-Tenant Cloud (Managed PostgreSQL with Active RLS + Isolated Worker Sandbox)  

---

## 1. Deployment Profile Selection Matrix

| Deployment Profile | Database Engine | Isolation Mechanism | Third-Party Plugins | Release Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **`local_research`** | Local SQLite / JSON Catalog | Process Memory / Single User | Built-in Only | **GO — APPROVED / VERIFIED** |
| **`hosted_single_user`** | SQLite / Managed PostgreSQL | Authenticated Ingress Gateway | Built-in Only | **GO — CONDITIONALLY APPROVED** |
| **`public_multi_tenant`** | Managed PostgreSQL 14+ | PostgreSQL Row-Level Security | Hardened Container / gVisor | **NO-GO (Requires provisioned PostgreSQL)** |
| **`untrusted_plugins`** | N/A | Container / gVisor runsc | Sandbox Worker | **NO-GO (Requires provisioned sandbox)** |

---

## 2. Environment Variables & Secret Configuration

Never commit secrets to Git. Configure the following environment variables via AWS Secrets Manager, HashiCorp Vault, or Zoho Catalyst Console:

| Variable Name | Required Mode | Purpose | Example Value |
| :--- | :--- | :--- | :--- |
| `DEPLOYMENT_MODE` | All | Enforces security checks (`local_research`, `hosted_single_user`, `public_multi_tenant`). | `public_multi_tenant` |
| `DATABASE_URL` | Multi-Tenant | PostgreSQL connection string. Must NOT be SQLite in multi-tenant mode. | `postgresql+asyncpg://app_user:pw@db.internal:5432/fragility` |
| `FRAGILITY_JWT_SECRET` | Hosted / Multi-Tenant | Cryptographic HMAC-SHA256 signing key ($\ge 32$ characters). | `k9X#m2$pL8vR!zQ4wT7bY@uC1eN5gH0s` |
| `ALLOWED_CORS_ORIGINS` | Multi-Tenant | Comma-separated domain allowlist. Wildcard `*` is strictly rejected in multi-tenant mode. | `https://app.fragilityshield.com` |
| `CONTAINER_RUNTIME_PATH` | Plugins | Path to Docker/Podman/gVisor binary for sandbox worker. | `/usr/bin/docker` or `/usr/local/bin/runsc` |
| `UPSTOX_API_KEY` | Market Data | Read-only Upstox developer key. | Redacted in deployment manifests |
| `UPSTOX_API_SECRET` | Market Data | Read-only Upstox secret key. | Redacted in deployment manifests |
| `UPSTOX_REDIRECT_URI` | Market Data | Authorized OAuth callback URI. | `https://app.fragilityshield.com/api/upstox/callback` |

---

## 3. Step-by-Step Deployment Procedure

### Step 1: Pre-Flight Security & Regression Verification
Run the 623-test automated regression suite:
```bash
PYTHONPATH=.:backend /opt/anaconda3/bin/pytest backend/tests
```
Assert exit code `0` and zero failures.

### Step 2: Database Migration & RLS Policy Application
If deploying in `public_multi_tenant` mode, execute the schema DDL against the managed PostgreSQL database:
```bash
psql -h $DB_HOST -U postgres -d fragilityshield -f backend/fragility_engine/db_schema.sql
```
Verify that RLS is active:
```sql
SELECT relname, relrowsecurity, relforcerowsecurity 
FROM pg_class 
WHERE relname IN ('portfolios', 'datasets', 'projects', 'models');
-- relrowsecurity must be TRUE, relforcerowsecurity must be TRUE
```

### Step 3: Run Configuration Validation
Execute the fail-closed security validator before starting the web server:
```bash
python -c "
from fragility_engine.db_schema import verify_production_security_configuration
import os
verify_production_security_configuration(
    deployment_mode=os.environ.get('DEPLOYMENT_MODE', 'public_multi_tenant'),
    database_url=os.environ['DATABASE_URL'],
    jwt_secret=os.environ['FRAGILITY_JWT_SECRET'],
    cors_origins=os.environ.get('ALLOWED_CORS_ORIGINS', '').split(','),
)
print('Production security configuration VERIFIED.')
"
```

### Step 4: Container Build & Service Launch
```bash
docker build -t fragilityshield:v1.0.0 .
docker run -d \
  --name fragility_app \
  -p 8000:8000 \
  --env-file /etc/fragilityshield/production.env \
  fragilityshield:v1.0.0
```

### Step 5: Post-Deployment Smoke Verification
```bash
# 1. Health Probe
curl -s http://localhost:8000/api/health | grep '"status":"healthy"'

# 2. Security Posture Probe
curl -s http://localhost:8000/api/security/status | grep '"success":true'

# 3. Defensive Security Headers Verification
curl -I http://localhost:8000/api/health | grep -i "x-content-type-options: nosniff"
curl -I http://localhost:8000/api/health | grep -i "x-frame-options: DENY"
```
