# FragilityShield — Phase 6: Validation and Reproducibility Lab Report

**Date:** 2026-10-24  
**Role:** Principal Software Architect, Quantitative Risk Engineer & Test Engineer  
**Status:** Complete & Independently Verified  
**Baseline Git Commit:** `cd78d7e`  
**Execution Environment:** macOS Darwin (arm64), Python 3.14.6, NumPy 2.2.3, pytest 9.0.3, pytest-cov 7.1.0, coverage 7.17.0  

---

## 1. Executive Summary

Phase 6 implements the **Validation and Reproducibility Lab** for FragilityShield. This engine extension answers the fundamental quantitative questions:
1. *What exact data and configuration produced this risk result?*
2. *Has the input data changed?*
3. *Was the exact same model configuration and algorithm version evaluated?*
4. *Does re-running the experiment produce bitwise-equivalent results?*
5. *Can an independent reviewer verify mathematical coherence without circular code execution?*
6. *When results diverge, is the difference caused by data drift, configuration drift, environment divergence, or numerical tolerance?*

All capabilities are pure Python and framework-independent. The full regression suite comprises **250 automated tests** passing in **0.42 seconds** with **93.8% statement coverage** (1301 statements, 81 missed) and **87.3% branch coverage** (512 branches, 65 missed), yielding an overall combined coverage of **92%**.

---

## 2. Phase 5 Verification Summary (Stage A)

Prior to implementing Phase 6, Stage A conducted an independent audit of Phase 5:
- **Baseline Git State:** Commit `cd78d7e` (`feat(fragility): implement Phase 5 Fragility Lab engine and tests`) verified on branch `main`. Working tree clean.
- **Starting Regression Suite:** 212 tests passed in 0.29s.
- **Starting Statement Coverage:** 94.2% statement coverage, 88.3% branch coverage.
- **Mathematical Integrity:** Re-verified discrete Acerbi & Tasche Expected Shortfall ($ES \ge VaR$), drawdown recovery dynamics, and exact portfolio concentration metrics:
  - Asset HHI: $0.11060000$ (1106.0 points).
  - Sector HHI: $0.19500000$ (1950.0 points).
- Documented in `docs/phase-5-verification-report.md`.

---

## 3. Phase 6 Architecture & Implementation (Stage B)

The Validation & Reproducibility Lab introduces `backend/fragility_engine/reproducibility.py` and exported contracts in `backend/fragility_engine/__init__.py`:

```
backend/fragility_engine/
├── __init__.py               # Public API exports (Phase 1–6)
├── concentration.py          # Portfolio allocation & HHI
├── fragility.py              # Fragility Lab perturbations (Phase 5)
├── models.py                 # Domain models (Holding, Portfolio, MetricResult)
├── portfolio_loader.py       # JSON/CSV loaders & exporters
├── reproducibility.py        # Validation & Reproducibility Lab Engine (Phase 6)
├── returns.py                # Return series calculations
├── risk.py                   # VaR, Expected Shortfall, Volatility, Drawdown
└── scenarios.py              # Macro & sector scenario shocks (Phase 4)
```

### Core Components

1. **Deterministic Canonical Serialization (`canonical_json_dumps`)**:
   - Serializes dicts with alphabetically sorted keys.
   - Normalizes lists, numpy arrays, sets, and frozen objects.
   - Strictly rejects non-finite floats (`NaN`, `+Inf`, `-Inf`) with `ValueError`.
   - Compact representation eliminating whitespace variance across platforms.

2. **Cryptographic Fingerprinting (`compute_canonical_hash`, `compute_dataset_hash`)**:
   - SHA-256 hash generation for datasets, configurations, and result sets.
   - Preserves chronological sequence in time-series arrays ($r_1, r_2, \dots, r_T$).
   - Computes deterministic asset-ordered hash for `Portfolio` structures.

3. **Experiment Specification (`ExperimentSpecification`)**:
   - Typed, immutable domain model specifying `experiment_id`, `name`, `dataset_id`, `baseline_config`, `perturbation_specs`, `schema_version`, `algorithm_version`, `random_seed`, and `date_range`.
   - Strictly isolates mathematical configuration parameters from informational metadata (`created_at`, `description`, `metadata`, `dataset_provenance`) so timestamps do not corrupt calculation fingerprints.

4. **Reproducible Experiment Runner (`run_reproducible_experiment`)**:
   - Orchestrates dataset validation, baseline risk calculations, perturbation executions, invariant validations, and manifest compilation.
   - Supports 1D return series, 2D multivariate return matrices, and `Portfolio` snapshots.
   - Formally maps and validates supported perturbation types: `lookback_window`, `volatility_estimator_ewma`, `return_friction`, `tail_confidence_level`, `correlation_stress`, and `portfolio_liquidation_shock`.

5. **Reproducibility Manifest (`ReproducibilityManifest`)**:
   - Captures `input_fingerprint`, `configuration_fingerprint`, and `output_fingerprint`.
   - Records runtime platform metadata: Python version, NumPy version, OS platform, machine architecture, and engine version.
   - Summarizes validation status, check counts, warnings, and methodology boundaries.

6. **Independent Invariant Verification (`verify_experiment_invariants`)**:
   - Non-circular mathematical validation:
     - Portfolio weights sum to $1.0 \pm 10^{-5}$.
     - Asset HHI scale consistency ($H_{\text{points}} = 10000 \times H_{\text{decimal}}$).
     - Coherence invariant: $\text{ES}_\alpha \ge \text{VaR}_\alpha - 10^{-9}$.
     - Maximum drawdown bounded within $[0.0, 1.0]$.
     - All baseline and perturbed metrics are strictly finite floats.

7. **Drift Detection & Run Comparison (`compare_experiment_runs`)**:
   - Compares two `ReproducibilityRunResult` objects.
   - Detects and categorizes:
     - `input_drift_detected`: Raw input dataset hash modified.
     - `config_drift_detected`: Experiment configuration hash modified.
     - `environment_drift_detected`: Python, NumPy, or OS platform modified.
     - `tolerance_exceeded`: Metrics diverge beyond configured tolerance $\epsilon$ (default $10^{-6}$).
   - Produces structured `DriftReport` with itemized metric differences.

---

## 4. Verification Evidence & Test Execution

### 4.1. Automated Test Suite Execution
Command:
```bash
.venv/bin/python -m pytest backend/tests/ -v
```

Output:
```
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/vemanahemanthbabu/srujana_hackathon_2/backend
configfile: pyproject.toml
plugins: cov-7.1.0, anyio-4.12.1, Faker-40.37.0, asyncio-1.4.0
collected 250 items

backend/tests/test_engine_foundation.py ................................ [ 12%]
....................                                                     [ 20%]
backend/tests/test_fragility_lab.py ................................     [ 33%]
backend/tests/test_portfolio_lab.py .............................        [ 45%]
backend/tests/test_reproducibility_lab.py .............................. [ 57%]
........                                                                 [ 60%]
backend/tests/test_risk_engine.py ...................................... [ 75%]
backend/tests/test_scenario_engine.py ..............................     [ 87%]
backend/tests/test_validation_edge_cases.py ............................ [ 98%]
...                                                                      [100%]

============================= 250 passed in 0.42s ==============================
```

### 4.2. Code Coverage Evidence
Command:
```bash
.venv/bin/python -m pytest backend/tests/ --cov=fragility_engine --cov-report=term-missing --cov-branch
```

Output:
```
Name                                           Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------
backend/fragility_engine/__init__.py              10      0      0      0   100%
backend/fragility_engine/concentration.py         60      3     22      3    93%   135, 159, 163
backend/fragility_engine/fragility.py            239      5     76      7    96%   184->183, 210->212, 327, 425, 545, 757-758, 765->769
backend/fragility_engine/models.py               111      4     38      4    95%   107, 110, 123, 139
backend/fragility_engine/portfolio_loader.py     161     23     86     16    83%   45, 48-51, 67, 85, 89, 94-95, 98, 102-103, 106, 113->123, 121, 124->129, 127, 142, 185, 188-191, 213, 319-320
backend/fragility_engine/reproducibility.py      365     27    162     24    90%   80, 82-85, 167, 169, 227, 229, 231, 244-245, 280, 281->284, 303, 304->307, 487, 498, 506, 538-539, 617, 622, 626, 634, 669->674, 739->741, 773, 778, 857, 938
backend/fragility_engine/returns.py               29      0     12      0   100%
backend/fragility_engine/risk.py                 173     14     56      6    91%   121, 125-126, 137-138, 156, 160-161, 169, 172-173, 465, 474-475, 476->479
backend/fragility_engine/scenarios.py            153      5     60      5    95%   74, 244, 291, 395, 402
------------------------------------------------------------------------------------------
TOTAL                                           1301     81    512     65    92%
============================= 250 passed in 0.42s ==============================
```

- **Statement Coverage:** 93.8% (1220/1301 statements executed).
- **Branch Coverage:** 87.3% (447/512 branches executed).
- **Total Combined Coverage:** 92%.
- **Reproducibility Test Coverage:** `reproducibility.py` achieved 90% combined coverage.

---

## 5. End-to-End Demonstration: Fingerprints & Drift Outcomes

### 5.1. Repeated Run Bitwise Equivalence
- **Experiment:** `EXP-REPRO-001` evaluated on 60-day synthetic return series ($T = 60$).
- **Run 1 Input Hash:** `593710777fa6dd5e6adce539553b6fae7e600a9446d790e6616086f685600c01`
- **Run 2 Input Hash:** `593710777fa6dd5e6adce539553b6fae7e600a9446d790e6616086f685600c01`
- **Run 1 Config Hash:** `63ba4e6b1d9bfdc630be82eb6b95b85ef571fe4379ba921eefcbe8a8c17dc15b`
- **Run 2 Config Hash:** `63ba4e6b1d9bfdc630be82eb6b95b85ef571fe4379ba921eefcbe8a8c17dc15b`
- **Run 1 Output Hash:** `e7e596bb0e71957c5bfeb7b8b29d4791a82f3ef80f1d7d58fa6c5c707ca1889c`
- **Run 2 Output Hash:** `e7e596bb0e71957c5bfeb7b8b29d4791a82f3ef80f1d7d58fa6c5c707ca1889c`
- **Drift Comparison:**
  - `runs_identical`: `True`
  - `input_drift_detected`: `False`
  - `config_drift_detected`: `False`
  - `summary`: `"Runs are identical and cryptographically verified. No drift detected."`

### 5.2. Input Data Drift Detection
- **Mutation:** Modified a single return observation by $+50\text{ bps}$ ($r_0' = r_0 + 0.005$).
- **Original Input Hash:** `593710777fa6dd5e6adce539553b6fae7e600a9446d790e6616086f685600c01`
- **Altered Input Hash:** `df2bb978d38e234c0aa0664c3c396dc7d4a23b3f2c5be0e9b6058e5d3fc351f0`
- **Drift Outcome:**
  - `runs_identical`: `False`
  - `input_drift_detected`: `True`
  - `config_drift_detected`: `False`
  - `summary`: `"Drift detected: Input data changed (different input fingerprint)."`

### 5.3. Configuration Drift Detection
- **Mutation:** Modified annualization factor from $252$ to $260$.
- **Original Config Hash:** `63ba4e6b1d9bfdc630be82eb6b95b85ef571fe4379ba921eefcbe8a8c17dc15b`
- **Altered Config Hash:** `b57fa0c7c88b0a531e217be54fb18ec06e12eec874108ce410e3fc6ce2882aa2`
- **Drift Outcome:**
  - `runs_identical`: `False`
  - `input_drift_detected`: `False`
  - `config_drift_detected`: `True`
  - `summary`: `"Drift detected: Experiment configuration changed (different configuration fingerprint)."`

### 5.4. Environment Drift Detection
- **Mutation:** Executed run on simulated Linux x86_64 runtime environment vs macOS arm64 baseline.
- **Drift Outcome:**
  - `environment_drift_detected`: `True`
  - `summary`: `"Drift detected: Runtime environment changed (different Python/NumPy/OS platform)."`

---

## 6. Known Reproducibility Boundaries & Limitations

1. **Floating-Point Determinism Across Architectures**:
   - IEEE 754 ensures consistent arithmetic on the same CPU architecture and compiled NumPy binary.
   - However, differences in FMA (fused multiply-add) instructions between ARM64 and x86_64, or differing BLAS/LAPACK implementations (Apple Accelerate vs OpenBLAS vs Intel MKL) can cause differences at the $\approx 10^{-15}$ level.
   - The engine provides configurable tolerance $\epsilon$ (default $10^{-6}$) to classify numerical equivalence vs actual algorithm drift.
2. **Missing Input Data**:
   - If historical time-series data or underlying asset returns are lost, cryptographic hashes can prove the data changed or is missing, but cannot recreate the missing observations.
3. **Multivariate Returns Synchronization**:
   - Multivariate correlation stress requires synchronized return matrices across all constituent assets. A static portfolio without time-series histories cannot compute correlation shifts.

---

## 7. Git Verification & Working Tree Status

- **Status:** All Phase 6 files created, tested, and validated.
- **Changed Files:**
  - `backend/fragility_engine/__init__.py` (updated with Phase 6 exports)
  - `backend/fragility_engine/reproducibility.py` (new Phase 6 engine)
  - `backend/tests/test_reproducibility_lab.py` (38 new automated tests)
  - `docs/phase-5-verification-report.md` (Stage A verification report)
  - `docs/phase-6-issue-review.md` (Phase 6 review and status matrix)
  - `docs/phase-6-report.md` (this comprehensive report)
  - `README.md` (updated documentation for Phase 6)
- **Secrets & Artifacts:** No API keys, credentials, or transient scratch files committed.
