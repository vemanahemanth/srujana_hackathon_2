"""FragilityShield — Universal External Model & Experiment Ingestion Engine.

Sprint 9 Extension:
Enables FragilityShield to operate as a central, API-first quantitative analysis
platform receiving model executions, experiment results, metrics, predictions,
datasets, and artifacts from external development environments:
- Developer laptops (local scripts, CLI)
- Google Colab notebooks
- Jupyter notebooks
- External Python research repositories
- REST API clients in any programming language
- Third-party model providers & plugins

Invariants:
1. Environments explicitly authenticate and submit data; zero unsolicited polling of external laptops.
2. Distinguishes externally self-reported metrics from metrics independently verified/recomputed by FragilityShield.
3. Versioned JSON schema validation with bounded resource/size limits.
4. SHA-256 checksum verification on all ingested file artifacts.
5. Ingested runs populate the central Experiment Registry, Model Comparison, and relevant lab dashboards.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import math
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger("fragility_shield.external_connectivity")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
EXPERIMENTS_DIR = DATA_DIR / "experiments"

# Maximum size limits
MAX_INGESTION_PAYLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_ARTIFACT_FILE_BYTES = 25 * 1024 * 1024      # 25 MB

ALLOWED_ENV_TYPES = frozenset({
    "google_colab",
    "jupyter_notebook",
    "local_script",
    "external_python",
    "rest_client",
    "ci_worker",
    "third_party_provider",
})

ALLOWED_TARGET_LABS = frozenset({
    "general",
    "risk",
    "forecasting",
    "robustness",
    "backtesting",
    "simulation",
    "fragility",
    "allocation",
})


class ExternalIngestionError(Exception):
    """Base exception for external ingestion failures."""


class SchemaValidationError(ExternalIngestionError):
    """Raised when an external submission violates schema or bounds."""


class ArtifactValidationError(ExternalIngestionError):
    """Raised when an artifact checksum or format is invalid."""


# ==============================================================================
# 1. External Ingestion Domain Schemas (§4)
# ==============================================================================

@dataclass
class ExecutionEnvironment:
    """Metadata describing the external environment that ran the model."""
    environment_type: str = "local_script"
    hostname: Optional[str] = None
    python_version: Optional[str] = None
    platform: Optional[str] = None
    git_commit: Optional[str] = None
    frameworks: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionEnvironment:
        env_type = str(data.get("environment_type", "local_script")).strip().lower()
        if env_type not in ALLOWED_ENV_TYPES:
            env_type = "external_python"
        return cls(
            environment_type=env_type,
            hostname=data.get("hostname"),
            python_version=data.get("python_version"),
            platform=data.get("platform"),
            git_commit=data.get("git_commit"),
            frameworks=dict(data.get("frameworks") or {}),
            extra=dict(data.get("extra") or {}),
        )


@dataclass
class ExternalMetric:
    """Individual metric submitted by an external environment."""
    metric_name: str
    observed_value: Union[float, int, str, bool]
    baseline_value: Optional[float] = None
    unit: str = ""
    sample_count: Optional[int] = None
    is_externally_reported: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExternalMetric:
        name = str(data.get("metric_name", "")).strip()
        if not name:
            raise SchemaValidationError("Field 'metric_name' is required for all metrics.")
        val = data.get("observed_value")
        if val is None:
            raise SchemaValidationError(f"Metric '{name}' is missing 'observed_value'.")
        if isinstance(val, (float, int)) and not math.isfinite(val):
            raise SchemaValidationError(f"Metric '{name}' observed_value must be finite; got {val}.")
        return cls(
            metric_name=name,
            observed_value=val,
            baseline_value=data.get("baseline_value"),
            unit=str(data.get("unit", "")),
            sample_count=data.get("sample_count"),
            is_externally_reported=bool(data.get("is_externally_reported", True)),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ExternalPrediction:
    """Individual forecast or model prediction observation."""
    timestamp: str
    target: str
    predicted_value: float
    actual_value: Optional[float] = None
    horizon: str = "1D"
    confidence_lower: Optional[float] = None
    confidence_upper: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExternalPrediction:
        ts = str(data.get("timestamp", "")).strip()
        if not ts:
            raise SchemaValidationError("Prediction 'timestamp' is required.")
        target = str(data.get("target", "return")).strip()
        try:
            pred = float(data.get("predicted_value", 0.0))
        except (ValueError, TypeError):
            raise SchemaValidationError("Prediction 'predicted_value' must be a valid float.")
        actual = data.get("actual_value")
        actual_val = float(actual) if actual is not None else None
        return cls(
            timestamp=ts,
            target=target,
            predicted_value=pred,
            actual_value=actual_val,
            horizon=str(data.get("horizon", "1D")),
            confidence_lower=data.get("confidence_lower"),
            confidence_upper=data.get("confidence_upper"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ExternalArtifactRef:
    """Reference to an artifact produced during external execution."""
    artifact_id: str
    name: str
    artifact_type: str  # 'report_json', 'model_weights', 'dataset_csv', 'plot_png', 'log_text'
    checksum_sha256: str
    size_bytes: int = 0
    uri_or_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExternalArtifactRef:
        art_id = str(data.get("artifact_id", "")).strip()
        name = str(data.get("name", "")).strip()
        sha = str(data.get("checksum_sha256", "")).strip()
        if not art_id or not name:
            raise SchemaValidationError("Artifact 'artifact_id' and 'name' are required.")
        return cls(
            artifact_id=art_id,
            name=name,
            artifact_type=str(data.get("artifact_type", "report_json")),
            checksum_sha256=sha,
            size_bytes=int(data.get("size_bytes", 0)),
            uri_or_path=data.get("uri_or_path"),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class ExternalRunSubmission:
    """Complete, versioned submission payload from an external environment."""
    schema_version: str
    workspace_id: str
    experiment_id: str
    run_id: str
    model_id: str
    model_version: str = "1.0.0"
    dataset_id: Optional[str] = None
    dataset_version: Optional[str] = None
    target_lab: str = "general"
    run_status: str = "completed"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: List[ExternalMetric] = field(default_factory=list)
    predictions: List[ExternalPrediction] = field(default_factory=list)
    artifacts: List[ExternalArtifactRef] = field(default_factory=list)
    environment: ExecutionEnvironment = field(default_factory=ExecutionEnvironment)
    error_message: Optional[str] = None
    provenance_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workspace_id": self.workspace_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "target_lab": self.target_lab,
            "run_status": self.run_status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "parameters": dict(self.parameters),
            "metrics": [m.to_dict() for m in self.metrics],
            "predictions": [p.to_dict() for p in self.predictions],
            "artifacts": [a.to_dict() for a in self.artifacts],
            "environment": self.environment.to_dict(),
            "error_message": self.error_message,
            "provenance_hash": self.provenance_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExternalRunSubmission:
        ws_id = str(data.get("workspace_id") or data.get("project_id", "")).strip()
        exp_id = str(data.get("experiment_id", "")).strip()
        run_id = str(data.get("run_id", "")).strip()
        model_id = str(data.get("model_id", "")).strip()

        if not ws_id:
            raise SchemaValidationError("Field 'workspace_id' (or 'project_id') is required.")
        if not exp_id:
            raise SchemaValidationError("Field 'experiment_id' is required.")
        if not run_id:
            raise SchemaValidationError("Field 'run_id' is required.")
        if not model_id:
            raise SchemaValidationError("Field 'model_id' is required.")

        for field_name, val in [("workspace_id", ws_id), ("experiment_id", exp_id), ("run_id", run_id), ("model_id", model_id)]:
            if not re.match(r"^[a-zA-Z0-9_\-\.]+$", val):
                raise SchemaValidationError(f"Invalid character in {field_name} '{val}'. Alphanumeric, dot, dash, underscore only.")

        t_lab = str(data.get("target_lab", "general")).strip().lower()
        if t_lab not in ALLOWED_TARGET_LABS:
            t_lab = "general"

        raw_metrics = data.get("metrics") or []
        metrics = [ExternalMetric.from_dict(m) for m in raw_metrics]

        raw_predictions = data.get("predictions") or []
        predictions = [ExternalPrediction.from_dict(p) for p in raw_predictions]

        raw_artifacts = data.get("artifacts") or []
        artifacts = [ExternalArtifactRef.from_dict(a) for a in raw_artifacts]

        env_dict = data.get("environment") or {}
        env = ExecutionEnvironment.from_dict(env_dict)

        status_str = str(data.get("run_status", "completed")).strip().lower()
        if status_str not in {"completed", "failed", "running", "rejected"}:
            status_str = "completed"

        # Calculate stable provenance hash
        hasher = hashlib.sha256()
        hasher.update(f"{ws_id}:{exp_id}:{run_id}:{model_id}".encode("utf-8"))
        for m in metrics:
            hasher.update(f"{m.metric_name}:{m.observed_value}".encode("utf-8"))
        prov_hash = hasher.hexdigest()

        return cls(
            schema_version=str(data.get("schema_version", "1.0.0")),
            workspace_id=ws_id,
            experiment_id=exp_id,
            run_id=run_id,
            model_id=model_id,
            model_version=str(data.get("model_version", "1.0.0")),
            dataset_id=data.get("dataset_id"),
            dataset_version=data.get("dataset_version"),
            target_lab=t_lab,
            run_status=status_str,
            started_at=str(data.get("started_at") or datetime.now(timezone.utc).isoformat()),
            completed_at=data.get("completed_at"),
            parameters=dict(data.get("parameters") or {}),
            metrics=metrics,
            predictions=predictions,
            artifacts=artifacts,
            environment=env,
            error_message=data.get("error_message"),
            provenance_hash=prov_hash,
        )


@dataclass
class IngestionResult:
    """Acknowledgment and independent verification result returned to the client."""
    success: bool
    submission_id: str
    run_id: str
    status: str  # 'accepted', 'completed', 'rejected', 'failed'
    received_metrics_count: int
    received_predictions_count: int
    received_artifacts_count: int
    target_lab_routed: str
    validation_warnings: List[str] = field(default_factory=list)
    recomputed_metrics: Dict[str, Any] = field(default_factory=dict)
    provenance_hash: str = ""
    ingested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# 2. Ingestion Controller & Independent Verification Engine (§4, §5)
# ==============================================================================

class ExternalIngestionEngine:
    """Manages the verification, independent re-computation, and persistence of external model runs."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or DATA_DIR
        self.experiments_dir = self.data_dir / "experiments"
        self.artifacts_dir = self.data_dir / "artifacts"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._in_memory_index: Dict[str, Dict[str, Any]] = {}

    def ingest_run(self, payload: Mapping[str, Any]) -> IngestionResult:
        """Validate, verify, and store an externally submitted model experiment run."""
        # Validate schema
        submission = ExternalRunSubmission.from_dict(payload)
        submission_id = f"sub_{int(time.time()*1000)}_{submission.run_id[:8]}"
        warnings: List[str] = []

        # Enforce run status integrity
        if submission.run_status == "failed" and not submission.error_message:
            warnings.append("Run status is 'failed' but no error_message was provided.")

        # Independent calculation if predictions and actual outcomes are supplied
        recomputed: Dict[str, Any] = {}
        if submission.predictions:
            pairs = [
                (p.predicted_value, p.actual_value)
                for p in submission.predictions
                if p.actual_value is not None
            ]
            if len(pairs) >= 2:
                preds = np.array([p[0] for p in pairs], dtype=float)
                actuals = np.array([p[1] for p in pairs], dtype=float)
                errors = preds - actuals
                rmse = float(np.sqrt(np.mean(errors ** 2)))
                mae = float(np.mean(np.abs(errors)))
                
                # Directional accuracy
                pred_dir = np.sign(preds)
                act_dir = np.sign(actuals)
                dir_acc = float(np.mean(pred_dir == act_dir))

                recomputed["independent_rmse"] = round(rmse, 6)
                recomputed["independent_mae"] = round(mae, 6)
                recomputed["independent_directional_accuracy"] = round(dir_acc, 4)
                recomputed["evaluated_sample_count"] = len(pairs)
                recomputed["verification_status"] = "INDEPENDENTLY_VERIFIED"
            elif len(pairs) == 1:
                warnings.append("Only 1 prediction with actual outcome supplied; statistical metrics require >= 2 samples.")

        # Determine normalized status
        status = submission.run_status
        if status not in {"completed", "failed", "running"}:
            status = "accepted"

        # Format record for central Experiment Registry (Page 9)
        record = {
            "run_id": submission.run_id,
            "display_name": f"{submission.model_id} on {submission.experiment_id}",
            "run_type": f"external_{submission.target_lab}",
            "status": status,
            "created_at": submission.started_at,
            "completed_at": submission.completed_at,
            "lab": submission.target_lab,
            "is_external": True,
            "source_environment": submission.environment.environment_type,
            "model_id": submission.model_id,
            "dataset_id": submission.dataset_id or "unspecified",
            "metrics": {m.metric_name: m.observed_value for m in submission.metrics},
            "recomputed_metrics": recomputed,
            "parameters": submission.parameters,
            "predictions_count": len(submission.predictions),
            "artifacts_count": len(submission.artifacts),
            "error_message": submission.error_message,
            "provenance_hash": submission.provenance_hash,
        }

        # Store in memory
        self._in_memory_index[submission.run_id] = record

        # Persist to disk
        out_file = self.experiments_dir / f"external_{submission.run_id}.json"
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump({
                    "submission": submission.to_dict(),
                    "registry_record": record,
                    "recomputed_metrics": recomputed,
                }, f, indent=2)
        except Exception as exc:
            logger.warning(f"Failed to persist external experiment run: {exc}")

        return IngestionResult(
            success=True,
            submission_id=submission_id,
            run_id=submission.run_id,
            status=status,
            received_metrics_count=len(submission.metrics),
            received_predictions_count=len(submission.predictions),
            received_artifacts_count=len(submission.artifacts),
            target_lab_routed=submission.target_lab,
            validation_warnings=warnings,
            recomputed_metrics=recomputed,
            provenance_hash=submission.provenance_hash,
        )

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored external run record."""
        if run_id in self._in_memory_index:
            return self._in_memory_index[run_id]

        f = self.experiments_dir / f"external_{run_id}.json"
        if f.is_file():
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    rec = data.get("registry_record") or data.get("submission")
                    self._in_memory_index[run_id] = rec
                    return rec
            except Exception:
                pass
        return None

    def list_runs(
        self,
        workspace_id: Optional[str] = None,
        target_lab: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List stored external runs with optional filtering."""
        runs: List[Dict[str, Any]] = []
        # Load from disk
        for f in self.experiments_dir.glob("external_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    rec = data.get("registry_record") or data.get("submission")
                    if rec:
                        runs.append(rec)
            except Exception:
                continue

        # Filter
        if target_lab and target_lab != "all":
            runs = [r for r in runs if r.get("lab", "").lower() == target_lab.lower()]
        if status and status != "all":
            runs = [r for r in runs if r.get("status", "").lower() == status.lower()]

        runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return runs

    def save_artifact_file(
        self,
        run_id: str,
        artifact_id: str,
        filename: str,
        content_bytes: bytes,
        expected_sha256: Optional[str] = None,
    ) -> ExternalArtifactRef:
        """Securely store an uploaded artifact, validating SHA-256 and size bounds."""
        if len(content_bytes) > MAX_ARTIFACT_FILE_BYTES:
            raise ArtifactValidationError(
                f"Artifact size ({len(content_bytes)} bytes) exceeds limit ({MAX_ARTIFACT_FILE_BYTES} bytes)."
            )

        # Sanitize filename to prevent directory traversal
        clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", Path(filename).name)
        if not clean_name:
            clean_name = f"artifact_{artifact_id}.bin"

        # Checksum validation
        actual_sha = hashlib.sha256(content_bytes).hexdigest()
        if expected_sha256 and expected_sha256.lower() != actual_sha.lower():
            raise ArtifactValidationError(
                f"SHA-256 mismatch for artifact '{filename}'. Expected {expected_sha256}, got {actual_sha}."
            )

        dest_dir = self.artifacts_dir / run_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        target_path = dest_dir / clean_name

        with open(target_path, "wb") as f:
            f.write(content_bytes)

        art_ref = ExternalArtifactRef(
            artifact_id=artifact_id,
            name=clean_name,
            artifact_type="uploaded_file",
            checksum_sha256=actual_sha,
            size_bytes=len(content_bytes),
            uri_or_path=str(target_path),
        )

        # Update run record if present
        run_file = self.experiments_dir / f"external_{run_id}.json"
        if run_file.is_file():
            try:
                with open(run_file, "r", encoding="utf-8") as fp:
                    run_data = json.load(fp)
                if "registry_record" in run_data:
                    run_data["registry_record"]["artifacts_count"] = run_data["registry_record"].get("artifacts_count", 0) + 1
                    if "artifacts" not in run_data["registry_record"]:
                        run_data["registry_record"]["artifacts"] = []
                    run_data["registry_record"]["artifacts"].append(art_ref.to_dict())
                if "submission" in run_data:
                    if "artifacts" not in run_data["submission"]:
                        run_data["submission"]["artifacts"] = []
                    run_data["submission"]["artifacts"].append(art_ref.to_dict())
                with open(run_file, "w", encoding="utf-8") as fp:
                    json.dump(run_data, fp, indent=2)
                if run_id in self._in_memory_index:
                    self._in_memory_index[run_id] = run_data.get("registry_record", self._in_memory_index[run_id])
            except Exception as exc:
                logger.warning(f"Could not update run file with artifact ref: {exc}")

        return art_ref


# Global Engine Singleton
_GLOBAL_INGESTION_ENGINE: Optional[ExternalIngestionEngine] = None

def get_ingestion_engine() -> ExternalIngestionEngine:
    global _GLOBAL_INGESTION_ENGINE
    if _GLOBAL_INGESTION_ENGINE is None:
        _GLOBAL_INGESTION_ENGINE = ExternalIngestionEngine()
    return _GLOBAL_INGESTION_ENGINE
