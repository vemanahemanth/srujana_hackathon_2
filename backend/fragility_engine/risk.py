"""Risk calculation engine for FragilityShield.

Implements pure, deterministic functions for:
- Annualized Historical Volatility (sample standard deviation with configurable ddof and annualization factor)
- Historical Value at Risk (VaR at 95% and 99%, positive-loss convention, explicit empirical quantile)
- Historical Expected Shortfall (Conditional VaR / ES, coherent tail loss conditional expectation)
- Maximum Drawdown (peak-to-trough decline, positive loss fraction)
- Peak-to-Trough Duration & Recovery Duration analysis

Mathematical Conventions & Methodologies:
1. Input Data Types:
   - Returns functions accept simple arithmetic returns: r_t = p_t / p_{t-1} - 1.0.
   - Drawdown functions accept chronological portfolio-value / equity curves: V_t > 0.
2. Sign Convention:
   - Positive VaR and Expected Shortfall represent a LOSS magnitude (e.g. VaR=0.02 indicates a 2% loss).
   - Losses are defined as L = -R.
3. Volatility Annualization:
   - sigma_annual = sigma_daily * sqrt(annualization_factor), default annualization_factor=252.0.
   - Sample standard deviation uses Bessel's correction: ddof=1 by default.
4. Maximum Drawdown:
   - Expressed as a positive loss fraction on [0.0, 1.0]: MDD = (P_peak - V_trough) / P_peak.
   - Durations are measured in observation intervals (integer steps).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np


@dataclass(frozen=True)
class DrawdownResult:
    """Comprehensive analysis of maximum drawdown and duration dynamics.

    Attributes:
        max_drawdown: Maximum peak-to-trough decline as a positive loss fraction in [0.0, 1.0].
        peak_value: Portfolio equity value at the peak prior to the maximum drawdown trough.
        trough_value: Lowest portfolio equity value attained during the maximum drawdown episode.
        peak_index: Integer observation index of the peak.
        trough_index: Integer observation index of the trough.
        peak_to_trough_duration: Number of observation intervals from peak to trough (trough_index - peak_index).
        recovery_index: Index at which portfolio equity first re-attained or exceeded peak_value, or None if unrecovered.
        recovery_duration: Number of observation intervals from trough to recovery, or None if unrecovered.
        total_drawdown_duration: Number of observation intervals from peak to recovery, or None if unrecovered.
        is_recovered: True if the equity curve recovered to peak_value before the series ended, False otherwise.
        drawdown_series: 1D NumPy array representing the positive drawdown fraction at each observation point.
    """

    max_drawdown: float
    peak_value: float
    trough_value: float
    peak_index: int
    trough_index: int
    peak_to_trough_duration: int
    recovery_index: Optional[int]
    recovery_duration: Optional[int]
    total_drawdown_duration: Optional[int]
    is_recovered: bool
    drawdown_series: np.ndarray

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a serializable dictionary."""
        return {
            "max_drawdown": float(self.max_drawdown),
            "peak_value": float(self.peak_value),
            "trough_value": float(self.trough_value),
            "peak_index": int(self.peak_index),
            "trough_index": int(self.trough_index),
            "peak_to_trough_duration": int(self.peak_to_trough_duration),
            "recovery_index": int(self.recovery_index) if self.recovery_index is not None else None,
            "recovery_duration": int(self.recovery_duration) if self.recovery_duration is not None else None,
            "total_drawdown_duration": int(self.total_drawdown_duration) if self.total_drawdown_duration is not None else None,
            "is_recovered": bool(self.is_recovered),
            "drawdown_series": self.drawdown_series.tolist(),
        }


@dataclass(frozen=True)
class RiskMetricsReport:
    """Consolidated summary report of core financial risk metrics."""

    volatility_daily: float
    volatility_annualized: float
    var_95: float
    var_99: float
    expected_shortfall_95: float
    expected_shortfall_99: float
    drawdown: Optional[DrawdownResult]
    annualization_factor: float
    ddof: int
    observations_count: int
    warnings: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to serializable dictionary."""
        return {
            "volatility_daily": float(self.volatility_daily),
            "volatility_annualized": float(self.volatility_annualized),
            "var_95": float(self.var_95),
            "var_99": float(self.var_99),
            "expected_shortfall_95": float(self.expected_shortfall_95),
            "expected_shortfall_99": float(self.expected_shortfall_99),
            "drawdown": self.drawdown.to_dict() if self.drawdown is not None else None,
            "annualization_factor": float(self.annualization_factor),
            "ddof": int(self.ddof),
            "observations_count": int(self.observations_count),
            "warnings": list(self.warnings),
        }


def _validate_returns(returns: Sequence[float] | np.ndarray) -> np.ndarray:
    """Validate and copy a sequence of simple returns into a 1D float64 array.

    Raises:
        TypeError: If returns is None or not a sized sequence.
        ValueError: If returns has fewer than 2 elements, or contains non-finite numbers (NaN/Inf).
    """
    if returns is None:
        raise TypeError("returns sequence cannot be None")

    try:
        n_obs = len(returns)
    except TypeError as exc:
        raise TypeError(f"returns must be a sized sequence or array; got {type(returns)}") from exc

    if n_obs < 2:
        raise ValueError(f"Risk calculations require at least 2 return observations; received {n_obs}")

    cleaned: List[float] = []
    for idx, raw_val in enumerate(returns):
        if raw_val is None:
            raise ValueError(f"Return observation at index {idx} is None; missing values are rejected")
        try:
            val = float(raw_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Return at index {idx} could not be converted to float: {raw_val!r}") from exc

        if not math.isfinite(val):
            raise ValueError(f"Return at index {idx} must be finite (not NaN or Inf); got {val!r}")

        cleaned.append(val)

    return np.array(cleaned, dtype=np.float64, copy=True)


def _validate_equity_curve(equity: Sequence[float] | np.ndarray) -> np.ndarray:
    """Validate and copy a sequence of portfolio equity values into a 1D float64 array.

    Raises:
        TypeError: If equity is None or not a sized sequence.
        ValueError: If equity has fewer than 2 elements, or contains non-positive or non-finite values.
    """
    if equity is None:
        raise TypeError("equity curve cannot be None")

    try:
        n_obs = len(equity)
    except TypeError as exc:
        raise TypeError(f"equity must be a sized sequence or array; got {type(equity)}") from exc

    if n_obs < 2:
        raise ValueError(f"Drawdown calculation requires at least 2 equity observations; received {n_obs}")

    cleaned: List[float] = []
    for idx, raw_val in enumerate(equity):
        if raw_val is None:
            raise ValueError(f"Equity observation at index {idx} is None")
        try:
            val = float(raw_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Equity at index {idx} could not be converted to float: {raw_val!r}") from exc

        if not math.isfinite(val):
            raise ValueError(f"Equity at index {idx} must be finite (not NaN or Inf); got {val!r}")

        if val <= 0.0:
            raise ValueError(f"Equity at index {idx} must be strictly positive; got {val!r}")

        cleaned.append(val)

    return np.array(cleaned, dtype=np.float64, copy=True)


def calculate_annualized_volatility(
    returns: Sequence[float] | np.ndarray,
    annualization_factor: float = 252.0,
    ddof: int = 1,
) -> float:
    """Calculate annualized historical volatility from a sequence of periodic returns.

    Formula:
        sigma_periodic = sqrt( sum( (r_t - mean(r))^2 ) / (N - ddof) )
        sigma_annual = sigma_periodic * sqrt(annualization_factor)

    Args:
        returns: Sequence or array of periodic simple returns.
        annualization_factor: Number of return periods in an operating year (default 252.0 for daily trading days).
        ddof: Delta Degrees of Freedom (default 1 for sample standard deviation with Bessel's correction).

    Returns:
        Annualized volatility as a positive float.

    Raises:
        ValueError: If returns has fewer observations than (ddof + 1), contains non-finite values,
                    or annualization_factor is non-positive.
    """
    arr = _validate_returns(returns)

    if not math.isfinite(annualization_factor) or annualization_factor <= 0.0:
        raise ValueError(f"annualization_factor must be positive and finite; got {annualization_factor!r}")

    if not isinstance(ddof, int) or ddof < 0:
        raise ValueError(f"ddof must be a non-negative integer; got {ddof!r}")

    if len(arr) <= ddof:
        raise ValueError(
            f"Sample size N={len(arr)} must be strictly greater than ddof={ddof} to compute sample variance"
        )

    daily_std = float(np.std(arr, ddof=ddof))
    annual_std = daily_std * math.sqrt(annualization_factor)

    return annual_std


def calculate_historical_var(
    returns: Sequence[float] | np.ndarray,
    confidence_level: float = 0.95,
    method: str = "linear",
) -> float:
    """Calculate Historical Value at Risk (VaR) from returns.

    Sign Convention:
        VaR is reported as a POSITIVE LOSS fraction.
        E.g. VaR=0.03 means a 3% portfolio loss threshold.
        Losses are defined as L = -R.
        VaR_alpha = Quantile(L, alpha, method).

    Args:
        returns: Sequence or array of historical simple returns.
        confidence_level: Confidence level in range (0.0, 1.0), typically 0.95 or 0.99.
        method: Empirical quantile interpolation method supported by numpy.quantile
                ('linear', 'lower', 'higher', 'midpoint', 'nearest').

    Returns:
        Historical VaR as a float (positive indicates loss).

    Raises:
        ValueError: If confidence_level is not strictly in (0.0, 1.0) or inputs are invalid.
    """
    arr = _validate_returns(returns)

    if not isinstance(confidence_level, (int, float)) or isinstance(confidence_level, bool):
        raise ValueError(
            f"confidence_level must be strictly between 0.0 and 1.0; got {confidence_level!r}"
        )

    conf = float(confidence_level)
    if not math.isfinite(conf) or conf <= 0.0 or conf >= 1.0:
        raise ValueError(
            f"confidence_level must be strictly between 0.0 and 1.0; got {confidence_level!r}"
        )

    valid_methods = {"linear", "lower", "higher", "midpoint", "nearest"}
    if method not in valid_methods:
        raise ValueError(f"method must be one of {valid_methods}; got {method!r}")

    # Convert returns to losses: Loss = -Return
    losses = -arr

    # Empirical quantile of losses at confidence_level
    var_value = float(np.quantile(losses, conf, method=method))

    return var_value


def calculate_expected_shortfall(
    returns: Sequence[float] | np.ndarray,
    confidence_level: float = 0.95,
    method: str = "linear",
) -> float:
    """Calculate historical Expected Shortfall (Conditional Value at Risk / CVaR).

    Formula:
        Losses L = -R
        VaR = calculate_historical_var(returns, confidence_level, method)
        Tail losses = { L_i : L_i >= VaR }
        ES = mean(Tail losses)

    Sign Convention:
        Reported as a POSITIVE LOSS fraction.
        Guarantees ES >= VaR.

    Args:
        returns: Sequence or array of historical simple returns.
        confidence_level: Confidence level in range (0.0, 1.0), typically 0.95 or 0.99.
        method: Empirical quantile method used for the underlying VaR threshold.

    Returns:
        Expected Shortfall as a float (positive indicates loss).

    Raises:
        ValueError: If confidence_level is invalid or inputs contain non-finite values.
    """
    arr = _validate_returns(returns)

    # Validate confidence level and compute baseline VaR
    var_val = calculate_historical_var(arr, confidence_level=confidence_level, method=method)

    losses = -arr
    sorted_losses = np.sort(losses)
    n = len(sorted_losses)
    tail_prob = 1.0 - float(confidence_level)
    w = n * tail_prob

    # Acerbi & Tasche (2002) coherent discrete Expected Shortfall formulation
    if w <= 1.0:
        es_val = float(sorted_losses[-1])
    else:
        k = int(np.floor(w))
        frac = w - k
        sum_tail = float(np.sum(sorted_losses[-k:]))
        if frac > 1e-12:
            sum_tail += frac * float(sorted_losses[-k - 1])
        es_val = sum_tail / w

    # Coherence guarantee: ES must never be less than VaR
    return max(es_val, var_val)


def calculate_maximum_drawdown(equity_series: Sequence[float] | np.ndarray) -> DrawdownResult:
    """Calculate Maximum Drawdown (MDD) and duration statistics from an equity curve.

    Formula:
        Running Peak: P_t = max_{0 <= s <= t} V_s
        Drawdown Fraction: D_t = (P_t - V_t) / P_t >= 0.0
        MDD = max_{0 <= t < N} D_t

    Args:
        equity_series: Chronological sequence or array of portfolio equity values (all V_t > 0).

    Returns:
        DrawdownResult containing max drawdown magnitude, peak/trough values and indices,
        peak-to-trough duration, and recovery duration diagnostics.

    Raises:
        ValueError: If equity_series has fewer than 2 elements or contains non-positive/non-finite values.
    """
    arr = _validate_equity_curve(equity_series)
    n = len(arr)

    # Compute running maximum peak
    running_peaks = np.maximum.accumulate(arr)

    # Drawdown series as a positive fraction: (Peak - Value) / Peak
    drawdowns = (running_peaks - arr) / running_peaks

    # Identify trough of maximum drawdown
    # If multiple points share the exact same maximum drawdown, take the earliest occurrence
    max_dd = float(np.max(drawdowns))
    trough_idx = int(np.argmax(drawdowns))

    # If maximum drawdown is zero (monotonically non-decreasing series)
    if math.isclose(max_dd, 0.0, abs_tol=1e-12):
        return DrawdownResult(
            max_drawdown=0.0,
            peak_value=float(arr[0]),
            trough_value=float(arr[0]),
            peak_index=0,
            trough_index=0,
            peak_to_trough_duration=0,
            recovery_index=0,
            recovery_duration=0,
            total_drawdown_duration=0,
            is_recovered=True,
            drawdown_series=drawdowns,
        )

    # Identify the corresponding peak prior to or at the trough
    # Peak index is the index of the running peak value leading to this trough
    peak_val = float(running_peaks[trough_idx])
    trough_val = float(arr[trough_idx])

    # Find the earliest index where arr equals peak_val prior to trough_idx
    peak_idx = int(np.where(arr[: trough_idx + 1] == peak_val)[0][-1])

    peak_to_trough_duration = trough_idx - peak_idx

    # Check for recovery after trough_idx
    recovery_idx: Optional[int] = None
    is_recovered = False
    recovery_duration: Optional[int] = None
    total_drawdown_duration: Optional[int] = None

    if trough_idx < n - 1:
        # Search for first point where equity reaches or exceeds peak_val
        post_trough = arr[trough_idx + 1 :]
        recovered_indices = np.where(post_trough >= peak_val)[0]
        if len(recovered_indices) > 0:
            recovery_idx = int(trough_idx + 1 + recovered_indices[0])
            is_recovered = True
            recovery_duration = recovery_idx - trough_idx
            total_drawdown_duration = recovery_idx - peak_idx

    return DrawdownResult(
        max_drawdown=max_dd,
        peak_value=peak_val,
        trough_value=trough_val,
        peak_index=peak_idx,
        trough_index=trough_idx,
        peak_to_trough_duration=peak_to_trough_duration,
        recovery_index=recovery_idx,
        recovery_duration=recovery_duration,
        total_drawdown_duration=total_drawdown_duration,
        is_recovered=is_recovered,
        drawdown_series=drawdowns,
    )


def calculate_risk_report(
    returns: Sequence[float] | np.ndarray,
    equity_series: Optional[Sequence[float] | np.ndarray] = None,
    annualization_factor: float = 252.0,
    ddof: int = 1,
) -> RiskMetricsReport:
    """Compute a consolidated risk metrics report from returns and optional equity curve.

    Args:
        returns: Sequence or array of periodic simple returns.
        equity_series: Optional chronological equity curve. If None, reconstructed from returns
                       starting from baseline 1.0: V_t = 1.0 * cumprod(1 + r_t).
        annualization_factor: Annualization multiplier for volatility (default 252.0).
        ddof: Degrees of freedom for sample standard deviation (default 1).

    Returns:
        RiskMetricsReport instance.
    """
    arr_returns = _validate_returns(returns)
    n = len(arr_returns)
    warnings: List[str] = []

    # Small sample caveats
    if n < 20:
        warnings.append(
            f"Sample size N={n} is small for 95% VaR (rule-of-thumb N >= 20); quantile estimates may have high variance."
        )
    if n < 100:
        warnings.append(
            f"Sample size N={n} is insufficient for reliable 99% VaR/ES (rule-of-thumb N >= 100); tail may lack observations."
        )

    vol_daily = float(np.std(arr_returns, ddof=ddof))
    vol_annual = vol_daily * math.sqrt(annualization_factor)

    var_95 = calculate_historical_var(arr_returns, confidence_level=0.95)
    var_99 = calculate_historical_var(arr_returns, confidence_level=0.99)

    es_95 = calculate_expected_shortfall(arr_returns, confidence_level=0.95)
    es_99 = calculate_expected_shortfall(arr_returns, confidence_level=0.99)

    dd_res: Optional[DrawdownResult] = None
    if equity_series is not None:
        dd_res = calculate_maximum_drawdown(equity_series)
    else:
        # Reconstruct synthetic normalized equity curve starting at 1.0
        # Cumulative growth: V_0 = 1.0, V_{t+1} = V_t * (1 + r_t)
        eq_curve = np.empty(n + 1, dtype=np.float64)
        eq_curve[0] = 1.0
        for i, r in enumerate(arr_returns):
            eq_curve[i + 1] = eq_curve[i] * (1.0 + r)
            if eq_curve[i + 1] <= 0.0:
                warnings.append("Cumulative return dropped portfolio equity to zero or negative; drawdown halted.")
                break
        if np.all(eq_curve > 0.0):
            dd_res = calculate_maximum_drawdown(eq_curve)

    return RiskMetricsReport(
        volatility_daily=vol_daily,
        volatility_annualized=vol_annual,
        var_95=var_95,
        var_99=var_99,
        expected_shortfall_95=es_95,
        expected_shortfall_99=es_99,
        drawdown=dd_res,
        annualization_factor=annualization_factor,
        ddof=ddof,
        observations_count=n,
        warnings=tuple(warnings),
    )
