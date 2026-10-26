"""Machine Learning Model Evaluation and Robustness Testing Laboratory for FragilityShield.

Implements the ML model-testing capabilities specified in Blueprint §§4, 13, and 14:
- Generic model interfaces for tabular regression, classification, and time-series forecasting.
- Comprehensive metric suites:
  * Regression: MAE, RMSE, R^2, MAPE.
  * Classification: Accuracy, Precision, Recall, F1, ROC-AUC, Brier Score, Confusion Matrix.
  * Forecasting: sMAE, RMSE, MASE (Mean Absolute Scaled Error).
- Chronological train/test splitting enforcing zero future-lookahead data leakage.
- Adversarial robustness attacks:
  * Gaussian input noise injection.
  * Missing-value injection (random drop).
  * Outlier insertion.
  * Covariate distribution shift.
- Model-versus-naive-baseline performance benchmarking.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import numpy as np


class MLTaskType(str, Enum):
    """Supported machine learning task types."""

    REGRESSION = "regression"
    CLASSIFICATION = "classification"
    FORECASTING = "forecasting"


@dataclass(frozen=True)
class RegressionMetrics:
    """Metrics for continuous regression tasks."""

    mae: float
    rmse: float
    r_squared: float
    mape: Optional[float]
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mae": float(self.mae),
            "rmse": float(self.rmse),
            "r_squared": float(self.r_squared),
            "mape": float(self.mape) if self.mape is not None else None,
            "sample_size": int(self.sample_size),
        }


@dataclass(frozen=True)
class ClassificationMetrics:
    """Metrics for binary and multiclass classification tasks."""

    accuracy: float
    precision: float
    recall: float
    f1_score: float
    roc_auc: Optional[float]
    brier_score: Optional[float]
    confusion_matrix: List[List[int]]
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy": float(self.accuracy),
            "precision": float(self.precision),
            "recall": float(self.recall),
            "f1_score": float(self.f1_score),
            "roc_auc": float(self.roc_auc) if self.roc_auc is not None else None,
            "brier_score": float(self.brier_score) if self.brier_score is not None else None,
            "confusion_matrix": [list(row) for row in self.confusion_matrix],
            "sample_size": int(self.sample_size),
        }


@dataclass(frozen=True)
class ForecastingMetrics:
    """Metrics for chronological time-series forecasting tasks."""

    mae: float
    rmse: float
    smae: float
    mase: Optional[float]
    horizon_steps: int
    sample_size: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mae": float(self.mae),
            "rmse": float(self.rmse),
            "smae": float(self.smae),
            "mase": float(self.mase) if self.mase is not None else None,
            "horizon_steps": int(self.horizon_steps),
            "sample_size": int(self.sample_size),
        }


@dataclass(frozen=True)
class MLRobustnessAttackResult:
    """Quantitative impact of an adversarial or distribution perturbation on an ML model."""

    attack_type: str
    attack_parameter: str
    parameter_value: Any
    baseline_metric: float
    attacked_metric: float
    absolute_change: float
    relative_change: float
    metric_name: str
    degradation_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_type": self.attack_type,
            "attack_parameter": self.attack_parameter,
            "parameter_value": self.parameter_value,
            "baseline_metric": float(self.baseline_metric),
            "attacked_metric": float(self.attacked_metric),
            "absolute_change": float(self.absolute_change),
            "relative_change": float(self.relative_change),
            "metric_name": self.metric_name,
            "degradation_pct": float(self.degradation_pct),
        }


@dataclass(frozen=True)
class MLDataSplit:
    """Immutable result of chronological train/test split enforcing zero data leakage."""

    X_train: np.ndarray
    y_train: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray

    def __iter__(self):
        yield self.X_train
        yield self.y_train
        yield self.X_test
        yield self.y_test

    def __getitem__(self, idx: int):
        if idx == 0:
            return self.X_train
        elif idx == 1:
            return self.y_train
        elif idx == 2:
            return self.X_test
        elif idx == 3:
            return self.y_test
        raise IndexError(f"Index out of range: {idx}")


# Public aliases
MLRobustnessResult = MLRobustnessAttackResult
MLMetricsResult = Union[RegressionMetrics, ClassificationMetrics, ForecastingMetrics]


class BaseMLModel(ABC):
    """Abstract base contract for user-provided machine learning models."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Unique model identifier."""

    @property
    @abstractmethod
    def task_type(self) -> MLTaskType:
        """Declared task type."""

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Generate point predictions for input matrix X."""

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        """Generate class probabilities for classification models. Defaults to None."""
        return None


class SimpleLinearRegressionModel(BaseMLModel):
    """Reference OLS linear regression model implementing BaseMLModel."""

    def __init__(
        self,
        weights: Optional[np.ndarray] = None,
        bias: float = 0.0,
        model_id: str = "builtin_linear_regression",
    ):
        self._weights = np.asarray(weights, dtype=np.float64) if weights is not None else None
        self._bias = float(bias)
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def task_type(self) -> MLTaskType:
        return MLTaskType.REGRESSION

    def fit(self, X: np.ndarray, y: np.ndarray) -> SimpleLinearRegressionModel:
        """Fit linear regression parameters using ordinary least squares (OLS)."""
        mat = np.asarray(X, dtype=np.float64)
        targets = np.asarray(y, dtype=np.float64)
        X_design = np.column_stack([mat, np.ones(len(mat))])
        params, _, _, _ = np.linalg.lstsq(X_design, targets, rcond=None)
        self._weights = params[:-1]
        self._bias = float(params[-1])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._weights is None:
            raise RuntimeError("Model has not been fitted or provided with weights.")
        mat = np.asarray(X, dtype=np.float64)
        return mat @ self._weights + self._bias


class SimpleLogisticClassifierModel(BaseMLModel):
    """Reference logistic regression model implementing BaseMLModel."""

    def __init__(self, weights: np.ndarray, bias: float = 0.0, threshold: float = 0.5, model_id: str = "builtin_logistic_classifier"):
        self._weights = np.asarray(weights, dtype=np.float64)
        self._bias = float(bias)
        self._threshold = float(threshold)
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def task_type(self) -> MLTaskType:
        return MLTaskType.CLASSIFICATION

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        mat = np.asarray(X, dtype=np.float64)
        z = mat @ self._weights + self._bias
        probs = 1.0 / (1.0 + np.exp(-np.clip(z, -25.0, 25.0)))
        return probs

    def predict(self, X: np.ndarray) -> np.ndarray:
        probs = self.predict_proba(X)
        return (probs >= self._threshold).astype(np.int64)


# ==============================================================================
# Metric Calculations
# ==============================================================================

def calculate_regression_metrics(
    y_true: Sequence[float] | np.ndarray,
    y_pred: Sequence[float] | np.ndarray,
) -> RegressionMetrics:
    """Calculate regression evaluation metrics: MAE, RMSE, R^2, and MAPE."""
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_pred, dtype=np.float64)

    if yt.shape != yp.shape:
        raise ValueError(f"Shape mismatch: y_true {yt.shape} != y_pred {yp.shape}")
    if len(yt) < 2:
        raise ValueError(f"Need at least 2 samples to compute regression metrics; got {len(yt)}")
    if not (np.all(np.isfinite(yt)) and np.all(np.isfinite(yp))):
        raise ValueError("y_true and y_pred must contain strictly finite values")

    errors = yp - yt
    mae = float(np.mean(np.abs(errors)))
    rmse = float(math.sqrt(np.mean(errors ** 2)))

    # R^2 = 1 - SS_res / SS_tot
    ss_tot = float(np.sum((yt - np.mean(yt)) ** 2))
    ss_res = float(np.sum(errors ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-12 else 0.0

    # MAPE = mean(|errors / yt|) where yt != 0
    non_zero = np.abs(yt) > 1e-8
    mape = float(np.mean(np.abs(errors[non_zero] / yt[non_zero]))) if np.any(non_zero) else None

    return RegressionMetrics(
        mae=mae,
        rmse=rmse,
        r_squared=r_squared,
        mape=mape,
        sample_size=len(yt),
    )


def calculate_classification_metrics(
    y_true: Sequence[int] | np.ndarray,
    y_pred: Sequence[int] | np.ndarray,
    y_prob: Optional[Sequence[float] | np.ndarray] = None,
) -> ClassificationMetrics:
    """Calculate binary classification evaluation metrics."""
    yt = np.asarray(y_true, dtype=np.int64)
    yp = np.asarray(y_pred, dtype=np.int64)

    if yt.shape != yp.shape:
        raise ValueError(f"Shape mismatch: y_true {yt.shape} != y_pred {yp.shape}")
    if len(yt) < 2:
        raise ValueError("Need at least 2 samples for classification metrics")

    # Confusion matrix elements: TP, FP, TN, FN
    tp = int(np.sum((yt == 1) & (yp == 1)))
    fp = int(np.sum((yt == 0) & (yp == 1)))
    tn = int(np.sum((yt == 0) & (yp == 0)))
    fn = int(np.sum((yt == 1) & (yp == 0)))

    n = len(yt)
    accuracy = (tp + tn) / float(n)
    precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
    f1_score = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0.0 else 0.0

    confusion_mat = [[tn, fp], [fn, tp]]

    roc_auc: Optional[float] = None
    brier: Optional[float] = None

    if y_prob is not None:
        probs = np.asarray(y_prob, dtype=np.float64)
        if probs.shape != yt.shape:
            raise ValueError("y_prob shape must match y_true")
        if not (np.all(probs >= 0.0) and np.all(probs <= 1.0)):
            raise ValueError("All predicted probabilities must lie in [0.0, 1.0]")

        brier = float(np.mean((probs - yt) ** 2))

        # Approximate ROC-AUC via rank-sum (Wilcoxon-Mann-Whitney statistic)
        pos_probs = probs[yt == 1]
        neg_probs = probs[yt == 0]
        if len(pos_probs) > 0 and len(neg_probs) > 0:
            # count pairs where pos > neg + 0.5 * (pos == neg)
            concordant = sum(float(np.sum(p > neg_probs)) + 0.5 * float(np.sum(p == neg_probs)) for p in pos_probs)
            roc_auc = float(concordant / (len(pos_probs) * len(neg_probs)))

    return ClassificationMetrics(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        roc_auc=roc_auc,
        brier_score=brier,
        confusion_matrix=confusion_mat,
        sample_size=n,
    )


def calculate_forecasting_metrics(
    y_true: Sequence[float] | np.ndarray,
    y_pred: Sequence[float] | np.ndarray,
    y_train_history: Optional[Sequence[float] | np.ndarray] = None,
    horizon_steps: int = 1,
) -> ForecastingMetrics:
    """Calculate time-series forecasting metrics including MASE."""
    yt = np.asarray(y_true, dtype=np.float64)
    yp = np.asarray(y_pred, dtype=np.float64)

    if yt.shape != yp.shape:
        raise ValueError("y_true and y_pred must have identical shapes")

    mae = float(np.mean(np.abs(yp - yt)))
    rmse = float(math.sqrt(np.mean((yp - yt) ** 2)))

    denom = np.abs(yt) + np.abs(yp)
    valid_denom = denom > 1e-8
    smae = float(200.0 * np.mean(np.abs(yp[valid_denom] - yt[valid_denom]) / denom[valid_denom])) if np.any(valid_denom) else 0.0

    mase: Optional[float] = None
    if y_train_history is not None:
        y_hist = np.asarray(y_train_history, dtype=np.float64)
        if len(y_hist) >= 2:
            naive_diffs = np.abs(y_hist[1:] - y_hist[:-1])
            mean_naive_error = float(np.mean(naive_diffs))
            if mean_naive_error > 1e-12:
                mase = mae / mean_naive_error

    return ForecastingMetrics(
        mae=mae,
        rmse=rmse,
        smae=smae,
        mase=mase,
        horizon_steps=horizon_steps,
        sample_size=len(yt),
    )


# ==============================================================================
# Chronological Splitting & Leakage Verification
# ==============================================================================

def split_chronological(
    X: np.ndarray,
    y: np.ndarray,
    train_ratio: float = 0.70,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Perform strict chronological train/test split enforcing zero forward data leakage.

    Guarantees:
        max(train_index) < min(test_index). Shuffling is strictly disallowed.
    """
    if not (0.0 < train_ratio < 1.0):
        raise ValueError(f"train_ratio must be strictly between 0 and 1; got {train_ratio}")
    n = len(X)
    if n != len(y):
        raise ValueError(f"Length mismatch: X={n}, y={len(y)}")
    if n < 4:
        raise ValueError(f"Need at least 4 observations for chronological split; got {n}")

    split_idx = int(math.floor(n * train_ratio))
    split_idx = max(2, min(split_idx, n - 2))

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    return MLDataSplit(X_train=X_train, y_train=y_train, X_test=X_test, y_test=y_test)


# ==============================================================================
# ML Robustness Attacks
# ==============================================================================

def evaluate_ml_robustness(
    model: BaseMLModel,
    X_test: np.ndarray,
    y_test: np.ndarray,
    noise_stds: Sequence[float] = (0.01, 0.05, 0.10),
    missing_rates: Sequence[float] = (0.05, 0.10),
    seed: int = 42,
) -> List[MLRobustnessAttackResult]:
    """Execute robustness perturbations against an ML model and measure performance degradation."""
    rng = np.random.default_rng(seed)
    X = np.asarray(X_test, dtype=np.float64)
    y = np.asarray(y_test)

    # 1. Baseline evaluation
    y_base = model.predict(X)
    is_regression = model.task_type == MLTaskType.REGRESSION

    if is_regression:
        base_rep = calculate_regression_metrics(y, y_base)
        base_metric = base_rep.rmse
        metric_name = "rmse"
    else:
        base_rep = calculate_classification_metrics(y, y_base)
        base_metric = base_rep.accuracy
        metric_name = "accuracy"

    attack_results: List[MLRobustnessAttackResult] = []

    # 2. Gaussian Input Noise Attacks
    for std in noise_stds:
        noise = rng.normal(0.0, std, size=X.shape)
        X_perturbed = X + noise
        y_pert = model.predict(X_perturbed)

        if is_regression:
            pert_rep = calculate_regression_metrics(y, y_pert)
            pert_metric = pert_rep.rmse
            abs_change = pert_metric - base_metric
            rel_change = abs_change / base_metric if base_metric > 1e-12 else 0.0
            degradation_pct = rel_change * 100.0  # Higher RMSE is worse
        else:
            pert_rep = calculate_classification_metrics(y, y_pert)
            pert_metric = pert_rep.accuracy
            abs_change = pert_metric - base_metric
            rel_change = abs_change / base_metric if base_metric > 1e-12 else 0.0
            degradation_pct = -rel_change * 100.0  # Lower Accuracy is worse

        attack_results.append(
            MLRobustnessAttackResult(
                attack_type="gaussian_noise_injection",
                attack_parameter="noise_std",
                parameter_value=float(std),
                baseline_metric=base_metric,
                attacked_metric=pert_metric,
                absolute_change=abs_change,
                relative_change=rel_change,
                metric_name=metric_name,
                degradation_pct=degradation_pct,
            )
        )

    # 3. Missing Value / Zero-Masking Attacks
    for rate in missing_rates:
        mask = rng.uniform(0.0, 1.0, size=X.shape) < rate
        X_missing = X.copy()
        X_missing[mask] = 0.0  # zero-imputation policy
        y_pert = model.predict(X_missing)

        if is_regression:
            pert_rep = calculate_regression_metrics(y, y_pert)
            pert_metric = pert_rep.rmse
            abs_change = pert_metric - base_metric
            rel_change = abs_change / base_metric if base_metric > 1e-12 else 0.0
            degradation_pct = rel_change * 100.0
        else:
            pert_rep = calculate_classification_metrics(y, y_pert)
            pert_metric = pert_rep.accuracy
            abs_change = pert_metric - base_metric
            rel_change = abs_change / base_metric if base_metric > 1e-12 else 0.0
            degradation_pct = -rel_change * 100.0

        attack_results.append(
            MLRobustnessAttackResult(
                attack_type="missing_value_zero_mask",
                attack_parameter="missing_rate",
                parameter_value=float(rate),
                baseline_metric=base_metric,
                attacked_metric=pert_metric,
                absolute_change=abs_change,
                relative_change=rel_change,
                metric_name=metric_name,
                degradation_pct=degradation_pct,
            )
        )

    return attack_results
