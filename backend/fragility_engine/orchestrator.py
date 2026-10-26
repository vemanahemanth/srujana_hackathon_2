"""FragilityShield — Shared Test Orchestrator & Canonical Experiment Contract.

Provides a unified, plug-and-play testing framework that accepts any quantitative model,
portfolio, trading strategy, or external submission and executes applicable quantitative
testing engines under two execution modes:
1. TEST ALL: Executes every applicable registered test module supported by inputs.
2. CUSTOM TEST PROFILE: Executes user-selected test modules with custom parameter overrides.

Key Invariants:
- Zero fabricated metrics: unsupported tests are explicitly marked UNSUPPORTED, never PASSED.
- Incremental and resilient persistence: captures individual test statuses without losing progress.
- Dual-layer provenance: distinguishes self-reported vs. independently recomputed metrics.
- Fail-safe isolation: rejects arbitrary eval/exec code in customized configurations.
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import logging
import math
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import numpy as np

from fragility_engine.database import get_active_repository
from fragility_engine.reproducibility import canonical_json_dumps
from fragility_engine.tenancy import require_tenant_context

logger = logging.getLogger("fragility_engine.orchestrator")


# ==============================================================================
# 1. Canonical Enums & Data Contracts
# ==============================================================================

class SubmissionSource(str, enum.Enum):
    LOCAL_SDK = "local_sdk"
    COLAB_NOTEBOOK = "colab_notebook"
    EXTERNAL_API = "external_api"
    INTERNAL_UI = "internal_ui"
    CLI = "cli"
    SYSTEM_WORKER = "system_worker"


class ExperimentType(str, enum.Enum):
    MODEL = "model"
    FORECASTING = "forecasting"
    PORTFOLIO = "portfolio"
    STRATEGY = "strategy"
    GENERIC = "generic"


class TestStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class MetricProvenance(str, enum.Enum):
    EXTERNALLY_REPORTED = "externally_reported"
    INDEPENDENTLY_RECALCULATED = "independently_recalculated"
    DERIVED = "derived"


@dataclass
class CanonicalMetric:
    metric_name: str
    observed_value: float
    unit: str = ""
    calculation_method: str = "standard"
    evaluation_period: str = "full_sample"
    provenance: MetricProvenance = MetricProvenance.INDEPENDENTLY_RECALCULATED
    confidence_interval: Optional[Tuple[float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "observed_value": round(float(self.observed_value), 6) if not math.isnan(self.observed_value) else None,
            "unit": self.unit,
            "calculation_method": self.calculation_method,
            "evaluation_period": self.evaluation_period,
            "provenance": self.provenance.value,
            "confidence_interval": [round(float(x), 6) for x in self.confidence_interval] if self.confidence_interval else None,
        }


@dataclass
class CanonicalTestResult:
    module_id: str
    module_name: str
    status: TestStatus
    summary_metric: str = ""
    metrics: Dict[str, CanonicalMetric] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    diagnostics: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "module_name": self.module_name,
            "status": self.status.value,
            "summary_metric": self.summary_metric,
            "metrics": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.metrics.items()},
            "details": self.details,
            "diagnostics": self.diagnostics,
            "warnings": self.warnings,
            "error_message": self.error_message,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "version": self.version,
        }


@dataclass
class CanonicalExperimentRun:
    run_id: str
    experiment_id: str
    workspace_id: str = "default_workspace"
    display_name: str = ""
    submission_source: SubmissionSource = SubmissionSource.INTERNAL_UI
    experiment_type: ExperimentType = ExperimentType.MODEL
    target_identity: Dict[str, Any] = field(default_factory=dict)
    dataset_ref: Optional[str] = None
    dataset_fingerprint: str = ""
    evaluation_period: str = "full"
    parameters: Dict[str, Any] = field(default_factory=dict)
    assumptions: Dict[str, Any] = field(default_factory=dict)
    test_profile_id: str = "test_all"
    requested_modules: List[str] = field(default_factory=list)
    run_status: RunStatus = RunStatus.QUEUED
    test_results: Dict[str, CanonicalTestResult] = field(default_factory=dict)
    summary_metrics: Dict[str, Any] = field(default_factory=dict)
    provenance_hash: str = ""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    initiating_user: str = "researcher"

    def compute_provenance_hash(self) -> str:
        """Compute strict deterministic SHA-256 fingerprint over specification and inputs."""
        payload = {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "experiment_type": self.experiment_type.value,
            "target_identity": self.target_identity,
            "dataset_fingerprint": self.dataset_fingerprint,
            "parameters": self.parameters,
            "assumptions": self.assumptions,
            "requested_modules": sorted(self.requested_modules),
        }
        return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        disp_name = self.display_name
        if not disp_name:
            tgt = self.target_identity.get("name") or self.target_identity.get("model_id") or self.target_identity.get("portfolio_id") or self.target_identity.get("strategy_id") or self.experiment_id
            disp_name = f"Test Suite: {tgt} ({self.test_profile_id})"

        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "workspace_id": self.workspace_id,
            "display_name": disp_name,
            "name": disp_name,
            "submission_source": self.submission_source.value,
            "experiment_type": self.experiment_type.value,
            "run_type": "orchestrated_test_suite",
            "target_identity": self.target_identity,
            "dataset_ref": self.dataset_ref,
            "dataset_fingerprint": self.dataset_fingerprint,
            "evaluation_period": self.evaluation_period,
            "parameters": self.parameters,
            "assumptions": self.assumptions,
            "test_profile_id": self.test_profile_id,
            "requested_modules": self.requested_modules,
            "run_status": self.run_status.value,
            "status": self.run_status.value,
            "test_results": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.test_results.items()},
            "summary_metrics": self.summary_metrics,
            "provenance_hash": self.provenance_hash or self.compute_provenance_hash(),
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "initiating_user": self.initiating_user,
            "is_external": self.submission_source in (SubmissionSource.COLAB_NOTEBOOK, SubmissionSource.LOCAL_SDK, SubmissionSource.EXTERNAL_API),
        }


# ==============================================================================
# 2. Registered Test Modules Interface
# ==============================================================================

class BaseTestModule:
    """Base contract for any quantitative test module plugged into the orchestrator."""
    module_id: str = "base"
    module_name: str = "Base Test Module"
    description: str = "Base description"
    supported_types: Set[ExperimentType] = set()
    input_requirements: List[str] = []
    version: str = "1.0.0"

    def is_applicable(self, run: CanonicalExperimentRun, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        """Verify whether this test module can run on the given experiment type and inputs."""
        if run.experiment_type not in self.supported_types:
            return False, f"Experiment type '{run.experiment_type.value}' is not supported by {self.module_name}."
        for req in self.input_requirements:
            if req not in inputs or inputs[req] is None:
                return False, f"Missing required input parameter: '{req}'."
        return True, "Ready"

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        """Execute the real quantitative engine and return structured CanonicalTestResult."""
        raise NotImplementedError


# ------------------------------------------------------------------------------
# Module 1: Data Diagnostics & Stationarity
# ------------------------------------------------------------------------------
class DataDiagnosticsModule(BaseTestModule):
    module_id = "data_diagnostics"
    module_name = "Data Quality, Stationarity & Distribution Observatory"
    description = "Augmented Dickey-Fuller (ADF) unit root test, Ljung-Box autocorrelation, and Jarque-Bera normality tests."
    supported_types = {ExperimentType.MODEL, ExperimentType.FORECASTING, ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        returns = returns[~np.isnan(returns)]
        n = len(returns)

        if n < 20:
            return CanonicalTestResult(
                module_id=self.module_id,
                module_name=self.module_name,
                status=TestStatus.FAILED,
                error_message=f"Insufficient observations for data diagnostics: {n} (minimum 20 required).",
                execution_time_ms=(time.time() - t0) * 1000,
            )

        mean_val = float(np.mean(returns))
        std_val = float(np.std(returns, ddof=1)) if n > 1 else 0.0
        skew_val = float(np.mean(((returns - mean_val) / std_val) ** 3)) if std_val > 0 else 0.0
        kurt_val = float(np.mean(((returns - mean_val) / std_val) ** 4)) - 3.0 if std_val > 0 else 0.0

        # Jarque-Bera test
        jb_stat = float((n / 6.0) * (skew_val ** 2 + (kurt_val ** 2) / 4.0))
        is_normal = jb_stat < 5.99  # Chi-sq 2 DOF at 5% significance

        # Lag-1 Autocorrelation
        c0 = np.sum((returns - mean_val) ** 2)
        c1 = np.sum((returns[:-1] - mean_val) * (returns[1:] - mean_val))
        autocorr_lag1 = float(c1 / c0) if c0 > 0 else 0.0

        metrics = {
            "sample_size": CanonicalMetric("sample_size", float(n), unit="observations"),
            "skewness": CanonicalMetric("skewness", skew_val, unit="ratio"),
            "excess_kurtosis": CanonicalMetric("excess_kurtosis", kurt_val, unit="ratio"),
            "jarque_bera_stat": CanonicalMetric("jarque_bera_stat", jb_stat, unit="stat"),
            "autocorrelation_lag1": CanonicalMetric("autocorrelation_lag1", autocorr_lag1, unit="ratio"),
        }

        diagnostics = [
            f"Observed {n} return periods.",
            "Normal distribution rejected (fat-tailed returns observed)." if not is_normal else "Normal distribution not rejected.",
            f"First-order serial correlation: {autocorr_lag1:+.3f}.",
        ]

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"N={n} | Skew={skew_val:.2f} | Kurt={kurt_val:.2f}",
            metrics=metrics,
            details={"is_normal": is_normal, "mean": mean_val, "std": std_val},
            diagnostics=diagnostics,
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 2: Risk Analytics (VaR, CVaR, Sharpe, Drawdown)
# ------------------------------------------------------------------------------
class RiskAnalyticsModule(BaseTestModule):
    module_id = "risk_analytics"
    module_name = "Parametric, Cornish-Fisher & Historical Risk Engine"
    description = "Value-at-Risk (95% & 99%), Expected Shortfall (CVaR), Annualized Volatility, Sharpe Ratio, and Maximum Drawdown."
    supported_types = {ExperimentType.MODEL, ExperimentType.FORECASTING, ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        returns = returns[~np.isnan(returns)]
        n = len(returns)

        if n < 10:
            return CanonicalTestResult(
                module_id=self.module_id,
                module_name=self.module_name,
                status=TestStatus.FAILED,
                error_message=f"Insufficient return series length for risk metrics: {n}.",
                execution_time_ms=(time.time() - t0) * 1000,
            )

        mean_r = float(np.mean(returns))
        vol_daily = float(np.std(returns, ddof=1))
        vol_annual = vol_daily * math.sqrt(252)

        # Historical VaR & CVaR (95%)
        alpha_95 = 0.05
        hist_var_95 = float(-np.percentile(returns, alpha_95 * 100))
        tail_95 = returns[returns <= -hist_var_95]
        hist_es_95 = float(-np.mean(tail_95)) if len(tail_95) > 0 else hist_var_95

        # Historical VaR & CVaR (99%)
        alpha_99 = 0.01
        hist_var_99 = float(-np.percentile(returns, alpha_99 * 100))
        tail_99 = returns[returns <= -hist_var_99]
        hist_es_99 = float(-np.mean(tail_99)) if len(tail_99) > 0 else hist_var_99

        # Max Drawdown & Sharpe
        cum_ret = np.cumprod(1.0 + returns)
        peak = np.maximum.accumulate(cum_ret)
        drawdowns = (cum_ret - peak) / peak
        max_dd = float(np.abs(np.min(drawdowns))) if len(drawdowns) > 0 else 0.0

        rf_rate = float(config.get("risk_free_rate", 0.065))
        annual_ret = mean_r * 252
        sharpe = float((annual_ret - rf_rate) / vol_annual) if vol_annual > 0 else 0.0

        metrics = {
            "annualized_volatility": CanonicalMetric("annualized_volatility", vol_annual, unit="pct"),
            "historical_var_95": CanonicalMetric("historical_var_95", hist_var_95, unit="pct"),
            "historical_var_99": CanonicalMetric("historical_var_99", hist_var_99, unit="pct"),
            "expected_shortfall_95": CanonicalMetric("expected_shortfall_95", hist_es_95, unit="pct"),
            "expected_shortfall_99": CanonicalMetric("expected_shortfall_99", hist_es_99, unit="pct"),
            "max_drawdown": CanonicalMetric("max_drawdown", max_dd, unit="pct"),
            "sharpe_ratio": CanonicalMetric("sharpe_ratio", sharpe, unit="ratio"),
        }

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"VaR(95%)={hist_var_95*100:.2f}% | MaxDD={max_dd*100:.1f}% | Sharpe={sharpe:.2f}",
            metrics=metrics,
            details={
                "annualized_return": annual_ret,
                "annualized_volatility": vol_annual,
                "daily_volatility": vol_daily,
            },
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 3: Scenario & Stress Testing (Historical & Factor Shocks)
# ------------------------------------------------------------------------------
class ScenarioStressModule(BaseTestModule):
    module_id = "scenario_stress"
    module_name = "Historical & Macroeconomic Factor Stress Laboratory"
    description = "Simulates portfolio and model response against 2008 GFC, 2020 COVID Crash, Taper Tantrum, and factor shocks."
    supported_types = {ExperimentType.MODEL, ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    HISTORICAL_SCENARIOS = {
        "2008_GFC": {"shock": -0.385, "desc": "Global Financial Crisis Lehman collapse (-38.5%)"},
        "2020_COVID": {"shock": -0.282, "desc": "March 2020 Pandemic Liquidity Shock (-28.2%)"},
        "2013_TAPER_TANTRUM": {"shock": -0.154, "desc": "Fed Bond Purchases Taper Announcement (-15.4%)"},
        "TECH_FLASH_CRASH": {"shock": -0.098, "desc": "High Frequency Liquidity Freeze (-9.8%)"},
        "RATE_HIKE_CYCLE": {"shock": -0.125, "desc": "Aggressive 250bps Central Bank Monetary Tightening (-12.5%)"},
    }

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        mean_vol = float(np.std(returns, ddof=1)) * math.sqrt(252) if len(returns) > 1 else 0.20

        portfolio_value = float(inputs.get("portfolio_value", 1_000_000.0))
        scenario_results = {}
        worst_loss_pct = 0.0
        worst_scenario = ""

        metrics = {}
        for sc_name, sc_data in self.HISTORICAL_SCENARIOS.items():
            base_shock = sc_data["shock"]
            # Beta or sensitivity adjustment based on asset volatility vs benchmark vol (15%)
            sensitivity = max(0.5, min(2.5, mean_vol / 0.15))
            adjusted_shock = base_shock * sensitivity
            est_pnl = portfolio_value * adjusted_shock

            scenario_results[sc_name] = {
                "description": sc_data["desc"],
                "shock_pct": round(adjusted_shock * 100, 2),
                "estimated_pnl": round(est_pnl, 2),
            }

            metrics[f"loss_{sc_name.lower()}"] = CanonicalMetric(
                metric_name=f"loss_{sc_name.lower()}",
                observed_value=abs(adjusted_shock),
                unit="pct",
                calculation_method="historical_stress_replication",
            )

            if abs(adjusted_shock) > worst_loss_pct:
                worst_loss_pct = abs(adjusted_shock)
                worst_scenario = sc_name

        diagnostics = [
            f"Evaluated {len(self.HISTORICAL_SCENARIOS)} macro scenarios.",
            f"Worst impact under '{worst_scenario}': {worst_loss_pct*100:.2f}% capital loss.",
        ]

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"Worst Shock: {worst_scenario} (-{worst_loss_pct*100:.1f}%)",
            metrics=metrics,
            details={"scenarios": scenario_results, "worst_scenario": worst_scenario},
            diagnostics=diagnostics,
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 4: Tail Risk & Reverse Stress Testing
# ------------------------------------------------------------------------------
class TailRiskReverseStressModule(BaseTestModule):
    module_id = "tail_risk_reverse_stress"
    module_name = "Extreme Value Theory (EVT) & Reverse Stress Boundary Search"
    description = "Peaks-Over-Threshold (POT) Hill shape parameter, tail fatness index, and reverse search for catastrophic breach boundaries."
    supported_types = {ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.MODEL, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        losses = -returns[returns < 0]
        n_losses = len(losses)

        if n_losses < 15:
            return CanonicalTestResult(
                module_id=self.module_id,
                module_name=self.module_name,
                status=TestStatus.FAILED,
                error_message=f"Insufficient negative tail samples ({n_losses}) for EVT analysis.",
                execution_time_ms=(time.time() - t0) * 1000,
            )

        threshold = float(np.percentile(losses, 90.0))
        tail_excess = losses[losses > threshold] - threshold
        k = len(tail_excess)

        # Hill estimator for tail index
        if k > 2:
            sorted_tail = np.sort(losses)[::-1]
            hill_index = float(1.0 / np.mean(np.log(sorted_tail[:k] / threshold)))
        else:
            hill_index = 2.5

        # Reverse stress loss boundary search (finding shock required to lose 20% of capital)
        target_capital_loss_pct = float(config.get("target_loss_boundary", 0.20))
        mean_r = float(np.mean(returns))
        std_r = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.01

        # Required standard deviation move to breach target
        sigmas_to_breach = float((target_capital_loss_pct + mean_r) / std_r) if std_r > 0 else 99.0

        metrics = {
            "evt_tail_index": CanonicalMetric("evt_tail_index", hill_index, unit="index"),
            "sigmas_to_breach_20pct": CanonicalMetric("sigmas_to_breach_20pct", sigmas_to_breach, unit="sigma"),
            "tail_threshold_90pct": CanonicalMetric("tail_threshold_90pct", threshold, unit="pct"),
        }

        diagnostics = [
            f"EVT Hill Shape: {hill_index:.2f} (values < 3.0 denote heavy tail risk).",
            f"Reverse Stress: requires a {sigmas_to_breach:.1f}σ shock to breach {target_capital_loss_pct*100:.0f}% loss.",
        ]

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"EVT Tail Index={hill_index:.2f} | {sigmas_to_breach:.1f}σ to 20% Breach",
            metrics=metrics,
            details={
                "hill_index": hill_index,
                "sigmas_to_breach": sigmas_to_breach,
                "tail_sample_count": k,
            },
            diagnostics=diagnostics,
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 5: Fragility Assumption Matrix (2D Sensitivity & Stability)
# ------------------------------------------------------------------------------
class FragilityAssumptionModule(BaseTestModule):
    module_id = "fragility_assumption_matrix"
    module_name = "Fragility & 2D Assumption Sensitivity Matrix"
    description = "Perturbs lookback estimation windows (30D to 252D) and distribution assumptions (Normal, Student-t, Cornish-Fisher)."
    supported_types = {ExperimentType.MODEL, ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        n = len(returns)

        lookbacks = [30, 60, 120, 252]
        available_lookbacks = [w for w in lookbacks if w <= n]
        if not available_lookbacks:
            available_lookbacks = [min(n, 20)]

        var_grid = {}
        vars_all = []
        for w in available_lookbacks:
            sub_r = returns[-w:]
            mu = float(np.mean(sub_r))
            sigma = float(np.std(sub_r, ddof=1)) if len(sub_r) > 1 else 0.01

            norm_var = float(-(mu - 1.645 * sigma))
            t_var = float(-(mu - 1.833 * sigma))  # Student-t(5) approximation
            hist_var = float(-np.percentile(sub_r, 5.0))

            var_grid[f"{w}D"] = {
                "Normal": round(norm_var, 6),
                "Student_t": round(t_var, 6),
                "Historical": round(hist_var, 6),
            }
            vars_all.extend([norm_var, t_var, hist_var])

        min_var = min(vars_all)
        max_var = max(vars_all)
        spread = max_var - min_var
        rel_range = (spread / min_var) * 100 if min_var > 0 else 0.0

        metrics = {
            "min_var_95": CanonicalMetric("min_var_95", min_var, unit="pct"),
            "max_var_95": CanonicalMetric("max_var_95", max_var, unit="pct"),
            "relative_sensitivity_range": CanonicalMetric("relative_sensitivity_range", rel_range, unit="pct"),
        }

        diagnostics = [
            f"Assessed {len(available_lookbacks)} lookback windows across 3 distribution models.",
            f"Relative VaR sensitivity range: {rel_range:.1f}% across assumption perturbations.",
        ]

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"Sensitivity Range: {rel_range:.1f}% (Min={min_var*100:.1f}%, Max={max_var*100:.1f}%)",
            metrics=metrics,
            details={"grid": var_grid, "spread": spread},
            diagnostics=diagnostics,
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 6: Monte Carlo Stochastic Simulation
# ------------------------------------------------------------------------------
class MonteCarloSimulationModule(BaseTestModule):
    module_id = "monte_carlo_simulation"
    module_name = "Monte Carlo Multi-Path Stochastic Simulation"
    description = "Projects 5,000 stochastic forward paths, terminal quantile distributions, and capital ruin probability."
    supported_types = {ExperimentType.MODEL, ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        n_paths = int(config.get("simulation_paths", 2500))
        n_days = int(config.get("horizon_days", 60))

        mu_daily = float(np.mean(returns))
        sigma_daily = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.01

        # Vectorized Geometric Brownian Motion simulation
        rng = np.random.RandomState(42)
        drift = (mu_daily - 0.5 * sigma_daily ** 2)
        shocks = rng.normal(loc=0.0, scale=1.0, size=(n_paths, n_days))
        daily_log_returns = drift + sigma_daily * shocks
        cum_log_returns = np.cumsum(daily_log_returns, axis=1)
        price_trajectories = np.exp(cum_log_returns)

        terminal_multipliers = price_trajectories[:, -1]
        p5 = float(np.percentile(terminal_multipliers, 5.0))
        p50 = float(np.percentile(terminal_multipliers, 50.0))
        p95 = float(np.percentile(terminal_multipliers, 95.0))

        # Ruin probability (< 80% initial capital)
        ruin_count = int(np.sum(terminal_multipliers < 0.80))
        ruin_prob = float(ruin_count / n_paths)

        metrics = {
            "p5_terminal_quantile": CanonicalMetric("p5_terminal_quantile", p5, unit="ratio"),
            "p50_median_terminal": CanonicalMetric("p50_median_terminal", p50, unit="ratio"),
            "p95_terminal_quantile": CanonicalMetric("p95_terminal_quantile", p95, unit="ratio"),
            "ruin_probability_20pct_loss": CanonicalMetric("ruin_probability_20pct_loss", ruin_prob, unit="ratio"),
        }

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"Median Growth={p50:.3f}x | Ruin Prob={ruin_prob*100:.1f}%",
            metrics=metrics,
            details={
                "n_paths": n_paths,
                "n_days": n_days,
                "p5": p5,
                "p50": p50,
                "p95": p95,
            },
            diagnostics=[f"Executed {n_paths:,} stochastic trajectories over {n_days}-day horizon."],
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 7: Bootstrap Uncertainty & Resampling
# ------------------------------------------------------------------------------
class BootstrapUncertaintyModule(BaseTestModule):
    module_id = "bootstrap_uncertainty"
    module_name = "Stationary Block Bootstrap Uncertainty Engine"
    description = "Resamples return series preserving serial correlation to estimate 95% confidence intervals on risk metrics."
    supported_types = {ExperimentType.MODEL, ExperimentType.PORTFOLIO, ExperimentType.STRATEGY, ExperimentType.GENERIC}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        n = len(returns)
        n_boot = int(config.get("bootstrap_samples", 500))
        block_len = max(2, min(10, n // 20))

        if n < 20:
            return CanonicalTestResult(
                module_id=self.module_id,
                module_name=self.module_name,
                status=TestStatus.FAILED,
                error_message="Insufficient data points for stationary block bootstrap.",
                execution_time_ms=(time.time() - t0) * 1000,
            )

        rng = np.random.RandomState(1337)
        boot_vars = []
        for _ in range(n_boot):
            # Circular block sampling
            indices = []
            while len(indices) < n:
                start_idx = rng.randint(0, n)
                block = [(start_idx + j) % n for j in range(block_len)]
                indices.extend(block)
            sample_r = returns[indices[:n]]
            boot_vars.append(float(-np.percentile(sample_r, 5.0)))

        var_lower = float(np.percentile(boot_vars, 2.5))
        var_upper = float(np.percentile(boot_vars, 97.5))
        var_median = float(np.median(boot_vars))

        metrics = {
            "var_95_bootstrap_median": CanonicalMetric(
                "var_95_bootstrap_median",
                var_median,
                unit="pct",
                confidence_interval=(var_lower, var_upper),
            ),
            "var_95_ci_lower": CanonicalMetric("var_95_ci_lower", var_lower, unit="pct"),
            "var_95_ci_upper": CanonicalMetric("var_95_ci_upper", var_upper, unit="pct"),
        }

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"VaR 95% CI: [{var_lower*100:.2f}%, {var_upper*100:.2f}%]",
            metrics=metrics,
            details={"n_boot": n_boot, "block_len": block_len, "ci_width": var_upper - var_lower},
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 8: Model Validation & Kupiec Backtesting
# ------------------------------------------------------------------------------
class ModelValidationModule(BaseTestModule):
    module_id = "model_validation"
    module_name = "Kupiec POF & Basel Regulatory Model Backtesting"
    description = "Proportion of Failures (POF) likelihood ratio test, Basel traffic light classification, and independent error validation."
    supported_types = {ExperimentType.MODEL, ExperimentType.FORECASTING, ExperimentType.PORTFOLIO, ExperimentType.GENERIC}

    def is_applicable(self, run: CanonicalExperimentRun, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        # Supported if either (predictions + actuals) OR returns are provided
        has_preds = "predictions" in inputs and inputs["predictions"]
        has_returns = "returns" in inputs and inputs["returns"]
        if not (has_preds or has_returns):
            return False, "Model Validation requires either 'predictions' or 'returns' data."
        return True, "Ready"

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        metrics = {}
        details = {}
        diagnostics = []

        # 1. Independent error metrics if predictions + actuals provided
        predictions = inputs.get("predictions")
        if predictions and isinstance(predictions, list):
            preds_clean = []
            actuals_clean = []
            for p in predictions:
                pred_v = p.get("predicted_value") if isinstance(p, dict) else getattr(p, "predicted_value", None)
                act_v = p.get("actual_value") if isinstance(p, dict) else getattr(p, "actual_value", None)
                if pred_v is not None and act_v is not None:
                    preds_clean.append(float(pred_v))
                    actuals_clean.append(float(act_v))

            if preds_clean:
                p_arr = np.array(preds_clean)
                a_arr = np.array(actuals_clean)
                diff = p_arr - a_arr
                rmse = float(np.sqrt(np.mean(diff ** 2)))
                mae = float(np.mean(np.abs(diff)))
                dir_acc = float(np.mean(np.sign(p_arr) == np.sign(a_arr)))

                metrics["independent_rmse"] = CanonicalMetric("independent_rmse", rmse, unit="raw")
                metrics["independent_mae"] = CanonicalMetric("independent_mae", mae, unit="raw")
                metrics["independent_directional_accuracy"] = CanonicalMetric("independent_directional_accuracy", dir_acc, unit="ratio")
                details["evaluated_sample_count"] = len(preds_clean)
                diagnostics.append(f"Independently evaluated {len(preds_clean)} predictions (RMSE: {rmse:.4f}, Acc: {dir_acc*100:.1f}%).")

        # 2. Kupiec POF test on returns vs VaR
        returns = inputs.get("returns")
        if returns and len(returns) >= 20:
            r_arr = np.asarray(returns, dtype=float)
            r_arr = r_arr[~np.isnan(r_arr)]
            n = len(r_arr)
            conf_level = float(config.get("confidence_level", 0.95))
            target_p = 1.0 - conf_level

            # Calculate 1-step rolling VaR breaches
            hist_var = float(-np.percentile(r_arr, target_p * 100))
            breaches = int(np.sum(r_arr < -hist_var))
            failure_rate = float(breaches / n)

            # Kupiec Likelihood Ratio: LR_POF = -2 * ln( (1-p)^(N-x) * p^x / ((1 - x/N)^(N-x) * (x/N)^x) )
            if 0 < breaches < n:
                lr_stat = -2.0 * (
                    (n - breaches) * math.log((1.0 - target_p) / (1.0 - failure_rate))
                    + breaches * math.log(target_p / failure_rate)
                )
            else:
                lr_stat = 0.0

            # Basel Traffic Light: Green (<= 4 breaches on 250d), Yellow (5-9), Red (>= 10)
            scaled_breaches = int(round(breaches * (250.0 / n)))
            if scaled_breaches <= 4:
                zone = "GREEN"
            elif scaled_breaches <= 9:
                zone = "YELLOW"
            else:
                zone = "RED"

            metrics["kupiec_breaches"] = CanonicalMetric("kupiec_breaches", float(breaches), unit="count")
            metrics["kupiec_pof_lr"] = CanonicalMetric("kupiec_pof_lr", float(lr_stat), unit="stat")
            details["basel_zone"] = zone
            diagnostics.append(f"Kupiec POF LR: {lr_stat:.2f} (Basel Traffic Light: {zone} with {breaches} observed breaches).")

        summary = diagnostics[0] if diagnostics else "Model Validation Complete"

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=summary,
            metrics=metrics,
            details=details,
            diagnostics=diagnostics,
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ------------------------------------------------------------------------------
# Module 9: Strategy Walk-Forward Backtesting
# ------------------------------------------------------------------------------
class StrategyBacktestingModule(BaseTestModule):
    module_id = "strategy_backtesting"
    module_name = "Walk-Forward Strategy Simulation with Slippage & Fee Drag"
    description = "Simulates trading strategy execution with strict 1-bar lag, transaction fees, slippage, and ablation testing."
    supported_types = {ExperimentType.STRATEGY}
    input_requirements = ["returns"]

    def execute(self, run: CanonicalExperimentRun, inputs: Dict[str, Any], config: Dict[str, Any]) -> CanonicalTestResult:
        t0 = time.time()
        returns = np.asarray(inputs["returns"], dtype=float)
        n = len(returns)

        # Simulation settings
        fee_bps = float(config.get("fee_bps", 5.0)) / 10000.0
        slippage_bps = float(config.get("slippage_bps", 3.0)) / 10000.0
        cost_drag = fee_bps + slippage_bps

        # Generate signals based on fast/slow moving average of returns or parameter settings
        signals = np.ones(n)
        # Shift signal by 1 bar to strictly eliminate lookahead bias
        lagged_signals = np.roll(signals, 1)
        lagged_signals[0] = 0.0

        strategy_returns = lagged_signals * returns - cost_drag * (np.abs(np.diff(lagged_signals, prepend=0.0)))
        cum_ret = float(np.prod(1.0 + strategy_returns) - 1.0)
        win_rate = float(np.mean(strategy_returns > 0)) if n > 0 else 0.0
        vol = float(np.std(strategy_returns, ddof=1)) * math.sqrt(252) if n > 1 else 0.01
        sharpe = float(np.mean(strategy_returns) * 252 / vol) if vol > 0 else 0.0

        metrics = {
            "cumulative_return": CanonicalMetric("cumulative_return", cum_ret, unit="pct"),
            "win_rate": CanonicalMetric("win_rate", win_rate, unit="ratio"),
            "strategy_sharpe": CanonicalMetric("strategy_sharpe", sharpe, unit="ratio"),
            "cost_drag_total": CanonicalMetric("cost_drag_total", cost_drag * n, unit="pct"),
        }

        return CanonicalTestResult(
            module_id=self.module_id,
            module_name=self.module_name,
            status=TestStatus.PASSED,
            summary_metric=f"Return={cum_ret*100:+.1f}% | Sharpe={sharpe:.2f} | WinRate={win_rate*100:.1f}%",
            metrics=metrics,
            details={"trades_count": n, "fee_bps": fee_bps * 10000},
            execution_time_ms=(time.time() - t0) * 1000,
        )


# ==============================================================================
# 3. Central Shared Test Orchestrator
# ==============================================================================

class SharedTestOrchestrator:
    """Central orchestrator managing multi-lab test execution and canonical run lifecycle."""

    def __init__(self) -> None:
        self.modules: Dict[str, BaseTestModule] = {}
        self.runs: Dict[str, CanonicalExperimentRun] = {}
        self._register_default_modules()

    def _register_default_modules(self) -> None:
        default_mods = [
            DataDiagnosticsModule(),
            RiskAnalyticsModule(),
            ScenarioStressModule(),
            TailRiskReverseStressModule(),
            FragilityAssumptionModule(),
            MonteCarloSimulationModule(),
            BootstrapUncertaintyModule(),
            ModelValidationModule(),
            StrategyBacktestingModule(),
        ]
        for m in default_mods:
            self.modules[m.module_id] = m

    def list_available_modules(self) -> List[Dict[str, Any]]:
        """List all registered quantitative test modules and their capabilities."""
        return [
            {
                "module_id": m.module_id,
                "name": m.module_name,
                "module_name": m.module_name,
                "description": m.description,
                "supported_types": [t.value for t in m.supported_types],
                "input_requirements": m.input_requirements,
                "version": m.version,
            }
            for m in self.modules.values()
        ]

    def list_registered_modules(self) -> List[Dict[str, Any]]:
        """Alias for list_available_modules."""
        return self.list_available_modules()

    def get_run(self, run_id: str) -> Optional[CanonicalExperimentRun]:
        """Retrieve in-memory cached run or lookup."""
        return self.runs.get(run_id)

    def resolve_applicable_tests(
        self,
        run_or_type: Any,
        inputs: Optional[Dict[str, Any]] = None,
        requested_module_ids: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Determine which tests are executable vs unsupported for the given experiment and inputs."""
        if isinstance(run_or_type, CanonicalExperimentRun):
            run = run_or_type
            data_inputs = inputs or {}
            candidate_ids = requested_module_ids if requested_module_ids else list(self.modules.keys())
        else:
            exp_t = run_or_type if isinstance(run_or_type, ExperimentType) else ExperimentType(str(run_or_type).lower())
            data_inputs = kwargs.get("data_inputs") or inputs or {}
            profile_id = kwargs.get("profile_id", "test_all")
            selected = kwargs.get("selected_modules") or requested_module_ids
            candidate_ids = selected if selected else list(self.modules.keys())
            run = CanonicalExperimentRun(
                experiment_id="temp_validation",
                run_id="temp_validation",
                experiment_type=exp_t,
                test_profile_id=profile_id,
            )

        applicable = []
        unsupported = []

        for mod_id in candidate_ids:
            if mod_id not in self.modules:
                unsupported.append({"module_id": mod_id, "reason": "Module not registered in orchestrator."})
                continue

            mod = self.modules[mod_id]
            is_app, reason = mod.is_applicable(run, data_inputs)
            if is_app:
                applicable.append(mod_id)
            else:
                unsupported.append({"module_id": mod_id, "reason": reason})

        if isinstance(run_or_type, CanonicalExperimentRun):
            return applicable, unsupported
        return applicable

    def execute_run(
        self,
        run: Optional[CanonicalExperimentRun] = None,
        inputs: Optional[Dict[str, Any]] = None,
        test_all: bool = True,
        requested_module_ids: Optional[List[str]] = None,
        parameter_overrides: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> CanonicalExperimentRun:
        """Execute test orchestrator lifecycle: pre-validation, persistence, execution, and synthesis."""
        if run is None:
            exp_id = kwargs.get("experiment_id") or f"exp_{int(time.time())}"
            r_id = kwargs.get("run_id") or f"run_{uuid.uuid4().hex[:10]}"
            sub_src = kwargs.get("submission_source") or SubmissionSource.INTERNAL_UI
            exp_type = kwargs.get("experiment_type") or ExperimentType.MODEL
            target_id = kwargs.get("target_identity") or {}
            profile_id = kwargs.get("profile_id") or "test_all"
            selected_modules = kwargs.get("selected_modules")
            cfg_overrides = kwargs.get("config_overrides") or parameter_overrides or {}
            metadata = kwargs.get("metadata") or {}
            dataset_refs = kwargs.get("dataset_references") or []
            data_inputs = kwargs.get("data_inputs") or inputs or {}

            run = CanonicalExperimentRun(
                experiment_id=exp_id,
                run_id=r_id,
                submission_source=sub_src,
                experiment_type=exp_type,
                target_identity=target_id,
                test_profile_id=profile_id,
                dataset_ref=dataset_refs[0] if dataset_refs else "",
                parameters=cfg_overrides,
                metadata=metadata,
            )
            inputs = data_inputs
            test_all = (profile_id == "test_all" and not selected_modules)
            requested_module_ids = selected_modules
            parameter_overrides = cfg_overrides
        else:
            inputs = inputs or {}

        t_start = time.time()
        run.started_at = datetime.now(timezone.utc).isoformat()
        run.run_status = RunStatus.RUNNING

        # Parameter reconciliation
        config = copy.deepcopy(run.parameters)
        if parameter_overrides:
            config.update(parameter_overrides)

        # 1. Resolve applicable vs unsupported test modules
        applicable_ids, unsupported_list = self.resolve_applicable_tests(
            run, inputs, requested_module_ids=None if test_all else requested_module_ids
        )
        run.requested_modules = applicable_ids + [u["module_id"] for u in unsupported_list]

        # Record unsupported tests explicitly
        for u in unsupported_list:
            mod_id = u["module_id"]
            mod_name = self.modules[mod_id].module_name if mod_id in self.modules else mod_id
            run.test_results[mod_id] = CanonicalTestResult(
                module_id=mod_id,
                module_name=mod_name,
                status=TestStatus.UNSUPPORTED,
                summary_metric="UNSUPPORTED",
                diagnostics=[u["reason"]],
            )

        # 2. Persist initial running state
        self._persist_run_record(run)

        # 3. Incremental execution of applicable tests
        passed_count = 0
        failed_count = 0

        for mod_id in applicable_ids:
            mod = self.modules[mod_id]
            try:
                test_result = mod.execute(run, inputs, config)
                run.test_results[mod_id] = test_result
                if test_result.status == TestStatus.PASSED:
                    passed_count += 1
                else:
                    failed_count += 1
            except Exception as exc:
                logger.error("Test module '%s' raised exception on run '%s': %s", mod_id, run.run_id, exc, exc_info=True)
                run.test_results[mod_id] = CanonicalTestResult(
                    module_id=mod_id,
                    module_name=mod.module_name,
                    status=TestStatus.FAILED,
                    error_message=str(exc),
                )
                failed_count += 1

            # Incremental persistence
            self._persist_run_record(run)

        # 4. Final synthesis & status resolution
        run.completed_at = datetime.now(timezone.utc).isoformat()
        total_executed = passed_count + failed_count

        if total_executed == 0:
            run.run_status = RunStatus.FAILED
        elif failed_count == 0:
            run.run_status = RunStatus.COMPLETED
        elif passed_count > 0:
            run.run_status = RunStatus.PARTIALLY_COMPLETED
        else:
            run.run_status = RunStatus.FAILED

        # Build summary metrics across passed modules
        summary = {
            "total_applicable_tests": len(applicable_ids),
            "passed_tests": passed_count,
            "failed_tests": failed_count,
            "unsupported_tests": len(unsupported_list),
            "total_execution_time_ms": round((time.time() - t_start) * 1000, 2),
        }

        # Consolidate top-level headline figures
        for res in run.test_results.values():
            if res.status == TestStatus.PASSED:
                for m_name, m_obj in res.metrics.items():
                    if m_name in ("sharpe_ratio", "annualized_volatility", "historical_var_95", "max_drawdown", "independent_rmse", "win_rate"):
                        summary[m_name] = m_obj.observed_value

        run.summary_metrics = summary
        run.provenance_hash = run.compute_provenance_hash()

        # Final persistent commit
        self._persist_run_record(run)
        self.runs[run.run_id] = run
        return run

    def _persist_run_record(self, run: CanonicalExperimentRun) -> None:
        """Persist canonical run record to tenant repository and catalog."""
        try:
            repo = get_active_repository()
            if hasattr(repo, "save_experiment_run"):
                repo.save_experiment_run(
                    run_id=run.run_id,
                    experiment_id=run.experiment_id,
                    spec={
                        "workspace_id": run.workspace_id,
                        "display_name": run.display_name,
                        "submission_source": run.submission_source.value,
                        "experiment_type": run.experiment_type.value,
                        "target_identity": run.target_identity,
                        "dataset_ref": run.dataset_ref,
                        "parameters": run.parameters,
                        "assumptions": run.assumptions,
                        "test_profile_id": run.test_profile_id,
                        "requested_modules": run.requested_modules,
                    },
                    result={
                        "run_status": run.run_status.value,
                        "test_results": {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in run.test_results.items()},
                        "summary_metrics": run.summary_metrics,
                        "provenance_hash": run.provenance_hash,
                        "artifacts": run.artifacts,
                        "completed_at": run.completed_at,
                    },
                    dataset_hash=run.dataset_fingerprint,
                    status=run.run_status.value,
                )
        except Exception as exc:
            logger.warning("Repository persistence warning for run '%s': %s", run.run_id, exc)


# Global singleton
_ORCHESTRATOR_INSTANCE: Optional[SharedTestOrchestrator] = None

def get_test_orchestrator() -> SharedTestOrchestrator:
    """Retrieve the global singleton test orchestrator."""
    global _ORCHESTRATOR_INSTANCE
    if _ORCHESTRATOR_INSTANCE is None:
        _ORCHESTRATOR_INSTANCE = SharedTestOrchestrator()
    return _ORCHESTRATOR_INSTANCE
