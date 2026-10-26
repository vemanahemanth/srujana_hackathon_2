# QA REPORT — FRAGILITYSHIELD PAGE 16: BACKTESTING LAB

**Route:** `/labs/backtesting`  
**Status:** **VERIFIED**  
**Date:** 2026-10-25  
**Component:** `frontend/src/components/pages/StrategyBacktestLab.tsx`  
**Backend Engine:** `backend/fragility_engine/backtesting_lab.py` & `backend/fragility_engine/strategy_engine.py`  
**Test Suite:** `backend/tests/test_page_16_backtesting_lab.py` (8/8 passed)

---

## 1. Executive Summary

Page 16 (Backtesting Lab) delivers institutional-grade quantitative strategy evaluation. It enforces a strict anti-bias verification protocol (detecting lookahead bias, unhedged cash drag, execution latency violations, and missing transaction friction), executes genuine path-dependent trade ablation studies, and provides full configuration lifecycle management.

---

## 2. Implemented Capabilities & Entry Points

| Capability | Technical Description | Source Entry Point |
|---|---|---|
| **Anti-Bias Preflight Audit** | Checks strategy specifications against 8 mandatory rules: lookahead execution, causal indicator integrity, survivorship, train/test contamination, timestamp alignment, execution friction, and sample size sufficiency. | [`backend/fragility_engine/backtesting_lab.py:run_antibias_audit`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/backtesting_lab.py) |
| **Trade Ablation Engine** | Rigorously distinguishes between simple post-hoc trade deletion and genuine path-dependent portfolio re-simulation, revealing true performance fragility. | [`backend/fragility_engine/backtesting_lab.py:run_trade_ablation_analysis`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/backtesting_lab.py) |
| **Realistic Cost Modeling** | Deducts statutory exchange fees, STT, brokerage, and bid-ask slippage on every fill. Fails if execution delay is $< 1$ bar (T+1 fill required). | [`backend/fragility_engine/strategy_engine.py:simulate_strategy_execution`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/strategy_engine.py) |
| **Configuration Workspace** | Enables saving, listing, and cloning parameter configurations with deterministic seeds and persistent profile keys. | [`backend/fragility_engine/backtesting_lab.py:save_backtest_configuration`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/backtesting_lab.py) |
| **Interactive Research UI** | Visualizes equity curve, underwater drawdown chart, fill log table, rolling analytics, and bias audit scorecard. | [`frontend/src/components/pages/StrategyBacktestLab.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/StrategyBacktestLab.tsx) |

---

## 3. Endpoints & API Contract

- `POST /api/backtesting/validate`: Audits configuration against bias rules and returns verification badges.
- `POST /api/backtesting/run`: Executes full sequential backtest on genuine Upstox historical candles.
- `POST /api/backtesting/ablation`: Runs ablation analysis across entry filters, stop losses, and take-profit targets.
- `GET /api/backtesting/configs`: Lists saved backtest configuration profiles.
- `POST /api/backtesting/configs/save`: Persists custom backtest parameters.
- `POST /api/backtesting/configs/duplicate`: Clones an existing configuration for parameter iteration.

---

## 4. Test Verification & Actual Outcomes

Command executed:
```bash
PYTHONPATH=backend:. pytest backend/tests/test_page_16_backtesting_lab.py -v
```

Output:
```
============================= test session starts ==============================
backend/tests/test_page_16_backtesting_lab.py::test_page_16_preflight_validation PASSED [ 12%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_antibias_audit PASSED [ 25%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_trade_ablation_analysis PASSED [ 37%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_configuration_management PASSED [ 50%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_api_endpoints PASSED [ 62%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_chronological_execution_and_frictions PASSED [ 75%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_cash_accounting_and_drawdown PASSED [ 87%]
backend/tests/test_page_16_backtesting_lab.py::test_page_16_trade_ledger_integrity PASSED [100%]
========================= 8 passed, 1 warning in 1.32s =========================
```

---

## 5. Traceability Matrix

1. **Anti-Bias Verification**: 8 checks executed with explicit statuses (`passed`, `failed`, `warning`, `not assessed`).
2. **Path-Dependent Ablation**: Clearly distinguishes report-only filtering from genuine path-dependent re-simulation.
3. **Execution Delay**: Enforces $T+1$ execution delay on signals to prevent lookahead leakage.
4. **Realistic Costs**: Strict fee bps and slippage bps modeling.
5. **No Synthetic Candles**: Uses verified Upstox V3 historical candles from local catalog.
