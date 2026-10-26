"""Tests for Lab 2 Model and Integration Lab (Blueprint §2, §4)."""

import pytest
import numpy as np

from fragility_engine.model_lab import (
    IntegrationTestResult,
    IntegrationTestStatus,
    ModelIntegrationReport,
    run_determinism_test,
    run_error_handling_test,
    run_input_contract_test,
    run_model_integration_suite,
    run_model_smoke_test,
    run_numeric_validity_test,
    run_output_contract_test,
    run_timeout_test,
    run_version_change_test,
)
from fragility_engine.projects import ModelFamily, ModelManifest


def dummy_linear_model(inputs: np.ndarray) -> np.ndarray:
    """Deterministic linear predictor."""
    return np.asarray(inputs, dtype=np.float64) * 2.5 + 1.0


def dummy_stochastic_model(inputs: np.ndarray) -> np.ndarray:
    """Non-deterministic predictor."""
    return np.asarray(inputs, dtype=np.float64) + np.random.uniform(0.01, 0.05, size=len(inputs))


def dummy_dict_model(inputs: np.ndarray) -> dict:
    """Returns structured risk metrics."""
    arr = np.asarray(inputs, dtype=np.float64)
    return {
        "volatility": float(np.std(arr)),
        "mean": float(np.mean(arr)),
    }


def test_smoke_test_pass_and_fail() -> None:
    res = run_model_smoke_test(dummy_linear_model, np.array([1.0, 2.0, 3.0]))
    assert res.status == IntegrationTestStatus.PASS
    assert "Smoke test passed" in res.message
    assert res.execution_time_ms >= 0.0

    def failing_model(x):
        raise RuntimeError("Out of memory simulated failure")

    fail_res = run_model_smoke_test(failing_model, [1, 2, 3])
    assert fail_res.status == IntegrationTestStatus.FAIL
    assert "Out of memory" in fail_res.message


def test_input_contract_test() -> None:
    manifest = ModelManifest(
        model_id="multi_factor_risk",
        name="Multi Factor Risk",
        required_inputs=("timestamp", "returns", "market_cap", "sector"),
    )

    pass_res = run_input_contract_test(manifest, ["TIMESTAMP", "returns", "market_cap", "SECTOR", "extra_col"])
    assert pass_res.status == IntegrationTestStatus.PASS

    fail_res = run_input_contract_test(manifest, ["timestamp", "returns"])
    assert fail_res.status == IntegrationTestStatus.FAIL
    assert "market_cap" in str(fail_res.details)


def test_output_contract_test() -> None:
    manifest = ModelManifest(
        model_id="dict_risk",
        name="Dict Risk",
        expected_output_schema={"volatility": "float", "mean": "float"},
    )

    out = dummy_dict_model(np.array([0.01, -0.02, 0.03]))
    pass_res = run_output_contract_test(manifest, out)
    assert pass_res.status == IntegrationTestStatus.PASS

    # Missing schema key
    bad_out = {"volatility": 0.05}
    fail_res = run_output_contract_test(manifest, bad_out)
    assert fail_res.status == IntegrationTestStatus.FAIL


def test_numeric_validity_test() -> None:
    valid_res = run_numeric_validity_test(np.array([1.0, 2.5, -0.8, 4.2]))
    assert valid_res.status == IntegrationTestStatus.PASS

    nan_res = run_numeric_validity_test(np.array([1.0, np.nan, 3.0]))
    assert nan_res.status == IntegrationTestStatus.FAIL
    assert nan_res.details["nan_count"] == 1

    inf_res = run_numeric_validity_test(np.array([1.0, np.inf, 3.0]))
    assert inf_res.status == IntegrationTestStatus.FAIL
    assert inf_res.details["inf_count"] == 1


def test_determinism_test() -> None:
    # Deterministic model passes
    det_res = run_determinism_test(dummy_linear_model, np.array([1.0, 2.0, 3.0]), repetitions=3)
    assert det_res.status == IntegrationTestStatus.PASS

    # Stochastic model fails determinism
    stoch_res = run_determinism_test(dummy_stochastic_model, np.array([1.0, 2.0, 3.0]), repetitions=3)
    assert stoch_res.status == IntegrationTestStatus.FAIL


def test_error_handling_test() -> None:
    def validating_model(x):
        if not isinstance(x, (list, tuple, np.ndarray)):
            raise TypeError("Expected sequence input")
        if len(x) == 0:
            raise ValueError("Sequence cannot be empty")
        return sum(x)

    res = run_error_handling_test(validating_model, ["bad_string", [], 12345])
    assert res.status == IntegrationTestStatus.PASS
    assert res.details["controlled_catches"] == 3


def test_timeout_test() -> None:
    import time

    def fast_model(x):
        return x

    def slow_model(x):
        time.sleep(0.05)
        return x

    fast_res = run_timeout_test(fast_model, [1, 2], timeout_sec=0.10)
    assert fast_res.status == IntegrationTestStatus.PASS

    slow_res = run_timeout_test(slow_model, [1, 2], timeout_sec=0.01)
    assert slow_res.status == IntegrationTestStatus.FAIL


def test_version_change_test() -> None:
    v1 = ModelManifest(
        model_id="model_a",
        name="Model A",
        version="1.0.0",
        required_inputs=("returns",),
        expected_output_schema={"volatility": "float"},
    )
    v2_compatible = ModelManifest(
        model_id="model_a",
        name="Model A",
        version="1.1.0",
        required_inputs=("returns",),
        expected_output_schema={"volatility": "float", "var": "float"},
    )
    v2_breaking = ModelManifest(
        model_id="model_a",
        name="Model A",
        version="2.0.0",
        required_inputs=("returns", "new_required_field"),
        expected_output_schema={"volatility": "int"},  # changed type
    )

    compat_res = run_version_change_test(v1, v2_compatible)
    assert compat_res.status == IntegrationTestStatus.PASS

    break_res = run_version_change_test(v1, v2_breaking)
    assert break_res.status == IntegrationTestStatus.WARNING
    assert len(break_res.details["breaking_changes"]) == 2


def test_full_model_integration_suite() -> None:
    manifest = ModelManifest(
        model_id="production_factor_risk",
        name="Production Factor Risk Model",
        version="1.0.0",
        required_inputs=("returns", "weights"),
        expected_output_schema={"volatility": "float", "mean": "float"},
        runtime_limits={"timeout_sec": 2.0},
        code_isolation_required=True,
    )

    report = run_model_integration_suite(
        model_callable=dummy_dict_model,
        manifest=manifest,
        sample_input=np.array([0.01, -0.02, 0.015, -0.005, 0.02]),
        provided_columns=["returns", "weights", "sector"],
        malformed_inputs=["not_an_array"],
    )

    assert report.model_id == "production_factor_risk"
    assert report.passed >= 4
    assert report.failed == 0
    assert report.isolation_status == "Isolated Worker Required"
    data = report.to_dict()
    assert data["tests_run"] == len(report.results)
