# FragilityShield — Zoho Catalyst Deployment Architecture & Feasibility Analysis

## 1. Executive Summary

FragilityShield is designed to deploy to **Zoho Catalyst**, Zoho's serverless and cloud application platform. This document defines the defensible deployment architecture, runtime requirements, network constraints, persistence models, secret management, and operational boundaries on Zoho Catalyst.

---

## 2. Zoho Catalyst Service Selection: AppSail vs. Functions

Zoho Catalyst provides two primary compute models for backend services:
1. **Catalyst Serverless Functions (Python):**
   - *Constraints:* 15-minute maximum execution timeout, ephemeral read-only filesystem (except `/tmp`), cold starts, restrictive binary dependency packaging, stateless execution.
   - *Verdict:* Incompatible with long-running quantitative simulations, walk-forward tournaments, and SQLite database persistence.
2. **Catalyst AppSail (Standalone Container Service):**
   - *Capabilities:* Runs custom containerized web applications (FastAPI/Uvicorn), supports persistent connections, configurable RAM (up to 4 GB) and vCPU, exposed HTTP/HTTPS port, persistent logs.
   - *Verdict:* **Recommended & Selected Target.** AppSail allows running the complete FastAPI backend alongside the static frontend with predictable execution.

---

## 3. Architecture Specification

```
[ Client Browser / CLI / SDK ]
               |
               v (HTTPS :443)
[ Zoho Catalyst API Gateway / Custom Domain ]
               |
      [ JWT / Auth Verification ]
               |
               v
[ Zoho Catalyst AppSail (Docker Container) ]
  ├── Port: 8000 (Internal)
  ├── Runtime: Python 3.11 / 3.12 (Debian Slim)
  ├── Web Server: Uvicorn (ASGI)
  ├── App Framework: FastAPI
  ├── Static Files: /frontend mounted at /
  ├── SQLite Database: /data/fragilityshield.db (Mounted Volume or Catalyst Data Store)
  └── Quantitative Engine: NumPy / SciPy / Pandas / Scikit-Learn
               |
               v (Outbound HTTPS :443)
  [ Upstox API v3 (api.upstox.com) ]
```

---

## 4. Key Deployment Constraints & Enforcements

### 4.1 Persistence & Data Storage
- **Ephemeral Storage Warning:** Default AppSail container filesystems are ephemeral. Any restarts or deployments will wipe local SQLite databases stored in container root.
- **Production Solution:**
  1. Mount a Catalyst Cloud Storage / Persistent Volume to `/data`, OR
  2. Substitute the SQLite database driver with an external managed PostgreSQL database (e.g., Supabase, RDS, or Cloud SQL) using the standard `DATABASE_URL` environment variable.

### 4.2 Network & Upstox Ingress/Egress
- AppSail instances have outbound Internet access over standard ports 80/443.
- Calls to `api.upstox.com` for historical candles and live quotes succeed without dedicated VPC peering.
- OAuth redirect URL (`UPSTOX_REDIRECT_URI`) must match the Catalyst AppSail public URL registered in the Upstox Developer Console.

### 4.3 Secrets Management
- All sensitive variables (`UPSTOX_CLIENT_ID`, `UPSTOX_CLIENT_SECRET`, `UPSTOX_ACCESS_TOKEN`, `SECRET_KEY`) must be configured via **Catalyst Environment Variables** in the Catalyst Console.
- Never bake `.env` or credentials into the Docker container image.

### 4.4 Multi-Tenant Warning & Release Boundary
- Zoho Catalyst does not inherently partition database rows between users unless application-level tenancy or Catalyst Authentication is enforced.
- Because FragilityShield currently operates without multi-tenant row-level security (RLS), **hosted deployment on Catalyst is classified as a SECURED SINGLE-TENANT RELEASE**.
- An upstream HTTP Basic Auth or Catalyst API Gateway token layer MUST protect access to the AppSail instance.
