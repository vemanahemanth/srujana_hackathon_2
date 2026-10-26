# FragilityShield — Deployment Runbook (Zoho Catalyst AppSail)

## 1. Prerequisites

Before initiating deployment:
1. **Zoho Catalyst CLI:** Installed via `npm install -g zcatalyst-cli` and logged in (`catalyst login`).
2. **Docker Engine:** Local daemon running for container build validation.
3. **Upstox Developer Account:** Active API key, API secret, and authorized redirect URI.
4. **Clean Baseline:** All 585 tests passing locally.

---

## 2. Containerization: Dockerfile Specification

Create the production `Dockerfile` in repository root:

```dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install system dependencies for NumPy/SciPy build if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and frontend source
COPY backend /app/backend
COPY frontend /app/frontend

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Start Uvicorn web server
CMD ["uvicorn", "backend.fragility_engine.studio:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3. Catalyst Project Configuration (`catalyst.json`)

```json
{
  "appsail": [
    {
      "name": "fragilityshield",
      "source": ".",
      "build": "docker",
      "env_variables": {
        "ENV": "production",
        "PORT": "8000"
      }
    }
  ]
}
```

---

## 4. Deployment Steps

### Step 1: Pre-Flight Verification
Run the complete regression test suite:
```bash
pytest backend/tests -v
```

### Step 2: Local Container Smoke Test
```bash
docker build -t fragilityshield:latest .
docker run -p 8000:8000 --env-file .env.example fragilityshield:latest
# Verify health endpoint
curl -s http://localhost:8000/api/v1/health | grep '"status":"ok"'
```

### Step 3: Deploy via Catalyst CLI
```bash
catalyst appsail:deploy --app fragilityshield
```

### Step 4: Configure Production Secrets in Catalyst Console
Navigate to **Catalyst Console > AppSail > Environment Variables** and populate:
- `UPSTOX_CLIENT_ID`
- `UPSTOX_CLIENT_SECRET`
- `UPSTOX_REDIRECT_URI`
- `SECRET_KEY` (minimum 32-character high-entropy secret)

### Step 5: Post-Deployment Smoke Verification
Execute the verification probe against the live URL:
```bash
curl -I https://fragilityshield.catalystservers.com/api/v1/health
```
Ensure HTTP 200 is returned.
