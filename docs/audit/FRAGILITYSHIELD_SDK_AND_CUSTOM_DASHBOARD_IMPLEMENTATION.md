# FRAGILITYSHIELD — OFFICIAL SDK, CAPABILITY MODEL REGISTRY & CUSTOM DASHBOARD IMPLEMENTATION REPORT

**Author**: Antigravity Principal Systems Architect & Quantitative Engineering Lead  
**Date**: October 26, 2026  
**Repository**: `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Status**: COMPLETE, TESTED & PRODUCTION-READY (24/24 E2E Tests Passing, 100% Pass Rate)

---

## 1. Executive Summary

This engineering implementation delivers two first-class product capabilities directly into the core FragilityShield platform:

1. **A Real, Tested, Public Python SDK (`fragilityshield`)**:
   - A fully installable and locally discoverable Python package exposing stable contracts for **5 quantitative extension types**: `RiskModel`, `ForecastingModel`, `CustomMetric`, `SimulationEngine`, and `TradingStrategy`.
   - Schema-driven parameter declarations (`FloatParam`, `IntParam`, `ChoiceParam`, `BoolParam`) with strict runtime contract validation, rejection of NaN/inf, bounds verification, and cryptographic output hashing.
   - Capability-based model discovery allowing compatible research labs to query and mount registered user algorithms automatically without frontend modifications.
   - Authoritative registry persistence to the persistent filesystem catalog (`data/catalog/models/`) and run ledger (`data/catalog/runs/`).

2. **A Customizable, Persistent Dashboard System (`/dashboards`)**:
   - A multi-dashboard workspace allowing quants and risk managers to create, rename, duplicate, reorder, resize, and delete dashboards with tenant scoping and default layout protection.
   - A **10-type schema-driven Widget Catalog** spanning Portfolio Risk, VaR & Expected Shortfall Distributions, Drawdown & Stress Loss, Asset Risk Contribution, ML Forecast Performance, Multi-Model Benchmarks, Strategy Backtests, Monte Carlo Simulation Paths, Experiment Run History, and Cryptographic Data Lineage.
   - An **authentic quantitative calculation engine** (`execute_widget_query`) that computes live numerical values and charts from portfolios and registered models, strictly eliminating zero-placeholder values and displaying explicit `"unavailable"` badges when market observations are insufficient.
   - Interactive React workspace UI (`CustomDashboardWorkspace.tsx`) mounted at `/dashboards` and `/custom-dashboard`, featuring Recharts visualizers, live KPI cards, interactive modals, and model selection.

---

## 2. Architecture & File Inventory

### 2.1 Backend SDK & Contracts (`backend/fragilityshield/`)

| File Path | Description | Key Classes / Functions |
| :--- | :--- | :--- |
| `backend/fragilityshield/__init__.py` | Package root & public exports | `Client`, `BaseModel`, `RiskModel`, `ForecastingModel`, `CustomMetric`, `SimulationEngine`, `TradingStrategy` |
| `backend/fragilityshield/contracts.py` | Strict abstract contracts & parameter schemas | `BaseModel`, `ParameterDefinition`, `FloatParam`, `IntParam`, `ChoiceParam`, `BoolParam`, `RiskMetricsOutput`, `ForecastOutput`, `MetricOutput`, `SimulationOutput`, `StrategySignalsOutput`, `ModelContractValidationError` |
| `backend/fragilityshield/client.py` | Unified public SDK client & HTTP gateways | `Client`, `ModelRegistryClient`, `DashboardClient` |
| `backend/fragilityshield/examples/custom_ewma_risk.py` | Working Reference Extension: Risk Model | `CustomEWMARiskModel` (EWMA VaR 95/99, Expected Shortfall, Volatility) |
| `backend/fragilityshield/examples/custom_ar_forecaster.py` | Working Reference Extension: Forecasting Model | `CustomARForecaster` (Autoregressive return forecaster with confidence bands) |
| `backend/fragilityshield/examples/custom_sortino_metric.py` | Working Reference Extension: Custom Metric | `CustomSortinoRatioMetric` (Downside deviation & Sortino calculation) |
| `backend/fragilityshield/examples/custom_gbm_simulator.py` | Working Reference Extension: Simulation Engine | `CustomGBMSimulator` (Geometric Brownian Motion paths & quantiles) |
| `backend/fragilityshield/examples/custom_momentum_strategy.py` | Working Reference Extension: Trading Strategy | `CustomMomentumStrategy` (Dual moving average trend following & target weights) |

### 2.2 Dashboard Engine & Storage (`backend/fragility_engine/dashboards.py`)

| Component | Responsibility |
| :--- | :--- |
| `SUPPORTED_WIDGET_TYPES` | 10 schema-driven widget specifications defining categories, dimensions, compatible metrics, and parameter schemas. |
| `DashboardStorage` | Thread-safe persistent JSON storage scoped to `data/catalog/dashboards/{id}.json` with automatic seeding of default executive risk layout. |
| `execute_widget_query` | Pure quantitative analytics calculation engine computing real metrics, empirical quantiles, and historical series. |

### 2.3 API Route Integrations (`backend/app.py`)

| HTTP Method | Route Path | Handler Function | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/models/registered` | `api_list_registered_models` | Query catalog with capability, category, and lab filters |
| `GET` | `/api/models/registered/{id}` | `api_get_registered_model` | Retrieve model manifest and parameter schemas |
| `PUT` | `/api/models/registered/{id}/toggle`| `api_toggle_registered_model` | Enable or disable model from lab discovery |
| `POST` | `/api/models/register` | `api_register_custom_model` | Register and persist user model manifest |
| `POST` | `/api/models/execute` | `api_execute_custom_model` | Execute model in validated container or local research mode |
| `GET` | `/api/dashboards` | `api_list_dashboards` | List all saved dashboards for current tenant |
| `POST` | `/api/dashboards` | `api_create_dashboard` | Create a new custom persistent dashboard |
| `GET` | `/api/dashboards/{id}` | `api_get_dashboard` | Retrieve dashboard configuration and widget list |
| `PUT` | `/api/dashboards/{id}` | `api_update_dashboard` | Save modified layout, reordered widgets, and parameters |
| `DELETE` | `/api/dashboards/{id}` | `api_delete_dashboard` | Delete custom dashboard (safeguards default layout) |
| `POST` | `/api/dashboards/{id}/duplicate` | `api_duplicate_dashboard` | Clone existing dashboard into independent layout |
| `GET` | `/api/dashboards/widgets/catalog`| `api_list_widget_catalog` | Catalog of 10 supported widget types and metadata |
| `POST` | `/api/dashboards/widgets/query` | `api_query_widget` | Execute live computation for a widget without placeholder zeros |

### 2.4 Frontend Integration (`frontend/`)

| File Path | Description | Key Additions |
| :--- | :--- | :--- |
| `frontend/src/lib/api.ts` | Strongly typed API client | `RegisteredModel`, `DashboardWidget`, `DashboardConfig`, `WidgetCatalogItem`, `WidgetQueryResult`, `listDashboards`, `updateDashboard`, `queryWidget`, etc. |
| `frontend/src/components/pages/CustomDashboardWorkspace.tsx` | Custom dashboard application workspace | Multi-dashboard switcher, Add Widget catalog modal, Widget settings modal, 12-column grid layout, resize/reorder controls, live Recharts visualizers, lineage badges. |
| `frontend/src/App.tsx` | Application router & navigation | Mounted `/dashboards` and `/custom-dashboard` routes with sidebar entry. |

---

## 3. Public Python SDK Usage Guide

### 3.1 Installation

The SDK is locally discoverable from the repository root:
```bash
cd /Users/vemanahemanthbabu/srujana_hackathon_2
pip install -e .
```

### 3.2 Defining a Custom Quantitative Model

```python
import math
from typing import Any, Dict, Sequence
import fragilityshield as fs

class CustomVolTargetRiskModel(fs.RiskModel):
    def __init__(self):
        super().__init__(
            model_id="custom.vol_target_risk",
            name="Volatility-Targeted Tail Risk Model",
            version="1.0.0",
            author="lead_quant",
            description="Computes parametric VaR scaled by dynamic volatility targeting.",
            parameters=[
                fs.FloatParam("target_vol", default=0.15, min_value=0.05, max_value=0.50),
                fs.FloatParam("confidence_level", default=0.95, min_value=0.80, max_value=0.999),
            ]
        )

    def calculate_risk(self, returns: Sequence[float], parameters: Dict[str, Any]) -> fs.RiskMetricsOutput:
        target_vol = float(parameters.get("target_vol", 0.15))
        conf = float(parameters.get("confidence_level", 0.95))
        
        sample_std = float(np.std(returns))
        ann_vol = sample_std * math.sqrt(252)
        vol_scalar = target_vol / max(1e-4, ann_vol)
        
        z = 1.645 if conf < 0.99 else 2.326
        var_95 = z * sample_std * vol_scalar
        es_95 = var_95 * 1.25

        return fs.RiskMetricsOutput(
            var_95=float(var_95),
            expected_shortfall_95=float(es_95),
            annualized_volatility=float(target_vol),
            metrics={"vol_scalar": float(vol_scalar), "unscaled_ann_vol": float(ann_vol)},
        )
```

### 3.3 Registering, Discovering, and Executing via the SDK Client

```python
client = fs.Client(base_url="http://127.0.0.1:8000")

# 1. Register custom model
model = CustomVolTargetRiskModel()
client.models.register(model)

# 2. Query registry with capability filter
risk_models = client.models.list(lab="risk")
print(f"Discovered {len(risk_models)} risk models in registry.")

# 3. Execute model against market returns
result = client.models.execute(
    model_id="custom.vol_target_risk",
    inputs={"returns": [0.012, -0.015, 0.008, 0.018, -0.022, 0.005]},
    parameters={"target_vol": 0.12}
)
print("Run ID:", result["run_id"])
print("VaR 95%:", result["metrics"]["var_95"])

# 4. Add model to a custom dashboard
dashboard = client.dashboards.create(
    name="Quant Risk Command Center",
    widgets=[
        {
            "widget_id": "w1",
            "type": "portfolio_risk",
            "title": "Vol-Targeted VaR",
            "model_id": "custom.vol_target_risk",
            "parameters": {"confidence_level": 0.95},
            "width": 2,
            "order": 0
        }
    ]
)
```

---

## 4. Verification & Automated Test Results

### 4.1 Pytest End-to-End Suite (`test_sdk_and_dashboard_e2e.py`)

Execution command:
```bash
PYTHONPATH=backend /opt/anaconda3/bin/pytest backend/tests/test_sdk_and_dashboard_e2e.py -v
```

Observed test output:
```text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.0.3, pluggy-1.6.0 -- /opt/anaconda3/bin/python
cachedir: .pytest_cache
rootdir: /Users/vemanahemanthbabu/srujana_hackathon_2/backend
plugins: anyio-4.12.1, Faker-40.37.0, asyncio-1.4.0
collected 24 items

backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_01_registration_succeeds PASSED [  4%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_02_registry_persists_registration PASSED [  8%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_03_model_appears_in_registry_query PASSED [ 12%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_04_schema_and_capabilities_are_returned PASSED [ 16%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_05_compatible_lab_discovers_without_frontend_change PASSED [ 20%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_06_executes_through_supported_execution_path PASSED [ 25%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_07_real_result_is_persisted_and_retrieved PASSED [ 29%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_08_incompatible_lab_rejects_clearly PASSED [ 33%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_09_invalid_output_fails_validation PASSED [ 37%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestSDKAcceptanceCriteria::test_criterion_10_versioning_preserves_provenance PASSED [ 41%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestAllExtensionTypes::test_01_risk_model PASSED [ 45%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestAllExtensionTypes::test_02_forecasting_model PASSED [ 50%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestAllExtensionTypes::test_03_custom_metric PASSED [ 54%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestAllExtensionTypes::test_04_simulation_engine PASSED [ 58%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestAllExtensionTypes::test_05_trading_strategy PASSED [ 62%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_01_list_dashboards_includes_default PASSED [ 66%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_02_create_custom_dashboard PASSED [ 70%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_03_update_dashboard_reorder_and_resize PASSED [ 75%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_04_duplicate_dashboard PASSED [ 79%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_05_delete_dashboard PASSED [ 83%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_06_widget_catalog_specifications PASSED [ 87%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_07_query_widget_live_calculation PASSED [ 91%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestDashboardPersistenceAndCustomization::test_08_unavailable_widget_state_truthful_reporting PASSED [ 95%]
backend/tests/test_sdk_and_dashboard_e2e.py::TestFull12StepWorkflow::test_complete_12_step_user_journey PASSED [100%]

============================== 24 passed in 0.25s ==============================
```

### 4.2 Regression Test Suite (`test_sdk_and_cli.py`)

Execution command:
```bash
PYTHONPATH=backend /opt/anaconda3/bin/pytest backend/tests/test_sdk_and_cli.py -v
```

Observed test output:
```text
============================== 13 passed in 0.66s ==============================
```

### 4.3 Browser Interaction Verification

- Video artifact recorded: `custom_dashboard_verification_1792975915846.webp`
- Screenshots captured confirming:
  - Header & Diagnostics rendering with NSE ₹10 Lakh portfolio.
  - Active layout rendering 6 widgets with real values and charts.
  - 10-type Widget Catalog modal opening with categorized tabs.
  - Adding Monte Carlo simulation widget to grid.
  - Widget settings modal adjusting titles and parameters.
  - Persistence toast confirming updated configuration saved to disk.

---

## 5. Security & Isolation Boundaries

1. **Untrusted Model Containment**:
   Third-party custom models are treated as untrusted calculations.
   In local research deployment mode (`DEPLOYMENT_MODE="local_research"`), in-process execution is permitted for validated instances.
   In hosted multi-tenant deployment mode (`DEPLOYMENT_MODE="production"`), remote execution strictly enforces container isolation with memory limits, timeouts, and authorization controls. Arbitrary code is never executed directly in the API process.

2. **Zero-Placeholder Guarantee**:
   The calculation engine does not substitute fake `0.00%` values when data is absent or queries fail. Instead, it emits `status: "unavailable"` or `status: "failed"` with explicit warning banners.

3. **Immutable Lineage & Auditability**:
   Every model run creates a unique `run_id` and persists the exact input payload, output metrics, execution duration, and cryptographic SHA-256 fingerprint to `data/catalog/runs/{run_id}.json`. Prior historical runs are never silently overwritten when new versions are registered.

---

## 6. Conclusion

Both required capabilities — the Public Python SDK with model contracts and capability-based registry, and the Customizable Persistent Dashboard Workspace — are completely implemented, integrated end-to-end, and verified through automated tests and interactive browser validation.
