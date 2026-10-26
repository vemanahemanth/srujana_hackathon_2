# Phase 15 — Mathematical Conventions, Definitions & Attribution Specifications

**Audit Date:** 2026-10-25  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Auditor:** Quantitative Finance Validation Researcher

---

## 1. Risk Metric Mathematical Conventions

### 1.1 Return versus Loss Definition
FragilityShield operates on arithmetic simple returns:
$$R_t = \frac{P_t}{P_{t-1}} - 1.0$$
where $P_t$ is the asset price or portfolio equity at time $t$.
- **The Loss Random Variable ($L$):**
  $$L_t = -R_t$$
  - A positive return $R_t = +0.02$ corresponds to a negative loss $L_t = -0.02$.
  - A loss of 3% ($R_t = -0.03$) corresponds to a positive loss $L_t = +0.03$.

### 1.2 Value at Risk ($\text{VaR}_\alpha$) Sign Convention
FragilityShield strictly adheres to the **Positive Loss Convention**:
$$\text{VaR}_\alpha = Q_L(\alpha)$$
where $Q_L(\alpha)$ is the $\alpha$-quantile of the loss distribution $L = -R$.
- **Interpretation:** $\text{VaR}_{0.95} = +0.035$ means: *"With 95% confidence, portfolio losses will not exceed 3.5% over the holding period."*
- **Profitable / Low-Risk Portfolios:** If all historical returns are strictly positive, losses are strictly negative, resulting in $\text{VaR} < 0.0$ (indicating guaranteed gain at the quantile threshold).

### 1.3 Quantile Interpolation Methods
In `calculate_historical_var`, empirical quantiles are computed using `np.quantile(losses, confidence_level, method=method)`.
Supported interpolation methods:
- `'linear'` (default): $i + (j - i) \times \text{fraction}$, standard continuous interpolation.
- `'lower'`: $i$.
- `'higher'`: $j$.
- `'midpoint'`: $(i + j) / 2$.
- `'nearest'`: nearest observation index.

### 1.4 Expected Shortfall ($\text{ES}_\alpha$) Tail Selection & Fractional Weights
Following Acerbi & Tasche (2002), discrete empirical Expected Shortfall is defined to ensure subadditivity and coherence:
Let $L_{(1)} \le L_{(2)} \le \dots \le L_{(n)}$ be the sorted losses.
The nominal tail observation count is:
$$w = n \cdot (1 - \alpha)$$
1. **Integer or Near-Integer Tail ($w \approx k \in \mathbb{N}$ within $10^{-11}$):**
   - If $k \le 1$: the tail consists of at most 1 observation: $\text{ES} = L_{(n)}$ (the maximum observed loss).
   - If $k > 1$: the tail consists of the $k$ worst losses:
     $$\text{ES}_\alpha = \frac{1}{k} \sum_{i=1}^k L_{(n - k + i)}$$
2. **Fractional Tail ($w = k + \text{frac}$, with $k = \lfloor w \rfloor \ge 1$ and $\text{frac} \in (0, 1)$):**
   - Tail sum combines the $k$ worst losses with a fractional weight on the $(k+1)$-th worst loss:
     $$\text{ES}_\alpha = \frac{1}{w} \left( \sum_{i=1}^k L_{(n - k + i)} + \text{frac} \cdot L_{(n - k)} \right)$$
3. **Small Sample with Tail $< 1.0$ ($w < 1.0$):**
   - When sample size $n$ is small or $\alpha$ is very close to 1.0 (e.g. $n = 5, \alpha = 0.95 \implies w = 0.25$):
     $$\text{ES}_\alpha = L_{(n)}$$
4. **Coherence Guarantee:**
   $$\text{ES}_\alpha \ge \text{VaR}_\alpha$$
   guaranteed by evaluating $\max(\text{ES}_{\text{empirical}}, \text{VaR}_{\alpha})$.

### 1.5 Missing & Non-Finite Observations
- `None`, `NaN`, `+Inf`, and `-Inf` are strictly rejected by `_validate_returns`.
- Risk calculations require a minimum sample size of $N \ge 2$ observations. Empty or singleton series raise `ValueError`.

---

## 2. Risk Attribution Specifications & Methodological Distinctions

FragilityShield's `calculate_portfolio_risk_attribution` in `backend/fragility_engine/attribution.py` computes Euler risk decomposition. It is essential to distinguish between what the engine implements and what it does not:

| Attribution Method | Status in FragilityShield | Formula | Applicable Asset Class |
| :--- | :--- | :--- | :--- |
| **Linear Covariance Beta Decomposition (Component VaR)** | **IMPLEMENTED & VERIFIED** | $\beta_i = \frac{\text{Cov}(R_i, R_p)}{\text{Var}(R_p)}$, $\text{MCR}_i = \beta_i \text{VaR}_p$, $\text{CVaR}_i = w_i \text{MCR}_i$ | Equities, multi-asset linear portfolios |
| **Volatility Covariance Attribution** | **IMPLEMENTED & VERIFIED** | $\frac{\partial \sigma_p}{\partial w_i} = \frac{(\Sigma w)_i}{\sigma_p}$, $\sigma_p = \sum w_i \frac{\partial \sigma_p}{\partial w_i}$ | Gaussian portfolios, tracking error |
| **Historical Empirical Tail Attribution** | **NOT IMPLEMENTED** | $\mathbb{E}[-R_i \mid -R_p \ge \text{VaR}_p]$ | Heavy-tailed nonlinear assets |
| **Cornish-Fisher Skewness/Kurtosis Attribution** | **NOT IMPLEMENTED** | Higher-moment marginal co-skewness / co-kurtosis | Asymmetric hedge funds |

### 2.1 The Euler Homogeneity Property
Because portfolio volatility $\sigma_p(w) = \sqrt{w^\top \Sigma w}$ is a homogeneous function of degree 1 with respect to asset weights $w$:
$$w^\top \nabla \sigma_p(w) = \sigma_p(w)$$
For asset betas:
$$\sum_{i=1}^M w_i \beta_i = \frac{\sum_{i=1}^M w_i \text{Cov}(R_i, R_p)}{\text{Var}(R_p)} = \frac{\text{Cov}(\sum w_i R_i, R_p)}{\text{Var}(R_p)} = \frac{\text{Var}(R_p)}{\text{Var}(R_p)} = 1.0$$
Multiplying by $\text{VaR}_p$:
$$\sum_{i=1}^M \text{ComponentVaR}_i = \sum_{i=1}^M w_i \beta_i \text{VaR}_p = \text{VaR}_p$$

### 2.2 Methodological Disclosure & Limitations
- **Euler reconciliation ($\sum \text{CVaR}_i = \text{VaR}_p$) is an algebraic identity of the linear beta model, NOT proof of exact historical tail attribution.**
- For non-elliptical or heavy-tailed distributions with tail dependence, true quantile sensitivities $\frac{\partial \text{VaR}}{\partial w_i}$ diverge from $\beta_i \text{VaR}_p$.
- FragilityShield explicitly returns `methodology_type = "linear_covariance_beta_component_var"` and includes disclosure warnings in the API response.

---

## 3. Statistical Validation Conventions

### 3.1 Kupiec POF Test
Tests the null hypothesis that empirical breach probability $p$ equals nominal coverage $p_0 = 1 - \alpha$:
$$H_0: p = p_0 \quad \text{vs} \quad H_1: p \ne p_0$$
- **Likelihood Ratio Statistic:**
  $$\text{LR}_{\text{POF}} = -2 \ln \left[ \frac{(1 - p_0)^{n - x} p_0^x}{(1 - \hat{p})^{n - x} \hat{p}^x} \right] \sim \chi^2(1)$$
- **Exact Boundary Solutions:**
  - $x = 0$ (Zero breaches): $\text{LR} = -2 n \ln(1 - p_0)$.
  - $x = n$ (All breaches): $\text{LR} = -2 n \ln(p_0)$.
  - $\hat{p} = p_0$: $\text{LR} = 0.0$.
- **Sample Size Warning ($N < 250$):**
  - Basel committee standard specifies a minimum 250-day backtesting window.
  - The warning emitted when $N < 250$ is **informational**. It notes limited statistical power to reject false models, but does not alter the mathematical calculation of the asymptotic test statistic.
  - **Critical Rule:** Failure to reject $H_0$ (`ACCEPT_NULL`) must NOT be interpreted as proof that a risk model is correct.

### 3.2 Christoffersen Independence Test
Evaluates first-order Markov temporal clustering of breaches:
$$\text{LR}_{\text{ind}} = -2 \ln \left[ \frac{(1 - \pi)^{n_{00} + n_{10}} \pi^{n_{01} + n_{11}}}{(1 - \pi_{01})^{n_{00}} \pi_{01}^{n_{01}} (1 - \pi_{11})^{n_{10}} \pi_{11}^{n_{11}}} \right] \sim \chi^2(1)$$
Combined Conditional Coverage:
$$\text{LR}_{\text{CC}} = \text{LR}_{\text{POF}} + \text{LR}_{\text{ind}} \sim \chi^2(2)$$
Exact p-value for $\chi^2(2)$:
$$p_{\text{CC}} = \exp\left(-\frac{\text{LR}_{\text{CC}}}{2}\right)$$
The test detects both positive clustering (consecutive crisis days) and negative autocorrelation (alternating breach days).
