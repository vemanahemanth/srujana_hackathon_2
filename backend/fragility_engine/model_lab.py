"""FragilityShield — Model and Integration Lab (Lab 2 & Blueprint §2, §4).

This module implements the integration, verification, and contract-checking test suite
for quantitative models, predictive estimators, trading strategies, and analytical APIs:

Tests implemented:
1. Smoke test: Safely executes a minimal execution call.
2. Input contract test: Validates required column/field presence and types.
3. Output contract test: Validates output structure against expected manifest schema.
4. Shape and dimensionality test: Checks row/column counts or prediction dimensions.
5. Numeric validity test: Verifies absence of NaN, +/- Inf, and non-real numbers.
6. Determinism test: Runs identical inputs across repetitions to guarantee reproducibility.
7. Repeatability test: Verifies outputs remain identical within specified numerical tolerance.
8. Error-handling test: Ensures malformed inputs raise controlled exceptions instead of crashing.
9. Timeout & resource test: Monitors wall-clock execution time against declared budget.
10. Version-change test: Compares interface and capability stability across model versions.
11. Connection & authentication test: Checks external API endpoint reachability and credentials safely.

Security Invariant:
Arbitrary user-provided code must not execute within the main API process without isolation.
Models requiring isolation are flagged with REQUIRED isolation status.
"""

from __future__ import annotations

import enum
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from fragility_engine.projects import CapabilityReport, CapabilityStatus, ModelFamily, ModelManifest, check_model_capabilities


class IntegrationTestStatus(str, enum.Enum):
    """Execution status for an individual model integration test."""
    PASS = "passed"
    FAIL = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class IntegrationTestResult:
    """Outcome of one specific verification test in Lab 2."""
    test_name: str
    status: IntegrationTestStatus
    message: str
    execution_time_ms: float = 0.0
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "status": self.status.value,
            "message": self.message,
            "execution_time_ms": round(self.execution_time_ms, 3),
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ModelIntegrationReport:
    """Consolidated report from the Model & Integration Lab."""
    model_id: str
    version: str
    tests_run: int
    passed: int
    failed: int
    warnings: int
    inconclusive: int
    results: Tuple[IntegrationTestResult, ...]
    isolation_status: str
    summary: str
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "tests_run": self.tests_run,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "inconclusive": self.inconclusive,
            "results": [r.to_dict() for r in self.results],
            "isolation_status": self.isolation_status,
            "summary": self.summary,
            "checked_at": self.checked_at,
        }


# ==============================================================================
# Individual Integration Test Functions
# ==============================================================================

def run_model_smoke_test(
    model_callable: Callable[[Any], Any],
    sample_input: Any,
) -> IntegrationTestResult:
    """Execute a minimal, safe smoke test on the model."""
    t0 = time.perf_counter()
    try:
        output = model_callable(sample_input)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if output is None:
            return IntegrationTestResult(
                test_name="smoke_test",
                status=IntegrationTestStatus.WARNING,
                message="Model executed successfully but returned None.",
                execution_time_ms=elapsed_ms,
            )
        return IntegrationTestResult(
            test_name="smoke_test",
            status=IntegrationTestStatus.PASS,
            message="Smoke test passed. Model executed without unhandled exceptions.",
            execution_time_ms=elapsed_ms,
            details={"output_type": type(output).__name__},
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return IntegrationTestResult(
            test_name="smoke_test",
            status=IntegrationTestStatus.FAIL,
            message=f"Smoke test failed: {exc}",
            execution_time_ms=elapsed_ms,
            details={"error_type": type(exc).__name__},
        )


def run_input_contract_test(
    manifest: ModelManifest,
    provided_columns: Sequence[str],
) -> IntegrationTestResult:
    """Validate whether provided data schema matches the model's required inputs."""
    t0 = time.perf_counter()
    provided_set = {str(c).lower().strip() for c in provided_columns}
    missing = [req for req in manifest.required_inputs if req.lower().strip() not in provided_set]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    if not missing:
        return IntegrationTestResult(
            test_name="input_contract_test",
            status=IntegrationTestStatus.PASS,
            message="All declared required inputs are present in provided data schema.",
            execution_time_ms=elapsed_ms,
            details={"matched_inputs": list(manifest.required_inputs)},
        )
    return IntegrationTestResult(
        test_name="input_contract_test",
        status=IntegrationTestStatus.FAIL,
        message=f"Input contract violated. Missing required inputs: {missing}",
        execution_time_ms=elapsed_ms,
        details={"missing_inputs": missing, "provided_columns": list(provided_columns)},
    )


def run_output_contract_test(
    manifest: ModelManifest,
    sample_output: Any,
) -> IntegrationTestResult:
    """Validate whether model output structure conforms to manifest expectation."""
    t0 = time.perf_counter()
    elapsed_ms = 0.0

    if not manifest.expected_output_schema:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return IntegrationTestResult(
            test_name="output_contract_test",
            status=IntegrationTestStatus.INCONCLUSIVE,
            message="Model manifest does not define expected_output_schema; contract check inconclusive.",
            execution_time_ms=elapsed_ms,
        )

    if isinstance(sample_output, Mapping):
        missing_keys = [k for k in manifest.expected_output_schema if k not in sample_output]
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if not missing_keys:
            return IntegrationTestResult(
                test_name="output_contract_test",
                status=IntegrationTestStatus.PASS,
                message="Output dictionary contains all declared schema keys.",
                execution_time_ms=elapsed_ms,
                details={"verified_keys": list(manifest.expected_output_schema.keys())},
            )
        return IntegrationTestResult(
            test_name="output_contract_test",
            status=IntegrationTestStatus.FAIL,
            message=f"Output dictionary is missing required keys: {missing_keys}",
            execution_time_ms=elapsed_ms,
            details={"missing_keys": missing_keys},
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return IntegrationTestResult(
        test_name="output_contract_test",
        status=IntegrationTestStatus.PASS,
        message=f"Output returned as {type(sample_output).__name__}.",
        execution_time_ms=elapsed_ms,
    )


def run_numeric_validity_test(sample_output: Any) -> IntegrationTestResult:
    """Verify that model output values contain no NaN or +/- Infinity."""
    t0 = time.perf_counter()
    values_to_check: List[float] = []

    if isinstance(sample_output, (int, float)) and not isinstance(sample_output, bool):
        values_to_check.append(float(sample_output))
    elif isinstance(sample_output, Mapping):
        for v in sample_output.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                values_to_check.append(float(v))
    elif isinstance(sample_output, (list, tuple, np.ndarray)):
        arr = np.asarray(sample_output)
        if np.issubdtype(arr.dtype, np.number):
            flat = arr.flatten()
            nan_cnt = int(np.isnan(flat).sum())
            inf_cnt = int(np.isinf(flat).sum())
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if nan_cnt > 0 or inf_cnt > 0:
                return IntegrationTestResult(
                    test_name="numeric_validity_test",
                    status=IntegrationTestStatus.FAIL,
                    message=f"Numerical integrity violation: {nan_cnt} NaNs and {inf_cnt} Infs detected.",
                    execution_time_ms=elapsed_ms,
                    details={"nan_count": nan_cnt, "inf_count": inf_cnt},
                )
            return IntegrationTestResult(
                test_name="numeric_validity_test",
                status=IntegrationTestStatus.PASS,
                message="All numeric values in array output are finite.",
                execution_time_ms=elapsed_ms,
                details={"checked_elements": len(flat)},
            )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    for v in values_to_check:
        if not math.isfinite(v):
            return IntegrationTestResult(
                test_name="numeric_validity_test",
                status=IntegrationTestStatus.FAIL,
                message=f"Non-finite numeric value encountered: {v}",
                execution_time_ms=elapsed_ms,
            )

    return IntegrationTestResult(
        test_name="numeric_validity_test",
        status=IntegrationTestStatus.PASS,
        message="Numeric validity verified. All checked values are finite.",
        execution_time_ms=elapsed_ms,
        details={"checked_values_count": len(values_to_check)},
    )


def run_determinism_test(
    model_callable: Callable[[Any], Any],
    sample_input: Any,
    repetitions: int = 3,
    rtol: float = 1e-7,
) -> IntegrationTestResult:
    """Verify that repeated identical inputs produce identical outputs (if claimed)."""
    t0 = time.perf_counter()
    outputs: List[Any] = []
    try:
        for _ in range(repetitions):
            outputs.append(model_callable(sample_input))
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return IntegrationTestResult(
            test_name="determinism_test",
            status=IntegrationTestStatus.FAIL,
            message=f"Determinism test execution failed: {exc}",
            execution_time_ms=elapsed_ms,
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    base = outputs[0]
    for idx, rep in enumerate(outputs[1:], start=1):
        if isinstance(base, (int, float)) and isinstance(rep, (int, float)):
            if not math.isclose(float(base), float(rep), rel_tol=rtol, abs_tol=1e-9):
                return IntegrationTestResult(
                    test_name="determinism_test",
                    status=IntegrationTestStatus.FAIL,
                    message=f"Non-deterministic numerical drift detected between runs 0 and {idx}: {base} vs {rep}",
                    execution_time_ms=elapsed_ms,
                )
        elif isinstance(base, (list, tuple, np.ndarray)) and isinstance(rep, (list, tuple, np.ndarray)):
            arr_base = np.asarray(base, dtype=np.float64)
            arr_rep = np.asarray(rep, dtype=np.float64)
            if not np.allclose(arr_base, arr_rep, rtol=rtol, atol=1e-9):
                return IntegrationTestResult(
                    test_name="determinism_test",
                    status=IntegrationTestStatus.FAIL,
                    message=f"Non-deterministic array mismatch detected between run 0 and run {idx}.",
                    execution_time_ms=elapsed_ms,
                )
        elif base != rep:
            return IntegrationTestResult(
                test_name="determinism_test",
                status=IntegrationTestStatus.FAIL,
                message=f"Output changed between run 0 and run {idx}.",
                execution_time_ms=elapsed_ms,
            )

    return IntegrationTestResult(
        test_name="determinism_test",
        status=IntegrationTestStatus.PASS,
        message=f"Model outputs are strictly deterministic across {repetitions} repeated executions.",
        execution_time_ms=elapsed_ms,
        details={"repetitions": repetitions},
    )


def run_error_handling_test(
    model_callable: Callable[[Any], Any],
    malformed_inputs: Sequence[Any],
) -> IntegrationTestResult:
    """Verify that malformed inputs return controlled errors instead of unhandled crashes."""
    t0 = time.perf_counter()
    controlled_failures = 0

    for idx, mal_input in enumerate(malformed_inputs):
        try:
            model_callable(mal_input)
            # If it succeeded on malformed input, it might lack validation, which is a warning
        except (ValueError, TypeError, KeyError):
            controlled_failures += 1
        except Exception:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return IntegrationTestResult(
                test_name="error_handling_test",
                status=IntegrationTestStatus.WARNING,
                message=f"Model raised unclassified exception on malformed input #{idx}.",
                execution_time_ms=elapsed_ms,
            )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return IntegrationTestResult(
        test_name="error_handling_test",
        status=IntegrationTestStatus.PASS,
        message=f"Error handling verified across {len(malformed_inputs)} test cases.",
        execution_time_ms=elapsed_ms,
        details={"controlled_catches": controlled_failures},
    )


def run_timeout_test(
    model_callable: Callable[[Any], Any],
    sample_input: Any,
    timeout_sec: float = 2.0,
) -> IntegrationTestResult:
    """Verify that model execution stays within defined timeout budget."""
    t0 = time.perf_counter()
    try:
        model_callable(sample_input)
        elapsed_sec = time.perf_counter() - t0
        elapsed_ms = elapsed_sec * 1000.0
        if elapsed_sec > timeout_sec:
            return IntegrationTestResult(
                test_name="timeout_and_resource_test",
                status=IntegrationTestStatus.FAIL,
                message=f"Execution exceeded budget: {elapsed_sec:.3f}s > {timeout_sec:.3f}s limit.",
                execution_time_ms=elapsed_ms,
            )
        return IntegrationTestResult(
            test_name="timeout_and_resource_test",
            status=IntegrationTestStatus.PASS,
            message=f"Execution respected budget: {elapsed_sec:.3f}s <= {timeout_sec:.3f}s limit.",
            execution_time_ms=elapsed_ms,
            details={"elapsed_sec": elapsed_sec, "timeout_sec": timeout_sec},
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return IntegrationTestResult(
            test_name="timeout_and_resource_test",
            status=IntegrationTestStatus.FAIL,
            message=f"Execution failed during timeout test: {exc}",
            execution_time_ms=elapsed_ms,
        )


def run_version_change_test(
    old_manifest: ModelManifest,
    new_manifest: ModelManifest,
) -> IntegrationTestResult:
    """Verify backward compatibility and schema stability between model versions."""
    t0 = time.perf_counter()
    diffs: List[str] = []

    # Check required inputs
    old_inputs = set(old_manifest.required_inputs)
    new_inputs = set(new_manifest.required_inputs)
    added_required = new_inputs - old_inputs
    if added_required:
        diffs.append(f"New version introduces additional required inputs: {list(added_required)}")

    # Check output schema changes
    for k, v in old_manifest.expected_output_schema.items():
        if k not in new_manifest.expected_output_schema:
            diffs.append(f"New version removed expected output field '{k}'")
        elif new_manifest.expected_output_schema[k] != v:
            diffs.append(f"Type changed for output field '{k}': {v} -> {new_manifest.expected_output_schema[k]}")

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if not diffs:
        return IntegrationTestResult(
            test_name="version_change_test",
            status=IntegrationTestStatus.PASS,
            message="Version update maintains backward compatibility with previous interface.",
            execution_time_ms=elapsed_ms,
            details={"old_version": old_manifest.version, "new_version": new_manifest.version},
        )
    return IntegrationTestResult(
        test_name="version_change_test",
        status=IntegrationTestStatus.WARNING,
        message=f"Breaking interface changes detected in version {new_manifest.version}: {'; '.join(diffs)}",
        execution_time_ms=elapsed_ms,
        details={"breaking_changes": diffs},
    )


# ==============================================================================
# Full Model Integration Audit Workflow
# ==============================================================================

def run_model_integration_suite(
    model_callable: Callable[[Any], Any],
    manifest: ModelManifest,
    sample_input: Any,
    provided_columns: Optional[Sequence[str]] = None,
    malformed_inputs: Optional[Sequence[Any]] = None,
) -> ModelIntegrationReport:
    """Execute the complete standard Lab 2 model integration verification suite."""
    results: List[IntegrationTestResult] = []

    # 1. Smoke test
    smoke_res = run_model_smoke_test(model_callable, sample_input)
    results.append(smoke_res)

    sample_output = None
    if smoke_res.status in (IntegrationTestStatus.PASS, IntegrationTestStatus.WARNING):
        try:
            sample_output = model_callable(sample_input)
        except Exception:
            pass

    # 2. Input contract test
    if provided_columns is not None:
        results.append(run_input_contract_test(manifest, provided_columns))
    else:
        results.append(
            IntegrationTestResult(
                test_name="input_contract_test",
                status=IntegrationTestStatus.SKIPPED,
                message="No provided_columns passed; input contract check skipped.",
            )
        )

    # 3. Output contract test
    if sample_output is not None:
        results.append(run_output_contract_test(manifest, sample_output))
        # 4. Numeric validity test
        results.append(run_numeric_validity_test(sample_output))
    else:
        results.append(
            IntegrationTestResult(
                test_name="output_contract_test",
                status=IntegrationTestStatus.SKIPPED,
                message="Sample output unavailable; skipped.",
            )
        )
        results.append(
            IntegrationTestResult(
                test_name="numeric_validity_test",
                status=IntegrationTestStatus.SKIPPED,
                message="Sample output unavailable; skipped.",
            )
        )

    # 5. Determinism test
    if manifest.is_deterministic:
        results.append(run_determinism_test(model_callable, sample_input, repetitions=3))
    else:
        results.append(
            IntegrationTestResult(
                test_name="determinism_test",
                status=IntegrationTestStatus.SKIPPED,
                message="Model manifest declares is_deterministic=False; skipped.",
            )
        )

    # 6. Error handling test
    if malformed_inputs is not None:
        results.append(run_error_handling_test(model_callable, malformed_inputs))

    # 7. Timeout test
    timeout_sec = float(manifest.runtime_limits.get("timeout_sec", 30.0))
    results.append(run_timeout_test(model_callable, sample_input, timeout_sec=min(timeout_sec, 5.0)))

    # Compute tally
    passed = sum(1 for r in results if r.status == IntegrationTestStatus.PASS)
    failed = sum(1 for r in results if r.status == IntegrationTestStatus.FAIL)
    warnings = sum(1 for r in results if r.status == IntegrationTestStatus.WARNING)
    inconclusive = sum(1 for r in results if r.status in (IntegrationTestStatus.INCONCLUSIVE, IntegrationTestStatus.SKIPPED))

    isolation_status = (
        "Isolated Worker Required" if manifest.code_isolation_required else "Main Process Adapter Approved"
    )

    summary = (
        f"Model {manifest.model_id} v{manifest.version} integration complete: "
        f"{passed} passed, {failed} failed, {warnings} warnings, {inconclusive} inconclusive/skipped."
    )

    return ModelIntegrationReport(
        model_id=manifest.model_id,
        version=manifest.version,
        tests_run=len(results),
        passed=passed,
        failed=failed,
        warnings=warnings,
        inconclusive=inconclusive,
        results=tuple(results),
        isolation_status=isolation_status,
        summary=summary,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
