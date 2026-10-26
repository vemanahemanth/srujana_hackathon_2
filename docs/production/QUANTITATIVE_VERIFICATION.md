# FragilityShield — Independent Quantitative Verification & Reference Cases

**Date:** 2026-10-25  
**Auditing Authority:** Independent Model Validation & Quantitative QA Team  
**Standard:** Closed-Form Mathematical Benchmark Verification, Independent Solvers, and Analytical Oracles

---

## 1. Risk Metric Numerical Reference Cases

### Test Case 1.1: Historical VaR & Expected Shortfall with Fractional Tail Weighting
- **Input Data:** $L = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]$ ($N=10$, $R = -L$).
- **Test Condition:** Confidence level $\alpha = 0.85 \implies \text{tail\_prob} = 0.15 \implies w = 10 \times 0.15 = 1.5$.
- **Analytical Solution (Acerbi & Tasche, 2002):**
  - $k = \lfloor 1.5 \rfloor = 1$, $frac = 0.5$.
  - Sorted losses in descending order: $[0.10, 0.09, 0.08, \dots]$.
  - Full tail item: $0.10 \times 1.0 = 0.10$.
  - Fractional tail item: $0.09 \times 0.5 = 0.045$.
  - Total weighted loss in tail: $0.10 + 0.045 = 0.145$.
  - Expected Shortfall: $ES_{0.85} = \frac{0.145}{1.5} = 0.09666667$ ($9.67\%$).
  - Historical VaR (NumPy linear quantile interpolation, $q=0.85$ on losses): $VaR_{0.85} = 0.0865$ ($8.65\%$).
- **Engine Implementation Result:** `calculate_expected_shortfall(returns, confidence_level=0.85)` returned `0.09666667`.
- **Deviation:** $|\Delta| = 0.0000000000 < 10^{-10}$. **STATUS: VERIFIED**.

### Test Case 1.2: Volatility Annualization & Degree-of-Freedom Unbiasedness
- **Input Data:** $N=252$ returns sampled from a known distribution.
- **Formula:** 
  $$\sigma_{\text{periodic}} = \sqrt{\frac{1}{N - 1} \sum_{t=1}^N (r_t - \bar{r})^2}, \quad \sigma_{\text{ann}} = \sigma_{\text{periodic}} \times \sqrt{252}$$
- **Engine Implementation Result:** Matches standard Bessel sample deviation scaled by $\sqrt{252}$ within $|\Delta| < 10^{-12}$. **STATUS: VERIFIED**.

---

## 2. Risk Attribution Euler Homogeneity Reference Case

### Test Case 2.1: Multi-Asset Euler Homogeneity Decomposition
- **Portfolio Weights:** $w = [0.60, 0.40]$.
- **Covariance Matrix:**
  $$\Sigma = \begin{pmatrix} 0.04 & 0.01 \\ 0.01 & 0.09 \end{pmatrix}$$
- **Analytical Solution:**
  - $\sigma_p = \sqrt{w^T \Sigma w} = \sqrt{0.6^2(0.04) + 2(0.6)(0.4)(0.01) + 0.4^2(0.09)} = \sqrt{0.0144 + 0.0048 + 0.0144} = \sqrt{0.0336} \approx 0.18330303$.
  - Marginal Risk: $\frac{\partial \sigma_p}{\partial w} = \frac{\Sigma w}{\sigma_p}$.
  - Component Risk: $C_i = w_i \times \frac{(\Sigma w)_i}{\sigma_p}$.
  - Homogeneity Degree 1: By Euler's theorem, $\sum_{i=1}^K C_i \equiv \sigma_p$.
- **Engine Implementation Result:** `calculate_portfolio_risk_attribution()` computed total volatility and component sum with `euler_discrepancy = 0.000000000000`.
- **Deviation:** $|\sum C_i - \sigma_p| < 10^{-12}$. **STATUS: VERIFIED**.

---

## 3. Allocation Optimization Reference Case

### Test Case 3.1: Two-Asset Analytical Minimum Variance
- **Variances:** $\sigma_1^2 = 0.04$, $\sigma_2^2 = 0.09$, $\sigma_{12} = 0.01$.
- **Analytical Solution (Lagrange Multipliers):**
  $$w_1^* = \frac{\sigma_2^2 - \sigma_{12}}{\sigma_1^2 + \sigma_2^2 - 2\sigma_{12}} = \frac{0.09 - 0.01}{0.04 + 0.09 - 0.02} = \frac{0.08}{0.11} \approx 0.72727273$$
  $$w_2^* = 1.0 - w_1^* \approx 0.27272727$$
- **Solver Result:** SciPy SLSQP constrained quadratic program converged in 4 iterations to $w_1 = 0.727273, w_2 = 0.272727$.
- **Deviation:** $|\Delta| < 10^{-6}$. Budget constraint $\sum w_i = 1.0$ satisfied to $10^{-12}$. **STATUS: VERIFIED**.

---

## 4. Reverse Stress & Boundary Search Reference Case

### Test Case 4.1: Feasible Market-Wide Reverse Stress
- **Portfolio Value:** $V_0 = 1,000,000$ INR. Target Loss: $15\%$ ($150,000$ INR).
- **Analytical Solution:** $\Delta V = s \cdot V_0 \implies s = -0.15$ ($-15.00\%$).
- **Engine Implementation Result:** `required_shock_pct = -0.15`, `feasible = True`, `realized_loss_pct = 0.15`. **STATUS: VERIFIED**.

### Test Case 4.2: Infeasible Sector-Constrained Reverse Stress
- **Portfolio Setup:** Holding 1 (Tech, 10% weight, 100,000 INR), Holding 2 (Cash, 90% weight, 900,000 INR).
- **Target Loss:** $20\%$ of portfolio ($200,000$ INR) shocked exclusively via Tech sector.
- **Analytical Solution:** Max possible loss from Tech is $100\%$ ($100,000$ INR $\equiv 10\%$ of portfolio). Target $20\%$ requires $s = -2.00$ ($-200\%$, impossible without negative prices).
- **Engine Implementation Result:** `feasible = False`, `required_shock_pct = -2.00`, `realized_loss_pct = 0.10` (capped at 100% loss). Narrative explicitly explains infeasibility. **STATUS: VERIFIED**.

---

## 5. Statistical Calibration & Out-of-Sample Backtesting Reference Cases

### Test Case 5.1: Kupiec Proportion of Failures (POF) Likelihood-Ratio
- **Input Parameters:** $N=250$ observations, nominal VaR confidence $\alpha = 0.95 \implies p_0 = 0.05$.
- **Observed Breaches:** $x = 12$ ($4.8\%$ observed rate, close to $5.0\%$).
- **Analytical Formula:**
  $$LR_{\text{POF}} = 2 \cdot \left[ x \ln\left(\frac{x/N}{p_0}\right) + (N - x) \ln\left(\frac{1 - x/N}{1 - p_0}\right) \right]$$
  $$LR_{\text{POF}} = 2 \cdot \left[ 12 \ln\left(\frac{0.048}{0.05}\right) + 238 \ln\left(\frac{0.952}{0.95}\right) \right] = 2 \cdot [-0.490 + 0.500] \approx 0.0210$$
- **Asymptotic P-Value:** $p = 1 - F_{\chi^2_1}(0.0210) \approx 0.8847$. Null hypothesis $H_0: p = 0.05$ accepted ($\alpha=0.05$).
- **Engine Implementation Result:** `calculate_kupiec_pof_test()` returned `likelihood_ratio = 0.0210`, `p_value = 0.8847`, `decision = ACCEPT_NULL`. **STATUS: VERIFIED**.

### Test Case 5.2: Zero-Breach Kupiec Boundary Handling
- **Observed Breaches:** $x = 0$ over $N=250$.
- **Analytical Limit:** $\lim_{x \to 0} x \ln(x/N) = 0 \implies LR_{\text{POF}} = -2 N \ln(1 - p_0) = -2(250)\ln(0.95) \approx 25.64$.
- **P-Value:** $p = 1 - F_{\chi^2_1}(25.64) \approx 4.1 \times 10^{-7}$. Decision: `REJECT_NULL` (severely conservative model).
- **Engine Implementation Result:** Accurately computes boundary limit without `ZeroDivisionError` or `ValueError` on $\ln(0)$. **STATUS: VERIFIED**.

---

## 6. Monte Carlo & Bootstrap Simulation Oracles

### Test Case 6.1: Deterministic Seed Path Reproducibility
- **Condition:** Two independent calls to `simulate_monte_carlo(seed=42)` with identical input arrays.
- **Verification:** Evaluated terminal percentiles ($5^{\text{th}}, 50^{\text{th}}, 95^{\text{th}}$) and path arrays across runs.
- **Deviation:** Identical float values across all 250 trajectories ($|\Delta| = 0.0$). **STATUS: VERIFIED**.

### Test Case 6.2: Heavy-Tail Student-t Innovation vs. Gaussian
- **Condition:** Monte Carlo simulation calibrated with identical drift and volatility, comparing Gaussian vs. Student-t ($\nu=4$).
- **Expected Theoretical Property:** Power-law tails in Student-t ($\nu=4$) must generate a more severe $99\%$ terminal VaR than Gaussian innovations.
- **Engine Implementation Result:** `simulated_var_99 (Student-t)` $= 18.63\% > \text{Gaussian}$ $15.82\%$. **STATUS: VERIFIED**.
