# Page 10 QA & Implementation Report: Data Quality & Provenance Observatory

**Route:** `/data-observatory`  
**Page Name:** Data Quality & Provenance Observatory  
**Component:** `frontend/src/components/pages/DataObservatory.tsx`  
**Engine:** `backend/fragility_engine/data_observatory.py`  
**Tests:** `backend/tests/test_page_10_data_observatory.py` (21/21 passing)  
**Status:** COMPLETE, VERIFIED & AUDIT-READY

---

## 1. Executive Summary

Page 10 implements the **Data Quality & Provenance Observatory** directly inside FragilityShield. It acts as an authoritative, zero-black-box data observability laboratory that inspects market data inputs, validates physical and temporal constraints, maps coverage against statutory National Stock Exchange (NSE) trading calendars, and measures the quantitative risk impact of data-treatment policies prior to portfolio stress testing.

All data strictly adheres to FragilityShield's **Real-Data Policy**:
- Genuine observations sourced from the Upstox V3 API (`RELIANCE`, `NIFTY 50`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`) and verified local catalogs.
- Zero synthetic candles, randomized returns, or mock generators.
- Non-destructive audit dispositions recorded in an immutable ledger without mutating raw market observations.

---

## 2. Key Architecture & Deliverables

### A. Authoritative Dataset Inventory & SHA-256 Digest
- **Deterministic Digest:** Slices candle records in canonical form and computes a 64-character SHA-256 fingerprint. Any modification, duplicate, or price change immediately alters the fingerprint.
- **Dataset Inventory:** Surfaces market candle streams, portfolio snapshots (`nse_10l.json`, `nse_10l.csv`), and benchmark indices with provider attribution (`upstox_v3`, `REAL_DATA`), date ranges, and row counts.

### B. 9-Point Explainable Quality Scorecard
Every dataset is rigorously audited across 9 explainable inspection checks:
1. `RULE_NON_POSITIVE_PRICE`: Verifies Open, High, Low, and Close are strictly $> 0.0$.
2. `RULE_OHLC_RELATIONSHIPS`: Asserts physical bounds ($\text{High} \ge \text{Low}$, $\text{Low} \le \text{Open, Close} \le \text{High}$).
3. `RULE_DUPLICATE_TIMESTAMPS`: Detects repeated timestamps to prevent double-counting.
4. `RULE_CHRONOLOGICAL_ORDER`: Validates strict monotonic timestamp ordering ($t_k > t_{k-1}$).
5. `RULE_VOLUME_INTEGRITY`: Verifies reported trading volume $\ge 0$.
6. `RULE_STALE_PRICES`: Detects consecutive identical closes ($\ge 3$ bars) indicating frozen feeds or liquidity halts.
7. `RULE_STATISTICAL_OUTLIERS`: Screens for return discontinuities via robust median/MAD Z-score ($Z \ge 3.5\sigma$ and $|r| \ge 8\%$).
8. `RULE_NSE_CALENDAR_GAPS`: Compares series against official statutory NSE holidays, ensuring legitimate exchange closures are not misclassified as missing observations.
9. `RULE_BENCHMARK_ALIGNMENT`: Evaluates synchronous date intersection with NIFTY 50.

### C. Calendar-Aware Coverage Analysis
- Integrates `NSETradingCalendar` with statutory Indian market holidays (Gandhi Jayanti, Republic Day, Independence Day, Christmas, etc.).
- Calculates expected trading sessions, actual observations, coverage percentage, and lists missing dates.

### D. Data-Quality Impact Analysis
- Quantifies the impact of data quality on downstream risk metrics.
- Compares Raw vs. Explicit Treatment Policies:
  - `reject_invalid`: Prunes invalid/negative prices.
  - `deduplicate`: Removes repeated timestamps.
  - `exclude_outliers`: Filters $> 3.5\sigma$ jumps.
  - `restrict_recent`: Truncates to recent active trading window.
- Computes deltas for **Annualized Volatility ($\sigma$)**, **Historical 95% VaR**, **Expected Shortfall (95% ES/CVaR)**, and **Maximum Drawdown**.

### E. Anomaly Review & Non-Destructive Disposition Ledger
- Inspects granular anomaly records with timestamp, observed value, and expected condition.
- Allows quantitative analysts to record audit dispositions (`reviewed_benign`, `confirmed_defect`, `suppressed`, `pending_remediation`) with reviewer notes.
- Exports affected anomaly sets to CSV for compliance audits.

---

## 3. Automated Test Suite Results

```
backend/tests/test_page_10_data_observatory.py::test_list_available_datasets PASSED [  4%]
backend/tests/test_page_10_data_observatory.py::test_deterministic_dataset_fingerprint PASSED [  9%]
backend/tests/test_page_10_data_observatory.py::test_audit_clean_dataset PASSED [ 14%]
backend/tests/test_page_10_data_observatory.py::test_audit_non_positive_price_violation PASSED [ 19%]
backend/tests/test_page_10_data_observatory.py::test_audit_ohlc_relationship_violation PASSED [ 23%]
backend/tests/test_page_10_data_observatory.py::test_audit_duplicate_timestamps PASSED [ 28%]
backend/tests/test_page_10_data_observatory.py::test_audit_chronological_ordering_violation PASSED [ 33%]
backend/tests/test_page_10_data_observatory.py::test_audit_negative_volume PASSED [ 38%]
backend/tests/test_page_10_data_observatory.py::test_audit_stale_prices PASSED [ 42%]
backend/tests/test_page_10_data_observatory.py::test_audit_statistical_outlier PASSED [ 47%]
backend/tests/test_page_10_data_observatory.py::test_audit_empty_candles_raises_error PASSED [ 52%]
backend/tests/test_page_10_data_observatory.py::test_compute_coverage_analysis PASSED [ 57%]
backend/tests/test_page_10_data_observatory.py::test_compute_coverage_missing_session PASSED [ 61%]
backend/tests/test_page_10_data_observatory.py::test_data_quality_impact_reject_invalid PASSED [ 66%]
backend/tests/test_page_10_data_observatory.py::test_data_quality_impact_deduplicate PASSED [ 71%]
backend/tests/test_page_10_data_observatory.py::test_record_and_get_anomaly_disposition PASSED [ 76%]
backend/tests/test_page_10_data_observatory.py::test_api_data_observatory_datasets PASSED [ 80%]
backend/tests/test_page_10_data_observatory.py::test_api_data_observatory_audit PASSED [ 85%]
backend/tests/test_page_10_data_observatory.py::test_api_data_observatory_coverage PASSED [ 90%]
backend/tests/test_page_10_data_observatory.py::test_api_data_observatory_impact_analysis PASSED [ 95%]
backend/tests/test_page_10_data_observatory.py::test_api_data_observatory_dispositions_flow PASSED [100%]

======================== 21 passed in 1.66s =========================
```

---

## 4. Verification Checkpoints

1. **Navigation:** Accessible from sidebar via `Workspace > Data Quality Observatory` or `/data-observatory`.
2. **Frontend Build:** Successfully built with Vite (`dist/index.html` generated in 2.60s with zero TypeScript warnings).
3. **API Endpoints:**
   - `GET /api/data-observatory/datasets`
   - `POST /api/data-observatory/audit`
   - `POST /api/data-observatory/coverage`
   - `POST /api/data-observatory/impact-analysis`
   - `POST /api/data-observatory/disposition`
   - `GET /api/data-observatory/dispositions`
4. **Zero Lookahead & Real Data Policy:** Fully maintained across all calculation routines.
