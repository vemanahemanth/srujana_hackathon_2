# FragilityShield — Phase 8.1: Issue Review Report
## Benchmark Integrity, Risk Calibration, Statistical Correctness & Inherited Defect Resolution

**Date:** 2026-10-24  
**Auditor / Reviewer:** Combined Senior Quantitative Risk Researcher, Model Validation Specialist, Principal Python Engineer, and Reliability Engineer  
**Baseline Starting Commit:** `98ffd89db117eea26bdf18cce726341888bcd329`  
**Referenced Deliverables:** `backend/fragility_engine/plugins.py`, `backend/fragility_engine/benchmarks.py`, `backend/tests/test_plugin_benchmarking.py`, `backend/tests/test_statistical_calibration.py`

---

## 1. Executive Summary & Audit Mandate

Phase 8.1 conducted a comprehensive mathematical and software engineering audit of the FragilityShield plugin system and model benchmarking laboratory introduced in Phase 8. 

The primary objective was to ensure that **model rankings, statistical metrics, perturbation analyses, and reproducibility fingerprints are mathematically sound, defensible, and free from misleading claims of model superiority**.

### Core Principle Enforced
> **A lower estimated Value-at-Risk or Volatility reflects a lower risk estimate on sample data, NOT a superior, more robust, or better-calibrated risk model.** Evaluating predictive model quality requires out-of-sample backtesting against realized outcomes under formal statistical loss functions.

---

## 2. Confirmed Defects & Resolutions

| Issue ID | Affected Component | Severity | Root Cause | Fix / Resolution | Regression Test | Verification Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ISSUE-8.1-01** | `benchmarks.py` (`ModelRankingEntry`, `BenchmarkReport`) | **High** | Comparative ranking sorted models by `var_95` with `ranking_direction="lower_is_better"` without qualifying that lower VaR merely means a lower risk estimate on historical data, presenting Rank 1 ambiguously as the "best" model. | Decoupled risk magnitude from model quality. Added `unit` and `interpretation` (`"lower_estimated_risk"`) to `ModelRankingEntry`. Added `ranking_metric`, `ranking_direction`, `ranking_interpretation`, and prominent `ranking_disclaimer` to `BenchmarkReport` and all export formats (JSON, Markdown, CSV). | `test_statistical_calibration.py::TestBenchmarkRankingSemanticsAndDisclaimers` | **Verified (Passed)** |
| **ISSUE-8.1-02** | `plugins.py` (`ParametricGaussianPlugin`, `EWMAVolatilityPlugin`) | **Medium** | Both plugins exported `"var_historical": var_95`, incorrectly labelling a parametric Gaussian formula as a non-parametric empirical historical simulation metric. | Removed `"var_historical"` alias from both parametric Gaussian and EWMA models. Both continue to export standard `"var_95"` and `"var_99"`. Non-parametric historical simulation is exclusively reported by `HistoricalSimulationPlugin`. | `test_statistical_calibration.py::TestParametricGaussianAnalyticalFormulas` | **Verified (Passed)** |
| **ISSUE-8.1-03** | `plugins.py` (`EWMAVolatilityPlugin`) | **Medium** | `EWMAVolatilityPlugin` derived VaR and ES using Gaussian quantiles without declaring its conditional normal distribution assumption in its name or metadata limitations. | Renamed plugin to `"RiskMetrics EWMA Volatility & Conditional Gaussian Model"`. Documented conditional normal distribution assumptions, zero-excess-kurtosis limits, and exponential decay memory in limitations. Added optional `zero_mean` config flag for RiskMetrics 1996 standard. | `test_statistical_calibration.py::TestEWMAVolatilityAnalyticalRecurrence` | **Verified (Passed)** |
| **ISSUE-8.1-04** | `benchmarks.py` (`BenchmarkSpecification.__post_init__`) | **Medium** | Perturbation specifications were validated only lazily during execution, allowing invalid configs (negative friction, lookback < 2, decay outside (0, 1)) to pass specification validation. | Added up-front validation in `BenchmarkSpecification.__post_init__` verifying supported perturbation types and enforcing `friction_bps >= 0.0`, `lookback_window >= 2`, and `decay_factor \in (0, 1)`. | `test_statistical_calibration.py::TestPerturbationParameterValidation` | **Verified (Passed)** |
| **ISSUE-8.1-05** | `benchmarks.py` (`execute_model_benchmark`) | **Medium** | `output_fingerprint` previously hashed only baseline metrics and status, leaving perturbation metrics, perturbation deltas, and rankings unhashed. | Expanded `manifest_results` to hash `baseline_metrics`, `perturbation_metrics`, `perturbation_deltas`, and `rankings` using canonical serialization. Any perturbation drift or ranking shift changes `output_fingerprint`. | `test_plugin_benchmarking.py::TestDeterministicModelBenchmarking` | **Verified (Passed)** |
| **ISSUE-8.1-06** | `benchmarks.py` (`BenchmarkSpecification.__post_init__`) | **Low** | Default `target_ranking_metric="var_95"` caused unexpected validation errors when callers provided custom `metrics_to_compare` without `var_95`. | Gracefully set `target_ranking_metric = None` (unranked report) when caller supplies custom metrics not containing `var_95` and did not explicitly override `target_ranking_metric`. Explicit non-matching overrides continue to raise a descriptive `ValueError`. | `test_plugin_benchmarking.py::test_benchmark_with_ewma_perturbation` | **Verified (Passed)** |

---

## 3. Mathematical Conventions Verified

1. **Loss vs Return Convention:**
   - Losses defined as $L_t = -R_t$.
   - A positive Value-at-Risk ($\text{VaR}_\alpha > 0$) denotes a potential loss threshold at confidence $\alpha$.
   - A higher estimated VaR denotes higher potential loss; hence risk magnitude ranking uses `lower_is_better` to sort by `lower_estimated_risk`.

2. **Parametric Gaussian Closed-Form:**
   - Under Gaussian return assumptions $R \sim \mathcal{N}(\mu, \sigma^2)$:
     $$\text{VaR}_\alpha(L) = -\mu + z_\alpha \sigma$$
     $$\text{ES}_\alpha(L) = -\mu + \sigma \frac{\phi(z_\alpha)}{1 - \alpha}$$
   - Verified against exact analytical formulas with zero volatility degenerate cases ($\sigma = 0 \implies \text{VaR} = -\mu$).

3. **RiskMetrics EWMA Volatility Recurrence:**
   - Evaluated step-by-step:
     $$\sigma_t^2 = \lambda \sigma_{t-1}^2 + (1 - \lambda) r_t^2$$
     with uncentered initialization $\sigma_0^2 = \frac{1}{N}\sum_{i=1}^N r_i^2$ and annualization factor $A = 252.0$.
   - Conditional Gaussian VaR and ES derived explicitly using conditional standard deviation $\sigma_T$.

4. **Long-Only Portfolio Concentration (HHI):**
   - For asset weights $w_i \ge 0, \sum w_i = 1$:
     $$\text{HHI} = \sum_{i=1}^N w_i^2 \in [1/N, 1.0]$$
   - Points scaling: $\text{HHI}_{\text{points}} = \text{HHI}_{\text{decimal}} \times 10{,}000$.

---

## 4. Test Suite & Coverage Impact

- **Baseline Test Suite:** 323 passed tests.
- **Phase 8.1 Test Suite:** 339 passed tests (+16 new quantitative and statistical calibration tests).
- **Statement Coverage:** 93.78% (2200 / 2346 statements).
- **Branch Coverage:** 86.96% (807 / 928 branches).
- **Combined Coverage:** 91.84% (3007 / 3274 elements).
- **Test Execution Time:** 0.62 seconds (100% deterministic, zero flakiness).
