# FragilityShield API & SDK Integration Guide

## 1. Overview

FragilityShield enables quantitative researchers to run automated model validation, portfolio stress tests, and fragility analyses directly from Python scripts, automated CI/CD pipelines, and Google Colab notebooks.

This guide details both the REST API endpoints and the Python SDK (`fragility_engine.sdk.Client`).

---

## 2. Authentication & Server Addressing

All API and SDK operations require a Bearer token or configured API key.

- **Local Development**: `http://127.0.0.1:8000`
- **Google Colab / Cloud Deployment**: `https://fragshield-dev.loca.lt` (or your production domain)
- **Authorization Header**: `Authorization: Bearer <FRAGILITYSHIELD_API_TOKEN>`

---

## 3. Python SDK Quickstart

### 3.1 Installation & Initialization
```python
from fragility_engine.sdk import Client

client = Client(
    api_url="https://fragshield-dev.loca.lt",
    api_token="dev_test_bearer_token",
    workspace_id="ws_colab_alpha_research",
    environment_type="google_colab"
)

print("SDK Client initialized with external connectivity.")
```

### 3.2 Automated Full-Suite Testing (Test All)
Submit model predictions and trigger an automated multi-engine validation suite in one call:

```python
import time

# 1. Register Model and Dataset
client.external.register_model(
    model_id="colab_volatility_forecaster",
    name="Colab NIFTY 50 Volatility Forecaster",
    version="1.0.0",
    author="quant_researcher",
    description="Intraday GARCH volatility forecasting trained on Google Colab."
)

client.external.register_dataset(
    dataset_id="ds_nse_nifty50_hourly",
    name="NSE Nifty 50 1-Hour Intraday Dataset",
    version="1.0.0",
    symbols=["NIFTY_50"]
)

# 2. Submit Experiment Run with auto_test_all=True
run_id = f"colab_run_{int(time.time())}"
result = client.external.submit_run(
    experiment_id="exp_colab_alpha_01",
    run_id=run_id,
    model_id="colab_volatility_forecaster",
    dataset_id="ds_nse_nifty50_hourly",
    display_name="Colab Alpha Automated Robustness Suite",
    metrics=[
        {"metric_name": "val_rmse", "observed_value": 0.0142, "unit": "volatility_points"},
        {"metric_name": "val_r2", "observed_value": 0.684, "unit": "ratio"}
    ],
    predictions=[
        {"timestamp": "2026-03-01T10:00:00Z", "prediction_value": 0.165, "ground_truth": 0.161},
        {"timestamp": "2026-03-01T11:00:00Z", "prediction_value": 0.172, "ground_truth": 0.169}
    ],
    auto_test_all=True
)

print(f"Run submitted! Status: {result.get('status')}")
```

### 3.3 Running Custom Test Profiles via SDK
```python
# List available testing engines
modules = client.orchestrator.list_modules()
print(f"Registered modules: {len(modules)}")

# Pre-flight compatibility validation
val = client.orchestrator.validate(
    experiment_type="model",
    data={"returns": [0.005, -0.012, 0.008, 0.003, -0.021]},
    profile_id="basel_regulatory_suite"
)
print("Applicable modules:", val.get("applicable_count"))

# Run custom profile with parameter overrides
suite_result = client.orchestrator.run_profile(
    experiment_id="exp_custom_stress",
    profile_id="custom",
    experiment_type="model",
    selected_modules=["risk_analytics", "scenario_stress", "monte_carlo_simulation"],
    data={"returns": [0.005, -0.012, 0.008, 0.003, -0.021, 0.015, -0.004, 0.007, -0.018, 0.009]},
    config_overrides={
        "scenario_stress": {"shock_multipliers": {"covid": 1.5}},
        "monte_carlo_simulation": {"n_paths": 2000, "n_days": 180}
    }
)

print("Suite Status:", suite_result.get("status"))
print("Summary Metrics:", suite_result.get("summary_metrics"))
```

---

## 4. REST API Reference

### 4.1 Orchestrator Endpoints

#### `GET /api/orchestrator/modules`
Returns all registered quantitative testing modules and their metadata.

#### `POST /api/orchestrator/validate`
Validates inputs against module requirements before running.
```json
{
  "experiment_type": "model",
  "profile_id": "test_all",
  "inputs": {
    "returns": [0.01, -0.02, 0.015, -0.008]
  }
}
```

#### `POST /api/orchestrator/run`
Executes Test All or a Custom Test Profile.
```json
{
  "experiment_id": "exp_alpha_01",
  "run_id": "run_test_all_001",
  "display_name": "Full Robustness Suite",
  "experiment_type": "model",
  "submission_source": "external_api",
  "test_profile": "test_all",
  "inputs": {
    "returns": [0.005, -0.012, 0.008, 0.003, -0.021, 0.015, -0.004, 0.007, -0.018, 0.009]
  }
}
```

#### `GET /api/orchestrator/runs/{run_id}`
Retrieves detailed test results, metrics, diagnostics, and errors for a specific run.

---

### 4.2 Declarative Configuration Endpoints

- `GET /api/configurations/strategies` & `POST /api/configurations/strategies`
- `GET /api/configurations/scenarios` & `POST /api/configurations/scenarios`
- `GET /api/configurations/test-profiles` & `POST /api/configurations/test-profiles`

All configuration endpoints validate against declarative dataclasses without dynamic `eval`/`exec`.
