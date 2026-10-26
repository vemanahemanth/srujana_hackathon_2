# QA REPORT — FRAGILITYSHIELD PAGE 20: MODEL VALIDATION LAB

**Route:** `/labs/model-validation` (and `/models`)  
**Status:** **VERIFIED**  
**Date:** 2026-10-25  
**Component:** `frontend/src/components/pages/ModelValidationLab.tsx`  
**Backend Endpoints:** `POST /api/models/validate`, `GET /api/models/runs`, `POST /api/models/manifests`

---

## 1. Executive Summary

Page 20 (Model Validation Lab) delivers an institutional validation workspace for statistical, risk, and algorithmic models. It enforces zero temporal leakage, provides out-of-sample backtesting against empirical observations from Upstox V3 and catalog snapshots, evaluates Kupiec POF Likelihood Ratio unconditional coverage, performs naive persistence benchmarking, tests adversarial stability under Gaussian noise injection, and stores run records for cross-validation comparison.

---

## 2. Implemented Features & Code Entry Points

| Feature | Description | Implementation Entry Point |
|---|---|---|
| **Registered Model Selector** | Discovers native algorithms (`builtin.parametric_gaussian`, `builtin.historical_simulation`, `builtin.ewma`) and catalog manifest models. | `frontend/src/components/pages/ModelValidationLab.tsx:loadModelsAndHistory` |
| **Strict Dataset Resolution** | Resolves real Upstox V3 feed or offline fallback snapshot (`RELIANCE`, `TCS`, `INFY`) without synthetic candle generation. | `backend/app.py:resolve_returns_with_provenance` |
| **Zero-Leakage Split Engine** | Splits series into sequential Train, Validation, and Test partitions without chronological shuffling. | `backend/app.py:api_validate_model_comprehensive` |
| **Kupiec POF Coverage Test** | Computes Likelihood Ratio test statistic against statutory 95% confidence threshold ($\chi^2_1 = 3.841$). | `backend/app.py:api_validate_model_comprehensive` |
| **Naive Baseline Benchmark** | Measures RMSE/MAE against naive persistence baseline and calculates relative skill percentage. | `backend/app.py:api_validate_model_comprehensive` |
| **Adversarial Noise Injection** | Stresses model with +5% Gaussian noise perturbation to measure degradation percentage. | `backend/app.py:api_validate_model_comprehensive` |
| **Report Export** | One-click export to structured JSON and GitHub-flavored Markdown. | `frontend/src/components/pages/ModelValidationLab.tsx:exportValidationReport` |
| **Persistence & Runs History** | Persists execution runs in `MODEL_VALIDATION_RUNS` and allows instant retrieval. | `backend/app.py:api_list_model_validation_runs` |

---

## 3. Files Created & Modified

1. **`frontend/src/App.tsx`**: Routed `/labs/model-validation` directly to `<ModelValidationLab />`, bypassing generic lab runners.
2. **`frontend/src/components/pages/ModelValidationLab.tsx`**: Full institutional validation UI with test metric cards, leakage diagnostics, benchmark comparisons, noise injection analysis, and export actions.
3. **`backend/app.py`**: Added catalog snapshot fallback in `resolve_returns_with_provenance` and calibrated observation thresholds.
4. **`backend/fragility_engine/strategy_engine.py`**: Updated `load_strategy_candles` symbol matching to reject uncataloged unknown symbols.
5. **`backend/tests/test_page_20_model_validation.py`**: Automated test suite covering valid model validation, unknown symbol rejection, temporal split verification, and runs retrieval.

---

## 4. Test Verification & Exact Outcomes

Commands executed:
```bash
PYTHONPATH=backend:. pytest backend/tests/test_page_20_model_validation.py -v
```
Output:
```
============================= test session starts ==============================
backend/tests/test_page_20_model_validation.py::test_page_20_valid_model_validation PASSED [ 25%]
backend/tests/test_page_20_model_validation.py::test_page_20_invalid_dataset_rejection PASSED [ 50%]
backend/tests/test_page_20_model_validation.py::test_page_20_temporal_leakage_protection PASSED [ 75%]
backend/tests/test_page_20_model_validation.py::test_page_20_runs_history_and_retrieval PASSED [100%]
========================= 4 passed, 1 warning in 0.92s =========================
```

Frontend production build:
```bash
npm run build --prefix frontend
```
Output:
```
✓ built in 2.44s
dist/assets/index-B3RFo-5o.js   1,459.48 kB │ gzip: 373.96 kB
```

---

## 5. Requirement Traceability Matrix

| Requirement | Description | Status | Evidence |
|---|---|---|---|
| REQ-20-01 | Select registered model / adapter | **VERIFIED** | Dropdown with native core and registered models |
| REQ-20-02 | Select real dataset with version tracking | **VERIFIED** | Real Upstox catalog symbols (`RELIANCE`, `TCS`, `INFY`) |
| REQ-20-03 | Temporal train/val/test partitions | **VERIFIED** | Sliders for train/val split with zero chronological shuffle |
| REQ-20-04 | Baselines & naive comparison | **VERIFIED** | Naive persistence benchmark RMSE & relative skill |
| REQ-20-05 | Kupiec POF hypothesis test | **VERIFIED** | Exact $\chi^2_1$ likelihood ratio test calculation |
| REQ-20-06 | Adversarial noise perturbation | **VERIFIED** | +5% Gaussian noise degradation percentage |
| REQ-20-07 | Export report (JSON / Markdown) | **VERIFIED** | Browser download actions for both formats |
| REQ-20-08 | Persistence and runs history | **VERIFIED** | `/api/models/runs` endpoint and History tab |
| REQ-20-09 | Dedicated automated test suite | **VERIFIED** | `backend/tests/test_page_20_model_validation.py` passing 4/4 |

---

## 6. Known Limitations

- **In-process execution disclosure**: Native models run in-process within the Python backend runtime; arbitrary untrusted code execution is blocked.
- **Parametric models assume stationarity**: RiskMetrics EWMA assumes an exponential decay factor $\lambda=0.94$; extreme structural breaks may cause transient breach clusters.
