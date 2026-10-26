"""Tests for FragilityEngine ML Model Testing Laboratory."""

import pytest
import numpy as np

from fragility_engine.ml import (
    MLTaskType,
    BaseMLModel,
    SimpleLinearRegressionModel,
    SimpleLogisticClassifierModel,
    calculate_regression_metrics,
    calculate_classification_metrics,
    calculate_forecasting_metrics,
    split_chronological,
    evaluate_ml_robustness,
)


def test_regression_metrics_hand_calculated():
    y_true = np.array([2.0, 4.0, 6.0, 8.0])
    y_pred = np.array([2.5, 3.5, 6.0, 9.0])
    # Errors: [0.5, -0.5, 0.0, 1.0]
    # Absolute errors: [0.5, 0.5, 0.0, 1.0] => sum = 2.0 / 4 = 0.50
    # Squared errors: [0.25, 0.25, 0.0, 1.0] => sum = 1.5 / 4 = 0.375 => RMSE = sqrt(0.375) approx 0.61237
    # y_true mean = 5.0, SS_tot = (9 + 1 + 1 + 9) = 20.0, SS_res = 1.5 => R^2 = 1 - 1.5/20 = 0.925
    # Relative errors: [0.5/2, 0.5/4, 0/6, 1/8] = [0.25, 0.125, 0.0, 0.125] => sum = 0.50 / 4 = 0.125 (12.5%)

    rep = calculate_regression_metrics(y_true, y_pred)
    assert pytest.approx(rep.mae, abs=1e-5) == 0.50
    assert pytest.approx(rep.rmse, abs=1e-4) == 0.6124
    assert pytest.approx(rep.r_squared, abs=1e-4) == 0.9250
    assert pytest.approx(rep.mape, abs=1e-4) == 0.1250
    assert rep.sample_size == 4


def test_classification_metrics_hand_calculated():
    y_true = np.array([1, 1, 0, 0, 1])
    y_pred = np.array([1, 0, 0, 0, 1])
    y_prob = np.array([0.9, 0.4, 0.1, 0.2, 0.8])

    # TP = 2 (idx 0, 4), FN = 1 (idx 1), TN = 2 (idx 2, 3), FP = 0
    # Accuracy = (2 + 2) / 5 = 0.80
    # Precision = 2 / (2 + 0) = 1.0
    # Recall = 2 / (2 + 1) = 2/3 approx 0.6667
    # F1 = 2 * (1.0 * 2/3) / (1.0 + 2/3) = (4/3) / (5/3) = 0.80

    rep = calculate_classification_metrics(y_true, y_pred, y_prob=y_prob)
    assert pytest.approx(rep.accuracy, abs=1e-4) == 0.80
    assert pytest.approx(rep.precision, abs=1e-4) == 1.00
    assert pytest.approx(rep.recall, abs=1e-4) == 0.6667
    assert pytest.approx(rep.f1_score, abs=1e-4) == 0.80
    assert rep.roc_auc is not None and rep.roc_auc > 0.80
    assert rep.brier_score is not None and rep.brier_score < 0.20
    assert rep.confusion_matrix == [[2, 0], [1, 2]]


def test_forecasting_metrics():
    y_true = np.array([10.0, 12.0, 14.0])
    y_pred = np.array([11.0, 11.0, 15.0])
    y_hist = np.array([6.0, 8.0, 10.0])  # naive diffs = [2.0, 2.0] => mean = 2.0

    rep = calculate_forecasting_metrics(y_true, y_pred, y_train_history=y_hist, horizon_steps=1)
    # MAE = (|1| + |1| + |1|) / 3 = 1.0
    # MASE = 1.0 / 2.0 = 0.50
    assert pytest.approx(rep.mae, abs=1e-4) == 1.0
    assert rep.mase is not None and pytest.approx(rep.mase, abs=1e-4) == 0.50


def test_chronological_splitting_zero_leakage():
    X = np.arange(100).reshape(-1, 1)
    y = np.arange(100)

    X_train, y_train, X_test, y_test = split_chronological(X, y, train_ratio=0.80)
    assert len(X_train) == 80
    assert len(X_test) == 20
    # Strict chronological boundary check: max(train) < min(test)
    assert np.max(y_train) < np.min(y_test)
    assert np.max(y_train) == 79
    assert np.min(y_test) == 80


def test_ml_robustness_attacks():
    # Linear model: y = 2*x1 + 3*x2 + 1
    weights = np.array([2.0, 3.0])
    model = SimpleLinearRegressionModel(weights=weights, bias=1.0)

    X_test = np.array([[1.0, 2.0], [2.0, 1.0], [3.0, 3.0], [4.0, 2.0]])
    y_test = model.predict(X_test)  # perfectly fitted zero-error baseline

    attacks = evaluate_ml_robustness(
        model,
        X_test,
        y_test,
        noise_stds=(0.05, 0.10),
        missing_rates=(0.10,),
        seed=42,
    )

    assert len(attacks) == 3
    for att in attacks:
        assert att.metric_name == "rmse"
        # Since baseline was 0.0 error, attacked metric will be strictly positive degradation
        assert att.attacked_metric >= att.baseline_metric
