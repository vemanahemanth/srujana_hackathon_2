# FragilityShield — Phase 11 Audit Evidence Challenge

**Audit Date:** October 25, 2026  
**Auditor:** Independent Senior Software Auditor, Quantitative Validation Lead & Application Security Reviewer  
**Scope:** Independent challenge of Phase 10 verification claims, tracing claims to actual source code, tests, and independently computed reference values.  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  

---

## 1. Challenge Methodology

Every claim in the Phase 10 audit documents was subjected to independent scrutiny. A claim was not accepted merely because a function exists or an automated test passes.

### Evaluation Criteria
1. **Mathematical Ground Truth:** Does the code compute the exact mathematical formula it claims, or is it an approximation/heuristic?
2. **Boundary Sensitivity:** How does the implementation behave under binary floating-point representation limits ($1.0 - 0.95 = 0.050000000000000044$), zero volatility, ties, and small sample sizes?
3. **Execution Reality vs Contract Declaration:** Does a capability flag (e.g. `code_isolation_required`) trigger physical isolation, or is it only a metadata label?
4. **Negative Case Handling:** Are invalid bounds ($min\_param > max\_param$) or negative positions handled safely, or do they produce false passes?

---

## 2. Claim-by-Claim Verification & Challenge Matrix

| Phase 10 Claim | Source Function & File | Supporting Test | Actually Executed? | Independent Expected Result | Observed Implementation Result | Missing Edge Cases Identified | Phase 11 Challenged Status |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- | :---: |
| **Claim 1: Coherent Expected Shortfall** ($ES \ge VaR$) | `calculate_expected_shortfall` in `risk.py` lines 282–334 | `test_risk_engine.py`, `test_statistical_calibration.py` | Yes | For $N=20, \alpha=0.95$, returns `[0.02]*20`: expected $ES = -0.02$, $VaR = -0.02$. | $VaR = -0.0200$, but $ES = -0.019999999999999983$. | **Floating-point boundary bug:** $20 \times (1.0 - 0.95) = 1.0000000000000009 > 1.0$. Bypasses $w \le 1.0$ branch, evaluates $frac = 8.88 \times 10^{-16} < 10^{-12}$, omits fractional tail from numerator, and divides by $w > 1$. | **PARTIALLY VERIFIED** (Downgraded due to numerical boundary precision defect) |
| **Claim 2: Exact Euler Risk Attribution** ($\sum CVaR_i = VaR_p$) | `calculate_portfolio_risk_attribution` in `attribution.py` lines 80–185 | `test_attribution.py` | Yes | $\sum \text{CVaR}_i = \text{VaR}_p$ holds algebraically by linear construction ($\sum w_i \beta_i \equiv 1.0$). | Sum matches portfolio VaR to 9 decimal places. | **Distributional Assumption Mismatch:** Exact for Gaussian/linear models; diverges sharply from numerical finite-difference gradient ($\Delta = 0.041178$) under heavy-tailed Student-$t$ ($\nu=3$). **No short position support:** `Holding` forbids negative quantities ($quantity \le 0$ raises `ValueError`). | **PARTIALLY VERIFIED** (Downgraded from exact claim to linear beta approximation) |
| **Claim 3: Kupiec POF Likelihood-Ratio Test** | `calculate_kupiec_pof_test` in `backtest.py` lines 460–550 | `test_forecast_backtest.py` | Yes | For $N=100, x=0, \alpha=0.95$: $LR = -200 \ln(0.95) \approx 10.258659, p \approx 0.001360$. | $LR = 10.258659, p = 0.001360$, decision `REJECT_NULL`. | $N=1$ evaluates single trial without warning of insufficient trials; $N < 30$ issues asymptotic warning. | **VERIFIED** |
| **Claim 4: Christoffersen Independence Test** | `calculate_christoffersen_test` in `backtest.py` lines 557–670 | `test_forecast_backtest.py` | Yes | For $N=50$, $5$ clustered breaches: $n_{11}=4, LR_{\text{ind}} > 10$. | $n_{11}=4, LR_{\text{ind}}=17.7458, p < 10^{-4}$ (`REJECT_NULL`). | When zero breaches occur in transitions, sets $LR_{\text{ind}} = 0.0, p = 1.0$ (`ACCEPT_NULL`). Higher-order lag dependencies ($lag > 1$) not tested. | **VERIFIED** |
| **Claim 5: Stress-Boundary Search Convergence** | `run_stress_boundary_search` in `fragility.py` lines 1309–1412 | `test_reverse_stress_and_boundary.py` | Yes | For $R = [0.01, \dots], \text{Sharpe} \le 0.0$, bisection converges to break-even friction. | Converged to $0.0125$ ($125$ bps) in 15 iterations. | **Missing input validation:** When $min\_param = 0.05 > max\_param = 0.01$ (inverted bounds), fails to reject inputs and claims false convergence (`converged: True`, `iters: 0`). | **PARTIALLY VERIFIED** (Valid for monotonic friction, but lacks boundary sanity checks) |
| **Claim 6: Model Plugin Security Isolation** | `PluginRegistry` in `plugins.py`, `model_lab.py` | `test_model_integration_lab.py` | Yes | Custom plugin must be isolated from host environment, filesystem, and credentials. | Custom `InspectingPlugin` executed in-process with access to all 54 host `os.environ` keys and root filesystem (`/etc`). | `code_isolation_required: True` is purely a metadata capability flag; no sandbox runner or worker subprocess exists. | **BROKEN** (as a security claim; functional only as an in-process adapter) |
| **Claim 7: Reverse Stress Testing Solvers** | `run_reverse_stress_test` in `scenarios.py` lines 684–780 | `test_reverse_stress_and_boundary.py` | Yes | Target loss $10\%$ on portfolio ₹65,000 requires $-10\%$ market shock ($-\tau$). | Solves $s^* = -0.100000$, realized loss = ₹6,500.00. | Over-allocated target loss on minor sector correctly returns `feasible: False` with maximum 100% sector loss. | **VERIFIED** |
| **Claim 8: Zero Look-Ahead ML Splitting** | `create_chronological_split` in `ml.py` lines 240–310 | `test_ml_evaluation.py` | Yes | Training indices strictly precede test indices: $\max(T_{\text{train}}) < \min(T_{\text{test}})$. | Proven by assertion: `max(train_idx) < min(test_idx)`. | Assumes incoming data is pre-sorted chronologically; does not re-sort by timestamp automatically. | **VERIFIED** |
| **Claim 9: API / SDK / CLI Parity** | `app.py`, `sdk.py`, `cli.py` | Inline execution verification | Yes | Identical 10-return sample calculation across SDK, REST API, and CLI. | 95% VaR ($0.022750$) and annualized volatility ($0.276098$) match to $10^{-9}$. | Formatting differences: CLI rounds to 4 decimals (e.g. `2.27%`), API/SDK retain double-precision floats. | **VERIFIED** |

---

## 3. Detailed Forensic Deconstruction of High-Priority Claims

### 3.1 Challenge to Priority A: Expected Shortfall Floating-Point Boundary Anomaly
- **Claim in Phase 10:** "Acerbi & Tasche (2002) spectral discrete estimator is exact and coherent."
- **Independent Finding:**
  In `risk.py`:
  ```python
  tail_prob = 1.0 - float(confidence_level)
  w = n * tail_prob
  if w <= 1.0:
      es_val = float(sorted_losses[-1])
  else:
      k = int(np.floor(w))
      frac = w - k
      sum_tail = float(np.sum(sorted_losses[-k:]))
      if frac > 1e-12:
          sum_tail += frac * float(sorted_losses[-k - 1])
      es_val = sum_tail / w
  ```
  When $N=20$ and $\alpha=0.95$:
  - Mathematically, $N(1-\alpha) = 20 \times 0.05 = 1.0$.
  - In IEEE 754 binary floating-point:
    $$1.0 - 0.95 = 0.05000000000000004440892098500626$$
    $$w = 20 \times (1.0 - 0.95) = 1.000000000000000888178419700125$$
  - Because $w > 1.0$, the condition `w <= 1.0` evaluates to **`False`**!
  - It enters the `else:` branch with $k = \lfloor w \rfloor = 1$, and $frac = 8.88 \times 10^{-16}$.
  - Because $frac < 10^{-12}$, line 328 skips adding the fractional tail element to `sum_tail`.
  - However, line 330 divides `sum_tail` by $w = 1.0000000000000009$!
  - Result: for constant return $0.02$, $ES = -0.019999999999999983$ instead of $-0.020000000000000000$.
- **Conclusion:** While the difference is small ($O(10^{-16})$), it proves that boundary integer counts are not handled robustly against floating-point epsilon.
- **Downgrade Status:** Downgraded from Fully Verified to **PARTIALLY VERIFIED**.

---

### 3.2 Challenge to Priority B: Euler Risk Attribution Mathematical Meaning
- **Claim in Phase 10:** "Proves Euler's homogeneity theorem: $\sum \text{CVaR}_i = \text{Total\_VaR}$."
- **Independent Finding:**
  In `attribution.py`:
  $$\text{ComponentVaR}_i = w_i \beta_i \text{VaR}_p, \quad \text{where } \beta_i = \frac{(\Sigma w)_i}{w^T \Sigma w}$$
  1. The sum $\sum \text{ComponentVaR}_i = \text{VaR}_p$ is an algebraic identity that holds for **ANY** scalar multiplied by $w_i \beta_i$, because $\sum w_i \beta_i \equiv 1.0$.
  2. This identity represents the **linear Gaussian covariance beta decomposition (Jorion/Hallerbach)**.
  3. Under non-Gaussian heavy-tailed distributions (e.g. Student-$t$ with $\nu=3$), the true partial derivative $\frac{\partial \text{VaR}}{\partial w_i}$ evaluated numerically was $-0.010208$, while the implemented beta marginal VaR was $+0.030970$ (a difference of $0.041178$).
  4. The domain model `Holding` explicitly forbids negative quantities (`quantity <= 0.0` raises `ValueError`), meaning short positions and negative weights cannot be represented in a `Portfolio`.
- **Conclusion:** The implementation is a valid Gaussian beta linear allocation, but cannot claim to be exact non-parametric Historical VaR decomposition, nor does it support short positions.
- **Downgrade Status:** Downgraded from Fully Verified to **PARTIALLY VERIFIED**.

---

### 3.3 Challenge to Priority D: Stress-Boundary Search Robustness
- **Claim in Phase 10:** "Uses robust root bisection to discover break-even friction."
- **Independent Finding:**
  In `fragility.py`:
  ```python
  def run_stress_boundary_search(returns, ..., min_param=0.0, max_param=0.05, ...):
      m_base = _evaluate_metric_under_param(arr, target_metric, attack_type, min_param)
      if is_lower_bounded and m_base <= failure_threshold:
          return StressBoundaryResult(..., boundary_parameter_value=min_param, converged=True)
  ```
  1. If a user passes inverted bounds $min\_param = 0.05, max\_param = 0.01$, the function evaluates $m_{\text{base}}$ at $0.05$ (where Sharpe ratio is negative), triggers line 1346, and immediately returns `converged: True` with boundary $0.05$ without performing any bisection.
  2. The function lacks an assertion or check that $min\_param < max\_param$ and $tolerance > 0$.
- **Conclusion:** Bisection is mathematically sound for monotonic transaction friction, but the function lacks essential input validation for search interval boundaries.
- **Downgrade Status:** Downgraded to **PARTIALLY VERIFIED**.

---

### 3.4 Challenge to Priority E: Plugin Security Isolation
- **Claim in Phase 10:** "Feature-flagged in capability report (`code_isolation_required`), but physically executes in-process."
- **Independent Finding:**
  1. A custom `ModelPlugin` registered in `PluginRegistry` executes within the primary ASGI server process.
  2. An independent inspection plugin demonstrated unrestricted access to `os.environ` (reading all 54 environment variables) and the host filesystem.
  3. No subprocess, seccomp jail, or container sandbox is ever spawned.
- **Conclusion:** As a security isolation claim, arbitrary third-party model sandboxing is **BROKEN / NOT IMPLEMENTED**. It is solely functional as an in-process developer adapter.
- **Downgrade Status:** Downgraded to **BROKEN / IN-PROCESS ONLY**.
