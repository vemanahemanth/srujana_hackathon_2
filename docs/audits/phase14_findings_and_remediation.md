# Phase 14 — Findings, Vulnerabilities & Remediation Register

**Audit Date:** 2026-10-25  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Classification Guide:**
- **CRITICAL:** Remote code execution, arbitrary data loss, authentication bypass, severe financial risk metric calculation corruption without warning.
- **HIGH:** Absence of OS-level process isolation for third-party extensions, systemic edge-case divergence in risk bounds, potential denial-of-service.
- **MEDIUM:** Sub-optimal numerical convergence in pathological edge cases, missing schema fields, missing rate limiting.
- **LOW:** Deprecated library warning, minor UI cosmetic alignment, synthetic adapter labeling clarity.
- **INFORMATIONAL:** Methodological boundary documentation, sample size recommendations, operational guidance.

---

## Findings Summary

| Finding ID | Severity | Affected Component | Title | Status |
| :--- | :--- | :--- | :--- | :--- |
| **FINDING-P14-01** | **HIGH** | `fragility_engine/plugins.py` | In-process execution of plugins lacks OS kernel sandboxing | **OPEN** (Documented Architectural Limitation) |
| **FINDING-P14-02** | **MEDIUM** | `fragility_engine/backtest.py` | Asymptotic Kupiec POF test distorted on small samples ($N < 250$) | **REMEDIATED & GUARDED** |
| **FINDING-P14-03** | **MEDIUM** | `fragility_engine/attribution.py` | Gaussian linear beta attribution does not model non-linear tail jumps | **REMEDIATED & DISCLOSED** |
| **FINDING-P14-04** | **LOW** | `backend/tests/test_application_api.py` | StarletteDeprecationWarning regarding httpx with TestClient | **OPEN** (Harmless Deprecation) |
| **FINDING-P14-05** | **INFORMATIONAL** | `fragility_engine/market_data.py` | Upstox market data adapter operates in synthetic sandbox mode only | **BY DESIGN** |

---

## Detailed Findings Register

### FINDING-P14-01: In-Process Execution of Plugins Lacks OS Kernel Sandboxing
- **Unique ID:** `FINDING-P14-01`
- **Severity:** **HIGH**
- **Affected Lab / Function / Route:**  
  - Lab: **Model Benchmark & Comparison Lab**
  - Component: `backend/fragility_engine/plugins.py` (`PluginRegistry.execute_plugin`)
  - Route: `POST /api/models/benchmark`
- **Reproduction Steps:**
  1. Define a third-party Python class implementing `ModelPlugin`.
  2. Register the plugin into `PluginRegistry` with `trusted=True`.
  3. Execute the plugin via `registry.execute_plugin(plugin_id, data)`.
  4. Notice that the execution occurs in the exact same OS process as the FastAPI web server.
- **Expected vs Actual Result:**
  - *Expected:* Third-party untrusted or semi-trusted plugins should execute in an isolated ephemeral microVM or container (e.g. gVisor, Docker container, Firecracker) with restricted filesystem, dropped capabilities, and blocked network access.
  - *Actual:* Execution occurs in-process. While `enforce_trusted_execution=True` prevents plugins registered with `trusted=False` from running, any plugin admitted as trusted has full host OS process permissions.
- **Evidence:**
  ```python
  # fragility_engine/plugins.py:883-889
  if self._enforce_trusted_execution and not self.is_trusted(plugin_id) and not trusted_override:
      raise PermissionError(...)
  return plugin.execute(input_data, config)  # In-process call on the host Python process!
  ```
  The registry's own `get_isolation_status()` confirms:
  `"os_isolation_active": False, "host_execution_model": "in_process"`.
- **User & Financial Model Impact:**
  If users are allowed to upload or register arbitrary third-party model plugins in a shared multi-tenant environment, a compromised plugin could read sensitive environment variables, access stored portfolio data, or alter calculation state.
- **Recommended Remediation:**
  For multi-tenant cloud deployments, decouple model execution from the web server using an asynchronous worker queue (Celery/Temporal) executing inside gVisor-sandboxed worker containers with `read_only` root filesystems.
- **Status:** **OPEN (Documented Architectural Constraint)**. The current policy gate correctly protects the single-user local deployment; containerization is required before multi-tenant cloud hosting.

---

### FINDING-P14-02: Asymptotic Kupiec POF Test Distorted on Small Samples ($N < 250$)
- **Unique ID:** `FINDING-P14-02`
- **Severity:** **MEDIUM**
- **Affected Lab / Function / Route:**  
  - Lab: **Statistical Calibration & Validation Lab**
  - Component: `backend/fragility_engine/backtest.py` (`calculate_kupiec_pof_test`)
  - Route: `POST /api/validation/calibrate`
- **Reproduction Steps:**
  1. Run Kupiec POF test with sample size $N = 30$ and confidence level 0.95.
  2. Expected breaches: $30 \times 0.05 = 1.5$.
  3. If 0 breaches occur, likelihood ratio is $-2 \times 30 \times \ln(0.95) \approx 3.08$.
  4. Compare against asymptotic $\chi^2(1)$ distribution critical value ($3.84$).
  5. The test fails to reject $H_0$ despite a true breach rate of zero, due to low power in small samples.
- **Expected vs Actual Result:**
  - *Expected:* When $N < 250$, the system must inform the quantitative user that the asymptotic $\chi^2(1)$ distribution has low statistical power and cannot reliably reject false models.
  - *Actual:* Engine correctly computes the exact mathematical likelihood ratio, and adds a `sample_size_warning` in the response when $N < 250$.
- **Evidence:**
  Verified in `backend/tests/test_forecast_backtest.py` and `backend/tests/test_phase14_adversarial_verification.py`. The warning is explicitly populated:
  `"Sample size N=30 is below the recommended minimum of 250 observations for asymptotic chi-square validity."`
- **User & Financial Model Impact:**
  Without disclosure, risk managers might falsely conclude that a model passed backtesting when the sample size was simply too small to detect under-performance.
- **Recommended Remediation:**
  Maintain the existing warning and provide an exact binomial test p-value alongside the asymptotic $\chi^2$ likelihood ratio.
- **Status:** **REMEDIATED & GUARDED**.

---

### FINDING-P14-03: Gaussian Linear Beta Attribution Does Not Model Non-Linear Tail Jumps
- **Unique ID:** `FINDING-P14-03`
- **Severity:** **MEDIUM**
- **Affected Lab / Function / Route:**  
  - Lab: **Risk Attribution Lab**
  - Component: `backend/fragility_engine/attribution.py` (`calculate_portfolio_risk_attribution`)
  - Route: `POST /api/attribution/evaluate`
- **Reproduction Steps:**
  1. Construct a portfolio with options or jump-diffusion assets with heavy tail dependence.
  2. Compute risk attribution using `calculate_portfolio_risk_attribution`.
  3. Inspect the returned component risk numbers.
- **Expected vs Actual Result:**
  - *Expected:* The output must explicitly declare that the attribution uses linear covariance beta decomposition and does not account for non-linear copula tail dependence.
  - *Actual:* The result includes:
    `"methodology_type": "linear_covariance_beta_component_var"`
    and lists explicit limitations in the result payload.
- **Evidence:**
  Verified in [test_attribution.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_attribution.py) and [test_phase14_adversarial_verification.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_phase14_adversarial_verification.py).
- **User & Financial Model Impact:**
  Users managing portfolios with derivative assets or asymmetrical payout structures are warned not to rely solely on linear beta attribution during severe tail events.
- **Recommended Remediation:**
  In future releases, supplement linear Gaussian attribution with historical Cornish-Fisher or empirical Expected Shortfall Euler attribution.
- **Status:** **REMEDIATED & DISCLOSED**.

---

### FINDING-P14-04: StarletteDeprecationWarning Regarding HTTPX with TestClient
- **Unique ID:** `FINDING-P14-04`
- **Severity:** **LOW**
- **Affected Lab / Function / Route:**  
  - Component: `backend/tests/test_application_api.py:18`
- **Reproduction Steps:**
  1. Run `pytest backend/tests/test_application_api.py`.
  2. Pytest produces 1 warning:
     `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`
- **Expected vs Actual Result:**
  - *Expected:* Clean test execution with zero warnings.
  - *Actual:* One benign library deprecation warning emitted by Starlette/FastAPI TestClient compatibility layer.
- **Evidence:**
  Pytest output: `527 passed, 1 warning in 1.56s`.
- **User & Financial Model Impact:**
  Zero impact on user experience or calculation accuracy.
- **Recommended Remediation:**
  Upgrade test fixture to modern Starlette TestClient syntax or update dependency in a future dependency maintenance cycle.
- **Status:** **OPEN (Harmless Deprecation)**.

---

### FINDING-P14-05: Upstox Market Data Adapter Operates in Synthetic Sandbox Mode Only
- **Unique ID:** `FINDING-P14-05`
- **Severity:** **INFORMATIONAL**
- **Affected Lab / Function / Route:**  
  - Lab: **Market Data Lab**
  - Component: `backend/fragility_engine/market_data.py` (`UpstoxSandboxAdapter`)
  - Route: `GET /api/market/quote/{symbol}`
- **Reproduction Steps:**
  1. Query `GET /api/market/quote/RELIANCE`.
  2. Observe simulated bid/ask, LTP, and timestamp generated via sandbox logic without making external HTTP/WebSocket requests to Upstox.
- **Expected vs Actual Result:**
  - *Expected:* Clear disclosure that the adapter is a sandbox test double and does not connect to live broker exchanges.
  - *Actual:* Code clearly names the class `UpstoxSandboxAdapter` and outputs deterministic synthetic ticks.
- **Evidence:**
  `backend/fragility_engine/market_data.py:28-35` docstring explicitly declares synthetic simulation mode.
- **User & Financial Model Impact:**
  Protects users from accidental live market execution or leaking credentials.
- **Recommended Remediation:**
  Maintain synthetic sandbox as default. Any future live broker integration must require explicit user opt-in, two-factor authentication, and separate microservice isolation.
- **Status:** **BY DESIGN**.
