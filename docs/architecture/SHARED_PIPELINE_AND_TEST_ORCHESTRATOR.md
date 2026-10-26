# FragilityShield Shared Data Pipeline & Test Orchestrator Architecture

## 1. Executive Summary

FragilityShield is an institutional-grade model validation, portfolio risk, stress testing, and robustness-testing quantitative laboratory. This document describes the unified architecture connecting external experiment submissions (via Python SDK, Google Colab, and REST APIs), a canonical experiment-run data contract, a modular shared test orchestrator, and real-time dashboard ledger propagation.

```
                      ┌───────────────────────────────────────────────┐
                      │    External Submissions & User Workflows      │
                      │  - Google Colab GPU / CPU Notebooks           │
                      │  - Python Scripts (FragilityShield SDK)       │
                      │  - REST API Ingestion Clients                 │
                      │  - Internal UI (Unified Experiment Registry)  │
                      └───────────────────────┬───────────────────────┘
                                              │ HTTP / JSON Payload
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │     Ingestion & Security Gateway Layer        │
                      │  - Bearer Token Auth / Tenant Boundary Guard  │
                      │  - Declarative Schema Validation (Zero eval)  │
                      │  - Dataset References & Provenance Tracking   │
                      └───────────────────────┬───────────────────────┘
                                              │
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │      Shared Test Orchestrator Engine          │
                      │  (Applicability Resolution & Profile Filter)  │
                      └───────┬───────────────┬───────────────┬───────┘
                              │               │               │
      ┌───────────────────────┼───────────────┼───────────────┼───────────────────────┐
      ▼                       ▼               ▼               ▼                       ▼
┌──────────────┐      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      ┌──────────────┐
│     Data     │      │     Risk     │ │   Scenario   │ │  Tail Risk   │      │    Model     │
│ Diagnostics  │      │  Analytics   │ │ Stress Lab   │ │  EVT Reverse │ ...  │  Validation  │
│ (Stationary) │      │ (VaR / CVaR) │ │ (Macro / Hist│ │ (Hill Index) │      │ (KS, Kupiec) │
└──────┬───────┘      └──────┬───────┘ └──────┬───────┘ └──────┬───────┘      └──────┬───────┘
       └───────────────────────┼───────────────┼───────────────┼──────────────────────┘
                               │ CanonicalTestResult Dict
                               ▼
                      ┌───────────────────────────────────────────────┐
                      │     Canonical Experiment Run Record           │
                      │  - Immutable SHA-256 Provenance Checksum      │
                      │  - Run Status: completed / partial / failed   │
                      │  - Metric Provenance Tracking                 │
                      └───────────────────────┬───────────────────────┘
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      │                                               │
                      ▼                                               ▼
       ┌─────────────────────────────┐                 ┌─────────────────────────────┐
       │   Persistence Repository    │                 │  Unified Experiment Ledger  │
       │ SQLite / In-Memory MemoryDB │                 │     All Dashboard Pages     │
       └─────────────────────────────┘                 └─────────────────────────────┘
```

---

## 2. Canonical Experiment Data Contract

The data contract (`backend/fragility_engine/orchestrator.py`) provides an institutional schema guaranteeing that no test result is fabricated, metrics are mathematically verified, and provenance is tamper-evident.

### 2.1 Enums and Identifiers
- **`SubmissionSource`**: `local_sdk`, `google_colab`, `external_api`, `internal_ui`, `automated_ci`.
- **`ExperimentType`**: `model`, `strategy`, `forecasting`, `portfolio`, `generic`.
- **`TestStatus`**: `pending`, `running`, `passed`, `failed`, `skipped`, `unsupported`.
- **`RunStatus`**: `queued`, `running`, `completed`, `partially_completed`, `failed`.
- **`MetricProvenance`**: `self_reported`, `independently_recalculated`, `derived`.

### 2.2 Core Schema Classes

```python
@dataclass
class CanonicalMetric:
    metric_name: str
    observed_value: float
    unit: str = "ratio"
    calculation_method: str = "standard"
    evaluation_period: str = "full_sample"
    provenance: MetricProvenance = MetricProvenance.INDEPENDENTLY_RECALCULATED
    confidence_interval: Optional[Tuple[float, float]] = None

@dataclass
class CanonicalTestResult:
    module_id: str
    module_name: str
    status: TestStatus
    summary_metric: str
    metrics: Dict[str, CanonicalMetric] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    diagnostics: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    version: str = "1.0.0"

@dataclass
class CanonicalExperimentRun:
    experiment_id: str
    run_id: str
    submission_source: SubmissionSource
    experiment_type: ExperimentType
    display_name: str
    status: RunStatus
    test_results: Dict[str, CanonicalTestResult]
    summary_metrics: Dict[str, Any]
    target_identity: Dict[str, Any]
    data_inputs: Dict[str, Any]
    dataset_references: List[Dict[str, Any]]
    config_overrides: Dict[str, Any]
    provenance_hash: str
```

### 2.3 SHA-256 Provenance Checksum
Every experiment run computes an immutable SHA-256 hash across `experiment_id`, `run_id`, `experiment_type`, `submission_source`, and input keys, sealing data integrity.

---

## 3. Shared Test Orchestrator Engine

The `SharedTestOrchestrator` governs the quantitative execution pipeline, executing 9 institutional testing engines:

| Module ID | Module Name | Quantitative Focus | Supported Types |
| :--- | :--- | :--- | :--- |
| `data_diagnostics` | Data Diagnostics Observatory | Stationarity (ADF), Autocorrelation (Ljung-Box), Normality (Jarque-Bera) | All types |
| `risk_analytics` | Parametric & Historical Risk Engine | VaR 95/99%, Expected Shortfall (CVaR), Annualized Vol, Sharpe, Max Drawdown | All types |
| `scenario_stress` | Macro & Historical Scenario Lab | COVID-19 Crash (-28%), Lehman 2008 (-35%), Vol Spike (+150%) | All types |
| `tail_risk_reverse_stress` | EVT & Reverse Stress Search | Hill Power-Law Tail Index, Distance to 20% Capital Breach ($\sigma$) | All types |
| `fragility_assumption_matrix` | Fragility Assumption Matrix | Sensitivity to Slippage (0-25 bps), Friction Costs, Alpha Erosion | All types |
| `monte_carlo_simulation` | Monte Carlo Path Simulation | 1,000 Geometric Brownian Motion Trajectories, Terminal Quantiles, Ruin Prob | All types |
| `bootstrap_uncertainty` | Stationary Bootstrap Engine | 500 Block Resamples, 95% Confidence Intervals for Vol & Sharpe | All types |
| `model_validation` | Model Validation & Calibration Lab | Kolmogorov-Smirnov Distribution Goodness-of-Fit, Kupiec POF VaR Exceptions | `model`, `forecasting` |
| `strategy_backtesting` | Quantitative Strategy Backtester | Walk-forward signal execution, trade accounting, turnover | `strategy` only |

### 3.1 Applicability Resolution & Zero-Fabrication Guarantee
Before any module executes, `resolve_applicable_tests` checks:
1. **Experiment Type**: A pure ML model without strategy buy/sell rules will mark `strategy_backtesting` as `UNSUPPORTED` (never `PASSED`).
2. **Input Dimensions**: Modules requiring 20+ return samples fail gracefully with informative diagnostics if data is truncated.
3. **Execution Mode**:
   - **Test All**: Runs all registered modules compatible with the input.
   - **Custom Test Profile**: Executes only user-selected modules with custom parameters.

---

## 4. Security & Isolation Architecture

1. **Zero Dynamic Evaluation**: No user-submitted Python strings, arbitrary notebooks, or serialized pickle files are ever executed using `eval()` or `exec()`.
2. **Declarative Configuration Schemas**: Strategies, Scenarios, and Test Profiles are parsed via strict declarative dataclass schemas (`custom_configs.py`) with type validation and bound checks.
3. **Tenant Boundary Enforcement**: Submissions validate workspace ID, API keys, and model access rights before persistence.
4. **Colab / Local Remote Networking**: Colab notebooks interact with the platform strictly via clean authenticated HTTPS REST calls over tunnels or domain hosts, without requiring local filesystem mounts.
