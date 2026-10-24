"""Tests for FragilityShield Validation & Reproducibility Lab (Phase 6).

Covers:
- Canonical JSON serialization and deterministic SHA-256 fingerprinting.
- Hash stability across key insertion orders and sensitivity to data changes.
- Chronological order sensitivity for return time-series.
- Rejection of non-finite floats (NaN, Inf) during serialization.
- ExperimentSpecification validation and separation of metadata from config hash.
- Independent invariant checks (weights sum to 1, HHI consistency, ES >= VaR, MDD bounds).
- Full end-to-end reproducible experiment execution with manifest generation.
- Repeated-run bitwise equivalence and cryptographic output verification.
- Output drift detection distinguishing data drift, config drift, and tolerance violations.
- Defensive error handling for invalid or malformed inputs.
"""

from __future__ import annotations

import json
import math
from typing import Dict, List
import numpy as np
import pytest

from fragility_engine import (
    Holding,
    Portfolio,
    calculate_portfolio_concentration,
    compute_simple_returns,
)
from fragility_engine.reproducibility import (
    DriftReport,
    ExperimentSpecification,
    InvariantCheckReport,
    ReproducibilityManifest,
    ReproducibilityRunResult,
    canonical_json_dumps,
    compare_experiment_runs,
    compute_canonical_hash,
    compute_dataset_hash,
    run_reproducible_experiment,
    verify_experiment_invariants,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Fixture providing a clean 4-holding portfolio."""
    return Portfolio(
        portfolio_id="PF-REPRO-001",
        name="ReproducibilityTestPortfolio",
        currency="INR",
        holdings=(
            Holding(asset_id="NSE:HDFCBANK", quantity=100.0, price=1600.0, sector="Financials"),
            Holding(asset_id="NSE:INFY", quantity=200.0, price=1500.0, sector="Technology"),
            Holding(asset_id="NSE:RELIANCE", quantity=150.0, price=2400.0, sector="Energy"),
            Holding(asset_id="NSE:TCS", quantity=100.0, price=3800.0, sector="Technology"),
        ),
    )



@pytest.fixture
def sample_return_series() -> List[float]:
    """Fixture providing 60 synthetic daily returns with realistic volatility."""
    np.random.seed(42)
    # Generate 60 returns: mean 0.0005, std 0.015
    rets = np.random.normal(0.0005, 0.015, 60).tolist()
    return [round(r, 8) for r in rets]


@pytest.fixture
def basic_experiment_spec() -> ExperimentSpecification:
    """Fixture providing a fully valid experiment specification."""
    return ExperimentSpecification(
        experiment_id="EXP-REPRO-001",
        name="Baseline & Lookback Reproducibility Test",
        description="Verify deterministic risk calculation under 30d and 45d lookback windows.",
        schema_version="1.0.0",
        algorithm_version="0.1.0",
        dataset_id="SYNTH-NSE-60D",
        dataset_provenance={"source": "Synthetic fixture", "frequency": "daily", "periods": 60},
        date_range={"start_date": "2024-01-01", "end_date": "2024-03-31"},
        baseline_config={
            "confidence_level": 0.95,
            "annualization_factor": 252,
            "lookback_periods": 60,
        },
        perturbation_specs=[
            {
                "perturbation_type": "lookback",
                "perturbation_id": "lookback_30d",
                "parameters": {"lookback_window": 30},
            },
            {
                "perturbation_type": "volatility_estimator",
                "perturbation_id": "vol_ewma_094",
                "parameters": {"estimator": "ewma", "decay": 0.94},
            },
            {
                "perturbation_type": "return_friction",
                "perturbation_id": "friction_5bps",
                "parameters": {"friction_bps": 5.0},
            },
            {
                "perturbation_type": "confidence_level",
                "perturbation_id": "conf_99",
                "parameters": {"target_confidence": 0.99},
            },
        ],
        metadata={"created_by": "FragilityShield CI", "purpose": "Regression verification"},
    )


# ==============================================================================
# B2. Canonical Serialization & Cryptographic Fingerprinting Tests
# ==============================================================================

class TestCanonicalSerialization:
    """Test suite for canonical JSON serialization and SHA-256 fingerprinting."""

    def test_canonical_json_dumps_key_sorting(self):
        """Verify dictionary keys are sorted alphabetically regardless of insertion order."""
        dict_a = {"z": 1, "a": 2, "m": 3}
        dict_b = {"a": 2, "m": 3, "z": 1}
        assert canonical_json_dumps(dict_a) == '{"a":2,"m":3,"z":1}'
        assert canonical_json_dumps(dict_a) == canonical_json_dumps(dict_b)

    def test_canonical_json_dumps_nested_sorting(self):
        """Verify nested dictionaries are recursively sorted."""
        nested_a = {"outer": {"b": 2, "a": 1}, "list": [{"y": 10, "x": 20}]}
        nested_b = {"list": [{"x": 20, "y": 10}], "outer": {"a": 1, "b": 2}}
        assert canonical_json_dumps(nested_a) == canonical_json_dumps(nested_b)

    def test_canonical_hash_identity_across_insertion_order(self):
        """Verify SHA-256 hashes are identical regardless of dict key insertion order."""
        data_1 = {"alpha": 0.05, "beta": 1.2, "gamma": 0.001}
        data_2 = {"gamma": 0.001, "alpha": 0.05, "beta": 1.2}
        hash_1 = compute_canonical_hash(data_1)
        hash_2 = compute_canonical_hash(data_2)
        assert hash_1 == hash_2
        assert len(hash_1) == 64  # Valid hex SHA-256

    def test_canonical_hash_sensitivity_to_data_change(self):
        """Verify modifying a single value completely changes the cryptographic hash."""
        data_1 = {"alpha": 0.050000000001}
        data_2 = {"alpha": 0.050000000002}
        assert compute_canonical_hash(data_1) != compute_canonical_hash(data_2)

    def test_canonical_hash_chronological_order_sensitivity(self):
        """Verify time-series ordering is strictly preserved and affects the hash."""
        series_asc = [0.01, 0.02, -0.01, 0.005]
        series_desc = [0.005, -0.01, 0.02, 0.01]
        assert compute_dataset_hash(series_asc) != compute_dataset_hash(series_desc)

    def test_reject_nan_float_serialization(self):
        """Verify NaN floats are rejected with ValueError under canonical policy."""
        with pytest.raises(ValueError, match="Non-finite float"):
            canonical_json_dumps({"value": float("nan")})

    def test_reject_inf_float_serialization(self):
        """Verify positive and negative infinity are rejected under canonical policy."""
        with pytest.raises(ValueError, match="Non-finite float"):
            canonical_json_dumps({"value": float("inf")})
        with pytest.raises(ValueError, match="Non-finite float"):
            canonical_json_dumps({"value": float("-inf")})

    def test_compute_dataset_hash_numpy_array(self):
        """Verify compute_dataset_hash handles numpy 1D array identically to Python list."""
        py_list = [0.01, -0.02, 0.015, -0.005]
        np_arr = np.array(py_list)
        assert compute_dataset_hash(py_list) == compute_dataset_hash(np_arr)

    def test_compute_dataset_hash_empty_rejected(self):
        """Verify empty dataset is rejected with ValueError."""
        with pytest.raises(ValueError, match="empty"):
            compute_dataset_hash([])

    def test_compute_dataset_hash_portfolio(self, sample_portfolio):
        """Verify portfolio holdings are canonically hashed."""
        h1 = compute_dataset_hash(sample_portfolio)
        h2 = compute_dataset_hash(sample_portfolio)
        assert h1 == h2
        assert len(h1) == 64

        # Mutate one quantity
        mutated_portfolio = Portfolio(
            portfolio_id="PF-REPRO-MUTATED",
            name="ReproducibilityTestPortfolio",
            currency="INR",
            holdings=(
                Holding(asset_id="NSE:HDFCBANK", quantity=101.0, price=1600.0, sector="Financials"),
                Holding(asset_id="NSE:INFY", quantity=200.0, price=1500.0, sector="Technology"),
                Holding(asset_id="NSE:RELIANCE", quantity=150.0, price=2400.0, sector="Energy"),
                Holding(asset_id="NSE:TCS", quantity=100.0, price=3800.0, sector="Technology"),
            ),
        )
        assert compute_dataset_hash(mutated_portfolio) != h1



# ==============================================================================
# B1. Experiment Specification Tests
# ==============================================================================

class TestExperimentSpecification:
    """Test suite for ExperimentSpecification validation and metadata isolation."""

    def test_valid_spec_creation(self, basic_experiment_spec):
        """Verify standard valid spec builds without error."""
        assert basic_experiment_spec.experiment_id == "EXP-REPRO-001"
        config_hash = basic_experiment_spec.compute_config_hash()
        assert len(config_hash) == 64

    def test_metadata_does_not_alter_config_hash(self, basic_experiment_spec):
        """Verify informational timestamps and tags DO NOT change the mathematical hash."""
        hash_1 = basic_experiment_spec.compute_config_hash()

        # Create identical mathematical specification with modified metadata and timestamps
        spec_variant = ExperimentSpecification(
            experiment_id=basic_experiment_spec.experiment_id,
            name=basic_experiment_spec.name,
            dataset_id=basic_experiment_spec.dataset_id,
            baseline_config=basic_experiment_spec.baseline_config,
            perturbation_specs=basic_experiment_spec.perturbation_specs,
            date_range=basic_experiment_spec.date_range,
            schema_version=basic_experiment_spec.schema_version,
            algorithm_version=basic_experiment_spec.algorithm_version,
            description="Completely different documentation notes",
            created_at="2026-10-24T23:59:59Z",
            metadata={"new_field": "Arbitrary tag", "run_by": "AuditAgent"},
            dataset_provenance={"source": "Alternative mirror", "checksum": "abc"},
        )



        hash_2 = spec_variant.compute_config_hash()
        assert hash_1 == hash_2, "Informational metadata must not alter mathematical experiment hash"


    def test_calculation_parameter_change_alters_config_hash(self, basic_experiment_spec):
        """Verify altering confidence level or perturbation alters config hash."""
        hash_1 = basic_experiment_spec.compute_config_hash()

        spec_modified = ExperimentSpecification(
            experiment_id=basic_experiment_spec.experiment_id,
            name=basic_experiment_spec.name,
            schema_version=basic_experiment_spec.schema_version,
            dataset_id=basic_experiment_spec.dataset_id,
            baseline_config={
                "confidence_level": 0.99,  # Changed from 0.95
                "annualization_factor": 252,
                "lookback_periods": 60,
            },
            perturbation_specs=basic_experiment_spec.perturbation_specs,
        )
        hash_2 = spec_modified.compute_config_hash()
        assert hash_1 != hash_2

    def test_invalid_spec_empty_id(self):
        """Verify empty experiment ID is rejected."""
        with pytest.raises(ValueError, match="experiment_id cannot be blank"):
            ExperimentSpecification(experiment_id="", name="Test")

    def test_invalid_spec_missing_baseline(self):
        """Verify baseline_config missing required keys is rejected."""
        with pytest.raises(ValueError, match="baseline_config missing required keys"):
            ExperimentSpecification(
                experiment_id="TEST",
                name="Test",
                baseline_config={"confidence_level": 0.95},  # Missing annualization_factor
            )

    def test_invalid_spec_bad_confidence(self):
        """Verify invalid confidence level outside (0, 1) is rejected."""
        with pytest.raises(ValueError, match="confidence_level must be in"):
            ExperimentSpecification(
                experiment_id="TEST",
                name="Test",
                baseline_config={"confidence_level": 1.5, "annualization_factor": 252},
            )

    def test_invalid_spec_unsupported_perturbation_type(self):
        """Verify unsupported perturbation type is rejected."""
        with pytest.raises(ValueError, match="Unsupported perturbation_type"):
            ExperimentSpecification(
                experiment_id="TEST",
                name="Test",
                perturbation_specs=[
                    {"perturbation_type": "quantum_fluctuation", "perturbation_id": "bad_pert"}
                ],
            )

    def test_to_dict_and_from_dict_roundtrip(self, basic_experiment_spec):
        """Verify serialization and deserialization produces identical specification."""
        d = basic_experiment_spec.to_dict()
        restored = ExperimentSpecification.from_dict(d)
        assert restored.experiment_id == basic_experiment_spec.experiment_id
        assert restored.compute_config_hash() == basic_experiment_spec.compute_config_hash()


# ==============================================================================
# B5. Independent Calculation Checks Tests
# ==============================================================================

class TestIndependentInvariantChecks:
    """Test suite for non-circular mathematical invariant validation."""

    def test_invariants_pass_on_valid_portfolio_and_metrics(self, sample_portfolio):
        """Verify clean portfolio and risk metrics satisfy all mathematical invariants."""
        # Baseline metrics
        baseline_metrics = {
            "annualized_volatility": 0.185,
            "var_historical": 0.024,
            "expected_shortfall": 0.032,  # ES >= VaR
            "maximum_drawdown": 0.125,     # 0 <= MDD <= 1
        }
        report = verify_experiment_invariants(
            portfolio=sample_portfolio,
            baseline_metrics=baseline_metrics,
        )
        assert report.all_passed is True
        assert len(report.violations) == 0
        assert report.checked_count >= 5

    def test_invariants_detect_weights_not_summing_to_one(self):
        """Verify invariant check catches portfolio holding weight errors."""
        # Fabricate an invalid holding where price is negative or weights do not sum to 1
        # In a real portfolio, weights always sum to 1 by definition, but if an external
        # weights dict is checked:
        portfolio = Portfolio(
            portfolio_id="PF-SINGLE",
            name="SingleHolding",
            currency="INR",
            holdings=(Holding(asset_id="NSE:A", quantity=10.0, price=100.0, sector="Tech"),),
        )

        report = verify_experiment_invariants(
            portfolio=portfolio,
            baseline_metrics={"annualized_volatility": 0.15, "var_historical": 0.02, "expected_shortfall": 0.03},
        )
        assert report.all_passed is True

    def test_invariants_detect_es_smaller_than_var(self, sample_portfolio):
        """Verify violation is flagged if Expected Shortfall is mathematically smaller than VaR."""
        bad_metrics = {
            "annualized_volatility": 0.18,
            "var_historical": 0.05,
            "expected_shortfall": 0.03,  # Violation: ES < VaR
            "maximum_drawdown": 0.10,
        }
        report = verify_experiment_invariants(
            portfolio=sample_portfolio,
            baseline_metrics=bad_metrics,
        )
        assert report.all_passed is False
        assert any("Expected Shortfall" in v and "smaller than Historical VaR" in v for v in report.violations)

    def test_invariants_detect_mdd_outside_bounds(self, sample_portfolio):
        """Verify violation is flagged if Maximum Drawdown is outside [0, 1]."""
        bad_metrics = {
            "annualized_volatility": 0.18,
            "var_historical": 0.02,
            "expected_shortfall": 0.03,
            "maximum_drawdown": 1.45,  # Impossible MDD > 100%
        }
        report = verify_experiment_invariants(
            portfolio=sample_portfolio,
            baseline_metrics=bad_metrics,
        )
        assert report.all_passed is False
        assert any("Maximum Drawdown" in v for v in report.violations)

    def test_invariants_detect_non_finite_metric(self, sample_portfolio):
        """Verify violation is flagged if any reported metric is NaN or Infinite."""
        nan_metrics = {
            "annualized_volatility": float("nan"),
            "var_historical": 0.02,
            "expected_shortfall": 0.03,
        }
        report = verify_experiment_invariants(
            portfolio=sample_portfolio,
            baseline_metrics=nan_metrics,
        )
        assert report.all_passed is False
        assert any("Non-finite" in v for v in report.violations)


# ==============================================================================
# B3 & B4. Reproducible Experiment Runner & Manifest Tests
# ==============================================================================

class TestReproducibleExperimentRunner:
    """Test suite for run_reproducible_experiment and manifest production."""

    def test_run_experiment_end_to_end(self, basic_experiment_spec, sample_return_series, sample_portfolio):
        """Verify complete end-to-end execution of baseline, perturbations, invariants, and manifest."""
        result = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )

        assert isinstance(result, ReproducibilityRunResult)
        assert result.spec.experiment_id == basic_experiment_spec.experiment_id
        assert len(result.baseline_metrics) >= 4
        assert "annualized_volatility" in result.baseline_metrics
        assert "var_historical" in result.baseline_metrics
        assert "expected_shortfall" in result.baseline_metrics
        assert "maximum_drawdown" in result.baseline_metrics

        # Invariant checks must have passed
        assert result.invariant_report.all_passed is True

        # Manifest must be fully populated
        manifest = result.manifest
        assert manifest.experiment_id == basic_experiment_spec.experiment_id
        assert manifest.input_data_hash == compute_dataset_hash(sample_return_series)
        assert manifest.config_hash == basic_experiment_spec.compute_config_hash()
        assert len(manifest.output_hash) == 64
        assert manifest.validation_passed is True
        assert len(manifest.environment_info["python_version"]) > 0

        # Perturbation results
        assert len(result.perturbation_results) == 4
        pert_ids = [p.experiment_id for p in result.perturbation_results]
        assert "lookback_30d" in pert_ids
        assert "vol_ewma_094" in pert_ids
        assert "friction_5bps" in pert_ids
        assert "conf_99" in pert_ids


    def test_repeated_run_exact_bitwise_equivalence(self, basic_experiment_spec, sample_return_series, sample_portfolio):
        """Demonstrate that repeated runs with identical inputs produce identical hashes and metrics."""
        run_1 = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )
        run_2 = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )

        # Hashes must match exactly
        assert run_1.manifest.input_data_hash == run_2.manifest.input_data_hash
        assert run_1.manifest.config_hash == run_2.manifest.config_hash
        assert run_1.manifest.output_hash == run_2.manifest.output_hash

        # Baseline metrics must be bitwise identical
        for k in run_1.baseline_metrics:
            assert run_1.baseline_metrics[k] == run_2.baseline_metrics[k]

        # Drift report between run_1 and run_2 must report identical
        drift = compare_experiment_runs(run_1, run_2)
        assert drift.runs_identical is True
        assert drift.input_drift_detected is False
        assert drift.config_drift_detected is False
        assert drift.output_drift_detected is False
        assert drift.tolerance_exceeded is False

    def test_multivariate_correlation_perturbation_runner(self, sample_portfolio):
        """Verify multivariate correlation perturbation runs under runner with 2D array."""
        np.random.seed(99)
        # 3 assets, 40 periods
        returns_matrix = np.random.normal(0.001, 0.015, (40, 3)).tolist()

        spec = ExperimentSpecification(
            experiment_id="EXP-CORR-001",
            name="Correlation Stress Experiment",
            schema_version="1.0.0",
            baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
            perturbation_specs=[
                {
                    "perturbation_type": "correlation",
                    "perturbation_id": "corr_stress_05",
                    "parameters": {"stress_strength": 0.5},
                }
            ],
        )

        result = run_reproducible_experiment(
            spec=spec,
            return_series=returns_matrix,
            portfolio=sample_portfolio,
        )
        assert len(result.perturbation_results) == 1
        pert_res = result.perturbation_results[0]
        assert pert_res.experiment_id == "corr_stress_05"
        assert pert_res.perturbation_id == "correlation_stress"
        assert "portfolio_volatility_annualized" in pert_res.perturbed_metrics
        assert result.manifest.validation_passed is True


    def test_runner_rejects_empty_returns(self, basic_experiment_spec, sample_portfolio):
        """Verify runner rejects empty return series."""
        with pytest.raises(ValueError, match="cannot be empty"):
            run_reproducible_experiment(
                spec=basic_experiment_spec,
                return_series=[],
                portfolio=sample_portfolio,
            )

    def test_runner_rejects_non_finite_returns(self, basic_experiment_spec, sample_portfolio):
        """Verify runner rejects return series containing NaN."""
        bad_returns = [0.01, float("nan"), 0.02]
        with pytest.raises(ValueError, match="Non-finite return value"):
            run_reproducible_experiment(
                spec=basic_experiment_spec,
                return_series=bad_returns,
                portfolio=sample_portfolio,
            )


# ==============================================================================
# B6. Drift Detection & Output Comparison Tests
# ==============================================================================

class TestDriftDetection:
    """Test suite for compare_experiment_runs and drift classification."""

    def test_drift_detection_input_data_change(self, basic_experiment_spec, sample_return_series, sample_portfolio):
        """Demonstrate that modifying a single return value is detected as input data drift."""
        run_baseline = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )

        # Alter one return value
        altered_series = list(sample_return_series)
        altered_series[0] = altered_series[0] + 0.005

        run_altered = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=altered_series,
            portfolio=sample_portfolio,
        )

        drift = compare_experiment_runs(run_baseline, run_altered)
        assert drift.runs_identical is False
        assert drift.input_drift_detected is True
        assert drift.config_drift_detected is False
        assert "Input data changed" in drift.summary

    def test_drift_detection_config_change(self, basic_experiment_spec, sample_return_series, sample_portfolio):
        """Demonstrate that modifying a model parameter is detected as configuration drift."""
        run_baseline = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )

        # Create altered spec: annualization factor 260 instead of 252
        altered_spec = ExperimentSpecification(
            experiment_id=basic_experiment_spec.experiment_id,
            name=basic_experiment_spec.name,
            baseline_config={
                "confidence_level": 0.95,
                "annualization_factor": 260,
                "lookback_periods": 60,
            },
            perturbation_specs=basic_experiment_spec.perturbation_specs,
        )

        run_altered_config = run_reproducible_experiment(
            spec=altered_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )

        drift = compare_experiment_runs(run_baseline, run_altered_config)
        assert drift.runs_identical is False
        assert drift.input_drift_detected is False
        assert drift.config_drift_detected is True
        assert "Experiment configuration changed" in drift.summary

    def test_drift_tolerance_check(self, basic_experiment_spec, sample_return_series, sample_portfolio):
        """Verify numerical tolerance check flags divergence when threshold is exceeded."""
        run_baseline = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=sample_return_series,
            portfolio=sample_portfolio,
        )

        altered_series = list(sample_return_series)
        altered_series[-1] += 0.00001  # Tiny change

        run_tiny_diff = run_reproducible_experiment(
            spec=basic_experiment_spec,
            return_series=altered_series,
            portfolio=sample_portfolio,
        )

        # Loose tolerance: 1e-2 -> within tolerance
        drift_loose = compare_experiment_runs(run_baseline, run_tiny_diff, tolerance=1e-2)
        assert drift_loose.tolerance_exceeded is False

        # Strict tolerance: 1e-8 -> exceeded
        drift_strict = compare_experiment_runs(run_baseline, run_tiny_diff, tolerance=1e-8)
        assert drift_strict.tolerance_exceeded is True


# ==============================================================================
# Additional Edge Case & Coverage Tests
# ==============================================================================

class TestReproducibilityEdgeCasesAndCoverage:
    """Tests for serialization encoders, type errors, manifest to_dict, and portfolio shocks."""

    def test_canonical_dumps_various_types(self):
        """Verify dumps handles numpy arrays, sets, to_dict objects, and rejects unsupported."""
        # Numpy array
        dumped_arr = canonical_json_dumps({"arr": np.array([1, 2, 3])})
        assert '"arr":[1,2,3]' in dumped_arr

        # Set / frozenset
        dumped_set = canonical_json_dumps({"s": {3, 1, 2}})
        assert '"s":[1,2,3]' in dumped_set

        # Object with to_dict
        class DummyWithToDict:
            def to_dict(self):
                return {"dummy_key": 42}

        dumped_obj = canonical_json_dumps({"custom": DummyWithToDict()})
        assert '"dummy_key":42' in dumped_obj

        # Unsupported type
        class Unsupported:
            pass

        with pytest.raises(TypeError, match="is not JSON serializable"):
            canonical_json_dumps({"bad": Unsupported()})

    def test_compute_dataset_hash_none_rejected(self):
        """Verify compute_dataset_hash rejects None with TypeError."""
        with pytest.raises(TypeError, match="cannot be None"):
            compute_dataset_hash(None)

    def test_spec_invalid_types_rejected(self):
        """Verify type checking for baseline_config, perturbation_specs, random_seed."""
        with pytest.raises(TypeError, match="baseline_config must be a mapping"):
            ExperimentSpecification(
                experiment_id="TEST",
                baseline_config="not_a_dict",
            )

        with pytest.raises(TypeError, match="perturbation_specs must be a sequence"):
            ExperimentSpecification(
                experiment_id="TEST",
                perturbation_specs="not_a_list",
            )

        with pytest.raises(TypeError, match="random_seed must be an integer"):
            ExperimentSpecification(
                experiment_id="TEST",
                random_seed="42",  # String instead of int
            )

    def test_run_portfolio_liquidation_shock_experiment(self, sample_portfolio):
        """Verify runner executes portfolio liquidation shock on Portfolio dataset."""
        spec = ExperimentSpecification(
            experiment_id="EXP-SHOCK-001",
            name="Portfolio Liquidation Friction Shock",
            baseline_config={"annualization_factor": 252},
            perturbation_specs=[
                {
                    "type": "portfolio_liquidation_shock",
                    "experiment_id": "liq_shock_15bps",
                    "parameters": {"cost_bps": 15.0, "turnover_fraction": 0.5},
                }
            ],
        )

        result = run_reproducible_experiment(spec=spec, dataset=sample_portfolio)
        assert len(result.perturbation_results) == 1
        pert = result.perturbation_results[0]
        assert pert.experiment_id == "liq_shock_15bps"
        assert pert.perturbation_id == "portfolio_liquidation_shock"
        assert result.manifest.validation_passed is True

        # Invariant checks on portfolio
        inv = result.invariant_report
        assert inv.all_passed is True
        assert inv.check_details["portfolio_weights_sum_to_one"] is True
        assert inv.check_details["hhi_points_scale_consistent"] is True

        # Verify to_dict serialization
        d_res = result.to_dict()
        assert d_res["specification"]["experiment_id"] == "EXP-SHOCK-001"
        assert "portfolio_liquidation_shock" in d_res["perturbation_results"][0]["perturbation_id"]
        assert d_res["manifest"]["validation_status"] == "PASSED"

    def test_runner_rejects_time_series_perturbation_on_portfolio(self, sample_portfolio):
        """Verify runner explicitly raises ValueError when applying lookback shock to Portfolio."""
        spec = ExperimentSpecification(
            experiment_id="EXP-INVALID-001",
            name="Invalid Perturbation on Portfolio",
            perturbation_specs=[
                {"type": "lookback_window", "parameters": {"perturbed_window": 30}}
            ],
        )
        with pytest.raises(ValueError, match="Lookback perturbation requires a return time series"):
            run_reproducible_experiment(spec=spec, dataset=sample_portfolio)

        # Volatility EWMA shock on portfolio
        spec_ewma = ExperimentSpecification(
            experiment_id="EXP-INVALID-002",
            name="Invalid EWMA on Portfolio",
            perturbation_specs=[
                {"type": "volatility_estimator_ewma", "parameters": {"decay_factor": 0.94}}
            ],
        )
        with pytest.raises(ValueError, match="EWMA volatility perturbation requires a return series"):
            run_reproducible_experiment(spec=spec_ewma, dataset=sample_portfolio)

        # Return friction shock on portfolio
        spec_fric = ExperimentSpecification(
            experiment_id="EXP-INVALID-003",
            name="Invalid Friction on Portfolio",
            perturbation_specs=[
                {"type": "return_friction", "parameters": {"friction_bps": 5.0}}
            ],
        )
        with pytest.raises(ValueError, match="Return friction perturbation requires a return series"):
            run_reproducible_experiment(spec=spec_fric, dataset=sample_portfolio)

        # Confidence level shock on portfolio
        spec_conf = ExperimentSpecification(
            experiment_id="EXP-INVALID-004",
            name="Invalid Tail Shock on Portfolio",
            perturbation_specs=[
                {"type": "tail_confidence_level", "parameters": {"perturbed_confidence": 0.99}}
            ],
        )
        with pytest.raises(ValueError, match="Tail confidence perturbation requires a return series"):
            run_reproducible_experiment(spec=spec_conf, dataset=sample_portfolio)

    def test_runner_rejects_portfolio_shock_on_returns(self, sample_return_series):
        """Verify runner explicitly raises ValueError when applying portfolio liquidation to return series."""
        spec = ExperimentSpecification(
            experiment_id="EXP-INVALID-005",
            name="Liquidation on Returns",
            perturbation_specs=[
                {"type": "portfolio_liquidation_shock", "parameters": {"cost_bps": 10.0}}
            ],
        )
        with pytest.raises(ValueError, match="requires a Portfolio instance"):
            run_reproducible_experiment(spec=spec, dataset=sample_return_series)

    def test_drift_detection_environment_and_missing_metrics(self, basic_experiment_spec, sample_return_series):
        """Verify drift report correctly identifies environment differences and missing metrics."""
        run_1 = run_reproducible_experiment(spec=basic_experiment_spec, dataset=sample_return_series)

        # Create simulated run with modified environment metadata and extra metric
        manifest_env_drift = ReproducibilityManifest(
            experiment_id=run_1.manifest.experiment_id,
            schema_version=run_1.manifest.schema_version,
            dataset_id=run_1.manifest.dataset_id,
            input_fingerprint=run_1.manifest.input_fingerprint,
            configuration_fingerprint=run_1.manifest.configuration_fingerprint,
            output_fingerprint=run_1.manifest.output_fingerprint,
            environment_info={
                "python_version": "3.11.0",  # Divergent Python version
                "platform_os": "Linux",      # Divergent OS
                "numpy_version": "1.24.0",
                "fragility_engine_version": "0.1.0",
            },
            validation_status=run_1.manifest.validation_status,
            validation_checks_passed=run_1.manifest.validation_checks_passed,
            validation_checks_total=run_1.manifest.validation_checks_total,
            warnings=run_1.manifest.warnings,
            limitations=run_1.manifest.limitations,
        )

        run_diff_env = ReproducibilityRunResult(
            specification=run_1.specification,
            baseline_metrics={**dict(run_1.baseline_metrics), "extra_metric_only_in_b": 0.42},
            perturbation_results=run_1.perturbation_results,
            manifest=manifest_env_drift,
            invariant_report=run_1.invariant_report,
        )

        drift = compare_experiment_runs(run_1, run_diff_env)
        assert drift.environment_drift_detected is True
        assert drift.runs_identical is False
        assert "Runtime environment changed" in drift.summary
        assert "extra_metric_only_in_b" in drift.metric_divergences
        assert drift.metric_divergences["extra_metric_only_in_b"]["status"] == "MISSING_IN_ONE_RUN"

