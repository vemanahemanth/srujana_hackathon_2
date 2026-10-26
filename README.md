# FragilityShield

> **Open-Source Financial & ML Model Testing Laboratory**  
> *"How much should we trust a model's outputs when its assumptions, inputs, data quality, parameters, and operating conditions are challenged?"*

FragilityShield is an empirical stress-testing, validation, and fragility laboratory for financial portfolios and quantitative models. It provides a standardized environment to measure how sensitive outputs are to parameter shifts, data anomalies, and market shocks.

---

## Important Disclaimers

FragilityShield is **not** an investment advice platform, automated trading bot, or profitability guarantee system. All metrics, scenario analyses, and fragility audits are for research, educational, and model-validation purposes only.

---

## Architecture Overview

- **`backend/fragility_engine/`**: Pure, framework-agnostic Python quantitative calculation engine (`models.py`, `returns.py`, `risk.py`, `attribution.py`, `scenarios.py`, `fragility.py`, `allocation.py`, `validation.py`, `ml.py`, `market_data.py`, `plugins.py`, `benchmarks.py`, `backtest.py`, `data_diagnostics.py`, `simulation.py`, `assumptions.py`, `studio.py`, `reproducibility.py`, `sdk.py`, `cli.py`).
- **`backend/app.py`**: Starlette / FastAPI asynchronous REST API serving domain endpoints, background job worker, artifact storage, and static application assets from `frontend/dist`.
- **`frontend/`**: Canonical quantitative research terminal built with React 19, TypeScript, Vite, Tailwind CSS, Lucide icons, and Recharts. Connects to real FastAPI endpoints for portfolio risk, scenario stress testing, fragility audits, async job execution, and artifact downloads.
- **`backend/tests/`**: Comprehensive automated test suite with 701 tests spanning quantitative correctness, multi-tenancy RLS, worker isolation, and frontend integration.
- **`legacy_frontend_backup/`**: Preserved backup of original vanilla HTML/JS assets before replacement.
- **`data/sample_portfolios/`**: Illustrative test fixtures, including the ₹10 Lakh NSE sample portfolio (`nse_10l.json`, `nse_10l.csv`).
- **`data/experiments/`**: Local catalog storage for reproducible studio experiment reports.
- **`docs/`**: Authoritative requirements and architecture documentation:
  - [`docs/production/SPRINT_6_FRONTEND_REPLACEMENT_BASELINE.md`](docs/production/SPRINT_6_FRONTEND_REPLACEMENT_BASELINE.md): Frontend replacement baseline, discovery, and migration plan.
  - [`docs/production/SPRINT_6_API_INTEGRATION_MAP.md`](docs/production/SPRINT_6_API_INTEGRATION_MAP.md): API contract, endpoint schemas, and frontend integration mapping.
  - [`docs/production/SPRINT_6_IMPLEMENTATION_REPORT.md`](docs/production/SPRINT_6_IMPLEMENTATION_REPORT.md): Verified outcome of frontend replacement and safe backend integration.
  - [`docs/blueprint-requirements-matrix.md`](docs/blueprint-requirements-matrix.md): 100% verified traceability matrix for all requirements.
  - [`docs/backend-architecture.md`](docs/backend-architecture.md): Canonical reference architecture and layer contracts.
  - [`docs/backend-implementation-status.md`](docs/backend-implementation-status.md): Complete section-by-section audit and implementation status.

---

## Local Setup & Application Launch

### 1. Requirements
- Python 3.10+ (tested on Python 3.12 / 3.14)
- Node.js 18+ and npm
- Git

### 2. Environment Setup
```bash
# Clone and enter the repository
cd srujana_hackathon_2

# Create a local virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the engine and API dependencies in editable mode
pip install -e backend

# Install frontend dependencies
cd frontend && npm install && cd ..
```

### 3. Launch the Application

There are two primary ways to run FragilityShield:

#### Mode A: Production Single-Process Mode (FastAPI serves compiled frontend)
```bash
# 1. Build the production React frontend bundle
cd frontend && npm run build && cd ..

# 2. Launch the backend API (automatically mounts frontend/dist at /)
python -m backend.app
# Or via uvicorn:
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
Open your browser to: **`http://127.0.0.1:8000`**

#### Mode B: Active Development Mode (Vite Dev Server with Proxy)
```bash
# Terminal 1: Start backend API
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Start Vite React Dev Server
cd frontend
npm run dev
```
Open your browser to: **`http://localhost:5173`** (Vite proxies all `/api/*` calls directly to `http://127.0.0.1:8000`).

### 4. Run Automated Tests
```bash
# Frontend typecheck & production build verification
cd frontend && npm run typecheck && npm run build && cd ..

# Backend regression and integration test suite (701 passed)
pytest backend/tests/ -q
```

---

## Python SDK & Command Line Interface

### Python SDK Quickstart
All laboratory services can be programmatically controlled using the typed `Client`:

```python
from fragility_engine import Client, Holding

client = Client()

# Ingest a portfolio
portfolio = client.portfolios.create(
    portfolio_id="nse_core",
    name="Institutional Alpha Portfolio",
    currency="INR",
    holdings=[
        Holding("INFY", 100.0, 1500.0, "Information Technology"),
        Holding("HDFCBANK", 200.0, 1600.0, "Banking"),
        Holding("RELIANCE", 100.0, 2500.0, "Energy"),
    ],
)

# Compute coherent tail risk metrics (Loss convention L = -R, Acerbi-Tasche ES >= VaR)
returns = client.market_data.offline_sample_provider().get_returns("INFY")
risk = client.risk.calculate(returns)
print(f"Annualized Volatility: {risk.volatility_annualized:.2%}")
print(f"95% Value-at-Risk:    {risk.var_95:.2%}")
print(f"95% Expected Shortfall: {risk.expected_shortfall_95:.2%}")

# Execute stress scenario with exact P&L reconciliation
result = client.scenarios.execute(
    portfolio=portfolio,
    sector_shocks={"Information Technology": 0.05, "Banking": -0.15},
)
print(f"Stressed Portfolio P&L: ₹{result.total_pnl:,.2f}")

# Execute 5-attack fragility audit with sensitivity rankings
audit = client.fragility.run_audit(returns)
print(f"Top Sensitive Assumption: {audit.sensitivity_ranking.most_sensitive_perturbation}")

# Optimize portfolio via minimum-variance quadratic programming
cov_matrix = client.risk.covariance_matrix(
    [client.market_data.offline_sample_provider().get_returns(a) for a in ["INFY", "HDFCBANK", "RELIANCE"]]
)
alloc = client.allocation.optimize_minimum_variance(cov_matrix, ["INFY", "HDFCBANK", "RELIANCE"])
print(f"Optimal Weights: {alloc.weights}")
```

### CLI Quickstart
Execute research tasks directly from the terminal:

```bash
# Calculate portfolio risk
.venv/bin/python -m fragility_engine.cli risk --returns 0.01,-0.015,0.02,-0.025,0.005

# Run fragility assumption audit
.venv/bin/python -m fragility_engine.cli fragility --returns 0.01,-0.015,0.02,-0.025,0.005

# Run analytical reference-value validation suite
.venv/bin/python -m fragility_engine.cli validation

# List registered risk model plugins
.venv/bin/python -m fragility_engine.cli plugins

# Calculate statutory Indian trade charges (STT, GST, SEBI fee, Stamp Duty)
.venv/bin/python -m fragility_engine.cli charges --price 2500.0 --quantity 100 --order-type delivery
```

---

## Interactive Application & Research Workspace

FragilityShield provides an assumption-aware research laboratory accessible via a modern web interface.

### The 12 Comprehensive Research Laboratories
1. **Overview**: Live summary of portfolio valuation, position counts, concentration indicators, baseline volatility/VaR KPIs, scenario loss metrics, and model ranking highlights.
2. **Portfolio Lab**: Multi-asset portfolio creation and validation. Supports loading bundled ₹10L NSE JSON and CSV fixtures (`data/sample_portfolios/`) or pasting custom JSON/CSV. Calculates Herfindahl-Hirschman Index (decimal and points) across assets and sectors with SVG donut charts.
3. **Data Diagnostics Lab**: Evaluates empirical return distribution properties before model selection. Calculates sample skewness, excess kurtosis, Jarque-Bera normality test with exact $\chi^2$ p-values, lag-1 autocorrelation ($\rho_1$), zero-return frequency, SVG return distribution histogram, and automated model suitability verdicts.
4. **Risk & Attribution**: Calculates Annualized Volatility, Value-at-Risk (95% & 99%), Expected Shortfall (CVaR), and Maximum Drawdown with dual-axis Equity Curve / Drawdown charts. Features an **Euler Marginal Risk Allocation & Component VaR table** ($CVaR_i = w_i \cdot \beta_i \cdot VaR_p$) proving exact mathematical reconciliation ($\sum CVaR_i = VaR_p$) under Euler's homogeneous degree 1 theorem.
5. **Simulation & Uncertainty**: Dual-engine uncertainty exploration:
   - **Forward Monte Carlo Simulation**: Multi-path simulations (Gaussian or Student-t fat-tailed innovations) generating 5th, 50th, and 95th percentile envelope paths and terminal loss distributions.
   - **Non-Parametric Bootstrap Uncertainty**: Resamples return histories to generate 90% and 95% confidence intervals for VaR and ES, revealing sample-size sensitivity.
6. **Scenario Lab**: Instantaneous factor and sector stress scenarios (e.g. Banking -20%, IT -10%). Performs full P&L reconciliation with sector attribution breakdown and explicit disclaimers regarding static sensitivity versus forecasting.
7. **Fragility Lab (Central Differentiator)**: Investigates how risk estimates change when assumptions change. Executes perturbation attacks on historical lookback windows (20d vs 60d), volatility estimators (Sample StdDev vs RiskMetrics EWMA $\lambda=0.94$), transaction friction (10 bps drag), tail confidence shifts (95% vs 99%), and portfolio liquidation costs. Renders sensitivity tornado rankings to identify dominant model sensitivities.
8. **Assumption Registry**: Centralized catalog documenting the mathematical formulations, distributional assumptions, temporal dynamics, preconditions, known failure regimes, and fragility vulnerabilities for parametric, non-parametric, conditional volatility, and heavy-tailed models.
9. **Custom Model Builder**: Allows researchers to interactively configure and register custom quantitative risk models (e.g. Student-t with specific degrees of freedom, EWMA with custom decay, Cornish-Fisher expansion, historical quantiles). Registered models dynamically integrate into the shared engine registry for benchmarking and backtesting.
10. **Model Benchmarking**: Multi-model comparative laboratory evaluating registered plugins (`parametric_gaussian`, `historical_simulation`, `ewma`, plus any registered custom models). Enforces Phase 8.1 ranking semantics ("A lower estimated VaR is not automatically a better risk model").
11. **VaR Backtesting**: Rolling walk-forward evaluation aligning 1-step-ahead forecasts with realized returns without look-ahead contamination. Features breach timeline visualization, Kupiec POF test, and Christoffersen independence and conditional coverage tests.
12. **Experiments & Reports**: Catalog of executed experiments, SHA-256 cryptographic reproducibility manifests, and formatted export to Markdown, JSON, and CSV.

### REST API Endpoints

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Engine version, status, registered models, and capabilities |
| `GET` | `/api/portfolios/sample?id=...` | Load bundled sample portfolio fixtures |
| `POST` | `/api/portfolios/validate` | Validate user-uploaded portfolio JSON/CSV |
| `POST` | `/api/portfolios/concentration` | Calculate asset and sector HHI concentration |
| `POST` | `/api/data/diagnostics` | Compute skewness, kurtosis, Jarque-Bera normality, and suitability |
| `POST` | `/api/risk/calculate` | Compute volatility, VaR, ES, and equity curve |
| `POST` | `/api/risk/attribution` | Calculate Euler Marginal Risk Allocation and Component VaR |
| `POST` | `/api/simulation/monte-carlo` | Multi-path forward Monte Carlo envelope simulation |
| `POST` | `/api/simulation/bootstrap` | Non-parametric bootstrap confidence intervals for VaR/ES |
| `GET` | `/api/assumptions/catalog` | Catalog of model assumptions, failure regimes, and vulnerabilities |
| `POST` | `/api/models/register` | Register user-configured custom quantitative model plugin |
| `POST` | `/api/scenarios/execute` | Run stress scenario with P&L reconciliation |
| `POST` | `/api/fragility/run` | Execute assumption perturbation attacks and sensitivity ranking |
| `GET` | `/api/benchmarks/models` | List registered quantitative model plugins |
| `POST` | `/api/benchmarks/execute` | Execute comparative model benchmark evaluation |
| `POST` | `/api/backtest/run` | Run rolling walk-forward backtest with Kupiec/Christoffersen tests |
| `GET` | `/api/studio/catalog` | Retrieve saved experiment catalog |
| `POST` | `/api/studio/experiment` | Execute and catalog unified studio experiment |
| `POST` | `/api/export` | Export reports as JSON, Markdown, or CSV |

---

## Out-of-Sample VaR Backtesting & Statistical Validation (Phase 8.2)

Located in `backend/fragility_engine/backtest.py`:
- **Quantitative Forecast Integrity**: Formally establishes forecast origin times ($t$), information sets ($\mathcal{F}_t$), forecast horizons ($h=1$), and realized outcome targets ($t+1$).
- **Elimination of Look-Ahead Bias**:
  - `BenchmarkSpecification` and `BenchmarkReport` encode `evaluation_mode: str = "in_sample_descriptive"` to explicitly differentiate fitted in-sample calculations from predictive forecasts.
  - EWMA volatility recurrence supports explicit, causal `initial_variance` and sequential variance evaluation (`calculate_ewma_conditional_variances`) guaranteeing that future returns $R_{t+1 \dots T}$ cannot alter historical variance estimates $\sigma_0^2 \dots \sigma_t^2$.
- **Canonical Loss and Breach Convention**:
  - Loss defined as $L_{t+1} = -R_{t+1}$.
  - Strict breach indicator: $I_{t+1} = \mathbf{1}[L_{t+1} > \text{VaR}_{\alpha, t}]$, with equality ($L == \text{VaR}$) treated strictly as non-breach.
- **Kupiec Unconditional Coverage Test (POF)**:
  - Exact likelihood ratio test statistic: $LR_{POF} = 2 [ x \ln(\widehat{p} / p_0) + (N - x) \ln((1 - \widehat{p}) / (1 - p_0)) ] \sim \chi^2_1$.
  - Exact survival p-value via `math.erfc(math.sqrt(LR / 2.0))`.
  - Boundary handling for $x=0$ ($LR = -2 N \ln(1 - p_0)$) and $x=N$ ($LR = -2 N \ln(p_0)$) preventing numerical division-by-zero or $\ln(0)$ crashes.
- **Christoffersen Independence & Conditional Coverage Tests**:
  - Evaluates first-order Markov chain transitions ($n_{00}, n_{01}, n_{10}, n_{11}$) to detect breach clustering ($LR_{ind} \sim \chi^2_1$).
  - Combined Conditional Coverage: $LR_{CC} = LR_{POF} + LR_{ind} \sim \chi^2_2$, with exact closed-form p-value $\exp(-LR_{CC} / 2.0)$.
- **Automated Rolling Walk-Forward Backtester (`backtest_model_rolling`)**:
  - Automatically executes rolling out-of-sample backtests across registered model plugins.
  - Trains exclusively on $[t - W + 1 : t + 1]$, forecasts $t+1$, evaluates against $-R_{t+1}$, and outputs `BacktestReport` with full cryptographic SHA-256 manifest.

---

## Model Plugin System & Benchmarking Laboratory (Phase 8 & Phase 8.1)

Located in `backend/fragility_engine/plugins.py` and `backend/fragility_engine/benchmarks.py`:
- **Product Goal**: An assumption-aware quantitative model benchmarking laboratory and typed plugin architecture. Allows researchers and risk managers to evaluate competing financial risk models, test sensitivity to assumptions, validate outputs, and rank models under identical market data and shock conditions.

### Key Capabilities

1. **Typed Model Plugin Contract (`ModelPlugin`)**:
   - Clean, decoupled abstract protocol requiring three methods:
     - `@property metadata -> PluginMetadata`: Stable identifier, version, supported data types, capabilities, and explicit limitations.
     - `validate_input(data, config) -> None`: Pre-execution validation screening for non-finite values, empty datasets, invalid dimensions, and out-of-bounds parameters.
     - `execute(data, config) -> ModelExecutionResult`: Computes verified metrics, execution timing in milliseconds, observation counts, and diagnostic warnings.
   - Built-in adapters directly reuse the core engine without algorithm duplication:
     - `builtin.historical_simulation`: Empirical historical VaR, coherent Expected Shortfall (Acerbi-Tasche), annualized volatility, and drawdown dynamics.
     - `builtin.parametric_gaussian`: Theoretical analytical Gaussian benchmark ($\text{VaR}_\alpha = -\mu + z_\alpha \sigma$, $\text{ES}_\alpha = -\mu + \sigma \frac{\phi(z_\alpha)}{1 - \alpha}$).
     - `builtin.ewma`: RiskMetrics Exponentially Weighted Moving Average volatility with decay factor $\lambda$.
     - `builtin.portfolio_concentration`: Herfindahl-Hirschman Indices (decimal and points) and total portfolio valuation.

2. **In-Process Plugin Registry (`PluginRegistry`)**:
   - Deterministic plugin registration, safe unregistration, lookup, and capability filtering.
   - Rejects duplicate identifiers and unsafe path traversal characters.
   - Pre-loaded default registry accessible via `get_default_registry()`.

3. **Deterministic Model Benchmarking (`execute_model_benchmark`)**:
   - **Fair Comparison Guarantee**: Compares models evaluated on identical sample windows and baseline configurations. Incompatible models (e.g. Portfolio models applied to Return Series) are isolated with `incompatible` status.
   - **Robustness Perturbation Testing**: Runs models through parameter shocks (return friction drag, lookback window alterations, decay factor shifts) and records baseline vs perturbed metric deltas.
   - **Post-Execution Invariant Verification**: Verifies mathematical properties across all outputs via `verify_experiment_invariants`.
   - **Directional Risk Rankings & Semantics**: Transparent ranking supporting `lower_is_better` and `higher_is_better`.
     - **Risk Magnitude vs Model Quality**: Lower estimated Value-at-Risk or Volatility reflects a lower risk estimate on the sample data, **not** a superior, more robust, or better-calibrated risk model. Model forecast accuracy requires out-of-sample backtesting against realized outcomes.
     - **Deterministic Tie Handling**: Detects and reports numerical ties within configurable tolerance $\epsilon$ (default $10^{-6}$).
     - **Explicit Measurement Units & Interpretations**: Every ranking records `unit` (e.g. `'decimal fraction'`, `'points (0-10000)'`, `'currency'`) and `interpretation` (e.g. `'lower_estimated_risk'`).
     - **Exclusion of Incomparable Models**: Incompatible models (e.g. evaluating portfolio concentration on return series) and failed plugins are explicitly excluded from rankings with recorded diagnostic reasons.
   - **Fault Isolation**: Caught exceptions in plugins are captured without crashing the benchmark or corrupting valid results.

4. **Multi-Format Publication Reports (`BenchmarkReport`)**:
   - **JSON (`.to_json()`)**: Machine-readable RFC 8259 canonical format with embedded reproducibility manifests, cryptographic provenance hashes, ranking disclaimers, and unit annotations.
   - **Markdown (`.to_markdown()`)**: Publication-grade tables with metric comparison grids, directional rankings with units and interpretations, model comparison disclaimers, diagnostic warnings, and limitations.
   - **CSV (`.to_csv()`)**: Standardized tabular format with explicit `unit` column for downstream analysis in spreadsheets or data science workflows.

5. **Security & Containment Boundaries**:
   - Plugins execute in-process with application permissions. External code auto-execution, dynamic `pip` installation, and remote imports are prohibited.
   - Strict identifier validation prevents filesystem path traversal attacks.

### Implementing a Custom Plugin

```python
from typing import Any, Mapping
import numpy as np
from fragility_engine.plugins import ModelPlugin, PluginMetadata, ModelExecutionResult

class CustomRollingVolPlugin(ModelPlugin):
    """Custom model computing 20-day rolling volatility."""

    def __init__(self) -> None:
        self._meta = PluginMetadata(
            plugin_id="custom.rolling_vol",
            name="Custom Rolling Volatility",
            description="Computes standard deviation over the most recent 20 observations.",
            plugin_version="1.0.0",
            api_version="1.0.0",
            supported_data_types=("return_series",),
            capabilities=("rolling_vol_20",),
            limitations=("Requires at least 20 observations; ignores long-term regime shifts.",),
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        arr = np.asarray(data, dtype=np.float64)
        if len(arr) < 20:
            raise ValueError(f"CustomRollingVolPlugin requires >= 20 observations; got {len(arr)}")

    def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
        self.validate_input(data, config)
        arr = np.asarray(data, dtype=np.float64)[-20:]
        vol = float(np.std(arr, ddof=1)) * np.sqrt(252.0)
        return ModelExecutionResult(
            plugin_id=self._meta.plugin_id,
            model_version=self._meta.plugin_version,
            metrics={"rolling_vol_20": vol},
            execution_time_ms=0.5,
            observations_used=len(arr),
            limitations=self._meta.limitations,
        )
```

### Running a Benchmark Example

```python
import numpy as np
from fragility_engine.benchmarks import BenchmarkSpecification, execute_model_benchmark

# 1. Deterministic synthetic return data (fat-tailed Student-t)
rng = np.random.default_rng(42)
returns = rng.standard_t(df=4, size=500) * 0.015 - 0.0005

# 2. Benchmark Specification
spec = BenchmarkSpecification(
    benchmark_id="BM-TAIL-001",
    name="Tail Risk Benchmark: Historical vs Gaussian",
    description="Evaluate empirical non-parametric VaR vs Gaussian under return friction.",
    dataset_id="SYNTHETIC-T4-500D",
    plugin_ids=("builtin.historical_simulation", "builtin.parametric_gaussian"),
    metrics_to_compare=("var_95", "expected_shortfall_95", "volatility_annualized"),
    target_ranking_metric="var_95",
    ranking_direction="lower_is_better",
    perturbation_specs=(
        {"type": "return_friction", "parameters": {"friction_bps": 10.0}},
    ),
)

# 3. Execute benchmark
report = execute_model_benchmark(spec, dataset=returns)

# 4. Inspect rankings and provenance
print(f"Status: {report.status}")
print(f"Provenance Hash: {report.output_fingerprint[:16]}...")
for r in report.rankings:
    print(f"Rank {r.rank}: {r.model_name} -> VaR(95%) = {r.metric_value * 100:.3f}%")
```

---

## Experiment Studio & Reports (Phase 7)

Located in `backend/fragility_engine/studio.py`:
- **Product Goal**: An empirical research studio allowing quantitative researchers to define, execute, evaluate, compare, export, and catalog risk and fragility stress experiments through structured configurations.
- **Key Capabilities**:
  1. **Typed Experiment Definition (`StudioExperimentDefinition`)**:
     - Configures `experiment_id`, `name`, `description`, `dataset_id`, `baseline_config` (confidence level, annualization factor), `perturbation_specs`, `target_ranking_metric`, `tags`, and metadata.
     - Strict path-traversal prevention: disallows `..`, `/`, `\`, and null bytes.
     - Separates calculation parameters from informational metadata.
  2. **Automated Studio Execution (`execute_studio_experiment`)**:
     - Orchestrates baseline evaluation, fragility shocks, independent invariant verification, sensitivity ranking, and reproducibility manifest generation.
     - Employs honest 4-state status tracking: `completed`, `completed_with_warnings`, `failed_validation`, and `failed_execution`.
  3. **Multi-Format Report Export (`ExperimentReport`)**:
     - **JSON (`.to_json()`)**: Versioned, machine-readable canonical JSON (RFC 8259).
     - **Markdown (`.to_markdown()`)**: Executive summary with unit-aware tables (`pts`, `%`, currency), diagnostic summaries, and methodological limitations.
     - **CSV (`.to_csv()`)**: Tabular dataset with standardized headers including explicit `unit` designation.
  4. **Cross-Experiment Comparison (`compare_experiment_reports`)**:
     - Formally checks comparability: flags non-comparable runs when dataset IDs or input hashes differ.
     - Itemizes baseline metric deltas against configurable tolerance $\epsilon$ (default $10^{-6}$).
     - Analyzes perturbation impact changes and sensitivity rank shifts.
  5. **Local Experiment Catalog (`LocalExperimentCatalog`)**:
     - File-based catalog indexing reports as versioned JSON.
     - Overwrite protection enabled by default (`overwrite=False`).
     - Query filters by `status`, `tag`, and `dataset_id`.
     - Graceful handling of missing or corrupted files with diagnostic error messages.
     - Path-sanitized lookups and deletions.

### Usage Example

```python
from fragility_engine import (
    StudioExperimentDefinition,
    execute_studio_experiment,
    compare_experiment_reports,
    LocalExperimentCatalog,
)

# 1. Define an experiment
definition = StudioExperimentDefinition(
    experiment_id="EXP-STUDIO-001",
    name="Studio Tail Risk & Friction Audit",
    description="Evaluates tail risk under 5bps and 10bps return drag and 30-day window truncation.",
    dataset_id="NSE-60D-EQUITIES",
    baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
    perturbation_specs=[
        {"type": "return_friction", "experiment_id": "drag_5bps", "parameters": {"friction_bps": 5.0}},
        {"type": "return_friction", "experiment_id": "drag_10bps", "parameters": {"friction_bps": 10.0}},
        {"type": "lookback_window", "experiment_id": "window_30d", "parameters": {"lookback_window": 30}},
    ],
    target_ranking_metric="var_historical",
    tags=["risk", "friction", "equities"],
)

# 2. Execute experiment workflow
returns = [0.005, -0.012, 0.008, -0.003, 0.015, -0.021] # ... daily return series
report = execute_studio_experiment(definition=definition, return_series=returns)

# 3. Export reports
json_str = report.to_json()
md_summary = report.to_markdown()
csv_table = report.to_csv()

# 4. Catalog and index report
catalog = LocalExperimentCatalog(catalog_dir="data/catalog")
catalog.save_report(report)
saved_report = catalog.get_report("EXP-STUDIO-001")
all_reports = catalog.list_reports(status="completed", tag="risk")

# 5. Compare against another experiment
# comparison = compare_experiment_reports(report_a=report_1, report_b=report_2)
```

### Supported Metrics & Perturbations
- **Baseline Metrics**: `annualized_volatility`, `volatility_daily`, `var_95`, `var_99`, `expected_shortfall_95`, `expected_shortfall_99`, `max_drawdown`, `asset_hhi`, `sector_hhi`.
- **Perturbations**:
  - `lookback_window`: Sample window truncation.
  - `volatility_estimator`: Sample standard deviation vs RiskMetrics EWMA ($\lambda$).
  - `return_friction`: Basis point drag deduction ($r_t' = r_t - c / 10000$).
  - `liquidation_cost`: Turnover friction on portfolio valuation ($\text{Cost} = \text{MV} \times \tau \times c / 10000$).
  - `correlation_stress`: Uniform stress toward crisis correlation target ($C_\alpha = (1-\alpha)C_0 + \alpha C_{\text{target}}$).
  - `confidence_shift`: Confidence level perturbation from 95% to 99%.

### Known Limitations & Deferred Features
- **Dataset Storage Boundary**: Cryptographic SHA-256 hashes detect data tampering and drift, but cannot recreate lost input files.
- **Cross-Platform Precision**: Minor divergence at $10^{-16}$ can occur across differing CPU architectures (ARM64 vs x86-64). A configurable tolerance $\epsilon = 10^{-6}$ is applied.
- **Web UI & Live Feeds**: Phase 7 focuses exclusively on the quantitative engine, reporting, and catalog layer. Web dashboard and live market connectors are deferred to future phases.

### Reports & Audits
- Phase 6 Verification Report: [`docs/phase-6-verification-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-6-verification-report.md).
- Phase 7 Issue Review: [`docs/phase-7-issue-review.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-7-issue-review.md).
- Phase 7 Completion Report: [`docs/phase-7-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-7-report.md).

---

## Validation & Reproducibility Lab (Phase 6)

Located in `backend/fragility_engine/reproducibility.py`:
- **Cryptographic Fingerprinting (`compute_canonical_hash`, `compute_dataset_hash`)**:
  - Deterministic SHA-256 fingerprinting for datasets, calculation configurations, and execution results.
  - Implements canonical JSON serialization (`canonical_json_dumps`): alphabetically sorted dictionary keys, IEEE 754 float precision, strict rejection of non-finite numbers (`NaN`, `Inf`), and compact representation.
  - Separates mathematical calculation parameters from informational metadata (`created_at`, `description`, `metadata`, `dataset_provenance`) so timestamps and user notes never corrupt calculation fingerprints.
- **Experiment Specification (`ExperimentSpecification`)**:
  - Fully typed, immutable domain model specifying `experiment_id`, `name`, `dataset_id`, `baseline_config`, `perturbation_specs`, `schema_version`, `algorithm_version`, `random_seed`, and `date_range`.
  - Validates baseline parameters (e.g. `confidence_level` $\in (0, 1)$) and rejects unsupported perturbation types.
- **Reproducible Experiment Runner (`run_reproducible_experiment`)**:
  - Orchestrates: (1) Dataset and configuration fingerprinting; (2) Baseline risk and concentration calculations; (3) Execution of configured perturbations; (4) Independent mathematical invariant validation; (5) Manifest generation with execution environment capture.
  - Supports 1D return series, 2D multivariate return matrices, and `Portfolio` instances.
- **Reproducibility Manifest (`ReproducibilityManifest`)**:
  - Immutable audit artifact capturing `input_fingerprint`, `configuration_fingerprint`, `output_fingerprint`, environment metadata (Python version, NumPy version, OS platform, machine architecture), validation status, check counts, warnings, and limitations.
- **Independent Invariant Verification (`verify_experiment_invariants`)**:
  - Validates non-circular mathematical constraints:
    - Portfolio weights sum to $1.0 \pm 10^{-5}$.
    - Asset HHI scale consistency ($H_{\text{points}} = 10000 \times H_{\text{decimal}}$).
    - Tail coherence: $\text{ES}_\alpha \ge \text{VaR}_\alpha - 10^{-9}$.
    - Maximum drawdown bounded within $[0.0, 1.0]$.
    - Strict finiteness of all baseline and perturbed metrics.
- **Output Comparison & Drift Detection (`compare_experiment_runs`)**:
  - Compares two experiment runs and produces a structured `DriftReport`.
  - Accurately classifies drift source:
    - **Input Data Drift**: Input dataset SHA-256 changed.
    - **Configuration Drift**: Model parameters or perturbation specs changed.
    - **Environment Drift**: Operating system, Python release, or NumPy version changed.
    - **Tolerance Divergence**: Numerical metrics diverged beyond configurable threshold $\epsilon$ (default $10^{-6}$).
- **Reports & Audits**:
  - Phase 5 Verification Report: [`docs/phase-5-verification-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-5-verification-report.md).
  - Phase 6 Issue Review: [`docs/phase-6-issue-review.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-6-issue-review.md).
  - Phase 6 Implementation Report: [`docs/phase-6-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-6-report.md).

---


## Fragility Lab (Phase 5)

Located in `backend/fragility_engine/fragility.py`:
- **Risk & Model Robustness Laboratory**:
  - Measures how sensitive risk conclusions and portfolio metrics are to shifts in underlying assumptions.
  - Generates structured, immutable `FragilityExperimentResult` artifacts containing baseline metrics, perturbed metrics, absolute changes ($\Delta = M_1 - M_0$), and relative changes ($\Delta / |M_0|$).
  - Handles zero-baseline relative change safely by emitting `None` (JSON `null`) rather than NaN or infinity.
- **Supported Perturbation Models**:
  - **Lookback Window Perturbation (`run_lookback_perturbation`)**: Evaluates risk sensitivity when the historical sample window is truncated.
  - **Alternative Volatility Estimator (`run_volatility_estimator_perturbation`)**: Compares standard sample volatility against RiskMetrics Exponentially Weighted Moving Average (EWMA) volatility (`calculate_ewma_volatility`, $\lambda \in (0, 1)$).
  - **Return Friction Shock (`run_return_friction_perturbation`)**: Evaluates return series drag by deducting constant basis points ($r_t' = r_t - \frac{c}{10000}$) to measure tail risk expansion.
  - **Portfolio Liquidation Cost Shock (`calculate_portfolio_liquidation_shock`)**: Models turnover execution friction on total portfolio valuation ($\text{Cost} = \text{MV} \times \tau \times \frac{c}{10000}$).
  - **Multivariate Correlation Stress (`run_correlation_perturbation`)**: Perturbs empirical correlation matrix toward a uniform crisis target ($C_\alpha = (1-\alpha) C_0 + \alpha C_{\text{target}}$) for synchronized 2D return matrices, evaluating diversified portfolio risk expansion.
  - **Tail Confidence Level Shift (`run_confidence_level_perturbation`)**: Evaluates tail risk expansion between 95% and 99% confidence.
- **Sensitivity Ranking Engine (`rank_perturbation_sensitivities`)**:
  - Ranks experiments by absolute impact $|\Delta|$ on any target metric, identifying the most vulnerable modeling assumption without arbitrary composite scores.
- **Reports & Audits**:
  - Phase 4.1 Verification: [`docs/phase-4.1-verification-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-4.1-verification-report.md).
  - Phase 5 Issue Review: [`docs/phase-5-issue-review.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-5-issue-review.md).
  - Phase 5 Implementation Report: [`docs/phase-5-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-5-report.md).

---

## Scenario Lab (Phase 4)

Located in `backend/fragility_engine/scenarios.py`:
- **Pure Deterministic Scenario Engine (`apply_scenario`)**:
  - Applies instantaneous price shocks to an existing portfolio snapshot without modifying caller inputs.
  - Calculates holding-level stressed prices, market values, and monetary P&L contributions.
  - Aggregates portfolio-level stressed valuation, net monetary P&L, percentage return, and positive loss magnitude.
  - Produces sector-level P&L attribution and identifies explicitly unshocked holdings.
  - Mathematical integrity: Guarantees exact reconciliation $\sum \text{holding\_pnl} = \text{portfolio\_pnl}$ and $\sum \text{sector\_pnl} = \text{portfolio\_pnl}$.
- **Scenario Specification (`ScenarioDefinition`)**:
  - Supports stable `scenario_id`, human-readable name, narrative description, `sector_shocks`, `asset_shocks`, and `version`.
  - Shocks are expressed as decimal returns (e.g. `-0.20` for -20%, `+0.10` for +10%).
- **Strict Conflict Policy**:
  - Rejects overlapping rules by default: If a holding is targeted simultaneously by a sector shock and an asset-specific shock, execution is aborted with a `ValueError`. Silent precedence or combining of shocks is prohibited.
- **Robust Validation**:
  - Rejects non-finite (NaN, $\pm\infty$) shocks and shocks producing non-positive prices ($\text{shock} \le -1.0$).
  - Rejects unknown sector and asset identifiers not present in the portfolio snapshot.
- **Standard Benchmark Preset (`create_preset_scenario`)**:
  - `"banking_minus_20_it_minus_10"`: -20% instantaneous shock on Banking and -10% on Information Technology assets.
  - Illustrative ₹10 Lakh portfolio impact: Stressed value = ₹9,20,000.00, P&L = -₹80,000.00 (-8.00%), Loss magnitude = ₹80,000.00.
- **Audit & Issue Review**:
  - Documented in `docs/phase-4-issue-review.md`.

---

## Risk Calculation Engine (Phase 3)

Located in `backend/fragility_engine/risk.py`:
- **Annualized Volatility (`calculate_annualized_volatility`)**:
  - Sample standard deviation with Bessel's correction (`ddof=1` default).
  - Formula: $\sigma_{\text{ann}} = \sigma_{\text{daily}} \times \sqrt{252}$.
- **Historical Value at Risk (`calculate_historical_var`)**:
  - Positive-loss convention: Positive VaR indicates loss magnitude ($L = -R$).
  - Evaluated at 95% and 99% confidence using explicit empirical quantile interpolation (`method="linear"`).
- **Historical Expected Shortfall (`calculate_expected_shortfall`)**:
  - Implements coherent discrete tail expectation via **Acerbi & Tasche (2002)** with fractional tail weighting.
  - Solves finite-sample tie and boundary distortions; mathematically guarantees $\text{ES} \ge \text{VaR}$ without artificial clamping.
- **Maximum Drawdown & Duration Dynamics (`calculate_maximum_drawdown`)**:
  - Peak-to-trough decline as a positive loss fraction on $[0.0, 1.0]$.
  - Tracks `peak_to_trough_duration`, `recovery_duration`, and `total_drawdown_duration` in observation intervals.
  - Distinguishes fully recovered drawdowns from ongoing/unrecovered drawdowns and partial rebounds.
- **Consolidated Risk Report (`calculate_risk_report`)**:
  - Bundles daily/annualized volatility, VaR (95%/99%), ES (95%/99%), drawdown diagnostics, and sample size caveats into `RiskMetricsReport`.

## Portfolio Lab & Analytics (Phase 2)

### 1. Illustrative ₹10 Lakh NSE Portfolio Fixtures
Located in `data/sample_portfolios/`:
- `nse_10l.json`: JSON portfolio fixture with metadata and illustrative holdings summing to exactly ₹10,00,000.
- `nse_10l.csv`: Deterministic CSV fixture matching the JSON representation.
- **Sectors covered:** Banking (30%), Information Technology (20%), Energy (15%), FMCG (15%), Healthcare (10%), Industrials (10%).
- *Disclaimer:* All prices, quantities, and allocations are deterministic test assumptions for empirical model testing and do not represent live market data or investment advice.

### 2. Portfolio Loader (`portfolio_loader.py`)
- `load_portfolio_from_json(source)`: Safe JSON parser with strict field checks and contradictory valuation rejection.
- `load_portfolio_from_csv(source)`: Strict all-or-nothing CSV parser requiring `asset_id,quantity,price,sector` columns.
- `export_portfolio_to_csv(portfolio, target)`: Deterministic CSV export with stable column ordering.

### 3. Allocation & Concentration Analytics (`concentration.py`)
- `calculate_portfolio_concentration(portfolio)`: Computes aggregate valuation, asset weights, sector market values, and sector proportions.
- `calculate_hhi(weights)`: Calculates both decimal Herfindahl-Hirschman Index ($[0.0, 1.0]$) and conventional HHI points ($[0, 10000]$).
  - *Reference:* Under Antitrust guidelines, HHI points $<1500$ indicates diversification, $1500-2500$ moderate concentration, and $>2500$ high concentration.
  - *Disclaimer:* HHI measures bucket concentration across weights, not correlation or tail risk.

---

## Core Domain Models (Phase 1)

1. **`Holding`**: Represents an individual asset holding with strict validation for positive, finite quantity, price, and non-empty asset identifier. Calculates `market_value` dynamically.
2. **`Portfolio`**: Represents a multi-asset portfolio with currency validation, unique asset verification, total valuation, and portfolio weights calculation.
3. **`MetricResult`**: Standardized container for quantitative outputs with formal methodology citations, parameter tracking, and diagnostic warnings.
4. **`compute_simple_returns`**: Pure function calculating arithmetic returns from consecutive positive prices without modifying caller-owned sequences.
