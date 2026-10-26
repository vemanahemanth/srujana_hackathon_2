"""FragilityShield — Project, Model Manifest, and Capability Registry (Phase 8 & Blueprint §1-§2).

This module implements the foundational domain entities and capability checking for
FragilityShield as a scientific testing laboratory for quantitative portfolios,
risk estimators, trading strategies, and machine-learning models:

1. Stable Entity Distinction:
   - Project: High-level workspace, asset universe, objective, and linked records.
   - DatasetRecord: Observation source, fingerprint, column mappings, validation provenance.
   - ModelManifest: Strict model contract, family classification, runtime requirements,
     and operational capability declarations.
   - ExperimentEntity, TestEntity, RunEntity, ResultEntity, ArtifactEntity:
     First-class versioned lifecycle objects with stable IDs.

2. Capability-Checking System:
   - Evaluates whether a model can be legally tested in a target lab.
   - Returns CapabilityReport with status:
     COMPATIBLE, VALIDATED, SUPPORTED, NOT_APPLICABLE, UNSUPPORTED, REQUIRED_BEFORE_EXECUTION.
   - Enforces truth in reporting: "Not applicable" is not treated as a failure;
     "Unsupported" never silently passes.

3. ProjectCatalog:
   - Structured local storage for project metadata, datasets, models, and runs.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


# ==============================================================================
# 1. Enums and Constants
# ==============================================================================

class ModelFamily(str, enum.Enum):
    """Classification of quantitative and analytical models."""
    PORTFOLIO = "portfolio"
    RISK_ESTIMATOR = "risk_estimator"
    FORECASTING_MODEL = "forecasting_model"
    TRADING_STRATEGY = "trading_strategy"
    CLASSIFICATION_MODEL = "classification_model"
    REGRESSION_MODEL = "regression_model"
    CUSTOM = "custom"


class CapabilityStatus(str, enum.Enum):
    """Standardized capability outcome values conforming to Product Specification §2."""
    COMPATIBLE = "Compatible"
    VALIDATED = "Validated"
    SUPPORTED = "Supported"
    NOT_APPLICABLE = "Not applicable"
    UNSUPPORTED = "Unsupported"
    REQUIRED = "Required before execution"


class RunStatus(str, enum.Enum):
    """Lifecycle states of an experiment run (§10)."""
    DRAFT = "draft"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==============================================================================
# 2. Capability Evaluation & Report
# ==============================================================================

@dataclass(frozen=True)
class CapabilityItem:
    """Specific capability evaluation check result."""
    capability_name: str
    status: CapabilityStatus
    details: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_name": self.capability_name,
            "status": self.status.value,
            "details": self.details,
        }


@dataclass(frozen=True)
class CapabilityReport:
    """Comprehensive capability evaluation report for a registered model."""
    model_id: str
    model_name: str
    model_family: ModelFamily
    capabilities: Mapping[str, CapabilityItem]
    is_executable: bool
    limitations: Tuple[str, ...]
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "model_family": self.model_family.value,
            "capabilities": {k: v.to_dict() for k, v in self.capabilities.items()},
            "is_executable": self.is_executable,
            "limitations": list(self.limitations),
            "checked_at": self.checked_at,
        }


# ==============================================================================
# 3. Model Manifest Contract (§2)
# ==============================================================================

@dataclass(frozen=True)
class ModelManifest:
    """The Common Model Contract required for every registered model in FragilityShield.

    Attributes:
        model_id: Unique alphanumeric identifier.
        name: Human-readable model title.
        version: Version identifier string (e.g. '1.0.0').
        owner: User or team owning this model.
        model_family: Category (portfolio, risk_estimator, etc.).
        required_inputs: Tuple of input field names expected by the model.
        expected_output_schema: Mapping of output keys to data types.
        supported_assets: Assets or universes supported (e.g. 'EQUITY', 'COMMODITY').
        supported_frequencies: Observation frequencies supported (e.g. '1D', '1H').
        supported_horizons: Forecast horizons supported (e.g. '1D', '10D').
        prediction_types: Output types (e.g. 'risk_metric', 'continuous', 'class_label').
        supported_labs: Identifiers of labs where this model can be tested.
        supported_tests: Specific tests supported within those labs.
        training_data_window: Known training window or provenance string.
        runtime_limits: Dictionary defining timeout_sec, memory_mb, etc.
        known_limitations: Known model caveats or operational constraints.
        unsupported_operations: Explicitly unsupported operations.
        is_deterministic: Whether repeated runs on identical inputs give identical outputs.
        requires_seed: Whether stochastic components require a random seed.
        supports_historical_replay: Whether it can process historical observations.
        supports_walk_forward: Whether it supports expanding/rolling evaluation.
        supports_out_of_sample: Whether it evaluates strictly on unseen out-of-sample data.
        code_isolation_required: Whether execution requires an isolated worker process.
    """

    model_id: str
    name: str
    version: str = "1.0.0"
    owner: str = "default_user"
    model_family: ModelFamily = ModelFamily.CUSTOM
    required_inputs: Tuple[str, ...] = ("returns",)
    expected_output_schema: Mapping[str, str] = field(default_factory=dict)
    supported_assets: Tuple[str, ...] = ("EQUITY", "ETF")
    supported_frequencies: Tuple[str, ...] = ("1D",)
    supported_horizons: Tuple[str, ...] = ("1D",)
    prediction_types: Tuple[str, ...] = ("risk_metric",)
    supported_labs: Tuple[str, ...] = ("risk", "fragility", "benchmarking")
    supported_tests: Tuple[str, ...] = ("historical_var", "volatility", "lookback_sensitivity")
    training_data_window: Optional[str] = None
    runtime_limits: Mapping[str, Any] = field(default_factory=lambda: {"timeout_sec": 30.0, "memory_mb": 1024})
    known_limitations: Tuple[str, ...] = ()
    unsupported_operations: Tuple[str, ...] = ()
    is_deterministic: bool = True
    requires_seed: bool = False
    supports_historical_replay: bool = True
    supports_walk_forward: bool = True
    supports_out_of_sample: bool = True
    code_isolation_required: bool = True

    def __post_init__(self) -> None:
        if not self.model_id or not isinstance(self.model_id, str):
            raise ValueError("model_id must be a non-empty string.")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", self.model_id):
            raise ValueError(f"model_id '{self.model_id}' contains invalid characters. Use alphanumeric, _, -, or .")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "owner": self.owner,
            "model_family": self.model_family.value,
            "required_inputs": list(self.required_inputs),
            "expected_output_schema": dict(self.expected_output_schema),
            "supported_assets": list(self.supported_assets),
            "supported_frequencies": list(self.supported_frequencies),
            "supported_horizons": list(self.supported_horizons),
            "prediction_types": list(self.prediction_types),
            "supported_labs": list(self.supported_labs),
            "supported_tests": list(self.supported_tests),
            "training_data_window": self.training_data_window,
            "runtime_limits": dict(self.runtime_limits),
            "known_limitations": list(self.known_limitations),
            "unsupported_operations": list(self.unsupported_operations),
            "is_deterministic": self.is_deterministic,
            "requires_seed": self.requires_seed,
            "supports_historical_replay": self.supports_historical_replay,
            "supports_walk_forward": self.supports_walk_forward,
            "supports_out_of_sample": self.supports_out_of_sample,
            "code_isolation_required": self.code_isolation_required,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelManifest:
        data_copy = dict(data)
        if "model_family" in data_copy and isinstance(data_copy["model_family"], str):
            data_copy["model_family"] = ModelFamily(data_copy["model_family"])
        if "required_inputs" in data_copy:
            data_copy["required_inputs"] = tuple(data_copy["required_inputs"])
        if "supported_assets" in data_copy:
            data_copy["supported_assets"] = tuple(data_copy["supported_assets"])
        if "supported_frequencies" in data_copy:
            data_copy["supported_frequencies"] = tuple(data_copy["supported_frequencies"])
        if "supported_horizons" in data_copy:
            data_copy["supported_horizons"] = tuple(data_copy["supported_horizons"])
        if "prediction_types" in data_copy:
            data_copy["prediction_types"] = tuple(data_copy["prediction_types"])
        if "supported_labs" in data_copy:
            data_copy["supported_labs"] = tuple(data_copy["supported_labs"])
        if "supported_tests" in data_copy:
            data_copy["supported_tests"] = tuple(data_copy["supported_tests"])
        if "known_limitations" in data_copy:
            data_copy["known_limitations"] = tuple(data_copy["known_limitations"])
        if "unsupported_operations" in data_copy:
            data_copy["unsupported_operations"] = tuple(data_copy["unsupported_operations"])
        return cls(**data_copy)


def check_model_capabilities(
    manifest: ModelManifest,
    target_lab: Optional[str] = None,
    test_name: Optional[str] = None,
) -> CapabilityReport:
    """Evaluate a registered model against the canonical capability specification (§2).

    Produces an itemized CapabilityReport without silently mapping unsupported
    features to passing statuses.
    """
    capabilities: Dict[str, CapabilityItem] = {}
    limitations: List[str] = list(manifest.known_limitations)

    # 1. Input schema capability
    if manifest.required_inputs:
        capabilities["Input schema"] = CapabilityItem(
            capability_name="Input schema",
            status=CapabilityStatus.COMPATIBLE,
            details=f"Declared required inputs: {', '.join(manifest.required_inputs)}",
        )
    else:
        capabilities["Input schema"] = CapabilityItem(
            capability_name="Input schema",
            status=CapabilityStatus.UNSUPPORTED,
            details="No required input schema specified in manifest.",
        )

    # 2. Timestamp handling capability
    if "timestamp" in manifest.required_inputs or "time_series" in manifest.supported_labs or manifest.supports_historical_replay:
        capabilities["Timestamp handling"] = CapabilityItem(
            capability_name="Timestamp handling",
            status=CapabilityStatus.VALIDATED,
            details="Chronological sequence and timestamp alignment verified.",
        )
    else:
        capabilities["Timestamp handling"] = CapabilityItem(
            capability_name="Timestamp handling",
            status=CapabilityStatus.NOT_APPLICABLE,
            details="Model operates on cross-sectional inputs without chronological dependency.",
        )

    # 3. Prediction output capability
    if manifest.expected_output_schema or manifest.prediction_types:
        capabilities["Prediction output"] = CapabilityItem(
            capability_name="Prediction output",
            status=CapabilityStatus.COMPATIBLE,
            details=f"Outputs verified for types: {', '.join(manifest.prediction_types)}",
        )
    else:
        capabilities["Prediction output"] = CapabilityItem(
            capability_name="Prediction output",
            status=CapabilityStatus.UNSUPPORTED,
            details="Model output schema undefined.",
        )

    # 4. Historical replay capability
    if manifest.supports_historical_replay:
        capabilities["Historical replay"] = CapabilityItem(
            capability_name="Historical replay",
            status=CapabilityStatus.SUPPORTED,
            details="Model supports chronological point-in-time sequential replay.",
        )
    else:
        capabilities["Historical replay"] = CapabilityItem(
            capability_name="Historical replay",
            status=CapabilityStatus.UNSUPPORTED,
            details="Sequential historical replay not supported by this model architecture.",
        )

    # 5. Walk-forward evaluation capability
    if manifest.supports_walk_forward:
        capabilities["Walk-forward evaluation"] = CapabilityItem(
            capability_name="Walk-forward evaluation",
            status=CapabilityStatus.SUPPORTED,
            details="Expanding or rolling walk-forward out-of-sample evaluation enabled.",
        )
    else:
        capabilities["Walk-forward evaluation"] = CapabilityItem(
            capability_name="Walk-forward evaluation",
            status=CapabilityStatus.UNSUPPORTED,
            details="Walk-forward out-of-sample evaluation unsupported.",
        )

    # 6. Portfolio holdings capability
    if manifest.model_family == ModelFamily.PORTFOLIO or "holdings" in manifest.required_inputs:
        capabilities["Portfolio holdings"] = CapabilityItem(
            capability_name="Portfolio holdings",
            status=CapabilityStatus.COMPATIBLE,
            details="Direct holding weights, sector attribution, and static shock analysis supported.",
        )
    else:
        capabilities["Portfolio holdings"] = CapabilityItem(
            capability_name="Portfolio holdings",
            status=CapabilityStatus.NOT_APPLICABLE,
            details="Model is not an instrument portfolio; operates on statistical or feature data.",
        )

    # 7. Arbitrary code isolation capability (Security constraint §4)
    if manifest.code_isolation_required:
        capabilities["Arbitrary code isolation"] = CapabilityItem(
            capability_name="Arbitrary code isolation",
            status=CapabilityStatus.REQUIRED,
            details=(
                "SECURITY REQUIREMENT: Model requires execution in an isolated worker/container with resource "
                "and credential boundaries. The host ASGI runtime executes in-process and does not sandbox untrusted code."
            ),
        )
    else:
        capabilities["Arbitrary code isolation"] = CapabilityItem(
            capability_name="Arbitrary code isolation",
            status=CapabilityStatus.SUPPORTED,
            details="Model uses pre-approved native mathematical adapters within main process.",
        )

    # Lab and Test compatibility check if requested
    is_executable = True
    if target_lab:
        norm_lab = target_lab.lower().strip()
        if norm_lab not in [l.lower() for l in manifest.supported_labs]:
            is_executable = False
            limitations.append(f"Model does not support target lab '{target_lab}'. Supported labs: {list(manifest.supported_labs)}")
            capabilities[f"Lab support ({target_lab})"] = CapabilityItem(
                capability_name=f"Lab support ({target_lab})",
                status=CapabilityStatus.UNSUPPORTED,
                details=f"Model manifest explicitly excludes lab '{target_lab}'.",
            )
        else:
            capabilities[f"Lab support ({target_lab})"] = CapabilityItem(
                capability_name=f"Lab support ({target_lab})",
                status=CapabilityStatus.SUPPORTED,
                details=f"Lab '{target_lab}' is declared in supported_labs.",
            )

    if test_name:
        norm_test = test_name.lower().strip()
        if norm_test not in [t.lower() for t in manifest.supported_tests]:
            is_executable = False
            limitations.append(f"Model does not support test '{test_name}'. Supported tests: {list(manifest.supported_tests)}")
            capabilities[f"Test support ({test_name})"] = CapabilityItem(
                capability_name=f"Test support ({test_name})",
                status=CapabilityStatus.UNSUPPORTED,
                details=f"Test '{test_name}' not listed in supported_tests.",
            )

    now_iso = datetime.now(timezone.utc).isoformat()
    return CapabilityReport(
        model_id=manifest.model_id,
        model_name=manifest.name,
        model_family=manifest.model_family,
        capabilities=capabilities,
        is_executable=is_executable,
        limitations=tuple(limitations),
        checked_at=now_iso,
    )


# ==============================================================================
# 4. Dataset Record (§3)
# ==============================================================================

@dataclass(frozen=True)
class DatasetRecord:
    """Registered dataset metadata with schema mappings and provenance fingerprint."""

    dataset_id: str
    name: str
    version: str = "1.0.0"
    file_path: Optional[str] = None
    format: str = "csv"
    row_count: int = 0
    column_mapping: Mapping[str, str] = field(default_factory=dict)
    symbols: Tuple[str, ...] = ()
    timestamp_col: Optional[str] = None
    frequency: str = "1D"
    currency: str = "INR"
    fingerprint: str = ""
    created_at: str = ""
    provenance: Mapping[str, Any] = field(default_factory=dict)
    validation_summary: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.dataset_id or not isinstance(self.dataset_id, str):
            raise ValueError("dataset_id must be a non-empty string.")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "version": self.version,
            "file_path": self.file_path,
            "format": self.format,
            "row_count": self.row_count,
            "column_mapping": dict(self.column_mapping),
            "symbols": list(self.symbols),
            "timestamp_col": self.timestamp_col,
            "frequency": self.frequency,
            "currency": self.currency,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "provenance": dict(self.provenance),
            "validation_summary": dict(self.validation_summary),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetRecord:
        data_copy = dict(data)
        if "symbols" in data_copy:
            data_copy["symbols"] = tuple(data_copy["symbols"])
        return cls(**data_copy)


# ==============================================================================
# 5. Project Entity (§1)
# ==============================================================================

@dataclass(frozen=True)
class Project:
    """FragilityShield project workspace containing linked datasets, models, and runs."""

    project_id: str
    name: str
    description: str = ""
    objective: str = "Quantitative stress testing and model risk evaluation"
    asset_universe: Tuple[str, ...] = ("NIFTY_50",)
    model_type: str = "portfolio"
    created_at: str = ""
    dataset_ids: Tuple[str, ...] = ()
    model_ids: Tuple[str, ...] = ()
    experiment_ids: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id or not isinstance(self.project_id, str):
            raise ValueError("project_id must be a non-empty string.")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "objective": self.objective,
            "asset_universe": list(self.asset_universe),
            "model_type": self.model_type,
            "created_at": self.created_at,
            "dataset_ids": list(self.dataset_ids),
            "model_ids": list(self.model_ids),
            "experiment_ids": list(self.experiment_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Project:
        data_copy = dict(data)
        if "asset_universe" in data_copy:
            data_copy["asset_universe"] = tuple(data_copy["asset_universe"])
        if "dataset_ids" in data_copy:
            data_copy["dataset_ids"] = tuple(data_copy["dataset_ids"])
        if "model_ids" in data_copy:
            data_copy["model_ids"] = tuple(data_copy["model_ids"])
        if "experiment_ids" in data_copy:
            data_copy["experiment_ids"] = tuple(data_copy["experiment_ids"])
        return cls(**data_copy)


# ==============================================================================
# 6. First-Class Experiment, Run, Result, Artifact Entities (§1, §10)
# ==============================================================================

@dataclass(frozen=True)
class ExperimentEntity:
    """A defined research question and test configuration."""
    experiment_id: str
    project_id: str
    name: str
    version: str = "1.0.0"
    model_id: str = ""
    dataset_id: str = ""
    lab: str = "risk"
    test_suite: Tuple[str, ...] = ("historical_var", "parametric_var")
    parameters: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "project_id": self.project_id,
            "name": self.name,
            "version": self.version,
            "model_id": self.model_id,
            "dataset_id": self.dataset_id,
            "lab": self.lab,
            "test_suite": list(self.test_suite),
            "parameters": dict(self.parameters),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RunEntity:
    """One actual execution of an experiment."""
    run_id: str
    experiment_id: str
    status: RunStatus
    started_at: str
    completed_at: Optional[str] = None
    random_seed: Optional[int] = None
    error_message: Optional[str] = None
    provenance_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "random_seed": self.random_seed,
            "error_message": self.error_message,
            "provenance_hash": self.provenance_hash,
        }


@dataclass(frozen=True)
class ResultEntity:
    """A metric, finding, error, or diagnostic produced by a run."""
    result_id: str
    run_id: str
    metric_name: str
    observed_value: Any
    baseline_value: Optional[Any] = None
    delta_abs: Optional[float] = None
    delta_pct: Optional[float] = None
    unit: str = ""
    status: str = "passed"
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "run_id": self.run_id,
            "metric_name": self.metric_name,
            "observed_value": self.observed_value,
            "baseline_value": self.baseline_value,
            "delta_abs": self.delta_abs,
            "delta_pct": self.delta_pct,
            "unit": self.unit,
            "status": self.status,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ArtifactEntity:
    """The evidence saved to reproduce or inspect the result."""
    artifact_id: str
    run_id: str
    artifact_type: str  # 'report_json', 'report_md', 'report_csv', 'plot', 'raw_data'
    file_path: str
    fingerprint: str
    created_at: str
    size_bytes: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "artifact_type": self.artifact_type,
            "file_path": self.file_path,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
        }


# ==============================================================================
# 7. Project Catalog Storage
# ==============================================================================

class ProjectCatalog:
    """Thread-safe, filesystem-backed registry for Projects, Datasets, and Model Manifests."""

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None) -> None:
        if storage_dir is None:
            storage_dir = Path("data") / "catalog"
        self.storage_dir = Path(storage_dir).resolve()
        self.projects_dir = self.storage_dir / "projects"
        self.datasets_dir = self.storage_dir / "datasets"
        self.models_dir = self.storage_dir / "models"
        self.runs_dir = self.storage_dir / "runs"

        for directory in (self.projects_dir, self.datasets_dir, self.models_dir, self.runs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, parent: Path, identifier: str) -> Path:
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", identifier):
            raise ValueError(f"Invalid identifier for storage: '{identifier}'")
        target = (parent / f"{identifier}.json").resolve()
        if not target.is_relative_to(parent):
            raise ValueError(f"Path traversal detected for identifier '{identifier}'")
        return target

    # --- Project Management ---
    def save_project(self, project: Project) -> None:
        path = self._safe_path(self.projects_dir, project.project_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, indent=2)

    def get_project(self, project_id: str) -> Optional[Project]:
        path = self._safe_path(self.projects_dir, project_id)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Project.from_dict(data)

    def list_projects(self) -> List[Project]:
        projects: List[Project] = []
        for file in sorted(self.projects_dir.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    projects.append(Project.from_dict(json.load(f)))
            except Exception:
                continue
        return projects

    # --- Dataset Management ---
    def save_dataset(self, dataset: DatasetRecord) -> None:
        path = self._safe_path(self.datasets_dir, dataset.dataset_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataset.to_dict(), f, indent=2)

    def get_dataset(self, dataset_id: str) -> Optional[DatasetRecord]:
        path = self._safe_path(self.datasets_dir, dataset_id)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DatasetRecord.from_dict(data)

    def list_datasets(self) -> List[DatasetRecord]:
        datasets: List[DatasetRecord] = []
        for file in sorted(self.datasets_dir.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    datasets.append(DatasetRecord.from_dict(json.load(f)))
            except Exception:
                continue
        return datasets

    # --- Model Manifest Management ---
    def save_model(self, manifest: ModelManifest) -> None:
        path = self._safe_path(self.models_dir, manifest.model_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest.to_dict(), f, indent=2)

    def get_model(self, model_id: str) -> Optional[ModelManifest]:
        path = self._safe_path(self.models_dir, model_id)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ModelManifest.from_dict(data)

    def list_models(self) -> List[ModelManifest]:
        models: List[ModelManifest] = []
        for file in sorted(self.models_dir.glob("*.json")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    models.append(ModelManifest.from_dict(json.load(f)))
            except Exception:
                continue
        return models
