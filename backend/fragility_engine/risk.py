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
import scipy.stats as stats


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


calculate_volatility = calculate_annualized_volatility


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


def calculate_parametric_var(
    returns: Sequence[float] | np.ndarray,
    confidence_level: float = 0.95,
    assume_zero_mean: bool = False,
    ddof: int = 1,
) -> float:
    """Calculate Analytical Parametric Value at Risk (VaR) assuming normally distributed returns.

    Sign Convention & Mathematical Formulation:
        - Input returns R_t = P_t / P_{t-1} - 1.0.
        - Losses are defined as L = -R.
        - For returns R ~ N(mu, sigma^2), L ~ N(-mu, sigma^2).
        - Under the POSITIVE LOSS convention (e.g. VaR=0.03 denotes a 3% loss threshold):
            VaR_alpha = -mu + z_alpha * sigma
          where z_alpha = Phi^{-1}(alpha) is the alpha-quantile of standard normal distribution.
        - If assume_zero_mean is True (RiskMetrics daily horizon convention):
            VaR_alpha = z_alpha * sigma

    Standard Normal Quantile Reference Values:
        - alpha = 0.90: z = 1.2815515655
        - alpha = 0.95: z = 1.6448536269
        - alpha = 0.99: z = 2.3263478740
        - alpha = 0.999: z = 3.0902323061

    Args:
        returns: Sequence or array of historical periodic returns.
        confidence_level: VaR confidence level alpha in (0.0, 1.0), default 0.95.
        assume_zero_mean: If True, fixes mu = 0.0 (unconditional zero-drift assumption).
        ddof: Degrees of freedom delta for sample standard deviation (default 1 for Bessel correction; 0 for population).

    Returns:
        Parametric VaR as a positive loss float.

    Raises:
        ValueError: If confidence_level is not strictly in (0.0, 1.0) or returns has <= ddof observations.
        TypeError: If returns is None or not a sized sequence.
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

    if not isinstance(ddof, int) or ddof < 0:
        raise ValueError(f"ddof must be a non-negative integer; got {ddof!r}")

    if len(arr) <= ddof:
        raise ValueError(
            f"Sample size N={len(arr)} must be strictly greater than ddof={ddof} to compute sample variance"
        )

    mu = 0.0 if assume_zero_mean else float(np.mean(arr))
    sigma = float(np.std(arr, ddof=ddof))

    z_alpha = float(stats.norm.ppf(conf))
    var_value = -mu + z_alpha * sigma
    return float(var_value)


def calculate_parametric_es(
    returns: Sequence[float] | np.ndarray,
    confidence_level: float = 0.95,
    assume_zero_mean: bool = False,
    ddof: int = 1,
) -> float:
    """Calculate Analytical Parametric Expected Shortfall (CVaR) assuming normally distributed returns.

    Mathematical Formulation:
        For R ~ N(mu, sigma^2) and losses L = -R ~ N(-mu, sigma^2):
            ES_alpha = E[L | L >= VaR_alpha]
                     = -mu + sigma * phi(z_alpha) / (1 - alpha)
        where phi(z) = (1 / sqrt(2*pi)) * exp(-0.5 * z^2) is the standard normal PDF,
        and z_alpha = Phi^{-1}(alpha).

    Coherence Guarantee:
        Since phi(z) / (1 - alpha) > z for all alpha in (0, 1),
        Parametric ES is strictly greater than Parametric VaR (ES > VaR).

    Args:
        returns: Sequence or array of historical periodic returns.
        confidence_level: Confidence level in (0.0, 1.0), default 0.95.
        assume_zero_mean: If True, fixes mu = 0.0.
        ddof: Delta Degrees of Freedom (default 1 for sample standard deviation).

    Returns:
        Parametric Expected Shortfall as a positive loss float.
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

    if not isinstance(ddof, int) or ddof < 0:
        raise ValueError(f"ddof must be a non-negative integer; got {ddof!r}")

    if len(arr) <= ddof:
        raise ValueError(
            f"Sample size N={len(arr)} must be strictly greater than ddof={ddof} to compute sample variance"
        )

    mu = 0.0 if assume_zero_mean else float(np.mean(arr))
    sigma = float(np.std(arr, ddof=ddof))

    z_alpha = float(stats.norm.ppf(conf))
    phi_z = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * z_alpha * z_alpha)
    tail_prob = 1.0 - conf

    es_value = -mu + sigma * (phi_z / tail_prob)
    return float(es_value)


def calculate_expected_shortfall(
    returns: Sequence[float] | np.ndarray,
    confidence_level: float = 0.95,
    method: str = "linear",
) -> float:
    """Calculate historical Expected Shortfall (Conditional Value at Risk / CVaR).

    Mathematical Framework & Conventions:
    1. Return & Loss Sign Convention:
       - Inputs are arithmetic simple returns R_t = P_t / P_{t-1} - 1.0.
       - Losses are defined as L_t = -R_t.
       - VaR and Expected Shortfall are reported as POSITIVE LOSS fractions
         (e.g., ES = 0.025 represents an expected loss of 2.5% in the tail).
    2. Confidence-Level Semantics:
       - confidence_level (alpha) must be strictly in (0.0, 1.0), typically 0.95 or 0.99.
       - The tail probability is tail_prob = 1.0 - alpha (e.g. 0.05 for alpha=0.95).
    3. Discrete Tail Inclusion & Weighting (Acerbi & Tasche, 2002):
       - Let L_{(1)} <= L_{(2)} <= ... <= L_{(n)} be the sorted losses.
       - The nominal tail observation count is w = n * tail_prob.
       - In IEEE 754 floating-point arithmetic, w can differ from an integer by machine epsilon
         (e.g., 20 * (1.0 - 0.95) = 1.0000000000000009).
       - To ensure numerical stability, if w is within tolerance (1e-11) of an integer k_int:
           * If k_int <= 1: the tail contains at most one observation; ES evaluates to L_{(n)}.
           * If k_int > 1: the tail contains the k_int worst losses; ES = mean(L_{(n - k_int + 1)} : L_{(n)}).
       - If w is genuinely fractional and w > 1.0:
           * k = floor(w), frac = w - k.
           * Tail sum = sum(k worst losses) + frac * (k+1)-th worst loss.
           * ES = Tail sum / w.
       - If w is genuinely fractional and w < 1.0 (small sample with tail < 1 observation):
           * The tail covers fewer than 1 observation; ES evaluates to L_{(n)} (the worst loss).
    4. Small Samples, Ties, & Constant Returns:
       - For constant returns R_t = c, all L_t = -c, and ES evaluates identically to -c.
       - For samples with ties at the quantile boundary, the fractional weight is applied to
         the next ordered loss, maintaining convex combination properties.
       - Non-finite observations (NaN, +Inf, -Inf) are strictly rejected by _validate_returns.
    5. Coherence Guarantee:
       - By definition, ES >= VaR for any sample and confidence level.

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

    # Check if w is numerically within machine epsilon of an integer
    k_round = round(w)
    if math.isclose(w, k_round, rel_tol=1e-9, abs_tol=1e-11):
        if k_round <= 1:
            es_val = float(sorted_losses[-1])
        else:
            es_val = float(np.mean(sorted_losses[-k_round:]))
    elif w < 1.0:
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


def calculate_rolling_volatility(
    returns: Sequence[float] | np.ndarray,
    window: int = 30,
    annualization_factor: float = 252.0,
    ddof: int = 1,
) -> np.ndarray:
    """Compute rolling window annualized volatility series.

    Args:
        returns: Sequence or 1D array of periodic returns.
        window: Integer rolling window size (>= 2).
        annualization_factor: Annualization multiplier (default 252.0).
        ddof: Degrees of freedom adjustment for sample standard deviation (default 1).

    Returns:
        1D NumPy array of length len(returns) - window + 1 containing annualized rolling volatilities.
    """
    arr = _validate_returns(returns)
    if not isinstance(window, int) or window < 2:
        raise ValueError(f"window must be an integer >= 2; got {window!r}")
    if len(arr) < window:
        raise ValueError(f"returns length ({len(arr)}) must be >= rolling window ({window})")

    n_out = len(arr) - window + 1
    rolling_vols = np.empty(n_out, dtype=np.float64)
    ann_mult = math.sqrt(annualization_factor)

    for i in range(n_out):
        chunk = arr[i : i + window]
        rolling_vols[i] = float(np.std(chunk, ddof=ddof)) * ann_mult

    return rolling_vols


def calculate_sharpe_ratio(
    returns: Sequence[float] | np.ndarray,
    risk_free_rate: float = 0.06,
    annualization_factor: float = 252.0,
) -> float:
    """Compute annualized Sharpe Ratio using configurable annual risk-free rate.

    Formula:
        Sharpe = (mean_annual_return - risk_free_rate) / annualized_volatility
        where mean_annual_return = mean(returns) * annualization_factor

    Args:
        returns: Sequence or 1D array of periodic returns.
        risk_free_rate: Annualized risk-free rate (e.g. 0.06 for 6% annual risk-free rate).
        annualization_factor: Trading days per year (default 252.0).

    Returns:
        Annualized Sharpe ratio. Returns 0.0 if annualized volatility is 0.
    """
    arr = _validate_returns(returns)
    if not math.isfinite(risk_free_rate):
        raise ValueError(f"risk_free_rate must be finite; got {risk_free_rate!r}")

    mean_ret = float(np.mean(arr))
    vol = float(np.std(arr, ddof=1))

    annual_ret = mean_ret * annualization_factor
    annual_vol = vol * math.sqrt(annualization_factor)

    if annual_vol <= 1e-12:
        return 0.0

    return float((annual_ret - risk_free_rate) / annual_vol)


def calculate_downside_deviation(
    returns: Sequence[float] | np.ndarray,
    target_return: float = 0.0,
    ddof: int = 1,
) -> float:
    """Compute downside standard deviation below a target return threshold.

    Formula:
        delta_down = sqrt( 1/(N - ddof) * sum( min(0, r_t - r_target)^2 ) )

    Args:
        returns: Sequence or 1D array of periodic returns.
        target_return: Minimum acceptable return (default 0.0).
        ddof: Degrees of freedom adjustment (default 1).

    Returns:
        Non-negative downside deviation.
    """
    arr = _validate_returns(returns)
    n = len(arr)
    if n <= ddof:
        raise ValueError(f"Sample size N={n} must be greater than ddof={ddof}")

    deviations = np.minimum(0.0, arr - target_return)
    sum_sq = float(np.sum(deviations ** 2))
    return math.sqrt(sum_sq / (n - ddof))


def calculate_sortino_ratio(
    returns: Sequence[float] | np.ndarray,
    risk_free_rate: float = 0.06,
    annualization_factor: float = 252.0,
    target_return: Optional[float] = None,
    required_return: Optional[float] = None,
) -> float:
    """Compute annualized Sortino Ratio penalizing only downside volatility.

    Formula:
        Sortino = (annual_mean_return - risk_free_rate) / (downside_deviation * sqrt(annualization_factor))
    """
    arr = _validate_returns(returns)
    eff_target = required_return if required_return is not None else target_return
    daily_rf = (1.0 + risk_free_rate) ** (1.0 / annualization_factor) - 1.0 if eff_target is None else eff_target

    mean_ret = float(np.mean(arr))
    annual_mean = mean_ret * annualization_factor

    downside_dev = calculate_downside_deviation(arr, target_return=daily_rf, ddof=1)
    annual_downside = downside_dev * math.sqrt(annualization_factor)

    if annual_downside <= 1e-12:
        return 0.0

    return float((annual_mean - risk_free_rate) / annual_downside)


def calculate_calmar_ratio(
    returns: Sequence[float] | np.ndarray,
    max_drawdown: Optional[float] = None,
    annualization_factor: float = 252.0,
) -> float:
    """Compute Calmar Ratio (annualized return divided by maximum drawdown).

    Formula:
        Calmar = annualized_mean_return / max_drawdown

    Args:
        returns: Sequence or 1D array of periodic returns.
        max_drawdown: Optional pre-calculated maximum drawdown fraction. If None, calculated from returns.
        annualization_factor: Trading periods per year (default 252.0).

    Returns:
        Calmar ratio. Returns 0.0 if maximum drawdown is 0.0.
    """
    arr = _validate_returns(returns)
    annual_mean = float(np.mean(arr)) * annualization_factor

    mdd = max_drawdown
    if mdd is None:
        rep = calculate_risk_report(arr, annualization_factor=annualization_factor)
        mdd = rep.drawdown.max_drawdown if rep.drawdown else 0.0

    if mdd <= 1e-8:
        return 0.0

    return float(annual_mean / mdd)


def calculate_semivariance(
    returns: Sequence[float] | np.ndarray,
    threshold: Optional[float] = None,
) -> float:
    """Compute downside semi-variance below a threshold (default sample mean).

    Args:
        returns: Sequence or 1D array of periodic returns.
        threshold: Reference threshold. If None, sample mean is used.

    Returns:
        Sample semi-variance.
    """
    arr = _validate_returns(returns)
    ref = float(np.mean(arr)) if threshold is None else float(threshold)
    deviations = np.minimum(0.0, arr - ref)
    return float(np.mean(deviations ** 2))


def calculate_covariance_matrix(
    returns_matrix: Sequence[Sequence[float]] | np.ndarray,
    ddof: int = 1,
) -> np.ndarray:
    """Compute the empirical covariance matrix from an (N_samples x K_assets) returns matrix.

    Args:
        returns_matrix: 2D array of returns where rows are time periods and columns are assets.
        ddof: Degrees of freedom (default 1 for sample covariance).

    Returns:
        (K x K) symmetric, positive semi-definite covariance matrix.
    """
    mat = np.asarray(returns_matrix, dtype=np.float64)
    if mat.ndim != 2:
        raise ValueError(f"returns_matrix must be a 2D array; got shape {mat.shape}")
    if mat.shape[0] < 2:
        raise ValueError(f"Need at least 2 time observations; got {mat.shape[0]}")
    if not np.all(np.isfinite(mat)):
        raise ValueError("returns_matrix contains non-finite numbers (NaN/Inf)")

    return np.cov(mat, rowvar=False, ddof=ddof)


def calculate_correlation_matrix(
    returns_matrix: Sequence[Sequence[float]] | np.ndarray,
) -> np.ndarray:
    """Compute the empirical correlation matrix from an (N_samples x K_assets) returns matrix.

    Args:
        returns_matrix: 2D array of returns.

    Returns:
        (K x K) correlation matrix with diagonal 1.0 and off-diagonal elements in [-1.0, 1.0].
    """
    cov = calculate_covariance_matrix(returns_matrix, ddof=1)
    d = np.diag(cov)
    std = np.sqrt(np.maximum(1e-12, d))
    outer_std = np.outer(std, std)
    corr = cov / outer_std
    np.fill_diagonal(corr, 1.0)
    return np.clip(corr, -1.0, 1.0)


def calculate_beta(
    asset_returns: Sequence[float] | np.ndarray,
    benchmark_returns: Sequence[float] | np.ndarray,
) -> float:
    """Compute CAPM Beta of an asset or portfolio against a benchmark index.

    Formula:
        beta = Cov(R_p, R_m) / Var(R_m)

    Args:
        asset_returns: 1D array of portfolio returns.
        benchmark_returns: 1D array of benchmark market returns (same length).

    Returns:
        Regression Beta. Returns 1.0 if benchmark variance is zero.
    """
    r_p = _validate_returns(asset_returns)
    r_m = _validate_returns(benchmark_returns)

    if len(r_p) != len(r_m):
        raise ValueError(f"asset_returns ({len(r_p)}) and benchmark_returns ({len(r_m)}) must have identical lengths")

    var_m = float(np.var(r_m, ddof=1))
    if var_m <= 1e-12:
        return 1.0

    cov_pm = float(np.cov(r_p, r_m, ddof=1)[0, 1])
    return float(cov_pm / var_m)


def calculate_capture_ratios(
    asset_returns: Sequence[float] | np.ndarray,
    benchmark_returns: Sequence[float] | np.ndarray,
) -> Tuple[float, float]:
    """Compute Upside and Downside capture ratios against a benchmark index.

    Formula:
        Up Capture = mean(R_p | R_m > 0) / mean(R_m | R_m > 0)
        Down Capture = mean(R_p | R_m < 0) / mean(R_m | R_m < 0)

    Args:
        asset_returns: 1D array of asset returns.
        benchmark_returns: 1D array of benchmark returns.

    Returns:
        Tuple of (upside_capture, downside_capture).
    """
    r_p = _validate_returns(asset_returns)
    r_m = _validate_returns(benchmark_returns)

    if len(r_p) != len(r_m):
        raise ValueError(f"Lengths must match: asset={len(r_p)}, benchmark={len(r_m)}")

    up_mask = r_m > 0.0
    down_mask = r_m < 0.0

    up_capture = 1.0
    if np.any(up_mask):
        mean_p_up = float(np.mean(r_p[up_mask]))
        mean_m_up = float(np.mean(r_m[up_mask]))
        if abs(mean_m_up) > 1e-12:
            up_capture = mean_p_up / mean_m_up

    down_capture = 1.0
    if np.any(down_mask):
        mean_p_down = float(np.mean(r_p[down_mask]))
        mean_m_down = float(np.mean(r_m[down_mask]))
        if abs(mean_m_down) > 1e-12:
            down_capture = mean_p_down / mean_m_down

    return float(up_capture), float(down_capture)


# Public alias for consistency
RiskReport = RiskMetricsReport
