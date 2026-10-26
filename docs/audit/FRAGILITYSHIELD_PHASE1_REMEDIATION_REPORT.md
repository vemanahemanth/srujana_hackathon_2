# FRAGILITYSHIELD — PHASE 1 QUANTITATIVE INTEGRITY REMEDIATION REPORT

**Author**: Senior Quantitative Risk Researcher & Statistical Validation Specialist  
**Repository**: `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Date**: October 26, 2026  
**Status**: COMPLETE — ALL TESTS VERIFIED (878 PASSED, 0 FAILED)  
**Deliverable**: `docs/audit/FRAGILITYSHIELD_PHASE1_REMEDIATION_REPORT.md`  

---

## 1. Executive Summary

Phase 1 Quantitative Integrity Remediation addressed three confirmed critical mathematical and provenance defects identified in the whole-repository audit evidence ledger (`docs/audit/FRAGILITYSHIELD_AUDIT_EVIDENCE_LEDGER.md`):

1. **Allocation Covariance Generation and Data Provenance (CRIT-01)**: Completely eradicated silent synthetic fallback correlations that masqueraded as empirical user portfolio data. Implemented rigorous covariance matrix validation (2D square, finiteness, symmetry tolerance $\le 10^{-4}$, positive semi-definiteness $\lambda_{\min} \ge -10^{-7}$, dimension/asset matching), empirical historical return alignment, explicit synthetic demo mode requirement (`allow_synthetic: true`), and structured HTTP 422 validation envelopes.
2. **Kupiec POF Statistical Correctness (CRIT-03)**: Replaced ad-hoc buggy inline logic with a mathematically rigorous unconditional-coverage likelihood ratio test using exact continuous limits ($0 \ln 0 = 0$), correctly handling both zero-breach over-conservatism ($x=0$) and catastrophic failure ($x=N$). Separated computed statistic from decision, evaluated Clopper-Pearson exact binomial confidence intervals, and instituted clear sample sufficiency categorization (`INSUFFICIENT_POWER`, `LOW_POWER`, `SUFFICIENT`) so small sample tests are never falsely presented as proof of calibration.
3. **VaR Quantile Scoring and Honest Presentation (MATH-01, FRONT-01)**: Replaced inappropriate point-forecast squared error (RMSE on loss threshold) with the strictly consistent quantile scoring rule (Tick / Pinball Loss at $lpha=0.95$). Evaluated relative skill against an empirical historical quantile baseline. Eliminated hardcoded `+` signs, hardcoded `'PASSED'` statuses, and deceptive badges in `frontend/src/components/pages/ModelValidationLab.tsx`. Small sample runs now honestly render as `INCONCLUSIVE (N=...)`, while underperforming models render negative skill in rose with `UNDERPERFORMING` badges.

---

## 2. Confirmed Root Cause Analysis

### Issue 1: Allocation Covariance Generation & Silent Synthetic Fallback (`CRIT-01`)
- **Root Cause**: `backend/app.py` around `api_optimize_allocation` previously generated a hardcoded synthetic sector correlation matrix ($0.35 + 0.65 I$) whenever historical price candles were missing or incomplete, without checking with the user or disclosing that synthetic data was used. The output returned without warning, misrepresenting simulated risk as user-supplied portfolio reality. Furthermore, user-supplied covariance matrices were accepted without checking symmetry, positive semi-definiteness, or NaN/Inf values.
- **Remediation**:
  - Implemented `validate_covariance_matrix(...)`: Enforces 2D square shape ($N \ge 2$), numeric finiteness, symmetry ($|C - C^T| \le 10^{-4}$), positive semi-definiteness ($\min(	ext{eig}) \ge -10^{-7}$), small regularizer ($10^{-8} I$) for near-singular matrices, and asset ID alignment.
  - Path 1 (Explicit Covariance): Validates user matrix + asset IDs, records `DataProvenance.user_uploaded`. Rejects invalid inputs with HTTP 422.
  - Path 2 (Empirical Return Observations): Accepts returns dict or aligned returns matrix ($\ge 5$ observations), computes sample covariance, records `DataProvenance.user_uploaded`.
  - Path 3 (Portfolio Holdings): Attempts empirical candle loading from local catalog. If all holdings have valid historical candles, computes empirical sample covariance and records `DataProvenance.real_provider(provider="historical_candles")`. If any holding lacks empirical data, explicitly requires `allow_synthetic: true`; otherwise rejects with structured HTTP 422 detailing missing assets.
  - When `allow_synthetic: true` is set, labels `is_synthetic: true` and `DataProvenance.synthetic_demo(reason=...)`.

### Issue 2: Kupiec POF Statistical Implementation & Boundary Failure (`CRIT-03`)
- **Root Cause**: `backend/app.py` contained an inline snippet where boundary cases $x = 0$ or $x = N$ caused $\ln(0)$ crashes, or were bypassed with conditional shortcuts that returned an automatic pass for $x=0$ or $x=N$. Furthermore, sample size was ignored: a sample of $N=4$ with 0 breaches was declared "PASSED" even though expected breaches was $4 	imes 0.05 = 0.2 < 1.0$, which has zero statistical power.
- **Remediation**:
  - Standardized on `fragility_engine.risk_model_validation.calculate_kupiec_test(...)`.
  - Implemented analytical continuous limits using $0 \ln 0 = 0$:
    - For $x = 0$: $	ext{LR} = -2 N \ln(1 - p)$. Catches over-conservative models (e.g., $N=100, x=0 \implies 	ext{LR}=10.2587 > 3.841 \implies$ REJECT).
    - For $x = N$: $	ext{LR} = -2 N \ln(p)$. Catches catastrophic model failure (e.g., $N=100, x=100 \implies 	ext{LR}=599.15 \gg 3.841 \implies$ REJECT).
  - Validated boundary inputs: $N > 0$, $0 \le x \le N$, $0 < p < 1$.
  - Integrated Clopper-Pearson exact binomial confidence intervals ($95\%$).
  - Separated statistical test decision from sample sufficiency:
    - $\mathbb{E}[x] < 1.0$: `INSUFFICIENT_POWER` $\implies$ `sample_size_warning = True`
    - $1.0 \le \mathbb{E}[x] < 5.0$: `LOW_POWER` $\implies$ `sample_size_warning = True`
    - $\mathbb{E}[x] \ge 5.0$: `SUFFICIENT` $\implies$ `sample_size_warning = False`
  - Explicitly documented that Kupiec unconditional coverage does not test breach independence or temporal clustering.

### Issue 3: VaR Quantile Scoring & Misleading UI Presentation (`MATH-01`, `FRONT-01`)
- **Root Cause**: In `backend/app.py:api_validate_model`, model "skill" was computed as an RMSE error reduction between model VaR threshold and test loss returns. In financial risk theory, VaR is a tail quantile forecast; squared error on threshold vs return is mathematically invalid and not a proper scoring rule for quantiles. In `frontend/src/components/pages/ModelValidationLab.tsx`, UI components had hardcoded `+` signs (`+${relative_skill_pct}%`) and hardcoded `'PASSED'` badges regardless of actual performance or sample size.
- **Remediation**:
  - Backend: Implemented the strictly consistent Quantile Pinball / Tick Loss scoring rule at nominal tail level $lpha=0.95$:
    $$S_lpha(y, q) = (y - q)(lpha - \mathbb{I}(y < q))$$
  - Baseline comparison: Evaluated against the empirical training sample quantile at $lpha=0.95$:
    $$	ext{Skill}_{	ext{quantile}} = \left(1.0 - rac{ar{S}_{	ext{model}}}{ar{S}_{	ext{baseline}}}ight) 	imes 100$$
  - Preserved negative skill values with true algebraic sign and assigned `UNDERPERFORMING` / `UNSKILLFUL` verdict.
  - Frontend:
    - Replaced hardcoded `+` prefixes with dynamic sign evaluation (`${val > 0 ? '+' : ''}${val}%`).
    - Render positive skill in emerald (`text-emerald-400`, `PASSED`).
    - Render negative skill in rose (`text-rose-400`, `UNDERPERFORMING`).
    - Render small sample Kupiec results as amber warnings (`text-amber-400`, `INCONCLUSIVE (N=...)`).
    - Added clear explanatory text that Kupiec POF does not test breach clustering.

---

## 3. Files and Functions Changed

| File Path | Function / Component | Type of Change | Rationale |
| :--- | :--- | :--- | :--- |
| `backend/app.py` | `validate_covariance_matrix` | New Function | Strict PSD, symmetry, finiteness, and dimension validation for covariance inputs |
| `backend/app.py` | `api_optimize_allocation` | Modified Endpoint | Enforces covariance validation, empirical candle resolution, explicit synthetic demo mode, and HTTP 422 on missing/invalid data |
| `backend/app.py` | `api_validate_model_comprehensive` | Modified Endpoint | Integrates `calculate_kupiec_test` and Pinball Loss quantile scoring rule vs training quantile baseline |
| `backend/fragility_engine/risk_model_validation.py` | `KupiecTestResult` & `calculate_kupiec_test` | Modified Function | Adds exact continuous limits ($0\ln 0 = 0$), sample sufficiency levels, boundary validation, and independence disclaimer |
| `frontend/src/components/pages/ModelValidationLab.tsx` | Top KPI Cards, Evidence Modal, Export & Comparison Tables | Modified Components | Removes hardcoded `+` and `'PASSED'` badges; renders negative skill and inconclusive small-sample states honestly |
| `backend/tests/test_phase1_quantitative_integrity.py` | 3 Test Classes (30 Tests) | New Test Suite | Comprehensive unit, analytical reference, and integration tests for Phase 1 remediations |

---

## 4. Mathematical Formulas and Decision Rules Used

### 4.1 Covariance Matrix Validation
1. **Dimension & Squareness**: $C \in \mathbb{R}^{N 	imes N}$ with $N \ge 2$, matching `asset_ids`.
2. **Numeric Finiteness**: $orall i, j \quad C_{ij} \in \mathbb{R}, \; |C_{ij}| < \infty, \; C_{ij} 
e 	ext{NaN}$.
3. **Symmetry Tolerance**: $\max_{i, j} |C_{ij} - C_{ji}| \le 10^{-4}$. Matrix is symmetrized via $C_{	ext{sym}} = rac{1}{2}(C + C^T)$.
4. **Positive Semi-Definiteness**: All real eigenvalues $\lambda_i(C_{	ext{sym}}) \ge -10^{-7}$. Near-singular matrices ($\lambda_{\min} < 10^{-9}$) receive small ridge regularization $C_{	ext{reg}} = C_{	ext{sym}} + 10^{-8} I_N$.

### 4.2 Kupiec Unconditional Coverage Likelihood Ratio (POF)
Under null hypothesis $H_0: p = 0.05$ (for 95% VaR) with $N$ out-of-sample observations and $x$ tail breaches:
$$	ext{LR} = -2 \ln \left[ rac{(1 - p)^{N-x} p^x}{(1 - \hat{p})^{N-x} \hat{p}^x} ight] \sim \chi^2(1)$$
where $\hat{p} = x / N$.

**Continuous Limits**:
- **Zero Breaches ($x = 0$)**:
  $$\lim_{\hat{p} 	o 0} (1 - \hat{p})^N \hat{p}^0 = 1.0 \implies 	ext{LR} = -2 N \ln(1 - p)$$
- **All Breaches ($x = N$)**:
  $$\lim_{\hat{p} 	o 1} (1 - \hat{p})^0 \hat{p}^N = 1.0 \implies 	ext{LR} = -2 N \ln(p)$$

**Decision Rule ($lpha_{	ext{stat}} = 0.05$, Critical Value $\chi^2_{0.05, 1} = 3.841459$)**:
- If $	ext{LR} < 3.841 \implies$ `ACCEPT` (Unconditional coverage satisfied).
- If $	ext{LR} \ge 3.841$ and $\hat{p} > p \implies$ `REJECT_UNDERESTIMATING_RISK`.
- If $	ext{LR} \ge 3.841$ and $\hat{p} < p \implies$ `REJECT_OVERESTIMATING_RISK`.

**Sample Sufficiency Separation**:
- $\mathbb{E}[x] = N \cdot p < 1.0 \implies$ `INSUFFICIENT_POWER` (Test is inconclusive; cannot reject underestimation).
- $1.0 \le \mathbb{E}[x] < 5.0 \implies$ `LOW_POWER` (Small-sample warning issued; asymptotic $\chi^2$ approximation has elevated Type II error).
- $\mathbb{E}[x] \ge 5.0 \implies$ `SUFFICIENT` (Standard asymptotic test justified).

### 4.3 Quantile Pinball Scoring Rule & Relative Skill
For loss observation $y \in \mathbb{R}$ and nominal VaR quantile forecast $q \in \mathbb{R}$ at level $lpha = 0.95$:
$$S_{0.95}(y, q) = (y - q) \cdot (0.95 - \mathbb{I}(y < q))$$
For test set of $N_{	ext{test}}$ observations:
$$ar{S}_{	ext{model}} = rac{1}{N_{	ext{test}}} \sum_{t=1}^{N_{	ext{test}}} S_{0.95}(y_t, q_{	ext{model}})$$
Baseline: Empirical sample quantile on in-sample training partition $q_{	ext{naive}} = 	ext{Quantile}(y_{	ext{train}}, 0.95)$:
$$ar{S}_{	ext{baseline}} = rac{1}{N_{	ext{test}}} \sum_{t=1}^{N_{	ext{test}}} S_{0.95}(y_t, q_{	ext{naive}})$$
$$	ext{Skill}_{	ext{pct}} = \left(1.0 - rac{ar{S}_{	ext{model}}}{ar{S}_{	ext{baseline}}}ight) 	imes 100$$
- $	ext{Skill}_{	ext{pct}} > 0 \implies$ `OUTPERFORMING` / `SKILLFUL` (Lower quantile loss than baseline).
- $	ext{Skill}_{	ext{pct}} < 0 \implies$ `UNDERPERFORMING` / `UNSKILLFUL` (Higher quantile loss; negative sign preserved).

---

## 5. Tests Added and Exact Test Results

A dedicated test module `backend/tests/test_phase1_quantitative_integrity.py` was implemented containing 30 rigorous test cases.

### Exact Test Suite Results
```text
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_missing_covariance_and_insufficient_history_returns_422 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_valid_empirical_returns_matrix_returns_200_and_user_uploaded_provenance PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_valid_explicit_covariance_matrix_returns_200 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_dimension_mismatch_and_ordering_returns_422 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_non_square_matrix_returns_422 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_non_finite_entries_returns_422 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_asymmetric_matrix_returns_422 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_non_psd_matrix_returns_422 PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_explicit_synthetic_demo_mode_labeled_accurately PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestAllocationCovarianceIntegrity::test_validate_covariance_matrix_helper_directly PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[100-0-0.05-10.2587-False] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[100-5-0.05-0.0-True] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[100-10-0.05-4.1308-False] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[100-100-0.05-599.1465-False] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[4-0-0.05-0.4103-True] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[252-0-0.05-25.8518-False] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[252-12-0.05-0.0305-True] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_analytical_references[252-25-0.05-10.1126-False] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_small_sample_sufficiency_warning PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_invalid_boundary_inputs[0-0-0.05] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_invalid_boundary_inputs[-10-0-0.05] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_invalid_boundary_inputs[100--1-0.05] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_invalid_boundary_inputs[100-105-0.05] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_invalid_boundary_inputs[100-5-0.0] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_kupiec_invalid_boundary_inputs[100-5-1.0] PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestKupiecPOFStatisticalCorrectness::test_model_validation_endpoint_integrates_kupiec PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestQuantileScoringAndHonestPresentation::test_pinball_loss_exact_mathematics PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestQuantileScoringAndHonestPresentation::test_relative_skill_positive_when_model_outperforms PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestQuantileScoringAndHonestPresentation::test_relative_skill_negative_when_model_underperforms PASSED
backend/tests/test_phase1_quantitative_integrity.py::TestQuantileScoringAndHonestPresentation::test_model_validation_endpoint_returns_pinball_scoring PASSED

======================== 30 passed in 0.72s =========================
```

### Full Repository Regression Verification
- **Full Backend Pytest Suite**: `878 passed, 0 failed, 28 skipped` (Postgres live RLS fixtures skipped offline) in 8.86s.
- **Frontend TypeScript Typecheck**: `tsc --noEmit` exited with code 0 (0 errors).
- **Frontend Production Build**: `vite build` completed in 2.46s (0 errors).

---

## 6. API Compatibility & Schema Changes

To prevent regressions across existing frontend views and external callers, all schema enhancements are strictly additive and backward-compatible:

1. **`POST /api/allocation/optimize`**:
   - `success: bool`, `weights: Dict[str, float]`, and `diagnostics` retained.
   - `data_provenance: dict` is now populated on all responses (both 200 OK and 422 Unprocessable Entity).
   - `is_synthetic: bool` explicitly flags whether synthetic covariance proxy was used.
   - HTTP 422 returned on missing empirical observations or invalid covariance with structured detail.
2. **`POST /api/models/validate`**:
   - `test_metrics` retains `kupiec_lr_statistic`, `kupiec_p_value`, `kupiec_test_passed`.
   - Added `sample_sufficiency`: `"INSUFFICIENT_POWER" | "LOW_POWER" | "SUFFICIENT"`.
   - Added `sample_size_warning: bool`.
   - Added `clopper_pearson_ci: [lower, upper]`.
   - Added `scoring_rule: "pinball_loss_quantile_0.95"`, `model_pinball_loss`, `naive_baseline_pinball_loss`.
   - `benchmarks` retains `naive_persistence_rmse` and `naive_persistence_mae` for backward compatibility, while adding `naive_persistence_pinball`, `relative_skill_pct` (pinball reduction), and `skill_verdict`.

---

## 7. Remaining Limitations and Unresolved Issues

1. **Independence Testing (Christoffersen CC)**: Kupiec POF tests unconditional coverage only. While `calculate_christoffersen_test` is implemented in `risk_model_validation.py`, full end-to-end conditional coverage reporting in Lab 7 is planned for a subsequent phase.
2. **Phase 2 & Phase 3 Out-of-Scope Items Preserved**: SQLite / PostgreSQL persistence for multi-tenant runs was not implemented in this phase, and legacy frontend views were preserved without deletion, in strict compliance with prompt constraints.

---

## 8. Final Git Status & Changed File Summary

```text
Branch: main
HEAD Commit: 74ef3fe docs(phase-9): record final commit hash in completion report

Modified Files:
- backend/app.py (covariance validation, Kupiec integration, pinball quantile skill)
- backend/fragility_engine/risk_model_validation.py (continuous limits, sufficiency power, boundary validation)
- frontend/src/components/pages/ModelValidationLab.tsx (honest status badges, sign rendering, small-sample warnings)
- backend/tests/test_phase1_quantitative_integrity.py (30 new quantitative regression tests)
- docs/audit/FRAGILITYSHIELD_PHASE1_REMEDIATION_REPORT.md (remediation report deliverable)

Preserved Untracked / Pre-existing Files:
- All pre-existing user modifications and untracked files remain intact.
```
