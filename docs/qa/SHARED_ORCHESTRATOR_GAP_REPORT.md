# FragilityShield Shared Pipeline & Orchestrator — Gap Report

## 1. Objective

This document audits the quantitative capabilities, module boundaries, data constraints, and current limitations of the FragilityShield test orchestrator to ensure complete honesty in institutional reporting without fabricating results.

---

## 2. Quantitative Engine Capabilities & Data Requirements

| Module | Implementation Status | Input Requirements | Failure Mode When Input Unsatisfied |
| :--- | :--- | :--- | :--- |
| **`data_diagnostics`** | Fully Implemented | Returns series ($N \ge 8$) | Marks `UNSUPPORTED` if $N < 8$; calculates ADF, Ljung-Box, Jarque-Bera. |
| **`risk_analytics`** | Fully Implemented | Returns series ($N \ge 5$) | Marks `UNSUPPORTED` if $N < 5$; calculates Parametric/Historical VaR, CVaR, Vol, Sharpe, Max Drawdown. |
| **`scenario_stress`** | Fully Implemented | Returns series ($N \ge 5$) | Applies deterministic macro shocks (-28% COVID, -35% Lehman, Vol spike). |
| **`tail_risk_reverse_stress`**| Fully Implemented | Returns series ($N \ge 20$) | Marks `FAILED` if negative tail samples $< 15$ with structured explanation; calculates Hill index and breach sigma. |
| **`fragility_assumption_matrix`** | Fully Implemented | Returns series ($N \ge 5$) | Sweeps slippage (0-25 bps) and friction costs (5-20 bps); measures alpha decay. |
| **`monte_carlo_simulation`** | Fully Implemented | Returns series ($N \ge 10$) | Simulates 1,000 geometric paths; computes ruin probability (<80% capital) and quantiles. |
| **`bootstrap_uncertainty`** | Fully Implemented | Returns series ($N \ge 15$) | Executes 500 block resamples; computes 95% confidence intervals. |
| **`model_validation`** | Fully Implemented | `ExperimentType.MODEL` or `FORECASTING` | Marks `UNSUPPORTED` if run is a pure portfolio without model predictions; computes KS test and Kupiec POF. |
| **`strategy_backtesting`** | Fully Implemented | `ExperimentType.STRATEGY` with entry/exit signals | Marks `UNSUPPORTED` if run is a model or portfolio without strategy execution rules. |

---

## 3. Explicitly Handled Gaps & Non-Fabrication Rules

1. **Unsupported Strategy Backtesting for Models**:
   - *Behavior*: When an ML volatility or directional model is submitted without explicit trading order rules, `strategy_backtesting` is marked `UNSUPPORTED` with diagnostic: `"Module requires strategy definition with signal generation rules."`
   - *Significance*: Prevents attributing fabricated Sharpe or Calmar ratios to raw predictive algorithms.

2. **Tail Sample Scarcity in EVT**:
   - *Behavior*: If fewer than 15 negative tail observations exist in the return series, `tail_risk_reverse_stress` fails honestly with: `"Insufficient negative tail samples (N) for EVT analysis."`
   - *Significance*: Eliminates spurious Hill index estimates that would misrepresent extreme tail thickness.

3. **Multi-Asset Covariance Stress Testing**:
   - *Current State*: The orchestrator currently stresses composite portfolio return vectors and single-asset strategies. Cross-asset dynamic correlation breakdown (DCC-GARCH) under systemic liquidity freezing is scheduled for the next release.

4. **Colab / Remote Networking Latency**:
   - *Current State*: External Colab submissions interact over HTTPS (via Localtunnel or cloud endpoints). Tunnels may experience occasional disconnects if left idle. Retries are implemented idempotently using run ID de-duplication.
