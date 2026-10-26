# FragilityShield — Quantitative Specification & Mathematical Models (Phase 4)

**Date:** 2026-10-25  
**Auditing Authority:** Independent Quantitative Finance & Model Validation Team  
**Standard:** Rigorous Mathematical Formulation of All Risk, Attribution, Optimization, and Evaluation Engines

---

## 1. Core Risk Measures & Statistical Formulations

### A. Return Definitions & Sign Convention
- Arithmetic Simple Return: $R_t = \frac{P_t - P_{t-1}}{P_{t-1}}$.
- Loss Convention: Value-at-Risk ($VaR$) and Expected Shortfall ($ES$) report loss magnitudes as **positive quantities**:
  $$L_t = -R_t$$
  A $95\%$ 1-day $VaR$ of $0.025$ means a $5\%$ probability of experiencing a loss $\ge 2.5\%$.

### B. Historical Value-at-Risk ($VaR_{hist}$)
Given sample returns $R_{(1)} \le R_{(2)} \le \dots \le R_{(T)}$, historical VaR at confidence level $\alpha \in (0, 1)$ is the negative of the empirical $(1-\alpha)$ quantile:
$$VaR_{hist, \alpha} = - Q_{1-\alpha}(R)$$

### C. Parametric Gaussian VaR ($VaR_{norm}$)
Assuming $R_t \sim \mathcal{N}(\mu, \sigma^2)$:
$$VaR_{norm, \alpha} = - (\mu + z_{1-\alpha} \sigma)$$
where $\mu = \frac{1}{T}\sum R_t$, $\sigma = \sqrt{\frac{1}{T-1}\sum (R_t - \mu)^2}$, and $z_{1-\alpha} = \Phi^{-1}(1-\alpha)$.

### D. Cornish-Fisher Expansion VaR ($VaR_{CF}$)
Adjusts the Gaussian quantile $z = \Phi^{-1}(1-\alpha)$ for empirical skewness $S$ and excess kurtosis $K$:
$$z_{CF} = z + \frac{1}{6}(z^2-1)S + \frac{1}{24}(z^3-3z)K - \frac{1}{36}(2z^3-5z)S^2$$
$$VaR_{CF, \alpha} = - (\mu + z_{CF} \sigma)$$

### E. Coherent Expected Shortfall (Acerbi & Tasche 2002)
For sorted losses $L_{(1)} \le L_{(2)} \le \dots \le L_{(T)}$ with tail probability $p = 1 - \alpha$ and nominal count $w = T \cdot p$:
- If $w \le 1.0$: $ES_\alpha = L_{(T)}$ (worst loss).
- If $w$ is within machine epsilon of an integer $k$:
  $$ES_\alpha = \frac{1}{k} \sum_{j=0}^{k-1} L_{(T-j)}$$
- If $w$ is genuinely fractional with $k = \lfloor w \rfloor$ and $frac = w - k$:
  $$ES_\alpha = \frac{1}{w} \left( \sum_{j=0}^{k-1} L_{(T-j)} + frac \cdot L_{(T-k)} \right)$$
- Coherence guarantee: $ES_\alpha \ge VaR_\alpha$ strictly holds.

### F. Maximum Drawdown & Durations
Given wealth curve $W_t = \prod_{s=1}^t (1 + R_s)$ and running peak $M_t = \max_{s \le t} W_s$:
$$\text{Drawdown}_t = \frac{M_t - W_t}{M_t} \in [0, 1]$$
$$\text{MaxDrawdown} = \max_{0 \le t \le T} \text{Drawdown}_t$$
Peak-to-trough duration is the number of trading periods between the peak and trough.

---

## 2. Portfolio Risk Attribution & Euler Homogeneity

### Homogeneous Decomposition Theorem
For a positive homogeneous risk measure $\rho(c \cdot w) = c \cdot \rho(w)$ for $c > 0$:
$$\rho(w) = \sum_{i=1}^N w_i \frac{\partial \rho(w)}{\partial w_i}$$
Definitions:
- Marginal VaR: $MVaR_i = \frac{\partial \rho(w)}{\partial w_i}$
- Component VaR: $CVaR_i = w_i \cdot MVaR_i$
- Reconciliation Identity: $\sum_{i=1}^N CVaR_i \equiv \rho(w)$

For portfolio variance $\sigma_p^2 = w^T \Sigma w$, total portfolio volatility is $\sigma_p = \sqrt{w^T \Sigma w}$. The marginal volatility vector is:
$$\nabla_w \sigma_p = \frac{\Sigma w}{\sigma_p}$$
Component volatility for asset $i$:
$$C_i = w_i \frac{(\Sigma w)_i}{\sigma_p} \implies \sum_{i=1}^N C_i = \frac{w^T \Sigma w}{\sigma_p} = \sigma_p$$

---

## 3. Reverse Stress Testing & Boundary Search

### Euler Loss Equation Solver
To find the required market shock $s^*$ to inflict target capital loss fraction $L^*$:
$$\Delta V(s) = \sum_{i=1}^N w_i s_i = s \implies s^* = -L^*$$
For sector-targeted shock on sector $sec$:
$$s_{sec}^* = -\frac{L^*}{\sum_{i \in sec} w_i}$$

### Bracketing Parameter Search
Given target metric function $f(\theta)$ and failure threshold $\theta^*$, the secant/bisection search solves:
$$f(\theta) - \theta^* = 0$$
within interval $[\theta_{min}, \theta_{max}]$ under convergence tolerance $\epsilon = 10^{-6}$.

---

## 4. Backtesting Statistical Coverage Tests

### Kupiec POF Unconditional Coverage Test
For $N$ breaches observed in $T$ out-of-sample periods under coverage rate $p_0 = 1 - \alpha$:
$$LR_{POF} = -2 \ln \left[ \frac{(1-p_0)^{T-N} p_0^N}{\left(1 - \frac{N}{T}\right)^{T-N} \left(\frac{N}{T}\right)^N} \right] \sim \chi^2_1$$

### Christoffersen Independence Test
Evaluates breach clustering via transition counts $n_{00}, n_{01}, n_{10}, n_{11}$:
$$LR_{ind} = -2 \ln \left[ \frac{\pi^{n_{01}+n_{11}}(1-\pi)^{n_{00}+n_{10}}}{\pi_{01}^{n_{01}}(1-\pi_{01})^{n_{00}} \pi_{11}^{n_{11}}(1-\pi_{11})^{n_{10}}} \right] \sim \chi^2_1$$

---

## 5. Quantitative Allocation & Optimization

$$\min_w \frac{1}{2} w^T \Sigma w \quad \text{subject to} \quad \sum_{i=1}^N w_i = 1.0, \quad w_{min} \le w_i \le w_{max}$$
Turnover between portfolio $w_0$ and $w_1$:
$$\text{Turnover} = \frac{1}{2} \sum_{i=1}^N |w_{1,i} - w_{0,i}|$$
Transaction friction cost:
$$\text{Cost} = \text{Turnover} \times \text{cost\_bps} \times 10^{-4}$$

---

## 6. Machine Learning Evaluation & Zero Leakage

### Chronological Train/Test Split
$$\text{split\_idx} = \lfloor N \cdot \text{train\_ratio} \rfloor$$
$$\max(\text{train\_indices}) < \min(\text{test\_indices})$$
Shuffling is prohibited to prevent forward lookahead leakage in financial time series.
- Regression Metrics: $\text{MAE} = \frac{1}{N}\sum |y_i - \hat{y}_i|$, $\text{RMSE} = \sqrt{\frac{1}{N}\sum (y_i - \hat{y}_i)^2}$, $R^2 = 1 - \frac{\sum (y_i - \hat{y}_i)^2}{\sum (y_i - \bar{y})^2}$.
- Classification Metrics: Accuracy, Precision, Recall, F1, ROC-AUC, Brier score.
- Forecasting: $\text{MASE} = \frac{\frac{1}{N}\sum |y_t - \hat{y}_t|}{\frac{1}{T-1}\sum_{i=2}^T |y_{naive, i} - y_{naive, i-1}|}$.
