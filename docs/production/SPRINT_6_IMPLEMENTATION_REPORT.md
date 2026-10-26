# Sprint 6 Implementation Report: Frontend Replacement & Safe Backend Integration

**Document Version:** 1.0.0  
**Date:** October 25, 2026  
**Status:** COMPLETE & VERIFIED  
**Canonical Frontend:** `frontend/` (React 19 / TypeScript / Vite / Tailwind CSS)  
**Backend:** FastAPI / Starlette (`backend/app.py`) & FragilityEngine (`backend/fragility_engine/`)  

---

## Executive Summary

Sprint 6 successfully executed the full replacement of FragilityShield's legacy vanilla HTML/JavaScript frontend with the modern, high-density React 19 / TypeScript quantitative research terminal originally generated in `frontend/Fragility-Shield/artifacts/fragilityshield`. 

The new frontend was decoupled from Replit platform dependencies, promoted to the canonical project location at `frontend/`, configured with standard npm packaging and Vite tooling, and connected via a typed API client (`frontend/src/lib/api.ts`) to real FastAPI backend endpoints. All legacy frontend assets were backed up into `legacy_frontend_backup/` before removal.

All 701 backend regression tests pass with 0 failures, the frontend builds and typechecks cleanly with 0 TypeScript errors, and end-to-end integration verifies live portfolio metrics calculation, stress testing, fragility audits, async job execution, and artifact downloads.

---

## 1. Frontend Identification

The new frontend was definitively identified at:
- **Discovered Location:** `frontend/Fragility-Shield/artifacts/fragilityshield`
- **Framework & Stack:** React 19 (`react: ^19.0.0`), TypeScript 5.7, Vite 6, Tailwind CSS 4, Radix UI primitives, Lucide React icons, Recharts, and TanStack React Query.
- **Visual Identity:** High-density institutional dark-mode terminal (`bg-zinc-950`, slate borders, mono fonts, quantitative risk telemetry cards, interactive SVG charts, tabbed analytical laboratories).
- **Canonical Destination:** Promoted to the root `frontend/` directory of the repository.

---

## 2. Legacy Frontend Removal

Before removing any files, a complete non-destructive backup was created in `legacy_frontend_backup/`. The following obsolete application files were removed from `frontend/`:
1. `frontend/app.js` — Legacy monolithic vanilla JavaScript client with hardcoded mock handlers and basic SVG renderers.
2. `frontend/style.css` — Legacy custom stylesheet with static CSS variable definitions.
3. Nested Replit artifact directory `frontend/Fragility-Shield/` — Completely consolidated into the top-level `frontend/` directory.

---

## 3. Retained & Migrated Files

### Migrated into Canonical `frontend/`
- `frontend/src/` — Complete React component tree:
  - `src/App.tsx`: Main quantitative dashboard layout, navigation tabs, laboratory orchestrator, and metrics panels.
  - `src/components/ui/`: Radix-based UI components (buttons, cards, dialogs, tabs, progress bars, toasts, tooltips).
  - `src/components/labs/`: Dedicated analytical lab views (Portfolio Risk Lab, Scenario Lab, Fragility Lab, Model Sandbox, Assumption Registry, Worker Queue, Data Provenance, Upstox Connector).
  - `src/lib/api.ts`: Typed API client connecting to FastAPI backend services.
- `frontend/public/` — Static assets, icons, and SVG illustrations.
- `frontend/index.html` — HTML shell configured for modern Vite entrypoint (`/src/main.tsx`).
- `frontend/package.json` — Cleaned and migrated from Replit catalog references to standard npm dependencies.
- `frontend/tsconfig.json` — TypeScript configuration with Vite client types and ESNext module resolution.
- `frontend/vite.config.ts` — Vite configuration with React and Tailwind plugins and an API proxy (`/api -> http://127.0.0.1:8000`).

### Preserved in `legacy_frontend_backup/`
- `legacy_frontend_backup/app.js`
- `legacy_frontend_backup/style.css`
- `legacy_frontend_backup/index.html`
- `legacy_frontend_backup/README.md`

### Unaltered Backend & Research Infrastructure
- No backend calculation engines (`backend/fragility_engine/`), database models, migrations, RLS policies, background workers, or test fixtures were modified or deleted.

---

## 4. Connected Real Backend Endpoints

The typed API client (`frontend/src/lib/api.ts`) communicates directly with the following live FastAPI endpoints:

| Endpoint | Method | Backend Handler | Connected Frontend Component |
| :--- | :--- | :--- | :--- |
| `/api/health` | `GET` | `api_health` | System Status Badge, Telemetry Bar |
| `/api/portfolios/sample` | `GET` | `api_load_sample_portfolio` | Portfolio Selector & Asset Concentration Card |
| `/api/portfolio/load` | `POST` | `api_portfolio_load` | Custom Portfolio Ingestion & File Upload |
| `/api/risk/calculate` | `POST` | `api_risk_calculate` | Risk Lab: VaR 95%, CVaR 95%, Volatility, Sharpe, Drawdown |
| `/api/scenarios/run` | `POST` | `api_scenarios_run` | Scenario Lab: Multi-Asset Shocks, Sector Contagion, P&L Waterfall |
| `/api/fragility/run` | `POST` | `api_fragility_run` | Fragility Lab: 5-Vector Adversarial Attacks & Sensitivity Ranking |
| `/api/workers/jobs` | `POST` | `api_submit_worker_job` | Async Workload Submitter (Heavy Monte Carlo / Backtesting) |
| `/api/workers/jobs/{id}`| `GET` | `api_get_worker_job_status` | Asynchronous Job Queue Poller & Execution Progress Bar |
| `/api/artifacts/{id}` | `GET` | `api_download_artifact` | Artifact Storage Browser & Signed Download Trigger |
| `/api/diagnostics/run` | `POST` | `api_diagnostics_run` | Data Provenance & Anomaly Diagnostics Scanner |

---

## 5. End-to-End Verified Workflows

1. **Portfolio Ingestion & Inspection:**
   - Loading the canonical ₹10 Lakh NSE portfolio (`nse_10l_illustrative`) resolves holdings (INFY, TCS, HDFCBANK, RELIANCE, etc.), asset weights, sector allocations, and current market values.
2. **Coherent Tail Risk Evaluation:**
   - Submitting active portfolio returns to `/api/risk/calculate` executes the Acerbi-Tasche Expected Shortfall and Cornish-Fisher VaR calculations, returning real quantitative metrics (Annualized Volatility, 95% Historical VaR, 95% Parametric VaR, Expected Shortfall, Maximum Drawdown, Sharpe Ratio).
3. **Macro Scenario Stress Testing:**
   - Applying simultaneous equity and sector shocks to `/api/scenarios/run` calculates holding-level P&L and portfolio drawdown with full mathematical reconciliation.
4. **Fragility & Sensitivity Auditing:**
   - Submitting returns to `/api/fragility/run` runs 5 adversarial perturbations (distributional shift, tail fatness, correlation breakdown, liquidity dry-up, volatility regime change) and ranks assumption fragility.
5. **Asynchronous Experiment Execution:**
   - Long-running calculations can be submitted to `/api/workers/jobs`, assigning a UUID job ID, executing via the isolated worker system, and polling status until completion.
6. **Artifact Storage & Manifests:**
   - Experiment results and reproducibility manifests can be listed and downloaded through the secure artifact storage manager (`/api/artifacts/{id}`).

---

## 6. Missing Backend Capabilities Implemented / Refined

1. **Query Parameter Compatibility for Sample Portfolios:**
   - Refined `api_load_sample_portfolio` in `backend/app.py` to accept both `name` and `id` query parameters (`?id=nse_10l_illustrative`), ensuring backwards compatibility with both legacy calls and modern terminal selector components.
2. **Dual-Mode Static Asset Mounting:**
   - Updated `backend/app.py` to check for compiled production assets in `frontend/dist`. When `frontend/dist` exists, FastAPI mounts `dist/` at `/` for single-process deployments; otherwise, it falls back gracefully to `frontend/`.
3. **CORS Configuration for Modern Tooling:**
   - Explicitly allowed `http://localhost:5173` and `http://127.0.0.1:5173` in `ALLOWED_CORS_ORIGINS` to allow seamless Vite HMR during local research and development.

---

## 7. Frontend Issues Identified & Resolved

1. **Replit Platform Coupling Removed:**
   - The initial frontend build required proprietary Replit Vite plugins (`@replit/vite-plugin-runtime-error-modal`, `@replit/vite-plugin-cartographer`) and non-standard environment variables (`PORT`, `BASE_PATH`), which broke builds on local machines and standard CI/CD. These were replaced with standard `@vitejs/plugin-react` and `@tailwindcss/vite`.
2. **Package Manager Normalization:**
   - Removed pnpm catalog references (`catalog:`) and macOS-excluded binaries, generating a standard `frontend/package.json` and clean lockfile installable via standard `npm install`.
3. **TypeScript Module Declarations:**
   - Configured `frontend/tsconfig.json` with `"types": ["vite/client", "node"]` and resolved all ImportMeta environment typing issues.
4. **Mock Replacement with Live Data:**
   - Replaced static placeholder metric constants in `App.tsx` with dynamic state populated from the typed API client upon portfolio selection and lab execution.
5. **FastAPI Route Shadowing Prevention:**
   - Ensured static file mount in `backend/app.py` does not shadow `/api/*` endpoints.

---

## 8. Security Boundaries & Verification

1. **Tenant Isolation & Row-Level Security:**
   - Backend PostgreSQL RLS policies remain authoritative. Requests derive tenant identity from JWT credentials or authenticated context; client-side requests cannot override tenant boundaries.
2. **Fail-Closed Custom Model Sandbox Limitation:**
   - FragilityShield enforces a strict fail-closed policy: untrusted custom model code is never executed in the main API process or browser. In environments lacking containerized gVisor/Docker isolation, the frontend displays an explicit security badge: `"Untrusted Sandbox Unavailable (Fail-Closed Policy Enforced)"`.
3. **No Credential Leakage:**
   - No database URLs, JWT signing secrets, or broker API keys are embedded in frontend source code or client bundles. All backend configuration is loaded from environment variables.
4. **CORS Boundary:**
   - CORS is restricted to defined origins (`localhost:8000`, `localhost:5173`, `127.0.0.1:8000`, `127.0.0.1:5173`). Wildcard `*` origins with credentials remain forbidden.

---

## 9. Test Execution & Verified Results

### Frontend Test Verification
- **TypeScript Typecheck:**
  ```bash
  npm run typecheck --prefix frontend
  ```
  **Result:** 0 errors. Clean pass.
- **Production Build Compilation:**
  ```bash
  npm run build --prefix frontend
  ```
  **Result:** Clean build in 1.93s producing optimized assets in `frontend/dist/`.

### Backend & Integration Test Verification
- **Command:**
  ```bash
  PYTHONPATH=.:backend /opt/anaconda3/bin/pytest backend/tests -q
  ```
  **Result:** **701 passed**, 1 warning in 6.79s.
  - Unit tests: Passed (446 tests)
  - Sprint 5 worker and artifact tests: Passed (35 tests)
  - Sprint 6 frontend integration suite: Passed (4 tests)
    - `test_frontend_dist_or_root_served`: Passed
    - `test_frontend_static_assets_delivered`: Passed
    - `test_api_routes_not_shadowed_by_frontend_mount`: Passed
    - `test_sample_portfolio_api_accessible_for_frontend`: Passed
  - Database, RLS, and security tests: Passed (216 tests)
- **Linter Check:**
  ```bash
  /opt/anaconda3/bin/ruff check backend/app.py backend/tests/test_frontend_integration.py
  ```
  **Result:** All checks passed (0 lint errors).

---

## 10. Tests Not Run & Environment Blockers

- **Real Upstox Live Broker Execution:**
  - Live order routing tests against the Upstox v2 broker API require active user OAuth tokens and API secret keys. Mock and adapter tests passed, but live broker transmission was skipped to prevent unauthenticated network calls.
- **Docker / gVisor Containerized Worker Isolation:**
  - In local development without a running Docker daemon, background workers run in secure subprocess fallback mode with restricted environment variables, while untrusted custom model execution remains safely disabled (fail-closed).

---

## 11. Remaining Non-Blocking Limitations

1. **Broker Live Feed:** The Upstox live tick connector requires real user credentials configured via environment variables or the API key entry modal.
2. **Container Sandbox Deployment:** Full multi-tenant untrusted user code execution requires a deployed container worker pool (e.g. Kubernetes with gVisor).

---

## 12. Application Startup Guide

### Option 1: Production Single-Process (Recommended)
```bash
# 1. Build the production React frontend bundle
cd frontend && npm install && npm run build && cd ..

# 2. Start the unified backend & frontend server
python -m backend.app
```
Access at: **`http://127.0.0.1:8000`**

### Option 2: Active Development (HMR & Hot Reload)
```bash
# Terminal 1: Backend API
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Frontend Vite Dev Server
cd frontend
npm run dev
```
Access at: **`http://localhost:5173`**

---

## 13. Verdict on Sprint 6 Frontend Replacement

**Verdict: COMPLETE & CANONICAL.**

The new React 19 / TypeScript quantitative research terminal is now the official and primary user interface for FragilityShield. The legacy vanilla HTML/JS frontend has been safely archived in `legacy_frontend_backup/` and removed from `frontend/`. Full API connectivity is verified, and all automated tests across frontend and backend pass without regressions.
