# FragilityShield — Phase 11 Mathematical Test Cases & Proofs

**Audit Date:** October 25, 2026  
**Auditor:** Quantitative Risk Validation & Numerical Analysis Lead  
**Scope:** Deterministic Test Cases, Analytical Proofs, Floating-Point Precision Boundaries, and Non-Gaussian Divergence  

---

## 1. Priority A — Expected Shortfall & Historical VaR Test Cases

### 1.1 Test Case A1: Constant Returns & Floating-Point Epsilon Anomaly
- **Objective:** Verify discrete Expected Shortfall when all observations are identical ($R_t = c$).
- **Inputs:**
  - $N = 20$ returns, all equal to $R_t = 0.02$.
  - Confidence level $\alpha = 0.95$.
- **Analytical Expectation:**
  - Losses $L_t = -0.02$ for all $t$.
  - Quantile $VaR_{0.95} = -0.02$.
  - Tail expectation $ES_{0.95} = \mathbb{E}[L \mid L \ge VaR] = -0.020000000000000000$.
- **Actual Implementation Output:**
  ```python
  var_val = -0.020000000000000000
  es_val  = -0.019999999999999983
  ```
- **Mathematical Root Cause:**
  ```python
  # risk.py lines 318-330
  tail_prob = 1.0 - float(confidence_level)  # In IEEE 754: 0.050000000000000044
  w = n * tail_prob                         # 20 * 0.050000000000000044 = 1.0000000000000009
  if w <= 1.0:                              # Evaluates to FALSE!
      es_val = float(sorted_losses[-1])
  else:
      k = int(np.floor(w))                  # k = 1
      frac = w - k                          # frac = 8.881784e-16
      sum_tail = float(np.sum(sorted_losses[-k:]))  # sum_tail = -0.02
      if frac > 1e-12:                      # Condition is FALSE (8.88e-16 < 1e-12)
          sum_tail += frac * float(sorted_losses[-k - 1])  # SKIPPED
      es_val = sum_tail / w                 # -0.02 / 1.0000000000000009 = -0.019999999999999983
  ```
- **Correction Requirement:**
  Use `math.isclose` or round effective tail count:
  `w = round(n * tail_prob, 10)` or `if math.isclose(w, 1.0, abs_tol=1e-12) or w < 1.0:`

---

### 1.2 Test Case A2: Single Extreme Loss in Small Sample ($N = 20, \alpha = 0.95$)
- **Inputs:**
  - $19$ returns of $+0.01$, $1$ return of $-0.50$ (losses: $19$ of $-0.01$, $1$ of $+0.50$).
  - $\alpha = 0.95$.
- **Analytical Expectation:**
  - Linear quantile of loss at $q = 19 \times 0.95 = 18.05$:
    $$-0.01 + 0.05 \times (0.50 - (-0.01)) = -0.01 + 0.0255 = 0.0155$$
  - Tail contains the single loss $+0.50$.
  - Tail expectation $ES = 0.5000$.
- **Observed Result:**
  - $VaR_{0.95} = 0.015500$.
  - $ES_{0.95} = 0.4999999999999996$ (affected by the same $w = 1.0000000000000009$ division).
  - Coherence holds: $ES \ge VaR$.

---

### 1.3 Test Case A3: Small Sample with Fractional Tail ($N = 4, \alpha = 0.95$)
- **Inputs:**
  - Returns: `[-0.04, -0.01, 0.02, 0.03]` (sorted losses: `[-0.03, -0.02, 0.01, 0.04]`).
  - $\alpha = 0.95 \implies tail\_prob = 0.05$.
  - $w = 4 \times 0.05 = 0.20 \le 1.0$.
- **Analytical Expectation:**
  - Tail has fewer than 1 observation ($w = 0.2 < 1$).
  - Under discrete spectral weighting, $ES_{0.95} = L_{(4)} = 0.0400$.
- **Observed Result:**
  - $w \le 1.0$ branch taken: $ES_{0.95} = 0.0400$.
  - $VaR_{0.95} = 0.0355$.
  - $ES \ge VaR$ strictly satisfied.

---

### 1.4 Test Case A4: Discrete Tied Quantiles
- **Inputs:**
  - Returns: `[-0.05, -0.05, -0.05, 0.01, 0.01, 0.02, 0.02, 0.03]`.
  - Top 3 losses are identical: `0.05, 0.05, 0.05`.
  - $\alpha = 0.95$.
- **Observed Result:**
  - $VaR_{0.95} = 0.0500$.
  - $ES_{0.95} = 0.0500$.
  - Equality $ES = VaR$ holds correctly when the tail is completely flat.

---

## 2. Priority B — Risk Attribution Mathematical Proofs

### 2.1 Theoretical Proof of Algebraic Euler Closure
Let $R_p = \sum_{i=1}^K w_i R_i$ be the portfolio return with weights $w \in \mathbb{R}^K$ such that $\sum w_i = 1$.
The implemented beta is:
$$\beta_i = \frac{\text{Cov}(R_i, R_p)}{\text{Var}(R_p)} = \frac{(\Sigma w)_i}{w^T \Sigma w}$$
Marginal risk is computed as:
$$\text{MVaR}_i = \beta_i \text{VaR}_p$$
Component risk is computed as:
$$\text{CVaR}_i = w_i \text{MVaR}_i = w_i \beta_i \text{VaR}_p$$
Summing across all $K$ holdings:
$$\sum_{i=1}^K \text{CVaR}_i = \sum_{i=1}^K w_i \beta_i \text{VaR}_p = \text{VaR}_p \left( \sum_{i=1}^K w_i \beta_i \right)$$
Substitute $\beta_i$:
$$\sum_{i=1}^K w_i \beta_i = \sum_{i=1}^K w_i \frac{(\Sigma w)_i}{w^T \Sigma w} = \frac{\sum_{i=1}^K w_i (\Sigma w)_i}{w^T \Sigma w} = \frac{w^T \Sigma w}{w^T \Sigma w} \equiv 1.0$$
$$\implies \sum_{i=1}^K \text{CVaR}_i \equiv \text{VaR}_p$$
**Proof Conclusion:** The sum of Component VaRs equals total portfolio VaR identically for any portfolio, regardless of whether the returns are normally distributed or whether Historical VaR is used.

---

### 2.2 Numerical Demonstration of Non-Gaussian Divergence
When returns are non-Gaussian, the true Euler marginal risk contribution is the partial derivative:
$$\frac{\partial \text{VaR}_\alpha}{\partial w_i} = -\mathbb{E}[R_i \mid -R_p = \text{VaR}_\alpha]$$
We evaluated a 2-asset portfolio with heavy-tailed Student-$t$ ($\nu=3$) returns ($N = 1000$):
- **Implemented Covariance Beta Marginal VaR ($\text{MVaR}_1$):** $+0.030970$
- **True Numerical Finite-Difference Marginal VaR:**
  $$\frac{\text{VaR}(w + \epsilon e_1) - \text{VaR}(w - \epsilon e_1)}{2\epsilon} = -0.010208$$
- **Absolute Divergence:**
  $$\Delta = |0.030970 - (-0.010208)| = 0.041178$$
**Conclusion:** The implemented formula is a **Gaussian linear beta approximation**. It cannot be claimed as an exact decomposition of empirical non-parametric Historical VaR.

---

### 2.3 Short Position Support Failure in Domain Model
- **Test:** Created a portfolio with a short holding `Holding("SHORT", -5.0, 100.0, "Tech")`.
- **Result:** Raised `ValueError: quantity must be strictly positive and finite; got -5.0`.
- **Proof:** `Holding.__post_init__` in `models.py` line 44 enforces:
  ```python
  if not math.isfinite(self.quantity) or self.quantity <= 0.0:
      raise ValueError(f"quantity must be strictly positive and finite; got {self.quantity!r}")
  ```
- **Conclusion:** Claims that negative weights or short positions are supported are mathematically and operationally **FALSE** in the current domain model.

---

## 3. Priority C — Backtesting Statistics Likelihood-Ratio Proofs

### 3.1 Kupiec Likelihood Ratio ($LR_{\text{POF}}$)
Under $H_0: p = p_0$ vs $H_1: p = \hat{p} = x/N$:
$$L(p_0) = (1 - p_0)^{N - x} p_0^x, \quad L(\hat{p}) = (1 - \hat{p})^{N - x} \hat{p}^x$$
$$LR_{\text{POF}} = -2 \ln \frac{L(p_0)}{L(\hat{p})} = 2 \left[ x \ln\left(\frac{x}{N p_0}\right) + (N - x) \ln\left(\frac{N - x}{N(1 - p_0)}\right) \right]$$
- **Zero Breaches ($x = 0$):**
  $$\lim_{x \to 0} x \ln\left(\frac{x}{N p_0}\right) = 0$$
  $$LR_{\text{POF}}(x = 0) = -2 N \ln(1 - p_0)$$
  For $N = 100, p_0 = 0.05$:
  $$LR = -200 \ln(0.95) = 10.2586588775$$
  $$p\text{-value} = \text{erfc}\left(\sqrt{\frac{10.258659}{2}}\right) = \text{erfc}(2.264802) = 0.001360$$
  - Observed code output: $LR = 10.258659, p = 0.001360$. Match is exact to $10^{-9}$.
- **100% Breaches ($x = N$):**
  $$\lim_{x \to N} (N - x) \ln\left(\frac{N - x}{N(1 - p_0)}\right) = 0$$
  $$LR_{\text{POF}}(x = N) = -2 N \ln(p_0)$$
  For $N = 50, p_0 = 0.05$:
  $$LR = -100 \ln(0.05) = 299.573227355$$
  $$p\text{-value} = \text{erfc}\left(\sqrt{\frac{299.573227}{2}}\right) = 4.080853 \times 10^{-67}$$
  - Observed code output matches exact theory.

---

### 3.2 Christoffersen Independence Likelihood Ratio ($LR_{\text{ind}}$)
For transition counts $n_{00}, n_{01}, n_{10}, n_{11}$:
$$L(\pi) = (1 - \pi)^{n_{00} + n_{10}} \pi^{n_{01} + n_{11}}$$
$$L(\pi_{01}, \pi_{11}) = (1 - \pi_{01})^{n_{00}} \pi_{01}^{n_{01}} (1 - \pi_{11})^{n_{10}} \pi_{11}^{n_{11}}$$
$$LR_{\text{ind}} = -2 \ln \frac{L(\pi)}{L(\pi_{01}, \pi_{11})} \sim \chi^2(1)$$
$$LR_{\text{CC}} = LR_{\text{POF}} + LR_{\text{ind}} \sim \chi^2(2)$$
Exact survival function for $\chi^2(2)$:
$$\mathbb{P}(\chi^2(2) \ge z) = \int_z^\infty \frac{1}{2} e^{-u/2} du = e^{-z/2}$$
Implemented as `p_val_cc = float(math.exp(-lr_cc / 2.0))`.
Tested against independent SciPy `chi2.sf(lr_cc, df=2)`; difference is $< 10^{-15}$.

---

## 4. Priority D — Stress-Boundary Bisection Search Proofs

### 4.1 Monotonicity of Return Friction
For a return series $R_t$ under transaction friction parameter $f \ge 0$:
$$R_t'(f) = R_t - f$$
$$\mu(f) = \frac{1}{N}\sum (R_t - f) = \bar{R} - f \implies \frac{d\mu}{df} = -1.0 < 0 \quad (\text{strictly monotonically decreasing})$$
$$\sigma^2(f) = \frac{1}{N-1}\sum (R_t - f - (\bar{R} - f))^2 = \frac{1}{N-1}\sum (R_t - \bar{R})^2 = \sigma^2 \implies \frac{d\sigma}{df} = 0 \quad (\text{constant})$$
$$\text{Sharpe}(f) = \frac{\bar{R} - f}{\sigma}\sqrt{252} \implies \frac{d\text{Sharpe}}{df} = -\frac{\sqrt{252}}{\sigma} < 0 \quad (\text{strictly monotonically decreasing})$$
**Mathematical Guarantee:** Because $\text{Sharpe}(f)$ is strictly monotonic in $f$, if $\text{Sharpe}(0) > 0$ and $\text{Sharpe}(f_{\max}) < 0$, by the Intermediate Value Theorem there exists a unique break-even root $f^* \in (0, f_{\max})$. Bisection is mathematically guaranteed to converge linearly at rate $2^{-n}$.

### 4.2 Inverted Boundary Vulnerability
- **Test:** Called `run_stress_boundary_search(returns, min_param=0.05, max_param=0.01)`.
- **Observed Behavior:**
  - Evaluated metric at $min\_param = 0.05$, obtaining $\text{Sharpe} = -48.1170 \le 0.0$.
  - Line 1346 executed:
    `if is_lower_bounded and m_base <= failure_threshold:`
  - Returned `StressBoundaryResult(boundary_parameter_value=0.05, converged=True, iterations=0)`.
- **Finding:** The algorithm claims convergence to a valid root when the search bounds are completely inverted. An input assertion `if min_param >= max_param: raise ValueError(...)` is missing.
