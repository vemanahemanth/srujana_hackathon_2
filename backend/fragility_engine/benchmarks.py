"""FragilityShield — Model Benchmarking Laboratory (Phase 8).

This module orchestrates deterministic, assumption-aware benchmarking across
multiple quantitative risk models, evaluating baseline metrics, comparative rankings,
and robustness shifts under shared perturbations.

Key Capabilities:
1. Benchmark Specification (`BenchmarkSpecification`):
   - Formal specification of models to compare, dataset, baseline assumptions,
     requested metrics, perturbation stress tests, and ranking criteria.
2. Fair Comparison & Incompatibility Isolation:
   - Tests models on identical observation windows and configurations.
   - Explicitly records incompatible data types and missing metrics without guessing.
3. Multi-Model Perturbation Robustness:
   - Evaluates how different models react to identical friction, lookback, and volatility shocks.
4. Transparent, Directional Model Ranking:
   - Formally specifies 'lower_is_better' vs 'higher_is_better' per metric.
   - Deterministic tie-handling without opaque composite scores.
5. Multi-Format Reporting & Reproducibility:
   - Full integration with Phase 6 cryptographic manifests and Phase 7 report exports (JSON, Markdown, CSV).
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np

import fragility_engine
from fragility_engine.models import Portfolio
from fragility_engine.plugins import (
    ModelPlugin,
    PluginMetadata,
    ModelExecutionResult,
    PluginRegistry,
    get_default_registry,
)
from fragility_engine.reproducibility import (
    canonical_json_dumps,
    compute_canonical_hash,
    compute_dataset_hash,
    verify_experiment_invariants,
    capture_environment_metadata,
)


def _clean_md_cell(text: Any) -> str:
    """Escape markdown pipes and newlines for clean table rendering."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def format_metric_unit(metric: str) -> str:
    """Return explicit financial unit representation for a metric."""
    if "points" in metric:
        return "points (0-10000)"
    if "market_value" in metric:
        return "currency"
    if "ratio" in metric:
        return "ratio"
    return "decimal fraction"


# ==============================================================================
# D1. Benchmark Specification
# ==============================================================================

@dataclass(frozen=True)
class BenchmarkSpecification:
    """Typed, validated configuration for a multi-model quantitative benchmark.

    Attributes:
        benchmark_id: Unique identifier for this benchmark run.
        name: Human-readable benchmark title.
        description: Methodological description and research intent.
        dataset_id: Identifier of the shared dataset or portfolio evaluated.
        baseline_config: Common baseline parameters (e.g. confidence_level, annualization_factor).
        plugin_ids: Sequence of registered model plugin IDs to benchmark.
        metrics_to_compare: List of metric keys to compare across models.
        perturbation_specs: Optional perturbations to evaluate across all compatible models.
        target_ranking_metric: Optional metric ID to rank models by.
        ranking_direction: Direction of ranking ('lower_is_better' or 'higher_is_better').
        tolerance: Numerical tolerance for detecting ties and drift (default 1e-6).
        schema_version: Specification schema version.
        algorithm_version: Benchmarking algorithm version.
        random_seed: Optional deterministic random seed.
        tags: Categorization tags.
        metadata: Additional informational notes.
    """

    benchmark_id: str
    name: str
    description: str
    dataset_id: str
    baseline_config: Mapping[str, Any] = field(default_factory=dict)
    plugin_ids: Tuple[str, ...] = ("builtin.historical_simulation", "builtin.parametric_gaussian")
    metrics_to_compare: Tuple[str, ...] = ("annualized_volatility", "var_95", "expected_shortfall_95")
    perturbation_specs: Tuple[Mapping[str, Any], ...] = ()
    target_ranking_metric: Optional[str] = "var_95"
    ranking_direction: str = "lower_is_better"
    evaluation_mode: str = "in_sample_descriptive"
    tolerance: float = 1e-6
    schema_version: str = "1.0.0"
    algorithm_version: str = "1.0.0"
    random_seed: Optional[int] = None
    tags: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark_id, str) or not self.benchmark_id.strip():
            raise ValueError("benchmark_id cannot be blank")

        if any(c in self.benchmark_id for c in ("/", "\\", "\0", "..")):
            raise ValueError(f"benchmark_id '{self.benchmark_id}' contains unsafe path traversal characters")

        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", self.benchmark_id):
            raise ValueError(f"Invalid benchmark_id '{self.benchmark_id}': only alphanumeric, dots, hyphens, and underscores permitted")

        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be blank")

        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id cannot be blank")

        if not self.plugin_ids:
            raise ValueError("plugin_ids sequence cannot be empty")

        if self.ranking_direction not in ("lower_is_better", "higher_is_better"):
            raise ValueError(f"ranking_direction must be 'lower_is_better' or 'higher_is_better'; got '{self.ranking_direction}'")

        if self.evaluation_mode not in ("in_sample_descriptive", "out_of_sample_walk_forward"):
            raise ValueError(
                f"evaluation_mode must be 'in_sample_descriptive' or 'out_of_sample_walk_forward'; got '{self.evaluation_mode}'"
            )

        if self.tolerance <= 0.0 or not math.isfinite(self.tolerance):
            raise ValueError(f"tolerance must be a positive finite float; got {self.tolerance}")

        if self.target_ranking_metric and self.metrics_to_compare:
            if self.target_ranking_metric not in self.metrics_to_compare:
                if self.target_ranking_metric == "var_95" and "var_95" not in self.metrics_to_compare:
                    object.__setattr__(self, "target_ranking_metric", None)
                else:
                    raise ValueError(
                        f"target_ranking_metric '{self.target_ranking_metric}' must be included in metrics_to_compare: {self.metrics_to_compare}"
                    )

        if "confidence_level" in self.baseline_config:
            try:
                conf = float(self.baseline_config["confidence_level"])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"confidence_level must be numeric float: {exc}") from exc
            if not (0.0 < conf < 1.0):
                raise ValueError(f"confidence_level must be in (0, 1); got {conf}")

        # Validate perturbation specifications up-front
        for idx, p_spec in enumerate(self.perturbation_specs, start=1):
            if not isinstance(p_spec, dict):
                raise TypeError(f"Perturbation spec at index {idx} must be a dictionary; got {type(p_spec).__name__}")
            p_type = p_spec.get("type", "")
            if p_type not in (
                "return_friction", "friction",
                "lookback_window", "lookback",
                "volatility_estimator_ewma", "volatility_estimator"
            ):
                raise ValueError(f"Unsupported perturbation type '{p_type}' in perturbation spec {idx}")
            params = p_spec.get("parameters", p_spec)
            if p_type in ("return_friction", "friction"):
                if "friction_bps" in params:
                    try:
                        fbps = float(params["friction_bps"])
                        if not math.isfinite(fbps) or fbps < 0.0:
                            raise ValueError(f"friction_bps must be finite and >= 0.0; got {fbps}")
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"Invalid friction_bps in perturbation spec {idx}: {exc}") from exc
            elif p_type in ("lookback_window", "lookback"):
                p_win = params.get("perturbed_window") or params.get("lookback_window")
                if p_win is not None:
                    try:
                        i_win = int(p_win)
                        if i_win < 2:
                            raise ValueError(f"lookback window must be an integer >= 2; got {i_win}")
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"Invalid lookback window in perturbation spec {idx}: {exc}") from exc
            elif p_type in ("volatility_estimator_ewma", "volatility_estimator"):
                if "decay_factor" in params:
                    try:
                        decay = float(params["decay_factor"])
                        if not math.isfinite(decay) or not (0.0 < decay < 1.0):
                            raise ValueError(f"decay_factor must be strictly between 0 and 1; got {decay}")
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"Invalid decay_factor in perturbation spec {idx}: {exc}") from exc

    def compute_config_hash(self) -> str:
        """Compute deterministic SHA-256 fingerprint over mathematical calculation parameters."""
        canonical_dict = {
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "dataset_id": self.dataset_id,
            "baseline_config": dict(self.baseline_config),
            "plugin_ids": list(self.plugin_ids),
            "metrics_to_compare": list(self.metrics_to_compare),
            "perturbation_specs": list(self.perturbation_specs),
            "target_ranking_metric": self.target_ranking_metric,
            "ranking_direction": self.ranking_direction,
            "evaluation_mode": self.evaluation_mode,
            "tolerance": self.tolerance,
            "random_seed": self.random_seed,
        }
        return compute_canonical_hash(canonical_dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert specification to a serializable dictionary."""
        return {
            "benchmark_id": self.benchmark_id,
            "name": self.name,
            "description": self.description,
            "dataset_id": self.dataset_id,
            "baseline_config": dict(self.baseline_config),
            "plugin_ids": list(self.plugin_ids),
            "metrics_to_compare": list(self.metrics_to_compare),
            "perturbation_specs": [dict(p) for p in self.perturbation_specs],
            "target_ranking_metric": self.target_ranking_metric,
            "ranking_direction": self.ranking_direction,
            "evaluation_mode": self.evaluation_mode,
            "tolerance": self.tolerance,
            "schema_version": self.schema_version,
            "algorithm_version": self.algorithm_version,
            "random_seed": self.random_seed,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


# ==============================================================================
# D2. Benchmark Output & Ranking Models
# ==============================================================================

@dataclass(frozen=True)
class ModelBenchmarkEntry:
    """Individual model evaluation record within a benchmark run.

    Attributes:
        plugin_id: Identifier of the evaluated model plugin.
        model_name: Human-readable model name.
        status: Execution status ('completed', 'failed_validation', 'failed_execution', 'incompatible').
        baseline_metrics: Computed baseline metrics for this model.
        perturbation_metrics: Mapping of perturbation_id -> {metric_name: value}.
        perturbation_deltas: Mapping of perturbation_id -> {metric_name: delta}.
        validation_passed: Whether independent mathematical invariants were satisfied.
        incompatible_reasons: Reasons why this model could not evaluate the dataset/metrics.
        failure_message: Error message if execution or validation failed.
        execution_time_ms: Wall-clock computation duration in milliseconds.
        warnings: Diagnostic warnings raised during evaluation.
        limitations: Methodological boundaries of this model.
    """

    plugin_id: str
    model_name: str
    status: str
    baseline_metrics: Mapping[str, float] = field(default_factory=dict)
    perturbation_metrics: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    perturbation_deltas: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    validation_passed: bool = True
    incompatible_reasons: Tuple[str, ...] = ()
    failure_message: Optional[str] = None
    execution_time_ms: float = 0.0
    warnings: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "model_name": self.model_name,
            "status": self.status,
            "baseline_metrics": {k: float(v) for k, v in self.baseline_metrics.items()},
            "perturbation_metrics": {
                pk: {mk: float(mv) for mk, mv in mdict.items()}
                for pk, mdict in self.perturbation_metrics.items()
            },
            "perturbation_deltas": {
                pk: {mk: float(mv) for mk, mv in mdict.items()}
                for pk, mdict in self.perturbation_deltas.items()
            },
            "validation_passed": self.validation_passed,
            "incompatible_reasons": list(self.incompatible_reasons),
            "failure_message": self.failure_message,
            "execution_time_ms": float(self.execution_time_ms),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class ModelRankingEntry:
    """Individual model standing in a comparative benchmark ranking.

    Attributes:
        rank: 1-based integer rank (1 = best according to ranking_direction).
        plugin_id: Model plugin identifier.
        model_name: Human-readable model name.
        metric_name: Evaluated metric name.
        metric_value: Numerical metric value used for ranking.
        unit: Measurement unit (e.g. 'decimal fraction', 'points (0-10000)').
        interpretation: Meaning of rank ordering (e.g. 'lower_estimated_risk').
        tied: Whether this model tied with an adjacent model within tolerance.
        ranking_direction: Stated direction ('lower_is_better' or 'higher_is_better').
    """

    rank: int
    plugin_id: str
    model_name: str
    metric_name: str
    metric_value: float
    unit: str = "decimal fraction"
    interpretation: str = "lower_estimated_risk"
    tied: bool = False
    ranking_direction: str = "lower_is_better"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "plugin_id": self.plugin_id,
            "model_name": self.model_name,
            "metric_name": self.metric_name,
            "metric_value": float(self.metric_value),
            "unit": self.unit,
            "interpretation": self.interpretation,
            "tied": self.tied,
            "ranking_direction": self.ranking_direction,
        }


@dataclass(frozen=True)
class BenchmarkReport:
    """Structured, reproducible benchmark report comparing multiple quantitative models.

    Attributes:
        benchmark_id: Identifier of the benchmark run.
        name: Benchmark title.
        status: Overall benchmark status ('completed', 'completed_with_warnings', 'failed').
        dataset_id: Identifier of the evaluated dataset.
        created_at: ISO 8601 UTC execution timestamp.
        schema_version: Benchmark report schema version.
        input_fingerprint: SHA-256 fingerprint of input data.
        configuration_fingerprint: SHA-256 fingerprint of benchmark specification.
        output_fingerprint: SHA-256 fingerprint of benchmark results.
        baseline_config: Parameter assumptions applied.
        metrics_compared: Tuple of compared metric keys.
        model_entries: Sequence of ModelBenchmarkEntry instances.
        rankings: Comparative model rankings.
        unranked_models: Models excluded from ranking with reasons.
        manifest: Cryptographic ReproducibilityManifest.
        warnings: Overall diagnostic warnings.
        limitations: Methodological boundaries of the comparative benchmark.
        tags: Categorization tags.
    """

    benchmark_id: str
    name: str
    status: str
    dataset_id: str
    created_at: str
    schema_version: str
    input_fingerprint: str
    configuration_fingerprint: str
    output_fingerprint: str
    baseline_config: Mapping[str, Any]
    metrics_compared: Tuple[str, ...]
    model_entries: Tuple[ModelBenchmarkEntry, ...]
    rankings: Tuple[ModelRankingEntry, ...]
    unranked_models: Tuple[Dict[str, Any], ...]
    manifest: Mapping[str, Any]
    ranking_metric: Optional[str] = None
    ranking_direction: Optional[str] = None
    ranking_interpretation: Optional[str] = None
    ranking_disclaimer: str = (
        "RANKING DISCLAIMER: Model rankings reflect ordering of estimated risk metrics on the provided sample "
        "data under specified model assumptions. A lower estimated Value-at-Risk or Volatility reflects a lower "
        "risk estimate, NOT a superior, more accurate, or better-calibrated risk model. Out-of-sample backtesting "
        "against realized outcomes is required to assess forecast accuracy."
    )
    evaluation_mode: str = "in_sample_descriptive"
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    limitations: Tuple[str, ...] = field(default_factory=tuple)
    tags: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        """Convert complete benchmark report to serializable dictionary."""
        return {
            "benchmark_id": self.benchmark_id,
            "name": self.name,
            "status": self.status,
            "dataset_id": self.dataset_id,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "input_fingerprint": self.input_fingerprint,
            "configuration_fingerprint": self.configuration_fingerprint,
            "output_fingerprint": self.output_fingerprint,
            "baseline_config": dict(self.baseline_config),
            "metrics_compared": list(self.metrics_compared),
            "model_entries": [m.to_dict() for m in self.model_entries],
            "rankings": [r.to_dict() for r in self.rankings],
            "unranked_models": [dict(u) for u in self.unranked_models],
            "manifest": dict(self.manifest),
            "ranking_metric": self.ranking_metric,
            "ranking_direction": self.ranking_direction,
            "ranking_interpretation": self.ranking_interpretation,
            "ranking_disclaimer": self.ranking_disclaimer,
            "evaluation_mode": self.evaluation_mode,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "tags": list(self.tags),
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        """Serialize benchmark report to RFC 8259-compliant canonical JSON."""
        return json.dumps(
            self.to_dict(),
            indent=indent,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BenchmarkReport:
        """Instantiate BenchmarkReport from dictionary."""
        model_entries = tuple(
            ModelBenchmarkEntry(
                plugin_id=m["plugin_id"],
                model_name=m["model_name"],
                status=m["status"],
                baseline_metrics=dict(m.get("baseline_metrics", {})),
                perturbation_metrics=dict(m.get("perturbation_metrics", {})),
                perturbation_deltas=dict(m.get("perturbation_deltas", {})),
                validation_passed=m.get("validation_passed", True),
                incompatible_reasons=tuple(m.get("incompatible_reasons", ())),
                failure_message=m.get("failure_message"),
                execution_time_ms=float(m.get("execution_time_ms", 0.0)),
                warnings=tuple(m.get("warnings", ())),
                limitations=tuple(m.get("limitations", ())),
            )
            for m in data.get("model_entries", [])
        )

        rankings = tuple(
            ModelRankingEntry(
                rank=int(r["rank"]),
                plugin_id=r["plugin_id"],
                model_name=r["model_name"],
                metric_name=r["metric_name"],
                metric_value=float(r["metric_value"]),
                unit=r.get("unit", "decimal fraction"),
                interpretation=r.get("interpretation", "lower_estimated_risk"),
                tied=bool(r.get("tied", False)),
                ranking_direction=r.get("ranking_direction", "lower_is_better"),
            )
            for r in data.get("rankings", [])
        )

        return cls(
            benchmark_id=str(data.get("benchmark_id", "")),
            name=str(data.get("name", "")),
            status=str(data.get("status", "completed")),
            dataset_id=str(data.get("dataset_id", "")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            schema_version=str(data.get("schema_version", "1.0.0")),
            input_fingerprint=str(data.get("input_fingerprint", "")),
            configuration_fingerprint=str(data.get("configuration_fingerprint", "")),
            output_fingerprint=str(data.get("output_fingerprint", "")),
            baseline_config=dict(data.get("baseline_config", {})),
            metrics_compared=tuple(data.get("metrics_compared", ())),
            model_entries=model_entries,
            rankings=rankings,
            unranked_models=tuple(data.get("unranked_models", ())),
            manifest=dict(data.get("manifest", {})),
            ranking_metric=data.get("ranking_metric"),
            ranking_direction=data.get("ranking_direction"),
            ranking_interpretation=data.get("ranking_interpretation"),
            ranking_disclaimer=str(data.get("ranking_disclaimer", (
                "RANKING DISCLAIMER: Model rankings reflect ordering of estimated risk metrics on the provided sample "
                "data under specified model assumptions. A lower estimated Value-at-Risk or Volatility reflects a lower "
                "risk estimate, NOT a superior, more accurate, or better-calibrated risk model. Out-of-sample backtesting "
                "against realized outcomes is required to assess forecast accuracy."
            ))),
            evaluation_mode=str(data.get("evaluation_mode", "in_sample_descriptive")),
            warnings=tuple(data.get("warnings", ())),
            limitations=tuple(data.get("limitations", ())),
            tags=tuple(data.get("tags", ())),
        )

    @classmethod
    def from_json(cls, json_str: str) -> BenchmarkReport:
        """Instantiate BenchmarkReport from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def to_markdown(self) -> str:
        """Generate human-readable publication-grade Markdown benchmark report."""
        lines = [
            f"# FragilityShield — Model Benchmark Report: {self.name}",
            "",
            f"**Benchmark ID:** `{self.benchmark_id}`  ",
            f"**Status:** `{self.status.upper()}`  ",
            f"**Dataset ID:** `{self.dataset_id}`  ",
            f"**Evaluation Mode:** `{self.evaluation_mode}`  ",
            f"**Generated At:** `{self.created_at}`  ",
            f"**Schema Version:** `{self.schema_version}`  ",
            "",
            "---",
            "",
            "## 1. Cryptographic Provenance & Fingerprints",
            "",
            "| Fingerprint Type | SHA-256 Digest |",
            "| :--- | :--- |",
            f"| **Input Data Fingerprint** | `{self.input_fingerprint}` |",
            f"| **Configuration Fingerprint** | `{self.configuration_fingerprint}` |",
            f"| **Output Results Fingerprint** | `{self.output_fingerprint}` |",
            "",
            "---",
            "",
            "## 2. Comparative Model Rankings",
            "",
        ]

        if not self.rankings:
            lines.append("*No comparative rankings computed.*")
        else:
            first_rank = self.rankings[0]
            interp = self.ranking_interpretation or first_rank.interpretation
            lines.extend([
                f"**Target Metric:** `{first_rank.metric_name}`  ",
                f"**Measurement Unit:** `{first_rank.unit}`  ",
                f"**Ranking Direction:** `{first_rank.ranking_direction}` ({interp})  ",
                "",
                f"> **Model Comparison Disclaimer:** {self.ranking_disclaimer}",
                "",
                "| Rank | Model Plugin | Model Name | Metric Value | Unit | Interpretation | Tied |",
                "| :---: | :--- | :--- | :---: | :--- | :--- | :---: |",
            ])
            for r in self.rankings:
                tied_str = "Yes" if r.tied else "No"
                lines.append(
                    f"| {r.rank} | `{r.plugin_id}` | {r.model_name} | {r.metric_value:.6f} | {r.unit} | {r.interpretation} | {tied_str} |"
                )

        if self.unranked_models:
            lines.extend([
                "",
                "### Excluded / Incomparable Models",
                "",
                "| Model Plugin | Reason For Exclusion |",
                "| :--- | :--- |",
            ])
            for u in self.unranked_models:
                lines.append(f"| `{u.get('plugin_id', '-')}` | {u.get('reason', '-')} |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Metric Comparison Grid",
            "",
        ])

        # Header with all compared metrics
        header = ["Model Plugin", "Status"] + [f"`{m}`" for m in self.metrics_compared]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join([":---"] * len(header)) + " |")

        for m in self.model_entries:
            row = [f"`{m.plugin_id}`", m.status]
            for mk in self.metrics_compared:
                if mk in m.baseline_metrics:
                    val = m.baseline_metrics[mk]
                    row.append(f"{val:.6f}")
                else:
                    row.append("-")
            lines.append("| " + " | ".join(row) + " |")

        # Perturbation Robustness Table
        has_perturbations = any(m.perturbation_metrics for m in self.model_entries)
        if has_perturbations:
            lines.extend([
                "",
                "---",
                "",
                "## 4. Perturbation Robustness Comparison",
                "",
                "| Model Plugin | Perturbation ID | Metric | Baseline | Stressed | Delta |",
                "| :--- | :--- | :--- | :---: | :---: | :---: |",
            ])
            for m in self.model_entries:
                for pk, pmetrics in m.perturbation_metrics.items():
                    for mk, stressed_val in pmetrics.items():
                        base_val = m.baseline_metrics.get(mk)
                        delta = m.perturbation_deltas.get(pk, {}).get(mk)
                        b_str = f"{base_val:.6f}" if base_val is not None else "-"
                        d_str = f"{delta:+.6f}" if delta is not None else "-"
                        lines.append(
                            f"| `{m.plugin_id}` | `{pk}` | `{mk}` | {b_str} | {stressed_val:.6f} | {d_str} |"
                        )

        # Invariant Verification & Warnings
        lines.extend([
            "",
            "---",
            "",
            "## 5. Independent Validation & Limitations",
            "",
        ])

        if self.warnings:
            lines.append("### Diagnostic Warnings")
            for w in self.warnings:
                lines.append(f"- [WARNING] {w}")
            lines.append("")

        if self.limitations:
            lines.append("### Methodological Limitations")
            for lim in self.limitations:
                lines.append(f"- [LIMITATION] {lim}")
            lines.append("")

        return "\n".join(lines)

    def to_csv(self) -> str:
        """Export model benchmark grid as clean, standardized tabular CSV."""
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        writer.writerow([
            "benchmark_id",
            "dataset_id",
            "plugin_id",
            "model_name",
            "status",
            "metric_name",
            "unit",
            "baseline_value",
            "perturbation_id",
            "stressed_value",
            "delta",
            "execution_time_ms",
        ])

        for m in self.model_entries:
            # Baseline rows
            for mk in self.metrics_compared:
                if mk in m.baseline_metrics:
                    writer.writerow([
                        self.benchmark_id,
                        self.dataset_id,
                        m.plugin_id,
                        m.model_name,
                        m.status,
                        mk,
                        format_metric_unit(mk),
                        m.baseline_metrics[mk],
                        "",
                        "",
                        "",
                        m.execution_time_ms,
                    ])

            # Perturbation rows
            for pk, pmetrics in m.perturbation_metrics.items():
                for mk, stressed_val in pmetrics.items():
                    base_val = m.baseline_metrics.get(mk, "")
                    delta = m.perturbation_deltas.get(pk, {}).get(mk, "")
                    writer.writerow([
                        self.benchmark_id,
                        self.dataset_id,
                        m.plugin_id,
                        m.model_name,
                        m.status,
                        mk,
                        format_metric_unit(mk),
                        base_val,
                        pk,
                        stressed_val,
                        delta,
                        m.execution_time_ms,
                    ])

        return output.getvalue()


# ==============================================================================
# D3. Benchmark Execution Workflow
# ==============================================================================

def execute_model_benchmark(
    spec: BenchmarkSpecification,
    dataset: Sequence[float] | np.ndarray | Portfolio,
    registry: Optional[PluginRegistry] = None,
    environment_metadata: Optional[Mapping[str, Any]] = None,
) -> BenchmarkReport:
    """Execute end-to-end quantitative model benchmark.

    Workflow:
    1. Validates benchmark specification and dataset.
    2. Discovers and queries requested model plugins.
    3. Runs baseline calculations across all models on identical data.
    4. Evaluates requested stress perturbations across models.
    5. Validates independent mathematical invariants on model outputs.
    6. Constructs transparent, directional rankings.
    7. Generates cryptographic SHA-256 manifest and structured BenchmarkReport.

    Args:
        spec: Validated BenchmarkSpecification.
        dataset: Input return series or Portfolio instance.
        registry: Optional custom PluginRegistry (defaults to get_default_registry()).
        environment_metadata: Optional runtime environment dictionary.

    Returns:
        Structured, reproducible BenchmarkReport.
    """
    if not isinstance(spec, BenchmarkSpecification):
        raise TypeError(f"spec must be a BenchmarkSpecification; got {type(spec).__name__}")

    if dataset is None:
        raise TypeError("dataset cannot be None")

    if registry is None:
        registry = get_default_registry()

    now_utc = datetime.now(timezone.utc).isoformat()
    warnings: List[str] = []
    limitations: List[str] = [
        "Comparative rankings evaluate specific risk estimator formulas on historical data.",
        "A lower risk estimate does not guarantee superior real-world risk management.",
    ]

    # Compute input and config fingerprints
    input_fp = compute_dataset_hash(dataset)
    config_fp = spec.compute_config_hash()

    # Determine data shape
    is_portfolio = isinstance(dataset, Portfolio)
    data_type_tag = "portfolio" if is_portfolio else "return_series"

    model_entries: List[ModelBenchmarkEntry] = []
    all_validation_passed = True

    # 1. Execute each requested plugin
    for pid in spec.plugin_ids:
        if pid not in registry:
            model_entries.append(
                ModelBenchmarkEntry(
                    plugin_id=pid,
                    model_name=pid,
                    status="incompatible",
                    incompatible_reasons=(f"Plugin '{pid}' is not registered in the provided registry.",),
                )
            )
            continue

        plugin = registry.get(pid)
        meta = plugin.metadata

        # Check data type compatibility
        if data_type_tag not in meta.supported_data_types:
            model_entries.append(
                ModelBenchmarkEntry(
                    plugin_id=pid,
                    model_name=meta.name,
                    status="incompatible",
                    incompatible_reasons=(
                        f"Model supports data types {meta.supported_data_types}, "
                        f"which does not include current dataset type '{data_type_tag}'.",
                    ),
                    limitations=meta.limitations,
                )
            )
            continue

        # Execute baseline
        t0 = time.perf_counter()
        try:
            res = plugin.execute(dataset, spec.baseline_config)
            t_ms = (time.perf_counter() - t0) * 1000.0
            base_metrics = dict(res.metrics)
            exec_warnings = list(res.warnings)
            model_status = "completed"
            failure_msg = None
        except Exception as exc:
            t_ms = (time.perf_counter() - t0) * 1000.0
            model_entries.append(
                ModelBenchmarkEntry(
                    plugin_id=pid,
                    model_name=meta.name,
                    status="failed_execution",
                    failure_message=str(exc),
                    execution_time_ms=t_ms,
                    limitations=meta.limitations,
                )
            )
            continue

        # Run independent invariant checks on baseline
        inv_rep = verify_experiment_invariants(
            baseline_metrics=base_metrics,
            perturbation_results=(),
            portfolio=dataset if is_portfolio else None,
        )

        if not inv_rep.all_passed:
            all_validation_passed = False
            model_status = "failed_validation"
            failure_msg = "; ".join(inv_rep.failure_messages)

        # 2. Execute perturbations if configured
        pert_metrics: Dict[str, Dict[str, float]] = {}
        pert_deltas: Dict[str, Dict[str, float]] = {}

        if not is_portfolio and spec.perturbation_specs:
            arr_data = np.asarray(dataset, dtype=np.float64)

            for idx, p_spec in enumerate(spec.perturbation_specs, start=1):
                p_type = p_spec.get("type", "")
                p_id = p_spec.get("experiment_id") or f"pert_{idx}_{p_type}"
                p_params = p_spec.get("parameters", p_spec)

                try:
                    if p_type in ("return_friction", "friction"):
                        fric_bps = float(p_params.get("friction_bps", 5.0))
                        cost_dec = fric_bps / 10000.0
                        perturbed_arr = arr_data - cost_dec
                        p_res = plugin.execute(perturbed_arr, spec.baseline_config)
                        pert_metrics[p_id] = {k: v for k, v in p_res.metrics.items() if k in spec.metrics_to_compare}

                    elif p_type in ("lookback_window", "lookback"):
                        p_win = int(p_params.get("perturbed_window") or p_params.get("lookback_window", 30))
                        if p_win > len(arr_data):
                            continue
                        perturbed_arr = arr_data[-p_win:]
                        p_res = plugin.execute(perturbed_arr, spec.baseline_config)
                        pert_metrics[p_id] = {k: v for k, v in p_res.metrics.items() if k in spec.metrics_to_compare}

                    elif p_type in ("volatility_estimator_ewma", "volatility_estimator"):
                        if "decay_factor" in meta.optional_config_keys or "decay_factor" in meta.required_config_keys:
                            decay = float(p_params.get("decay_factor", 0.94))
                            cfg = dict(spec.baseline_config)
                            cfg["decay_factor"] = decay
                            p_res = plugin.execute(arr_data, cfg)
                            pert_metrics[p_id] = {k: v for k, v in p_res.metrics.items() if k in spec.metrics_to_compare}

                    # Compute deltas for recorded metrics
                    if p_id in pert_metrics:
                        deltas: Dict[str, float] = {}
                        for mk, s_val in pert_metrics[p_id].items():
                            if mk in base_metrics:
                                deltas[mk] = s_val - base_metrics[mk]
                        pert_deltas[p_id] = deltas

                except Exception as p_err:
                    warnings.append(f"Model '{pid}' perturbation '{p_id}' failed: {p_err}")

        model_entries.append(
            ModelBenchmarkEntry(
                plugin_id=pid,
                model_name=meta.name,
                status=model_status,
                baseline_metrics=base_metrics,
                perturbation_metrics=pert_metrics,
                perturbation_deltas=pert_deltas,
                validation_passed=inv_rep.all_passed,
                failure_message=failure_msg,
                execution_time_ms=t_ms,
                warnings=tuple(exec_warnings),
                limitations=meta.limitations,
            )
        )

    # 3. Construct Rankings if target_ranking_metric is specified
    rankings: List[ModelRankingEntry] = []
    unranked_models: List[Dict[str, Any]] = []

    if spec.target_ranking_metric:
        target_m = spec.target_ranking_metric
        eligible_entries: List[ModelBenchmarkEntry] = []

        for m in model_entries:
            if m.status not in ("completed", "completed_with_warnings"):
                unranked_models.append({
                    "plugin_id": m.plugin_id,
                    "reason": f"Model status is '{m.status}' (failed execution or validation).",
                })
            elif target_m not in m.baseline_metrics:
                unranked_models.append({
                    "plugin_id": m.plugin_id,
                    "reason": f"Model does not report target metric '{target_m}'.",
                })
            else:
                eligible_entries.append(m)

        # Sort eligible models according to ranking direction
        reverse_sort = (spec.ranking_direction == "higher_is_better")
        sorted_entries = sorted(
            eligible_entries,
            key=lambda m: m.baseline_metrics[target_m],
            reverse=reverse_sort,
        )

        current_rank = 1
        for idx, m in enumerate(sorted_entries):
            val = m.baseline_metrics[target_m]
            is_tied = False

            # Check tie with predecessor
            if idx > 0:
                prev_val = sorted_entries[idx - 1].baseline_metrics[target_m]
                if abs(val - prev_val) <= spec.tolerance:
                    is_tied = True

            # Check tie with successor
            if idx < len(sorted_entries) - 1:
                next_val = sorted_entries[idx + 1].baseline_metrics[target_m]
                if abs(val - next_val) <= spec.tolerance:
                    is_tied = True

            if idx > 0 and not is_tied:
                current_rank = idx + 1
            elif idx > 0 and is_tied:
                prev_val = sorted_entries[idx - 1].baseline_metrics[target_m]
                if abs(val - prev_val) > spec.tolerance:
                    current_rank = idx + 1

            target_unit = format_metric_unit(target_m)
            interp = (
                "lower_estimated_risk"
                if spec.ranking_direction == "lower_is_better"
                else "higher_estimated_risk"
            )
            rankings.append(
                ModelRankingEntry(
                    rank=current_rank,
                    plugin_id=m.plugin_id,
                    model_name=m.model_name,
                    metric_name=target_m,
                    metric_value=val,
                    unit=target_unit,
                    interpretation=interp,
                    tied=is_tied,
                    ranking_direction=spec.ranking_direction,
                )
            )

    # 4. Generate Output Fingerprint & Manifest covering baseline metrics, perturbations, and rankings
    manifest_results = {
        "models": {
            m.plugin_id: {
                "status": m.status,
                "baseline_metrics": {k: float(v) for k, v in m.baseline_metrics.items()},
                "perturbation_metrics": {
                    pk: {mk: float(mv) for mk, mv in pdict.items()}
                    for pk, pdict in m.perturbation_metrics.items()
                },
                "perturbation_deltas": {
                    pk: {mk: float(mv) for mk, mv in pdict.items()}
                    for pk, pdict in m.perturbation_deltas.items()
                },
            }
            for m in model_entries
        },
        "rankings": [r.to_dict() for r in rankings],
    }
    output_fp = compute_canonical_hash(manifest_results)

    env_info = dict(environment_metadata) if environment_metadata else capture_environment_metadata()
    manifest_dict = {
        "benchmark_id": spec.benchmark_id,
        "input_fingerprint": input_fp,
        "configuration_fingerprint": config_fp,
        "output_fingerprint": output_fp,
        "environment_info": env_info,
        "validation_status": "PASSED" if all_validation_passed else "FAILED",
        "models_evaluated": len(model_entries),
        "execution_timestamp": now_utc,
    }

    # Determine overall status
    overall_status = "completed"
    if not all_validation_passed:
        overall_status = "completed_with_warnings" if any(m.status == "completed" for m in model_entries) else "failed"
    elif all(m.status == "failed_execution" for m in model_entries):
        overall_status = "failed"
    elif any(m.status != "completed" for m in model_entries) or warnings:
        overall_status = "completed_with_warnings"

    ranking_interp = None
    if spec.target_ranking_metric:
        ranking_interp = (
            "lower_estimated_risk"
            if spec.ranking_direction == "lower_is_better"
            else "higher_estimated_risk"
        )

    return BenchmarkReport(
        benchmark_id=spec.benchmark_id,
        name=spec.name,
        status=overall_status,
        dataset_id=spec.dataset_id,
        created_at=now_utc,
        schema_version=spec.schema_version,
        input_fingerprint=input_fp,
        configuration_fingerprint=config_fp,
        output_fingerprint=output_fp,
        baseline_config=dict(spec.baseline_config),
        metrics_compared=spec.metrics_to_compare,
        model_entries=tuple(model_entries),
        rankings=tuple(rankings),
        unranked_models=tuple(unranked_models),
        manifest=manifest_dict,
        ranking_metric=spec.target_ranking_metric,
        ranking_direction=spec.ranking_direction if spec.target_ranking_metric else None,
        ranking_interpretation=ranking_interp,
        evaluation_mode=spec.evaluation_mode,
        warnings=tuple(warnings),
        limitations=tuple(limitations),
        tags=spec.tags,
    )
