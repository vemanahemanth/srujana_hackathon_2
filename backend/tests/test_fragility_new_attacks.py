"""Unit tests for newly added Blueprint fragility attacks and audit suite."""

from __future__ import annotations

import numpy as np
import pytest

from fragility_engine.fragility import (
    run_outlier_sensitivity_attack,
    run_missing_data_attack,
    run_regime_shift_attack,
    run_fragility_audit,
    FragilityAuditReport,
    FragilityExperimentResult,
)


@pytest.fixture
def sample_returns() -> list[float]:
    """Synthetic 40-day return series with heavy negative tails."""
    return [
        0.010, -0.015, 0.005, 0.020, -0.025,
        0.008, -0.004, 0.012, -0.050, 0.018,
        -0.010, 0.015, -0.005, 0.002, -0.012,
        0.022, -0.008, 0.004, -0.018, 0.011,
        0.005, -0.007, 0.003, 0.014, -0.060,
        0.009, -0.002, 0.011, -0.016, 0.017,
        -0.008, 0.013, -0.004, 0.006, -0.011,
        0.020, -0.009, 0.003, -0.015, 0.012,
    ]


def test_outlier_sensitivity_attack_winsorize(sample_returns: list[float]) -> None:
    res = run_outlier_sensitivity_attack(sample_returns, trim_pct=0.05, method="winsorize")
    assert isinstance(res, FragilityExperimentResult)
    assert res.perturbation_id == "outlier_sensitivity"
    # Winsorizing heavy tails should reduce reported volatility
    assert res.perturbed_metrics["volatility_annualized"] <= res.baseline_metrics["volatility_annualized"]
    assert res.observations_used == len(sample_returns)
    d = res.to_dict()
    assert "baseline_metrics" in d
    assert "perturbed_metrics" in d


def test_outlier_sensitivity_attack_trim(sample_returns: list[float]) -> None:
    res = run_outlier_sensitivity_attack(sample_returns, trim_pct=0.05, method="trim")
    assert res.perturbation_id == "outlier_sensitivity"
    assert res.observations_used < len(sample_returns)


def test_missing_data_attack_forward_fill(sample_returns: list[float]) -> None:
    res = run_missing_data_attack(sample_returns, drop_rate=0.10, impute_method="forward_fill", random_seed=42)
    assert isinstance(res, FragilityExperimentResult)
    assert res.perturbation_id == "missing_data_policy"
    # Forward fill (0 return) dampens measured volatility
    assert res.perturbed_metrics["volatility_annualized"] <= res.baseline_metrics["volatility_annualized"]
    assert res.observations_used == len(sample_returns)


def test_missing_data_attack_drop(sample_returns: list[float]) -> None:
    res = run_missing_data_attack(sample_returns, drop_rate=0.10, impute_method="drop", random_seed=42)
    assert res.observations_used < len(sample_returns)


def test_regime_shift_attack(sample_returns: list[float]) -> None:
    res = run_regime_shift_attack(sample_returns, window_length=15)
    assert isinstance(res, FragilityExperimentResult)
    assert res.perturbation_id == "regime_shift"
    # Stress regime volatility should exceed full sample volatility
    assert res.perturbed_metrics["volatility_annualized"] >= res.baseline_metrics["volatility_annualized"]
    assert res.observations_used == 15


def test_run_fragility_audit(sample_returns: list[float]) -> None:
    audit = run_fragility_audit(sample_returns, target_metric="volatility_annualized", audit_id="audit_test_01")
    assert isinstance(audit, FragilityAuditReport)
    assert audit.audit_id == "audit_test_01"
    assert len(audit.experiments) == 5
    assert audit.sensitivity_ranking.metric_id == "volatility_annualized"
    assert audit.sensitivity_ranking.most_sensitive_perturbation is not None
    assert audit.summary["experiments_count"] == 5
    d = audit.to_dict()
    assert d["audit_id"] == "audit_test_01"
    assert len(d["experiments"]) == 5
