"""Data Lab & Statistical Diagnostics Engine.

Provides empirical data quality assessment and hypothesis testing for financial return series:
- Higher moments: Sample Skewness and Excess Kurtosis.
- Jarque-Bera Normality Test with exact Chi-Square p-values.
- First-order Autocorrelation ($\rho_1$) checking i.i.d. preconditions.
- Zero-return frequency checking for liquidity or stale-pricing issues.
- Automated model suitability verdicts and parameter recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple
import numpy as np


@dataclass(frozen=True)
class DataQualityReport:
    """Consolidated statistical diagnostic report for an input return series."""

    observations_count: int
    mean: float
    std_dev: float
    annualized_volatility: float
    skewness: float
    excess_kurtosis: float
    jarque_bera_stat: float
    jarque_bera_p_value: float
    is_normal_at_5pct: bool
    autocorrelation_lag1: float
    zero_returns_pct: float
    min_return: float
    max_return: float
    suitability_verdict: str
    warnings: Tuple[str, ...]
    recommendations: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to serializable dictionary."""
        return {
            "observations_count": int(self.observations_count),
            "mean": float(self.mean),
            "std_dev": float(self.std_dev),
            "annualized_volatility": float(self.annualized_volatility),
            "skewness": float(self.skewness),
            "excess_kurtosis": float(self.excess_kurtosis),
            "jarque_bera_stat": float(self.jarque_bera_stat),
            "jarque_bera_p_value": float(self.jarque_bera_p_value),
            "is_normal_at_5pct": bool(self.is_normal_at_5pct),
            "autocorrelation_lag1": float(self.autocorrelation_lag1),
            "zero_returns_pct": float(self.zero_returns_pct),
            "min_return": float(self.min_return),
            "max_return": float(self.max_return),
            "suitability_verdict": self.suitability_verdict,
            "warnings": list(self.warnings),
            "recommendations": list(self.recommendations),
        }


def calculate_data_diagnostics(
    returns: Sequence[float],
    annualization_factor: float = 252.0,
) -> DataQualityReport:
    """Compute empirical statistical diagnostics and normality test on return series.

    Args:
        returns: Sequence of numerical return observations.
        annualization_factor: Annualization multiplier (default 252.0).

    Returns:
        DataQualityReport containing sample moments, test statistics, and recommendations.

    Raises:
        ValueError: If returns is empty, contains non-finite values, or has fewer than 8 observations.
    """
    if returns is None:
        raise TypeError("returns cannot be None")

    arr = np.asarray(returns, dtype=np.float64)
    if arr.size == 0:
        raise ValueError("Cannot compute diagnostics on an empty return series")
    if not np.all(np.isfinite(arr)):
        raise ValueError("Return series contains non-finite values (NaN or Inf)")

    n = len(arr)
    if n < 8:
        raise ValueError(f"Diagnostics require at least 8 observations; got {n}")

    mean_val = float(np.mean(arr))
    # Unbiased sample variance with Bessel's correction
    variance_val = float(np.var(arr, ddof=1))
    std_val = math.sqrt(variance_val)
    ann_vol = std_val * math.sqrt(annualization_factor)

    # Higher central moments
    devs = arr - mean_val
    m2 = float(np.mean(devs ** 2))
    m3 = float(np.mean(devs ** 3))
    m4 = float(np.mean(devs ** 4))

    # Sample skewness and excess kurtosis
    if m2 > 1e-14:
        skewness = m3 / (m2 ** 1.5)
        excess_kurtosis = (m4 / (m2 ** 2.0)) - 3.0
    else:
        skewness = 0.0
        excess_kurtosis = 0.0

    # Jarque-Bera Test Statistic: JB = (N/6) * (S^2 + (K^2 / 4))
    # Under H0 (normal distribution), JB asymptotically follows Chi-Square with 2 degrees of freedom.
    jb_stat = (n / 6.0) * (skewness ** 2 + (excess_kurtosis ** 2) / 4.0)

    # For Chi-Square with df=2, the survival function (p-value) is exact: P(X >= x) = exp(-x / 2)
    jb_p_value = math.exp(-0.5 * jb_stat)
    is_normal = bool(jb_p_value >= 0.05)

    # Autocorrelation lag-1: rho_1 = sum((r_t - mean)*(r_{t-1} - mean)) / sum((r_t - mean)^2)
    if n > 1 and m2 > 1e-14:
        devs_t = devs[1:]
        devs_t_minus_1 = devs[:-1]
        denom = float(np.sum(devs ** 2))
        autocorr_1 = float(np.sum(devs_t * devs_t_minus_1) / denom)
    else:
        autocorr_1 = 0.0

    zero_returns_count = int(np.count_nonzero(np.isclose(arr, 0.0, atol=1e-8)))
    zero_returns_pct = (zero_returns_count / n) * 100.0

    min_ret = float(np.min(arr))
    max_ret = float(np.max(arr))

    # Automated suitability analysis
    warnings: List[str] = []
    recommendations: List[str] = []

    if not is_normal:
        warnings.append(
            f"Jarque-Bera rejects normality at 5% significance level (JB={jb_stat:.2f}, p={jb_p_value:.4e}). "
            f"Parametric Gaussian models will underestimate extreme tail losses."
        )
        if excess_kurtosis > 1.0:
            recommendations.append(
                f"Excess kurtosis ({excess_kurtosis:.2f} > 0) indicates heavy tails. Use Student-t or Historical Simulation."
            )
        if abs(skewness) > 0.5:
            recommendations.append(
                f"Asymmetric return skewness ({skewness:.2f}) observed. Consider Cornish-Fisher expansion to capture tail asymmetry."
            )

    if abs(autocorr_1) > 0.15:
        warnings.append(
            f"Statistically notable lag-1 autocorrelation detected (rho_1={autocorr_1:.3f}). "
            f"Violates i.i.d. returns assumption; standard historical simulation may underestimate clustered risks."
        )
        recommendations.append("Apply RiskMetrics EWMA or GARCH filtering to account for volatility clustering.")

    if zero_returns_pct > 10.0:
        warnings.append(
            f"High zero-return frequency ({zero_returns_pct:.1f}%). May indicate illiquid assets or stale price feeds."
        )

    if n < 30:
        warnings.append(
            f"Small sample size (N={n}). VaR and Expected Shortfall quantiles will have elevated sampling variance."
        )

    if not is_normal and excess_kurtosis > 1.0:
        verdict = "FAT_TAILS_USE_T_OR_HISTORICAL"
    elif abs(autocorr_1) > 0.15:
        verdict = "AUTOCORRELATED_VIOLATES_IID"
    elif n < 30:
        verdict = "SMALL_SAMPLE_CAUTION"
    elif is_normal:
        verdict = "NORMAL_DISTRIBUTION_ACCEPTED"
    else:
        verdict = "NON_NORMAL_GENERAL"

    return DataQualityReport(
        observations_count=n,
        mean=mean_val,
        std_dev=std_val,
        annualized_volatility=ann_vol,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
        jarque_bera_stat=jb_stat,
        jarque_bera_p_value=jb_p_value,
        is_normal_at_5pct=is_normal,
        autocorrelation_lag1=autocorr_1,
        zero_returns_pct=zero_returns_pct,
        min_return=min_ret,
        max_return=max_ret,
        suitability_verdict=verdict,
        warnings=tuple(warnings),
        recommendations=tuple(recommendations),
    )


# ==============================================================================
# Lab 1 — Project & Data Lab: Comprehensive Data Quality & Financial Validation
# ==============================================================================

@dataclass(frozen=True)
class OHLCVCandleReport:
    """Validation report for financial Open-High-Low-Close-Volume (OHLCV) market series."""

    total_candles: int
    valid_candles: int
    invalid_candles: int
    is_valid: bool
    negative_prices_count: int
    high_low_violations: int
    open_close_out_of_bounds: int
    negative_volume_count: int
    duplicate_timestamps_count: int
    warnings: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_candles": self.total_candles,
            "valid_candles": self.valid_candles,
            "invalid_candles": self.invalid_candles,
            "is_valid": self.is_valid,
            "negative_prices_count": self.negative_prices_count,
            "high_low_violations": self.high_low_violations,
            "open_close_out_of_bounds": self.open_close_out_of_bounds,
            "negative_volume_count": self.negative_volume_count,
            "duplicate_timestamps_count": self.duplicate_timestamps_count,
            "warnings": list(self.warnings),
        }


def validate_financial_ohlcv(
    candles: Sequence[Mapping[str, Any]],
) -> OHLCVCandleReport:
    """Validate financial OHLCV candlestick records for price integrity and physical bounds.

    Rules checked:
    1. All prices (Open, High, Low, Close) must be strictly positive (> 0).
    2. High must be >= Low for every candle.
    3. Open and Close must be within the [Low, High] range.
    4. Volume must be >= 0.
    5. Timestamps must not contain duplicates.
    """
    total = len(candles)
    if total == 0:
        raise ValueError("Cannot validate empty candle sequence")

    neg_prices = 0
    hl_violations = 0
    oc_out_of_bounds = 0
    neg_volume = 0
    seen_timestamps = set()
    dup_timestamps = 0
    warnings: List[str] = []

    for idx, c in enumerate(candles):
        # Timestamp check
        ts = c.get("timestamp") or c.get("date") or c.get("time")
        if ts is not None:
            if ts in seen_timestamps:
                dup_timestamps += 1
            seen_timestamps.add(ts)

        try:
            o = float(c["open"])
            h = float(c["high"])
            l = float(c["low"])
            cl = float(c["close"])
            v = float(c.get("volume", 0.0))
        except (KeyError, TypeError, ValueError) as err:
            warnings.append(f"Candle at index {idx} has missing or unparseable fields: {err}")
            neg_prices += 1
            continue

        if o <= 0.0 or h <= 0.0 or l <= 0.0 or cl <= 0.0:
            neg_prices += 1

        if h < l:
            hl_violations += 1

        if not (l <= o <= h) or not (l <= cl <= h):
            oc_out_of_bounds += 1

        if v < 0.0:
            neg_volume += 1

    invalid = neg_prices + hl_violations + oc_out_of_bounds + neg_volume + dup_timestamps
    is_valid = (invalid == 0)

    if neg_prices > 0:
        warnings.append(f"Detected {neg_prices} candles with non-positive price values.")
    if hl_violations > 0:
        warnings.append(f"Detected {hl_violations} candles where High < Low (physically impossible).")
    if oc_out_of_bounds > 0:
        warnings.append(f"Detected {oc_out_of_bounds} candles where Open or Close lies outside [Low, High].")
    if neg_volume > 0:
        warnings.append(f"Detected {neg_volume} candles with negative trading volume.")
    if dup_timestamps > 0:
        warnings.append(f"Detected {dup_timestamps} duplicate timestamp keys.")

    return OHLCVCandleReport(
        total_candles=total,
        valid_candles=total - (1 if invalid > 0 else 0),
        invalid_candles=invalid,
        is_valid=is_valid,
        negative_prices_count=neg_prices,
        high_low_violations=hl_violations,
        open_close_out_of_bounds=oc_out_of_bounds,
        negative_volume_count=neg_volume,
        duplicate_timestamps_count=dup_timestamps,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class TabularSchemaReport:
    """Schema, completeness, and missingness audit for a tabular dataset."""

    row_count: int
    column_count: int
    columns: Tuple[str, ...]
    missing_counts: Mapping[str, int]
    missing_percentages: Mapping[str, float]
    duplicate_rows_count: int
    non_numeric_violations: Mapping[str, int]
    is_schema_valid: bool
    warnings: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": list(self.columns),
            "missing_counts": dict(self.missing_counts),
            "missing_percentages": dict(self.missing_percentages),
            "duplicate_rows_count": self.duplicate_rows_count,
            "non_numeric_violations": dict(self.non_numeric_violations),
            "is_schema_valid": self.is_schema_valid,
            "warnings": list(self.warnings),
        }


def validate_tabular_dataset(
    records: Sequence[Mapping[str, Any]],
    required_columns: Sequence[str] = (),
    expected_numeric: Sequence[str] = (),
) -> TabularSchemaReport:
    """Perform schema validation, missingness audit, duplicate check, and numeric type verification."""
    n_rows = len(records)
    if n_rows == 0:
        raise ValueError("Cannot audit an empty tabular dataset")

    # Discover columns
    all_cols = sorted({k for r in records for k in r.keys()})
    missing_counts: Dict[str, int] = {c: 0 for c in all_cols}
    non_num_counts: Dict[str, int] = {c: 0 for c in expected_numeric}
    warnings: List[str] = []

    # Check required columns
    for req in required_columns:
        if req not in all_cols:
            warnings.append(f"Required column '{req}' is completely missing from dataset schema.")

    seen_hashes = set()
    dup_rows = 0

    for r in records:
        # Check row uniqueness
        row_tuple = tuple((k, str(r.get(k))) for k in all_cols)
        h = hash(row_tuple)
        if h in seen_hashes:
            dup_rows += 1
        seen_hashes.add(h)

        for col in all_cols:
            val = r.get(col)
            if val is None or val == "" or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                missing_counts[col] += 1

        for num_col in expected_numeric:
            val = r.get(num_col)
            if val is not None and val != "":
                try:
                    f = float(val)
                    if math.isnan(f) or math.isinf(f):
                        non_num_counts[num_col] += 1
                except (ValueError, TypeError):
                    non_num_counts[num_col] += 1

    missing_pcts = {c: (cnt / n_rows) * 100.0 for c, cnt in missing_counts.items()}
    is_valid = len(warnings) == 0 and sum(non_num_counts.values()) == 0

    return TabularSchemaReport(
        row_count=n_rows,
        column_count=len(all_cols),
        columns=tuple(all_cols),
        missing_counts=missing_counts,
        missing_percentages=missing_pcts,
        duplicate_rows_count=dup_rows,
        non_numeric_violations=non_num_counts,
        is_schema_valid=is_valid,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class OutlierAuditReport:
    """Outlier screening report using parametric Z-scores and non-parametric IQR fences."""

    total_observations: int
    zscore_outliers_count: int
    iqr_outliers_count: int
    outlier_indices: Tuple[int, ...]
    outlier_values: Tuple[float, ...]
    iqr_lower_fence: float
    iqr_upper_fence: float
    z_threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_observations": self.total_observations,
            "zscore_outliers_count": self.zscore_outliers_count,
            "iqr_outliers_count": self.iqr_outliers_count,
            "outlier_indices": list(self.outlier_indices),
            "outlier_values": list(self.outlier_values),
            "iqr_lower_fence": float(self.iqr_lower_fence),
            "iqr_upper_fence": float(self.iqr_upper_fence),
            "z_threshold": float(self.z_threshold),
        }


def audit_outliers(
    series: Sequence[float],
    z_threshold: float = 3.0,
    iqr_multiplier: float = 1.5,
) -> OutlierAuditReport:
    """Detect statistical outliers using dual-criteria: Z-score > z_threshold and Tukey's IQR fences."""
    arr = np.asarray(series, dtype=np.float64)
    n = len(arr)
    if n < 4:
        raise ValueError("Outlier detection requires at least 4 observations")

    mean_v = float(np.mean(arr))
    std_v = float(np.std(arr, ddof=1))

    z_outliers = []
    if std_v > 1e-12:
        z_scores = np.abs((arr - mean_v) / std_v)
        z_outliers = np.where(z_scores > z_threshold)[0]

    q25 = float(np.percentile(arr, 25))
    q75 = float(np.percentile(arr, 75))
    iqr = q75 - q25
    lower_fence = q25 - (iqr_multiplier * iqr)
    upper_fence = q75 + (iqr_multiplier * iqr)

    iqr_outliers = np.where((arr < lower_fence) | (arr > upper_fence))[0]
    all_outlier_idx = sorted(set(z_outliers).union(set(iqr_outliers)))

    return OutlierAuditReport(
        total_observations=n,
        zscore_outliers_count=len(z_outliers),
        iqr_outliers_count=len(iqr_outliers),
        outlier_indices=tuple(int(i) for i in all_outlier_idx),
        outlier_values=tuple(float(arr[i]) for i in all_outlier_idx),
        iqr_lower_fence=lower_fence,
        iqr_upper_fence=upper_fence,
        z_threshold=float(z_threshold),
    )


@dataclass(frozen=True)
class DatasetDriftReport:
    """Kolmogorov-Smirnov two-sample test report for empirical distribution drift."""

    reference_count: int
    current_count: int
    ks_statistic: float
    p_value: float
    has_drifted: bool
    significance_level: float
    verdict: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_count": self.reference_count,
            "current_count": self.current_count,
            "ks_statistic": float(self.ks_statistic),
            "p_value": float(self.p_value),
            "has_drifted": self.has_drifted,
            "significance_level": float(self.significance_level),
            "verdict": self.verdict,
        }


def detect_dataset_drift(
    reference_sample: Sequence[float],
    current_sample: Sequence[float],
    alpha: float = 0.05,
) -> DatasetDriftReport:
    """Test whether current sample distribution has drifted from reference baseline using 2-sample KS test."""
    from scipy.stats import ks_2samp

    ref = np.asarray(reference_sample, dtype=np.float64)
    cur = np.asarray(current_sample, dtype=np.float64)

    if len(ref) < 5 or len(cur) < 5:
        raise ValueError("Both reference and current samples require at least 5 observations")

    res = ks_2samp(ref, cur)
    has_drift = bool(res.pvalue < alpha)
    verdict = "DISTRIBUTION_DRIFT_DETECTED" if has_drift else "DISTRIBUTIONS_MATCH_STABLE"

    return DatasetDriftReport(
        reference_count=len(ref),
        current_count=len(cur),
        ks_statistic=float(res.statistic),
        p_value=float(res.pvalue),
        has_drifted=has_drift,
        significance_level=float(alpha),
        verdict=verdict,
    )


@dataclass(frozen=True)
class ContaminationReport:
    """Audit of train/test data overlap and exact sample contamination."""

    train_count: int
    test_count: int
    overlapping_count: int
    overlap_rate: float
    is_contaminated: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "train_count": self.train_count,
            "test_count": self.test_count,
            "overlapping_count": self.overlapping_count,
            "overlap_rate": float(self.overlap_rate),
            "is_contaminated": self.is_contaminated,
        }


def detect_train_test_contamination(
    train_records: Sequence[Any],
    test_records: Sequence[Any],
) -> ContaminationReport:
    """Detect exact duplicate records spanning train and test splits."""
    n_train = len(train_records)
    n_test = len(test_records)
    if n_train == 0 or n_test == 0:
        raise ValueError("Train and test collections must both be non-empty")

    train_set = {str(r) for r in train_records}
    test_set = {str(r) for r in test_records}

    overlap = train_set.intersection(test_set)
    overlap_count = len(overlap)
    rate = overlap_count / n_test if n_test > 0 else 0.0

    return ContaminationReport(
        train_count=n_train,
        test_count=n_test,
        overlapping_count=overlap_count,
        overlap_rate=rate,
        is_contaminated=overlap_count > 0,
    )


@dataclass(frozen=True)
class LeakageAuditReport:
    """Screening for features suspiciously correlated with target values."""

    features_evaluated: int
    suspect_features: Tuple[str, ...]
    correlations: Mapping[str, float]
    has_leakage_risk: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "features_evaluated": self.features_evaluated,
            "suspect_features": list(self.suspect_features),
            "correlations": dict(self.correlations),
            "has_leakage_risk": self.has_leakage_risk,
        }


def screen_target_leakage(
    feature_matrix: np.ndarray,
    target: np.ndarray,
    feature_names: Optional[Sequence[str]] = None,
    correlation_threshold: float = 0.98,
) -> LeakageAuditReport:
    """Detect features with absolute correlation >= correlation_threshold with the target variable."""
    X = np.asarray(feature_matrix, dtype=np.float64)
    y = np.asarray(target, dtype=np.float64).squeeze()

    if X.ndim == 1:
        X = X.reshape(-1, 1)

    n_samples, n_features = X.shape
    if n_samples != len(y):
        raise ValueError(f"Feature rows ({n_samples}) does not match target length ({len(y)})")

    names = list(feature_names) if feature_names is not None else [f"feature_{i}" for i in range(n_features)]
    corrs: Dict[str, float] = {}
    suspects: List[str] = []

    y_std = float(np.std(y))
    for i in range(n_features):
        col = X[:, i]
        col_std = float(np.std(col))
        if col_std > 1e-12 and y_std > 1e-12:
            r = float(np.corrcoef(col, y)[0, 1])
        else:
            r = 0.0
        corrs[names[i]] = r
        if abs(r) >= correlation_threshold:
            suspects.append(names[i])

    return LeakageAuditReport(
        features_evaluated=n_features,
        suspect_features=tuple(suspects),
        correlations=corrs,
        has_leakage_risk=len(suspects) > 0,
    )
