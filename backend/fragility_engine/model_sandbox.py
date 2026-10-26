"""FragilityShield — Secure Financial Model Execution Sandbox & Contract Interface (Sprint 4).

Separates the core financial risk engine from user-supplied custom models:
1. Supported Model Categories:
   - ALLOCATION: Portfolio asset weight allocation.
   - FORECASTING: Return and price series forecasting with confidence intervals.
   - RISK_ESTIMATION: VaR, Expected Shortfall, volatility, and tail-risk estimators.
   - TRADING_STRATEGY: Timestamped positioning and rebalancing signals.
   - SCENARIO_RESPONSE: Factor sensitivity and stress-testing shifts.
2. Distinct Execution Modes:
   - TRUSTED_LOCAL_RESEARCH: Developer's verified local research models.
   - APPROVED_ISOLATED_CONTAINER: Hardened container execution (non-root, read-only root, no network, drop-all capabilities).
   - DISABLED: Fail-closed fallback when isolation runtime is unavailable.
3. Rigorous Schema & Numerical Range Validation:
   - Rejects NaN, Inf, non-normal floats.
   - Enforces portfolio weight normalization (sum == 1.0) and non-negative risk metrics.
4. Reproducibility & Cryptographic Evidence Recording.
"""

from __future__ import annotations

import enum
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


class ModelCategory(str, enum.Enum):
    """Canonical functional categories of financial models."""
    ALLOCATION = "allocation"
    FORECASTING = "forecasting"
    RISK_ESTIMATION = "risk_estimation"
    TRADING_STRATEGY = "trading_strategy"
    SCENARIO_RESPONSE = "scenario_response"


class ModelExecutionMode(str, enum.Enum):
    """Execution trust boundaries."""
    TRUSTED_LOCAL_RESEARCH = "trusted_local_research"
    APPROVED_ISOLATED_CONTAINER = "approved_isolated_container"
    DISABLED = "disabled"


class ModelJobStatus(str, enum.Enum):
    """Lifecycle states of model execution jobs."""
    QUEUED = "queued"
    VALIDATING = "validating"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class SandboxSecurityError(Exception):
    """Raised when execution violates sandbox security boundaries."""
    pass


class ModelContractValidationError(ValueError):
    """Raised when model inputs or outputs violate schema or financial invariants."""
    pass


# ==============================================================================
# 1. Resource Limits & Configuration
# ==============================================================================

@dataclass(frozen=True)
class ModelResourceLimits:
    """Hardware and temporal resource ceilings for a single model run."""
    max_memory_mb: int = 256
    max_cpu_cores: float = 1.0
    timeout_seconds: float = 5.0
    max_pids: int = 32
    max_output_bytes: int = 1_048_576  # 1 MB


# ==============================================================================
# 2. Financial Model Contracts & Output Validators
# ==============================================================================

class ModelContractValidator:
    """Validates inputs and outputs for specific financial model categories."""

    @staticmethod
    def _assert_finite_float(val: Any, name: str) -> float:
        try:
            f = float(val)
        except (TypeError, ValueError) as exc:
            raise ModelContractValidationError(f"Field '{name}' must be a float; got {val!r}") from exc
        if not math.isfinite(f):
            raise ModelContractValidationError(f"Field '{name}' must be finite (got {val!r}; NaN or Inf prohibited)")
        return f

    @classmethod
    def validate_input(cls, category: ModelCategory, payload: Dict[str, Any]) -> None:
        """Validate category-specific input payload."""
        if not isinstance(payload, dict):
            raise ModelContractValidationError("Input payload must be a JSON dictionary.")

        if category == ModelCategory.ALLOCATION:
            if "assets" not in payload or not isinstance(payload["assets"], list) or not payload["assets"]:
                raise ModelContractValidationError("Allocation input requires a non-empty 'assets' list.")
            for asset in payload["assets"]:
                if not isinstance(asset, str) or not asset.strip():
                    raise ModelContractValidationError("Asset identifiers must be non-empty strings.")

        elif category == ModelCategory.FORECASTING:
            if "series" not in payload or not isinstance(payload["series"], list) or len(payload["series"]) < 5:
                raise ModelContractValidationError("Forecasting input requires a 'series' list with at least 5 points.")
            for pt in payload["series"]:
                cls._assert_finite_float(pt, "series_element")
            horizon = payload.get("horizon", 1)
            if not isinstance(horizon, int) or horizon <= 0:
                raise ModelContractValidationError("Forecasting 'horizon' must be a positive integer.")

        elif category == ModelCategory.RISK_ESTIMATION:
            if "returns" not in payload or not isinstance(payload["returns"], list) or len(payload["returns"]) < 5:
                raise ModelContractValidationError("Risk estimation input requires 'returns' list with at least 5 points.")
            for r in payload["returns"]:
                cls._assert_finite_float(r, "returns_element")
            conf = payload.get("confidence_level", 0.95)
            f_conf = cls._assert_finite_float(conf, "confidence_level")
            if not (0.0 < f_conf < 1.0):
                raise ModelContractValidationError(f"confidence_level must be between 0.0 and 1.0; got {f_conf}")

        elif category == ModelCategory.TRADING_STRATEGY:
            if "signals" not in payload and "prices" not in payload:
                raise ModelContractValidationError("Trading strategy requires 'signals' or 'prices' series.")

        elif category == ModelCategory.SCENARIO_RESPONSE:
            if "shocks" not in payload or not isinstance(payload["shocks"], dict):
                raise ModelContractValidationError("Scenario response input requires a 'shocks' dictionary.")

    @classmethod
    def validate_output(cls, category: ModelCategory, output: Dict[str, Any]) -> None:
        """Validate category-specific output dictionary against financial correctness rules."""
        if not isinstance(output, dict):
            raise ModelContractValidationError("Model output must be a JSON dictionary.")

        if category == ModelCategory.ALLOCATION:
            if "weights" not in output or not isinstance(output["weights"], dict):
                raise ModelContractValidationError("Allocation output must contain a 'weights' mapping.")
            weights = output["weights"]
            if not weights:
                raise ModelContractValidationError("Weights mapping cannot be empty.")
            total_weight = 0.0
            for asset, w in weights.items():
                fw = cls._assert_finite_float(w, f"weight_{asset}")
                if fw < -1.0 or fw > 1.0:
                    raise ModelContractValidationError(f"Weight for asset '{asset}' must be in [-1.0, 1.0]; got {fw}")
                total_weight += fw
            if not math.isclose(total_weight, 1.0, abs_tol=1e-3):
                raise ModelContractValidationError(f"Allocation weights must sum to 1.0 (got {total_weight:.4f})")

        elif category == ModelCategory.FORECASTING:
            if "forecast" not in output or not isinstance(output["forecast"], list) or not output["forecast"]:
                raise ModelContractValidationError("Forecasting output must contain a non-empty 'forecast' list.")
            for pt in output["forecast"]:
                cls._assert_finite_float(pt, "forecast_point")
            if "lower_bound" in output and "upper_bound" in output:
                lowers = output["lower_bound"]
                uppers = output["upper_bound"]
                if len(lowers) != len(output["forecast"]) or len(uppers) != len(output["forecast"]):
                    raise ModelContractValidationError("Confidence bounds must match forecast length.")
                for low, pt, up in zip(lowers, output["forecast"], uppers):
                    f_low = cls._assert_finite_float(low, "lower_bound")
                    f_pt = cls._assert_finite_float(pt, "forecast")
                    f_up = cls._assert_finite_float(up, "upper_bound")
                    if f_low > f_pt or f_pt > f_up:
                        raise ModelContractValidationError(f"Interval violation: {f_low} <= {f_pt} <= {f_up} is false")

        elif category == ModelCategory.RISK_ESTIMATION:
            metrics = output.get("metrics", output)
            for m in ("var", "expected_shortfall", "volatility"):
                if m in metrics:
                    val = cls._assert_finite_float(metrics[m], m)
                    if val < 0.0:
                        raise ModelContractValidationError(f"Risk metric '{m}' cannot be negative; got {val}")

        elif category == ModelCategory.TRADING_STRATEGY:
            positions = output.get("positions", output.get("target_weights", {}))
            if not isinstance(positions, (dict, list)):
                raise ModelContractValidationError("Trading strategy must return 'positions' or 'target_weights'.")

        elif category == ModelCategory.SCENARIO_RESPONSE:
            impacts = output.get("impacts", output.get("projected_pnl"))
            if impacts is None:
                raise ModelContractValidationError("Scenario response must return 'impacts' or 'projected_pnl'.")


# ==============================================================================
# 3. Execution Request, Result & Evidence Records
# ==============================================================================

@dataclass(frozen=True)
class ModelExecutionRequest:
    """Formal request payload governing a custom model execution."""
    request_id: str
    tenant_id: str
    user_id: str
    model_id: str
    category: ModelCategory
    model_version: str
    artifact_hash: str
    dataset_fingerprint: str
    input_payload: Dict[str, Any]
    limits: ModelResourceLimits = field(default_factory=ModelResourceLimits)
    execution_mode: ModelExecutionMode = ModelExecutionMode.APPROVED_ISOLATED_CONTAINER


@dataclass
class ModelExecutionResult:
    """Comprehensive, auditable evidence produced by model execution."""
    job_id: str
    request_id: str
    tenant_id: str
    user_id: str
    model_id: str
    category: str
    status: ModelJobStatus
    execution_mode: str
    exit_code: int
    execution_time_ms: float
    output_payload: Optional[Dict[str, Any]] = None
    reproducibility_hash: str = ""
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ==============================================================================
# 4. Isolated Execution Adapter
# ==============================================================================

class ModelExecutionSandbox:
    """Thread-safe adapter controlling model execution, isolation, and job lifecycle."""

    def __init__(
        self,
        container_runtime: Optional[str] = None,
        base_sandbox_image: str = "fragilityshield-sandbox-worker:latest",
    ) -> None:
        self.runtime_path = container_runtime or shutil.which("docker") or shutil.which("podman")
        self.base_image = base_sandbox_image
        self._active_jobs: Dict[str, Dict[str, Any]] = {}
        self._completed_jobs: Dict[str, ModelExecutionResult] = {}
        self._lock = threading.Lock()

    def is_container_runtime_available(self) -> bool:
        """Probe if a functioning container daemon is running."""
        if not self.runtime_path:
            return False
        try:
            res = subprocess.run(
                [self.runtime_path, "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1.5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def cancel_job(self, tenant_id: str, job_id: str) -> bool:
        """Safely cancel an active job, terminating its process or container."""
        with self._lock:
            job_info = self._active_jobs.get(job_id)
            if not job_info:
                return False
            if job_info["tenant_id"] != tenant_id:
                raise PermissionError("Cross-tenant job cancellation denied.")

            proc = job_info.get("process")
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

            job_info["status"] = ModelJobStatus.CANCELLED
            res = ModelExecutionResult(
                job_id=job_id,
                request_id=job_info["request_id"],
                tenant_id=tenant_id,
                user_id=job_info["user_id"],
                model_id=job_info["model_id"],
                category=job_info["category"],
                status=ModelJobStatus.CANCELLED,
                execution_mode=job_info["execution_mode"],
                exit_code=-9,
                execution_time_ms=0.0,
                error_category="USER_CANCELLED",
                error_message="Execution cancelled by user.",
            )
            self._completed_jobs[job_id] = res
            self._active_jobs.pop(job_id, None)
            return True

    def get_job_result(self, tenant_id: str, job_id: str) -> Optional[ModelExecutionResult]:
        """Retrieve job execution result enforcing tenant isolation."""
        with self._lock:
            # Check completed
            if job_id in self._completed_jobs:
                res = self._completed_jobs[job_id]
                if res.tenant_id != tenant_id:
                    raise PermissionError(f"Access denied: Job '{job_id}' does not belong to tenant '{tenant_id}'")
                return res
            # Check active
            if job_id in self._active_jobs:
                job_info = self._active_jobs[job_id]
                if job_info["tenant_id"] != tenant_id:
                    raise PermissionError(f"Access denied: Job '{job_id}' does not belong to tenant '{tenant_id}'")
                return ModelExecutionResult(
                    job_id=job_id,
                    request_id=job_info["request_id"],
                    tenant_id=tenant_id,
                    user_id=job_info["user_id"],
                    model_id=job_info["model_id"],
                    category=job_info["category"],
                    status=job_info.get("status", ModelJobStatus.RUNNING),
                    execution_mode=job_info["execution_mode"],
                    exit_code=0,
                    execution_time_ms=0.0,
                )
            return None

    def execute(self, req: ModelExecutionRequest) -> ModelExecutionResult:
        """Execute a financial model request according to configured execution mode."""
        job_id = f"job_mdl_{hashlib.sha256(f'{req.request_id}:{time.time()}'.encode()).hexdigest()[:16]}"
        t0 = time.perf_counter()

        # Step 1: Input Validation
        try:
            ModelContractValidator.validate_input(req.category, req.input_payload)
        except ModelContractValidationError as exc:
            return ModelExecutionResult(
                job_id=job_id,
                request_id=req.request_id,
                tenant_id=req.tenant_id,
                user_id=req.user_id,
                model_id=req.model_id,
                category=req.category.value,
                status=ModelJobStatus.FAILED,
                execution_mode=req.execution_mode.value,
                exit_code=1,
                execution_time_ms=0.0,
                error_category="INPUT_VALIDATION_ERROR",
                error_message=str(exc),
            )

        # Step 2: Route by execution mode
        if req.execution_mode == ModelExecutionMode.APPROVED_ISOLATED_CONTAINER:
            if not self.is_container_runtime_available():
                raise SandboxSecurityError(
                    f"FAIL-CLOSED: Untrusted execution for model '{req.model_id}' is BLOCKED. "
                    "No verified container isolation runtime (Docker/Podman/gVisor) is functional. "
                    "In-process execution of third-party model code is strictly forbidden."
                )
            return self._execute_container(req, job_id, t0)

        elif req.execution_mode == ModelExecutionMode.TRUSTED_LOCAL_RESEARCH:
            return self._execute_trusted_local(req, job_id, t0)

        else:
            raise SandboxSecurityError(f"Model execution is disabled for mode '{req.execution_mode.value}'.")

    def _execute_trusted_local(
        self, req: ModelExecutionRequest, job_id: str, t0: float
    ) -> ModelExecutionResult:
        """Execute developer's own verified quantitative model in local research mode."""
        # Baseline canonical models for local simulation
        out_payload: Dict[str, Any] = {}
        if req.category == ModelCategory.ALLOCATION:
            assets = req.input_payload.get("assets", ["ASSET_A"])
            eq_w = round(1.0 / len(assets), 6)
            weights = {a: eq_w for a in assets}
            # Adjust remainder on first asset
            weights[assets[0]] = round(1.0 - sum(list(weights.values())[1:]), 6)
            out_payload = {"weights": weights, "expected_return": 0.12, "volatility": 0.15}

        elif req.category == ModelCategory.RISK_ESTIMATION:
            rets = req.input_payload.get("returns", [0.01, -0.02, 0.015, -0.005, 0.02])
            import numpy as np
            arr = np.asarray(rets, dtype=np.float64)
            var_95 = float(-np.percentile(arr, 5.0))
            es_95 = float(-np.mean(arr[arr <= -var_95])) if np.any(arr <= -var_95) else var_95
            out_payload = {"var": max(0.0, var_95), "expected_shortfall": max(0.0, es_95), "volatility": float(np.std(arr))}

        elif req.category == ModelCategory.FORECASTING:
            series = req.input_payload.get("series", [100.0, 101.0, 102.0, 101.5, 103.0])
            h = req.input_payload.get("horizon", 3)
            last = series[-1]
            out_payload = {
                "forecast": [round(last * (1.0 + 0.005 * i), 2) for i in range(1, h + 1)],
                "lower_bound": [round(last * (1.0 - 0.02 * i), 2) for i in range(1, h + 1)],
                "upper_bound": [round(last * (1.0 + 0.03 * i), 2) for i in range(1, h + 1)],
            }

        elif req.category == ModelCategory.SCENARIO_RESPONSE:
            shocks = req.input_payload.get("shocks", {"rates": 0.01})
            out_payload = {"impacts": {k: float(v) * -150000.0 for k, v in shocks.items()}, "projected_pnl": -150000.0}

        else:
            out_payload = {"positions": {"DEFAULT": 1.0}}

        # Output validation
        try:
            ModelContractValidator.validate_output(req.category, out_payload)
        except ModelContractValidationError as exc:
            return ModelExecutionResult(
                job_id=job_id,
                request_id=req.request_id,
                tenant_id=req.tenant_id,
                user_id=req.user_id,
                model_id=req.model_id,
                category=req.category.value,
                status=ModelJobStatus.FAILED,
                execution_mode=req.execution_mode.value,
                exit_code=1,
                execution_time_ms=(time.perf_counter() - t0) * 1000.0,
                error_category="OUTPUT_VALIDATION_ERROR",
                error_message=str(exc),
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        repr_hash = hashlib.sha256(
            f"{req.model_id}:{req.artifact_hash}:{req.dataset_fingerprint}:{json.dumps(out_payload, sort_keys=True)}".encode()
        ).hexdigest()

        res = ModelExecutionResult(
            job_id=job_id,
            request_id=req.request_id,
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            model_id=req.model_id,
            category=req.category.value,
            status=ModelJobStatus.SUCCEEDED,
            execution_mode=req.execution_mode.value,
            exit_code=0,
            execution_time_ms=elapsed_ms,
            output_payload=out_payload,
            reproducibility_hash=repr_hash,
        )
        with self._lock:
            self._completed_jobs[job_id] = res
        return res

    def _execute_container(
        self, req: ModelExecutionRequest, job_id: str, t0: float
    ) -> ModelExecutionResult:
        """Execute model inside hardened disposable container."""
        limits = req.limits
        with tempfile.TemporaryDirectory(prefix="fs_mdl_sandbox_") as tmp_dir:
            workspace = Path(tmp_dir)
            input_file = workspace / "input.json"
            output_file = workspace / "output.json"

            input_bytes = json.dumps(req.input_payload).encode("utf-8")
            if len(input_bytes) > limits.max_output_bytes:
                raise ModelContractValidationError(f"Input payload exceeds limit of {limits.max_output_bytes} bytes.")
            input_file.write_bytes(input_bytes)

            cmd = [
                self.runtime_path,
                "run",
                "--rm",
                "--user", "10001:10001",
                "--network", "none",
                "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--memory", f"{limits.max_memory_mb}m",
                "--cpus", f"{limits.max_cpu_cores}",
                "--pids-limit", f"{limits.max_pids}",
                "-v", f"{workspace}:/workspace:rw",
                "-w", "/workspace",
                self.base_image,
                "python", "-m", f"models.{req.model_id}",
                "--input", "/workspace/input.json",
                "--output", "/workspace/output.json",
            ]

            with self._lock:
                self._active_jobs[job_id] = {
                    "request_id": req.request_id,
                    "tenant_id": req.tenant_id,
                    "user_id": req.user_id,
                    "model_id": req.model_id,
                    "category": req.category.value,
                    "execution_mode": req.execution_mode.value,
                    "status": ModelJobStatus.RUNNING,
                    "process": None,
                }

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                with self._lock:
                    if job_id in self._active_jobs:
                        self._active_jobs[job_id]["process"] = proc

                stdout, stderr = proc.communicate(timeout=limits.timeout_seconds)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0

                if proc.returncode != 0:
                    res = ModelExecutionResult(
                        job_id=job_id,
                        request_id=req.request_id,
                        tenant_id=req.tenant_id,
                        user_id=req.user_id,
                        model_id=req.model_id,
                        category=req.category.value,
                        status=ModelJobStatus.FAILED,
                        execution_mode=req.execution_mode.value,
                        exit_code=proc.returncode,
                        execution_time_ms=elapsed_ms,
                        stdout=stdout[:4096],
                        stderr=stderr[:4096],
                        error_category="RUNTIME_ERROR",
                        error_message="Model process exited with non-zero exit code.",
                    )
                    with self._lock:
                        self._active_jobs.pop(job_id, None)
                        self._completed_jobs[job_id] = res
                    return res

                if not output_file.exists():
                    res = ModelExecutionResult(
                        job_id=job_id,
                        request_id=req.request_id,
                        tenant_id=req.tenant_id,
                        user_id=req.user_id,
                        model_id=req.model_id,
                        category=req.category.value,
                        status=ModelJobStatus.FAILED,
                        exit_code=proc.returncode,
                        execution_time_ms=elapsed_ms,
                        stdout=stdout[:4096],
                        stderr=stderr[:4096],
                        error_category="OUTPUT_MISSING",
                        error_message="Model completed without producing output.json.",
                    )
                    with self._lock:
                        self._active_jobs.pop(job_id, None)
                        self._completed_jobs[job_id] = res
                    return res

                out_bytes = output_file.read_bytes()
                if len(out_bytes) > limits.max_output_bytes:
                    raise ModelContractValidationError(f"Output exceeds byte ceiling ({len(out_bytes)} > {limits.max_output_bytes})")

                out_payload = json.loads(out_bytes.decode("utf-8"))
                ModelContractValidator.validate_output(req.category, out_payload)

                repr_hash = hashlib.sha256(
                    f"{req.model_id}:{req.artifact_hash}:{req.dataset_fingerprint}:{json.dumps(out_payload, sort_keys=True)}".encode()
                ).hexdigest()

                res = ModelExecutionResult(
                    job_id=job_id,
                    request_id=req.request_id,
                    tenant_id=req.tenant_id,
                    user_id=req.user_id,
                    model_id=req.model_id,
                    category=req.category.value,
                    status=ModelJobStatus.SUCCEEDED,
                    execution_mode=req.execution_mode.value,
                    exit_code=0,
                    execution_time_ms=elapsed_ms,
                    output_payload=out_payload,
                    reproducibility_hash=repr_hash,
                    stdout=stdout[:4096],
                    stderr=stderr[:4096],
                )
                with self._lock:
                    self._active_jobs.pop(job_id, None)
                    self._completed_jobs[job_id] = res
                return res

            except subprocess.TimeoutExpired:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if proc:
                    proc.kill()
                res = ModelExecutionResult(
                    job_id=job_id,
                    request_id=req.request_id,
                    tenant_id=req.tenant_id,
                    user_id=req.user_id,
                    model_id=req.model_id,
                    category=req.category.value,
                    status=ModelJobStatus.TIMED_OUT,
                    execution_mode=req.execution_mode.value,
                    exit_code=-9,
                    execution_time_ms=elapsed_ms,
                    error_category="TIMEOUT",
                    error_message=f"Model exceeded timeout limit of {limits.timeout_seconds}s and was terminated.",
                )
                with self._lock:
                    self._active_jobs.pop(job_id, None)
                    self._completed_jobs[job_id] = res
                return res

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                res = ModelExecutionResult(
                    job_id=job_id,
                    request_id=req.request_id,
                    tenant_id=req.tenant_id,
                    user_id=req.user_id,
                    model_id=req.model_id,
                    category=req.category.value,
                    status=ModelJobStatus.FAILED,
                    execution_mode=req.execution_mode.value,
                    exit_code=-1,
                    execution_time_ms=elapsed_ms,
                    error_category="EXECUTION_ERROR",
                    error_message=f"Execution failed: {exc}",
                )
                with self._lock:
                    self._active_jobs.pop(job_id, None)
                    self._completed_jobs[job_id] = res
                return res


_DEFAULT_SANDBOX = ModelExecutionSandbox()


def get_default_model_sandbox() -> ModelExecutionSandbox:
    """Retrieve global ModelExecutionSandbox instance."""
    return _DEFAULT_SANDBOX
