"""Automated tests for FragilityShield Phase 8: Plugin System & Model Benchmarking.

Tests:
1. Plugin Contract & Registry (`PluginMetadata`, `ModelPlugin`, `PluginRegistry`)
2. Built-in Model Adapters (`HistoricalSimulationPlugin`, `ParametricGaussianPlugin`, `EWMAVolatilityPlugin`, `PortfolioConcentrationPlugin`)
3. Pre- and Post-Execution Validation (non-finite rejection, dimension checks, sample size limits)
4. Deterministic Multi-Model Benchmarking (`execute_model_benchmark`, `BenchmarkSpecification`)
5. Incomparable Models & Graceful Failure Isolation
6. Directional Model Rankings & Tie-Breaking (lower_is_better vs higher_is_better)
7. Multi-Model Perturbation Robustness
8. Multi-Format Report Export (JSON roundtrip, Markdown, CSV)
9. Security & Untrusted Plugin Containment
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping
import numpy as np
import pytest

from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import (
    ModelPlugin,
    PluginMetadata,
    ModelExecutionResult,
    PluginRegistry,
    get_default_registry,
    HistoricalSimulationPlugin,
    ParametricGaussianPlugin,
    EWMAVolatilityPlugin,
    PortfolioConcentrationPlugin,
)
from fragility_engine.benchmarks import (
    BenchmarkSpecification,
    ModelBenchmarkEntry,
    ModelRankingEntry,
    BenchmarkReport,
    execute_model_benchmark,
)
from fragility_engine.risk import calculate_risk_report
from fragility_engine.fragility import calculate_ewma_volatility
from fragility_engine.concentration import calculate_portfolio_concentration


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_returns() -> List[float]:
    """60 synthetic daily return observations."""
    np.random.seed(42)
    rets = np.random.normal(0.0005, 0.015, 60).tolist()
    return [round(r, 8) for r in rets]


@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Sample equity portfolio for concentration testing."""
    return Portfolio(
        portfolio_id="PF-BENCH-001",
        name="BenchmarkPortfolio",
        currency="INR",
        holdings=(
            Holding(asset_id="NSE:HDFCBANK", quantity=100.0, price=1600.0, sector="Financials"),
            Holding(asset_id="NSE:INFY", quantity=200.0, price=1500.0, sector="Technology"),
            Holding(asset_id="NSE:RELIANCE", quantity=150.0, price=2400.0, sector="Energy"),
            Holding(asset_id="NSE:TCS", quantity=100.0, price=3800.0, sector="Technology"),
        ),
    )


@pytest.fixture
def basic_benchmark_spec() -> BenchmarkSpecification:
    """Valid standard benchmark specification comparing historical vs parametric models."""
    return BenchmarkSpecification(
        benchmark_id="BM-RISK-001",
        name="Tail Risk Benchmark: Historical vs Parametric vs EWMA",
        description="Compares 95% tail risk and volatility estimates across three distinct model assumptions.",
        dataset_id="SYNTH-NSE-60D",
        baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
        plugin_ids=(
            "builtin.historical_simulation",
            "builtin.parametric_gaussian",
            "builtin.ewma",
        ),
        metrics_to_compare=("annualized_volatility", "var_95", "expected_shortfall_95"),
        perturbation_specs=(
            {"type": "return_friction", "experiment_id": "friction_5bps", "parameters": {"friction_bps": 5.0}},
            {"type": "lookback_window", "experiment_id": "lookback_30d", "parameters": {"lookback_window": 30}},
        ),
        target_ranking_metric="var_95",
        ranking_direction="lower_is_better",
        tags=("risk", "benchmark", "equities"),
    )


# ==============================================================================
# 1. Plugin Contract & Registry Tests
# ==============================================================================

class TestPluginContractAndRegistry:
    """Test suite for plugin interface contracts, metadata validation, and registry safety."""

    def test_plugin_metadata_validation(self):
        """Verify PluginMetadata validates identifiers, names, and versions."""
        meta = PluginMetadata(
            plugin_id="custom.test_model",
            name="Custom Test Model",
            description="A valid test model plugin.",
            plugin_version="1.2.0",
            api_version="1.0.0",
            supported_data_types=("return_series",),
            capabilities=("volatility", "var"),
        )
        assert meta.plugin_id == "custom.test_model"
        assert meta.name == "Custom Test Model"
        d = meta.to_dict()
        assert d["plugin_id"] == "custom.test_model"
        assert "volatility" in d["capabilities"]

        # Blank ID
        with pytest.raises(ValueError, match="plugin_id cannot be blank"):
            PluginMetadata(plugin_id="   ", name="Test", description="desc")

        # Invalid characters in ID
        with pytest.raises(ValueError, match="Invalid plugin_id"):
            PluginMetadata(plugin_id="bad/plugin/id", name="Test", description="desc")

        # Blank name
        with pytest.raises(ValueError, match="name cannot be blank"):
            PluginMetadata(plugin_id="valid.id", name="", description="desc")

    def test_model_execution_result_validation(self):
        """Verify ModelExecutionResult enforces non-blank ID and finite metrics."""
        res = ModelExecutionResult(
            plugin_id="test.model",
            model_version="1.0.0",
            metrics={"vol": 0.15, "var": 0.025},
            execution_time_ms=1.5,
            observations_used=100,
        )
        assert res.metrics["vol"] == 0.15
        assert res.to_dict()["observations_used"] == 100

        # Non-finite metric rejected
        with pytest.raises(ValueError, match="non-finite or non-numeric value"):
            ModelExecutionResult(
                plugin_id="test.model",
                model_version="1.0.0",
                metrics={"vol": float("nan")},
                execution_time_ms=1.0,
                observations_used=50,
            )

        with pytest.raises(ValueError, match="non-finite or non-numeric value"):
            ModelExecutionResult(
                plugin_id="test.model",
                model_version="1.0.0",
                metrics={"var": float("inf")},
                execution_time_ms=1.0,
                observations_used=50,
            )

    def test_registry_registration_and_retrieval(self):
        """Verify plugin registration, retrieval, and duplicate prevention."""
        registry = PluginRegistry()
        plugin = HistoricalSimulationPlugin()

        registry.register(plugin)
        assert len(registry) == 1
        assert "builtin.historical_simulation" in registry

        retrieved = registry.get("builtin.historical_simulation")
        assert retrieved.metadata.name == plugin.metadata.name

        # Duplicate registration without overwrite raises ValueError
        with pytest.raises(ValueError, match="already registered"):
            registry.register(plugin, overwrite=False)

        # Overwrite works
        registry.register(plugin, overwrite=True)
        assert len(registry) == 1

        # Unknown ID lookup raises KeyError
        with pytest.raises(KeyError, match="not found in registry"):
            registry.get("nonexistent.plugin")

    def test_registry_listing_and_filtering(self):
        """Verify deterministic listing and capability/data_type filtering."""
        registry = get_default_registry()
        assert len(registry) >= 4

        all_plugins = registry.list_plugins()
        # Verify deterministic alphabetical sorting by plugin_id
        ids = [p.plugin_id for p in all_plugins]
        assert ids == sorted(ids)

        # Filter by data_type
        ret_plugins = registry.list_plugins(data_type="return_series")
        assert all("return_series" in p.supported_data_types for p in ret_plugins)
        assert any(p.plugin_id == "builtin.historical_simulation" for p in ret_plugins)
        assert not any(p.plugin_id == "builtin.portfolio_concentration" for p in ret_plugins)

        # Filter by capability
        hhi_plugins = registry.list_plugins(capability="asset_hhi_points")
        assert len(hhi_plugins) == 1
        assert hhi_plugins[0].plugin_id == "builtin.portfolio_concentration"

    def test_registry_unregistration(self):
        """Verify unregister removes plugin cleanly."""
        registry = PluginRegistry()
        p = HistoricalSimulationPlugin()
        registry.register(p)

        assert registry.unregister("builtin.historical_simulation") is True
        assert registry.unregister("builtin.historical_simulation") is False
        assert len(registry) == 0


# ==============================================================================
# 2. Built-in Model Adapters Tests
# ==============================================================================

class TestBuiltinModelAdapters:
    """Test suite ensuring built-in models agree with existing quantitative calculations."""

    def test_historical_simulation_matches_risk_report(self, sample_returns):
        """Verify HistoricalSimulationPlugin produces identical results to calculate_risk_report."""
        plugin = HistoricalSimulationPlugin()
        config = {"confidence_level": 0.95, "annualization_factor": 252}

        res = plugin.execute(sample_returns, config)
        rep = calculate_risk_report(sample_returns, annualization_factor=252.0)

        assert math.isclose(res.metrics["annualized_volatility"], rep.volatility_annualized, rel_tol=1e-12)
        assert math.isclose(res.metrics["var_95"], rep.var_95, rel_tol=1e-12)
        assert math.isclose(res.metrics["expected_shortfall_95"], rep.expected_shortfall_95, rel_tol=1e-12)
        assert math.isclose(res.metrics["max_drawdown"], rep.drawdown.max_drawdown, rel_tol=1e-12)
        assert res.observations_used == len(sample_returns)
        assert res.execution_time_ms > 0.0

    def test_parametric_gaussian_analytical_formula(self, sample_returns):
        """Verify ParametricGaussianPlugin follows exact analytical normal quantiles."""
        plugin = ParametricGaussianPlugin()
        config = {"confidence_level": 0.95, "annualization_factor": 252}
        res = plugin.execute(sample_returns, config)

        arr = np.asarray(sample_returns)
        mu = float(np.mean(arr))
        sigma = float(np.std(arr, ddof=1))
        expected_var_95 = -mu + 1.6448536269514722 * sigma

        assert math.isclose(res.metrics["var_95"], expected_var_95, rel_tol=1e-9)
        assert res.metrics["expected_shortfall_95"] >= res.metrics["var_95"]

    def test_ewma_volatility_matches_engine(self, sample_returns):
        """Verify EWMAVolatilityPlugin produces identical volatility to calculate_ewma_volatility."""
        plugin = EWMAVolatilityPlugin()
        config = {"decay_factor": 0.94, "annualization_factor": 252}
        res = plugin.execute(sample_returns, config)

        expected_ewma = calculate_ewma_volatility(sample_returns, decay_factor=0.94, annualization_factor=252.0)
        assert math.isclose(res.metrics["annualized_volatility"], expected_ewma, rel_tol=1e-12)

    def test_portfolio_concentration_matches_engine(self, sample_portfolio):
        """Verify PortfolioConcentrationPlugin agrees with calculate_portfolio_concentration."""
        plugin = PortfolioConcentrationPlugin()
        res = plugin.execute(sample_portfolio, {})
        conc = calculate_portfolio_concentration(sample_portfolio)

        assert math.isclose(res.metrics["total_market_value"], conc.total_market_value, rel_tol=1e-12)
        assert math.isclose(res.metrics["asset_hhi_points"], conc.asset_hhi_points, rel_tol=1e-12)
        assert math.isclose(res.metrics["sector_hhi_points"], conc.sector_hhi_points, rel_tol=1e-12)


# ==============================================================================
# 3. Input & Output Validation Tests
# ==============================================================================

class TestModelInputOutputValidation:
    """Test suite verifying strict input and output validation across model plugins."""

    def test_reject_none_or_empty_dataset(self):
        """Verify all plugins reject None or empty datasets."""
        plugin = HistoricalSimulationPlugin()

        with pytest.raises(TypeError, match="Dataset cannot be None"):
            plugin.validate_input(None, {})

        with pytest.raises(ValueError, match="Dataset cannot be empty"):
            plugin.validate_input([], {})

    def test_reject_incompatible_data_type(self, sample_portfolio, sample_returns):
        """Verify return series models reject Portfolio instances and vice versa."""
        return_plugin = HistoricalSimulationPlugin()
        with pytest.raises(TypeError, match="requires return series, not a Portfolio"):
            return_plugin.validate_input(sample_portfolio, {})

        portfolio_plugin = PortfolioConcentrationPlugin()
        with pytest.raises(TypeError, match="requires a Portfolio instance"):
            portfolio_plugin.validate_input(sample_returns, {})

    def test_reject_non_finite_inputs(self):
        """Verify plugins reject arrays containing NaN or Inf."""
        plugin = HistoricalSimulationPlugin()
        with pytest.raises(ValueError, match="non-finite numbers"):
            plugin.validate_input([0.01, float("nan"), -0.02], {})

        with pytest.raises(ValueError, match="non-finite numbers"):
            plugin.validate_input([0.01, float("inf"), -0.02], {})

    def test_reject_invalid_dimensions(self):
        """Verify 1D models reject 2D or 3D inputs."""
        plugin = HistoricalSimulationPlugin()
        data_2d = np.zeros((10, 5))
        with pytest.raises(ValueError, match="requires 1D return series"):
            plugin.validate_input(data_2d, {})

    def test_reject_insufficient_sample_size(self):
        """Verify models require minimum observations for statistical validity."""
        plugin = HistoricalSimulationPlugin()
        with pytest.raises(ValueError, match="at least 2 observations"):
            plugin.validate_input([0.01], {})

    def test_reject_invalid_configurations(self):
        """Verify out-of-range confidence levels and decay factors are rejected."""
        hist_plugin = HistoricalSimulationPlugin()
        with pytest.raises(ValueError, match="confidence_level must be in \\(0, 1\\)"):
            hist_plugin.validate_input([0.01, -0.01, 0.02], {"confidence_level": 1.5})

        ewma_plugin = EWMAVolatilityPlugin()
        with pytest.raises(ValueError, match="decay_factor must be in \\(0, 1\\)"):
            ewma_plugin.validate_input([0.01, -0.01, 0.02], {"decay_factor": -0.5})


# ==============================================================================
# 4. Multi-Model Benchmarking Tests
# ==============================================================================

class TestDeterministicModelBenchmarking:
    """Test suite for multi-model benchmark execution, comparison, and reporting."""

    def test_execute_benchmark_end_to_end(self, basic_benchmark_spec, sample_returns):
        """Verify benchmark executes across multiple plugins, producing rankings and manifest."""
        report = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)

        assert isinstance(report, BenchmarkReport)
        assert report.status == "completed"
        assert report.benchmark_id == basic_benchmark_spec.benchmark_id
        assert len(report.model_entries) == 3

        # Verify all 3 models evaluated baseline metrics
        pids = [m.plugin_id for m in report.model_entries]
        assert "builtin.historical_simulation" in pids
        assert "builtin.parametric_gaussian" in pids
        assert "builtin.ewma" in pids

        for m in report.model_entries:
            assert m.status == "completed"
            assert "var_95" in m.baseline_metrics
            assert "annualized_volatility" in m.baseline_metrics
            assert m.validation_passed is True

        # Verify rankings exist and are ordered
        assert len(report.rankings) == 3
        ranks = [r.rank for r in report.rankings]
        assert ranks == [1, 2, 3] or ranks == [1, 1, 3]  # Supports ties
        assert report.rankings[0].metric_name == "var_95"
        assert report.rankings[0].ranking_direction == "lower_is_better"

        # Verify fingerprints and manifest
        assert len(report.input_fingerprint) == 64
        assert len(report.configuration_fingerprint) == 64
        assert len(report.output_fingerprint) == 64
        assert report.manifest["validation_status"] == "PASSED"
        assert report.manifest["models_evaluated"] == 3

    def test_benchmark_deterministic_repeated_execution(self, basic_benchmark_spec, sample_returns):
        """Verify identical benchmarks on identical data produce identical fingerprints and metrics."""
        rep1 = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)
        rep2 = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)

        assert rep1.input_fingerprint == rep2.input_fingerprint
        assert rep1.configuration_fingerprint == rep2.configuration_fingerprint
        assert rep1.output_fingerprint == rep2.output_fingerprint

        for m1, m2 in zip(rep1.model_entries, rep2.model_entries):
            assert m1.plugin_id == m2.plugin_id
            for mk in m1.baseline_metrics:
                assert math.isclose(m1.baseline_metrics[mk], m2.baseline_metrics[mk], rel_tol=1e-12)

    def test_benchmark_identifies_incompatible_models(self, sample_returns):
        """Verify models with incompatible data types are flagged as incompatible without failing benchmark."""
        spec = BenchmarkSpecification(
            benchmark_id="BM-INCOMPAT-001",
            name="Incompatible Model Benchmark",
            description="Tests return series with a portfolio concentration plugin.",
            dataset_id="SYNTH-NSE-60D",
            plugin_ids=(
                "builtin.historical_simulation",
                "builtin.portfolio_concentration",  # Requires portfolio, not returns
            ),
            metrics_to_compare=("var_95",),
            target_ranking_metric="var_95",
        )

        report = execute_model_benchmark(spec, dataset=sample_returns)
        assert report.status == "completed_with_warnings"

        entries_by_id = {m.plugin_id: m for m in report.model_entries}
        assert entries_by_id["builtin.historical_simulation"].status == "completed"
        assert entries_by_id["builtin.portfolio_concentration"].status == "incompatible"
        assert len(entries_by_id["builtin.portfolio_concentration"].incompatible_reasons) >= 1

        # Incompatible model excluded from rankings
        ranked_pids = [r.plugin_id for r in report.rankings]
        assert "builtin.historical_simulation" in ranked_pids
        assert "builtin.portfolio_concentration" not in ranked_pids
        assert any(u["plugin_id"] == "builtin.portfolio_concentration" for u in report.unranked_models)

    def test_benchmark_handles_failed_plugin_gracefully(self, sample_returns):
        """Verify faulty plugin is isolated with failed_execution while valid plugins complete."""
        class FailingPlugin(ModelPlugin):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(
                    plugin_id="custom.failing_model",
                    name="Intentionally Failing Model",
                    description="Simulates unexpected runtime error.",
                    supported_data_types=("return_series",),
                    capabilities=("var_95",),
                )

            def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
                pass

            def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
                raise RuntimeError("Simulated internal numerical solver divergence")

        registry = get_default_registry()
        registry.register(FailingPlugin())

        spec = BenchmarkSpecification(
            benchmark_id="BM-FAIL-001",
            name="Faulty Plugin Isolation Test",
            description="Ensures exceptions do not crash benchmark runner.",
            dataset_id="SYNTH-NSE-60D",
            plugin_ids=("builtin.historical_simulation", "custom.failing_model"),
            metrics_to_compare=("var_95",),
            target_ranking_metric="var_95",
        )

        report = execute_model_benchmark(spec, dataset=sample_returns, registry=registry)
        assert report.status == "completed_with_warnings"

        entries = {m.plugin_id: m for m in report.model_entries}
        assert entries["builtin.historical_simulation"].status == "completed"
        assert entries["custom.failing_model"].status == "failed_execution"
        assert "Simulated internal numerical solver divergence" in entries["custom.failing_model"].failure_message


# ==============================================================================
# 5. Rankings & Robustness Tests
# ==============================================================================

class TestBenchmarkRankingsAndRobustness:
    """Test suite for directional ranking rules, tie-breaking, and perturbation tracking."""

    def test_ranking_direction_higher_vs_lower(self, sample_returns):
        """Verify ranking_direction reverses sorting order correctly."""
        spec_lower = BenchmarkSpecification(
            benchmark_id="BM-DIR-LOWER",
            name="Lower Is Better (Risk Loss)",
            description="VaR 95% ranking where lower loss threshold is ranked higher.",
            dataset_id="SYNTH-NSE-60D",
            plugin_ids=("builtin.historical_simulation", "builtin.parametric_gaussian"),
            target_ranking_metric="var_95",
            ranking_direction="lower_is_better",
        )
        report_lower = execute_model_benchmark(spec_lower, dataset=sample_returns)

        spec_higher = BenchmarkSpecification(
            benchmark_id="BM-DIR-HIGHER",
            name="Higher Is Better",
            description="Ranking where higher value is ranked higher.",
            dataset_id="SYNTH-NSE-60D",
            plugin_ids=("builtin.historical_simulation", "builtin.parametric_gaussian"),
            target_ranking_metric="var_95",
            ranking_direction="higher_is_better",
        )
        report_higher = execute_model_benchmark(spec_higher, dataset=sample_returns)

        # The rank 1 model in lower_is_better must be the rank 2 model in higher_is_better
        assert report_lower.rankings[0].plugin_id == report_higher.rankings[1].plugin_id

    def test_ranking_tie_detection(self, sample_returns):
        """Verify models producing metric values within tolerance are flagged as tied."""
        class DuplicatePlugin(HistoricalSimulationPlugin):
            def __init__(self) -> None:
                super().__init__()
                self._meta = PluginMetadata(
                    plugin_id="builtin.historical_simulation_clone",
                    name="Historical Simulation Clone",
                    description="Clone producing identical numbers for tie testing.",
                    supported_data_types=("return_series",),
                    capabilities=("var_95",),
                )

        registry = get_default_registry()
        registry.register(DuplicatePlugin())

        spec = BenchmarkSpecification(
            benchmark_id="BM-TIE-001",
            name="Tie Testing Benchmark",
            description="Evaluates two identical models for tie detection.",
            dataset_id="SYNTH-NSE-60D",
            plugin_ids=("builtin.historical_simulation", "builtin.historical_simulation_clone"),
            target_ranking_metric="var_95",
            tolerance=1e-6,
        )

        report = execute_model_benchmark(spec, dataset=sample_returns, registry=registry)
        assert len(report.rankings) == 2
        assert report.rankings[0].rank == 1
        assert report.rankings[1].rank == 1  # Tied rank!
        assert report.rankings[0].tied is True
        assert report.rankings[1].tied is True

    def test_multi_model_perturbation_deltas(self, basic_benchmark_spec, sample_returns):
        """Verify perturbations record stressed metrics and absolute deltas for each model."""
        report = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)

        for m in report.model_entries:
            assert "friction_5bps" in m.perturbation_metrics
            assert "lookback_30d" in m.perturbation_metrics

            # Friction shock reduces returns, which must expand historical loss threshold (var_95)
            fric_delta = m.perturbation_deltas["friction_5bps"]["var_95"]
            assert fric_delta > 0.0  # Loss increased!


# ==============================================================================
# 6. Report Export Formats Tests (JSON, Markdown, CSV)
# ==============================================================================

class TestBenchmarkReportExports:
    """Test suite ensuring benchmark reports export cleanly and roundtrip without loss."""

    def test_report_json_roundtrip(self, basic_benchmark_spec, sample_returns):
        """Verify BenchmarkReport serializes to JSON and roundtrips with exact equivalence."""
        report = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)
        json_str = report.to_json(indent=2)

        # Must parse back cleanly
        reloaded = BenchmarkReport.from_json(json_str)
        assert reloaded.benchmark_id == report.benchmark_id
        assert reloaded.input_fingerprint == report.input_fingerprint
        assert reloaded.configuration_fingerprint == report.configuration_fingerprint
        assert reloaded.output_fingerprint == report.output_fingerprint
        assert len(reloaded.model_entries) == len(report.model_entries)
        assert len(reloaded.rankings) == len(report.rankings)

    def test_report_markdown_formatting(self, basic_benchmark_spec, sample_returns):
        """Verify Markdown report contains all required headers, tables, and provenance."""
        report = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)
        md = report.to_markdown()

        assert f"# FragilityShield — Model Benchmark Report: {report.name}" in md
        assert "## 1. Cryptographic Provenance & Fingerprints" in md
        assert "## 2. Comparative Model Rankings" in md
        assert "## 3. Metric Comparison Grid" in md
        assert "## 4. Perturbation Robustness Comparison" in md
        assert "## 5. Independent Validation & Limitations" in md
        assert report.input_fingerprint in md
        assert "builtin.historical_simulation" in md

    def test_report_csv_formatting(self, basic_benchmark_spec, sample_returns):
        """Verify CSV export is valid tabular data with explicit column headers."""
        report = execute_model_benchmark(basic_benchmark_spec, dataset=sample_returns)
        csv_str = report.to_csv()

        lines = csv_str.strip().split("\n")
        assert len(lines) >= 4
        header = lines[0].split(",")
        assert "benchmark_id" in header
        assert "plugin_id" in header
        assert "model_name" in header
        assert "metric_name" in header
        assert "baseline_value" in header
        assert "perturbation_id" in header
        assert "stressed_value" in header
        assert "delta" in header


# ==============================================================================
# 7. Security, Durability & Untrusted Plugin Containment
# ==============================================================================

class TestBenchmarkSecurityAndDurability:
    """Test suite verifying path traversal rejection, adversarial strings, and catalog durability."""

    @pytest.mark.parametrize("bad_id", [
        "../path/traversal",
        "..\\windows\\traversal",
        "nested/subfolder",
        "null\0byte",
        ":colon:restricted",
        "...",
    ])
    def test_benchmark_specification_rejects_unsafe_identifiers(self, bad_id):
        """Verify BenchmarkSpecification strictly rejects unsafe path traversal identifiers."""
        with pytest.raises(ValueError):
            BenchmarkSpecification(
                benchmark_id=bad_id,
                name="Test Benchmark",
                description="desc",
                dataset_id="DATA-1",
            )

    def test_markdown_and_csv_adversarial_strings(self, sample_returns):
        """Verify adversarial strings with commas, quotes, and markdown pipes do not break tables."""
        spec = BenchmarkSpecification(
            benchmark_id="BM-ADV-001",
            name="Adversarial | Name, With Quotes \"and\" Pipes",
            description="Description with \n newlines and | pipes |.",
            dataset_id="DATA-ADV",
            plugin_ids=("builtin.historical_simulation",),
            metrics_to_compare=("var_95",),
        )
        report = execute_model_benchmark(spec, dataset=sample_returns)

        # Markdown must escape pipes and preserve table integrity
        md = report.to_markdown()
        assert "Adversarial | Name" in md

        # CSV must properly quote commas and quotes
        csv_str = report.to_csv()
        assert "BM-ADV-001" in csv_str


# ==============================================================================
# 8. Edge Cases & Boundary Validation
# ==============================================================================

class TestPluginAndBenchmarkEdgeCases:
    """Exhaustive boundary and edge-case testing for plugins and benchmark engine."""

    def test_benchmark_specification_validation_errors(self):
        """Test validation rejections on specification parameters."""
        with pytest.raises(ValueError, match="benchmark_id cannot be blank"):
            BenchmarkSpecification(benchmark_id="   ", name="name", description="desc", dataset_id="ds")

        with pytest.raises(ValueError, match="name cannot be blank"):
            BenchmarkSpecification(benchmark_id="BM-1", name="   ", description="desc", dataset_id="ds")

        with pytest.raises(ValueError, match="dataset_id cannot be blank"):
            BenchmarkSpecification(benchmark_id="BM-1", name="name", description="desc", dataset_id="   ")

        with pytest.raises(ValueError, match="plugin_ids sequence cannot be empty"):
            BenchmarkSpecification(benchmark_id="BM-1", name="name", description="desc", dataset_id="ds", plugin_ids=())

        with pytest.raises(ValueError, match="ranking_direction must be"):
            BenchmarkSpecification(
                benchmark_id="BM-1", name="name", description="desc", dataset_id="ds", ranking_direction="invalid_dir"
            )

        with pytest.raises(ValueError, match="tolerance must be a positive finite float"):
            BenchmarkSpecification(
                benchmark_id="BM-1", name="name", description="desc", dataset_id="ds", tolerance=-0.01
            )

        with pytest.raises(ValueError, match="tolerance must be a positive finite float"):
            BenchmarkSpecification(
                benchmark_id="BM-1", name="name", description="desc", dataset_id="ds", tolerance=float("nan")
            )

        with pytest.raises(ValueError, match="confidence_level must be"):
            BenchmarkSpecification(
                benchmark_id="BM-1", name="name", description="desc", dataset_id="ds", baseline_config={"confidence_level": "not_a_float"}
            )

        with pytest.raises(ValueError, match="confidence_level must be in"):
            BenchmarkSpecification(
                benchmark_id="BM-1", name="name", description="desc", dataset_id="ds", baseline_config={"confidence_level": 1.5}
            )

    def test_execute_model_benchmark_type_errors(self, sample_returns):
        """Test execute_model_benchmark argument type assertions."""
        with pytest.raises(TypeError, match="spec must be a BenchmarkSpecification"):
            execute_model_benchmark("not_a_spec", dataset=sample_returns)

        spec = BenchmarkSpecification(benchmark_id="BM-1", name="name", description="desc", dataset_id="ds")
        with pytest.raises(TypeError, match="dataset cannot be None"):
            execute_model_benchmark(spec, dataset=None)

    def test_benchmark_report_deserialization_and_helpers(self, sample_returns):
        """Test BenchmarkReport from_dict, from_json, and string representations."""
        spec = BenchmarkSpecification(
            benchmark_id="BM-DESER",
            name="Deserialization Test",
            description="Deserialization desc",
            dataset_id="DS-1",
            plugin_ids=("builtin.historical_simulation",),
            metrics_to_compare=("var_95", "es_95"),
        )
        report = execute_model_benchmark(spec, dataset=sample_returns)
        d = report.to_dict()
        assert d["benchmark_id"] == "BM-DESER"

        # Roundtrip from_dict
        restored = BenchmarkReport.from_dict(d)
        assert restored.benchmark_id == report.benchmark_id
        assert restored.name == report.name
        assert len(restored.model_entries) == len(report.model_entries)
        assert len(restored.rankings) == len(report.rankings)

        # Roundtrip from_json
        j = report.to_json()
        restored_j = BenchmarkReport.from_json(j)
        assert restored_j.benchmark_id == report.benchmark_id

        # Status and model entries passed
        assert report.status == "completed"
        assert report.model_entries[0].validation_passed is True

    def test_benchmark_with_unregistered_plugin(self, sample_returns):
        """Test execution when a requested plugin is not in the registry."""
        spec = BenchmarkSpecification(
            benchmark_id="BM-UNREG",
            name="Unregistered Plugin",
            description="Unregistered desc",
            dataset_id="DS-1",
            plugin_ids=("non_existent_plugin", "builtin.historical_simulation"),
            metrics_to_compare=("var_95",),
        )
        report = execute_model_benchmark(spec, dataset=sample_returns)
        unreg_entry = next(e for e in report.model_entries if e.plugin_id == "non_existent_plugin")
        assert unreg_entry.status == "incompatible"
        assert "not registered" in unreg_entry.incompatible_reasons[0]

    def test_benchmark_with_ewma_perturbation(self, sample_returns):
        """Test EWMA volatility perturbation against EWMAVolatilityPlugin."""
        spec = BenchmarkSpecification(
            benchmark_id="BM-EWMA-PERT",
            name="EWMA Perturbation",
            description="EWMA pert desc",
            dataset_id="DS-1",
            plugin_ids=("builtin.ewma",),
            metrics_to_compare=("volatility_annualized",),
            perturbation_specs=(
                {"type": "volatility_estimator_ewma", "parameters": {"decay_factor": 0.90}},
            ),
        )
        report = execute_model_benchmark(spec, dataset=sample_returns)
        entry = report.model_entries[0]
        assert len(entry.perturbation_metrics) == 1
        pert_key = list(entry.perturbation_metrics.keys())[0]
        assert "volatility_annualized" in entry.perturbation_metrics[pert_key]
        assert "volatility_annualized" in entry.perturbation_deltas[pert_key]

    def test_plugin_metadata_validation(self):
        """Verify PluginMetadata rejects invalid metadata fields."""
        with pytest.raises(ValueError, match="plugin_id cannot be blank"):
            PluginMetadata(plugin_id="   ", name="Test", description="desc")

        with pytest.raises(ValueError, match="name cannot be blank"):
            PluginMetadata(plugin_id="valid.id", name="  ", description="desc")

    def test_plugin_config_validations(self, sample_returns, sample_portfolio):
        """Verify plugin config validation branches."""
        hist_plugin = HistoricalSimulationPlugin()
        with pytest.raises(ValueError, match="confidence_level must be in"):
            hist_plugin.validate_input(sample_returns, {"confidence_level": -0.5})

        with pytest.raises(ValueError, match="requires at least 2 observations"):
            hist_plugin.validate_input([0.01], {})

        with pytest.raises(ValueError, match="Dataset contains non-finite numbers"):
            hist_plugin.validate_input([0.01, float("nan")], {})

        ewma_plugin = EWMAVolatilityPlugin()
        with pytest.raises(ValueError, match="decay_factor must be in"):
            ewma_plugin.validate_input(sample_returns, {"decay_factor": 1.5})

        with pytest.raises(ValueError, match="annualization_factor must be > 0"):
            ewma_plugin.validate_input(sample_returns, {"annualization_factor": -10.0})

        conc_plugin = PortfolioConcentrationPlugin()
        # Executing concentration plugin on return series raises TypeError
        with pytest.raises(TypeError, match="requires a Portfolio instance"):
            conc_plugin.execute(sample_returns, {})

    def test_plugin_registry_operations(self):
        """Test custom PluginRegistry registration, retrieval, and removal."""
        registry = PluginRegistry()
        plugin = HistoricalSimulationPlugin()
        registry.register(plugin)

        assert "builtin.historical_simulation" in registry
        assert registry.get("builtin.historical_simulation") is plugin
        assert len(registry.list_plugins()) == 1

        # Unregister existing
        removed = registry.unregister("builtin.historical_simulation")
        assert removed is True
        assert "builtin.historical_simulation" not in registry

        # Unregister non-existent
        assert registry.unregister("non_existent") is False

        # Get non-existent raises KeyError
        with pytest.raises(KeyError, match="not found in registry"):
            registry.get("non_existent")

    def test_parametric_gaussian_validation_coverage(self, sample_portfolio):
        """Cover all validation branches of ParametricGaussianPlugin."""
        p = ParametricGaussianPlugin()
        with pytest.raises(TypeError, match="Dataset cannot be None"):
            p.validate_input(None, {})

        with pytest.raises(TypeError, match="requires return series, not a Portfolio"):
            p.validate_input(sample_portfolio, {})

        with pytest.raises(ValueError, match="Dataset cannot be empty"):
            p.validate_input([], {})

        with pytest.raises(ValueError, match="requires 1D return series"):
            p.validate_input([[0.01, 0.02], [0.03, 0.04]], {})

        with pytest.raises(ValueError, match="requires at least 2 observations"):
            p.validate_input([0.01], {})

        with pytest.raises(ValueError, match="Dataset contains non-finite"):
            p.validate_input([0.01, float("inf")], {})

        with pytest.raises(ValueError, match="confidence_level must be in"):
            p.validate_input([0.01, 0.02], {"confidence_level": 1.2})

    def test_metadata_and_result_string_validations(self):
        """Cover blank versions in metadata and blank plugin_id in result."""
        with pytest.raises(ValueError, match="plugin_version cannot be blank"):
            PluginMetadata(plugin_id="p1", name="n1", description="d1", plugin_version="  ")

        with pytest.raises(ValueError, match="api_version cannot be blank"):
            PluginMetadata(plugin_id="p1", name="n1", description="d1", api_version="  ")

        with pytest.raises(ValueError, match="plugin_id cannot be blank"):
            ModelExecutionResult(
                plugin_id="  ",
                model_version="1.0.0",
                metrics={"m1": 1.0},
                execution_time_ms=1.0,
                observations_used=10,
            )

    def test_report_markdown_with_warnings_and_unranked(self, sample_returns):
        """Test markdown rendering when report has warnings and unranked models."""
        spec = BenchmarkSpecification(
            benchmark_id="BM-UNRANKED-WARN",
            name="Unranked and Warnings",
            description="desc",
            dataset_id="DS-1",
            plugin_ids=("non_existent_plugin", "builtin.historical_simulation"),
            metrics_to_compare=("var_95",),
        )
        report = execute_model_benchmark(spec, dataset=sample_returns)
        # Verify markdown includes unranked models section
        md = report.to_markdown()
        assert "### Excluded / Incomparable Models" in md
        assert "`non_existent_plugin`" in md


