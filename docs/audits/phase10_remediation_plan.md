# FragilityShield — Phase 10 Remediation & Hardening Plan

**Audit Date:** October 25, 2026  
**Auditor:** Senior Software Architect & Quantitative Systems Auditor  
**Status:** Audit Findings Documented (Remediation Actions Staged for Authorization)  

---

## 1. Prioritization Framework

Audit findings are categorized according to the following risk hierarchy:
- **P0 — Critical:** Material security risk, fabricated outputs, or severe mathematical error affecting core scientific conclusions.
- **P1 — High:** Core workflow broken, material calculation defect, or false verification claims.
- **P2 — Medium:** Incomplete integration, missing robustness checks, misleading diagnostics, or reproducibility gaps.
- **P3 — Low:** Documentation, usability, nomenclature ambiguities, or minor maintainability issues.

---

## 2. Prioritized Findings & Remediation Items

### Item 1: Sandboxed Execution Environment for Untrusted User Code (Priority: P1 — High)
- **Evidence:** `PluginRegistry` (`fragility_engine/plugins.py`) and `run_model_integration_suite` (`fragility_engine/model_lab.py`) execute Python callable objects directly in the main server process. `ModelManifest.code_isolation_required` correctly flags `Required before execution` in capability reports, but does not prevent direct in-process invocation if invoked via the plugin registry.
- **Impact:** In a multi-tenant or web-hosted deployment, untrusted user code can access server environment variables, filesystem files, or execute system commands.
- **Recommended Fix:**
  1. Introduce an `ExecutionBackend` abstraction in `plugins.py` supporting `InProcessBackend` (default for local development) and `SubprocessIsolatedBackend` or `ContainerIsolatedBackend`.
  2. For isolated execution, spawn a subprocess with dropped privileges (`setuid`/`setgid` or seccomp filter on Linux) and pass serialized inputs/outputs via stdin/stdout with strict timeouts and memory caps (`resource.setrlimit`).
- **Acceptance Test:**
  Create a test model plugin that attempts to read an environment variable `SECRET_KEY` or call `os.system("echo hack")`. The test must prove that under isolated execution, the attempt is blocked or confined to the sandbox.
- **Dependencies:** Standard library `multiprocessing` / `subprocess` or container runtime for cloud deployment.

---

### Item 2: Euler Marginal Risk Attribution Terminology and Exact Formulation Disclosure (Priority: P2 — Medium)
- **Evidence:** In `backend/fragility_engine/attribution.py`, `calculate_portfolio_risk_attribution` computes component risk using the linear covariance beta formula:
  $$\text{CVaR}_i = w_i \beta_i \text{VaR}_p, \quad \text{where } \beta_i = \frac{\text{Cov}(R_i, R_p)}{\text{Var}(R_p)}$$
  Because $\sum w_i \beta_i \equiv 1$, $\sum \text{CVaR}_i = \text{VaR}_p$ holds algebraically. However, in quantitative literature, this represents the **Gaussian beta linear approximation to Component VaR** (Jorion, 2007; Hallerbach, 2003). For non-Gaussian returns, the true derivative of Historical VaR with respect to portfolio weight is the conditional tail expectation $\mathbb{E}[-R_i \mid -R_p = \text{VaR}_p]$. Furthermore, using `CVaR` for Component VaR risks confusion with Conditional VaR (Expected Shortfall).
- **Impact:** Quantitative researchers might interpret the attribution as non-parametric quantile derivatives rather than the Gaussian beta decomposition.
- **Recommended Fix:**
  1. Clarify the methodology string in `PortfolioRiskAttributionReport`: `"Linear Covariance Beta Decomposition (Jorion Component VaR)"`.
  2. Update field names or documentation to distinguish `component_var` clearly from `conditional_var` (Expected Shortfall).
  3. Provide an optional non-parametric kernel-smoothed or quantile-regression marginal VaR estimator for non-Gaussian portfolios.
- **Acceptance Test:**
  Unit test asserting that `report.methodology` explicitly documents the linear Gaussian beta assumption and verifies that $\sum w_i \beta_i = 1.0$ is verified before decomposition.
- **Dependencies:** None. Pure documentation and optional estimator addition.

---

### Item 3: Reconcile Prior Documentation Claims Regarding Test Counts (Priority: P2 — Medium)
- **Evidence:** The previous summary report claimed "28 suites but lists 27 test-file entries and 473 passing tests", and included an entry for a non-existent test file `backend/tests/test_portfolio_concentration.py (12 tests)`. Forensic analysis confirmed that there are **exactly 27 test files** in `backend/tests/` and **473 collected test cases**, with concentration tests residing in `test_portfolio_lab.py` and `test_statistical_calibration.py`.
- **Impact:** Misleads external auditors and team members reading previous markdown completion reports.
- **Recommended Fix:**
  Update `docs/backend-implementation-status.md` and `docs/blueprint-requirements-matrix.md` to accurately state: **473 tests across 27 test files**, removing references to the phantom 28th suite.
- **Acceptance Test:**
  Script counting `ls -1 backend/tests/test_*.py` confirms 27 files, and pytest output confirms 473 tests.
- **Dependencies:** Documentation edit only.

---

### Item 4: Asynchronous Offloading of Heavy Quantitative Calculations (Priority: P2 — Medium)
- **Evidence:** In `backend/app.py`, endpoints such as `/api/risk/calculate`, `/api/fragility/run`, and `/api/scenarios/reverse-stress` run CPU-bound NumPy operations directly in the async route handler.
- **Impact:** Under concurrent HTTP requests, long-running calculations (e.g. 1000-path Monte Carlo simulations) block the asyncio event loop, increasing request latency for other API callers.
- **Recommended Fix:**
  Wrap compute-intensive calls in `anyio.to_thread.run_sync(...)`:
  ```python
  report = await anyio.to_thread.run_sync(calculate_risk_report, returns, ...)
  ```
- **Acceptance Test:**
  Load test simulating concurrent requests to `/api/health` during a long-running calculation to ensure `/api/health` responds in $< 10\text{ ms}$.
- **Dependencies:** Starlette / AnyIO (already installed in `.venv`).

---

### Item 5: Out-of-Sample EWMA Variance Initialization Causal Strictness (Priority: P3 — Low)
- **Evidence:** In `fragility_engine/fragility.py`, `calculate_ewma_volatility` initializes variance as `var_t = float(np.mean(arr ** 2))` when `initial_variance is None`. This computes the uncentered sample variance over the entire input array before running the recurrence loop.
- **Impact:** For rolling or out-of-sample evaluations, if a caller passes the evaluation test slice without specifying `initial_variance`, the initial variance uses future observations of that slice.
- **Recommended Fix:**
  Add a parameter `causal_mode: bool = False` or document that for out-of-sample testing, `initial_variance` should always be explicitly passed from the terminal variance of the training/in-sample window.
- **Acceptance Test:**
  Test showing that passing `initial_variance` from the training window yields strictly causal out-of-sample volatility forecasts.
- **Dependencies:** None.

---

## 3. Summary of Action Items

| Item | Finding | Priority | Recommended Action | Risk if Unaddressed |
| :---: | :--- | :---: | :--- | :--- |
| **1** | In-process execution of custom model code | **P1** | Implement process-isolated worker backend for untrusted code execution | Untrusted code could execute host operations in multi-tenant environments |
| **2** | Euler risk attribution methodology disclosure | **P2** | Clarify Gaussian beta approximation vs quantile sensitivity | Quantitative users might misinterpret non-normal tail decomposition |
| **3** | Test inventory documentation reconciliation | **P2** | Correct "28 suites" claim to exact 27 test files / 473 tests | Misleading documentation in project reports |
| **4** | Asyncio loop blocking on heavy compute | **P2** | Offload compute functions to `anyio.to_thread.run_sync` | Latency spikes on concurrent REST API calls |
| **5** | EWMA variance initialization in out-of-sample | **P3** | Enforce passing prior variance for walk-forward evaluation | Subtle in-sample variance contamination in test slice |
