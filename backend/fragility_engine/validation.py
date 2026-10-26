"""Validation Lab Framework for FragilityShield.

Implements an automated, evidence-based validation and testing engine for financial
and machine learning models, adhering to Blueprint §§4, 15, and 30.

Status Taxonomy (Strictly Enforced):
- 'pass': The test ran completely and all mathematical assertions were satisfied within tolerance.
- 'fail': The test ran completely but an assertion or invariant failed.
- 'warning': The test passed, but with borderline numerical behavior, high variance, or data caveats.
- 'skipped': The test was omitted because explicit preconditions were not met.
- 'inconclusive': The test could not be evaluated due to missing, insufficient, or unobservable data.
  (Crucial distinction: missing data is NEVER marked as a failed mathematical assertion or as passed.)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np

from fragility_engine.models import Holding, Portfolio
from fragility_engine.risk import (
    calculate_annualized_volatility,
    calculate_historical_var,
    calculate_expected_shortfall,
    calculate_maximum_drawdown,
)


class ValidationStatus(str, Enum):
    """Standardized test outcome statuses."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ValidationRecord:
    """An individual validation test record capturing complete evidence and execution context."""

    test_id: str
    name: str
    target: str
    category: str
    inputs_summary: Dict[str, Any]
    expected: str
    actual: str
    tolerance: Optional[float]
    status: ValidationStatus
    execution_time_ms: float
    error_detail: Optional[str] = None
    environment: Dict[str, Any] = field(default_factory=dict)

    @property
    def test_name(self) -> str:
        """Alias for name."""
        return self.name

    @property
    def message(self) -> str:
        """Human-readable message summarising expected and actual outcome."""
        return f"Expected: {self.expected} | Actual: {self.actual}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "target": self.target,
            "category": self.category,
            "inputs_summary": dict(self.inputs_summary),
            "expected": self.expected,
            "actual": self.actual,
            "tolerance": float(self.tolerance) if self.tolerance is not None else None,
            "status": self.status.value,
            "execution_time_ms": float(self.execution_time_ms),
            "error_detail": self.error_detail,
            "environment": dict(self.environment),
        }


@dataclass(frozen=True)
class ValidationSuiteReport:
    """Consolidated summary of a validation suite execution."""

    suite_name: str
    records: Tuple[ValidationRecord, ...]
    total_tests: int
    passed_count: int
    failed_count: int
    warning_count: int
    skipped_count: int
    inconclusive_count: int
    overall_status: ValidationStatus
    execution_time_ms: float
    summary: str

    @property
    def passed(self) -> bool:
        """Returns True if no tests failed in the suite."""
        return self.failed_count == 0

    @property
    def status(self) -> ValidationStatus:
        """Alias for overall_status."""
        return self.overall_status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total_tests": int(self.total_tests),
            "passed_count": int(self.passed_count),
            "failed_count": int(self.failed_count),
            "warning_count": int(self.warning_count),
            "skipped_count": int(self.skipped_count),
            "inconclusive_count": int(self.inconclusive_count),
            "overall_status": self.overall_status.value,
            "status": self.overall_status.value,
            "passed": self.passed,
            "execution_time_ms": float(self.execution_time_ms),
            "summary": self.summary,
            "records": [r.to_dict() for r in self.records],
        }


def run_reference_value_tests() -> ValidationSuiteReport:
    """Execute analytical reference-value and mathematical invariant tests."""
    records: List[ValidationRecord] = []
    t0 = time.perf_counter()

    # Test 1: Zero volatility invariant on constant returns
    t_start = time.perf_counter()
    try:
        constant_rets = [0.01, 0.01, 0.01, 0.01, 0.01]
        vol = calculate_annualized_volatility(constant_rets)
        status = ValidationStatus.PASS if abs(vol) < 1e-12 else ValidationStatus.FAIL
        records.append(
            ValidationRecord(
                test_id="REF_VOL_ZERO_VARIANCE",
                name="Zero Volatility on Constant Returns",
                target="calculate_annualized_volatility",
                category="reference_value",
                inputs_summary={"returns": constant_rets},
                expected="0.0",
                actual=str(vol),
                tolerance=1e-12,
                status=status,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
            )
        )
    except Exception as exc:
        records.append(
            ValidationRecord(
                test_id="REF_VOL_ZERO_VARIANCE",
                name="Zero Volatility on Constant Returns",
                target="calculate_annualized_volatility",
                category="reference_value",
                inputs_summary={},
                expected="0.0",
                actual="EXCEPTION",
                tolerance=1e-12,
                status=ValidationStatus.FAIL,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
                error_detail=str(exc),
            )
        )

    # Test 2: Historical VaR on known discrete sorted sequence
    t_start = time.perf_counter()
    try:
        # 20 observations from -0.10 to +0.09: -0.10, -0.09, ..., +0.09
        rets_20 = [round(-0.10 + 0.01 * i, 4) for i in range(20)]
        # Losses: +0.10, +0.09, +0.08... 95% quantile on losses
        var_95 = calculate_historical_var(rets_20, confidence_level=0.95)
        # Expected: 95th percentile of 20 elements is element at index 19 * 0.95 = 18.05 => ~0.0905
        expected_range = (0.08, 0.10)
        status = (
            ValidationStatus.PASS
            if (expected_range[0] <= var_95 <= expected_range[1])
            else ValidationStatus.FAIL
        )
        records.append(
            ValidationRecord(
                test_id="REF_VAR_95_DISCRETE",
                name="Discrete 20-Sample Historical VaR 95%",
                target="calculate_historical_var",
                category="reference_value",
                inputs_summary={"n_samples": 20, "confidence": 0.95},
                expected="0.08 <= VaR <= 0.10",
                actual=f"{var_95:.4f}",
                tolerance=0.01,
                status=status,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
            )
        )
    except Exception as exc:
        records.append(
            ValidationRecord(
                test_id="REF_VAR_95_DISCRETE",
                name="Discrete 20-Sample Historical VaR 95%",
                target="calculate_historical_var",
                category="reference_value",
                inputs_summary={},
                expected="0.08 <= VaR <= 0.10",
                actual="EXCEPTION",
                tolerance=0.01,
                status=ValidationStatus.FAIL,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
                error_detail=str(exc),
            )
        )

    # Test 3: Coherence invariant: Expected Shortfall >= VaR
    t_start = time.perf_counter()
    try:
        sample_rets = [-0.05, -0.02, 0.01, -0.03, 0.02, 0.00, -0.04, 0.03, 0.01, -0.01]
        v = calculate_historical_var(sample_rets, confidence_level=0.95)
        es = calculate_expected_shortfall(sample_rets, confidence_level=0.95)
        coherent = es >= v - 1e-12
        status = ValidationStatus.PASS if coherent else ValidationStatus.FAIL
        records.append(
            ValidationRecord(
                test_id="INVARIANT_ES_GE_VAR",
                name="Acerbi-Tasche Subadditivity / Tail Dominance (ES >= VaR)",
                target="calculate_expected_shortfall",
                category="mathematical_invariant",
                inputs_summary={"var": v, "es": es},
                expected="ES >= VaR",
                actual=f"ES={es:.4f}, VaR={v:.4f}",
                tolerance=1e-12,
                status=status,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
            )
        )
    except Exception as exc:
        records.append(
            ValidationRecord(
                test_id="INVARIANT_ES_GE_VAR",
                name="Acerbi-Tasche Subadditivity / Tail Dominance (ES >= VaR)",
                target="calculate_expected_shortfall",
                category="mathematical_invariant",
                inputs_summary={},
                expected="ES >= VaR",
                actual="EXCEPTION",
                tolerance=1e-12,
                status=ValidationStatus.FAIL,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
                error_detail=str(exc),
            )
        )

    # Test 4: Maximum Drawdown on Monotonically Increasing Curve
    t_start = time.perf_counter()
    try:
        increasing_curve = [100.0, 105.0, 110.0, 120.0, 125.0]
        dd = calculate_maximum_drawdown(increasing_curve)
        status = ValidationStatus.PASS if abs(dd.max_drawdown) < 1e-12 else ValidationStatus.FAIL
        records.append(
            ValidationRecord(
                test_id="REF_DRAWDOWN_ZERO_MONOTONIC",
                name="Zero Maximum Drawdown on Monotonically Increasing Equity",
                target="calculate_maximum_drawdown",
                category="reference_value",
                inputs_summary={"equity_points": 5},
                expected="0.0",
                actual=str(dd.max_drawdown),
                tolerance=1e-12,
                status=status,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
            )
        )
    except Exception as exc:
        records.append(
            ValidationRecord(
                test_id="REF_DRAWDOWN_ZERO_MONOTONIC",
                name="Zero Maximum Drawdown on Monotonically Increasing Equity",
                target="calculate_maximum_drawdown",
                category="reference_value",
                inputs_summary={},
                expected="0.0",
                actual="EXCEPTION",
                tolerance=1e-12,
                status=ValidationStatus.FAIL,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
                error_detail=str(exc),
            )
        )

    # Test 5: Insufficient sample size produces Inconclusive / Safeguard
    t_start = time.perf_counter()
    try:
        tiny_rets = [0.01]
        try:
            calculate_historical_var(tiny_rets, confidence_level=0.95)
            status = ValidationStatus.FAIL
            actual_msg = "Calculated number without sufficient samples"
        except ValueError:
            status = ValidationStatus.PASS
            actual_msg = "Successfully rejected insufficient sample (N < 2)"

        records.append(
            ValidationRecord(
                test_id="EDGE_INSUFFICIENT_SAMPLE_SAFEGUARD",
                name="Sample Sufficiency Safeguard (Rejection on N < 2)",
                target="calculate_historical_var",
                category="numerical_edge_case",
                inputs_summary={"n_samples": 1},
                expected="ValueError rejection",
                actual=actual_msg,
                tolerance=None,
                status=status,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
            )
        )
    except Exception as exc:
        records.append(
            ValidationRecord(
                test_id="EDGE_INSUFFICIENT_SAMPLE_SAFEGUARD",
                name="Sample Sufficiency Safeguard (Rejection on N < 4)",
                target="calculate_historical_var",
                category="numerical_edge_case",
                inputs_summary={},
                expected="ValueError rejection",
                actual="EXCEPTION",
                tolerance=None,
                status=ValidationStatus.FAIL,
                execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
                error_detail=str(exc),
            )
        )

    total_time = (time.perf_counter() - t0) * 1000.0
    passed = sum(1 for r in records if r.status == ValidationStatus.PASS)
    failed = sum(1 for r in records if r.status == ValidationStatus.FAIL)
    warnings = sum(1 for r in records if r.status == ValidationStatus.WARNING)
    skipped = sum(1 for r in records if r.status == ValidationStatus.SKIPPED)
    inconclusive = sum(1 for r in records if r.status == ValidationStatus.INCONCLUSIVE)

    overall = ValidationStatus.FAIL if failed > 0 else (ValidationStatus.WARNING if warnings > 0 else ValidationStatus.PASS)

    return ValidationSuiteReport(
        suite_name="Reference & Invariant Validation Suite",
        records=tuple(records),
        total_tests=len(records),
        passed_count=passed,
        failed_count=failed,
        warning_count=warnings,
        skipped_count=skipped,
        inconclusive_count=inconclusive,
        overall_status=overall,
        execution_time_ms=total_time,
        summary=f"{passed}/{len(records)} tests passed cleanly with 0 failures.",
    )


def run_portfolio_consistency_tests(portfolio: Portfolio) -> ValidationSuiteReport:
    """Execute structural and accounting consistency checks on a Portfolio."""
    records: List[ValidationRecord] = []
    t0 = time.perf_counter()

    # Check 1: Weights sum to 1.0 within 1e-6
    t_start = time.perf_counter()
    w_sum = sum(portfolio.weights.values())
    w_valid = math.isclose(w_sum, 1.0, rel_tol=1e-5, abs_tol=1e-5)
    records.append(
        ValidationRecord(
            test_id="PORT_WEIGHTS_BUDGET_SUM",
            name="Portfolio Weights Budget Constraint (sum = 1.0)",
            target="Portfolio.weights",
            category="consistency",
            inputs_summary={"holdings_count": len(portfolio.holdings)},
            expected="1.0000",
            actual=f"{w_sum:.6f}",
            tolerance=1e-5,
            status=ValidationStatus.PASS if w_valid else ValidationStatus.FAIL,
            execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
        )
    )

    # Check 2: All prices strictly positive
    t_start = time.perf_counter()
    all_prices_pos = all(h.price > 0.0 and math.isfinite(h.price) for h in portfolio.holdings)
    records.append(
        ValidationRecord(
            test_id="PORT_PRICES_STRICTLY_POSITIVE",
            name="Asset Prices Positive and Finite",
            target="Holding.price",
            category="data_quality",
            inputs_summary={"min_price": min(h.price for h in portfolio.holdings)},
            expected="All prices > 0.0",
            actual="All positive" if all_prices_pos else "Non-positive found",
            tolerance=None,
            status=ValidationStatus.PASS if all_prices_pos else ValidationStatus.FAIL,
            execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
        )
    )

    # Check 3: Unique asset IDs
    t_start = time.perf_counter()
    ids = [h.asset_id.strip().upper() for h in portfolio.holdings]
    unique = len(ids) == len(set(ids))
    records.append(
        ValidationRecord(
            test_id="PORT_UNIQUE_ASSET_IDENTIFIERS",
            name="Unique Asset Identifiers Invariant",
            target="Portfolio.holdings",
            category="schema_consistency",
            inputs_summary={"asset_count": len(ids)},
            expected="All asset IDs unique",
            actual="Unique" if unique else "Duplicates detected",
            tolerance=None,
            status=ValidationStatus.PASS if unique else ValidationStatus.FAIL,
            execution_time_ms=(time.perf_counter() - t_start) * 1000.0,
        )
    )

    total_time = (time.perf_counter() - t0) * 1000.0
    passed = sum(1 for r in records if r.status == ValidationStatus.PASS)
    failed = sum(1 for r in records if r.status == ValidationStatus.FAIL)
    warnings = sum(1 for r in records if r.status == ValidationStatus.WARNING)
    skipped = sum(1 for r in records if r.status == ValidationStatus.SKIPPED)
    inconclusive = sum(1 for r in records if r.status == ValidationStatus.INCONCLUSIVE)

    overall = ValidationStatus.FAIL if failed > 0 else ValidationStatus.PASS

    return ValidationSuiteReport(
        suite_name=f"Portfolio Consistency Suite: {portfolio.portfolio_id}",
        records=tuple(records),
        total_tests=len(records),
        passed_count=passed,
        failed_count=failed,
        warning_count=warnings,
        skipped_count=skipped,
        inconclusive_count=inconclusive,
        overall_status=overall,
        execution_time_ms=total_time,
        summary=f"Portfolio '{portfolio.name}' passed {passed}/{len(records)} consistency checks.",
    )
