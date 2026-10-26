# FragilityShield — Sprint 6 Frontend Replacement Baseline

**Date:** 2026-10-25  
**Baseline Git Commit:** `74ef3fe7ad6f9ef681e8eab66cf0c080438637f7`  
**Security Status:** SPRINT 6 DISCOVERY & BASELINE  
**Backend Test Baseline:** 697 passed, 1 warning in 6.51s (100% pass rate)

---

## 1. Identification of Frontends

### 1.1 Old Legacy Frontend
- **Root Directory:** `/Users/vemanahemanthbabu/srujana_hackathon_2/frontend`
- **Source Files:**
  - `frontend/index.html` (63 KB): Monolithic HTML5 file with inline modal templates and tab containers.
  - `frontend/app.js` (65.5 KB): Vanilla JavaScript class `FragilityShieldApp` orchestrating manual DOM manipulation, inline SVG chart generation, and raw `fetch` calls.
  - `frontend/style.css` (15.6 KB): Handcrafted CSS with basic custom properties.
  - `frontend/README.md` (1.7 KB): Conceptual overview specifying a planned React/Vite migration.
- **Serving Mechanism:** FastAPI/Starlette `StaticFiles` mounted at `/` pointing directly to `BASE_DIR / "frontend"`.
- **Status & Limitations:** Single-page prototype with no framework, no component isolation, no TypeScript type safety, limited styling, and fragile imperative DOM manipulation.
- **Safety & Backup:** All files backed up to `legacy_frontend_backup/` before any replacement operations.

### 1.2 Newly Created Frontend (The Target Official Interface)
- **Source Location:** `/Users/vemanahemanthbabu/srujana_hackathon_2/frontend/Fragility-Shield/artifacts/fragilityshield`
- **Origin & Originating Agent:** Generated as a multi-package Replit workspace with modern institutional research terminal design specifications.
- **Architecture & Technology Stack:**
  - **Framework:** React 19 (`react: 19.1.0`, `react-dom: 19.1.0`)
  - **Language:** TypeScript 5.9 (`strict: true`)
  - **Bundler:** Vite 7 with `@vitejs/plugin-react`
  - **Styling:** Tailwind CSS v4, Lucide React icons, high-density terminal CSS (`src/terminal.css`, 53 KB), and shadcn-style token system (`src/index.css`, 13 KB).
  - **Routing:** Wouter client-side router (`wouter ^3.3.5`)
  - **State & Query:** TanStack React Query v5 (`@tanstack/react-query`)
  - **Visualizations:** Recharts (`recharts ^2.15.2`) supporting line, area, bar, scatter, pie, and histogram representations.
  - **Component Library:** 55+ accessible primitives in `src/components/ui/` (Radix UI wrappers for dialog, tabs, dropdowns, tables, forms, toasts, etc.).
- **Scope of Views:**
  - **Workspace:** Overview / Command Center (`/overview`), Market Terminal (`/market`, `/market/instrument/:id`), Portfolio Workbench (`/portfolio`), Data Sources (`/data`), Saved Portfolios (`/saved-portfolios`).
  - **Risk Laboratory:** Risk Analytics (`/labs/risk`), Attribution (`/labs/attribution`), Scenario Analysis (`/labs/scenarios`), Reverse Stress Testing (`/labs/reverse-stress`), Fragility & Sensitivity Studio (`/labs/fragility`), Monte Carlo (`/labs/monte-carlo`), Bootstrap & Uncertainty (`/labs/uncertainty`), Model Validation (`/labs/model-validation`), Assumptions Registry (`/assumptions`).
  - **Models & Strategies:** Model Registry (`/models`), ML Forecasting (`/labs/ml-forecasting`), ML Robustness (`/labs/ml-robustness`), Strategy Library (`/strategies`), Backtesting (`/labs/backtesting`), Tournament (`/labs/tournament`), Quantitative Allocation (`/labs/allocation`).
  - **Operations:** Experiment Studio (`/experiments`), Experiment History (`/experiments/history`), Reproducibility & Provenance (`/provenance`), SDK & API Monitor (`/integrations`), Plugin Lab (`/plugins`), Notifications & Jobs (`/notifications`).

---

## 2. Integration Gaps & Discovered Incompatibilities

### 2.1 Replit Cloud Dependencies vs Standalone Environment
The newly created frontend was originally bundled inside a Replit pnpm workspace with cloud-specific dependencies:
1. `vite.config.ts` imported `@replit/vite-plugin-runtime-error-modal`, `@replit/vite-plugin-cartographer`, and `@replit/vite-plugin-dev-banner`.
2. `vite.config.ts` threw hard exceptions if `process.env.PORT` or `process.env.BASE_PATH` were not set by Replit's environment.
3. `pnpm-workspace.yaml` contained `minimumReleaseAge: 1440` and platform exclusions that stripped `darwin-arm64` and `darwin-x64` native binaries.
4. `@workspace/api-client-react` was declared in `package.json` as a workspace dependency but never imported in application code.

### 2.2 Frontend Mock State vs Real Backend APIs
In the generated `App.tsx`:
- Most buttons displayed `notify('No connected provider is available to refresh.')` or `notify('Execution unavailable in this workspace')`.
- Portfolios and datasets were stored in memory with dummy state or placeholder selectors.
- Financial metrics (VaR, volatility, HHI, scenarios) were static descriptions rather than live REST responses.
- However, the FastAPI backend already has fully operational, verified endpoints for:
  - `POST /api/portfolio/load` & `POST /api/portfolio/concentration`
  - `POST /api/risk/calculate`
  - `POST /api/scenarios/run` & `POST /api/fragility/run`
  - `POST /api/attribution/calculate`
  - `POST /api/simulation/monte-carlo` & `POST /api/simulation/bootstrap`
  - `POST /api/allocation/optimize`
  - `POST /api/models/execute` (supporting asynchronous jobs with 202 Accepted)
  - `GET /api/models/jobs/{id}` & `POST /api/models/jobs/{id}/cancel`
  - `GET /api/artifacts` & `GET /api/artifacts/{id}/download`
  - `GET /api/workers/status`
  - Upstox V3 live market data & instrument resolver

---

## 3. Migration & Replacement Strategy

1. **Standalone Package Restructuring:**
   - Consolidate the React application from `frontend/Fragility-Shield/artifacts/fragilityshield` directly into `frontend/`.
   - Update `frontend/package.json` with pinned, clean, standard open-source dependencies (removing Replit workspace references and cloud plugins).
   - Configure a clean `vite.config.ts` supporting standard development (`npm run dev` on port 5173 with proxy to backend port 8000) and production build (`npm run build` outputting to `frontend/dist`).
2. **Backend Static Mounting:**
   - Update `backend/app.py` so that when `frontend/dist` exists, it mounts `frontend/dist` for production delivery, while preserving API routes and CORS for Vite dev mode.
3. **API Client Integration:**
   - Create a typed, resilient API client (`frontend/src/lib/api.ts`) managing base URL configuration, JWT authorization headers, timeout handling, and consistent error extraction.
4. **Wire Real User Workflows:**
   - Connect active portfolio loading (NSE sample portfolios and user uploads).
   - Wire live risk calculation into `/labs/risk`.
   - Wire scenario testing into `/labs/scenarios`.
   - Wire fragility audits into `/labs/fragility`.
   - Wire async job submission, polling, and cancellation into `/notifications` and the experiment studio.
   - Wire artifact downloads and integrity checks into `/provenance` and `/experiments`.
   - Display honest warnings for unconfigured third-party providers (Upstox) and fail-closed sandbox notices for untrusted models.
5. **Verify & Test:**
   - Run `pnpm/npm install` and `npm run build`.
   - Verify all 697 backend tests pass without regressions.
   - Test end-to-end user workflows in the browser.
