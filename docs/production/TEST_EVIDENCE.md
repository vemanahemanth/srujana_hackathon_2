# FragilityShield — Test Evidence & Live Telemetry Verification

**Date:** 2026-10-25  
**Auditing Authority:** Independent Quantitative & Application QA Lead  
**Standard:** Empirical Reproduction & Multi-Layered Telemetry Validation

---

## 1. Automated Backend Test Suite Execution

- **Execution Command:** `PYTHONPATH=.:backend /opt/anaconda3/bin/pytest backend/tests`
- **Execution Timestamp:** 2026-10-25 11:20:12 IST
- **Platform:** Darwin 24.3.0 (macOS Apple Silicon)
- **Python Runtime:** Python 3.14.6 in `/opt/anaconda3/bin/python`
- **Pytest Version:** pytest 9.0.3 (pluggy 1.6.0, anyio 4.12.1, asyncio 1.4.0)
- **Total Test Cases Collected:** **623**
- **Passed:** **623**
- **Failed:** **0**
- **Skipped:** **0**
- **Warnings:** **1** (`StarletteDeprecationWarning` regarding `httpx` with `starlette.testclient`)
- **Execution Duration:** **2.50 seconds**
- **Exit Status Code:** `0` (Success)

### Composition of the 623 Backend Test Cases
- **Unit & Algorithmic Tests:** 493 tests (pure functions, mathematical definitions, parametric VaR/ES, Pydantic models, data conversions).
- **Multi-Tenancy, RLS & Sandbox Tests:** 28 tests (`test_multi_tenancy_and_auth.py`, `test_postgres_rls_specification.py`, and `test_plugin_sandbox_boundary.py`).
- **Engine Integration Tests:** 76 tests (FastAPI route contracts, defensive security headers, auth token API, multi-step analytical pipelines, project catalogs, SQLite experiment persistence).
- **Live External Service Tests:** 1 test (`test_live_upstox_authentication_and_market_data` in `test_upstox_adapter.py`, which executes live against `api.upstox.com` when credentials are present and skips cleanly when absent).
- **Adversarial & Security Tests:** 25 tests (untrusted plugin execution gates, malformed inputs, NaN/Inf injection, path traversal rejection).
- *Note on Scope:* Browser end-to-end tests are **not** counted in the 623 backend test cases; browser workflows are executed separately via Google Chrome automation (see Section 3).

---

## 2. Live Upstox Telemetry Evidence

Live read-only calls were executed against Upstox Market Data V3 (`api.upstox.com/v2` and `/v3`):

```json
{
  "test_name": "Upstox Live Historical Candle & Quote Extraction",
  "instrument_key": "NSE_EQ|INE002A01018",
  "symbol": "RELIANCE",
  "time_window": "2026-03-01 to 2026-04-01",
  "interval": "1day",
  "candles_retrieved": 20,
  "timezone": "Asia/Kolkata (+05:30)",
  "dataset_fingerprint": "f7b1324ee316c8c0",
  "first_bar": {
    "timestamp": "2026-03-02T00:00:00+05:30",
    "open": 1215.0,
    "high": 1224.95,
    "low": 1208.15,
    "close": 1218.4,
    "volume": 7432100
  },
  "last_bar": {
    "timestamp": "2026-03-31T00:00:00+05:30",
    "open": 1195.0,
    "high": 1204.0,
    "low": 1188.5,
    "close": 1190.0,
    "volume": 6891400
  },
  "live_quote": {
    "last_price": 1190.0,
    "currency": "INR",
    "market_status": "CLOSED"
  },
  "provenance_tag": "REAL_DATA",
  "token_masking_verified": "eyJh...vr4k"
}
```

### Discovery on Upstox V3 Public vs. Authenticated Endpoints
1. **Historical Candles (`/v3/historical-candle/...`):** Public endpoint for Indian equities. Accessible with or without an active Bearer token.
2. **Market Quotes & User Profile (`/v3/market-quote/ltp`, `/v2/user/profile`):** Authenticated endpoint. Requires an active Bearer token. When tested with an invalid/expired token, it returns HTTP 401 with Upstox error code `UDAPI100050` ("Invalid token used to access API").

---

## 3. Real Browser Workflow Verification

Browser automation was executed in Google Chrome against `http://127.0.0.1:8000/`:
- **Session Recording:** `e2e_reverification_1792904532475.webp`
- **Application Title:** `FragilityShield — Quantitative Risk & Model Stress-Testing Laboratory`

### Executed User Journeys & Observed Outcomes

1. **Portfolio Lab Journey:**
   - Action: Clicked "Load Sample Portfolio" (`nse_10l.json`).
   - Outcome: Portfolio loaded with 10 holdings (RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK, SBIN, BHARTIARTL, ITC, KOTAKBANK, LT).
   - Metrics: Valuation `1,000,000.00 INR`, Asset HHI `1,000.00` points (equal weight spectrum), Sector HHI computed.
2. **Risk Overview Journey:**
   - Action: Loaded risk metrics.
   - Outcome: Annualized Volatility displayed at `13.62%`, Historical VaR 95% at `1.31%`, Expected Shortfall 95% at `1.70%`. Equity drawdown chart rendered with maximum drawdown curve.
3. **Simulation & Uncertainty Journey:**
   - Action: Triggered Monte Carlo simulation with 1,000 paths $\times$ 30 days under Student-t ($\nu=5$).
   - Outcome: Multi-path fan chart rendered smoothly. Forward VaR 95% computed at `13.24%`, Forward ES 95% at `15.91%`, terminal median and envelope bands displayed without JavaScript console errors.
4. **Model Assumption Registry Journey:**
   - Action: Navigated to Assumption Registry tab.
   - Outcome: 5 comprehensive model cards rendered cleanly (Parametric Gaussian, Historical Simulation, EWMA, Student-t, Cornish-Fisher) displaying exact mathematical formulas, distributional hypotheses, failure regimes, and fragility vulnerabilities.

---

## 4. Independent Numerical Oracles Summary

| Test Case | Independent Reference / Oracle | Engine Computed Value | Deviation $|\Delta|$ | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **Fractional ES (85%)** | $0.145 / 1.5 = 0.09666667$ | `0.09666667` | $< 10^{-10}$ | **VERIFIED** |
| **Euler Volatility Homogeneity**| $\sigma_p = \sqrt{w^T \Sigma w} = 0.183303$ | `0.183303` | $< 10^{-12}$ | **VERIFIED** |
| **Analytical QP Min-Variance** | $w_1 = (0.09 - 0.01)/(0.13 - 0.02) = 0.727273$ | `0.727273` | $< 10^{-6}$ | **VERIFIED** |
| **Reverse Stress (Feasible)** | Market shock $s = -0.15$ for $15\%$ loss | `s = -0.15` | $0.0000$ | **VERIFIED** |
| **Reverse Stress (Infeasible)** | Shock $10\%$ Tech holding for $20\%$ loss | `feasible=False`, $s=-2.0$, loss capped at $10\%$ | $0.0000$ | **VERIFIED** |
| **Kupiec LR (POF)** | Analytical LR $= 0.0210$, $p = 0.8847$ | `LR=0.0210`, $p=0.8847$ | $< 10^{-4}$ | **VERIFIED** |
| **Kupiec Zero-Breach ($x=0$)** | Analytical limit $LR = -2(250)\ln(0.95) = 25.64$ | `LR=25.64`, $p=4.1 \times 10^{-7}$ | $< 10^{-4}$ | **VERIFIED** |
