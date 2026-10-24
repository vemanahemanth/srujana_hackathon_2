"""Quantitative Out-of-Sample VaR Backtesting & Statistical Validation Engine.

Phase 8.2 Quantitative Forecast Integrity:
- Formalizes forecast origins, horizons, and realized outcome alignment.
- Eliminates look-ahead bias and data leakage in risk validation.
- Implements the Kupiec Unconditional Coverage (POF) likelihood-ratio test.
- Implements the Christoffersen Independence and Conditional Coverage tests.
- Provides causal rolling walk-forward backtesting across registered model plugins.
- Cryptographically fingerprints backtest configurations and breach series.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from fragility_engine.models import Portfolio
from fragility_engine.plugins import ModelPlugin, get_default_registry
from fragility_engine.reproducibility import compute_canonical_hash


# ==============================================================================
# 1. Domain Models & Contracts
# ==============================================================================

@dataclass(frozen=True)
class VaRForecast:
    """Individual 1-step or multi-step out-of-sample risk forecast.

    Attributes:
        forecast_id: Unique identifier for this forecast point.
        origin_index: Integer time index t at which the forecast is produced.
        target_index: Integer time index t+h for which the loss threshold is predicted.
        horizon: Forecast horizon step count h (default 1).
        confidence_level: VaR confidence level (e.g. 0.95 or 0.99).
        var_estimate: Predicted loss threshold (positive fraction, L = -R).
        expected_shortfall_estimate: Optional predicted Expected Shortfall.
        model_id: Identifier of the producing model plugin.
        metadata: Informational configuration metadata at origin.
    """

    forecast_id: str
    origin_index: int
    target_index: int
    confidence_level: float
    var_estimate: float
    horizon: int = 1
    expected_shortfall_estimate: Optional[float] = None
    model_id: str = "model"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_index <= self.origin_index:
            raise ValueError(
                f"target_index ({self.target_index}) must be strictly greater than origin_index ({self.origin_index}) to prevent look-ahead bias"
            )
        if self.horizon < 1:
            raise ValueError(f"horizon must be an integer >= 1; got {self.horizon}")
        if not (0.0 < self.confidence_level < 1.0):
            raise ValueError(f"confidence_level must be in (0, 1); got {self.confidence_level}")
        if not math.isfinite(self.var_estimate):
            raise ValueError(f"var_estimate must be a finite float; got {self.var_estimate}")
        if self.expected_shortfall_estimate is not None:
            if not math.isfinite(self.expected_shortfall_estimate):
                raise ValueError(f"expected_shortfall_estimate must be finite; got {self.expected_shortfall_estimate}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "origin_index": self.origin_index,
            "target_index": self.target_index,
            "horizon": self.horizon,
            "confidence_level": float(self.confidence_level),
            "var_estimate": float(self.var_estimate),
            "expected_shortfall_estimate": (
                float(self.expected_shortfall_estimate)
                if self.expected_shortfall_estimate is not None
                else None
            ),
            "model_id": self.model_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class VaRBreachEvaluation:
    """Evaluation of an individual out-of-sample forecast against realized outcome.

    Attributes:
        forecast: The ex-ante VaR forecast.
        realized_return: Actual simple return R observed at target_index.
        realized_loss: Realized loss L = -R.
        is_breach: True if realized_loss strictly exceeds var_estimate.
        loss_exceedance: max(0.0, realized_loss - var_estimate).
    """

    forecast: VaRForecast
    realized_return: float
    realized_loss: float
    is_breach: bool
    loss_exceedance: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "forecast": self.forecast.to_dict(),
            "realized_return": float(self.realized_return),
            "realized_loss": float(self.realized_loss),
            "is_breach": bool(self.is_breach),
            "loss_exceedance": float(self.loss_exceedance),
        }


@dataclass(frozen=True)
class KupiecTestResult:
    """Kupiec Proportion of Failures (POF) Unconditional Coverage Test Result.

    Tests null hypothesis H0: p = p0 vs H1: p != p0, where p0 = 1 - alpha.
    Likelihood ratio test statistic follows an asymptotic Chi-Square distribution with df=1.
    """

    test_name: str = "Kupiec Unconditional Coverage (POF)"
    nominal_rate: float = 0.05
    observed_rate: float = 0.05
    total_observations: int = 0
    breach_count: int = 0
    likelihood_ratio: float = 0.0
    p_value: float = 1.0
    significance_level: float = 0.05
    decision: str = "ACCEPT_NULL"
    is_calibrated: bool = True
    warnings: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "nominal_rate": float(self.nominal_rate),
            "observed_rate": float(self.observed_rate),
            "total_observations": int(self.total_observations),
            "breach_count": int(self.breach_count),
            "likelihood_ratio": float(self.likelihood_ratio),
            "p_value": float(self.p_value),
            "significance_level": float(self.significance_level),
            "decision": self.decision,
            "is_calibrated": bool(self.is_calibrated),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class ChristoffersenTestResult:
    """Christoffersen Independence and Conditional Coverage Test Result.

    Tests breach clustering via 2-state Markov chain transitions:
    H0: Breaches are independently distributed over time (no clustering).
    Combined Conditional Coverage: LR_CC = LR_POF + LR_ind ~ Chi-Square(df=2).
    """

    test_name: str = "Christoffersen Independence & Conditional Coverage"
    contingency_matrix: Mapping[str, int] = field(default_factory=dict)
    lr_independence: float = 0.0
    p_value_independence: float = 1.0
    decision_independence: str = "ACCEPT_NULL"
    lr_conditional_coverage: float = 0.0
    p_value_conditional_coverage: float = 1.0
    decision_conditional_coverage: str = "ACCEPT_NULL"
    significance_level: float = 0.05
    is_independent: bool = True
    is_conditionally_calibrated: bool = True
    warnings: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "contingency_matrix": dict(self.contingency_matrix),
            "lr_independence": float(self.lr_independence),
            "p_value_independence": float(self.p_value_independence),
            "decision_independence": self.decision_independence,
            "lr_conditional_coverage": float(self.lr_conditional_coverage),
            "p_value_conditional_coverage": float(self.p_value_conditional_coverage),
            "decision_conditional_coverage": self.decision_conditional_coverage,
            "significance_level": float(self.significance_level),
            "is_independent": bool(self.is_independent),
            "is_conditionally_calibrated": bool(self.is_conditionally_calibrated),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class BacktestReport:
    """Comprehensive out-of-sample risk backtesting report with statistical tests."""

    backtest_id: str
    model_id: str
    confidence_level: float
    estimation_window: int
    evaluation_sample_size: int
    breach_count: int
    observed_breach_rate: float
    nominal_rate: float
    kupiec_test: KupiecTestResult
    christoffersen_test: ChristoffersenTestResult
    breach_evaluations: Tuple[VaRBreachEvaluation, ...]
    manifest: Mapping[str, Any]
    warnings: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "model_id": self.model_id,
            "confidence_level": float(self.confidence_level),
            "estimation_window": int(self.estimation_window),
            "evaluation_sample_size": int(self.evaluation_sample_size),
            "breach_count": int(self.breach_count),
            "observed_breach_rate": float(self.observed_breach_rate),
            "nominal_rate": float(self.nominal_rate),
            "kupiec_test": self.kupiec_test.to_dict(),
            "christoffersen_test": self.christoffersen_test.to_dict(),
            "breach_evaluations": [b.to_dict() for b in self.breach_evaluations],
            "manifest": dict(self.manifest),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(
            self.to_dict(),
            indent=indent,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BacktestReport:
        kupiec_data = dict(data.get("kupiec_test", {}))
        kupiec = KupiecTestResult(
            test_name=kupiec_data.get("test_name", "Kupiec Unconditional Coverage (POF)"),
            nominal_rate=float(kupiec_data.get("nominal_rate", 0.05)),
            observed_rate=float(kupiec_data.get("observed_rate", 0.05)),
            total_observations=int(kupiec_data.get("total_observations", 0)),
            breach_count=int(kupiec_data.get("breach_count", 0)),
            likelihood_ratio=float(kupiec_data.get("likelihood_ratio", 0.0)),
            p_value=float(kupiec_data.get("p_value", 1.0)),
            significance_level=float(kupiec_data.get("significance_level", 0.05)),
            decision=str(kupiec_data.get("decision", "ACCEPT_NULL")),
            is_calibrated=bool(kupiec_data.get("is_calibrated", True)),
            warnings=tuple(kupiec_data.get("warnings", ())),
            limitations=tuple(kupiec_data.get("limitations", ())),
        )

        chris_data = dict(data.get("christoffersen_test", {}))
        christoffersen = ChristoffersenTestResult(
            test_name=chris_data.get("test_name", "Christoffersen Independence & Conditional Coverage"),
            contingency_matrix=dict(chris_data.get("contingency_matrix", {})),
            lr_independence=float(chris_data.get("lr_independence", 0.0)),
            p_value_independence=float(chris_data.get("p_value_independence", 1.0)),
            decision_independence=str(chris_data.get("decision_independence", "ACCEPT_NULL")),
            lr_conditional_coverage=float(chris_data.get("lr_conditional_coverage", 0.0)),
            p_value_conditional_coverage=float(chris_data.get("p_value_conditional_coverage", 1.0)),
            decision_conditional_coverage=str(chris_data.get("decision_conditional_coverage", "ACCEPT_NULL")),
            significance_level=float(chris_data.get("significance_level", 0.05)),
            is_independent=bool(chris_data.get("is_independent", True)),
            is_conditionally_calibrated=bool(chris_data.get("is_conditionally_calibrated", True)),
            warnings=tuple(chris_data.get("warnings", ())),
            limitations=tuple(chris_data.get("limitations", ())),
        )

        breach_evals = tuple(
            VaRBreachEvaluation(
                forecast=VaRForecast(
                    forecast_id=b["forecast"]["forecast_id"],
                    origin_index=int(b["forecast"]["origin_index"]),
                    target_index=int(b["forecast"]["target_index"]),
                    horizon=int(b["forecast"].get("horizon", 1)),
                    confidence_level=float(b["forecast"]["confidence_level"]),
                    var_estimate=float(b["forecast"]["var_estimate"]),
                    expected_shortfall_estimate=(
                        float(b["forecast"]["expected_shortfall_estimate"])
                        if b["forecast"].get("expected_shortfall_estimate") is not None
                        else None
                    ),
                    model_id=str(b["forecast"].get("model_id", "model")),
                    metadata=dict(b["forecast"].get("metadata", {})),
                ),
                realized_return=float(b["realized_return"]),
                realized_loss=float(b["realized_loss"]),
                is_breach=bool(b["is_breach"]),
                loss_exceedance=float(b["loss_exceedance"]),
            )
            for b in data.get("breach_evaluations", [])
        )

        return cls(
            backtest_id=str(data.get("backtest_id", "")),
            model_id=str(data.get("model_id", "")),
            confidence_level=float(data.get("confidence_level", 0.95)),
            estimation_window=int(data.get("estimation_window", 250)),
            evaluation_sample_size=int(data.get("evaluation_sample_size", len(breach_evals))),
            breach_count=int(data.get("breach_count", 0)),
            observed_breach_rate=float(data.get("observed_breach_rate", 0.0)),
            nominal_rate=float(data.get("nominal_rate", 0.05)),
            kupiec_test=kupiec,
            christoffersen_test=christoffersen,
            breach_evaluations=breach_evals,
            manifest=dict(data.get("manifest", {})),
            warnings=tuple(data.get("warnings", ())),
            limitations=tuple(data.get("limitations", ())),
        )

    @classmethod
    def from_json(cls, json_str: str) -> BacktestReport:
        return cls.from_dict(json.loads(json_str))

    def to_markdown(self) -> str:
        lines = [
            f"# FragilityShield — Out-of-Sample VaR Backtest Report",
            "",
            f"**Backtest ID:** `{self.backtest_id}`  ",
            f"**Model ID:** `{self.model_id}`  ",
            f"**Confidence Level:** `{self.confidence_level * 100:.1f}%`  ",
            f"**Estimation Window:** `{self.estimation_window}` periods  ",
            f"**Evaluation Window:** `{self.evaluation_sample_size}` out-of-sample periods  ",
            "",
            "---",
            "",
            "## 1. Summary of Exceedances & Coverage",
            "",
            f"- **Nominal Exceedance Probability ($p_0$):** `{self.nominal_rate * 100:.2f}%`",
            f"- **Observed Breach Count ($x$):** `{self.breach_count}` / `{self.evaluation_sample_size}`",
            f"- **Observed Breach Rate ($\\hat{{p}}$):** `{self.observed_breach_rate * 100:.2f}%`",
            "",
            "> **Statistical Validation Notice:** A breach rate close to nominal does not, by itself, "
            "prove model optimality. Failure to reject the null hypothesis indicates empirical compatibility "
            "with nominal coverage, not definitive proof of true distributional correctness.",
            "",
            "---",
            "",
            "## 2. Kupiec Unconditional Coverage Test (POF)",
            "",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Likelihood Ratio ($LR_{{POF}}$)** | `{self.kupiec_test.likelihood_ratio:.4f}` |",
            f"| **Asymptotic P-Value ($\\chi^2_1$)** | `{self.kupiec_test.p_value:.6f}` |",
            f"| **Decision ($\alpha=0.05$)** | `{self.kupiec_test.decision}` |",
            f"| **Unconditional Calibration** | `{'CALIBRATED' if self.kupiec_test.is_calibrated else 'REJECTED'}` |",
            "",
            "---",
            "",
            "## 3. Christoffersen Independence & Conditional Coverage Test",
            "",
            "| Transition | Count | Interpretation |",
            "| :---: | :---: | :--- |",
            f"| $n_{{00}}$ | {self.christoffersen_test.contingency_matrix.get('n00', 0)} | Non-breach followed by non-breach |",
            f"| $n_{{01}}$ | {self.christoffersen_test.contingency_matrix.get('n01', 0)} | Non-breach followed by breach |",
            f"| $n_{{10}}$ | {self.christoffersen_test.contingency_matrix.get('n10', 0)} | Breach followed by non-breach |",
            f"| $n_{{11}}$ | {self.christoffersen_test.contingency_matrix.get('n11', 0)} | Breach followed by breach (clustering) |",
            "",
            "| Test Component | LR Statistic | P-Value | Decision |",
            "| :--- | :---: | :---: | :--- |",
            f"| **Independence ($LR_{{ind}}$)** | `{self.christoffersen_test.lr_independence:.4f}` | `{self.christoffersen_test.p_value_independence:.6f}` | `{self.christoffersen_test.decision_independence}` |",
            f"| **Conditional Coverage ($LR_{{CC}}$)** | `{self.christoffersen_test.lr_conditional_coverage:.4f}` | `{self.christoffersen_test.p_value_conditional_coverage:.6f}` | `{self.christoffersen_test.decision_conditional_coverage}` |",
            "",
        ]

        if self.warnings:
            lines.extend([
                "---",
                "",
                "## 4. Diagnostic Warnings",
                "",
            ])
            for w in self.warnings:
                lines.append(f"- [WARNING] {w}")
            lines.append("")

        if self.limitations:
            lines.extend([
                "---",
                "",
                "## 5. Methodological Limitations",
                "",
            ])
            for lim in self.limitations:
                lines.append(f"- [LIMITATION] {lim}")
            lines.append("")

        return "\n".join(lines)


# ==============================================================================
# 2. Breach Evaluation Primitive
# ==============================================================================

def evaluate_var_breaches(
    forecasts: Sequence[VaRForecast],
    realized_returns: Sequence[float] | np.ndarray,
) -> Tuple[VaRBreachEvaluation, ...]:
    """Evaluate ex-ante VaR forecasts against out-of-sample realized returns.

    Sign Convention:
        Realized loss is defined as L_{target} = -R_{target}.
        A breach occurs when L_{target} > VaR_estimate.
        Equality is NOT treated as a breach (strict loss exceedance requirement).

    Args:
        forecasts: Sequence of verified VaRForecast instances.
        realized_returns: Full series of observed simple returns.

    Returns:
        Tuple of VaRBreachEvaluation records for each aligned forecast.

    Raises:
        ValueError: If target_index exceeds available realized_returns.
    """
    arr = np.asarray(realized_returns, dtype=np.float64)
    evaluations: List[VaRBreachEvaluation] = []

    for f in forecasts:
        if f.target_index >= len(arr):
            raise ValueError(
                f"Forecast {f.forecast_id} targets index {f.target_index}, but realized_returns has length {len(arr)}"
            )

        r = float(arr[f.target_index])
        if not math.isfinite(r):
            raise ValueError(f"Realized return at index {f.target_index} is non-finite: {r}")

        loss = -r
        # Strict breach check with 1e-12 floating-point tolerance
        is_breach = bool(loss > f.var_estimate and not math.isclose(loss, f.var_estimate, abs_tol=1e-12))
        exceedance = max(0.0, loss - f.var_estimate)

        evaluations.append(
            VaRBreachEvaluation(
                forecast=f,
                realized_return=r,
                realized_loss=loss,
                is_breach=is_breach,
                loss_exceedance=exceedance,
            )
        )

    return tuple(evaluations)


# ==============================================================================
# 3. Kupiec Unconditional Coverage (POF) Likelihood-Ratio Test
# ==============================================================================

def calculate_kupiec_pof_test(
    breaches: Sequence[bool | int],
    confidence_level: float = 0.95,
    significance_level: float = 0.05,
) -> KupiecTestResult:
    """Calculate Kupiec Proportion of Failures (POF) Likelihood-Ratio Test.

    Formula:
        LR_POF = -2 * ln[ (1 - p0)^(N - x) * p0^x / ((1 - p_hat)^(N - x) * p_hat^x) ]
               = 2 * [ x * ln(p_hat / p0) + (N - x) * ln((1 - p_hat) / (1 - p0)) ]

    Boundary Handling:
        x = 0: LR_POF = -2 * N * ln(1 - p0)
        x = N: LR_POF = -2 * N * ln(p0)
        p_hat == p0: LR_POF = 0.0

    Asymptotics:
        LR_POF ~ Chi-Square(df=1).
        Exact survival p-value: erfc( sqrt(LR / 2) ).

    Args:
        breaches: Sequence of boolean or 0/1 breach indicators.
        confidence_level: VaR confidence level (e.g. 0.95).
        significance_level: Hypothesis test alpha (default 0.05).

    Returns:
        KupiecTestResult with test statistic, exact p-value, and decision.
    """
    if not (0.0 < confidence_level < 1.0):
        raise ValueError(f"confidence_level must be in (0, 1); got {confidence_level}")
    if not (0.0 < significance_level < 1.0):
        raise ValueError(f"significance_level must be in (0, 1); got {significance_level}")
    if not breaches:
        raise ValueError("breaches sequence cannot be empty")

    n = len(breaches)
    x = int(sum(bool(b) for b in breaches))
    p0 = 1.0 - confidence_level
    p_hat = x / n

    warnings: List[str] = []
    if n < 30:
        warnings.append(
            f"Sample size N={n} is smaller than recommended minimum (N>=30) for asymptotic chi-square validity."
        )
    if n < 250:
        warnings.append(
            f"Sample size N={n} is smaller than standard Basel 250-day window; statistical power may be limited."
        )

    # Compute Likelihood Ratio
    if x == 0:
        # lim_{p_hat -> 0} x * ln(p_hat) = 0
        lr = -2.0 * float(n) * math.log(1.0 - p0)
    elif x == n:
        # lim_{p_hat -> 1} (n - x) * ln(1 - p_hat) = 0
        lr = -2.0 * float(n) * math.log(p0)
    elif math.isclose(p_hat, p0, abs_tol=1e-12):
        lr = 0.0
    else:
        term1 = x * math.log(p_hat / p0)
        term2 = (n - x) * math.log((1.0 - p_hat) / (1.0 - p0))
        lr = 2.0 * (term1 + term2)

    lr = max(0.0, float(lr))

    # Exact Chi-Square(1) survival function: erfc(sqrt(lr / 2))
    p_val = float(math.erfc(math.sqrt(lr / 2.0)))
    decision = "REJECT_NULL" if p_val < significance_level else "ACCEPT_NULL"
    is_cal = (decision == "ACCEPT_NULL")

    limitations = (
        "Asymptotic test assumes independent and identically distributed Bernoulli trials.",
        "POF test examines unconditional frequency only; it does not detect breach clustering.",
        "Failure to reject null hypothesis does not constitute proof that the risk model is correct.",
    )

    return KupiecTestResult(
        test_name="Kupiec Unconditional Coverage (POF)",
        nominal_rate=p0,
        observed_rate=p_hat,
        total_observations=n,
        breach_count=x,
        likelihood_ratio=lr,
        p_value=p_val,
        significance_level=significance_level,
        decision=decision,
        is_calibrated=is_cal,
        warnings=tuple(warnings),
        limitations=limitations,
    )


# ==============================================================================
# 4. Christoffersen Independence & Conditional Coverage Test
# ==============================================================================

def calculate_christoffersen_test(
    breaches: Sequence[bool | int],
    confidence_level: float = 0.95,
    significance_level: float = 0.05,
) -> ChristoffersenTestResult:
    """Calculate Christoffersen Independence and Combined Conditional Coverage Test.

    Evaluates temporal clustering of breaches using first-order Markov chain transitions.
    LR_ind ~ Chi-Square(df=1).
    LR_CC = LR_POF + LR_ind ~ Chi-Square(df=2).

    Args:
        breaches: Sequence of boolean or 0/1 breach indicators in chronological order.
        confidence_level: VaR confidence level (e.g. 0.95).
        significance_level: Hypothesis test alpha (default 0.05).

    Returns:
        ChristoffersenTestResult with contingency matrix, LR statistics, and decisions.
    """
    if len(breaches) < 2:
        raise ValueError(f"Christoffersen test requires at least 2 consecutive observations; got {len(breaches)}")

    kupiec = calculate_kupiec_pof_test(
        breaches, confidence_level=confidence_level, significance_level=significance_level
    )

    int_breaches = [1 if b else 0 for b in breaches]
    n00 = 0
    n01 = 0
    n10 = 0
    n11 = 0

    for t in range(len(int_breaches) - 1):
        prev = int_breaches[t]
        curr = int_breaches[t + 1]
        if prev == 0 and curr == 0:
            n00 += 1
        elif prev == 0 and curr == 1:
            n01 += 1
        elif prev == 1 and curr == 0:
            n10 += 1
        elif prev == 1 and curr == 1:
            n11 += 1

    contingency = {"n00": n00, "n01": n01, "n10": n10, "n11": n11}
    warnings: List[str] = list(kupiec.warnings)

    denom0 = n00 + n01
    denom1 = n10 + n11
    total_transitions = denom0 + denom1

    if total_transitions == 0:
        lr_ind = 0.0
    elif n01 == 0 and n11 == 0:
        # Zero breaches in the transition pairs
        lr_ind = 0.0
    elif n00 == 0 and n10 == 0:
        # 100% breaches in all transitions
        lr_ind = 0.0
    else:
        # Empirical transition probabilities
        pi_01 = n01 / denom0 if denom0 > 0 else 0.0
        pi_11 = n11 / denom1 if denom1 > 0 else 0.0
        pi = (n01 + n11) / total_transitions

        # Unconstrained log-likelihood
        l_u = 0.0
        if n00 > 0 and (1.0 - pi_01) > 0.0:
            l_u += n00 * math.log(1.0 - pi_01)
        if n01 > 0 and pi_01 > 0.0:
            l_u += n01 * math.log(pi_01)
        if n10 > 0 and (1.0 - pi_11) > 0.0:
            l_u += n10 * math.log(1.0 - pi_11)
        if n11 > 0 and pi_11 > 0.0:
            l_u += n11 * math.log(pi_11)

        # Constrained log-likelihood (independence: pi_01 = pi_11 = pi)
        l_c = 0.0
        if (n00 + n10) > 0 and (1.0 - pi) > 0.0:
            l_c += (n00 + n10) * math.log(1.0 - pi)
        if (n01 + n11) > 0 and pi > 0.0:
            l_c += (n01 + n11) * math.log(pi)

        lr_ind = max(0.0, 2.0 * (l_u - l_c))

    # Independence p-value (df=1)
    p_val_ind = float(math.erfc(math.sqrt(lr_ind / 2.0)))
    dec_ind = "REJECT_NULL" if p_val_ind < significance_level else "ACCEPT_NULL"
    is_ind = (dec_ind == "ACCEPT_NULL")

    # Combined Conditional Coverage: LR_CC = LR_POF + LR_ind ~ Chi-Square(df=2)
    lr_cc = kupiec.likelihood_ratio + lr_ind
    # Exact survival function for Chi-Square(2): exp(-x / 2)
    p_val_cc = float(math.exp(-lr_cc / 2.0))
    dec_cc = "REJECT_NULL" if p_val_cc < significance_level else "ACCEPT_NULL"
    is_cond_cal = (dec_cc == "ACCEPT_NULL")

    limitations = (
        "First-order Markov property evaluates only 1-period memory; higher-order clustering is not detected.",
        "Small sample breach counts (especially n11=0) reduce test power to detect clustering.",
        "Test requires sequential, chronologically ordered breach indicators.",
    )

    return ChristoffersenTestResult(
        test_name="Christoffersen Independence & Conditional Coverage",
        contingency_matrix=contingency,
        lr_independence=lr_ind,
        p_value_independence=p_val_ind,
        decision_independence=dec_ind,
        lr_conditional_coverage=lr_cc,
        p_value_conditional_coverage=p_val_cc,
        decision_conditional_coverage=dec_cc,
        significance_level=significance_level,
        is_independent=is_ind,
        is_conditionally_calibrated=is_cond_cal,
        warnings=tuple(warnings),
        limitations=limitations,
    )


# ==============================================================================
# 5. Causal Rolling Walk-Forward Backtester
# ==============================================================================

def backtest_model_rolling(
    model: ModelPlugin | str,
    returns: Sequence[float] | np.ndarray,
    estimation_window: int = 250,
    confidence_level: float = 0.95,
    step_size: int = 1,
    var_metric_key: str = "var_95",
    es_metric_key: Optional[str] = "expected_shortfall_95",
    config: Optional[Mapping[str, Any]] = None,
    backtest_id: Optional[str] = None,
) -> BacktestReport:
    """Execute a strictly causal rolling walk-forward out-of-sample risk backtest.

    Temporal Integrity Guarantee:
        For each rolling origin t:
        - Estimation data: returns[t - estimation_window + 1 : t + 1] (strictly historical information).
        - Forecast target: return at t + 1 (period t+1).
        - Realized loss: L_{t+1} = -returns[t+1].
        - NO future observation after t is visible to the model during forecast generation.

    Args:
        model: Registered plugin ID (str) or ModelPlugin instance.
        returns: Chronologically ordered 1D sequence of simple returns.
        estimation_window: Number of historical periods used to calibrate model (default 250).
        confidence_level: Nominal VaR confidence level (default 0.95).
        step_size: Walk-forward step size in periods (default 1).
        var_metric_key: Metric key to extract from ModelExecutionResult (default 'var_95').
        es_metric_key: Optional metric key for Expected Shortfall.
        config: Additional configuration passed to plugin execution.
        backtest_id: Optional report identifier.

    Returns:
        BacktestReport containing aligned forecasts, breach evaluations, and statistical tests.
    """
    arr = np.asarray(returns, dtype=np.float64)
    if len(arr) < estimation_window + 5:
        raise ValueError(
            f"Backtest requires returns length >= estimation_window + 5 (minimum {estimation_window + 5}); got {len(arr)}"
        )
    if estimation_window < 10:
        raise ValueError(f"estimation_window must be >= 10; got {estimation_window}")
    if step_size < 1:
        raise ValueError(f"step_size must be >= 1; got {step_size}")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError(f"confidence_level must be in (0, 1); got {confidence_level}")

    # Resolve plugin
    if isinstance(model, str):
        registry = get_default_registry()
        plugin = registry.get(model)
        model_id = model
    elif isinstance(model, ModelPlugin):
        plugin = model
        model_id = model.metadata.plugin_id
    else:
        raise TypeError(f"model must be str or ModelPlugin; got {type(model).__name__}")

    cfg = dict(config) if config else {}
    cfg["confidence_level"] = confidence_level

    b_id = backtest_id or f"BT-{model_id.upper().replace('.', '-')}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    forecasts: List[VaRForecast] = []
    # Walk-forward loop: origin t runs from (estimation_window - 1) to (len(arr) - 2)
    # Target t+1 runs from estimation_window to len(arr) - 1
    t_start = estimation_window - 1
    t_end = len(arr) - 2

    for t in range(t_start, t_end + 1, step_size):
        # Strict historical window: [t - estimation_window + 1 : t + 1]
        window_data = arr[t - estimation_window + 1 : t + 1]
        res = plugin.execute(window_data, cfg)

        if var_metric_key not in res.metrics:
            raise KeyError(
                f"Model '{model_id}' did not output required VaR metric '{var_metric_key}'. Available: {list(res.metrics.keys())}"
            )

        var_val = float(res.metrics[var_metric_key])
        es_val = float(res.metrics[es_metric_key]) if es_metric_key and es_metric_key in res.metrics else None

        f_id = f"FC-{t:06d}->{t+1:06d}"
        forecasts.append(
            VaRForecast(
                forecast_id=f_id,
                origin_index=t,
                target_index=t + 1,
                horizon=1,
                confidence_level=confidence_level,
                var_estimate=var_val,
                expected_shortfall_estimate=es_val,
                model_id=model_id,
            )
        )

    # Evaluate breaches
    breach_evals = evaluate_var_breaches(forecasts, arr)
    breach_indicators = [b.is_breach for b in breach_evals]

    # Run statistical tests
    kupiec = calculate_kupiec_pof_test(breach_indicators, confidence_level=confidence_level)
    christoffersen = calculate_christoffersen_test(breach_indicators, confidence_level=confidence_level)

    # Cryptographic manifest
    manifest_data = {
        "backtest_id": b_id,
        "model_id": model_id,
        "model_version": plugin.metadata.plugin_version,
        "estimation_window": estimation_window,
        "confidence_level": confidence_level,
        "step_size": step_size,
        "evaluation_sample_size": len(breach_evals),
        "breach_count": kupiec.breach_count,
        "observed_breach_rate": kupiec.observed_rate,
        "nominal_rate": kupiec.nominal_rate,
        "kupiec_lr": kupiec.likelihood_ratio,
        "kupiec_p_value": kupiec.p_value,
        "christoffersen_lr_ind": christoffersen.lr_independence,
        "christoffersen_lr_cc": christoffersen.lr_conditional_coverage,
        "breach_hash": compute_canonical_hash([int(b) for b in breach_indicators]),
    }

    warnings: List[str] = list(kupiec.warnings) + list(christoffersen.warnings)
    limitations = (
        "Walk-forward rolling estimation assumes parameter stationary over the chosen estimation window.",
        "One-step-ahead backtesting does not validate multi-period compound loss forecasts.",
        "Model calibration accepts nominal coverage as non-rejection of null, which depends on sample statistical power.",
    )

    return BacktestReport(
        backtest_id=b_id,
        model_id=model_id,
        confidence_level=confidence_level,
        estimation_window=estimation_window,
        evaluation_sample_size=len(breach_evals),
        breach_count=kupiec.breach_count,
        observed_breach_rate=kupiec.observed_rate,
        nominal_rate=kupiec.nominal_rate,
        kupiec_test=kupiec,
        christoffersen_test=christoffersen,
        breach_evaluations=breach_evals,
        manifest=manifest_data,
        warnings=tuple(warnings),
        limitations=limitations,
    )
