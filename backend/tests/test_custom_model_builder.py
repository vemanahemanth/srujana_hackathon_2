"""Unit and functional tests for ConfigurableCustomModelPlugin and Model Builder.

Verifies:
1. Student-t custom plugin parameter validation and execution.
2. EWMA custom plugin with dynamic decay factor.
3. Cornish-Fisher expansion plugin execution with empirical skew/kurtosis.
4. Historical Quantile plugin with custom interpolation.
5. In-memory registration persistence in get_default_registry().
6. Benchmarking compatibility with dynamically registered plugins.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.benchmarks import BenchmarkSpecification, execute_model_benchmark
from fragility_engine.plugins import (
    ConfigurableCustomModelPlugin,
    get_default_registry,
    reset_default_registry,
)


@pytest.fixture(autouse=True)
def clean_registry():
    reset_default_registry()
    yield
    reset_default_registry()


def test_custom_student_t_model_execution() -> None:
    """Test Student-t custom model parameterization, execution, and outputs."""
    plugin = ConfigurableCustomModelPlugin(
        model_id="student_t_nu4",
        name="Student-t Heavy-Tail (nu=4)",
        family="student_t",
        parameters={"degrees_of_freedom": 4.0},
    )

    meta = plugin.metadata
    assert meta.plugin_id == "student_t_nu4"
    assert "var_95" in meta.capabilities
    assert "expected_shortfall_95" in meta.capabilities

    np.random.seed(42)
    sample_rets = np.random.normal(0.0005, 0.015, 60)
    res = plugin.execute(sample_rets)

    metrics = res.metrics
    assert "var_95" in metrics
    assert "expected_shortfall_95" in metrics
    assert metrics["var_95"] > 0.0
    assert metrics["expected_shortfall_95"] >= metrics["var_95"]


def test_custom_ewma_model_execution() -> None:
    """Test EWMA custom model parameterization and execution."""
    plugin = ConfigurableCustomModelPlugin(
        model_id="ewma_fast",
        name="Fast EWMA (lambda=0.90)",
        family="ewma",
        parameters={"decay_factor": 0.90},
    )

    sample_rets = [0.01, -0.015, 0.02, -0.018, 0.005, -0.007, 0.012, -0.009] * 5
    res = plugin.execute(sample_rets)
    assert "ewma_volatility" in res.metrics
    assert res.metrics["ewma_volatility"] > 0.0


def test_custom_cornish_fisher_execution() -> None:
    """Test Cornish-Fisher semiparametric expansion with empirical skewness/kurtosis."""
    plugin = ConfigurableCustomModelPlugin(
        model_id="cf_custom",
        name="Cornish-Fisher Custom",
        family="cornish_fisher",
    )

    np.random.seed(42)
    sample_rets = np.random.normal(0.001, 0.02, 50)
    res = plugin.execute(sample_rets)

    assert "var_95" in res.metrics
    assert "cornish_fisher_z" in res.metrics
    assert res.metrics["var_95"] > 0.0


def test_custom_historical_quantile_execution() -> None:
    """Test Historical Quantile with configurable interpolation method."""
    plugin = ConfigurableCustomModelPlugin(
        model_id="hq_midpoint",
        name="Historical Quantile Midpoint",
        family="historical_quantile",
        parameters={"method": "midpoint"},
    )

    sample_rets = [0.01, -0.02, 0.015, -0.025, 0.005, -0.01] * 5
    res = plugin.execute(sample_rets)
    assert "var_95" in res.metrics
    assert "expected_shortfall_95" in res.metrics


def test_custom_plugin_parameter_validation_errors() -> None:
    """Check validation for illegal degrees of freedom, decay factors, and families."""
    # Illegal family
    with pytest.raises(ValueError, match="family must be one of"):
        ConfigurableCustomModelPlugin("m1", "M1", family="invalid_family")

    # Degrees of freedom out of [2.5, 100]
    with pytest.raises(ValueError, match="degrees of freedom must be in"):
        ConfigurableCustomModelPlugin("m2", "M2", family="student_t", parameters={"df": 1.5})

    # Decay factor out of [0.80, 0.999]
    with pytest.raises(ValueError, match="decay_factor must be in"):
        ConfigurableCustomModelPlugin("m3", "M3", family="ewma", parameters={"decay_factor": 1.2})


def test_dynamic_registry_and_benchmarking() -> None:
    """Register custom plugin in default registry and include it in benchmark suite."""
    registry = get_default_registry()
    initial_count = len(registry)

    custom_plugin = ConfigurableCustomModelPlugin(
        model_id="student_t_bench",
        name="Benchmarking Student-t",
        family="student_t",
        parameters={"degrees_of_freedom": 5.0},
    )

    registry.register(custom_plugin, overwrite=True)
    assert len(registry) == initial_count + 1
    assert "student_t_bench" in registry

    # Run benchmark including the new custom model
    spec = BenchmarkSpecification(
        benchmark_id="BM-CUSTOM-001",
        name="Custom Model Benchmark",
        description="Testing dynamically registered custom model",
        dataset_id="SYNTH-NSE-60D",
        plugin_ids=("builtin.parametric_gaussian", "builtin.historical_simulation", "student_t_bench"),
        metrics_to_compare=("var_95", "expected_shortfall_95"),
    )

    sample_rets = np.random.normal(0.0005, 0.015, 60)
    report = execute_model_benchmark(spec, sample_rets, registry=registry)

    assert len(report.model_entries) == 3
    result_ids = [r.plugin_id for r in report.model_entries]
    assert "student_t_bench" in result_ids
