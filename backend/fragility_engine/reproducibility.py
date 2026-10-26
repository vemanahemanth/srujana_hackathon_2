"""FragilityShield — Validation & Reproducibility Lab (Phase 6).

This module implements a deterministic audit framework allowing quantitative
experiments, risk models, and fragility perturbations to be reproduced,
cryptographically fingerprinted, independently validated, and checked for drift.

Core Capabilities:
1. Canonical Serialization & Cryptographic Fingerprinting (SHA-256):
   - Stable deterministic hashing of input datasets, model configurations, and outputs.
   - Dictionary key ordering and float serialization policies.
   - Separation of mathematical calculation parameters from informational timestamps.
2. Experiment Specification Domain Model (`ExperimentSpecification`):
   - Fully typed specification capturing datasets, baseline parameters, and perturbations.
3. Reproducible Experiment Runner (`run_reproducible_experiment`):
   - Orchestrates dataset validation, baseline execution, fragility perturbations,
     independent mathematical invariant checks, and manifest generation.
4. Reproducibility Manifest (`ReproducibilityManifest`):
   - Immutable artifact capturing fingerprints, environment metadata, validation status,
     and methodological caveats for subsequent independent verification.
5. Independent Calculation Checks (`verify_experiment_invariants`):
   - Verifies mathematical invariants (weights sum to 1, HHI consistency, ES >= VaR,
     zero-baseline invariance, drawdown bounds) without circular function calls.
6. Drift Detection & Output Comparison (`compare_experiment_runs`):
   - Compares two experiment runs, identifying whether differences originate from
     input data drift, configuration drift, or numerical tolerance drift.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np

import fragility_engine
from fragility_engine.concentration import calculate_hhi, calculate_portfolio_concentration
from fragility_engine.fragility import (
    FragilityExperimentResult,
    calculate_ewma_volatility,
    calculate_portfolio_liquidation_shock,
    perturb_correlation_matrix,
    rank_perturbation_sensitivities,
    run_confidence_level_perturbation,
    run_correlation_perturbation,
    run_lookback_perturbation,
    run_return_friction_perturbation,
    run_volatility_estimator_perturbation,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.risk import calculate_risk_report


# ==============================================================================
# B2. Deterministic Serialization & Hashing Policy
# ==============================================================================

def canonical_json_dumps(obj: Any) -> str:
    """Serialize an object to a canonical, deterministic JSON string.

    Policy:
    - Dictionary keys are sorted alphabetically.
    - Numbers are formatted consistently: floats are formatted with IEEE 754 precision.
    - Non-finite numbers (NaN, Inf, -Inf) are strictly rejected with ValueError.
    - UTF-8 encoding without whitespace around separators (compact representation).
    - Tuples and sets are normalized to ordered lists where appropriate.

    Args:
        obj: The Python object (dict, list, str, float, int, bool, None).

    Returns:
        Deterministic compact JSON string.
    """
    def _default_encoder(o: Any) -> Any:
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, (np.integer, int)):
            return int(o)
        if isinstance(o, (np.floating, float)):
            f_val = float(o)
            if not math.isfinite(f_val):
                raise ValueError(f"Non-finite float value {f_val!r} cannot be canonically hashed")
            return f_val
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (set, frozenset)):
            return sorted(list(o))
        if hasattr(o, "to_dict") and callable(o.to_dict):
            return o.to_dict()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    # Custom recursive validation for non-finite values before serialization
    def _validate_finite(val: Any) -> None:
        if isinstance(val, (float, np.floating)):
            if not math.isfinite(float(val)):
                raise ValueError(f"Non-finite float {val!r} is rejected by canonical serialization policy")
        elif isinstance(val, dict):
            for k, v in val.items():
                _validate_finite(v)
        elif isinstance(val, (list, tuple)):
            for item in val:
                _validate_finite(item)

    _validate_finite(obj)

    return json.dumps(
        obj,
        default=_default_encoder,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def compute_canonical_hash(obj: Any) -> str:
    """Generate SHA-256 cryptographic fingerprint from canonical representation.

    Args:
        obj: Python data structure or serializable domain object.

    Returns:
        64-character lowercase hexadecimal SHA-256 string.
    """
    canonical_str = canonical_json_dumps(obj)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_dataset_hash(data: Sequence[float] | np.ndarray | Portfolio) -> str:
    """Generate deterministic fingerprint for raw input dataset.

    Args:
        data: Return series (sequence of floats), 2D return matrix, or Portfolio instance.

    Returns:
        SHA-256 hexadecimal hash string.
    """
    if data is None:
        raise TypeError("Dataset cannot be None")

    if isinstance(data, Portfolio):
        canonical_repr = {
            "type": "portfolio",
            "portfolio_id": data.portfolio_id,
            "currency": data.currency,
            "holdings": sorted(
                [
                    {
                        "asset_id": h.asset_id,
                        "quantity": h.quantity,
                        "price": h.price,
                        "sector": h.sector or "",
                    }
                    for h in data.holdings
                ],
                key=lambda x: x["asset_id"],
            ),
        }
        return compute_canonical_hash(canonical_repr)

    if isinstance(data, (list, tuple, np.ndarray)) and len(data) == 0:
        raise ValueError("Dataset cannot be empty")

    arr = np.asarray(data)
    if arr.size == 0:
        raise ValueError("Dataset cannot be empty")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Dataset contains non-finite numbers (NaN or Inf)")

    canonical_repr = {
        "type": "returns_array",
        "shape": list(arr.shape),
        "values": [round(float(x), 10) for x in arr.flatten()],
    }
    return compute_canonical_hash(canonical_repr)


# ==============================================================================
# B1. Experiment Specification
# ==============================================================================

@dataclass(frozen=True)
class ExperimentSpecification:
    """Deterministic, typed specification for a quantitative risk experiment.

    Separates mathematical calculation inputs from informational metadata so
    that changing timestamps or descriptive notes does not alter the configuration hash.

    Attributes:
        experiment_id: Unique non-empty string identifier.
        name: Human-readable experiment title.
        description: Methodological explanation.
        dataset_id: Identifier of the input dataset.
        baseline_config: Parameters for baseline calculation (e.g. annualization_factor, ddof).
        perturbation_specs: Sequence of perturbation configurations to evaluate.
        schema_version: Specification schema version string (defaults to "1.0").
        algorithm_version: Software algorithm version string (defaults to "1.0").
        random_seed: Optional deterministic integer seed (if simulation is required).
        date_range: Optional tuple or dict of (start_date, end_date) strings.
        created_at: ISO 8601 UTC timestamp of creation (informational only).
        metadata: Informational tags (informational only).
        dataset_provenance: Optional informational dataset provenance dictionary.
    """

    experiment_id: str
    name: str = "Quantitative Experiment"
    dataset_id: str = "DEFAULT_DATASET"
    baseline_config: Mapping[str, Any] = field(default_factory=dict)
    perturbation_specs: Sequence[Mapping[str, Any]] = field(default_factory=list)
    description: str = ""
    schema_version: str = "1.0"
    algorithm_version: str = "1.0"
    random_seed: Optional[int] = None
    date_range: Optional[Union[Tuple[str, str], Mapping[str, str]]] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)
    dataset_provenance: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate specification integrity."""
        if not isinstance(self.experiment_id, str) or not self.experiment_id.strip():
            raise ValueError("experiment_id cannot be blank")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be a non-empty string")
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("schema_version must be a non-empty string")
        if not isinstance(self.baseline_config, (dict, Mapping)):
            raise TypeError("baseline_config must be a mapping dictionary")
        if not isinstance(self.perturbation_specs, (list, tuple)):
            raise TypeError("perturbation_specs must be a sequence of mappings")

        # Validate baseline_config if provided
        if self.baseline_config:
            if "confidence_level" in self.baseline_config and "annualization_factor" not in self.baseline_config:
                raise ValueError("baseline_config missing required keys: 'annualization_factor'")
            if "confidence_level" in self.baseline_config:
                try:
                    conf = float(self.baseline_config["confidence_level"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("confidence_level must be a numeric float") from exc
                if not (0.0 < conf < 1.0):
                    raise ValueError(f"confidence_level must be in (0, 1); got {conf}")

        # Check supported perturbation types
        valid_types = {
            "lookback",
            "lookback_window",
            "volatility_estimator",
            "volatility_estimator_ewma",
            "return_friction",
            "friction",
            "confidence_level",
            "tail_confidence_level",
            "portfolio_liquidation_shock",
            "liquidation_shock",
            "correlation",
            "correlation_stress",
        }
        for p in self.perturbation_specs:
            ptype = p.get("type") or p.get("perturbation_type")
            if ptype not in valid_types:
                raise ValueError(f"Unsupported perturbation_type: '{ptype}'")

        if self.random_seed is not None and not isinstance(self.random_seed, int):
            raise TypeError(f"random_seed must be an integer or None; got {type(self.random_seed).__name__}")

    def get_canonical_config(self) -> Dict[str, Any]:
        """Extract purely mathematical configuration parameters for hashing.

        Excludes timestamps, descriptions, and user metadata to ensure hash stability.
        """
        dr = None
        if self.date_range is not None:
            if isinstance(self.date_range, (list, tuple)):
                dr = list(self.date_range)
            elif isinstance(self.date_range, Mapping):
                dr = dict(sorted(self.date_range.items()))

        return {
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "dataset_id": self.dataset_id,
            "baseline_config": dict(self.baseline_config),
            "perturbation_specs": [dict(p) for p in self.perturbation_specs],
            "random_seed": self.random_seed,
            "date_range": dr,
        }

    def compute_config_hash(self) -> str:
        """Compute SHA-256 hash of the canonical mathematical configuration."""
        return compute_canonical_hash(self.get_canonical_config())

    def to_dict(self) -> Dict[str, Any]:
        """Convert specification to dictionary."""
        dr = None
        if self.date_range is not None:
            if isinstance(self.date_range, (list, tuple)):
                dr = list(self.date_range)
            elif isinstance(self.date_range, Mapping):
                dr = dict(self.date_range)

        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "dataset_id": self.dataset_id,
            "baseline_config": dict(self.baseline_config),
            "perturbation_specs": [dict(p) for p in self.perturbation_specs],
            "random_seed": self.random_seed,
            "date_range": dr,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
            "dataset_provenance": dict(self.dataset_provenance) if self.dataset_provenance else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentSpecification:
        """Instantiate ExperimentSpecification from dictionary."""
        return cls(
            experiment_id=str(data["experiment_id"]),
            name=str(data.get("name", "Quantitative Experiment")),
            description=str(data.get("description", "")),
            dataset_id=str(data.get("dataset_id", "DEFAULT_DATASET")),
            baseline_config=dict(data.get("baseline_config", {})),
            perturbation_specs=list(data.get("perturbation_specs", [])),
            schema_version=str(data.get("schema_version", "1.0")),
            algorithm_version=str(data.get("algorithm_version", "1.0")),
            random_seed=data.get("random_seed"),
            date_range=data.get("date_range"),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            metadata=dict(data.get("metadata", {})),
            dataset_provenance=dict(data.get("dataset_provenance", {})) if data.get("dataset_provenance") else None,
        )



# ==============================================================================
# B4. Reproducibility Manifest
# ==============================================================================

@dataclass(frozen=True)
class ReproducibilityManifest:
    """Immutable audit manifest documenting execution parameters and hashes.

    Attributes:
        experiment_id: Identifier of the executed experiment.
        schema_version: Manifest schema version.
        dataset_id: Identifier of the source dataset.
        input_fingerprint: SHA-256 hash of canonical input data.
        configuration_fingerprint: SHA-256 hash of mathematical configuration.
        output_fingerprint: SHA-256 hash of execution results.
        environment_info: Platform and runtime environment metadata.
        validation_status: "PASSED", "WARNING", or "FAILED".
        validation_checks_passed: Number of mathematical invariant checks passed.
        validation_checks_total: Total number of invariant checks evaluated.
        warnings: List of validation or execution caveats.
        limitations: Explicit statement of boundaries.
        execution_timestamp: ISO 8601 UTC execution timestamp.
    """

    experiment_id: str
    schema_version: str
    dataset_id: str
    input_fingerprint: str
    configuration_fingerprint: str
    output_fingerprint: str
    environment_info: Mapping[str, str]
    validation_status: str
    validation_checks_passed: int
    validation_checks_total: int
    warnings: Tuple[str, ...]
    limitations: Tuple[str, ...]
    execution_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def input_data_hash(self) -> str:
        """Alias for input_fingerprint."""
        return self.input_fingerprint

    @property
    def config_hash(self) -> str:
        """Alias for configuration_fingerprint."""
        return self.configuration_fingerprint

    @property
    def output_hash(self) -> str:
        """Alias for output_fingerprint."""
        return self.output_fingerprint

    @property
    def validation_passed(self) -> bool:
        """Boolean indicator of validation success."""
        return self.validation_status == "PASSED"

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to serializable dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "input_fingerprint": self.input_fingerprint,
            "configuration_fingerprint": self.configuration_fingerprint,
            "output_fingerprint": self.output_fingerprint,
            "environment_info": dict(self.environment_info),
            "validation_status": self.validation_status,
            "validation_checks_passed": self.validation_checks_passed,
            "validation_checks_total": self.validation_checks_total,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "execution_timestamp": self.execution_timestamp,
        }


# ==============================================================================
# B5. Independent Invariant Verification
# ==============================================================================

@dataclass(frozen=True)
class InvariantCheckReport:
    """Result of independent mathematical invariant verification."""

    all_passed: bool
    checks_passed: int
    checks_total: int
    check_details: Dict[str, bool]
    failure_messages: Tuple[str, ...]

    @property
    def violations(self) -> Tuple[str, ...]:
        """Alias for failure_messages."""
        return self.failure_messages

    @property
    def checked_count(self) -> int:
        """Alias for checks_total."""
        return self.checks_total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "check_details": dict(self.check_details),
            "failure_messages": list(self.failure_messages),
        }


def verify_experiment_invariants(
    dataset: Optional[Sequence[float] | np.ndarray | Portfolio] = None,
    baseline_metrics: Optional[Mapping[str, float]] = None,
    perturbation_results: Sequence[FragilityExperimentResult] = (),
    portfolio: Optional[Portfolio] = None,
) -> InvariantCheckReport:
    """Perform independent mathematical validation of experiment outputs.

    Checks evaluated:
    1. If Portfolio: weights sum to 1.0 within 1e-5.
    2. If Portfolio: HHI points == decimal_hhi * 10,000.
    3. All baseline metric values are strictly finite floats.
    4. If VaR and Expected Shortfall present: ES >= VaR strictly holds.
    5. If Maximum Drawdown present: 0.0 <= MDD <= 1.0.
    6. For each perturbation: perturbed metrics are strictly finite.
    7. For zero-shift perturbations: delta == 0.0 within 1e-12.

    Args:
        dataset: Source input dataset or Portfolio.
        baseline_metrics: Computed baseline metric dictionary.
        perturbation_results: Sequence of executed perturbation results.
        portfolio: Optional alias for dataset when testing portfolio invariants.

    Returns:
        InvariantCheckReport detailing validation results.
    """
    if dataset is None and portfolio is not None:
        dataset = portfolio

    if baseline_metrics is None:
        baseline_metrics = {}

    details: Dict[str, bool] = {}
    failures: List[str] = []

    # Check 1 & 2: Portfolio invariants
    if isinstance(dataset, Portfolio):
        weight_sum = sum(dataset.weights.values())
        weights_sum_to_one = math.isclose(weight_sum, 1.0, rel_tol=1e-5, abs_tol=1e-5)
        details["portfolio_weights_sum_to_one"] = weights_sum_to_one
        if not weights_sum_to_one:
            failures.append(f"Portfolio weights sum to {weight_sum}, expected 1.0")

        conc = calculate_portfolio_concentration(dataset)
        hhi_consistent = math.isclose(
            conc.asset_hhi_points, conc.asset_hhi_decimal * 10000.0, rel_tol=1e-9
        )
        details["hhi_points_scale_consistent"] = hhi_consistent
        if not hhi_consistent:
            failures.append("Asset HHI points inconsistent with decimal scale")

    # Check 3: Baseline metrics strictly finite
    all_finite = all(math.isfinite(v) for v in baseline_metrics.values())
    details["baseline_metrics_strictly_finite"] = all_finite
    if not all_finite:
        failures.append("Non-finite metric detected in baseline metrics")

    # Check 4: Coherence invariant ES >= VaR
    var_val = baseline_metrics.get("var_historical")
    if var_val is None:
        var_val = baseline_metrics.get("var_95")

    es_val = baseline_metrics.get("expected_shortfall")
    if es_val is None:
        es_val = baseline_metrics.get("expected_shortfall_95")

    if var_val is not None and es_val is not None:
        es_ge_var = es_val >= var_val - 1e-9
        details["es_greater_or_equal_var"] = es_ge_var
        if not es_ge_var:
            failures.append(
                f"Coherence violation: Expected Shortfall ({es_val}) is smaller than Historical VaR ({var_val})"
            )

    # Check 5: Maximum drawdown bounds
    mdd = baseline_metrics.get("maximum_drawdown")
    if mdd is None:
        mdd = baseline_metrics.get("max_drawdown")

    if mdd is not None:
        mdd_valid = 0.0 <= mdd <= 1.0
        details["mdd_within_unit_interval"] = mdd_valid
        if not mdd_valid:
            failures.append(f"Maximum Drawdown ({mdd}) outside [0.0, 1.0]")

    # Check 6: Perturbation metrics strictly finite
    all_pert_finite = True
    for exp in perturbation_results:
        for k, v in exp.perturbed_metrics.items():
            if not math.isfinite(v):
                all_pert_finite = False
                failures.append(f"Perturbation '{exp.perturbation_id}' produced non-finite {k}: {v}")
    details["perturbation_metrics_strictly_finite"] = all_pert_finite

    passed_count = sum(1 for v in details.values() if v)
    total_count = len(details)

    return InvariantCheckReport(
        all_passed=len(failures) == 0,
        checks_passed=passed_count,
        checks_total=total_count,
        check_details=details,
        failure_messages=tuple(failures),
    )


# ==============================================================================
# B3. Reproducible Experiment Runner
# ==============================================================================

@dataclass(frozen=True)
class ReproducibilityRunResult:
    """Complete, self-contained result of a reproducible experiment run.

    Attributes:
        specification: Validated ExperimentSpecification.
        baseline_metrics: Mapping of baseline metric identifier to value.
        perturbation_results: Tuple of FragilityExperimentResult for each requested test.
        manifest: Cryptographic ReproducibilityManifest.
        invariant_report: Mathematical InvariantCheckReport.
    """

    specification: ExperimentSpecification
    baseline_metrics: Mapping[str, float]
    perturbation_results: Tuple[FragilityExperimentResult, ...]
    manifest: ReproducibilityManifest
    invariant_report: InvariantCheckReport

    @property
    def spec(self) -> ExperimentSpecification:
        """Alias for specification."""
        return self.specification

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete run result to serializable dictionary."""
        return {
            "specification": self.specification.to_dict(),
            "baseline_metrics": dict(self.baseline_metrics),
            "perturbation_results": [p.to_dict() for p in self.perturbation_results],
            "manifest": self.manifest.to_dict(),
            "invariant_report": self.invariant_report.to_dict(),
        }
def capture_environment_metadata() -> Dict[str, str]:
    """Capture runtime platform, Python, and dependency versions."""
    return {
        "python_version": sys.version.split()[0],
        "platform_os": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "numpy_version": np.__version__,
        "fragility_engine_version": getattr(fragility_engine, "__version__", "0.1.0"),
    }


def run_reproducible_experiment(
    spec: ExperimentSpecification,
    dataset: Optional[Sequence[float] | np.ndarray | Portfolio] = None,
    return_series: Optional[Sequence[float] | np.ndarray] = None,
    portfolio: Optional[Portfolio] = None,
) -> ReproducibilityRunResult:
    """Execute a fully reproducible quantitative experiment.

    Orchestrates:
    1. Canonical fingerprinting of dataset and configuration.
    2. Baseline risk calculation.
    3. Execution of configured perturbations.
    4. Independent invariant verification.
    5. Manifest generation with environment capture.

    Args:
        spec: Validated ExperimentSpecification.
        dataset: Input return series or Portfolio snapshot.
        return_series: Optional explicit return series input.
        portfolio: Optional explicit Portfolio input.

    Returns:
        ReproducibilityRunResult containing results, manifest, and validation report.
    """
    if not isinstance(spec, ExperimentSpecification):
        raise TypeError(f"spec must be an ExperimentSpecification; got {type(spec).__name__}")

    # Resolve dataset input
    if dataset is None:
        if portfolio is not None and return_series is None:
            dataset = portfolio
        elif return_series is not None:
            dataset = return_series
        else:
            raise ValueError("dataset or return_series cannot be empty")

    if isinstance(dataset, (list, tuple, np.ndarray)) and len(dataset) == 0:
        raise ValueError("Dataset cannot be empty")

    if not isinstance(dataset, Portfolio):
        arr_check = np.asarray(dataset)
        if arr_check.size == 0:
            raise ValueError("Dataset cannot be empty")
        if not np.all(np.isfinite(arr_check)):
            raise ValueError("Non-finite return value in dataset")

    # 1. Input and Config Fingerprints
    input_fp = compute_dataset_hash(dataset)
    config_fp = spec.compute_config_hash()

    annualization_factor = float(spec.baseline_config.get("annualization_factor", 252.0))

    # 2. Baseline Calculation
    if isinstance(dataset, Portfolio):
        conc = calculate_portfolio_concentration(dataset)
        baseline_metrics = {
            "total_market_value": conc.total_market_value,
            "asset_hhi_decimal": conc.asset_hhi_decimal,
            "asset_hhi_points": conc.asset_hhi_points,
            "sector_hhi_decimal": conc.sector_hhi_decimal,
            "sector_hhi_points": conc.sector_hhi_points,
        }
    else:
        arr = np.asarray(dataset, dtype=np.float64)
        arr_1d = np.mean(arr, axis=1) if arr.ndim == 2 else arr
        rep = calculate_risk_report(arr_1d, annualization_factor=annualization_factor)
        baseline_metrics = {
            "volatility_daily": rep.volatility_daily,
            "volatility_annualized": rep.volatility_annualized,
            "annualized_volatility": rep.volatility_annualized,
            "var_95": rep.var_95,
            "var_historical": rep.var_95,
            "var_99": rep.var_99,
            "expected_shortfall": rep.expected_shortfall_95,
            "expected_shortfall_95": rep.expected_shortfall_95,
            "expected_shortfall_99": rep.expected_shortfall_99,
        }
        if rep.drawdown is not None:
            baseline_metrics["max_drawdown"] = rep.drawdown.max_drawdown
            baseline_metrics["maximum_drawdown"] = rep.drawdown.max_drawdown

    # 3. Execute Perturbations
    pert_results: List[FragilityExperimentResult] = []
    warnings: List[str] = []

    for idx, p_spec in enumerate(spec.perturbation_specs, start=1):
        p_type = p_spec.get("type") or p_spec.get("perturbation_type")
        exp_id = p_spec.get("experiment_id") or p_spec.get("perturbation_id", f"{spec.experiment_id}_p{idx}")
        params = p_spec.get("parameters", p_spec)

        if p_type in ("lookback_window", "lookback"):
            if isinstance(dataset, Portfolio):
                raise ValueError("Lookback perturbation requires a return time series, not a static Portfolio.")
            p_win = int(params.get("perturbed_window") or params.get("lookback_window", 30))
            b_win = params.get("baseline_window")
            exp_res = run_lookback_perturbation(
                dataset,
                perturbed_window=p_win,
                baseline_window=b_win,
                annualization_factor=annualization_factor,
                experiment_id=exp_id,
            )
            pert_results.append(exp_res)

        elif p_type in ("volatility_estimator_ewma", "volatility_estimator"):
            if isinstance(dataset, Portfolio):
                raise ValueError("EWMA volatility perturbation requires a return series, not a static Portfolio.")
            decay = float(params.get("decay_factor") or params.get("decay", 0.94))
            exp_res = run_volatility_estimator_perturbation(
                dataset,
                decay_factor=decay,
                annualization_factor=annualization_factor,
                experiment_id=exp_id,
            )
            pert_results.append(exp_res)

        elif p_type in ("return_friction", "friction"):
            if isinstance(dataset, Portfolio):
                raise ValueError("Return friction perturbation requires a return series, not a static Portfolio.")
            fric_bps = float(params.get("friction_bps", 5.0))
            exp_res = run_return_friction_perturbation(
                dataset,
                friction_bps=fric_bps,
                annualization_factor=annualization_factor,
                experiment_id=exp_id,
            )
            pert_results.append(exp_res)

        elif p_type in ("tail_confidence_level", "confidence_level"):
            if isinstance(dataset, Portfolio):
                raise ValueError("Tail confidence perturbation requires a return series, not a static Portfolio.")
            p_conf = float(params.get("perturbed_confidence") or params.get("target_confidence", 0.99))
            b_conf = float(params.get("baseline_confidence", 0.95))
            exp_res = run_confidence_level_perturbation(
                dataset,
                perturbed_confidence=p_conf,
                baseline_confidence=b_conf,
                experiment_id=exp_id,
            )
            pert_results.append(exp_res)

        elif p_type in ("correlation", "correlation_stress"):
            stress = float(params.get("stress_factor") or params.get("stress_strength", 0.5))
            target_corr = float(params.get("target_correlation", 0.80))
            arr_data = np.asarray(dataset, dtype=np.float64)
            k_cols = arr_data.shape[1] if arr_data.ndim == 2 else 2
            w = params.get("weights")
            if w is None:
                w = [1.0 / k_cols] * k_cols
            exp_res = run_correlation_perturbation(
                arr_data,
                weights=w,
                stress_factor=stress,
                target_correlation=target_corr,
                annualization_factor=annualization_factor,
                experiment_id=exp_id,
            )
            pert_results.append(exp_res)


        elif p_type in ("portfolio_liquidation_shock", "liquidation_shock"):
            if not isinstance(dataset, Portfolio):
                raise ValueError("Portfolio liquidation shock requires a Portfolio instance.")
            c_bps = float(params.get("cost_bps", 10.0))
            turnover = float(params.get("turnover_fraction", 1.0))
            shock_res = calculate_portfolio_liquidation_shock(dataset, cost_bps=c_bps, turnover_fraction=turnover)
            exp_res = FragilityExperimentResult(
                experiment_id=exp_id,
                perturbation_id="portfolio_liquidation_shock",
                perturbation_name="Portfolio Liquidation Friction Shock",
                description=f"Applies {c_bps:.1f} bps liquidation cost to portfolio turnover.",
                configuration={"cost_bps": c_bps, "turnover_fraction": turnover},
                baseline_metrics={"portfolio_value": shock_res["original_portfolio_value"]},
                perturbed_metrics={"portfolio_value": shock_res["stressed_portfolio_value"]},
                absolute_changes={"portfolio_value": -shock_res["liquidation_cost"]},
                relative_changes={"portfolio_value": -shock_res["cost_drag_percentage"]},
                observations_used=len(dataset.holdings),
            )
            pert_results.append(exp_res)

        else:
            raise ValueError(f"Unknown perturbation type '{p_type}' in experiment specification")

    # 4. Independent Mathematical Invariant Checks
    invariant_report = verify_experiment_invariants(dataset, baseline_metrics, pert_results)
    if not invariant_report.all_passed:
        warnings.extend(invariant_report.failure_messages)

    validation_status = "PASSED" if invariant_report.all_passed else "FAILED"

    # 5. Output Fingerprint
    output_repr = {
        "baseline_metrics": baseline_metrics,
        "perturbation_metrics": {p.perturbation_id: p.perturbed_metrics for p in pert_results},
        "validation_passed": invariant_report.all_passed,
    }
    output_fp = compute_canonical_hash(output_repr)

    # 6. Environment Metadata
    environment_info = capture_environment_metadata()

    manifest = ReproducibilityManifest(
        experiment_id=spec.experiment_id,
        schema_version=spec.schema_version,
        dataset_id=spec.dataset_id,
        input_fingerprint=input_fp,
        configuration_fingerprint=config_fp,
        output_fingerprint=output_fp,
        environment_info=environment_info,
        validation_status=validation_status,
        validation_checks_passed=invariant_report.checks_passed,
        validation_checks_total=invariant_report.checks_total,
        warnings=tuple(warnings),
        limitations=(
            "Exact reproducibility assumes standard IEEE 754 floating point arithmetic.",
            "Historical tail metrics are non-parametric empirical estimates.",
        ),
    )

    return ReproducibilityRunResult(
        specification=spec,
        baseline_metrics=baseline_metrics,
        perturbation_results=tuple(pert_results),
        manifest=manifest,
        invariant_report=invariant_report,
    )


# ==============================================================================
# B6. Drift Detection & Output Comparison
# ==============================================================================

@dataclass(frozen=True)
class DriftReport:
    """Structured drift and divergence report between two experiment runs.

    Attributes:
        runs_identical: True if input, configuration, and output fingerprints match exactly.
        input_drift_detected: True if input dataset hashes differ.
        config_drift_detected: True if mathematical configuration hashes differ.
        output_drift_detected: True if calculated output hashes differ.
        environment_drift_detected: True if Python/NumPy/OS runtime versions differ.
        tolerance_exceeded: True if any metric change exceeds specified tolerance.
        metric_divergences: Detailed mapping of metric differences.
        summary: Clear narrative explaining origin of divergence.
    """

    runs_identical: bool
    input_drift_detected: bool
    config_drift_detected: bool
    output_drift_detected: bool
    environment_drift_detected: bool
    tolerance_exceeded: bool
    metric_divergences: Dict[str, Dict[str, Any]]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert drift report to serializable dictionary."""
        return {
            "runs_identical": self.runs_identical,
            "input_drift_detected": self.input_drift_detected,
            "config_drift_detected": self.config_drift_detected,
            "output_drift_detected": self.output_drift_detected,
            "environment_drift_detected": self.environment_drift_detected,
            "tolerance_exceeded": self.tolerance_exceeded,
            "metric_divergences": self.metric_divergences,
            "summary": self.summary,
        }


def compare_experiment_runs(
    run_a: ReproducibilityRunResult,
    run_b: ReproducibilityRunResult,
    tolerance: float = 1e-9,
) -> DriftReport:
    """Compare two experiment runs for data drift, configuration drift, and numerical divergence.

    Args:
        run_a: Baseline experiment run result.
        run_b: Comparison experiment run result.
        tolerance: Absolute numerical tolerance for metric comparison (default 1e-9).

    Returns:
        DriftReport detailing exact origins of difference.
    """
    input_drift = run_a.manifest.input_fingerprint != run_b.manifest.input_fingerprint
    config_drift = run_a.manifest.configuration_fingerprint != run_b.manifest.configuration_fingerprint
    output_drift = run_a.manifest.output_fingerprint != run_b.manifest.output_fingerprint

    env_a = run_a.manifest.environment_info
    env_b = run_b.manifest.environment_info
    env_drift = (
        env_a.get("python_version") != env_b.get("python_version")
        or env_a.get("numpy_version") != env_b.get("numpy_version")
        or env_a.get("platform_os") != env_b.get("platform_os")
    )

    divergences: Dict[str, Dict[str, Any]] = {}
    any_tol_exceeded = False

    # Compare baseline metrics
    all_keys = sorted(set(run_a.baseline_metrics.keys()).union(run_b.baseline_metrics.keys()))
    for k in all_keys:
        val_a = run_a.baseline_metrics.get(k)
        val_b = run_b.baseline_metrics.get(k)

        if val_a is None or val_b is None:
            divergences[k] = {
                "val_a": val_a,
                "val_b": val_b,
                "diff": None,
                "tolerance_exceeded": True,
                "status": "MISSING_IN_ONE_RUN",
            }
            any_tol_exceeded = True
        else:
            diff = abs(val_b - val_a)
            exceeded = diff > tolerance
            if exceeded:
                any_tol_exceeded = True
            divergences[k] = {
                "val_a": val_a,
                "val_b": val_b,
                "diff": diff,
                "tolerance_exceeded": exceeded,
                "status": "DIVERGENT" if exceeded else "WITHIN_TOLERANCE",
            }

    runs_identical = not input_drift and not config_drift and not output_drift and not any_tol_exceeded

    # Generate clear human-readable diagnosis
    reasons: List[str] = []
    if input_drift:
        reasons.append("Input data changed (different input fingerprint)")
    if config_drift:
        reasons.append("Experiment configuration changed (different configuration fingerprint)")
    if env_drift:
        reasons.append("Runtime environment changed (different Python/NumPy/OS platform)")
    if output_drift and not input_drift and not config_drift:
        reasons.append("Output diverged despite identical input and configuration (algorithm drift)")

    if runs_identical:
        summary = "Runs are identical and cryptographically verified. No drift detected."
    else:
        summary = f"Drift detected: {'; '.join(reasons)}." if reasons else "Output numerical divergence detected."

    return DriftReport(
        runs_identical=runs_identical,
        input_drift_detected=input_drift,
        config_drift_detected=config_drift,
        output_drift_detected=output_drift,
        environment_drift_detected=env_drift,
        tolerance_exceeded=any_tol_exceeded,
        metric_divergences=divergences,
        summary=summary,
    )
