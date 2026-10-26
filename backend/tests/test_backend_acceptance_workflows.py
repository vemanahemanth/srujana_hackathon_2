"""FragilityShield — Master End-to-End Backend Acceptance Workflows.

Validates the complete product backend against the Master Implementation Directive
and Blueprint requirements through 9 end-to-end acceptance workflows:

1. Workflow 1: Portfolio to Risk & Coherent Measures.
2. Workflow 2: Scenario Analysis with Exact P&L Accounting Reconciliation.
3. Workflow 3: Comprehensive Fragility & Assumption Perturbations (>= 5 attacks).
4. Workflow 4: Validation Taxonomy (PASS, FAIL, WARNING, SKIPPED, INCONCLUSIVE).
5. Workflow 5: ML Model Evaluation, Chronological Splitting & Robustness.
6. Workflow 6: Genuine Plugin Extensibility & Benchmarking.
7. Workflow 7: Experiment Lifecycle, Cryptographic Hashes & Drift Detection.
8. Workflow 8: Multi-Format Reporting (JSON, Markdown, CSV) with Numerical Integrity.
9. Workflow 9: Invalid Inputs, Conflict Rejection & Leakage Safeguards.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from typing import Dict, List
import numpy as np
import pytest

from fragility_engine import (
    Client,
    Holding,
    Portfolio,
    ValidationStatus,
    calculate_annualized_volatility,
    calculate_historical_var,
    calculate_expected_shortfall,
    calculate_risk_report,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_calmar_ratio,
    calculate_beta,
    calculate_capture_ratios,
    execute_scenario,
    list_preset_scenarios,
    apply_correlation_stress,
    run_lookback_perturbation,
    run_volatility_estimator_perturbation,
    run_confidence_level_perturbation,
    run_return_friction_perturbation,
    run_outlier_sensitivity_attack,
    run_missing_data_attack,
    run_regime_shift_attack,
    run_fragility_audit,
    rank_perturbation_sensitivities,
    run_reference_value_tests,
    run_portfolio_consistency_tests,
    split_chronological,
    calculate_regression_metrics,
    calculate_classification_metrics,
    calculate_forecasting_metrics,
    evaluate_ml_robustness,
    SimpleLinearRegressionModel,
    SimpleLogisticClassifierModel,
    PluginRegistry,
    ModelPlugin,
    PluginMetadata,
    ModelExecutionResult,
    execute_model_benchmark,
    BenchmarkSpecification,
    StudioExperimentDefinition,
    execute_studio_experiment,
    LocalExperimentCatalog,
    compare_experiment_reports,
)


# ==============================================================================
# Workflow 1: Portfolio to Risk & Coherent Measures
# ==============================================================================

def test_workflow_1_portfolio_to_risk() -> None:
    client = Client()

    # 1. Ingest multi-asset portfolio with diverse sectors and asset classes
    holdings = [
        Holding("RELIANCE", 100.0, 2500.0, "Energy", entry_price=2400.0, asset_class="equity"),
        Holding("TCS", 50.0, 3800.0, "Information Technology", entry_price=3600.0, asset_class="equity"),
        Holding("HDFCBANK", 100.0, 1600.0, "Banking", entry_price=1700.0, asset_class="equity"),
        Holding("NIFTYBEES", 200.0, 250.0, "Broad Market", entry_price=240.0, asset_class="etf"),
        Holding("LIQUIDBEES", 100.0, 1000.0, "Cash Equivalents", entry_price=1000.0, asset_class="cash"),
    ]
    portfolio = client.portfolios.create(
        portfolio_id="wf1_portfolio",
        name="Institutional Core Alpha",
        currency="INR",
        holdings=holdings,
    )

    # 2. Portfolio valuations and unrealized P&L checks
    expected_mv = (
        100.0 * 2500.0
        + 50.0 * 3800.0
        + 100.0 * 1600.0
        + 200.0 * 250.0
        + 100.0 * 1000.0
    )  # 250k + 190k + 160k + 50k + 100k = 750,000 INR
    assert portfolio.total_value == pytest.approx(750_000.0)
    assert portfolio.total_valuation() == pytest.approx(750_000.0)

    expected_invested = (
        100.0 * 2400.0
        + 50.0 * 3600.0
        + 100.0 * 1700.0
        + 200.0 * 240.0
        + 100.0 * 1000.0
    )  # 240k + 180k + 170k + 48k + 100k = 738,000 INR
    assert portfolio.total_invested_capital == pytest.approx(738_000.0)
    assert portfolio.total_unrealized_pnl == pytest.approx(12_000.0)
    assert portfolio.total_unrealized_pnl_pct == pytest.approx(12_000.0 / 738_000.0)

    # 3. Allocations by Sector & Asset Class
    sector_allocs = portfolio.allocations_by_sector()
    assert sector_allocs["Energy"] == pytest.approx(250_000.0 / 750_000.0)
    assert sector_allocs["Information Technology"] == pytest.approx(190_000.0 / 750_000.0)

    ac_allocs = portfolio.allocations_by_asset_class()
    assert ac_allocs["equity"] == pytest.approx(600_000.0 / 750_000.0)
    assert ac_allocs["cash"] == pytest.approx(100_000.0 / 750_000.0)

    # 4. Generate 60-day historical returns for portfolio and market benchmark
    rng = np.random.RandomState(101)
    port_returns = rng.normal(0.0008, 0.012, size=60)
    bench_returns = rng.normal(0.0005, 0.010, size=60)

    # Inject fat-tail stress
    port_returns[10] = -0.045
    port_returns[35] = -0.038

    # 5. Risk calculation and metric verification
    rep = client.risk.calculate(port_returns)
    assert rep.volatility_annualized > 0.0
    assert rep.volatility_daily > 0.0
    assert rep.var_95 > 0.0
    assert rep.var_99 > rep.var_95  # Tail monotonicity

    # Coherent risk condition: Acerbi-Tasche subadditivity (ES >= VaR)
    assert rep.expected_shortfall_95 >= rep.var_95
    assert rep.expected_shortfall_99 >= rep.var_99

    # Financial ratios
    sharpe = client.risk.sharpe_ratio(port_returns, risk_free_rate=0.05)
    sortino = client.risk.sortino_ratio(port_returns, required_return=0.0)
    calmar = client.risk.calmar_ratio(port_returns)
    beta = client.risk.beta(port_returns, bench_returns)
    up_cap, down_cap = client.risk.capture_ratios(port_returns, bench_returns)

    assert math.isfinite(sharpe)
    assert math.isfinite(sortino)
    assert math.isfinite(calmar)
    assert math.isfinite(beta)
    assert math.isfinite(up_cap) and math.isfinite(down_cap)


# ==============================================================================
# Workflow 2: Scenario Analysis with Exact P&L Accounting Reconciliation
# ==============================================================================

def test_workflow_2_scenario_analysis_pnl_reconciliation() -> None:
    client = Client()

    holdings = [
        Holding("INFY", 100.0, 1500.0, "Information Technology"),  # 150,000 INR
        Holding("HDFCBANK", 200.0, 1600.0, "Banking"),             # 320,000 INR
        Holding("RELIANCE", 100.0, 2500.0, "Energy"),              # 250,000 INR
    ]
    portfolio = client.portfolios.create("wf2_port", "Scenario Port", "INR", holdings=holdings)
    baseline_val = portfolio.total_value  # 720,000 INR

    # 1. Execute custom scenario with sector and asset shocks
    scenario_res = client.scenarios.execute(
        portfolio=portfolio,
        scenario_id="tech_boost_bank_drop",
        name="Tech Boost & Bank Drop",
        sector_shocks={
            "Information Technology": 0.10,  # +10% -> +15,000
            "Banking": -0.20,                 # -20% -> -64,000
            "Energy": 0.00,                   #   0% -> 0
        },
    )

    # 2. Verify Exact P&L Accounting Identity
    expected_pnl = 15_000.0 - 64_000.0  # -49,000 INR
    expected_stressed_val = baseline_val + expected_pnl  # 671,000 INR

    assert scenario_res.original_portfolio_value == pytest.approx(baseline_val)
    assert scenario_res.stressed_portfolio_value == pytest.approx(expected_stressed_val)
    assert scenario_res.total_pnl == pytest.approx(expected_pnl)
    assert scenario_res.scenario_return == pytest.approx(expected_pnl / baseline_val)

    # 3. Holding-level P&L sum reconciliation
    holding_pnl_sum = sum(h.pnl_contribution for h in scenario_res.holding_results)
    assert holding_pnl_sum == pytest.approx(expected_pnl)

    # 4. Sector-level P&L sum reconciliation
    sector_pnl_sum = sum(s.pnl_contribution for s in scenario_res.sector_results)
    assert sector_pnl_sum == pytest.approx(expected_pnl)

    # 5. Presets execution
    preset_res = client.scenarios.execute_preset(portfolio, "banking_minus_20_it_minus_10")
    # INFY: -10% (-15k), HDFCBANK: -20% (-64k), RELIANCE unshocked (0)
    assert preset_res.total_pnl == pytest.approx(-79_000.0)

    # 6. Correlation stress test with positive semi-definite preservation
    sample_cov = np.array([
        [0.04, 0.01, 0.015],
        [0.01, 0.05, 0.02],
        [0.015, 0.02, 0.06],
    ])
    stressed_cov = client.scenarios.stress_correlation(sample_cov, stress_correlation=0.85)
    # Check PSD: all eigenvalues >= 0
    eigvals = np.linalg.eigvalsh(stressed_cov)
    assert np.all(eigvals >= -1e-10)


# ==============================================================================
# Workflow 3: Comprehensive Fragility & Assumption Perturbations (>= 5 attacks)
# ==============================================================================

def test_workflow_3_comprehensive_fragility_audit() -> None:
    client = Client()

    # 50-day return series with heavy negative tails
    returns = [
        0.010, -0.015, 0.005, 0.020, -0.025,
        0.008, -0.004, 0.012, -0.055, 0.018,
        -0.010, 0.015, -0.005, 0.002, -0.012,
        0.022, -0.008, 0.004, -0.018, 0.011,
        0.005, -0.007, 0.003, 0.014, -0.040,
        0.009, -0.002, 0.011, -0.016, 0.017,
        -0.008, 0.013, -0.004, 0.006, -0.011,
        0.020, -0.009, 0.003, -0.015, 0.012,
        0.007, -0.011, 0.004, 0.009, -0.048,
        0.015, -0.006, 0.001, -0.014, 0.010,
    ]

    # Attack 1: Lookback window contraction
    att1 = client.fragility.run_lookback(returns, perturbed_window=25)
    assert att1.observations_used == 25
    assert att1.perturbation_id == "lookback_window"

    # Attack 2: Volatility estimator (sample stdev -> EWMA)
    att2 = client.fragility.run_volatility_estimator(returns, decay_factor=0.92)
    assert att2.perturbation_id == "volatility_estimator_ewma"
    assert "volatility_annualized" in att2.perturbed_metrics

    # Attack 3: Tail confidence level shift (95% -> 99%)
    att3 = client.fragility.run_confidence_level(returns, baseline_confidence=0.95, perturbed_confidence=0.99)
    assert att3.perturbation_id == "tail_confidence_level"
    assert att3.perturbed_metrics["var"] > att3.baseline_metrics["var"]

    # Attack 4: Return friction (+20 bps)
    att4 = client.fragility.run_friction(returns, friction_bps=20.0)
    assert att4.perturbation_id == "return_friction_shock"

    # Attack 5: Outlier sensitivity (winsorization of 5% tails)
    att5 = client.fragility.run_outliers(returns, trim_pct=0.05, method="winsorize")
    assert att5.perturbation_id == "outlier_sensitivity"
    assert att5.perturbed_metrics["volatility_annualized"] <= att5.baseline_metrics["volatility_annualized"]

    # Attack 6: Missing data dropout
    att6 = client.fragility.run_missing_data(returns, drop_rate=0.10, impute_method="forward_fill")
    assert att6.perturbation_id == "missing_data_policy"

    # Attack 7: Regime shift
    att7 = client.fragility.run_regime_shift(returns, window_length=15)
    assert att7.perturbation_id == "regime_shift"

    # Consolidated audit with sensitivity ranking
    audit = client.fragility.run_audit(returns, target_metric="volatility_annualized")
    assert audit.audit_id == "audit_sdk"
    assert len(audit.experiments) >= 5
    assert audit.sensitivity_ranking.most_sensitive_perturbation is not None

    # Verify ranking is strictly sorted descending by absolute impact
    ranked = audit.sensitivity_ranking.ranked_impacts
    for i in range(len(ranked) - 1):
        assert abs(ranked[i].absolute_change) >= abs(ranked[i + 1].absolute_change)


# ==============================================================================
# Workflow 4: Validation Taxonomy (PASS, FAIL, WARNING, SKIPPED, INCONCLUSIVE)
# ==============================================================================

def test_workflow_4_validation_suite_taxonomy() -> None:
    client = Client()

    # 1. Run reference-value tests against analytical closed-form solutions
    ref_suite = client.validation.run_reference_values()
    assert ref_suite.passed is True
    assert ref_suite.status == ValidationStatus.PASS
    assert ref_suite.total_tests == 5
    assert ref_suite.passed_count == 5
    assert ref_suite.failed_count == 0

    # Verify status enum completeness
    all_statuses = {
        ValidationStatus.PASS,
        ValidationStatus.FAIL,
        ValidationStatus.WARNING,
        ValidationStatus.SKIPPED,
        ValidationStatus.INCONCLUSIVE,
    }
    assert len(all_statuses) == 5

    # 2. Portfolio consistency validation
    port = client.portfolios.create(
        "val_port",
        "Val Port",
        "INR",
        holdings=[
            Holding("A1", 10.0, 100.0, "Tech"),
            Holding("A2", 20.0, 50.0, "Finance"),
        ],
    )
    port_suite = client.validation.run_portfolio_consistency(port)
    assert port_suite.passed is True
    assert len(port_suite.records) >= 3


# ==============================================================================
# Workflow 5: ML Model Evaluation, Chronological Splitting & Robustness
# ==============================================================================

def test_workflow_5_ml_evaluation_and_robustness() -> None:
    client = Client()

    # 1. Time-series data synthesis (100 sequential periods)
    X = np.arange(100, dtype=np.float64).reshape(-1, 1)
    y = 2.5 * X.squeeze() + 5.0

    # 2. Chronological train/test split - Verify ZERO future leakage
    split = client.ml.split_chronological(X, y, train_ratio=0.75)
    X_train, y_train, X_test, y_test = split
    assert len(X_train) == 75
    assert len(X_test) == 25
    assert np.max(X_train) < np.min(X_test)  # Strict time ordering

    # 3. Fit reference linear model
    model = SimpleLinearRegressionModel()
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # 4. Evaluate regression metrics
    metrics = client.ml.evaluate_regression(y_test, y_pred)
    assert metrics.mae < 1e-4
    assert metrics.rmse < 1e-4
    assert metrics.r_squared == pytest.approx(1.0, abs=1e-4)

    # 5. Evaluate classification metrics
    y_cls_true = np.array([1, 0, 1, 1, 0, 0, 1, 0])
    y_cls_pred = np.array([1, 0, 1, 0, 0, 0, 1, 1])
    cls_metrics = client.ml.evaluate_classification(y_cls_true, y_cls_pred)
    assert 0.0 <= cls_metrics.accuracy <= 1.0
    assert 0.0 <= cls_metrics.f1_score <= 1.0

    # 6. Adversarial input noise robustness attack
    rob_result = client.ml.evaluate_robustness(
        model=model,
        X_test=X_test,
        y_test=y_test,
        attack_type="gaussian_noise",
        severity=0.10,
        random_seed=42,
    )
    assert rob_result.attack_type in ("gaussian_noise", "gaussian_noise_injection")
    # Adding noise to a perfect linear predictor increases its MAE
    assert rob_result.attacked_metric >= rob_result.baseline_metric


# ==============================================================================
# Workflow 6: Genuine Plugin Extensibility & Benchmarking
# ==============================================================================

def test_workflow_6_plugin_extensibility_and_benchmarking() -> None:
    client = Client()

    # 1. Verify standard built-in plugins exist
    plugins = client.plugins.list()
    plugin_ids = [p.plugin_id for p in plugins]
    assert "builtin.historical_simulation" in plugin_ids
    assert "builtin.parametric_gaussian" in plugin_ids
    assert "builtin.ewma" in plugin_ids

    # 2. Register custom experimental model plugin
    class CustomLaplaceRiskPlugin(ModelPlugin):
        @property
        def metadata(self) -> PluginMetadata:
            return PluginMetadata(
                plugin_id="custom.laplace_risk",
                name="Laplace Double Exponential Risk Model",
                description="Heavy-tailed symmetric distribution model for asset returns.",
                plugin_version="1.0.0",
                api_version="1.0.0",
                supported_data_types=("return_series",),
                capabilities=("volatility", "var", "expected_shortfall"),
            )

        def validate_input(self, data: Any, config: Dict[str, Any]) -> None:
            arr = np.asarray(data, dtype=np.float64)
            if len(arr) < 5:
                raise ValueError("Requires >= 5 observations")

        def execute(self, data: Any, config: Dict[str, Any]) -> ModelExecutionResult:
            arr = np.asarray(data, dtype=np.float64)
            vol = float(np.std(arr, ddof=1) * math.sqrt(252.0))
            # Laplace 95% quantile factor = -ln(2 * 0.05) = ln(10) approx 2.3026
            var_95 = float(np.std(arr, ddof=1) * (math.log(10.0) / math.sqrt(2.0)))
            return ModelExecutionResult(
                plugin_id=self.metadata.plugin_id,
                model_version=self.metadata.plugin_version,
                metrics={"volatility_annualized": vol, "var_95": var_95, "expected_shortfall_95": var_95 * 1.25},
                execution_time_ms=1.2,
                observations_used=len(arr),
            )

    registry = client.plugins.registry
    custom_plugin = CustomLaplaceRiskPlugin()
    registry.register(custom_plugin, overwrite=True)

    # 3. Retrieve and execute custom plugin
    retrieved = registry.get("custom.laplace_risk")
    assert retrieved.metadata.name == "Laplace Double Exponential Risk Model"

    sample_returns = [0.01, -0.02, 0.015, -0.03, 0.005, -0.008, 0.012, -0.025, 0.018, -0.01]
    res = retrieved.execute(sample_returns, {})
    assert res.metrics["var_95"] > 0.0

    # 4. Model benchmark execution across plugins
    bench_spec = BenchmarkSpecification(
        benchmark_id="bench_wf6",
        name="Plugin Extensibility Benchmark",
        description="Comparing built-in and custom plugins.",
        dataset_id="sample_returns",
        plugin_ids=("builtin.historical_simulation", "builtin.parametric_gaussian", "custom.laplace_risk"),
        metrics_to_compare=("volatility_annualized", "var_95"),
    )
    bench_rep = execute_model_benchmark(bench_spec, dataset=sample_returns, registry=registry)
    assert len(bench_rep.model_entries) == 3
    assert all(e.status == "completed" for e in bench_rep.model_entries)


# ==============================================================================
# Workflow 7: Experiment Lifecycle, Cryptographic Hashes & Drift Detection
# ==============================================================================

def test_workflow_7_experiment_lifecycle_and_reproducibility() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = Client(catalog_dir=tmp_dir)

        returns = [0.01, -0.015, 0.02, -0.025, 0.005, -0.01, 0.015, -0.005, 0.012, -0.018]

        # 1. Define and execute structured experiment
        spec_def = StudioExperimentDefinition(
            experiment_id="exp_audit_001",
            name="Quarterly Risk Review",
            description="Testing core risk under volatility and lookback perturbations.",
            dataset_id="test_dataset_001",
            baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
            perturbation_specs=[
                {"type": "return_friction", "experiment_id": "pert_fric_10", "parameters": {"friction_bps": 10.0}},
            ],
        )
        report = client.experiments.run(spec_def, dataset=returns)
        assert report.experiment_id == "exp_audit_001"
        assert report.status in ("completed", "completed_with_warnings")

        # 2. Verify report was persisted in catalog
        cataloged = client.experiments.get("exp_audit_001")
        assert cataloged is not None
        assert cataloged.experiment_id == "exp_audit_001"
        assert cataloged.input_fingerprint == report.input_fingerprint

        # 3. Drift detection: compare report with a perturbed data run
        perturbed_returns = list(returns)
        perturbed_returns[0] += 0.05  # data shock

        spec_def_drift = StudioExperimentDefinition(
            experiment_id="exp_audit_002",
            name="Quarterly Risk Review (Perturbed)",
            description="Run on perturbed dataset.",
            dataset_id="test_dataset_001",
            baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
            perturbation_specs=[
                {"type": "return_friction", "experiment_id": "pert_fric_10", "parameters": {"friction_bps": 10.0}},
            ],
        )
        report_drift = client.experiments.run(spec_def_drift, dataset=perturbed_returns)

        comp = client.experiments.compare(report, report_drift)
        # Verify that data drift was correctly identified
        assert comp.input_data_identical is False
        assert comp.comparable is False
        assert any("Input data hashes differ" in r for r in comp.non_comparable_reasons)


# ==============================================================================
# Workflow 8: Multi-Format Reporting (JSON, Markdown, CSV) with Numerical Integrity
# ==============================================================================

def test_workflow_8_multi_format_reporting_numerical_integrity() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = Client(catalog_dir=tmp_dir)

        returns = [0.01, -0.015, 0.02, -0.025, 0.005, -0.01, 0.015, -0.005, 0.012, -0.018]

        spec_def = StudioExperimentDefinition(
            experiment_id="exp_rep_001",
            name="Reporting Invariance Test",
            description="Verify exported formats match in-memory metrics.",
            dataset_id="test_dataset_rep",
            baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
            perturbation_specs=[
                {"type": "return_friction", "experiment_id": "pert_fric_5", "parameters": {"friction_bps": 5.0}},
            ],
        )
        report = client.experiments.run(spec_def, dataset=returns)

        # 1. JSON Export
        json_str = client.reports.to_json(report)
        parsed_json = json.loads(json_str)
        assert parsed_json["experiment_id"] == "exp_rep_001"
        assert parsed_json["baseline_metrics"]["volatility_annualized"] == pytest.approx(
            report.baseline_metrics["volatility_annualized"]
        )

        # 2. Markdown Export
        md_str = client.reports.to_markdown(report)
        assert "# FragilityShield — Experiment Report: Reporting Invariance Test" in md_str
        assert "Baseline Risk Metrics" in md_str
        assert "annualized_volatility" in md_str

        csv_str = client.reports.to_csv(report)
        assert "experiment_id,report_id,status" in csv_str
        assert "volatility_annualized" in csv_str


# ==============================================================================
# Workflow 9: Invalid Inputs, Conflict Rejection & Leakage Safeguards
# ==============================================================================

def test_workflow_9_invalid_inputs_and_leakage_safeguards() -> None:
    client = Client()

    # 1. Rejection of invalid Holding parameters (zero/negative price or quantity)
    with pytest.raises(ValueError, match="strictly positive and finite"):
        Holding("ASSET1", 0.0, 100.0)

    with pytest.raises(ValueError, match="strictly positive and finite"):
        Holding("ASSET1", 10.0, -50.0)

    # 2. Rejection of non-finite numbers in returns
    with pytest.raises(ValueError):
        client.risk.calculate([0.01, np.nan, -0.02])

    with pytest.raises(ValueError):
        client.risk.calculate([0.01, np.inf, -0.02])

    # 3. Rejection of sample insufficiency (N < 2 for volatility)
    with pytest.raises(ValueError):
        client.risk.calculate([0.01])

    # 4. Scenario conflict rejection: simultaneous asset-level and sector-level shocks
    port = client.portfolios.create(
        "conflict_port",
        "Conflict Port",
        "INR",
        holdings=[Holding("INFY", 10.0, 1500.0, "Technology")],
    )
    with pytest.raises(ValueError, match="Conflicting scenario rules targeting holding"):
        client.scenarios.execute(
            portfolio=port,
            sector_shocks={"Technology": -0.10},
            asset_shocks={"INFY": -0.05},  # Conflict!
        )

    # 5. Invalid EWMA decay factor rejection
    with pytest.raises(ValueError):
        client.fragility.run_volatility_estimator([0.01, -0.01, 0.02], decay_factor=1.5)

    with pytest.raises(ValueError):
        client.fragility.run_volatility_estimator([0.01, -0.01, 0.02], decay_factor=-0.1)

    # 6. Chronological split forbids backward lookahead / random shuffling
    X = np.arange(20).reshape(-1, 1)
    y = np.arange(20)
    split = client.ml.split_chronological(X, y, train_ratio=0.70)
    assert np.max(split.y_train) < np.min(split.y_test)
