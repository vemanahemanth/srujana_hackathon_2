"""FragilityShield — Experiment Studio & Reports (Phase 7).

This module provides a unified orchestration, reporting, and cataloging workflow
for financial fragility and quantitative model stress experiments.

Core Capabilities:
1. Studio Experiment Definition (`StudioExperimentDefinition`):
   - Structured, validated experiment configuration extending Phase 6 specifications.
2. Experiment Execution Workflow (`execute_studio_experiment`):
   - Validates data and parameters.
   - Executes baseline risk and fragility perturbations with graceful partial-failure handling.
   - Runs sensitivity rankings and mathematical invariant checks.
   - Assigns explicit status ('completed', 'completed_with_warnings', 'failed_validation', 'failed_execution').
3. Structured Experiment Report (`ExperimentReport`):
   - Machine-readable, versioned schema with deterministic serialization.
   - Multi-format export: JSON, human-readable Markdown tables with unit awareness, and tabular CSV.
4. Multi-Experiment Comparison (`compare_experiment_reports`, `StudioComparisonReport`):
   - Itemized delta comparison across baselines, perturbations, sensitivity rankings, and fingerprints.
   - Identifies non-comparable runs due to dataset or methodology divergence.
5. Local Experiment Catalog (`LocalExperimentCatalog`):
   - Safe local file-system storage with path-traversal prevention.
   - Indexing, filtering, lookup, and explicit overwrite safeguards.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np

import fragility_engine
from fragility_engine.fragility import (
    FragilityExperimentResult,
    MetricSensitivityRanking,
    rank_perturbation_sensitivities,
)
from fragility_engine.models import Holding, Portfolio
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
# B2. Studio Experiment Definition
# ==============================================================================

VALID_STATUSES = {"completed", "completed_with_warnings", "failed_validation", "failed_execution"}


@dataclass(frozen=True)
class StudioExperimentDefinition:
    """Validated, high-level experiment configuration for the Experiment Studio.

    Attributes:
        experiment_id: Unique string identifier (must be safe for filenames).
        name: Human-readable experiment title.
        description: Methodological explanation and narrative context.
        dataset_id: Identifier of the input dataset or portfolio snapshot.
        baseline_config: Calculation parameters (e.g. annualization_factor, confidence_level).
        perturbation_specs: Sequence of perturbation configurations to evaluate.
        selected_metrics: Optional subset of risk metrics to focus on.
        target_ranking_metric: Optional target metric name to rank sensitivities against.
        schema_version: Specification schema version (defaults to "1.0.0").
        algorithm_version: Software algorithm version (defaults to "1.0.0").
        random_seed: Optional deterministic integer seed for stochastic models.
        date_range: Optional tuple or mapping of (start_date, end_date).
        tags: Categorization tags for catalog indexing.
        metadata: Informational metadata dictionary.
        dataset_provenance: Data source and integrity metadata.
        baseline_comparison_id: Optional ID of a previous experiment to compare against.
    """

    experiment_id: str
    name: str = "Studio Quantitative Experiment"
    description: str = ""
    dataset_id: str = "DEFAULT_DATASET"
    baseline_config: Mapping[str, Any] = field(default_factory=dict)
    perturbation_specs: Sequence[Mapping[str, Any]] = field(default_factory=list)
    selected_metrics: Sequence[str] = field(default_factory=list)
    target_ranking_metric: Optional[str] = None
    schema_version: str = "1.0.0"
    algorithm_version: str = "1.0.0"
    random_seed: Optional[int] = None
    date_range: Optional[Union[Tuple[str, str], Mapping[str, str]]] = None
    tags: Sequence[str] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    dataset_provenance: Optional[Mapping[str, Any]] = None
    baseline_comparison_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate specification integrity and security."""
        if not isinstance(self.experiment_id, str) or not self.experiment_id.strip():
            raise ValueError("experiment_id cannot be blank")

        # Security check: validate experiment_id does not contain path traversal characters
        if re.search(r"[\/\\:\0]", self.experiment_id) or ".." in self.experiment_id:
            raise ValueError(
                f"experiment_id '{self.experiment_id}' contains unsafe path traversal characters"
            )

        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")

        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be a non-empty string")

        if not isinstance(self.baseline_config, (dict, Mapping)):
            raise TypeError("baseline_config must be a mapping dictionary")

        if not isinstance(self.perturbation_specs, (list, tuple)):
            raise TypeError("perturbation_specs must be a sequence of mappings")

        if "confidence_level" in self.baseline_config:
            try:
                conf = float(self.baseline_config["confidence_level"])
            except (TypeError, ValueError) as exc:
                raise ValueError("confidence_level must be a numeric float") from exc
            if not (0.0 < conf < 1.0):
                raise ValueError(f"confidence_level must be in (0, 1); got {conf}")

        if self.random_seed is not None and not isinstance(self.random_seed, int):
            raise TypeError(f"random_seed must be an integer or None; got {type(self.random_seed).__name__}")

    def to_spec(self) -> ExperimentSpecification:
        """Convert definition into a Phase 6 ExperimentSpecification."""
        return ExperimentSpecification(
            experiment_id=self.experiment_id,
            name=self.name,
            description=self.description,
            dataset_id=self.dataset_id,
            baseline_config=dict(self.baseline_config),
            perturbation_specs=list(self.perturbation_specs),
            schema_version=self.schema_version,
            algorithm_version=self.algorithm_version,
            random_seed=self.random_seed,
            date_range=self.date_range,
            metadata=dict(self.metadata),
            dataset_provenance=dict(self.dataset_provenance) if self.dataset_provenance else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert definition to a serializable dictionary."""
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
            "dataset_id": self.dataset_id,
            "baseline_config": dict(self.baseline_config),
            "perturbation_specs": [dict(p) for p in self.perturbation_specs],
            "selected_metrics": list(self.selected_metrics),
            "target_ranking_metric": self.target_ranking_metric,
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "random_seed": self.random_seed,
            "date_range": dr,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "dataset_provenance": dict(self.dataset_provenance) if self.dataset_provenance else None,
            "baseline_comparison_id": self.baseline_comparison_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StudioExperimentDefinition:
        """Instantiate StudioExperimentDefinition from a dictionary."""
        return cls(
            experiment_id=str(data["experiment_id"]),
            name=str(data.get("name", "Studio Quantitative Experiment")),
            description=str(data.get("description", "")),
            dataset_id=str(data.get("dataset_id", "DEFAULT_DATASET")),
            baseline_config=dict(data.get("baseline_config", {})),
            perturbation_specs=list(data.get("perturbation_specs", [])),
            selected_metrics=list(data.get("selected_metrics", [])),
            target_ranking_metric=data.get("target_ranking_metric"),
            schema_version=str(data.get("schema_version", "1.0.0")),
            algorithm_version=str(data.get("algorithm_version", "1.0.0")),
            random_seed=data.get("random_seed"),
            date_range=data.get("date_range"),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
            dataset_provenance=dict(data.get("dataset_provenance", {})) if data.get("dataset_provenance") else None,
            baseline_comparison_id=data.get("baseline_comparison_id"),
        )


# ==============================================================================
# B5. Structured Experiment Report
# ==============================================================================

@dataclass(frozen=True)
class ExperimentReport:
    """Self-contained, structured report of an executed studio experiment.

    Attributes:
        report_id: Unique identifier for this report artifact.
        experiment_id: Identifier of the executed experiment.
        name: Experiment title.
        status: Execution status ('completed', 'completed_with_warnings', 'failed_validation', 'failed_execution').
        schema_version: Report schema version string (e.g. "1.0.0").
        created_at: ISO 8601 UTC execution timestamp.
        dataset_id: Identifier of the input dataset.
        date_range: Optional date range mapping.
        input_fingerprint: SHA-256 hash of the input dataset.
        configuration_fingerprint: SHA-256 hash of the mathematical configuration.
        output_fingerprint: SHA-256 hash of outputs and validation status.
        baseline_assumptions: Dictionary of baseline configuration parameters.
        baseline_metrics: Computed baseline risk and valuation metrics.
        perturbation_results: List of executed perturbation summaries and deltas.
        sensitivity_rankings: List of ranked perturbation sensitivities.
        manifest: Complete reproducibility manifest dictionary.
        validation_report: Mathematical invariant verification summary.
        warnings: List of execution or methodology caveats.
        limitations: List of known architectural or mathematical boundaries.
        tags: Categorization tags.
    """

    report_id: str
    experiment_id: str
    name: str
    status: str
    schema_version: str
    created_at: str
    dataset_id: str
    date_range: Optional[Mapping[str, str]]
    input_fingerprint: str
    configuration_fingerprint: str
    output_fingerprint: str
    baseline_assumptions: Mapping[str, Any]
    baseline_metrics: Mapping[str, float]
    perturbation_results: Sequence[Mapping[str, Any]]
    sensitivity_rankings: Sequence[Mapping[str, Any]]
    manifest: Mapping[str, Any]
    validation_report: Mapping[str, Any]
    warnings: Sequence[str]
    limitations: Sequence[str]
    tags: Sequence[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to serializable dictionary."""
        return {
            "report_id": self.report_id,
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "dataset_id": self.dataset_id,
            "date_range": dict(self.date_range) if self.date_range else None,
            "input_fingerprint": self.input_fingerprint,
            "configuration_fingerprint": self.configuration_fingerprint,
            "output_fingerprint": self.output_fingerprint,
            "baseline_assumptions": dict(self.baseline_assumptions),
            "baseline_metrics": dict(self.baseline_metrics),
            "perturbation_results": [dict(p) for p in self.perturbation_results],
            "sensitivity_rankings": [dict(r) for r in self.sensitivity_rankings],
            "manifest": dict(self.manifest),
            "validation_report": dict(self.validation_report),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "tags": list(self.tags),
        }

    def to_json(self, indent: int = 2) -> str:
        """Export report as formatted JSON string with deterministic key ordering."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentReport:
        """Instantiate ExperimentReport from dictionary."""
        return cls(
            report_id=str(data["report_id"]),
            experiment_id=str(data["experiment_id"]),
            name=str(data.get("name", "Studio Quantitative Experiment")),
            status=str(data.get("status", "completed")),
            schema_version=str(data.get("schema_version", "1.0.0")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            dataset_id=str(data.get("dataset_id", "DEFAULT_DATASET")),
            date_range=dict(data.get("date_range", {})) if data.get("date_range") else None,
            input_fingerprint=str(data.get("input_fingerprint", "")),
            configuration_fingerprint=str(data.get("configuration_fingerprint", "")),
            output_fingerprint=str(data.get("output_fingerprint", "")),
            baseline_assumptions=dict(data.get("baseline_assumptions", {})),
            baseline_metrics=dict(data.get("baseline_metrics", {})),
            perturbation_results=list(data.get("perturbation_results", [])),
            sensitivity_rankings=list(data.get("sensitivity_rankings", [])),
            manifest=dict(data.get("manifest", {})),
            validation_report=dict(data.get("validation_report", {})),
            warnings=list(data.get("warnings", [])),
            limitations=list(data.get("limitations", [])),
            tags=list(data.get("tags", [])),
        )

    @classmethod
    def from_json(cls, json_str: str) -> ExperimentReport:
        """Instantiate ExperimentReport from JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ==========================================================================
    # B6. Report Export Formats: Markdown & CSV
    # ==========================================================================

    def to_markdown(self) -> str:
        """Generate human-readable, publication-grade Markdown report."""
        lines = [
            f"# FragilityShield — Experiment Report: {self.name}",
            "",
            f"**Experiment ID:** `{self.experiment_id}`  ",
            f"**Report ID:** `{self.report_id}`  ",
            f"**Status:** `{self.status.upper()}`  ",
            f"**Dataset ID:** `{self.dataset_id}`  ",
            f"**Generated At:** `{self.created_at}`  ",
            f"**Schema Version:** `{self.schema_version}`  ",
            "",
            "---",
            "",
            "## 1. Cryptographic Fingerprints & Provenance",
            "",
            "| Fingerprint Type | SHA-256 Digest |",
            "| :--- | :--- |",
            f"| **Input Data Fingerprint** | `{self.input_fingerprint}` |",
            f"| **Configuration Fingerprint** | `{self.configuration_fingerprint}` |",
            f"| **Output Results Fingerprint** | `{self.output_fingerprint}` |",
            "",
            "---",
            "",
            "## 2. Baseline Assumptions & Risk Metrics",
            "",
            "### Baseline Risk Metrics",
            "",
            "| Metric | Value | Standard Unit |",
            "| :--- | :--- | :--- |",
        ]

        for k, v in sorted(self.baseline_metrics.items()):
            unit = _format_metric_unit(k)
            val_str = _format_metric_value(k, v)
            lines.append(f"| `{k}` | **{val_str}** | {unit} |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Perturbation Results & Impact",
            "",
            "| Perturbation ID | Perturbation Name | Metric | Baseline | Stressed | Absolute Delta | Relative Delta |",
            "| :--- | :--- | :--- | :---: | :---: | :---: | :---: |",
        ])

        if not self.perturbation_results:
            lines.append("| *None* | No perturbations executed | - | - | - | - | - |")
        else:
            for p in self.perturbation_results:
                pid = p.get("experiment_id") or p.get("perturbation_id", "-")
                pname = p.get("perturbation_name", "-")
                for m_key, m_val in p.get("perturbed_metrics", {}).items():
                    b_val = p.get("baseline_metrics", {}).get(m_key, self.baseline_metrics.get(m_key))
                    abs_d = p.get("absolute_changes", {}).get(m_key)
                    rel_d = p.get("relative_changes", {}).get(m_key)

                    b_str = _format_metric_value(m_key, b_val) if b_val is not None else "-"
                    s_str = _format_metric_value(m_key, m_val) if m_val is not None else "-"
                    abs_str = f"{abs_d:+.6f}" if abs_d is not None else "-"
                    rel_str = f"{rel_d:+.2%}" if rel_d is not None else "-"

                    lines.append(f"| `{pid}` | {pname} | `{m_key}` | {b_str} | {s_str} | {abs_str} | {rel_str} |")

        lines.extend([
            "",
            "---",
            "",
            "## 4. Sensitivity Rankings",
            "",
            "| Rank | Perturbation ID | Metric | Absolute Impact | Relative Impact | Vulnerability Assessment |",
            "| :---: | :--- | :--- | :---: | :---: | :--- |",
        ])

        if not self.sensitivity_rankings:
            lines.append("| - | *No rankings computed* | - | - | - | - |")
        else:
            for r in self.sensitivity_rankings:
                rank = r.get("rank", "-")
                pid = r.get("perturbation_id", "-")
                mname = r.get("metric_name", "-")
                abs_i = r.get("absolute_impact", 0.0)
                rel_i = r.get("relative_impact")
                rel_str = f"{rel_i:+.2%}" if rel_i is not None else "-"
                diag = r.get("diagnostic_summary", "Ranked impact")
                lines.append(f"| {rank} | `{pid}` | `{mname}` | {abs_i:.6f} | {rel_str} | {diag} |")

        lines.extend([
            "",
            "---",
            "",
            "## 5. Independent Validation & Limitations",
            "",
            f"- **Validation Status:** `{self.validation_report.get('all_passed', False)}` "
            f"({self.validation_report.get('checks_passed', 0)}/{self.validation_report.get('checks_total', 0)} checks passed)",
        ])

        if self.warnings:
            lines.append("\n### Warnings")
            for w in self.warnings:
                lines.append(f"- [WARNING] {w}")

        if self.limitations:
            lines.append("\n### Methodological Limitations")
            for lim in self.limitations:
                lines.append(f"- [LIMITATION] {lim}")

        return "\n".join(lines) + "\n"

    def to_csv(self) -> str:
        """Export tabular perturbation metrics as a clean, standardized CSV."""
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        writer.writerow([
            "experiment_id",
            "report_id",
            "status",
            "dataset_id",
            "perturbation_id",
            "perturbation_name",
            "metric_name",
            "baseline_value",
            "stressed_value",
            "absolute_delta",
            "relative_delta",
            "unit",
        ])

        for p in self.perturbation_results:
            pid = p.get("experiment_id") or p.get("perturbation_id", "")
            pname = p.get("perturbation_name", "")
            for m_key, m_val in p.get("perturbed_metrics", {}).items():
                b_val = p.get("baseline_metrics", {}).get(m_key, self.baseline_metrics.get(m_key))
                abs_d = p.get("absolute_changes", {}).get(m_key)
                rel_d = p.get("relative_changes", {}).get(m_key)
                unit = _format_metric_unit(m_key)

                writer.writerow([
                    self.experiment_id,
                    self.report_id,
                    self.status,
                    self.dataset_id,
                    pid,
                    pname,
                    m_key,
                    b_val if b_val is not None else "",
                    m_val if m_val is not None else "",
                    abs_d if abs_d is not None else "",
                    rel_d if rel_d is not None else "",
                    unit,
                ])

        return output.getvalue()


def _format_metric_unit(metric_name: str) -> str:
    """Helper to associate metric names with unambiguous units."""
    m = metric_name.lower()
    if "hhi_points" in m:
        return "points (0-10000)"
    if "value" in m or "cost" in m or "pnl" in m:
        return "currency"
    if "drawdown" in m or "hhi_decimal" in m or "volatility" in m or "var" in m or "shortfall" in m or "drag" in m:
        return "decimal fraction"
    return "ratio"


def _format_metric_value(metric_name: str, val: Optional[float]) -> str:
    """Helper to format numerical metric value for Markdown readability."""
    if val is None or not math.isfinite(val):
        return "-"
    m = metric_name.lower()
    if "hhi_points" in m:
        return f"{val:.1f} pts"
    if "value" in m or "cost" in m:
        return f"{val:,.2f}"
    if "volatility" in m or "drawdown" in m or "var" in m or "shortfall" in m:
        return f"{val:.6f} ({val:.2%})"
    return f"{val:.6f}"


# ==============================================================================
# B3. Experiment Studio Execution Workflow
# ==============================================================================

def execute_studio_experiment(
    definition: StudioExperimentDefinition,
    dataset: Optional[Sequence[float] | np.ndarray | Portfolio] = None,
    return_series: Optional[Sequence[float] | np.ndarray] = None,
    portfolio: Optional[Portfolio] = None,
    continue_on_perturbation_error: bool = True,
) -> ExperimentReport:
    """Execute complete Experiment Studio workflow.

    Workflow:
    1. Validates experiment definition and input dataset.
    2. Runs reproducible baseline risk/valuation calculations.
    3. Executes configured fragility perturbations with optional error isolation.
    4. Performs independent mathematical invariant checks.
    5. Computes sensitivity rankings if target metric is defined.
    6. Produces structured, immutable ExperimentReport artifact.

    Args:
        definition: Validated StudioExperimentDefinition.
        dataset: Input return series or Portfolio instance.
        return_series: Optional explicit return series input.
        portfolio: Optional explicit Portfolio input.
        continue_on_perturbation_error: If True, perturbation errors are recorded
            gracefully rather than aborting the entire experiment.

    Returns:
        Structured ExperimentReport.
    """
    if not isinstance(definition, StudioExperimentDefinition):
        raise TypeError(f"definition must be a StudioExperimentDefinition; got {type(definition).__name__}")

    # Resolve dataset input
    if dataset is None:
        if portfolio is not None and return_series is None:
            dataset = portfolio
        elif return_series is not None:
            dataset = return_series
        else:
            raise ValueError("dataset or return_series must be provided")

    # Validate dataset finiteness
    if isinstance(dataset, (list, tuple, np.ndarray)) and len(dataset) == 0:
        raise ValueError("Dataset cannot be empty")

    if not isinstance(dataset, Portfolio):
        arr_check = np.asarray(dataset)
        if arr_check.size == 0:
            raise ValueError("Dataset cannot be empty")
        if not np.all(np.isfinite(arr_check)):
            raise ValueError("Dataset contains non-finite numbers (NaN or Inf)")

    warnings: List[str] = []
    limitations: List[str] = [
        "Historical risk estimators assume stationarity and do not forecast regime transitions.",
        "Constant return drag models sensitivity, not dynamic trade execution logs.",
    ]

    status = "completed"
    now_utc = datetime.now(timezone.utc).isoformat()
    report_id = f"REP-{definition.experiment_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    # Build underlying Phase 6 ExperimentSpecification
    spec = definition.to_spec()

    try:
        run_res = run_reproducible_experiment(
            spec=spec,
            dataset=dataset,
        )
        baseline_metrics = dict(run_res.baseline_metrics)
        pert_results = list(run_res.perturbation_results)
        manifest_dict = run_res.manifest.to_dict()
        invariant_dict = run_res.invariant_report.to_dict()

        if not run_res.invariant_report.all_passed:
            status = "failed_validation"
            warnings.extend(run_res.invariant_report.failure_messages)
        elif len(run_res.manifest.warnings) > 0:
            status = "completed_with_warnings"
            warnings.extend(run_res.manifest.warnings)

    except Exception as exc:
        if not continue_on_perturbation_error:
            raise
        status = "failed_execution"
        warnings.append(f"Experiment execution encountered failure: {exc}")
        baseline_metrics = {}
        pert_results = []
        manifest_dict = {
            "experiment_id": definition.experiment_id,
            "status": "failed_execution",
            "error": str(exc),
        }
        invariant_dict = {
            "all_passed": False,
            "checks_passed": 0,
            "checks_total": 0,
            "failure_messages": [str(exc)],
        }

    # Compute sensitivity rankings if perturbations and target metric exist
    rankings: List[Dict[str, Any]] = []
    if pert_results and definition.target_ranking_metric:
        target_metric = definition.target_ranking_metric
        sample_metrics = pert_results[0].baseline_metrics if hasattr(pert_results[0], "baseline_metrics") else {}
        if target_metric not in sample_metrics:
            alias_map = {
                "var_historical": "var_95",
                "annualized_volatility": "volatility_annualized",
                "maximum_drawdown": "max_drawdown",
                "expected_shortfall": "expected_shortfall_95",
            }
            if target_metric in alias_map and alias_map[target_metric] in sample_metrics:
                target_metric = alias_map[target_metric]

        try:
            ranking_obj = rank_perturbation_sensitivities(
                experiments=pert_results,
                target_metric=target_metric,
            )
            for idx, imp in enumerate(ranking_obj.ranked_impacts, start=1):
                d = imp.to_dict()
                d["rank"] = idx
                d["metric_name"] = definition.target_ranking_metric
                d["absolute_impact"] = abs(imp.absolute_change)
                d["relative_impact"] = imp.relative_change
                d["diagnostic_summary"] = (
                    f"Perturbation {imp.perturbation_id} shifts {ranking_obj.metric_id} by "
                    f"{imp.absolute_change:+.6f}"
                )
                rankings.append(d)
        except Exception as rank_err:
            warnings.append(f"Sensitivity ranking skipped: {rank_err}")

    input_fp = compute_dataset_hash(dataset)
    config_fp = spec.compute_config_hash()
    output_fp = manifest_dict.get("output_fingerprint", compute_canonical_hash(baseline_metrics))

    return ExperimentReport(
        report_id=report_id,
        experiment_id=definition.experiment_id,
        name=definition.name,
        status=status,
        schema_version=definition.schema_version,
        created_at=now_utc,
        dataset_id=definition.dataset_id,
        date_range=dict(definition.date_range) if isinstance(definition.date_range, Mapping) else None,
        input_fingerprint=input_fp,
        configuration_fingerprint=config_fp,
        output_fingerprint=output_fp,
        baseline_assumptions=dict(definition.baseline_config),
        baseline_metrics=baseline_metrics,
        perturbation_results=[p.to_dict() if hasattr(p, "to_dict") else dict(p) for p in pert_results],
        sensitivity_rankings=rankings,
        manifest=manifest_dict,
        validation_report=invariant_dict,
        warnings=warnings,
        limitations=limitations,
        tags=list(definition.tags),
    )


# ==============================================================================
# B4. Multi-Experiment Comparison
# ==============================================================================

@dataclass(frozen=True)
class StudioComparisonReport:
    """Comparative evaluation across two ExperimentReport artifacts.

    Attributes:
        comparable: True if experiments share identical dataset and methodology conventions.
        report_a_id: ID of first report.
        report_b_id: ID of second report.
        input_data_identical: True if input datasets have identical SHA-256 hashes.
        configuration_identical: True if experiment configurations have identical SHA-256 hashes.
        baseline_metric_diffs: Dictionary of baseline metric differences (val_a, val_b, diff).
        perturbation_metric_diffs: Dictionary of perturbation metric comparisons.
        sensitivity_rank_diffs: Comparison of ranking orders.
        non_comparable_reasons: Sequence of reasons why runs cannot be compared apples-to-apples.
        summary: Diagnostic human-readable summary.
    """

    comparable: bool
    report_a_id: str
    report_b_id: str
    input_data_identical: bool
    configuration_identical: bool
    baseline_metric_diffs: Mapping[str, Dict[str, Any]]
    perturbation_metric_diffs: Mapping[str, Dict[str, Any]]
    sensitivity_rank_diffs: Sequence[Dict[str, Any]]
    non_comparable_reasons: Sequence[str]
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparable": self.comparable,
            "report_a_id": self.report_a_id,
            "report_b_id": self.report_b_id,
            "input_data_identical": self.input_data_identical,
            "configuration_identical": self.configuration_identical,
            "baseline_metric_diffs": dict(self.baseline_metric_diffs),
            "perturbation_metric_diffs": dict(self.perturbation_metric_diffs),
            "sensitivity_rank_diffs": list(self.sensitivity_rank_diffs),
            "non_comparable_reasons": list(self.non_comparable_reasons),
            "summary": self.summary,
        }


def compare_experiment_reports(
    report_a: ExperimentReport,
    report_b: ExperimentReport,
    tolerance: float = 1e-6,
) -> StudioComparisonReport:
    """Compare two experiment reports, itemizing metric shifts and checking compatibility."""
    if not isinstance(report_a, ExperimentReport) or not isinstance(report_b, ExperimentReport):
        raise TypeError("Both report_a and report_b must be ExperimentReport instances")

    non_comparable_reasons: List[str] = []

    if report_a.dataset_id != report_b.dataset_id:
        non_comparable_reasons.append(
            f"Different dataset IDs: '{report_a.dataset_id}' vs '{report_b.dataset_id}'"
        )

    if report_a.input_fingerprint != report_b.input_fingerprint:
        non_comparable_reasons.append(
            "Input data hashes differ (underlying return series or holdings are not identical)"
        )

    comparable = len(non_comparable_reasons) == 0
    input_identical = report_a.input_fingerprint == report_b.input_fingerprint
    config_identical = report_a.configuration_fingerprint == report_b.configuration_fingerprint

    # Baseline metric differences
    base_diffs: Dict[str, Dict[str, Any]] = {}
    all_base_keys = sorted(set(report_a.baseline_metrics.keys()).union(report_b.baseline_metrics.keys()))

    for k in all_base_keys:
        val_a = report_a.baseline_metrics.get(k)
        val_b = report_b.baseline_metrics.get(k)
        if val_a is None or val_b is None:
            base_diffs[k] = {"val_a": val_a, "val_b": val_b, "diff": None, "status": "MISSING_IN_ONE_REPORT"}
        else:
            diff = abs(val_b - val_a)
            base_diffs[k] = {
                "val_a": val_a,
                "val_b": val_b,
                "diff": diff,
                "tolerance_exceeded": diff > tolerance,
                "status": "DIVERGENT" if diff > tolerance else "MATCHING",
            }

    # Perturbation differences
    pert_diffs: Dict[str, Dict[str, Any]] = {}
    perts_a = {p.get("experiment_id") or p.get("perturbation_id"): p for p in report_a.perturbation_results}
    perts_b = {p.get("experiment_id") or p.get("perturbation_id"): p for p in report_b.perturbation_results}
    all_pert_keys = sorted(set(perts_a.keys()).union(perts_b.keys()))

    for pk in all_pert_keys:
        p_a = perts_a.get(pk)
        p_b = perts_b.get(pk)
        if p_a is None or p_b is None:
            pert_diffs[pk] = {"status": "MISSING_IN_ONE_REPORT"}
        else:
            # Compare perturbed metrics
            p_metrics_a = p_a.get("perturbed_metrics", {})
            p_metrics_b = p_b.get("perturbed_metrics", {})
            m_diffs: Dict[str, Any] = {}
            for mk in sorted(set(p_metrics_a.keys()).union(p_metrics_b.keys())):
                va = p_metrics_a.get(mk)
                vb = p_metrics_b.get(mk)
                if va is not None and vb is not None:
                    m_diffs[mk] = {"val_a": va, "val_b": vb, "diff": abs(vb - va)}
                else:
                    m_diffs[mk] = {"val_a": va, "val_b": vb, "status": "MISSING"}
            pert_diffs[pk] = {"status": "COMPARED", "metrics": m_diffs}

    # Sensitivity ranking differences
    rank_diffs: List[Dict[str, Any]] = []
    ranks_a = {r.get("perturbation_id"): r.get("rank") for r in report_a.sensitivity_rankings}
    ranks_b = {r.get("perturbation_id"): r.get("rank") for r in report_b.sensitivity_rankings}

    for pid in sorted(set(ranks_a.keys()).union(ranks_b.keys())):
        ra = ranks_a.get(pid)
        rb = ranks_b.get(pid)
        rank_diffs.append({"perturbation_id": pid, "rank_a": ra, "rank_b": rb, "rank_changed": ra != rb})

    if not comparable:
        summary = f"Reports are not directly comparable: {'; '.join(non_comparable_reasons)}."
    elif input_identical and config_identical:
        summary = "Reports share identical inputs and configurations. Calculations are verified equivalent."
    else:
        summary = "Reports evaluated on identical dataset with differing perturbation configurations."

    return StudioComparisonReport(
        comparable=comparable,
        report_a_id=report_a.report_id,
        report_b_id=report_b.report_id,
        input_data_identical=input_identical,
        configuration_identical=config_identical,
        baseline_metric_diffs=base_diffs,
        perturbation_metric_diffs=pert_diffs,
        sensitivity_rank_diffs=rank_diffs,
        non_comparable_reasons=non_comparable_reasons,
        summary=summary,
    )


# ==============================================================================
# B7. Local Experiment Catalog
# ==============================================================================

class LocalExperimentCatalog:
    """Safe, file-based catalog for storing and querying completed experiment reports.

    Attributes:
        catalog_dir: Path to directory where experiment report JSON files are stored.
    """

    def __init__(self, catalog_dir: Union[str, Path]) -> None:
        self.catalog_dir = Path(catalog_dir).resolve()
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_id(self, experiment_id: str) -> str:
        """Sanitize and validate experiment_id against path traversal attacks."""
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ValueError("experiment_id cannot be blank")

        if ".." in experiment_id or "/" in experiment_id or "\\" in experiment_id or "\0" in experiment_id:
            raise ValueError(f"Unsafe identifier: '{experiment_id}' contains invalid path characters")

        cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", experiment_id)
        if not cleaned:
            raise ValueError(f"Invalid identifier '{experiment_id}' produces empty safe name")
        return cleaned

    def _get_report_path(self, experiment_id: str) -> Path:
        """Resolve safe filepath for an experiment report."""
        safe_id = self._sanitize_id(experiment_id)
        return self.catalog_dir / f"{safe_id}.json"

    def save_report(self, report: ExperimentReport, overwrite: bool = False) -> Path:
        """Store an ExperimentReport to local catalog storage.

        Args:
            report: The ExperimentReport instance to persist.
            overwrite: If False, raises FileExistsError if report file exists.

        Returns:
            Resolved Path of the saved report JSON file.
        """
        if not isinstance(report, ExperimentReport):
            raise TypeError(f"report must be an ExperimentReport; got {type(report).__name__}")

        dest_path = self._get_report_path(report.experiment_id)

        if dest_path.exists() and not overwrite:
            raise FileExistsError(
                f"Report for experiment '{report.experiment_id}' already exists at {dest_path}. "
                "Specify overwrite=True to overwrite existing report."
            )

        json_content = report.to_json(indent=2)
        dest_path.write_text(json_content, encoding="utf-8")
        return dest_path

    def get_report(self, experiment_id: str) -> ExperimentReport:
        """Retrieve and parse a saved ExperimentReport by experiment_id.

        Args:
            experiment_id: Identifier of the experiment to retrieve.

        Returns:
            Loaded ExperimentReport instance.
        """
        report_path = self._get_report_path(experiment_id)
        if not report_path.exists():
            raise FileNotFoundError(f"No catalog report found for experiment_id '{experiment_id}' at {report_path}")

        try:
            content = report_path.read_text(encoding="utf-8")
            return ExperimentReport.from_json(content)
        except Exception as exc:
            raise ValueError(f"Corrupted catalog file for experiment '{experiment_id}': {exc}") from exc

    def list_reports(
        self,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List summary metadata for all valid saved reports in the catalog.

        Args:
            status: Optional filter by status ('completed', 'completed_with_warnings', etc.).
            tag: Optional filter by tag string.
            dataset_id: Optional filter by dataset_id.

        Returns:
            List of summary dictionary entries.
        """
        entries: List[Dict[str, Any]] = []

        for p in sorted(self.catalog_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                exp_status = data.get("status", "unknown")
                exp_tags = data.get("tags", [])
                exp_dataset = data.get("dataset_id", "")

                if status is not None and exp_status != status:
                    continue
                if tag is not None and tag not in exp_tags:
                    continue
                if dataset_id is not None and exp_dataset != dataset_id:
                    continue

                entries.append({
                    "experiment_id": data.get("experiment_id"),
                    "name": data.get("name"),
                    "status": exp_status,
                    "dataset_id": exp_dataset,
                    "created_at": data.get("created_at"),
                    "tags": exp_tags,
                    "filepath": str(p),
                })
            except Exception:
                # Corrupted or unparseable files are skipped during listing
                continue

        return entries

    def delete_report(self, experiment_id: str) -> bool:
        """Delete an experiment report from catalog storage.

        Returns:
            True if file was deleted, False if file did not exist.
        """
        report_path = self._get_report_path(experiment_id)
        if report_path.exists():
            report_path.unlink()
            return True
        return False
