# Page 01: Overview / Research Command Center — Inspection, Correction, and Verification Report

**Component Route:** `/overview`  
**Page Title:** Research Command Center / Quantitative Portfolio Overview  
**Audit Date:** 2026-10-25  
**Engine:** FragilityShield Quantitative Risk Engine (FastAPI + PostgreSQL RLS + Native Math Kernels)  
**Status:** **PASS** (All 11 Core Functional Groups Verified End-to-End)

---

## 1. Problems Discovered During Inspection

Before correction, the original `/overview` route contained multiple architectural and data-integrity shortcomings:

1. **Header & Controls Deficiencies:**
   - The workspace selector was a static text string with no interactive switching capability.
   - The portfolio selector in the overview panel was a non-interactive header (`<h2>{portfolio}</h2>`), requiring users to navigate elsewhere to change the active portfolio.
   - Benchmark selector was completely absent; users could not specify benchmark indices (`NIFTY 50`, `BANKNIFTY`, `NIFTY IT`, `FINNIFTY`), preventing relative risk and Beta calculations.
   - The date-range selector (`1M`, `3M`, `6M`, `1Y`, `ALL`) was visually present but did not adjust calculation lookback or slice the equity curve.
   - Layout customization only toggled 3 hardcoded panels and was lost on browser refresh because it lacked `localStorage` persistence.
   - "Export Overview" was missing from the header controls.

2. **Portfolio Summary Data Policy Violations:**
   - Daily returns, cumulative returns, CAPM Beta, and valuation timestamps were omitted.
   - When risk calculations were pending or missing, hardcoded mock values (`0.2018` for volatility, `0.0236` for VaR, `0.0281` for ES, `0.1885` for Max Drawdown, `0.85` for Sharpe) were silently injected as fallbacks in `frontend/src/lib/api.ts`.
   - The valuation curve had a hardcoded array fallback `[1.0, 1.008, 1.015, ...]` when real observations were empty, violating the Real-Data Policy.

3. **Market Coverage Limitations:**
   - Displayed static cards with no actual index price quotes or daily percentage changes.
   - Failed to surface Upstox V3 freshness timestamps or provider connectivity state.

4. **Risk Surveillance & Alerts Deficiencies:**
   - No dynamic risk radar evaluated portfolio concentration (HHI > 0.18), tail loss severity (ES > 3.5%), observation sample sizes, or provider authentication.
   - Actions like "Inspect", "Dismiss", "Open Lab", and "Create Experiment from Alert" did not exist.

5. **Recent Research Inaccuracies:**
   - Rendered static hardcoded cards claiming readiness without querying the backend persistence layer (`/api/experiments/runs` and `/api/audit/events`).
   - Failed to provide an honest empty state when no runs were recorded in the active tenant.

6. **Quick-Launch Incompleteness:**
   - Omitted several core laboratory workflows (e.g. Reverse Stress Testing, ML Forecasting, Reproducible Experiments).

---

## 2. Changes Implemented & File Traceability

### A. Dedicated Component Creation
- **File:** [`frontend/src/components/pages/OverviewCommandCenter.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/OverviewCommandCenter.tsx)
  - Implemented the complete 11-feature Research Command Center compliant with the Page 01 specification.
  - Implemented the 10-metric quantitative summary grid with explicit empty states (`— —`) when data is unavailable.
  - Added interactive Workspace selector (`Research workspace`, `Macro Risk Production`, `Local Sandbox`).
  - Added interactive Portfolio selector synchronizing with active quantitative research state.
  - Added Benchmark selector (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `NIFTY IT`) driving real CAPM Beta calculations.
  - Integrated `localStorage` persistence for dashboard customization (`Save Layout` and `Reset Layout`).
  - Integrated real Export Overview supporting Markdown (`.md`), CSV (`.csv`), and JSON (`.json`) exports via `/api/export`.
  - Added Market Benchmark Coverage with live Upstox V3 quotes and freshness timestamps.
  - Built dynamic Risk Radar generating alerts only from real mathematical thresholds (HHI, CVaR, sample size, Upstox authentication) with `Inspect`, `Dismiss`, `Open Lab`, and `Restore` actions.
  - Connected real persistence layer to display genuine experiment runs and an honest empty state.
  - Integrated all 9 Quick-Launch Quantitative Laboratory workflows.

### B. Backend Quantitative Risk Engine Enhancement
- **File:** [`backend/app.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py)
  - Updated `api_calculate_risk` to compute:
    - Annualized Sharpe ratio relative to $R_f = 6.5\%$ (`calculate_sharpe_ratio`).
    - Last daily return ($R_{t}$) and cumulative total return ($\prod (1 + R_i) - 1$).
    - CAPM Beta ($\beta = \frac{\text{Cov}(R_p, R_m)}{\text{Var}(R_m)}$) against the selected benchmark index (`calculate_beta`).
    - Real calculation timestamp in ISO format.
  - Handled automated alignment of benchmark and portfolio return vectors over identical observation windows.

### C. Client API Layer Hardening
- **File:** [`frontend/src/lib/api.ts`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/lib/api.ts)
  - Extended `RiskReport` interface with `daily_return`, `total_return`, `benchmark_beta`, and `timestamp`.
  - Completely removed hardcoded fallback mock constants (`0.2018`, `0.0236`, `0.0273`, `0.0281`, `0.0361`, `0.1885`, `0.85`).
  - Allowed `calculateRisk` to pass `benchmark_symbol` and `lookback_window`.

### D. Main Routing & Layout Integration
- **File:** [`frontend/src/App.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/App.tsx)
  - Replaced legacy inline `Overview` with `<OverviewCommandCenter />`.
  - Streamlined header rendering so `/overview` renders its own cohesive controls without duplicate headers or bars.

---

## 3. Real Data Sources for Each Section & Metric

| Section / Tile | Source | Integration Mechanism |
| :--- | :--- | :--- |
| **Workspace Selector** | Tenant Context (`ten_alpha_capital`) | App context & user preferences |
| **Portfolio Value** | Active Portfolio Holdings | Real sum $\sum (q_i \times p_i)$ from `/api/portfolios` |
| **Returns (Cumulative / 1D)** | Historical Return Series | Derived from log/simple return array via `api.calculateRisk` |
| **Annualized Volatility** | Return Observations ($\ge 20$d) | Native `calculate_risk_report` ($\sigma \times \sqrt{252}$) |
| **Sharpe Ratio** | Return Observations & $R_f = 6.5\%$ | Native `calculate_sharpe_ratio` |
| **CAPM Beta** | Portfolio & Benchmark Return Arrays | Native `calculate_beta` ($\frac{\text{Cov}(R_p, R_m)}{\text{Var}(R_m)}$) |
| **Maximum Drawdown** | Cumulative Wealth Index | Native `calculate_maximum_drawdown` peak-to-trough |
| **Historical VaR (95%)** | Empirical Quantile Loss | Native `calculate_historical_var` ($\alpha = 0.95$) |
| **Expected Shortfall (95%)** | Coherent Tail Integral | Native `calculate_expected_shortfall` (Acerbi-Tasche 2002) |
| **HHI Concentration** | Asset Portfolio Weights | Native `calculate_portfolio_concentration` ($\sum w_i^2$) |
| **Dominant Sector** | Portfolio Sleeve Aggregation | Real sum of weights grouped by sector metadata |
| **Valuation Curve** | Chronological Portfolio Wealth Index | Recharts `AreaChart` fed by `riskReport.equity_curve` |
| **Benchmark Quotes** | Upstox Market Data V3 | `/api/upstox/quote?symbols=NIFTY,BANKNIFTY,FINNIFTY,NIFTY IT` |
| **Risk Alerts** | Real Mathematical Boundary Check | Evaluated client-side against active `riskReport` and `concentration` |
| **Recent Research** | PostgreSQL Audit Ledger | `/api/experiments/runs` and `/api/audit/events` |
| **Engine Readiness** | Backend Health & Telemetry | `/api/health`, `/api/security/status`, `/api/upstox/status` |

---

## 4. Calculations and Assumptions Applied

1. **Annualization Factor:** Fixed at $252.0$ trading days per year for daily equity returns.
2. **Degrees of Freedom ($ddof$):** Sample standard deviation and sample variance use $ddof = 1$.
3. **Risk-Free Rate:** Assumed at $6.50\%$ annual ($0.065$), corresponding to the prevailing Reserve Bank of India (RBI) Repo Rate benchmark.
4. **Value at Risk Convention:** Reported as a positive loss fraction ($L = -R$). At $\alpha = 0.95$, $\text{VaR} = 1.91\%$ means $95\%$ of 1-day losses do not exceed $1.91\%$.
5. **Expected Shortfall Coherence:** Acerbi & Tasche (2002) fractional weighting guarantees sub-additivity and coherence ($\text{ES}_{0.95} \ge \text{VaR}_{0.95}$).
6. **CAPM Beta:** Computed via sample covariance of active portfolio return with benchmark index return over identical observation lookback ($\ge 20$ days).
7. **HHI Diversification:** Herfindahl-Hirschman Index $\sum_{i=1}^N w_i^2$. Values $< 0.15$ indicate broad diversification; values $> 0.18$ trigger concentration radar alerts. Effective $N = 1 / \text{HHI}$.

---

## 5. Mock-Data Paths Removed or Isolated

- **Removed `0.2018`, `0.0236`, `0.0281`, `0.1885`, `0.85` from `api.ts`:** No fake numbers are substituted when backend calculations fail or are uncalibrated; the UI now renders `— —`.
- **Removed synthetic fallback array `[1.0, 1.008, 1.015, ...]` from the production equity curve:** If observations are missing, the UI displays an honest message: *"Valuation curve unavailable: Select an active portfolio to calibrate observations."*
- **Removed hardcoded readiness cards in favor of live telemetry:** Diagnostic status directly reflects PostgreSQL RLS, Upstox authentication, and asynchronous worker leasing.
- **Removed fake recent research items:** When the database contains no past runs, an honest empty state with action `Launch First Experiment` is presented.

---

## 6. Verification & Test Results

| Verification Item | Status | Result & Evidence |
| :--- | :---: | :--- |
| **Backend Regression Suite** | `PASS` | 701 tests passed in 6.97s (`pytest backend/tests -q`) |
| **Frontend TypeScript Typecheck** | `PASS` | Zero errors (`./frontend/node_modules/.bin/tsc --noEmit`) |
| **Production Vite Build** | `PASS` | Built in 2.21s (`npm run build --prefix frontend`) |
| **Header & Workspace Switching** | `PASS` | Switches between active workspaces and triggers notification |
| **Portfolio Switching** | `PASS` | Dropdown switches active portfolio and recalculates metrics |
| **Benchmark Selection & Beta** | `PASS` | Switches benchmark (NIFTY vs BANKNIFTY) and computes Beta |
| **Observation Window Toggles** | `PASS` | 1M, 3M, 6M, 1Y, ALL update lookback window and equity curve |
| **Customize Layout & Save** | `PASS` | Toggles widgets, saves to `localStorage`, restores defaults |
| **Export Overview** | `PASS` | Generates and downloads Markdown report via `/api/export` |
| **10-Metric Summary Grid** | `PASS` | Real portfolio value, returns, vol, Sharpe, beta, MDD, VaR, ES, HHI |
| **Valuation Curve Chart** | `PASS` | Recharts `AreaChart` renders 245 calibrated daily observations |
| **Benchmark Coverage** | `PASS` | Real NIFTY, BANKNIFTY, FINNIFTY, NIFTY IT quotes and change % |
| **Risk Radar & Alerts** | `PASS` | Alerts derived from real data; Inspect modal & Dismiss verified |
| **All 9 Quick-Launch Labs** | `PASS` | Buttons navigate to `/labs/risk`, `/labs/scenarios`, etc. |
| **Audit Trail Persistence State** | `PASS` | Displays honest empty state when 0 runs exist in active tenant |
| **Engine Readiness Telemetry** | `PASS` | Probes PostgreSQL RLS, worker, and Upstox connection |

### Browser Automation Verification Artifacts
- **Full Initial Command Center View:** [`overview_page_1792923109070.png`](file:///Users/vemanahemanthbabu/.gemini/antigravity-ide/brain/568455ec-89d2-4cd2-b8dd-c7f50223e876/overview_page_1792923109070.png)
- **Scrolled Labs & Audit Trail View:** [`overview_page_scrolled_1792923123785.png`](file:///Users/vemanahemanthbabu/.gemini/antigravity-ide/brain/568455ec-89d2-4cd2-b8dd-c7f50223e876/overview_page_scrolled_1792923123785.png)
- **Customized Layout State:** [`final_overview_state_1792923201110.png`](file:///Users/vemanahemanthbabu/.gemini/antigravity-ide/brain/568455ec-89d2-4cd2-b8dd-c7f50223e876/final_overview_state_1792923201110.png)
- **Video Recording Session:** [`page_01_verify_1792923090425.webp`](file:///Users/vemanahemanthbabu/.gemini/antigravity-ide/brain/568455ec-89d2-4cd2-b8dd-c7f50223e876/page_01_verify_1792923090425.webp)

---

## 7. Remaining Limitations and Required Configuration

1. **Upstox API Token Expiration:**
   - Upstox V3 access tokens expire periodically per exchange security rules. When expired, the Market Benchmark Coverage and Market Terminal fall back to verified local historical datasets. Re-authentication can be triggered in `/integrations` or via OAuth.
2. **Multi-Tenant Database Isolation:**
   - In `local_research` mode, SQLite with simulated tenancy is active. In production deployments, setting `DATABASE_URL` activates full PostgreSQL Row-Level Security with tenant policies.

---

## 8. Summary Assessment

Page 01 (**Research Command Center / Overview**) is fully compliant with the FragilityShield specification. All financial metrics and charts are derived from authentic quantitative risk algorithms and verified historical observations. All mock data pathways have been eliminated from the production overview flow.
