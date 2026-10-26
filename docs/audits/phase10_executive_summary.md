# FragilityShield — Phase 10 Independent Verification & Forensic Audit: Executive Summary

**Audit Date:** October 25, 2026  
**Auditor:** Independent Senior Software Auditor, Quantitative Validation Lead & Application Security Reviewer  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Authoritative Specifications:** `FragilityShield_1.docx` and Complete Lab-by-Lab Product Specification  

---

## 1. Overall Audit Verdict

> **VERDICT: FUNCTIONAL SCIENTIFIC TESTING CORE WITH SPECIFIED BOUNDARIES**  
> The backend of FragilityShield is a **genuinely functional, mathematically rigorous, and unified quantitative testing engine**. The advertised 13 scientific testing laboratories are implemented and interconnected through a shared calculation core (`backend/fragility_engine/`).  
> Across 27 test files, all **473 collected unit, integration, and end-to-end acceptance tests execute and pass** with zero failures.  
> 
> However, forensic inspection revealed two material architectural nuances that must be clearly stated:
> 1. **Security Isolation:** While the model capability system correctly flags `code_isolation_required: True`, custom Python plugins currently execute **in-process**. Exception containment protects against runtime crashes, but true sandboxed OS isolation is not yet implemented.
> 2. **Euler Risk Attribution:** The identity $\sum \text{CVaR}_i = \text{VaR}_p$ is proven algebraically, but represents the **linear Gaussian covariance beta approximation** rather than exact non-parametric historical quantile derivatives.

---

## 2. Test Execution & Environment Baseline

| Environment Property | Observed Value |
| :--- | :--- |
| **Operating System** | macOS Darwin 24.x |
| **Python Version** | Python 3.14.6 |
| **Test Runner** | pytest 9.0.3, pluggy 1.6.0 |
| **Core Scientific Libraries** | NumPy 2.x, SciPy 1.18.0, Starlette 1.3.1, Uvicorn 0.40.0 |
| **Execution Command** | `.venv/bin/python -m pytest backend/tests/ -v` |
| **Test Inventory Collected** | **473 test cases across 27 test files** |
| **Execution Outcome** | **473 Passed, 0 Failed, 0 Skipped, 1 Warning** (`StarletteDeprecationWarning` regarding httpx testclient) |
| **Execution Time** | 1.04 seconds |
| **Statement Coverage** | **88% overall statement coverage** (4,932 / 5,602 statements executed) across `fragility_engine/` |

### Reconciliation of Test Inventory Claims
A prior summary report claimed: *"446 tests across 24 test suites"*, and later *"473 tests across 28 suites"* listing a phantom file `test_portfolio_concentration.py (12 tests)`.
Forensic audit resolved this discrepancy:
- Exactly **27 test files** exist in `backend/tests/test_*.py`.
- No file named `test_portfolio_concentration.py` exists; portfolio concentration tests are located inside `test_portfolio_lab.py`, `test_statistical_calibration.py`, and `test_validation_edge_cases.py`.
- The total collected test count is **exactly 473 tests**, all of which were executed and verified by this audit.

---

## 3. Laboratory-by-Laboratory Verification Status

All 13 laboratories defined in the product specification were audited:

| Lab Workspace | Scope & Advertised Function | Audit Status | Key Evidence |
| :---: | :--- | :---: | :--- |
| **Lab 1: Data Lab** | Tabular schema audits, OHLCV candle validation, outlier detection, 2-sample KS drift testing, sample contamination screening. | **VERIFIED** | `test_data_diagnostics.py`, `test_new_api_and_cli.py::test_api_data_validation_endpoints`. |
| **Lab 2: Model Lab** | Model manifest contract, capability audit matrix (`Compatible`, `Validated`, `Supported`, `Not applicable`, `Unsupported`, `Required`), integration smoke/shape/determinism/timeout test suite. | **VERIFIED** (Contract) / **PARTIALLY VERIFIED** (Sandbox) | `test_project_and_model_registry.py`, `test_model_integration_lab.py`. Flagging is verified; in-process execution is noted. |
| **Lab 3: Portfolio Lab** | Multi-asset holding representation, CSV/JSON loading, market valuations, normalized weights, HHI bounds ($10000/N$ to $10000$), Top-N concentration. | **VERIFIED** | `test_portfolio_lab.py` (29 tests), `test_statistical_calibration.py`. |
| **Lab 4: Risk Lab** | Positive loss VaR ($L = -R$), coherent Expected Shortfall ($ES \ge VaR$), parametric Gaussian, EWMA recurrence, drawdown duration, Sharpe, Sortino, Calmar, beta, capture ratios. | **VERIFIED** | `test_risk_engine.py` (38 tests), `test_statistical_calibration.py`. |
| **Lab 5: Scenario Lab** | Multi-asset/sector shocks, exact P&L identity ($\Delta V = \sum V_i s_i$), correlation stress with eigenvalue projection ($\max(\lambda, 10^{-9})$), reverse stress testing. | **VERIFIED** | `test_scenario_engine.py` (30 tests), `test_reverse_stress_and_boundary.py`. |
| **Lab 6: Fragility Lab** | Assumption attack families (lookback, EWMA, friction, winsorization, missing data, regime shift), sensitivity ranking ($\Delta M, \%\Delta M$), stress-boundary root bisection search. | **VERIFIED** | `test_fragility_lab.py` (32 tests), `test_fragility_new_attacks.py`, `test_reverse_stress_and_boundary.py`. |
| **Lab 7: Benchmarking Lab** | Multi-model benchmarking across identical datasets, metric alignment, explicit ranking rules, and statutory disclaimers. | **VERIFIED** | `test_plugin_benchmarking.py` (43 tests), `test_statistical_calibration.py`. |
| **Lab 8: Validation Lab** | Out-of-sample breach testing ($L_{t+1} > VaR_t$), Kupiec POF test ($\chi^2(1)$ exact erfc p-value), Christoffersen independence and combined conditional coverage ($\chi^2(2)$ exact exponential p-value). | **VERIFIED** | `test_forecast_backtest.py` (19 tests). |
| **Lab 9: ML Model Lab** | Zero look-ahead temporal splitting ($\max(T_{\text{train}}) < \min(T_{\text{test}})$), regression/classification metrics, confusion matrix, Gaussian noise injection robustness. | **VERIFIED** | `test_ml_evaluation.py` (5 tests). |
| **Lab 10: Experiment Studio** | First-class entities (`Project`, `DatasetRecord`, `ModelManifest`, `ExperimentEntity`, `TestEntity`, `RunEntity`, `ResultEntity`, `ArtifactEntity`), atomic filesystem catalog, SHA-256 manifests. | **VERIFIED** | `test_experiment_studio.py` (30 tests), `test_project_and_model_registry.py`. |
| **Lab 11: Plugin Lab** | In-memory plugin registry, custom quantitative model adapters (Student-$t$, Laplace, Cornish-Fisher, EWMA), exception containment. | **VERIFIED** | `test_plugin_benchmarking.py`, `test_custom_model_builder.py`. |
| **Lab 12: Reporting Lab** | Multi-format exports (Markdown, JSON, CSV), numerical precision preservation, provenance and limitation disclosures. | **VERIFIED** | `test_experiment_studio.py`, `test_backend_acceptance_workflows.py::test_workflow_8`. |
| **Lab 13: Interfaces** | Unified Starlette REST API (24+ endpoints), Python SDK Client (`fragility_engine.sdk.Client`), and terminal CLI (`fragility_engine.cli`). | **VERIFIED** | `test_application_api.py`, `test_sdk_and_cli.py`, `test_new_api_and_cli.py`, and verified dynamic numerical parity. |

---

## 4. End-to-End Acceptance Workflows Audited

The 5 primary acceptance workflows specified in Phase 10 were directly executed and verified:
1. **Workflow A (Portfolio Risk & Scenarios):** Ingested portfolio of ₹65,000 across TCS and HDFC; verified 95% Historical VaR (2.27%) and Expected Shortfall (2.50%); applied 20% banking shock yielding exact P&L of -₹6,000; executed reverse stress test solving for exact -10.0% market shock to achieve ₹6,500 loss; generated and validated full Markdown/CSV experiment reports.
2. **Workflow B (Model Integration & Rejection):** Registered forecasting model manifest; confirmed capability report correctly flags Portfolio Lab operations as `Not applicable`; executed full 8-check integration test suite with adapter callable.
3. **Workflow C (Risk Forecast Validation):** Evaluated 5-point out-of-sample ex-ante VaR forecast against realized losses; observed 2 breaches; verified Kupiec POF likelihood ratio and Christoffersen first-order Markov transition probabilities.
4. **Workflow D (Fragility & Boundary Search):** Executed stress-boundary bisection search on return friction; successfully converged to break-even friction threshold where annualized Sharpe ratio crosses 0.0.
5. **Workflow E (API / SDK / CLI Parity):** Executed identical 10-observation return series calculation across Python SDK, Starlette REST API, and terminal CLI. Annualized volatility ($0.276098$) and 95% VaR ($0.022750$) matched across all three interfaces to within $10^{-9}$.

---

## 5. Critical Mathematical & Security Findings

### 5.1 Mathematical Finding: Euler Risk Attribution
In `attribution.py`, component risk is computed using covariance betas:
$$\text{CVaR}_i = w_i \beta_i \text{VaR}_p, \quad \text{where } \beta_i = \frac{\text{Cov}(R_i, R_p)}{\text{Var}(R_p)}$$
Because $\sum w_i \beta_i \equiv 1.0$, the Euler sum $\sum \text{CVaR}_i = \text{VaR}_p$ holds algebraically. The audit notes that this is the **Gaussian beta linear approximation (Jorion/Hallerbach)**, which serves as a linear proxy for non-Gaussian empirical return distributions.

### 5.2 Security Finding: In-Process Plugin Execution Model
Plugins registered in `PluginRegistry` execute within the main API runtime process. While `try ... except Exception` catches runtime errors, it does not provide true process isolation. For local single-user research, this is acceptable; for multi-tenant web deployment, an out-of-process worker model is required.

---

## 6. Top Five Remediation Items

1. **Process-Isolated Execution Backend (P1 — High):** Implement an out-of-process runner (subprocess with dropped privileges or containerized worker) for untrusted user model code.
2. **Euler Attribution Methodology Clarification (P2 — Medium):** Update documentation to explicitly state that component risk decomposition uses the linear Gaussian covariance beta formulation.
3. **Documentation Test Inventory Correction (P2 — Medium):** Update repository documentation to accurately report 473 tests across 27 test files (removing references to the phantom 28th suite).
4. **Async Event Loop Offloading (P2 — Medium):** Wrap compute-intensive simulations and multi-attack fragility audits in `anyio.to_thread.run_sync` to prevent blocking the ASGI event loop.
5. **EWMA Variance Initialization Causal Strictness (P3 — Low):** Enforce passing prior variance for out-of-sample evaluation slices to prevent in-sample variance calculation across the evaluation window.

---

## 7. Deliverables & Documentation Index

The complete audit artifacts are preserved in `docs/audits/`:
1. `docs/audits/phase10_executive_summary.md` (This document)
2. `docs/audits/phase10_requirements_evidence_matrix.md` (Detailed 32-requirement traceability matrix)
3. `docs/audits/phase10_mathematical_validation.md` (Formal mathematical derivations and edge-case proofs)
4. `docs/audits/phase10_security_review.md` (Threat surface review and boundary analysis)
5. `docs/audits/phase10_remediation_plan.md` (Prioritized remediation schedule with acceptance tests)

**Frontend Safeguard Compliance:** Files `frontend/index.html`, `frontend/style.css`, and `frontend/app.js` were completely preserved without modification.
