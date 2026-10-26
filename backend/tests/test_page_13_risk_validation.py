"""Test Suite for Page 13: Risk Model Validation & Backtesting Observatory.

Validates statistical rigor, zero lookahead bias, edge cases, and REST API endpoints.
"""

import datetime
import math
import numpy as np
import pytest
from starlette.testclient import TestClient

from fragility_engine.risk_model_validation import (
    calculate_kupiec_test,
    calculate_christoffersen_test,
    validate_expected_shortfall,
    clopper_pearson_interval,
    predict_model_var_es,
    run_risk_model_validation,
    compare_risk_models,
)
from app import create_application


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_kupiec_test_independent_fixture():
    """Verify Kupiec LR test against independently calculated theoretical values."""
    # N = 250, p = 0.05, x = 12 (expected ~12.5) -> Should ACCEPT H0
    res = calculate_kupiec_test(n_observations=250, n_exceptions=12, confidence_level=0.95)
    assert res.n_observations == 250
    assert res.n_exceptions == 12
    assert res.empirical_rate == 12 / 250
    assert res.decision == "ACCEPT"
    assert res.p_value > 0.05
    assert res.lr_stat >= 0.0

    # N = 250, p = 0.05, x = 30 (extreme underestimation of risk) -> Should REJECT
    res_under = calculate_kupiec_test(n_observations=250, n_exceptions=30, confidence_level=0.95)
    assert res_under.decision == "REJECT_UNDERESTIMATING_RISK"
    assert res_under.p_value < 0.001

    # N = 250, p = 0.05, x = 1 (overestimation of risk) -> Should REJECT
    res_over = calculate_kupiec_test(n_observations=250, n_exceptions=1, confidence_level=0.95)
    assert res_over.decision == "REJECT_OVERESTIMATING_RISK"
    assert res_over.p_value < 0.05


def test_kupiec_boundary_edge_cases():
    """Verify zero-exception and all-exception edge cases do not crash with log(0)."""
    # x = 0 (Zero exceptions)
    res_zero = calculate_kupiec_test(n_observations=100, n_exceptions=0, confidence_level=0.95)
    assert res_zero.n_exceptions == 0
    assert res_zero.empirical_rate == 0.0
    # Expected LR = -2 * 100 * ln(0.95) ~= 10.258
    assert math.isclose(res_zero.lr_stat, -200 * math.log(0.95), rel_tol=1e-3)
    assert res_zero.p_value < 0.05

    # x = 100 (All exceptions)
    res_all = calculate_kupiec_test(n_observations=100, n_exceptions=100, confidence_level=0.95)
    assert res_all.n_exceptions == 100
    assert res_all.empirical_rate == 1.0
    assert res_all.p_value < 0.001


def test_clopper_pearson_confidence_interval():
    """Verify Clopper-Pearson binomial interval bounds."""
    low, high = clopper_pearson_interval(k=10, n=200, confidence=0.95)
    assert 0.0 <= low < 0.05
    assert 0.05 < high <= 1.0


def test_christoffersen_independence_and_conditional_coverage():
    """Verify Christoffersen Markov transition test and joint conditional coverage."""
    # Pattern with no clustering: alternating non-exceptions
    unclustered = [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0]
    res_unclustered = calculate_christoffersen_test(unclustered, lr_uc=0.5)
    assert res_unclustered.is_sufficient_sample is True
    assert res_unclustered.independence_decision == "ACCEPT"
    assert res_unclustered.lr_cc == pytest.approx(0.5 + res_unclustered.lr_ind)

    # Clustered exceptions: consecutive runs of 1s
    clustered = [0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0]
    res_clustered = calculate_christoffersen_test(clustered, lr_uc=1.5)
    assert res_clustered.n11 > 0
    assert res_clustered.independence_decision == "REJECT_CLUSTERED_EXCEPTIONS"
    assert res_clustered.p_value_ind < 0.05


def test_expected_shortfall_validation():
    """Verify McNeil-Frey standardized tail residuals test for Expected Shortfall."""
    # Tail losses well calibrated to predicted ES
    predicted_es = [0.03, 0.035, 0.04, 0.032, 0.038, 0.031]
    realized_losses = [0.029, 0.036, 0.039, 0.033, 0.037, 0.030]
    res = validate_expected_shortfall(realized_losses, predicted_es)
    assert res.n_tail_losses == 6
    assert res.status == "PASS"

    # Severe underestimation of ES
    underestimated_es = [0.02, 0.02, 0.02, 0.02, 0.02]
    catastrophic_losses = [0.08, 0.09, 0.07, 0.10, 0.085]
    res_fail = validate_expected_shortfall(catastrophic_losses, underestimated_es)
    assert res_fail.status == "FAIL_UNDERESTIMATED_ES"
    assert res_fail.p_value < 0.05


def test_expected_shortfall_insufficient_sample():
    """Verify strict handling when tail exception count is less than 5."""
    res_insuff = validate_expected_shortfall(
        tail_realized_losses=[0.05, 0.06],
        tail_predicted_es=[0.04, 0.04],
    )
    assert res_insuff.status == "INSUFFICIENT_EVIDENCE"
    assert res_insuff.n_tail_losses == 2


def test_time_aware_risk_model_predictors():
    """Verify in-sample VaR and ES predictions for all 4 model families."""
    np.random.seed(42)
    # 200 normal daily returns (mean=0.0005, vol=0.015)
    rets = np.random.normal(loc=0.0005, scale=0.015, size=200)

    for mid in ["historical_simulation", "parametric_gaussian", "cornish_fisher", "ewma"]:
        var, es = predict_model_var_es(model_id=mid, in_sample_returns=rets, confidence_level=0.95)
        assert var > 0.0, f"VaR must be positive loss magnitude for {mid}"
        assert es >= var, f"Expected Shortfall must be >= VaR for {mid}"


def test_reconstructed_rolling_backtest_no_lookahead():
    """Verify full rolling backtest enforces zero lookahead and correct dates."""
    np.random.seed(101)
    rets = np.random.normal(loc=0.0002, scale=0.012, size=180).tolist()
    start_d = datetime.date(2024, 1, 1)
    dates = [(start_d + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(180)]

    summary = run_risk_model_validation(
        symbol="SYNTHETIC_TEST",
        model_id="historical_simulation",
        confidence_level=0.95,
        training_window=100,
        re_estimation_step=5,
        custom_returns=rets,
        custom_dates=dates,
    )

    assert summary.leakage_check_passed is True
    assert summary.evaluation_window_size == 80
    assert len(summary.forecasts) == 80
    assert summary.training_window_size == 100

    # Ensure each evaluation date is strictly greater than training window end date
    for pt in summary.forecasts:
        assert pt.train_end_date < pt.date


def test_compare_risk_models():
    """Verify comparison function executes multiple models over identical returns."""
    res = compare_risk_models(
        symbol="RELIANCE",
        confidence_level=0.95,
        training_window=100,
        model_ids=["historical_simulation", "parametric_gaussian", "cornish_fisher", "ewma"],
    )
    assert len(res) == 4
    for item in res:
        assert item["n_observations"] > 0
        assert "kupiec_p_value" in item
        assert "christoffersen_p_value" in item
        assert item["leakage_passed"] is True


def test_api_models_risk_validation_run(client):
    """Verify POST /api/models/risk-validation/run endpoint."""
    resp = client.post("/api/models/risk-validation/run", json={
        "symbol": "RELIANCE",
        "model_id": "historical_simulation",
        "confidence_level": 0.95,
        "training_window": 120,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    val = data["validation"]
    assert val["model_id"] == "historical_simulation"
    assert "kupiec_unconditional_coverage" in val
    assert "christoffersen_conditional_coverage" in val
    assert "expected_shortfall_validation" in val
    assert len(val["forecast_sample"]) > 0


def test_api_models_risk_validation_compare(client):
    """Verify POST /api/models/risk-validation/compare endpoint."""
    resp = client.post("/api/models/risk-validation/compare", json={
        "symbol": "RELIANCE",
        "confidence_level": 0.95,
        "training_window": 120,
        "model_ids": ["historical_simulation", "parametric_gaussian", "cornish_fisher"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["comparison"]) == 3
