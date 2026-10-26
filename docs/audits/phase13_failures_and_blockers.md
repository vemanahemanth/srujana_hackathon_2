# Phase 13 — Failures, Blockers & Scope Limitations

**Platform:** FragilityShield Quantitative Risk & Model Stress-Testing Laboratory  
**Execution Environment:** macOS (Darwin 24.1.0), Python 3.14.6, Pytest 9.0.3  
**Audit Reference:** Phase 13 Full-Platform Real-User Testing Campaign  
**Date:** 2026-10-25

---

## 1. Executive Summary

During the Phase 13 Full-Platform Testing Campaign, all 13 implemented laboratories, 6 end-to-end user journeys, and individual lab features were exercised against realistic, synthetic, and adversarial scenarios.

This document records the defects discovered, edge-case limitations, mathematical boundary conditions, and architectural boundaries separating the current backend implementation from a multi-tenant enterprise deployment.

---

## 2. Classification of Defects & Corrected Items

### 2.1 Pre-Existing Defects Corrected & Verified in Phase 12/13
Prior to Phase 13, three mathematical and security defects were audited and resolved:
1. **P11-DEF-01 (Machine Epsilon Tail Discontinuity in Expected Shortfall):**
   - *Problem:* In `calculate_expected_shortfall` (`risk.py`), floating-point comparison `(1.0 - alpha) * n` suffered rounding errors when alpha matched machine epsilon thresholds, causing discontinuous jumps in discrete tail weighting.
   - *Resolution:* Added `TOL = 1e-12` margin and fractional interpolation conforming to Acerbi & Tasche (2002).
   - *Status:* Verified in Phase 13 Journey 1 & Lab 2 tests. Coherence $\text{ES} \ge \text{VaR}$ holds across all tests.
2. **P11-DEF-02 (Unbracketed Stress-Boundary False Convergence):**
   - *Problem:* `run_stress_boundary_search` (`fragility.py`) returned boundary values even when the target threshold was outside the search bracket $[a, b]$, reporting false break-even discoveries.
   - *Resolution:* Enforced interval validation ($a < b$, $\text{tol} > 0$), sign-change checking, and translation-invariance rejection. Returns `converged=False, boundary_parameter_value=None` when unbracketed.
   - *Status:* Verified in Phase 13 Journey 2 test (`test_journey_2_fragility_investigation_e2e`).
3. **P11-DEF-03 (Host Security Boundary for Untrusted Plugins):**
   - *Problem:* An untrusted plugin declaring `code_isolation_required=True` could attempt in-process execution on the ASGI host.
   - *Resolution:* Enforced trusted-mode-only execution policy in `PluginRegistry` (`plugins.py`), blocking untrusted plugins with an explicit `PermissionError`.
   - *Status:* Verified in Phase 12 & Phase 13 security test suite.

---

## 3. Discovered Behavioral & Integration Blockers

### 3.1 Strict Sector Validation in Scenario Engine
- **Observed Behavior:** When executing preset scenarios (such as `gfc_2008_replay`), `validate_scenario_against_portfolio` strictly checks that every sector in the scenario definition exists in the target portfolio. If a scenario contains a shock for `"Banking"`, but the portfolio holdings label their financial sector as `"Financial Services"`, the engine raises `ValueError: Unknown sector in scenario: 'Banking'`.
- **Root Cause:** By design, Rule 3 in `validate_scenario_against_portfolio` prevents silent shock omission or silent sector mapping.
- **Impact on Real Users:** Users importing third-party portfolios or using standard presets must explicitly map their sector taxonomy to match the scenario's sectors, or construct custom `ScenarioDefinition` instances with portfolio-aligned sectors.
- **Severity:** Medium (Operational / Usability). Does not affect mathematical correctness.

### 3.2 Parameter Baseline Requirement in Experiment Studio
- **Observed Behavior:** In `StudioExperimentDefinition`, specifying `baseline_config={"confidence_level": 0.95}` without `"annualization_factor"` raises `ValueError: baseline_config missing required keys: 'annualization_factor'`.
- **Root Cause:** In `fragility_engine/reproducibility.py` line 241, reproducibility validation mandates that when confidence level is set, annualization factor must be explicitly declared to prevent hidden configuration defaults.
- **Impact on Real Users:** Users cannot omit standard annualization conventions (e.g. 252 for daily data).
- **Severity:** Low (Validation Strictness). Guarantees reproducible configuration.

---

## 4. Mathematical Correctness Gaps & Methodology Boundaries

### 4.1 Linear Euler Risk Attribution vs Empirical Step-Distributions
- **Boundary Description:** The Euler decomposition implemented in `attribution.py` uses linear covariance-beta marginal VaR:
  $$\frac{\partial \text{VaR}_\alpha}{\partial w_i} = \frac{\text{Cov}(R_i, R_p)}{\sigma_p^2} \text{VaR}_\alpha(R_p)$$
- **Condition:** This formula is theoretically exact only when the joint return distribution is elliptical (e.g., multivariate Gaussian or t). On heavily skewed, non-elliptical empirical return distributions, marginal VaR derived from linear betas diverges from non-parametric quantile derivatives.
- **Safeguard Present:** The report explicitly emits `methodology_type="linear_covariance_beta_component_var"` and provides `verify_attribution_finite_difference` as an audit tool.
- **Severity:** Informational / Methodological. Documented in report limitations.

### 4.2 Non-Parametric Tail Small-Sample Uncertainty
- **Boundary Description:** Historical simulation 99% VaR requires at least 100 observations to observe a single breach. On small samples ($N < 250$), discrete historical VaR exhibits high sample-variance step jumps.
- **Safeguard Present:** FragilityShield requires $N \ge 4$ minimum observations and provides Lab 8 Bootstrap Confidence Intervals to quantify sample variance.
- **Severity:** Inherent to empirical risk modeling.

---

## 5. Security & Isolation Boundaries

### 5.1 Main-Process Execution Model
- **Boundary:** The FragilityShield backend runs as a single-process ASGI application.
- **Limitation:** The runtime does not isolate arbitrary Python code using Linux namespaces, cgroups, or Docker containers.
- **Enforced Security Policy:** Untrusted plugins requiring arbitrary execution are blocked with `PermissionError`. Only approved native adapters are permitted in-process.
- **Production Requirement:** For enterprise multi-tenant deployments running arbitrary user-submitted Python models, a dedicated Celery/Redis or Kubernetes worker pool with seccomp/apparmor sandboxing is required.

---

## 6. Scope Limitations & Non-Implemented Features

1. **Live Broker Order Execution (Not Implemented by Design):**
   - FragilityShield is a quantitative risk, scenario stress-testing, and model validation laboratory.
   - It does not contain brokerage order routing, FIX protocol connections, or live capital deployment.
2. **Real-Time Streaming WebSocket Feeds (Not Implemented):**
   - Market data is ingested as batch historical OHLCV or return matrices.
   - Live tick-level streaming quote sockets are not implemented.
3. **Multi-Tenant User Authentication & RBAC (Not Implemented):**
   - The REST API does not enforce OAuth2/JWT bearer tokens or role-based access control.
   - Designed for local deployment and single-tenant quantitative research environments.

---

## 7. Production Readiness Verdict

FragilityShield is mathematically verified, robustly validated, and reproducible for its intended domain: **offline and research-grade quantitative risk calculation, scenario stress-testing, and model fragility analysis**.

Before claiming enterprise production readiness, the following architectural additions are required:
1. **Containerized Worker Isolation:** For safely executing untrusted third-party Python models.
2. **Authentication & Tenant Boundaries:** JWT authentication and per-tenant catalog isolation.
3. **Sector Taxonomy Harmonizer:** Intelligent synonym mapping (e.g. `"Banking"` $\leftrightarrow$ `"Financial Services"`) with explicit user confirmation.
