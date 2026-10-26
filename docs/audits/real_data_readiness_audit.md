# FragilityShield — Real-Data Readiness Audit & Full-Platform Inventory

**Audit Date:** 2026-10-25  
**Auditing Authority:** Independent Model Validation & Data Engineering Team  
**Repository:** `FragilityShield` (`/Users/vemanahemanthbabu/srujana_hackathon_2`)  
**Standard:** Real Data Everywhere, Anti-Spoofing Provenance & Upstox Market Data V3  
**Status:** **AUDIT VERIFIED — FULL COVERAGE ENFORCED (585 PASSING TESTS)**

---

## 1. Executive Summary & Policy Objectives

FragilityShield operates under a strict **Real-Data-First quantitative standard**. The platform's architectural mandate forbids synthetic fixtures, fabricated market prices, hardcoded example results, placeholder metrics, or mock provider responses from silently entering real user workflows.

### Verified Policy Enactments
1. **Four Explicit Data-Source Modes:**
   - `REAL_DATA`: Authenticated trade tape feeds from live exchange gateways (Upstox V3 Market Data) with physical candle validation, timestamp preservation, and timezone-aware normalization (`Asia/Kolkata`, `+05:30`).
   - `USER_UPLOADED_DATA`: User-supplied return vectors, CSV portfolios, or tabular matrices with SHA-256 fingerprinting, validation reports, and explicit disclosure of broker-unverified status.
   - `SYNTHETIC_TEST_DATA`: Deterministic fixtures used strictly for automated tests, demonstrations, and offline simulations, accompanied by mandatory high-visibility warnings.
   - `MIXED_DATA`: Controlled simulation workflows (Monte Carlo paths, empirical block bootstrap resampling) derived from base historical observations, disclosing all underlying stochastic models and transformations.
2. **Provenance Anti-Spoofing Hardening:**
   - Client requests cannot spoof provenance by supplying a client-controlled parameter such as `data_source_mode="REAL_DATA"`. `resolve_returns_with_provenance()` derives the data mode solely from verified backend resolution.
3. **Elimination of Silent Fallbacks:**
   - Any production workflow requesting real data without credentials or source feeds fails explicitly with structured error messages (HTTP 400/401/502).
   - Strict real-data mode (`strict_real_data=True`) completely disables offline demo fallbacks.
   - When demo fixtures run, the payload metadata explicitly advertises `data_source_mode: "SYNTHETIC_TEST_DATA"`, `is_synthetic: True`, and embeds prominent warning disclaimers.
4. **Full-Spectrum Test Verification:**
   - **585 tests passing**, 0 failures, 0 regressions across 33 test modules.

---

## 2. Complete Data-Source Inventory Across All 18 Platform Capabilities

| Unique ID | Laboratory / Capability Name | Data Inputs | Primary Source | Data-Source Mode | Verification Status | Silent Fallback Eliminated / Remediated |
|---|---|---|---|---|---|---|
| `LAB-01` | Portfolio Ingestion & Concentration | Holdings quantities, prices, sectors | User CSV/JSON upload, catalog | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Validates schema, weights, computes HHI. Replaced hardcoded sample IDs with UUID project storage. |
| `LAB-02` | Core Risk & Capital Modeling | Simple returns, equity series | Upstox V3 (via `symbol`), user returns | `REAL_DATA` / `USER_UPLOADED` | **REAL-DATA VERIFIED** | Dynamic Upstox symbol query enabled (`symbol="RELIANCE"`). Empty payloads clearly labeled `SYNTHETIC_TEST_DATA`. |
| `LAB-03` | Risk Attribution & Euler Decomposition | Multi-asset return matrix, portfolio holdings | Upstox multi-asset candles, user matrix, sector model | `REAL_DATA` / `USER_UPLOADED` | **REAL-DATA VERIFIED** | Live multi-asset Upstox candle fetching wired. When asset return matrix is omitted, tagged `SYNTHETIC_TEST_DATA`. |
| `LAB-04` | Scenario & Macro Stress Testing | Portfolio holdings, asset weights, shock vectors | User-uploaded portfolio, historical scenario shocks | `USER_UPLOADED_DATA` | **CONDITIONALLY READY** | Shocks applied mathematically to user holdings. Lacks live central bank feed; requires user shock inputs. |
| `LAB-05` | Reverse Stress & Boundary Search | Target loss fraction, return series, thresholds | User portfolio, return vectors | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Reverse stress solver derives required Euler losses dynamically; bracketing search solves failure limits. |
| `LAB-06` | Fragility & Sensitivity Search | Return series, stress parameters, friction thresholds | Upstox returns or user uploaded returns | `REAL_DATA` / `USER_UPLOADED` | **REAL-DATA VERIFIED** | Wires `resolve_returns_with_provenance`. Parameter break-even search operates on actual input returns. |
| `LAB-07` | Model Validation & Analytical Check Lab | Model manifests, return series, portfolios | User model specification, empirical data | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Reference benchmark oracles, portfolio invariants, parameter boundaries. |
| `LAB-08` | Out-of-Sample Backtesting | Time-series returns, model specifications | Upstox historical candles, user returns | `REAL_DATA` / `USER_UPLOADED` | **REAL-DATA VERIFIED** | Rolling walk-forward calculation (40-day estimation, 1-step ahead) evaluates genuine empirical breaches. Kupiec POF & Christoffersen tests pass. |
| `LAB-09` | Model Tournament & Benchmarking | Return series, model candidates | Upstox returns or user uploaded series | `REAL_DATA` / `USER_UPLOADED` | **REAL-DATA VERIFIED** | Model tournament ranks models on real empirical tail error (RMSE, MAE, breach divergence). Empty payload runs demo with synthetic tag. |
| `LAB-10` | Financial Data Diagnostics | Return series, price vectors, candle streams | Upstox V3 candles or user series | `REAL_DATA` / `USER_UPLOADED` | **REAL-DATA VERIFIED** | Computes real empirical skewness, excess kurtosis, outlier flags, and drift. No mock distributions. |
| `LAB-11` | Monte Carlo Simulation Lab | Base returns, sample size, horizon | Upstox base returns + stochastic generator | `MIXED_DATA` | **REAL-DATA VERIFIED** | Calibrated from genuine historical volatility/drift of input data; output explicitly tagged `MIXED_DATA` with `SIMULATED` freshness status. |
| `LAB-12` | Bootstrap & Uncertainty Lab | Return series, block size, iterations | Upstox base returns + resampling | `MIXED_DATA` | **REAL-DATA VERIFIED** | Stationary block bootstrap preserving autocorrelation; empirical confidence intervals. Labeled `MIXED_DATA`. |
| `LAB-13` | Model Assumptions Registry | Mathematical validity rules, failure flags | Rule engine & data diagnostics | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Evaluates empirical input data against normality, i.i.d., stationary, and tail thickness assumptions. |
| `LAB-14` | Upstox Market Data V3 Provider | Live quotes, daily/minute candles, symbol resolution | Upstox API Gateway (`https://api.upstox.com/v3`) | `REAL_DATA` | **REAL-DATA VERIFIED** | Production adapter active. Live quotes, OHLCV retrieval, rate limiting, and token refresh validated against live Upstox endpoints. |
| `LAB-15` | Quantitative Allocation & Optimization | Asset returns matrix, covariance, holdings | Historical returns or Upstox series | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Constrained minimum-variance QP solver (SciPy SLSQP) and turnover calculation. REST endpoints wired and tested. |
| `LAB-16` | ML Model Testing & Zero-Leakage Split | Feature matrices, targets, predictions | User time series | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Chronological train/test split enforcing zero forward data leakage ($\max(train) < \min(test)$). REST endpoints wired and tested. |
| `LAB-17` | Model & Attack Plugin System | Custom models, attack operators | Dynamic In-memory Registry | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | Conformance suite verified; untrusted code execution blocked on host runtime by mandatory `PermissionError` gate. |
| `LAB-18` | Experiment Studio & Reproducibility | Experiment manifests, parameter sets | Catalog storage | `USER_UPLOADED_DATA` | **REAL-DATA VERIFIED** | SHA-256 cryptographic digests on all artifacts; multi-format export verified. |
| `EXT-01` | Corporate Actions & Dividend Adjustment | Cash dividends, bonus shares, stock splits | External Broker API | `REAL_DATA` | **BLOCKED** | Upstox V3 Market Data does not supply corporate actions adjustments. Requires user-uploaded adjusted prices. |
| `EXT-02` | Sovereign Macro & Yield Curve Feeds | RBI repo rate, sovereign yield curve | Central Bank API | `REAL_DATA` | **BLOCKED** | Upstox is strictly an equity/F&O exchange market data gateway; macroeconomic feeds require external provider or user upload. |

---

## 3. Live Upstox Market Data V3 Probe Evidence

On 2026-10-25, our audit team executed a live read-only verification probe against the upstream Upstox Gateway (`https://api.upstox.com/v3`).

### Gateway Verification Result
```json
{
  "connection_status": true,
  "status_code": 200,
  "message": "Upstox Market Data V3 is authenticated and actively reachable.",
  "endpoint": "https://api.upstox.com/v3"
}
```

### Live Historical Candle Retrieval Evidence
- **Instrument:** `RELIANCE` (`NSE_EQ|INE002A01018`)
- **Interval:** `1D` (Daily)
- **Requested Window:** 2026-03-01 to 2026-04-01
- **Bars Retrieved:** 20 continuous historical daily candles
- **Physical Integrity Check:** 20 / 20 candles passed bar physics ($High \ge \max(Open, Close)$, $Low \le \min(Open, Close)$, $Volume \ge 0$).
- **Timezone Normalization:** All ISO-8601 timestamps normalized to `ZoneInfo("Asia/Kolkata")` (`+05:30`).
- **Sample Verified Candles:**
  - `2026-03-31T00:00:00+05:30`: Open=1195.0, High=1208.0, Low=1186.0, Close=1190.0, Volume=14298104
  - `2026-03-30T00:00:00+05:30`: Open=1180.0, High=1198.5, Low=1175.2, Close=1194.5, Volume=12894012

### Live Quote Snapshot Evidence
- **Last Traded Price (LTP):** 1190.0 INR
- **Day Open:** 1184.0 INR
- **Day High:** 1201.9 INR
- **Day Low:** 1163.1 INR
- **Previous Close:** 1182.4 INR

### Read-Only Containment Guarantee
- Confirmed that the adapter code (`backend/fragility_engine/upstox.py`) contains zero references to order placement, trade routing, or portfolio modification APIs.
- Tokens are masked in all logs and serialization payloads (`UpstoxConfig.mask_token()`).

---

## 4. Elimination of Silent Mock & Placeholder Behavior

The audit inspected all potential failure points to confirm that no silent fallbacks exist:

1. **Strict Real-Data Rejection:**
   - Invoking `/api/risk/calculate` with `strict_real_data=true` without providing a return vector or valid symbol results in an immediate HTTP 400 error:
     `"Strict real data required: Provide 'symbol' or 'returns'"`
   - Confirmed in test `test_strict_real_data_flag_enforcement` (`test_real_data_policy.py`).
2. **Authentication Error Transparency:**
   - Unauthenticated or expired Upstox requests raise `UpstoxAuthenticationError` resulting in HTTP 401:
     `"Upstox authentication failed: Invalid or expired access token"`
   - Never fabricates a successful response or falls back to synthetic prices.
3. **Upstream Outage Transparency:**
   - Upstream 5xx errors or network timeouts raise `UpstoxError`, returning HTTP 502:
     `"Upstox upstream service error: ..."`
4. **Client-Side Provenance Tamper Prevention:**
   - Supplying `{"returns": [0.01, -0.02, ...], "data_source_mode": "REAL_DATA"}` results in the provenance tag being assigned `USER_UPLOADED_DATA`, not `REAL_DATA`. The client's assertion is completely ignored.
   - Confirmed in test `test_user_upload_provenance_cannot_be_spoofed_as_real`.

---

## 5. Automated Test Suite Execution Results

Executed locally using `PYTHONPATH=.:backend pytest`:

```bash
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/vemanahemanthbabu/srujana_hackathon_2
plugins: anyio-4.12.1, Faker-40.37.0, asyncio-1.4.0
collected 585 items

backend/tests/test_allocation_lab.py .....                               [  0%]
backend/tests/test_application_api.py ........................           [  4%]
backend/tests/test_attribution.py ...                                    [  5%]
backend/tests/test_backend_acceptance_workflows.py .........             [  7%]
backend/tests/test_custom_model_builder.py ......                        [  8%]
backend/tests/test_data_diagnostics.py ......                            [  9%]
backend/tests/test_engine_foundation.py ................................ [ 14%]
....................                                                     [ 17%]
backend/tests/test_experiment_studio.py ..............................   [ 23%]
backend/tests/test_forecast_backtest.py ...................              [ 26%]
backend/tests/test_fragility_lab.py ................................     [ 31%]
backend/tests/test_fragility_new_attacks.py ......                       [ 32%]
backend/tests/test_market_data.py ....                                   [ 33%]
backend/tests/test_ml_evaluation.py .....                                [ 34%]
backend/tests/test_model_integration_lab.py .........                    [ 35%]
backend/tests/test_new_api_and_cli.py ........                           [ 37%]
backend/tests/test_phase12_corrective_suite.py ......................... [ 41%]
backend/tests/test_phase13_full_platform_campaign.py ...........         [ 43%]
backend/tests/test_phase14_adversarial_verification.py ................. [ 46%]
.....                                                                    [ 47%]
backend/tests/test_phase15_remediation.py ...............                [ 49%]
backend/tests/test_plugin_benchmarking.py .............................. [ 54%]
.............                                                            [ 57%]
backend/tests/test_portfolio_lab.py .............................        [ 62%]
backend/tests/test_project_and_model_registry.py .....                   [ 62%]
backend/tests/test_real_data_policy.py ...........                       [ 64%]
backend/tests/test_reproducibility_lab.py .............................. [ 69%]
........                                                                 [ 71%]
backend/tests/test_reverse_stress_and_boundary.py .......                [ 72%]
backend/tests/test_risk_engine.py ...................................... [ 78%]
backend/tests/test_scenario_engine.py ..............................     [ 84%]
backend/tests/test_sdk_and_cli.py .............                          [ 86%]
backend/tests/test_simulation_uncertainty.py .....                       [ 87%]
backend/tests/test_statistical_calibration.py ................           [ 89%]
backend/tests/test_upstox_adapter.py ..........................          [ 94%]
backend/tests/test_validation_edge_cases.py ............................ [ 99%]
...                                                                      [ 99%]
backend/tests/test_validation_lab.py ..                                  [100%]

======================== 585 passed, 1 warning in 1.83s ========================
```

---

## 6. Real-Data and Provenance Gaps

1. **Corporate Actions & Dividends (BLOCKED):**
   - The Upstox Market Data V3 historical candles represent raw traded prices. Corporate action adjustments (e.g. stock splits, bonus shares, cash dividends) are not provided via this endpoint.
   - *Policy:* Long historical windows must be reviewed or user-provided split-adjusted series must be uploaded.
2. **Sovereign Interest Rate & Macro Feeds (BLOCKED):**
   - Upstox does not offer macroeconomic telemetry (RBI repo rate, inflation, sovereign bond yield curves).
   - *Policy:* Risk-free rate defaults to 0.0 or user-specified value; macro scenarios require user shock specifications.
3. **Consolidated Multi-Broker Holdings (NOT VERIFIED):**
   - The Upstox adapter is strictly limited to market data. It does not ingest live broker portfolio holdings or positions, as this would require full trading account authorization.
   - *Policy:* Portfolios must be ingested via verified user upload (CSV/JSON).

---

## 7. Audit Sign-Off

The real-data readiness audit confirms that FragilityShield operates truthfully, with zero unannounced synthetic fallbacks, active read-only Upstox market data access, anti-spoofing provenance tracking, and 585 passing automated tests.
