# Page 16: Strategy Backtesting & Assumption Audit Lab Implementation Report

**Project:** FragilityShield — The Assumption-Aware Investment Risk & Scenario Lab  
**Route:** `/backtesting-lab` (Alias `/labs/backtest`)  
**Page Title:** Strategy Backtesting & Assumption Audit Lab  
**Verification Date:** October 2026  
**Status:** FULLY IMPLEMENTED & VERIFIED  

---

## 1. Executive Summary

Page 16 enhances FragilityShield's quantitative backtesting engine by bridging realistic walk-forward portfolio simulation with a rigorous 8-point Anti-Bias diagnostic framework, rolling risk analytics, multi-level trade ablation, and complete mathematical cash reconciliation.

Every market observation is derived from genuine Upstox V3 historical market data across liquid NSE equities (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`, `SBIN`, `TATAMOTORS`, `BHARTIARTL`, `ITC`, `KOTAKBANK`). Zero synthetic candles, mock trades, or random number generators are permitted.

---

## 2. Quantitative Anti-Bias Framework (8 Checks)

The backtesting lab systematically evaluates strategy rules against 8 structural failure modes:

| # | Diagnostic Check | Verification Logic | Pass Criteria |
|---|---|---|---|
| 1 | **RULE_LOOKAHEAD_BIAS** | Verifies timestamp ordering; signals computed on $Close_t$ are strictly scheduled for execution on $Open_{t+1}$ | $t_{\text{exec}} > t_{\text{signal}}$ strictly |
| 2 | **RULE_EXECUTION_DELAY** | Confirms 1-bar execution delay is actively enforced; no same-bar fills | Fill bar index > Signal bar index |
| 3 | **RULE_SURVIVORSHIP_BIAS** | Checks point-in-time constituent flags and warns against post-hoc universe selection | Verified catalog or PIT flag |
| 4 | **RULE_TRANSACTION_COSTS** | Confirms non-zero fees and slippage deduction in every single trade execution | Fee + Slippage $\ge 1$ bps |
| 5 | **RULE_SAMPLE_SIZE_ADEQUACY** | Checks whether backtest contains at least 30 trade executions for statistical significance | Total trades $\ge 30$ |
| 6 | **RULE_OVERFITTING_DEGRADATION** | Compares In-Sample (Train) Sharpe vs Out-Of-Sample (Test) Sharpe | Degradation $\le 30\%$ |
| 7 | **RULE_DATA_SNOOPING_MULTIPLE_TESTS** | Evaluates whether strategy underwent grid search or parameter tuning without adjustment | DSR deflation test |
| 8 | **RULE_CASH_RECONCILIATION** | Matches cumulative net P&L of all closed trades against portfolio equity growth | $\| \Delta \text{Equity} - \sum \text{PnL} \| \le ₹0.01$ |

---

## 3. Trade Ablation Analysis

A core innovation of Page 16 is contrasting two fundamentally different ablation methodologies:

1. **Diagnostic Post-Hoc Removal (Statistical Heuristic):**  
   Removes top winning trades from the trade ledger after the backtest completes, demonstrating statistical fragility or dependence on outlier returns.
2. **Path-Dependent Portfolio Re-Simulation (Economic Reality):**  
   Re-simulates the portfolio from the inception date with those trade triggers skipped. At each skipped trade, the capital remains in cash, altering compounding, margin constraints, and subsequent entry opportunities across time.

---

## 4. REST API Endpoints

All endpoints are mounted in `backend/app.py`:

- `POST /api/backtesting/preflight-validate`: Pre-flight sanity validation of parameters, dates, and execution delay.
- `POST /api/backtesting/run`: Executes full walk-forward backtest, computes anti-bias scorecard, rolling 30-day Sharpe and volatility, and monthly returns.
- `POST /api/backtesting/trade-ablation`: Executes both post-hoc trade exclusion and true path-dependent re-simulation.
- `GET /api/backtesting/configs`: Retrieves saved backtest configurations.
- `POST /api/backtesting/configs`: Persists a backtest configuration with metadata.

---

## 5. Automated Test Suite

A dedicated automated test suite was created in `backend/tests/test_page_16_backtesting_lab.py`:
- `test_page_16_preflight_validation`: Tests parameter validity, negative capital rejection, and date range checks.
- `test_page_16_antibias_audit`: Validates that all 8 checks execute and return structured pass/warning/fail statuses.
- `test_page_16_trade_ablation_analysis`: Validates post-hoc removal vs path-dependent re-simulation.
- `test_page_16_configuration_management`: Tests configuration saving, retrieval, and schema adherence.
- `test_page_16_api_endpoints`: End-to-end HTTP integration tests for all 4 endpoints using Starlette `TestClient`.

**Status:** 5/5 tests PASSED (0 failures, 0 errors).
