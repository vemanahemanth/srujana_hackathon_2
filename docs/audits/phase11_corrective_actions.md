# FragilityShield — Phase 11 Corrective Actions & Hardening Blueprint

**Audit Date:** October 25, 2026  
**Auditor:** Quantitative Systems Architect & Forensic Auditor  
**Status:** Audit Specifications Staged for Authorized Remediation (No application code modified in Phase 11)  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  

---

## 1. Inventory of Specific Mathematical & Operational Deficiencies

From the Phase 11 evidence challenge, four specific code-level deficiencies and one architectural boundary limitation were identified:

1. **Deficiency 1 (Numerical Boundary Precision):** In `backend/fragility_engine/risk.py`, floating-point representation error in `tail_prob = 1.0 - float(confidence_level)` causes $w = N(1-\alpha)$ to equal $1.0000000000000009$ instead of $1.0$. This bypasses the $w \le 1.0$ check, enters the fractional tail branch, skips the fractional numerator addition ($frac < 10^{-12}$), and divides by $w > 1$, producing truncated Expected Shortfall estimates.
2. **Deficiency 2 (Boundary Interval Sanity Checks):** In `backend/fragility_engine/fragility.py`, `run_stress_boundary_search` lacks an assertion that $min\_param < max\_param$. When passed inverted bounds, it evaluates the baseline at $min\_param$ and falsely reports immediate convergence (`converged: True`, `iterations: 0`).
3. **Deficiency 3 (Risk Attribution Model Mismatch):** In `backend/fragility_engine/attribution.py`, `calculate_portfolio_risk_attribution` computes Component VaR as $w_i \beta_i \text{VaR}_p$. The documentation describes this as an exact decomposition, whereas it is the linear Gaussian covariance beta approximation (Jorion/Hallerbach).
4. **Deficiency 4 (Domain Model Short Position Constraint):** In `backend/fragility_engine/models.py`, `Holding.__post_init__` strictly enforces `quantity > 0.0`. Claims that the system supports negative weights, leverage, or short positions contradict the domain model constraint.
5. **Deficiency 5 (Untrusted Code Isolation Absence):** In `backend/fragility_engine/plugins.py`, all registered model plugins execute in-process within the main ASGI server process with full access to host environment variables and files.

---

## 2. Proposed Concrete Code Patches

*(These patches are documented here for audit review and staging; per the non-negotiable rules of Phase 11, application files have NOT been modified during this phase).*

### Patch 1: Floating-Point Boundary Fix in Expected Shortfall
- **File:** `backend/fragility_engine/risk.py`
- **Lines Affected:** 318–334
- **Proposed Patch:**
```diff
--- a/backend/fragility_engine/risk.py
+++ b/backend/fragility_engine/risk.py
@@ -318,10 +318,10 @@ def calculate_expected_shortfall(
     n = len(sorted_losses)
     tail_prob = 1.0 - float(confidence_level)
-    w = n * tail_prob
+    w = round(n * tail_prob, 9)
 
     # Acerbi & Tasche (2002) coherent discrete Expected Shortfall formulation
-    if w <= 1.0:
+    if w <= 1.0 or math.isclose(w, 1.0, abs_tol=1e-11):
         es_val = float(sorted_losses[-1])
     else:
         k = int(np.floor(w))
```
- **Acceptance Test:**
  `assert calculate_expected_shortfall([0.02] * 20, 0.95) == -0.02` passes exactly.

---

### Patch 2: Search Interval Validation in Stress-Boundary Search
- **File:** `backend/fragility_engine/fragility.py`
- **Lines Affected:** 1336–1341
- **Proposed Patch:**
```diff
--- a/backend/fragility_engine/fragility.py
+++ b/backend/fragility_engine/fragility.py
@@ -1336,6 +1336,12 @@ def run_stress_boundary_search(
     arr = np.asarray(returns, dtype=np.float64)
     if len(arr) < 5:
         raise ValueError("At least 5 return observations required for stress-boundary search.")
+    if not math.isfinite(min_param) or not math.isfinite(max_param):
+        raise ValueError(f"Search bounds must be finite; got min={min_param}, max={max_param}")
+    if min_param >= max_param:
+        raise ValueError(f"min_param ({min_param}) must be strictly less than max_param ({max_param})")
+    if tolerance <= 0.0 or not math.isfinite(tolerance):
+        raise ValueError(f"tolerance must be strictly positive; got {tolerance}")
 
     m_base = _evaluate_metric_under_param(arr, target_metric, attack_type, min_param)
```
- **Acceptance Test:**
  `run_stress_boundary_search(returns, min_param=0.05, max_param=0.01)` raises `ValueError("min_param (0.05) must be strictly less than max_param (0.01)")`.

---

### Patch 3: Attribution Methodology String & Short Position Review
- **File:** `backend/fragility_engine/attribution.py`
- **Lines Affected:** 180–210
- **Proposed Patch:**
```diff
--- a/backend/fragility_engine/attribution.py
+++ b/backend/fragility_engine/attribution.py
@@ -188,7 +188,7 @@ def calculate_portfolio_risk_attribution(
         asset_attributions=tuple(attributions),
         sector_risk_contributions=sector_contributions,
         euler_discrepancy=float(abs(port_var - sum(a.component_var for a in attributions))),
-        methodology="Euler Marginal Risk Allocation",
+        methodology="Euler Linear Covariance Beta Allocation (Jorion Component VaR)",
         disclaimer=(
             "Component VaR is derived using the linear covariance beta approximation. "
             "For non-Gaussian return distributions with heavy tails or skewness, "
             "true quantile sensitivity may deviate from linear beta contributions."
         ),
```

---

## 3. The Nine Critical Forensic Questions Answered

### 1. Is the VaR implementation correct under its declared convention?
**YES.** Historical VaR in `risk.py` strictly computes losses as $L = -R$ and evaluates the empirical quantile at $\alpha \in (0, 1)$ using NumPy's validated quantile methods. A 95% 1-day VaR of $0.0227$ means an expected maximum loss threshold of $2.27\%$, which aligns with standard positive loss convention.

### 2. Is the Expected Shortfall implementation correct under its declared convention?
**PARTIALLY YES (WITH A FLOATING-POINT BOUNDARY CAVEAT).** The algorithm implements the discrete spectral formulation of Acerbi & Tasche (2002) and guarantees $ES_\alpha \ge VaR_\alpha$. However, because binary floating-point representation of $1.0 - 0.95 = 0.050000000000000044$, when $N(1-\alpha)$ is mathematically an integer (e.g. $N=20, \alpha=0.95$), $w = 1.0000000000000009 > 1.0$. This skips the integer tail branch and divides the unaugmented tail sum by $w > 1$, resulting in a minor $O(10^{-16})$ truncation error (e.g. $ES = -0.019999999999999983$ instead of $-0.020000000000000000$). Patch 1 resolves this issue.

### 3. Does risk attribution calculate the risk measure it claims to calculate?
**NO — IT CALCULATES A LINEAR APPROXIMATION.** The code computes $\text{CVaR}_i = w_i \beta_i \text{VaR}_p$, where $\beta_i = \text{Cov}(R_i, R_p)/\text{Var}(R_p)$. While $\sum \text{CVaR}_i = \text{VaR}_p$ holds identically because $\sum w_i \beta_i \equiv 1.0$, this is the **Gaussian beta approximation (Jorion/Hallerbach Component VaR)**. For non-Gaussian heavy-tailed distributions (e.g. Student-$t$ with $\nu=3$), the numerical finite-difference marginal VaR diverges by over $400$ bps ($\Delta = 0.041178$) from the beta formula. Furthermore, `Holding` explicitly forbids short positions ($quantity \le 0$ raises `ValueError`).

### 4. Are the backtesting statistics correctly implemented, including edge cases?
**YES.** Kupiec POF likelihood-ratio test and Christoffersen Independence / Conditional Coverage tests match exact theoretical formulas:
- Zero breaches ($x = 0$): $LR = -2 N \ln(1 - p_0)$, matching to $10^{-9}$.
- 100% breaches ($x = N$): $LR = -2 N \ln(p_0)$, matching to $10^{-9}$.
- Clustered breaches: $n_{11} = 4$ correctly triggers $LR_{\text{ind}} = 17.7458, p < 10^{-4}$ (`REJECT_NULL`).
- P-values for $\chi^2(1)$ and $\chi^2(2)$ are computed using analytical closed-form survival functions ($\text{erfc}(\sqrt{LR/2})$ and $\exp(-LR_{\text{CC}}/2)$).

### 5. Is the stress-boundary search justified for every advertised attack type?
**YES FOR MONOTONIC ATTACKS, BUT LACKS INPUT VALIDATION.** Bisection is strictly justified for `transaction_friction` and `volatility_multiplier`, where Sharpe ratio and returns are provably monotonic. However, the implementation does not validate that $min\_param < max\_param$. When passed inverted bounds ($min=0.05, max=0.01$), it falsely reports `converged: True` with $0$ iterations.

### 6. Is arbitrary third-party model execution isolated from the main application process?
**NO.** The current execution model is **entirely in-process**. Custom plugins registered in `PluginRegistry` execute within the main Python runtime. Diagnostic tests proved that a plugin has full read access to all 54 host environment variables and the host filesystem. Exception catching prevents process crashes, but does not provide sandboxing.

### 7. Which Phase 10 verification claims should be downgraded?
1. **Model Plugin Security Isolation:** Downgraded from *Partially Verified* to **BROKEN / IN-PROCESS ONLY**. Capability declaration is verified; physical execution isolation is absent.
2. **Euler Risk Attribution:** Downgraded from *Verified* to **PARTIALLY VERIFIED (LINEAR BETA APPROXIMATION)**.
3. **Expected Shortfall:** Downgraded from *Verified* to **PARTIALLY VERIFIED (NUMERICAL BOUNDARY DEFECT)**.
4. **Stress-Boundary Search:** Downgraded from *Verified* to **PARTIALLY VERIFIED (MISSING BOUNDARY VALIDATION)**.

### 8. Which defects must be fixed before the project can credibly claim mathematical reliability?
1. The floating-point epsilon truncation in `calculate_expected_shortfall`.
2. The missing interval sanity validation ($min\_param < max\_param$) in `run_stress_boundary_search`.
3. The methodology disclosure in `calculate_portfolio_risk_attribution` clarifying that component risk is a Gaussian beta linear approximation.
4. The documentation claim regarding short positions, noting that `Holding` currently requires strictly positive quantities.

### 9. What are the five highest-priority fixes, with acceptance tests?

| Priority | Defect / Enhancement | Exact File & Lines | Acceptance Test |
| :---: | :--- | :--- | :--- |
| **P1** | Floating-point epsilon boundary fix in Expected Shortfall | `backend/fragility_engine/risk.py` lines 318–330 | Assert `calculate_expected_shortfall([0.02]*20, 0.95) == -0.02`. |
| **P1** | Boundary interval validation in stress-boundary search | `backend/fragility_engine/fragility.py` line 1339 | Assert `run_stress_boundary_search(returns, min_param=0.05, max_param=0.01)` raises `ValueError`. |
| **P2** | Methodology disclosure in risk attribution report | `backend/fragility_engine/attribution.py` line 191 | Assert `report.methodology` specifies linear covariance beta decomposition. |
| **P2** | Multi-tenant process-isolated worker backend | `backend/fragility_engine/plugins.py` line 855 | Assert custom plugin cannot access host `os.environ` when executed via isolated worker. |
| **P3** | Async offload of CPU calculations on ASGI loop | `backend/app.py` lines 280–310 | Assert `/api/health` responds in $< 10\text{ ms}$ during heavy simulation. |
