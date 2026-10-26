# FragilityShield — Production SDK Architecture & Verification Report

**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Package:** `fragility-engine` (Python SDK & CLI)  
**Standard:** Phase 3 — Production-Grade SDK, Capability-Aware Execution & Sandboxing  

---

## 1. SDK Overview & Public Interface

FragilityShield provides a fully typed, production-ready Python SDK for quantitative researchers and institutional engineers.

### Package Installation
The SDK can be installed directly from the repository using standard package managers:
```bash
# Editable development install
pip install -e .

# Production wheel build
python -m build
pip install dist/fragility_engine-*.whl
```

### Public Entrypoint
The canonical client is exported from `backend/fragility_engine/sdk.py`:
```python
from fragility_engine.sdk import FragilityShield, Client

# Initialize client with optional tenant authentication
client = FragilityShield(
    base_url="http://localhost:8000",
    api_key="fs_live_token_...",
    tenant_id="ten_alpha_capital"
)
```

---

## 2. Capability-Aware Algorithm Registration

User-defined algorithms and models register into the platform via typed configuration objects:

```python
from fragility_engine.custom_configs import CustomModelConfig, CustomStrategyConfig

# Define custom quantitative model
custom_model = CustomModelConfig(
    model_id="garch_vol_custom_v1",
    display_name="Custom GARCH(1,1) Volatility Model",
    model_type="risk_model",
    description="Student-t innovations GARCH for fat-tailed volatility estimation",
    parameters={
        "omega": 0.00001,
        "alpha": 0.08,
        "beta": 0.90
    },
    capabilities=["var_calculation", "expected_shortfall", "volatility_forecast"]
)

# Register with central engine
client.model_lab.register_model(custom_model)
```

### Capability Matrix & Lab Compatibility
Algorithms are matched against research labs using strict capability contracts:

| Algorithm Category | Required Capability Flags | Compatible Research Labs | Incompatible Labs (Explicitly Rejected) |
|---|---|---|---|
| **VaR / Risk Model** | `var_calculation`, `cvar_calculation` | Risk Analytics (`/labs/risk`), Model Validation (`/labs/model-validation`), Backtesting Observatory (`/models/risk-validation`) | Strategy Backtest, Portfolio Allocation |
| **Forecasting Model** | `volatility_forecast`, `return_forecast` | ML Forecasting (`/labs/ml-forecasting`), ML Robustness (`/labs/ml-robustness`), Monte Carlo (`/labs/monte-carlo`) | Strategy Backtest, Risk Attribution |
| **Trading Strategy** | `generate_signals`, `position_sizing` | Strategy Library (`/strategies`), Strategy Backtest (`/labs/backtesting`), Tournament (`/labs/tournament`) | Risk Analytics, Scenario Analysis |
| **Allocation Algorithm** | `optimize_weights`, `covariance_estimation` | Allocation & Optimization (`/labs/allocation`), Portfolio Workbench (`/portfolio`) | ML Forecasting, Reverse Stress |

If a user attempts to execute a Forecasting model inside the Strategy Backtest Lab, the system immediately returns an explicit HTTP 422 Unprocessable Entity error:
`IncompatibleAlgorithmError: Model 'garch_vol_custom_v1' does not implement 'generate_signals'.`

---

## 3. SDK Sandboxing & Execution Security

FragilityShield enforces a defensive execution boundary (`backend/fragility_engine/model_sandbox.py` and `plugin_sandbox.py`):

1. **Static AST Analysis:** Untrusted algorithm code is parsed via Python's `ast` module before execution. Imports of dangerous modules (`os`, `subprocess`, `sys`, `socket`, `shutil`) are rejected at validation time.
2. **Resource Boundaries:** Subprocess execution is restricted with:
   - CPU Timeout: Max 60 seconds per run (enforced via `signal.SIGALRM` or subprocess timeout).
   - Memory Limit: Max 1024 MB per worker process (enforced via `resource.setrlimit(resource.RLIMIT_AS, ...)`).
   - Output Truncation: Maximum artifact payload size 50 MB.
3. **Tenant Context Isolation:** All SDK requests enforce `tenant_id` validation; a tenant cannot query, execute, or overwrite another tenant's registered algorithms.

---

## 4. Automated SDK Test Coverage

The SDK test suite exercises the complete lifecycle:
- `backend/tests/test_sdk_and_cli.py`: Tests client initialization, portfolio submission, risk calculation, and export.
- `backend/tests/test_model_sandbox_and_contracts.py`: Tests AST import rejection, memory limits, and schema validation.
- `backend/tests/test_master_functionality_repair.py`: Tests end-to-end strategy registration, persistence, and backtest execution.