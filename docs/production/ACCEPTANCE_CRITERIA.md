# FragilityShield — Production Acceptance Criteria (Phase 1)

**Date:** 2026-10-25  
**Auditing Authority:** Independent Model Validation & Senior Engineering Team  
**Scope:** Measurable, evidence-backed criteria required for release certification.

---

## 1. Quantitative Correctness Criteria

| Criterion ID | Requirement | Mathematical Standard | Pass Threshold | Verification Method |
|---|---|---|---|---|
| `AC-MATH-01` | Historical Value-at-Risk | $VaR_\alpha = -Q_{1-\alpha}(R)$, loss sign convention | Exact match with NumPy linear quantile within $10^{-10}$ | Closed-form reference cases in `test_risk_engine.py` |
| `AC-MATH-02` | Expected Shortfall | Coherent tail loss conditional expectation (Acerbi & Tasche 2002) | $ES_\alpha \ge VaR_\alpha$ strictly; fractional weighting on boundary ties | Independent numerical oracle in `test_risk_engine.py` |
| `AC-MATH-03` | Euler Risk Attribution | Homogeneous first-degree decomposition: $\sum CVaR_i = TotalVaR$ | Reconciliation error $|\sum CVaR_i - TotalVaR| < 10^{-10}$ | Finite difference numerical gradient oracle in `test_attribution.py` |
| `AC-MATH-04` | Out-of-Sample Backtesting | Unconditional Coverage (Kupiec) & Independence (Christoffersen) | Likelihood ratio statistics follow asymptotic $\chi^2_1$ distribution | Benchmarked walk-forward runs in `test_forecast_backtest.py` |
| `AC-MATH-05` | Minimum Variance QP | Constrained quadratic optimization: $\min_w w^T \Sigma w \text{ s.t. } \sum w_i = 1, w_i \ge 0$ | Matches analytical 2-asset closed-form solution within $10^{-5}$ | SciPy SLSQP benchmark in `test_allocation_lab.py` |
| `AC-MATH-06` | Chronological ML Split | Zero forward data leakage: $\max(\text{train}) < \min(\text{test})$ | Shuffling strictly disabled; zero overlap between train and test | Verification in `test_ml_evaluation.py` |

---

## 2. Real-Data and Provenance Criteria

| Criterion ID | Requirement | Standard | Pass Threshold | Verification Method |
|---|---|---|---|---|
| `AC-DATA-01` | Live Upstox Telemetry | Ingest genuine daily candles and quote snapshots from Upstox V3 | Active connection (`HTTP 200`), valid bar physics, IST timezone | Live probe in `test_upstox_adapter.py` |
| `AC-DATA-02` | Anti-Spoofing Provenance | Client assertions of `data_source_mode="REAL_DATA"` are ignored | Provenance assigned strictly by verified backend source resolver | Security tests in `test_real_data_policy.py` |
| `AC-DATA-03` | Zero Silent Fallbacks | Missing data or provider errors produce explicit structured errors | HTTP 400/401/502 with diagnostic message; no fake results | Negative test cases in `test_real_data_policy.py` |
| `AC-DATA-04` | Mixed Simulation Tagging | Monte Carlo paths and bootstrap resamples explicitly tagged | `data_source_mode: "MIXED_DATA"`, `freshness_status: "SIMULATED"` | Output verification in `test_simulation_uncertainty.py` |

---

## 3. Security and Containment Criteria

| Criterion ID | Requirement | Standard | Pass Threshold | Verification Method |
|---|---|---|---|---|
| `AC-SEC-01` | Secret Redaction | Access tokens masked in memory and REST responses | Raw tokens never emitted in JSON responses or logs | `test_upstox_adapter.py::test_config_masks_sensitive_tokens` |
| `AC-SEC-02` | Git Secret Hygiene | `.env` file excluded from version control | Zero commits or tracked records containing `.env` | `git ls-files .env` returns empty |
| `AC-SEC-03` | Read-Only Broker Containment | Zero order placement or trading endpoints in codebase | Code contains only market data and quote query routines | Static audit of `backend/fragility_engine/upstox.py` |
| `AC-SEC-04` | Plugin Host Execution Gate | Untrusted third-party code blocked from running in host process | Raises `PermissionError` when untrusted plugin executed | Verification in `test_custom_model_builder.py` |

---

## 4. Operational and Stability Criteria

| Criterion ID | Requirement | Standard | Pass Threshold | Verification Method |
|---|---|---|---|---|
| `AC-OPS-01` | Test Suite Reliability | 100% of automated tests pass cleanly | 0 failures, 0 collection errors across all 585 tests | `pytest` full suite execution |
| `AC-OPS-02` | Resource Limits Enforcement | Oversized inputs rejected safely without memory exhaustion | Returns HTTP 400 on $N > 10,000$ or simulation paths $> 2,000$ | Input bounds checks in `simulation.py` and `risk.py` |
| `AC-OPS-03` | Non-Finite Number Sanitization | Inputs containing `NaN`, `Inf`, or `-Inf` rejected at ingestion | Raises `ValueError` with clear index location | Input validation checks in `risk.py` and `data_diagnostics.py` |
