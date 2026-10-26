"""FragilityShield — Automated Test Suite for Shared Test Orchestrator & Research Lab.

Covers:
1. Canonical Experiment Data Contract & Deterministic Provenance Hashing
2. Orchestrator Module Registry & Applicability Resolution
3. Test All Execution Mode (with zero fabricated metrics on unsupported tests)
4. Custom Test Profile Execution with Parameter Overrides
5. Resilient Error Handling & Partial Completion Tracking
6. REST API Endpoints & Unified Ledger Propagation
7. Declarative Configuration Registry for Custom Strategies & Scenarios
8. External SDK Ingestion with Automated Orchestration Trigger
"""

import copy
import json
import pytest
from starlette.testclient import TestClient

from backend.app import app
from fragility_engine.orchestrator import (
    CanonicalExperimentRun,
    CanonicalMetric,
    CanonicalTestResult,
    ExperimentType,
    MetricProvenance,
    RunStatus,
    SharedTestOrchestrator,
    SubmissionSource,
    TestStatus,
    get_test_orchestrator,
)
from fragility_engine.custom_configs import (
    ConfigValidationError,
    ConfigurationRegistry,
    CustomScenarioConfig,
    CustomStrategyConfig,
    CustomTestProfileConfig,
    get_config_registry,
)
from fragility_engine.sdk import Client


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def sample_returns():
    return [
        0.012, -0.015, 0.008, -0.022, 0.018, -0.005, 0.009, 0.014, -0.031, 0.025,
        0.003, -0.011, 0.007, -0.019, 0.021, -0.008, 0.013, -0.004, 0.017, -0.028,
        0.019, 0.006, -0.012, 0.015, -0.021, 0.008, -0.009, 0.011, -0.016, 0.022,
        0.005, -0.014, 0.018, -0.025, 0.012, -0.007, 0.019, -0.011, 0.008, -0.015
    ]


# ==============================================================================
# 1. Canonical Schema & Provenance Tests
# ==============================================================================

def test_canonical_run_schema_and_hashing():
    run = CanonicalExperimentRun(
        run_id="run_test_001",
        experiment_id="exp_test_alpha",
        workspace_id="ws_quant",
        display_name="Test Model Run",
        submission_source=SubmissionSource.LOCAL_SDK,
        experiment_type=ExperimentType.MODEL,
        target_identity={"model_id": "test_garch", "asset": "NIFTY_50"},
        dataset_fingerprint="abc123sha256",
        parameters={"alpha": 0.05, "lookback": 60},
    )

    h1 = run.compute_provenance_hash()
    assert isinstance(h1, str)
    assert len(h1) == 64  # SHA-256

    # Hashing is deterministic
    h2 = run.compute_provenance_hash()
    assert h1 == h2

    # Modifying parameters modifies the cryptographic hash
    run.parameters["alpha"] = 0.01
    h3 = run.compute_provenance_hash()
    assert h1 != h3

    # Serialization preserves contract
    d = run.to_dict()
    assert d["run_id"] == "run_test_001"
    assert d["submission_source"] == "local_sdk"
    assert d["is_external"] is True


def test_canonical_metric_and_test_result():
    metric = CanonicalMetric(
        metric_name="var_historical_95pct",
        observed_value=0.0245,
        unit="pct",
        provenance=MetricProvenance.INDEPENDENTLY_RECALCULATED,
    )
    res = CanonicalTestResult(
        module_id="risk_analytics",
        module_name="Risk Analytics Engine",
        status=TestStatus.PASSED,
        metrics={"var_95": metric},
        summary_metric="VaR 95%: 2.45%",
    )
    d = res.to_dict()
    assert d["module_id"] == "risk_analytics"
    assert d["status"] == "passed"
    assert "var_95" in d["metrics"]
    assert d["metrics"]["var_95"]["observed_value"] == 0.0245


# ==============================================================================
# 2. Orchestrator Module Registry & Test Selection
# ==============================================================================

def test_orchestrator_module_registry():
    orch = get_test_orchestrator()
    modules = orch.list_registered_modules()
    assert len(modules) >= 9

    mod_ids = {m["module_id"] for m in modules}
    expected = {
        "data_diagnostics",
        "risk_analytics",
        "scenario_stress",
        "tail_risk_reverse_stress",
        "fragility_assumption_matrix",
        "monte_carlo_simulation",
        "bootstrap_uncertainty",
        "model_validation",
        "strategy_backtesting",
    }
    assert expected.issubset(mod_ids)

    # Verify input requirements and versions
    for m in modules:
        assert "module_id" in m
        assert "description" in m
        assert "version" in m
        assert isinstance(m["supported_types"], list)


def test_orchestrator_applicability_resolution(sample_returns):
    orch = get_test_orchestrator()

    # Model experiment with returns
    app_model = orch.resolve_applicable_tests(
        run_or_type=ExperimentType.MODEL,
        data_inputs={"returns": sample_returns},
    )
    assert "risk_analytics" in app_model
    assert "data_diagnostics" in app_model
    assert "scenario_stress" in app_model
    assert "monte_carlo_simulation" in app_model
    # strategy_backtesting is NOT applicable to a pure MODEL without strategy definition
    assert "strategy_backtesting" not in app_model

    # Strategy experiment with returns
    app_strat = orch.resolve_applicable_tests(
        run_or_type=ExperimentType.STRATEGY,
        data_inputs={"returns": sample_returns},
    )
    assert "strategy_backtesting" in app_strat


# ==============================================================================
# 3. Test All Execution Mode
# ==============================================================================

def test_orchestrator_test_all_execution(sample_returns):
    orch = get_test_orchestrator()
    run = orch.execute_run(
        experiment_id="exp_suite_test_all",
        run_id="run_suite_001",
        submission_source=SubmissionSource.LOCAL_SDK,
        experiment_type=ExperimentType.MODEL,
        target_identity={"model_id": "garch_forecaster", "symbol": "NIFTY_50"},
        data_inputs={"returns": sample_returns},
        profile_id="test_all",
    )

    assert run.run_status == RunStatus.COMPLETED
    assert len(run.test_results) == 9

    # Verify that unsupported test is explicitly marked UNSUPPORTED, NOT PASSED
    strat_test = run.test_results["strategy_backtesting"]
    assert strat_test.status == TestStatus.UNSUPPORTED
    assert "not supported" in strat_test.diagnostics[0].lower()

    # Verify real quantitative calculations for passed modules
    risk_test = run.test_results["risk_analytics"]
    assert risk_test.status == TestStatus.PASSED
    assert "annualized_volatility" in risk_test.metrics
    assert risk_test.metrics["annualized_volatility"].observed_value > 0

    mc_test = run.test_results["monte_carlo_simulation"]
    assert mc_test.status == TestStatus.PASSED
    assert "ruin_probability_20pct_loss" in mc_test.metrics

    evt_test = run.test_results["tail_risk_reverse_stress"]
    assert evt_test.status == TestStatus.PASSED
    assert "sigmas_to_breach_20pct" in evt_test.metrics

    # Verify summary metrics
    summary = run.summary_metrics
    assert summary["passed_tests"] == 8
    assert summary["unsupported_tests"] == 1
    assert summary["failed_tests"] == 0
    assert summary["total_applicable_tests"] == 8


# ==============================================================================
# 4. Custom Test Profile Execution with Parameter Overrides
# ==============================================================================

def test_orchestrator_custom_profile_execution(sample_returns):
    orch = get_test_orchestrator()

    # Execute Basel pack with 99% confidence level
    run = orch.execute_run(
        experiment_id="exp_regulatory_basel",
        run_id="run_basel_001",
        submission_source=SubmissionSource.INTERNAL_UI,
        experiment_type=ExperimentType.MODEL,
        target_identity={"model_id": "internal_var_model"},
        data_inputs={"returns": sample_returns},
        profile_id="regulatory_basel_pack",
        selected_modules=["risk_analytics", "model_validation"],
        config_overrides={"confidence_level": 0.99},
    )

    assert run.run_status == RunStatus.COMPLETED
    assert "risk_analytics" in run.test_results
    assert "model_validation" in run.test_results

    risk_test = run.test_results["risk_analytics"]
    assert risk_test.status == TestStatus.PASSED
    # VaR 99% should be strictly higher than VaR 95%
    var_99 = risk_test.metrics["historical_var_99"].observed_value
    var_95 = risk_test.metrics["historical_var_95"].observed_value
    assert var_99 >= var_95


# ==============================================================================
# 5. Resilient Error Handling & Partial Completion
# ==============================================================================

def test_orchestrator_partial_completion_on_failure():
    orch = get_test_orchestrator()

    # Pass invalid data (empty array for returns)
    run = orch.execute_run(
        experiment_id="exp_failure_test",
        run_id="run_fail_001",
        submission_source=SubmissionSource.INTERNAL_UI,
        experiment_type=ExperimentType.MODEL,
        target_identity={"model_id": "failing_model"},
        data_inputs={"returns": []},
        profile_id="test_all",
    )

    # Empty returns causes failure in fragility_assumption_matrix while scenario_stress handles baseline
    # The run status must accurately be PARTIALLY_COMPLETED, distinguishing partial success from full completion
    assert run.run_status == RunStatus.PARTIALLY_COMPLETED
    assert run.test_results["fragility_assumption_matrix"].status == TestStatus.FAILED
    assert run.summary_metrics["failed_tests"] >= 1


# ==============================================================================
# 6. REST API Endpoints & Unified Ledger Propagation
# ==============================================================================

def test_api_orchestrator_modules_endpoint(test_client):
    resp = test_client.get("/api/orchestrator/modules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] >= 9


def test_api_orchestrator_validate_endpoint(test_client, sample_returns):
    resp = test_client.post(
        "/api/orchestrator/validate",
        json={
            "experiment_type": "model",
            "data": {"returns": sample_returns},
            "profile_id": "test_all",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["applicable_count"] >= 8


def test_api_orchestrator_run_and_registry_propagation(test_client, sample_returns):
    # 1. Run orchestrator
    run_id = f"test_api_orch_{id(sample_returns)}"
    resp = test_client.post(
        "/api/orchestrator/run",
        json={
            "experiment_id": "exp_api_propagation",
            "run_id": run_id,
            "submission_source": "external_api",
            "experiment_type": "model",
            "target_identity": {"model_id": "api_test_model", "symbol": "NIFTY_50"},
            "data": {"returns": sample_returns},
            "profile_id": "test_all",
        },
    )
    assert resp.status_code == 200
    orch_data = resp.json()
    assert orch_data["run_id"] == run_id
    assert orch_data["run_status"] == "completed"

    # 2. Check get_run endpoint
    resp_get = test_client.get(f"/api/orchestrator/runs/{run_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["run_id"] == run_id

    # 3. Verify propagation into Unified Experiment Registry (/api/experiments/runs)
    resp_reg = test_client.get("/api/experiments/runs")
    assert resp_reg.status_code == 200
    reg_data = resp_reg.json()
    assert reg_data["success"] is True

    matched_run = next((r for r in reg_data["runs"] if r["run_id"] == run_id), None)
    assert matched_run is not None, f"Orchestrated run '{run_id}' not found in registry!"
    assert matched_run["run_type"] == "orchestrated_test_suite"
    assert "metrics_summary" in matched_run
    assert matched_run["metrics_summary"]["passed_tests"] >= 8


# ==============================================================================
# 7. Declarative Configuration Registry Tests
# ==============================================================================

def test_custom_configuration_registry_validation():
    registry = get_config_registry()

    # Pre-seeded configurations
    strategies = registry.list_strategies()
    assert len(strategies) >= 2
    scenarios = registry.list_scenarios()
    assert len(scenarios) >= 3
    profiles = registry.list_profiles()
    assert len(profiles) >= 3

    # Save a valid custom strategy
    custom_strat = CustomStrategyConfig(
        strategy_id="strat_momentum_rsi_custom",
        name="RSI Momentum Breakout",
        description="RSI 14-period momentum strategy",
        author="quant_researcher",
        parameters={"rsi_period": {"default": 14, "type": "int", "min": 2, "max": 100}},
        cost_model={"fee_bps": 5.0, "slippage_bps": 2.5},
        position_sizing={"method": "fixed_pct", "value": 0.05, "max_leverage": 1.0},
        risk_limits={"stop_loss_pct": 3.0, "max_drawdown_limit": 15.0},
    )
    registry.save_strategy(custom_strat)
    retrieved = registry.get_strategy("strat_momentum_rsi_custom")
    assert retrieved is not None
    assert retrieved.name == "RSI Momentum Breakout"

    # Verify security: strict rejection of invalid parameters (no eval/exec possible)
    with pytest.raises(ConfigValidationError):
        CustomScenarioConfig.from_dict({
            "scenario_id": "bad_sc",
            "name": "Bad Scenario",
            "shocks": {"equity_shock": "DROP_TABLE;--"},  # Non-numeric shock rejected
        })


def test_api_custom_configuration_endpoints(test_client):
    # GET strategies
    res_s = test_client.get("/api/configurations/strategies")
    assert res_s.status_code == 200
    assert res_s.json()["count"] >= 2

    # GET scenarios
    res_sc = test_client.get("/api/configurations/scenarios")
    assert res_sc.status_code == 200
    assert res_sc.json()["count"] >= 3

    # POST new scenario
    res_new_sc = test_client.post(
        "/api/configurations/scenarios",
        json={
            "scenario_id": "sc_custom_stagflation",
            "name": "Stagflation Crisis 2026",
            "description": "Macro stagflation rate and equity shock",
            "shocks": {"equity_drawdown": -0.22, "volatility_multiplier": 2.2, "yield_shift_bps": 150},
        },
    )
    assert res_new_sc.status_code == 201
    assert res_new_sc.json()["scenario"]["scenario_id"] == "sc_custom_stagflation"


# ==============================================================================
# 8. External SDK Ingestion with Automated Test Orchestrator
# ==============================================================================

def test_external_sdk_auto_test_all_trigger(sample_returns):
    client = Client()

    # Submit external run with auto_test_all=True
    run_id = f"colab_auto_orch_{id(sample_returns)}"
    sub_res = client.external.submit_run(
        experiment_id="exp_colab_deep_alpha",
        run_id=run_id,
        model_id="colab_vol_model",
        target_lab="model_validation",
        metrics=[{"metric_name": "rmse", "observed_value": 0.0125}],
        predictions=[{
            "index": i,
            "timestamp": f"2026-03-01T10:0{i}:00Z",
            "y_true": float(r),
            "y_pred": float(r)*0.95
        } for i, r in enumerate(sample_returns[:10])],
        returns=sample_returns,
        auto_test_all=True,
    )

    assert sub_res.success is True
    assert sub_res.run_id == run_id
