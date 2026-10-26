# FRAGILITYSHIELD — RISK ANALYTICS LAB FRONTEND DATA-FLOW REPAIR AUDIT REPORT

**Date:** 2026-10-26  
**Auditor / Engineer:** Principal Software Architect & Quantitative Risk Engineer  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Target Route:** `/labs/risk` (Risk Analytics Lab)  
**Execution Environment:** macOS, Python 3.14 venv (FastAPI / Starlette Backend @ port 8000), Vite React 19 Frontend (@ port 5173)

---

## 1. Executive Summary

The Risk Analytics Lab (`/labs/risk`) previously presented users with non-functional placeholders, static sine waves with fake labels (`T02`, `T04`, `T06`), and an unconfigured analysis workspace that reported "missing prerequisites" even after backend calculations succeeded. Furthermore, the application footer rendered `worker_... (undefined processed)`.

Following this targeted remediation:
1. **Root Causes Identified and Extirpated:**
   - The route `/labs/risk` was routing through legacy generic `Lab` scaffolding (`App.tsx`), which rendered `ChartGallery` without passing calculation results (`labResult`) or portfolio data.
   - `ChartCard` used `buildPreviewData(definition.kind, range, frequency)` to render synthetic sine waves (`drift + wiggle`) and placeholder time categories (`T02, T04, T06`).
   - The protocol configuration form had hardcoded `<input readOnly value="Default / Calibrated" />` elements, preventing selection of lookback window, confidence level, or methodology.
   - The initial portfolio state was silently set to `nse_10l.json` ("Illustrative ₹10 Lakh NSE Portfolio") without an explicit distinction between real client holdings and sample fixtures.
   - The backend `/api/workers/status` returned `total_succeeded` and `total_claimed`, but the frontend accessed `workerInfo.jobs_processed`, printing `undefined processed`.

2. **Remediated Architecture:**
   - Designed and deployed a dedicated, high-performance `RiskAnalyticsLab.tsx` component following the patterns of `RiskScenarioLab.tsx` and `QuantitativeAllocationLab.tsx`.
   - Wired `/labs/risk` directly in `App.tsx` and excluded it from falling back into the broken legacy `Lab` container.
   - Bound protocol configuration controls directly to live state: Target Portfolio picker (Saved user portfolios vs. explicit Illustrative Demo fixture), Confidence Level (90%, 95%, 99%), Lookback Window (60d, 120d, 252d, 504d), Methodology, and Benchmark Symbol.
   - Added an unmistakable amber alert badge: `ILLUSTRATIVE — NOT REAL PORTFOLIO DATA` whenever sample demo fixtures are loaded.
   - Built 6 genuine quantitative charts consuming live Fragility Engine output:
     1. **Cumulative Returns**: Compounded equity curve trajectory $(E_t - 1.0) 	imes 100\%$ with real step/day indices and zero baseline.
     2. **Periodic Returns**: Daily discrete arithmetic returns with zero baseline and green/red positive/negative coloring.
     3. **Rolling Volatility**: 20-day annualized rolling volatility using sample standard deviation with Bessel correction ($ddof=1$). Displays a clean, chart-specific insufficient-data state when observations $< 20$.
     4. **Drawdown & Underwater Curve**: Peak-to-trough decline path $[-DD_t 	imes 100\%, 0\%]$ with soft rose gradient fill and Maximum Drawdown reference line.
     5. **Return Distribution & Normal Fit**: 12 empirical return bins with an overlaid theoretical Gaussian normal distribution based on sample mean and standard deviation.
     6. **VaR & CVaR Tail Visualization**: Ordered loss profile ($L = -R$) with vertical reference line at the selected VaR quantile (e.g. 95% / 99%) and highlighted Expected Shortfall (CVaR) tail breach zone.
   - Fixed the worker status display in `App.tsx` and `api.ts` to safely read `jobs_processed ?? total_succeeded ?? total_claimed`, falling back to `(Processed count unavailable)` if omitted, completely eliminating `undefined processed`.

3. **Verification Summary:**
   - **Backend Data Flow Tests:** 9 / 9 passed (`backend/tests/test_risk_analytics_lab_dataflow.py`).
   - **Frontend Typecheck & Production Build:** Passed with zero TypeScript errors; Vite bundle generated in 2.36s.
   - **Live Browser Verification:** Executed via browser subagent on `http://localhost:5173/labs/risk`. Confirmed successful calculation, all 6 charts populated with real observations, correct footer status `worker_3f2e05e4681d (0 processed)`, and all tabs functioning.

---

## 2. Forensic Investigation & Root Cause Ledger (Phase 0)

| Observed Issue | Root Cause | Source File & Line | Status |
| :--- | :--- | :--- | :--- |
| **Default Target Displays Illustrative Portfolio** | `activePortfolio` initialized unconditionally on mount to `api.getSamplePortfolio('nse_10l.json')` without visual labeling. | `App.tsx:282` | **Fixed:** Added prominent amber `[ILLUSTRATIVE — NOT REAL PORTFOLIO DATA]` banner and portfolio selector allowing switch to real portfolios. |
| **Charts Toggle Illustrative Previews** | `ChartGallery` called with `enabled={previewCharts}` and `charts={chartCatalog[page]}`, passing neither `labResult` nor `activePortfolio`. | `App.tsx:2185-2190` | **Fixed:** Replaced legacy `ChartGallery` with dedicated `RiskAnalyticsLab.tsx` consuming live engine observations. |
| **Charts Display Fake Labels (T02, T04, T06)** | `ChartCard.tsx` / `buildPreviewData()` unconditionally fabricated sine waves (`drift + wiggle`) and synthetic category labels `T01, T02...`. | `App.tsx:981-1050` | **Fixed:** Charts now use real observation steps (`Day 1`, `Day 25`, etc.) derived from returned returns array. |
| **Missing Prerequisites Despite SUCCEEDED** | `Lab` did not connect `labResult` to `ChartGallery`; `ChartCard` evaluated `!preview && !definition.live_ready` and rendered placeholder empty state. | `App.tsx:920-960` | **Fixed:** Direct state binding between `api.calculateRisk` response and Recharts visualizations. |
| **Worker Status: `undefined processed`** | Backend `/api/workers/status` returned `total_succeeded` and `total_claimed`, but frontend accessed `workerInfo.jobs_processed`. | `App.tsx:754` | **Fixed:** Safe fallback accessor `workerInfo.jobs_processed ?? workerInfo.total_succeeded ?? workerInfo.total_claimed`. |

---

## 3. Data Flow & Contract Repair Details (Phases 1 & 2)

### 3.1 Backend Contract Additions (`backend/app.py:api_calculate_risk`)
The backend calculation function `api_calculate_risk` was updated to explicitly supply top-level `returns` and `drawdown_series` in its response:
```python
# Added to API response:
"returns": [round(float(x), 6) for x in arr],
"drawdown_series": rep_dict.get("drawdown", {}).get("drawdown_series", []) if rep_dict.get("drawdown") else [],
```
This enables direct, zero-overhead consumption of empirical returns and continuous drawdown series without recalculation on the frontend.

### 3.2 Frontend API Client Updates (`frontend/src/lib/api.ts`)
Updated `RiskReport` and `WorkerDiagnostics` interfaces:
- `RiskReport`: Added `returns?: number[]`, `drawdown_series?: number[]`, `custom_var?: number`, `custom_es?: number`, `confidence_level?: number`, `data_provenance?: any`, `explanation_panels?: any`.
- `WorkerDiagnostics`: Added `total_succeeded?: number`, `total_claimed?: number`, `total_failed?: number`, and made `jobs_processed?: number` optional.
- `calculateRisk()`: Mapped returned arrays directly into the returned `RiskReport` object.

### 3.3 Protocol Configuration Binding
The configuration section in `RiskAnalyticsLab.tsx` now allows full interactive configuration:
- **Target Portfolio:** Dropdown allows selecting from saved user portfolios (via `api.listPortfolios()`), the illustrative demo fixture (`nse_10l.json`), or clear/none.
- **Confidence Level:** Interactive dropdown with 90%, 95% (Basel Standard), and 99% (Regulatory Tail).
- **Lookback Window:** Interactive dropdown with 60d, 120d, 252d (1-Year Baseline), and 504d (2-Year Cycle).
- **Risk Methodology:** Interactive dropdown selecting Historical Simulation, Parametric Gaussian, or Cornish-Fisher.
- **Benchmark Symbol:** Custom text input (default `NIFTY`).

### 3.4 Distinct UI States (Phase 2)
`RiskAnalyticsLab.tsx` strictly discriminates among eight mutually exclusive states:
1. `NO_PORTFOLIO_SELECTED`: Portfolio is unset (`null`). Displays guide prompting selection.
2. `CONFIG_INCOMPLETE`: Parameters are unselected.
3. `READY_TO_RUN`: Valid configuration and portfolio selected, ready for execution.
4. `RUNNING`: Calculation request in flight with loading spinner and disabled trigger.
5. `SUCCEEDED`: Successful execution with $\ge 20$ observations, all 6 charts fully populated.
6. `PARTIAL_DATA`: Calculation succeeded, but observation count is insufficient for specific charts (e.g. $N < 20$ for 20-day rolling vol). A clean chart-specific explanatory state is rendered for the affected chart while all other charts render.
7. `INSUFFICIENT_DATA`: Calculation returned $< 4$ observations.
8. `FAILED`: Server error or non-finite data rejection, rendering detailed error alert.

---

## 4. Quantitative Chart Mathematical Transformations (Phase 4)

All 6 charts consume actual empirical output from the Fragility Engine. Zero synthetic data or sine waves are used.

### Chart 1: Cumulative Returns
- **Formula:** $R_{cum, t} = (E_t - 1.0) 	imes 100\%$ where $E_t = \prod_{i=0}^t (1 + r_i)$.
- **Axes:** X-axis shows discrete observation step (`Day 1`, `Day 50`...); Y-axis shows percentage return.
- **Visuals:** `#14766c` stroke with gradient fill and dashed zero-baseline.

### Chart 2: Periodic Returns
- **Formula:** $r_t 	imes 100\%$.
- **Axes:** X-axis shows observation steps; Y-axis shows daily return percentage.
- **Visuals:** Bar chart with zero reference line; positive returns colored emerald (`#10b981`), negative returns colored rose (`#ef4444`).

### Chart 3: Rolling Volatility (20-Day Window)
- **Formula:** 
  $$\sigma_{20, t} = \sqrt{rac{1}{19} \sum_{k=t-19}^t (r_k - ar{r}_t)^2} 	imes \sqrt{252} 	imes 100\%$$
- **Prerequisite Validation:** If $N < 20$, displays honest diagnostic state:
  *"Rolling volatility requires at least 20 historical observations (current: N). Please select a longer lookback window."*
- **Visuals:** Amber `#f59e0b` line chart.

### Chart 4: Drawdown & Underwater Curve
- **Formula:**
  $$P_t = \max_{0 \le s \le t} E_s, \quad DD_t = rac{P_t - E_t}{P_t}, \quad 	ext{Underwater}_t = -DD_t 	imes 100\%$$
- **Visuals:** Inverted area chart anchored at $0.0\%$ with rose gradient fill and dashed reference line for Maximum Drawdown.

### Chart 5: Return Distribution & Normal Fit
- **Empirical Binning:** 12 uniform bins spanning $[\min(r), \max(r)]$.
- **Parametric Gaussian Fit:**
  $$f(x_k) = rac{1}{\sigma \sqrt{2\pi}} \exp\left(-rac{(x_k - \mu)^2}{2\sigma^2}ight) 	imes \Delta x 	imes N$$
  Scaled to empirical observation frequency so histogram bars and normal density overlay are on the same scale.

### Chart 6: VaR & CVaR Tail Visualization
- **Formula:** Losses $L_{(i)} = -r_{(i)}$ sorted in ascending order.
- **Tail Zone:** Observations with $L_{(i)} \ge 	ext{VaR}_lpha$ highlighted in solid deep red (`#dc2626`).
- **Reference Lines:** Vertical/horizontal threshold lines for $	ext{VaR}_lpha$ (e.g. 95% VaR: 1.91%) and $	ext{ES}_lpha$ (Expected Shortfall: 2.46%).
- **Coherence Note:** Cites Acerbi & Tasche (2002) sub-additivity guarantee ($	ext{ES} \ge 	ext{VaR}$).

---

## 5. Verification Results

### 5.1 Automated Unit & Contract Tests
Executed via pytest:
```bash
PYTHONPATH=. .venv/bin/python -m pytest backend/tests/test_risk_analytics_lab_dataflow.py
```
**Results:** 9 passed in 0.96s.
- `test_risk_calculate_returns_complete_chart_series`: PASSED
- `test_risk_calculate_insufficient_returns_rejected`: PASSED
- `test_risk_calculate_non_finite_rejected`: PASSED
- `test_worker_status_contract_and_field_handling`: PASSED
- `test_illustrative_sample_portfolio_fixture`: PASSED
- `test_cumulative_returns_transformation`: PASSED
- `test_rolling_volatility_transformation`: PASSED
- `test_underwater_drawdown_transformation`: PASSED
- `test_tail_loss_sorting_and_cvar_coherence`: PASSED

Full regression suite (`test_application_api.py`, `test_risk_engine.py`, `test_frontend_integration.py`): **76 passed in 2.28s**.

### 5.2 Frontend Compilation & Typecheck
```bash
npm run typecheck && npm run build
```
- `tsc --noEmit`: 0 errors.
- `vite build`: Successfully generated production bundle in 2.36s (`dist/assets/index-DCwVbma6.js`, 1.7 MB).

### 5.3 Live Browser Verification (Browser Subagent)
- **Target URL:** `http://localhost:5173/labs/risk`
- **Initial Load:**
  - Status: `READY TO RUN`
  - Portfolio: `Illustrative ₹10 Lakh NSE Portfolio (Demo Fixture)`
  - Amber banner visible: `[ILLUSTRATIVE — NOT REAL PORTFOLIO DATA]`
  - Footer worker status: `worker_3f2e05e4681d (0 processed)` (no `undefined processed`)
- **Calculation Execution:**
  - Triggered "Execute Calculation".
  - Status transitioned to `SUCCEEDED`.
  - Metrics populated:
    - Annualized Volatility: **17.40%** (245 observations)
    - Historical VaR (95%): **1.91%**
    - Expected Shortfall (CVaR): **2.46%**
    - Maximum Drawdown: **26.36%**
    - Sharpe Ratio: **-1.40**
    - Total Return: **-17.23%**
  - All 6 charts rendered with live engine observations.
  - Zero charts reported missing prerequisites or showed fake `T02/T04` categories.
- **Tabs Verified:**
  - "Visual Diagnostics (6 Quantitative Charts)": Rendered 6 charts.
  - "Mathematical Explanations & Formulas": Displayed exact equations for Volatility, VaR, CVaR, MDD.
  - "Data Provenance & Audit Trail": Displayed data source, observation count (245), engine version, and SHA256 checksum.

---

## 6. Changed Files Inventory

1. `backend/app.py`: Added top-level `returns` and `drawdown_series` to `api_calculate_risk` response.
2. `frontend/src/lib/api.ts`: Enhanced `RiskReport` and `WorkerDiagnostics` interfaces, updated `calculateRisk` field mapping.
3. `frontend/src/App.tsx`:
   - Imported `RiskAnalyticsLab`.
   - Routed `/labs/risk` to `<RiskAnalyticsLab ... />`.
   - Excluded `/labs/risk` from generic `Lab` fallback.
   - Updated worker status display in footer to prevent `undefined processed`.
4. `frontend/src/components/pages/RiskAnalyticsLab.tsx`: Created dedicated lab component with full configuration controls, 8 UI states, 6 quantitative charts, mathematical explanations tab, and data provenance tab.
5. `backend/tests/test_risk_analytics_lab_dataflow.py`: Created 9 test cases covering API contract, validation rejections, worker diagnostics, and mathematical chart transformations.
6. `docs/audit/FRAGILITYSHIELD_RISK_ANALYTICS_FRONTEND_REPAIR.md`: This comprehensive audit report.

---

## 7. Residual Risks & Unresolved Backend Contract Gaps

1. **Intraday Tick Granularity:** The Fragility Engine currently calculates risk metrics on daily simple arithmetic returns. If high-frequency intraday tick returns are required in a future release, the annualization factor (default 252) and frequency parameter should be made dynamic.
2. **Upstox Live Quotes vs. Fallback:** When the Upstox API credentials (`UPSTOX_ACCESS_TOKEN`) are not set in the environment, the engine uses validated historical daily return fixtures for Indian equities. The UI accurately reflects this in the Data Provenance tab.
