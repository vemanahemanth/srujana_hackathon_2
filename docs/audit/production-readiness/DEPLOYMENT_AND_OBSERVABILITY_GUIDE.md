# FragilityShield — Production Deployment & Observability Runbook

**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Target Environments:** Docker / Kubernetes / Linux Virtual Machines (systemd)  
**Standard:** Phase 10 & 11 — Production Deployment Readiness & Operational Diagnostics  

---

## 1. Environment Configuration Schema

All platform configuration is managed through validated environment variables. Create a `.env` file based on `.env.example`:

| Variable | Type | Mandatory? | Default | Description |
|---|---|---|---|---|
| `ENVIRONMENT` | string | Yes | `production` | Set to `production` or `development` |
| `DATABASE_URL` | string | Yes | `sqlite:///./data/fragility_shield.db` | PostgreSQL (`postgresql+psycopg2://...`) or SQLite |
| `ARTIFACT_STORAGE_PATH` | path | Yes | `./data/artifacts` | Durable local path or mount for reports and manifests |
| `JWT_SECRET` | string | Yes | (Required in prod) | Cryptographic secret for signing auth session tokens |
| `UPSTOX_API_KEY` | string | Optional | `""` | Upstox API key for live NSE feeds (optional in offline mode) |
| `UPSTOX_API_SECRET` | string | Optional | `""` | Upstox API secret for OAuth token exchange |
| `WORKER_CONCURRENCY` | int | No | `4` | Number of background worker processes for long-running calculations |
| `LOG_LEVEL` | string | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 2. Database Migrations

FragilityShield uses **Alembic** for schema migrations.

```bash
# Check current migration revision
alembic current

# Apply all pending migrations to database
alembic upgrade head

# Rollback single migration if needed
alembic downgrade -1
```

All migrations are located in `backend/migrations/` and have been verified on both clean SQLite and PostgreSQL databases.

---

## 3. Production Startup Commands

### Backend API Server
Start Uvicorn behind a production reverse proxy (e.g., Nginx, Traefik, or AWS ALB):
```bash
uvicorn backend.app:app \\
  --host 0.0.0.0 \\
  --port 8000 \\
  --workers 4 \\
  --proxy-headers \\
  --forwarded-allow-ips='*'
```

### Background Calculation Worker
For asynchronous Monte Carlo simulations, stress testing, and batch backtesting:
```bash
python -m backend.fragility_engine.worker --concurrency 4
```

### Frontend Production Build & Hosting
```bash
cd frontend
npm ci
npm run build
# Outputs optimized static bundle to frontend/dist/
```
Serve `frontend/dist/` with Nginx or Caddy with SPA fallback routing enabled (`try_files $uri $uri/ /index.html;`).

---

## 4. Health Checks & Observability Endpoints

FragilityShield provides standardized observability endpoints:

1. **Liveness & Health Check:**
   - `GET /api/health`
   - Response: `{"status": "healthy", "version": "1.0.0", "timestamp": "2026-10-26T04:20:00Z"}`
2. **Worker Status & Queue Diagnostics:**
   - `GET /api/workers/status`
   - Response:
     ```json
     {
       "success": true,
       "worker": {
         "status": "healthy",
         "active_workers": 1,
         "jobs_processed": 14,
         "queue_backlog": 0,
         "last_heartbeat": 1792969000
       }
     }
     ```
3. **Security & Session Diagnostics:**
   - `GET /api/security/status`
   - Returns tenant isolation mode, RLS status, and active authentication provider.

---

## 5. Rollback Procedure

If a deployment defect is detected in production:
1. **Frontend Rollback:** Point reverse proxy static root back to previous release build directory (`dist_prev/`).
2. **Backend Rollback:** Stop current Uvicorn process; restore previous release virtualenv/container; restart service.
3. **Database Rollback:** Run `alembic downgrade -1` only if the failed release introduced an incompatible schema change.