# QA REPORT — FRAGILITYSHIELD PAGE 19: BOOTSTRAP & UNCERTAINTY LAB

**Route:** `/labs/uncertainty` (and `/labs/bootstrap`)  
**Status:** **VERIFIED**  
**Date:** 2026-10-25  
**Backend Engine:** `backend/fragility_engine/uncertainty_engine.py`  
**Test Suite:** `backend/tests/test_page_19_uncertainty.py` (3/3 passed)

---

## 1. Executive Summary

Page 19 (Bootstrap & Uncertainty Lab) quantifies estimation noise and parameter vulnerability in backtested performance metrics. It supports block resampling methods preserving serial autocorrelation and volatility clustering, generates empirical confidence intervals (Percentile, Basic, and Normal approximation), and conducts block length sensitivity scans.

---

## 2. Core Capabilities & Mathematical Specifications

| Capability | Technical Description | Source Entry Point |
|---|---|---|
| **Resampling Methodologies** | Implements Moving Block Bootstrap (Künsch 1989), Circular Block Bootstrap (Politis & Romano 1992), Stationary Bootstrap (Politis & Romano 1994, geometric block length), and canonical i.i.d. draws. | `backend/fragility_engine/uncertainty_engine.py:run_bootstrap_uncertainty_analysis` |
| **Statistical Estimators** | Resamples and measures confidence distributions for Sharpe Ratio, Sortino Ratio, Calmar Ratio, Annualized Volatility, and Maximum Drawdown. | `backend/fragility_engine/uncertainty_engine.py:run_bootstrap_uncertainty_analysis` |
| **Confidence Interval Diagnostics** | Computes Percentile intervals $[q_{\alpha/2}, q_{1-\alpha/2}]$, Basic/Empirical intervals $[2\hat{\theta} - q_{1-\alpha/2}, 2\hat{\theta} - q_{\alpha/2}]$, and standard error Normal approximations. | `backend/fragility_engine/uncertainty_engine.py:run_bootstrap_uncertainty_analysis` |
| **Block Length Sensitivity Scan** | Scans window lengths from 1 to 40 days to diagnose sensitivity of confidence interval widths to underlying temporal dependence. | `backend/fragility_engine/uncertainty_engine.py:compute_block_length_sensitivity_scan` |
| **Sampling Histogram** | Produces a 25-bin empirical distribution of resampled metric replicates with overlay of standard error and p-value against zero skill. | `backend/fragility_engine/uncertainty_engine.py:run_bootstrap_uncertainty_analysis` |

---

## 3. Endpoints & API Contract

- `POST /api/uncertainty/bootstrap`: Executes bootstrap resamples across configured metric and block scheme.
- `POST /api/uncertainty/block-sensitivity`: Runs parameter sensitivity across block sizes (1 to 40).

---

## 4. Test Verification & Actual Outcomes

Command executed:
```bash
PYTHONPATH=backend:. pytest backend/tests/test_page_19_uncertainty.py -v
```
Output:
```
============================= test session starts ==============================
backend/tests/test_page_19_uncertainty.py::test_page_19_resampling_schemes PASSED [ 33%]
backend/tests/test_page_19_uncertainty.py::test_page_19_block_length_sensitivity PASSED [ 66%]
backend/tests/test_page_19_uncertainty.py::test_page_19_api_endpoints PASSED [100%]
============================== 3 passed in 0.31s ===============================
```

---

## 5. Traceability Matrix

| Requirement | Description | Status | Evidence |
|---|---|---|---|
| REQ-19-01 | 4 block resampling schemes | **VERIFIED** | Moving, Circular, Stationary, i.i.d. |
| REQ-19-02 | Metric uncertainty quantification | **VERIFIED** | Sharpe, Sortino, Calmar, Volatility, MaxDD |
| REQ-19-03 | Percentile, Basic, Normal CIs | **VERIFIED** | `uncertainty_metrics` in analysis response |
| REQ-19-04 | Block length sensitivity scan | **VERIFIED** | `compute_block_length_sensitivity_scan` |
| REQ-19-05 | Dedicated test suite | **VERIFIED** | `backend/tests/test_page_19_uncertainty.py` passing 3/3 |
