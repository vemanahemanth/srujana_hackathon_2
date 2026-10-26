# FragilityShield — Phase 10 Quantitative & Mathematical Validation Audit

**Audit Date:** October 25, 2026  
**Auditor:** Quantitative Risk Validation & Statistical Audit Lead  
**Scope:** Mathematical Formulations, Sign Conventions, Estimators, Attribution Theorems, and Numerical Edge Cases  

---

## 1. Executive Summary of Quantitative Findings

The quantitative engines in `backend/fragility_engine/` were independently audited against formal financial mathematical theory, regulatory risk modeling standards (Basel III/IV), and numerical analysis principles.

### Key Quantitative Verification Results
1. **Value-at-Risk & Sign Conventions (`risk.py`):**
   - Correctly enforces the positive loss convention: $L_t = -R_t$.
   - A 95% 1-day VaR of $0.024$ means a $2.4\%$ threshold loss ($R_t \le -2.4\%$) with $95\%$ confidence.
2. **Coherent Expected Shortfall (`risk.py`):**
   - Implements the exact discrete spectral formulation of Acerbi & Tasche (2002).
   - Invariant: $ES_\alpha(L) \ge VaR_\alpha(L)$ holds for all sample distributions, sample sizes, and confidence levels.
3. **Parametric Gaussian Formulations (`plugins.py`):**
   - Exact analytical normal tail integrals:
     $$VaR_\alpha = -\mu + z_\alpha \sigma, \quad ES_\alpha = -\mu + \sigma \frac{\phi(z_\alpha)}{1 - \alpha}$$
   - Proven by Mills' ratio: $\frac{\phi(z)}{1-\Phi(z)} > z \implies ES_\alpha > VaR_\alpha$ strictly holds for all $\sigma > 0$.
4. **Euler Marginal Risk Attribution & Deconstruction (`attribution.py`):**
   - **Audit Discovery:** The reported identity $\sum \text{CVaR}_i = \text{VaR}_p$ is mathematically verified, but **relies on the Gaussian beta approximation** ($\beta_i = \text{Cov}(R_i, R_p)/\text{Var}(R_p)$).
   - Because $\sum w_i \beta_i \equiv 1$, $\sum w_i \beta_i \text{VaR}_p = \text{VaR}_p$ holds algebraically by linear construction.
   - For true non-Gaussian Historical VaR, the exact mathematical derivative is the conditional expectation $\mathbb{E}[-R_i \mid -R_p = \text{VaR}_p]$, which differs from the covariance beta.
   - **Nomenclature Clarification:** In this module, `CVaR` denotes **Component VaR** ($w_i \cdot \text{MVaR}_i$), NOT **Conditional Value-at-Risk** (Expected Shortfall).
5. **Reverse Stress Testing Solvers (`scenarios.py`):**
   - Analytically solves the linear inverse shock: $s^* = -\frac{\tau \cdot V_0}{V_{\text{target}}}$.
   - Correctly verifies the feasibility boundary $s^* \ge -1.0$ (prices cannot be negative).
   - When a sector's total market value is less than the required portfolio loss, the solver correctly reports `feasible = False` with the maximum achievable 100% sector wipeout loss.
6. **Fragility Stress-Boundary Root Search (`fragility.py`):**
   - Implements bisection root finding to discover break-even friction / volatility limits.
   - **Mathematical Boundary Condition:** Bisection assumes monotonicity of the target metric with respect to the perturbation parameter (e.g., return friction $f$ strictly monotonically reduces Sharpe ratio).
7. **Statistical Backtesting Tests (`backtest.py`):**
   - Kupiec Unconditional Coverage POF test implements exact likelihood-ratio asymptotics with $\chi^2(1)$ exact survival p-value via $\text{erfc}(\sqrt{LR/2})$.
   - Christoffersen Independence test implements first-order Markov transition probabilities with $\chi^2(1)$ p-value.
   - Combined Conditional Coverage test $LR_{\text{CC}} = LR_{\text{POF}} + LR_{\text{ind}}$ implements $\chi^2(2)$ exact survival p-value via $\exp(-LR_{\text{CC}} / 2)$.

---

## 2. Mathematical Audit of Core Estimators

### 2.1 Historical Value-at-Risk (VaR)
- **Mathematical Definition:**
  For a return series $R = (R_1, \dots, R_N)$ and confidence level $\alpha \in (0, 1)$, define losses $L_t = -R_t$.
  $$VaR_\alpha(L) = \inf \{ l \in \mathbb{R} : F_L(l) \ge \alpha \}$$
- **Implementation in `risk.py`:**
  ```python
  losses = -arr
  var_value = float(np.quantile(losses, conf, method=method))
  ```
- **Independent Verification Case:**
  - Return sample: `[-0.03, -0.01, 0.00, 0.02, 0.04]` ($N = 5$).
  - Losses: `[0.03, 0.01, -0.00, -0.02, -0.04]`.
  - Sorted losses: `[-0.04, -0.02, 0.00, 0.01, 0.03]`.
  - $\alpha = 0.95$, method `'linear'`:
    Index $q = 0.95 \times (5 - 1) = 3.8 \implies 0.01 + 0.8 \times (0.03 - 0.01) = 0.0260$.
  - Executed result: `calculate_historical_var(..., 0.95, method='linear') == 0.0260`.
  - **Verdict:** VERIFIED.

### 2.2 Expected Shortfall (CVaR / Tail VaR)
- **Mathematical Definition (Acerbi & Tasche, 2002):**
  For a discrete sample of sorted losses $L_{(1)} \le L_{(2)} \le \dots \le L_{(N)}$, tail probability $p = 1 - \alpha$, and effective tail count $w = N(1 - \alpha)$:
  $$ES_\alpha(L) = \frac{1}{w} \left[ \sum_{j=1}^{\lfloor w \rfloor} L_{(N - j + 1)} + (w - \lfloor w \rfloor) L_{(N - \lfloor w \rfloor)} \right]$$
- **Implementation in `risk.py`:**
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
  return max(es_val, var_val)
  ```
- **Subadditivity & Coherence Guarantee:**
  Because $w = N(1-\alpha)$, when $w \le 1$ (sample tail has at most 1 observation), $ES_\alpha$ equals the maximum loss $L_{(N)}$.
  When $w > 1$, it integrates the fractional upper tail.
  The condition `return max(es_val, var_val)` enforces $ES_\alpha \ge VaR_\alpha$ even under small discrete sample rounding anomalies.
  - **Verdict:** VERIFIED.

### 2.3 Parametric Gaussian Models
- **Analytical Formulas:**
  Under $R_t \sim \mathcal{N}(\mu, \sigma^2)$, losses $L_t = -R_t \sim \mathcal{N}(-\mu, \sigma^2)$.
  $$VaR_\alpha = -\mu + z_\alpha \sigma$$
  $$ES_\alpha = \mathbb{E}[L \mid L > VaR_\alpha] = -\mu + \sigma \frac{\phi(z_\alpha)}{1 - \alpha}$$
  where $\phi(z) = \frac{1}{\sqrt{2\pi}} e^{-z^2/2}$ is the standard normal PDF.
- **Quantiles Used:**
  - $\alpha = 0.95 \implies z_{0.95} \approx 1.6448536269514722, \quad \phi(z_{0.95}) \approx 0.1031356403781258$
    $$\frac{\phi(z_{0.95})}{0.05} \approx 2.062712807562516 > 1.6448536269514722$$
  - $\alpha = 0.99 \implies z_{0.99} \approx 2.3263478740408408, \quad \phi(z_{0.99}) \approx 0.0266521422325983$
    $$\frac{\phi(z_{0.99})}{0.01} \approx 2.66521422325983 > 2.3263478740408408$$
- **Verification:**
  For $\mu = 0.001, \sigma = 0.02$:
  $$VaR_{0.95} = -0.001 + 1.6448536 \times 0.02 = 0.031897$$
  $$ES_{0.95} = -0.001 + 2.0627128 \times 0.02 = 0.040254$$
  Executed code matches theory to 10 decimal digits.
  - **Verdict:** VERIFIED.

---

## 3. Euler Risk Attribution Audit & Deconstruction

### 3.1 The Claim: $\sum \text{CVaR}_i = \text{VaR}_p$
In `backend/fragility_engine/attribution.py`, the system decomposes total portfolio VaR into constituent holding risk contributions:
$$\text{Total VaR} = \sum_{i=1}^K \text{ComponentVaR}_i$$

### 3.2 Theoretical Derivation & Investigation
Euler's Homogeneity Theorem states that if a risk measure $\rho(w)$ is positively homogeneous of degree 1 (i.e. $\rho(\lambda w) = \lambda \rho(w)$ for all $\lambda > 0$):
$$\rho(w) = \sum_{i=1}^K w_i \frac{\partial \rho(w)}{\partial w_i}$$

1. **For Parametric Gaussian VaR:**
   $$\text{VaR}_p(w) = -\mu_p + z_\alpha \sigma_p(w) = -\sum w_i \mu_i + z_\alpha \sqrt{w^T \Sigma w}$$
   $$\frac{\partial \sigma_p}{\partial w_i} = \frac{(\Sigma w)_i}{\sigma_p} = \frac{\text{Cov}(R_i, R_p)}{\sigma_p} = \beta_i \sigma_p$$
   $$\implies \frac{\partial \text{VaR}_p}{\partial w_i} = -\mu_i + z_\alpha \beta_i \sigma_p \approx \beta_i \text{VaR}_p \quad (\text{when } \mu \approx 0)$$
   $$\text{ComponentVaR}_i = w_i \frac{\partial \text{VaR}_p}{\partial w_i} \approx w_i \beta_i \text{VaR}_p$$

2. **The Implementation in `attribution.py`:**
   ```python
   # Line 153-166 of attribution.py:
   cov_matrix = np.cov(matrix, rowvar=False)
   cov_with_portfolio = cov_matrix @ weights
   var_portfolio_daily = float(np.var(port_returns, ddof=1))
   betas = cov_with_portfolio / var_portfolio_daily
   mcr = betas * port_var
   component_vars = weights * mcr
   ```
3. **The Algebraic Identity:**
   $$\sum_{i=1}^K \text{component\_vars}_i = \sum_{i=1}^K w_i (\beta_i \text{VaR}_p) = \text{VaR}_p \left( \sum_{i=1}^K w_i \beta_i \right)$$
   Note that:
   $$\sum_{i=1}^K w_i \beta_i = \sum_{i=1}^K w_i \frac{(\Sigma w)_i}{w^T \Sigma w} = \frac{w^T \Sigma w}{w^T \Sigma w} \equiv 1.0$$
   Therefore:
   $$\sum_{i=1}^K \text{ComponentVaR}_i \equiv 1.0 \times \text{VaR}_p = \text{VaR}_p$$

### 3.3 Critical Findings & Caveats
- **Exactness:** The sum of component risk contributions equals the portfolio VaR **identically and algebraically** because the weights dotted with the covariance betas identically equals 1.
- **Approximation Nature:** This Euler allocation represents the **Jorion/Hallerbach Gaussian beta approximation** to Component VaR. If the underlying portfolio returns are highly skewed or heavy-tailed, the true partial derivative $\frac{\partial \text{VaR}_\alpha}{\partial w_i} = -\mathbb{E}[R_i \mid -R_p = \text{VaR}_p]$ can deviate from $\beta_i \text{VaR}_p$.
- **Nomenclature:** The variable name `CVaR_i` is used in docstrings for **Component VaR**, which can be easily confused with **Conditional VaR** (Expected Shortfall).
- **Classification:** **PARTIALLY VERIFIED** (mathematically consistent under the declared linear covariance beta model, but requires clear docstring documentation that it is the beta-linear component allocation, not non-parametric quantile sensitivity).

---

## 4. Scenario Stress Testing & Correlation Matrix Regularization

### 4.1 First-Order Linear P&L Identity
In `backend/fragility_engine/scenarios.py`:
$$\Delta V = \sum_{i=1}^K \Delta V_i = \sum_{i=1}^K V_i s_i$$
- When a sector shock $s_{\text{sector}}$ is applied, each holding in that sector receives $s_i = s_{\text{sector}}$.
- The P&L reconciliation condition $|\Delta V - \sum \Delta V_i| < 10^{-7}$ is strictly checked and verified across all tests.

### 4.2 Correlation Matrix Regularization (Higham / Eigenvalue Projection)
When off-diagonal elements of a correlation matrix are stressed to $\rho_{\text{stress}} = 0.85$, the resulting matrix $\Sigma_{\text{stress}}$ may have negative eigenvalues if $K > 2$.
In `scenarios.py`:
```python
eigvals, eigvecs = np.linalg.eigh(stressed_cov)
clipped_eigvals = np.maximum(eigvals, 1e-9)
psd_cov = eigvecs @ np.diag(clipped_eigvals) @ eigvecs.T
return 0.5 * (psd_cov + psd_cov.T)
```
- Eigenvalues are clipped to $\lambda_{\min} = 10^{-9} > 0$.
- Matrix symmetry is enforced: $\frac{1}{2}(A + A^T)$.
- **Mathematical Property:** Guarantees that the resulting covariance matrix is strictly positive definite, preventing imaginary portfolio volatilities $\sqrt{w^T \Sigma w}$.
- **Verdict:** VERIFIED.

### 4.3 Reverse Stress Testing Feasibility
In `run_reverse_stress_test`:
$$s^* = -\frac{\tau \cdot V_0}{V_{\text{target}}}$$
- For market shock: $V_{\text{target}} = V_0 \implies s^* = -\tau$.
- For sector shock: $V_{\text{target}} = w_{\text{sector}} V_0 \implies s^* = -\frac{\tau}{w_{\text{sector}}}$.
- If $s^* < -1.0$, the required loss exceeds the total capital invested in that sector.
- The implementation flags `feasible = False`, and caps the maximum achievable loss at $100\%$ of sector capital ($w_{\text{sector}} V_0$).
- **Verdict:** VERIFIED.

---

## 5. Statistical Backtesting Likelihood-Ratio Formulations

### 5.1 Kupiec Proportion of Failures (POF) Likelihood-Ratio Test
Let $N$ be the evaluation sample size, $x$ the number of realized breaches, and $p_0 = 1 - \alpha$ the nominal breach rate.
$$\hat{p} = \frac{x}{N}$$
Under $H_0: p = p_0$ versus $H_1: p = \hat{p}$:
$$LR_{\text{POF}} = -2 \ln \left[ \frac{(1 - p_0)^{N - x} p_0^x}{(1 - \hat{p})^{N - x} \hat{p}^x} \right] = 2 \left[ x \ln\left(\frac{\hat{p}}{p_0}\right) + (N - x) \ln\left(\frac{1 - \hat{p}}{1 - p_0}\right) \right]$$
- **Asymptotic Distribution:** $LR_{\text{POF}} \sim \chi^2(\text{df} = 1)$ under $H_0$.
- **Exact Survival p-value:**
  $$\mathbb{P}(\chi^2(1) \ge z) = 2(1 - \Phi(\sqrt{z})) = \text{erfc}\left(\sqrt{\frac{z}{2}}\right)$$
- **Boundary Handling in Code:**
  - When $x = 0$: $LR = -2 N \ln(1 - p_0)$
  - When $x = N$: $LR = -2 N \ln(p_0)$
  - When $\hat{p} == p_0$: $LR = 0.0$
- **Verdict:** VERIFIED.

### 5.2 Christoffersen Independence Test
Evaluates temporal clustering via a first-order two-state Markov chain:
- $n_{ij}$: count of periods with state $i$ followed by state $j$ ($0 = \text{no breach}, 1 = \text{breach}$).
- $\pi_{01} = \frac{n_{01}}{n_{00} + n_{01}}$, $\pi_{11} = \frac{n_{11}}{n_{10} + n_{11}}$, $\pi = \frac{n_{01} + n_{11}}{n_{00} + n_{01} + n_{10} + n_{11}}$.
$$LR_{\text{ind}} = -2 \ln \left[ \frac{L(\pi)}{L(\pi_{01}, \pi_{11})} \right] \sim \chi^2(1)$$
$$LR_{\text{CC}} = LR_{\text{POF}} + LR_{\text{ind}} \sim \chi^2(2)$$
- **Exact Survival p-value for $\chi^2(2)$:**
  $$\mathbb{P}(\chi^2(2) \ge z) = \int_z^\infty \frac{1}{2} e^{-u/2} du = e^{-z/2}$$
- **Implementation in `backtest.py`:**
  ```python
  p_val_cc = float(math.exp(-lr_cc / 2.0))
  ```
- **Verdict:** VERIFIED.

---

## 6. Numerical Edge Cases Audited

| Test Case | Module | Inputs | Expected Mathematical Behavior | Actual Implementation Output | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Zero Volatility** | `risk.py` | `returns = [0.01, 0.01, 0.01, 0.01]` | Volatility $= 0.0$, Sharpe $= 0.0$, VaR $= -0.01$ | Returns $\sigma = 0.0$, Sharpe ratio $= 0.0$ (safe fallback) | **PASSED** |
| **All Constant Returns** | `plugins.py` | `returns = [0.005] * 20` | Normal variance $= 0.0$ | Handled without division-by-zero errors | **PASSED** |
| **Small Sample Size** | `risk.py` | $N = 3$ | Sample variance computable ($\text{ddof}=1$), small sample caveat issued | Issues explicit structured warnings for $N < 20$ (95% VaR) and $N < 100$ (99% VaR) | **PASSED** |
| **Under-Sampled Quantiles** | `risk.py` | $N = 4, \alpha = 0.99$ | Quantile exceeds observation rank | Computes linear interpolated quantile, issues sample size warning | **PASSED** |
| **Zero Breaches ($x = 0$)** | `backtest.py` | `breaches = [False] * 100` | $LR_{\text{POF}} = -2 N \ln(1 - p_0) > 0$ | $LR = -200 \ln(0.95) \approx 10.2587$, p-value $= 0.00136$ (`REJECT_NULL`) | **PASSED** |
| **100% Breaches ($x = N$)** | `backtest.py` | `breaches = [True] * 50` | $LR_{\text{POF}} = -2 N \ln(p_0) > 0$ | $LR = -100 \ln(0.05) \approx 299.57$, p-value $\approx 0.0$ (`REJECT_NULL`) | **PASSED** |
| **Non-Finite Returns (NaN/Inf)** | `risk.py` | `returns = [0.01, np.nan, 0.02]` | Rejection with descriptive exception | Raises `ValueError("Return at index 1 must be finite (not NaN or Inf)")` | **PASSED** |
| **Zero Portfolio Value** | `models.py` | `holdings = []` or all prices $= 0$ | Total valuation $= 0.0$, weights undefined | Raises `ValueError("Total portfolio value must be positive")` | **PASSED** |
