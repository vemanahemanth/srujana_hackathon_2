# FragilityShield — Production Deployment, Operations & Rollback Runbook

**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Target Environments:** Docker Container, Linux VM (systemd), or Kubernetes  

---

## 1. System Requirements & Environment Variables

Create `.env` in the project root:
```ini
ENVIRONMENT=production
DATABASE_URL=sqlite:///./data/fragility_shield.db
ARTIFACT_STORAGE_PATH=./data/artifacts
JWT_SECRET=replace_with_strong_cryptographic_secret_in_prod
WORKER_CONCURRENCY=4
LOG_LEVEL=INFO

# Optional Live Upstox Credentials
UPSTOX_API_KEY=
UPSTOX_API_SECRET=
```

---

## 2. Database Migrations

Apply database migrations using Alembic:
```bash
# Check current database state
alembic current

# Run forward migrations
alembic upgrade head
```

---

## 3. Production Deployment Commands

### Backend API Server (Uvicorn / FastAPI / Starlette)
```bash
uvicorn backend.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --proxy-headers \
  --forwarded-allow-ips='*'
```

### Background Worker Process
```bash
python -m backend.fragility_engine.worker --concurrency 4
```

### Frontend Production Build & Static Serving
```bash
cd frontend
npm ci
npm run build
```
Host the generated `frontend/dist/` directory with Nginx or Caddy with SPA fallback routing enabled (`try_files $uri $uri/ /index.html;`).

---

## 4. Health Checks & Monitoring

- **API Health:** `GET http://localhost:8000/api/health`
- **Worker Diagnostics:** `GET http://localhost:8000/api/workers/status`
- **Security Diagnostics:** `GET http://localhost:8000/api/security/status`

---

## 5. Rollback Procedures

If a critical defect is identified post-release:
1. **Frontend Rollback:** Switch Nginx static root symlink to the previous build artifact directory (`dist_previous/`).
2. **Backend Rollback:** Stop current Uvicorn process; restore previous virtual environment / container tag; restart service.
3. **Database Rollback:** If the release applied a schema migration, revert the single migration:
   ```bash
   alembic downgrade -1
   ```