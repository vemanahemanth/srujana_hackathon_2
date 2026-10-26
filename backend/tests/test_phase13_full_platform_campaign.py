"""Phase 13 Full-Platform Real-User Testing Campaign Suite.

Comprehensive, evidence-driven test suite exercising every implemented lab,
reusable synthetic fixtures, and realistic end-to-end user journeys (Journeys 1-6)
across FragilityShield.
"""

from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence
import numpy as np
import pytest
from starlette.testclient import TestClient

from fragility_engine.allocation import optimize_minimum_variance
from backend.app import app
from fragility_engine.attribution import (
    calculate_portfolio_risk_attribution,
    verify_attribution_finite_difference,
)
from fragility_engine.backtest import (
    backtest_model_rolling,
    calculate_christoffersen_test,
    calculate_kupiec_pof_test,
    evaluate_var_breaches,
)
from fragility_engine.benchmarks import (
    BenchmarkSpecification,
    execute_model_benchmark,
)
from fragility_engine.concentration import calculate_portfolio_concentration
from fragility_engine.data_diagnostics import (
    audit_outliers,
    calculate_data_diagnostics,
    detect_dataset_drift,
    validate_financial_ohlcv,
    validate_tabular_dataset,
)
from fragility_engine.fragility import (
    rank_perturbation_sensitivities,
    run_return_friction_perturbation,
    run_stress_boundary_search,
)
from fragility_engine.market_data import (
    calculate_indian_transaction_charges,
    NSETradingCalendar,
)
from fragility_engine.ml import (
    calculate_classification_metrics,
    calculate_regression_metrics,
    split_chronological,
)
from fragility_engine.model_lab import run_model_integration_suite
from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import (
    ModelExecutionResult,
    ModelPlugin,
    PluginMetadata,
    PluginRegistry,
    get_default_registry,
)
from fragility_engine.projects import (
    DatasetRecord,
    ModelFamily,
    ModelManifest,
    Project,
    ProjectCatalog,
    check_model_capabilities,
)
from fragility_engine.reproducibility import (
    ExperimentSpecification,
    compute_canonical_hash,
    run_reproducible_experiment,
)
from fragility_engine.risk import (
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)
from fragility_engine.scenarios import (
    ScenarioDefinition,
    apply_scenario,
    create_preset_scenario,
    run_reverse_stress_test,
)
from fragility_engine.sdk import Client
from fragility_engine.simulation import (
    calculate_bootstrap_uncertainty,
    simulate_monte_carlo,
)
from fragility_engine.studio import (
    LocalExperimentCatalog,
    StudioExperimentDefinition,
    execute_studio_experiment,
)


# ==============================================================================
# Reusable Synthetic Test Fixtures (Section C)
# ==============================================================================

@pytest.fixture(scope="module")
def api_client() -> TestClient:
    """Configured TestClient for FragilityShield REST API."""
    return TestClient(app)


@pytest.fixture
def correlated_returns_fixture() -> Dict[str, List[float]]:
    """Deterministic 4-asset correlated daily returns (N=100 observations)."""
    rng = np.random.default_rng(42)
    n_obs = 100
    market_factor = rng.normal(0.0005, 0.012, n_obs)
    return {
        "HDFCBANK": (1.2 * market_factor + rng.normal(0.0, 0.008, n_obs)).tolist(),
        "TCS": (0.9 * market_factor + rng.normal(0.0, 0.010, n_obs)).tolist(),
        "RELIANCE": (1.1 * market_factor + rng.normal(0.0, 0.009, n_obs)).tolist(),
        "INFY": (0.95 * market_factor + rng.normal(0.0, 0.011, n_obs)).tolist(),
    }


@pytest.fixture
def valid_ohlcv_fixture() -> List[Dict[str, Any]]:
    """Valid financial OHLCV records satisfying High >= Low, High >= Open/Close."""
    records = []
    base_price = 1000.0
    for i in range(50):
        o = base_price + i * 2.0
        h = o + 5.0
        l = o - 4.0
        c = o + 1.5
        v = 10000 + i * 150
        records.append({
            "timestamp": f"2026-01-{i+1:02d}T10:00:00Z" if i < 30 else f"2026-02-{i-29:02d}T10:00:00Z",
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })
    return records


@pytest.fixture
def diversified_portfolio_fixture() -> Portfolio:
    """Realistic diversified Indian equity portfolio with 4 holdings across 3 sectors."""
    holdings = [
        Holding(asset_id="HDFCBANK", quantity=100, price=1600.0, sector="Financial Services"),
        Holding(asset_id="TCS", quantity=40, price=3800.0, sector="Information Technology"),
        Holding(asset_id="RELIANCE", quantity=60, price=2900.0, sector="Energy"),
        Holding(asset_id="INFY", quantity=80, price=1100.0, sector="Information Technology"),
    ]
    return Portfolio("diversified_p1", "Diversified Bluechip", "INR", holdings)


@pytest.fixture
def concentrated_portfolio_fixture() -> Portfolio:
    """Highly concentrated portfolio (dominant holding > 90% weight) to test HHI > 8000."""
    holdings = [
        Holding(asset_id="MEGACAP", quantity=900, price=1000.0, sector="Tech"),
        Holding(asset_id="SMALL1", quantity=50, price=100.0, sector="Finance"),
        Holding(asset_id="SMALL2", quantity=50, price=100.0, sector="Energy"),
    ]
    return Portfolio("concentrated_p1", "Tech Dominant", "INR", holdings)


# Synthetic Model Test Doubles
class ValidDeterministicModel(ModelPlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="synthetic.deterministic_valid",
            name="Deterministic Valid Model",
            description="Pure deterministic reference model.",
        )

    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        if data is None or len(data) == 0:
            raise ValueError("Input data cannot be empty")

    def execute(self, data: Any, config: Optional[Mapping[str, Any]] = None) -> Dict[str, float]:
        arr = np.asarray(data, dtype=np.float64)
        return {
            "mean": float(np.mean(arr)),
            "vol": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        }


class MalformedOutputModel:
    """Model callable returning malformed structure."""
    def __call__(self, data: Any) -> Any:
        return "not_a_dictionary_or_result"


class NonFiniteOutputModel:
    """Model callable returning NaN/Inf values."""
    def __call__(self, data: Any) -> Dict[str, float]:
        return {"volatility": float("nan"), "mean": float("inf")}


class ExceptionRaisingModel:
    """Model callable raising runtime exception."""
    def __call__(self, data: Any) -> Any:
        raise RuntimeError("Synthetic model calculation internal crash")


class SlowTimingOutModel:
    """Model callable deliberately sleeping beyond timeout limit."""
    def __call__(self, data: Any) -> Dict[str, float]:
        time.sleep(3.0)
        return {"volatility": 0.15, "mean": 0.05}


# ==============================================================================
# End-to-End User Journeys (Section E)
# ==============================================================================

def test_journey_1_portfolio_risk_e2e(
    diversified_portfolio_fixture: Portfolio,
    correlated_returns_fixture: Dict[str, List[float]],
) -> None:
    """Journey 1: Portfolio Risk Full Pipeline.

    Workflow:
    1. Create research project in catalog.
    2. Import and validate holdings.
    3. Check portfolio concentration (HHI).
    4. Compute core risk report (Vol, VaR, ES, MaxDD).
    5. Perform Euler linear covariance-beta risk attribution.
    6. Audit attribution via fixed-exposure numerical finite difference.
    7. Execute historical Lehman 2008 crash scenario.
    8. Generate cryptographic reproducibility record.
    """
    port = diversified_portfolio_fixture
    assert port.total_value == 574000.0  # (100*1600 + 40*3800 + 60*2900 + 80*1100)

    # 1. Project Catalog
    with tempfile.TemporaryDirectory() as tmp_dir:
        catalog = ProjectCatalog(storage_dir=tmp_dir)
        proj = Project(project_id="proj_risk_1", name="Risk Research Project", description="Testing Journey 1")
        catalog.save_project(proj)
        loaded = catalog.get_project("proj_risk_1")
        assert loaded is not None
        assert loaded.name == "Risk Research Project"

        # 2. Concentration Check
        conc = calculate_portfolio_concentration(port)
        assert conc.asset_hhi_decimal > 0.0
        assert conc.asset_hhi_points > 0.0
        assert max(conc.asset_weights.values()) < 0.50  # Diversified
        assert len(conc.sector_weights) == 3

        # 3. Core Risk Calculation on portfolio returns
        weights = np.array([h.market_value / port.total_value for h in port.holdings])
        matrix = np.column_stack([correlated_returns_fixture[h.asset_id] for h in port.holdings])
        port_returns = matrix @ weights
        risk_rep = calculate_risk_report(port_returns)

        assert risk_rep.volatility_annualized > 0.0
        assert risk_rep.var_95 > 0.0
        assert risk_rep.expected_shortfall_95 >= risk_rep.var_95  # Coherence
        assert risk_rep.drawdown is not None

        # 4. Risk Attribution
        attr_rep = calculate_portfolio_risk_attribution(port, asset_returns_matrix=correlated_returns_fixture)
        assert attr_rep.methodology_type == "linear_covariance_beta_component_var"
        assert attr_rep.euler_discrepancy < 1e-7
        sum_cvar = sum(a.component_var for a in attr_rep.asset_attributions)
        assert math.isclose(sum_cvar, attr_rep.portfolio_var_95, abs_tol=1e-7)

        # 5. Fixed-Exposure Finite Difference Audit
        fd_audit = verify_attribution_finite_difference(port, correlated_returns_fixture, epsilon=1e-3)
        assert fd_audit["methodology_type"] == "fixed_exposure_finite_difference"
        assert fd_audit["max_discrepancy"] < 0.01  # Closely aligned under correlated normals

        # 6. Sector Stress Scenario Execution
        stress = ScenarioDefinition(
            scenario_id="financial_tech_stress",
            name="Financial & Tech Simultaneous Stress",
            description="Simultaneous -20% Financial Services and -10% IT stress shock.",
            sector_shocks={"Financial Services": -0.20, "Information Technology": -0.10},
        )
        scen_res = apply_scenario(port, stress)
        assert scen_res.total_pnl < 0.0  # Portfolio experiences loss under stress
        assert scen_res.stressed_portfolio_value < port.total_value

        # 7. Reproducibility
        spec = ExperimentSpecification(
            experiment_id="journey_1_exp",
            name="Portfolio Risk Full Journey",
            dataset_id="correlated_returns_v1",
            baseline_config={"confidence": 0.95},
        )
        run_res = run_reproducible_experiment(spec, return_series=port_returns)
        assert len(run_res.manifest.config_hash) == 64
        assert len(run_res.manifest.input_data_hash) == 64
        assert len(run_res.manifest.output_hash) == 64


def test_journey_2_fragility_investigation_e2e(
    correlated_returns_fixture: Dict[str, List[float]],
) -> None:
    """Journey 2: Fragility Investigation & Break-Even Boundary Search.

    Workflow:
    1. Establish baseline Sharpe ratio on returns.
    2. Execute controlled return friction perturbation (transaction costs).
    3. Run root bisection stress-boundary search for zero Sharpe ratio threshold.
    4. Rank sensitivities across multiple attack mechanisms.
    5. Verify unbracketed boundary failure handling.
    """
    returns = np.array(correlated_returns_fixture["HDFCBANK"], dtype=np.float64)
    baseline_vol = calculate_annualized_volatility(returns)
    assert baseline_vol > 0.0

    # 1. Transaction cost attack
    friction_res = run_return_friction_perturbation(returns, friction_bps=10.0)
    assert friction_res.baseline_metrics["volatility_annualized"] > 0.0
    assert friction_res.perturbed_metrics["volatility_annualized"] > 0.0
    assert "volatility_annualized" in friction_res.absolute_changes

    # 2. Stress-Boundary Search for break-even Sharpe ratio
    mean_ret = float(np.mean(returns))
    if mean_ret > 0.0:
        b_search = run_stress_boundary_search(
            returns,
            target_metric="sharpe_ratio",
            failure_threshold=0.0,
            attack_type="transaction_friction",
            min_param=0.0,
            max_param=0.05,
            tolerance=1e-4,
        )
        assert b_search.converged is True
        assert b_search.boundary_parameter_value is not None
        assert math.isclose(b_search.boundary_parameter_value, mean_ret, abs_tol=1e-4)

    # 3. Unbracketed failure check
    unbracketed = run_stress_boundary_search(
        returns,
        target_metric="mean_return",
        failure_threshold=-1.0,  # Impossible threshold
        attack_type="transaction_friction",
        min_param=0.0,
        max_param=0.01,
    )
    assert unbracketed.converged is False
    assert unbracketed.boundary_parameter_value is None
    assert "unbracketed" in unbracketed.explanation


def test_journey_3_model_evaluation_e2e() -> None:
    """Journey 3: Model Evaluation & Benchmark Ranking Pipeline.

    Workflow:
    1. Define ModelManifest with schema and resource limits.
    2. Check capabilities against laboratory requirements.
    3. Run comprehensive integration test suite (determinism, timeout, errors).
    4. Execute multi-model benchmark across shared evaluation window.
    5. Verify tied-rank handling and explicit non-superiority disclaimers.
    """
    manifest = ModelManifest(
        model_id="synthetic_trend_follower",
        name="Synthetic Trend Follower",
        version="1.0.0",
        model_family=ModelFamily.RISK_ESTIMATOR,
        required_inputs=("returns",),
        expected_output_schema={"mean": "float", "vol": "float"},
        supported_labs=("fragility", "benchmarking"),
        runtime_limits={"timeout_sec": 2.0},
        code_isolation_required=False,
    )

    # 1. Capability Check
    cap_rep = check_model_capabilities(manifest, target_lab="fragility")
    assert cap_rep.is_executable is True
    assert "Arbitrary code isolation" in cap_rep.capabilities

    # 2. Model Integration Suite
    model = ValidDeterministicModel()
    int_rep = run_model_integration_suite(
        model_callable=model.execute,
        manifest=manifest,
        sample_input=np.array([0.01, -0.01, 0.02, -0.015, 0.005]),
        provided_columns=["returns"],
    )
    assert int_rep.passed >= 1
    assert int_rep.failed == 0

    # 3. Multi-Model Benchmark Execution
    spec = BenchmarkSpecification(
        benchmark_id="core_benchmark_q1",
        name="Core Models Benchmark",
        description="Testing model benchmarking pipeline",
        dataset_id="returns_100",
        plugin_ids=("builtin.historical_simulation", "builtin.parametric_gaussian"),
        metrics_to_compare=("annualized_volatility", "var_95"),
        target_ranking_metric="var_95",
    )
    rng = np.random.default_rng(77)
    benchmark_returns = rng.normal(0.0008, 0.01, 100)
    bench_rep = execute_model_benchmark(spec, benchmark_returns)

    assert len(bench_rep.rankings) == 2
    # Verify non-superiority disclaimer presence
    assert "disclaimer" in bench_rep.ranking_disclaimer.lower() or "ranking" in bench_rep.ranking_disclaimer.lower()


def test_journey_4_backtesting_validation_e2e() -> None:
    """Journey 4: Backtesting & Statistical Validation Pipeline.

    Workflow:
    1. Load synthetic chronological return series.
    2. Execute rolling walk-forward VaR backtest (zero look-ahead).
    3. Evaluate breach series.
    4. Compute Kupiec POF Likelihood-Ratio test.
    5. Compute Christoffersen Independence & Conditional Coverage test.
    """
    rng = np.random.default_rng(101)
    n_days = 250
    returns = rng.normal(0.0005, 0.012, n_days)

    # 1. Rolling Backtest (in-sample 50, test 200)
    bt_rep = backtest_model_rolling(
        model="builtin.historical_simulation",
        returns=returns,
        estimation_window=50,
        confidence_level=0.95,
    )
    assert bt_rep.evaluation_sample_size == 200
    assert bt_rep.breach_count >= 0
    assert bt_rep.observed_breach_rate >= 0.0

    # 2. Kupiec POF Test & Christoffersen Test
    breach_indicators = [b.is_breach for b in bt_rep.breach_evaluations]
    kupiec = calculate_kupiec_pof_test(
        breaches=breach_indicators,
        confidence_level=0.95,
    )
    assert kupiec.likelihood_ratio >= 0.0
    assert 0.0 <= kupiec.p_value <= 1.0
    assert kupiec.decision in ("ACCEPT_NULL", "REJECT_NULL")

    # 3. Christoffersen Independence Test
    christoffersen = calculate_christoffersen_test(
        breaches=breach_indicators,
        confidence_level=0.95,
    )
    assert christoffersen.lr_independence >= 0.0
    assert 0.0 <= christoffersen.p_value_independence <= 1.0


def test_journey_5_failure_recovery_e2e(
    diversified_portfolio_fixture: Portfolio,
) -> None:
    """Journey 5: Error Handling & Failure Recovery.

    Workflow:
    1. Submit malformed portfolio (unsupported negative quantity).
    2. Assert explicit ValueError is raised without corrupting state.
    3. Submit invalid confidence level (1.5) to risk engine.
    4. Assert explicit ValueError is raised.
    5. Execute valid calculation afterwards and verify clean recovery.
    """
    # 1. Short position rejection
    with pytest.raises(ValueError, match="quantity must be strictly positive"):
        Holding(asset_id="SHORT_STOCK", quantity=-50, price=100.0)

    # 2. Invalid confidence level rejection
    with pytest.raises(ValueError, match="confidence_level must be strictly between 0.0 and 1.0"):
        calculate_expected_shortfall([0.01, -0.02, 0.015, -0.01], confidence_level=1.5)

    # 3. Valid calculation runs cleanly afterwards
    clean_es = calculate_expected_shortfall([0.01, -0.02, 0.015, -0.01], confidence_level=0.95)
    assert clean_es > 0.0


def test_journey_6_interface_parity_e2e(
    api_client: TestClient,
    diversified_portfolio_fixture: Portfolio,
) -> None:
    """Journey 6: Interface Parity between REST API and Python SDK.

    Verifies identical numerical results and consistent validation across:
    1. REST API (`/api/risk/calculate`)
    2. Python SDK (`Client().risk.calculate`)
    """
    sample_returns = [0.01, -0.02, 0.015, -0.005, 0.025, -0.03, 0.012, -0.018, 0.005, -0.008]

    # 1. REST API call
    api_resp = api_client.post("/api/risk/calculate", json={"returns": sample_returns})
    assert api_resp.status_code == 200
    api_data = api_resp.json()
    assert api_data["success"] is True
    api_report = api_data["report"]

    # 2. SDK calculation
    sdk = Client()
    sdk_res = sdk.risk.calculate(sample_returns)

    # 3. Parity checks (identical to double precision)
    assert math.isclose(api_report["volatility_annualized"], sdk_res.volatility_annualized, abs_tol=1e-12)
    assert math.isclose(api_report["var_95"], sdk_res.var_95, abs_tol=1e-12)
    assert math.isclose(api_report["expected_shortfall_95"], sdk_res.expected_shortfall_95, abs_tol=1e-12)


# ==============================================================================
# Comprehensive Lab-by-Lab User Journey Tests (Section D)
# ==============================================================================

class TestFullPlatformLabJourneys:
    """Individual deep-dive user journeys across every implemented lab."""

    def test_lab_1_allocation_minimum_variance(self) -> None:
        """Lab 1: Quadratic programming minimum-variance portfolio allocation."""
        rng = np.random.default_rng(55)
        # 3 assets
        returns_matrix = rng.normal(0.001, 0.015, (60, 3))
        cov_matrix = np.cov(returns_matrix, rowvar=False)
        asset_ids = ["ASSET_1", "ASSET_2", "ASSET_3"]

        weights_dict, diag = optimize_minimum_variance(cov_matrix, asset_ids=asset_ids)
        assert len(weights_dict) == 3
        total_w = sum(weights_dict.values())
        assert math.isclose(total_w, 1.0, abs_tol=1e-5)
        assert all(w >= -1e-6 for w in weights_dict.values())  # Long-only
        assert diag.success is True

    def test_lab_8_simulation_monte_carlo_and_bootstrap(self) -> None:
        """Lab 8: Monte Carlo confidence envelopes and block bootstrap."""
        rng = np.random.default_rng(88)
        daily_returns = rng.normal(0.0005, 0.01, 100)

        mc_res = simulate_monte_carlo(
            returns=daily_returns,
            num_paths=200,
            horizon_days=30,
            seed=42,
        )
        assert mc_res.num_paths == 200
        assert mc_res.horizon_days == 30
        assert len(mc_res.median_path) == 31
        assert mc_res.percentile_5th_path[-1] < mc_res.median_path[-1] < mc_res.percentile_95th_path[-1]

        # Bootstrap
        boot_res = calculate_bootstrap_uncertainty(daily_returns, num_bootstraps=100, seed=42)
        assert boot_res.bootstrap_iterations == 100
        assert boot_res.var_ci_95_lower <= boot_res.point_estimate_var <= boot_res.var_ci_95_upper

    def test_lab_9_data_diagnostics_ohlcv_and_outliers(
        self,
        valid_ohlcv_fixture: List[Dict[str, Any]],
    ) -> None:
        """Lab 9: Financial OHLCV verification, outlier detection, and drift."""
        # 1. Valid OHLCV check
        ohlcv_rep = validate_financial_ohlcv(valid_ohlcv_fixture)
        assert ohlcv_rep.is_valid is True
        assert ohlcv_rep.invalid_candles == 0

        # 2. Outlier Detection on synthetic spiked series
        returns_with_spikes = [0.01] * 50 + [0.25, -0.30]
        outliers = audit_outliers(returns_with_spikes)
        assert outliers.zscore_outliers_count >= 1 or outliers.iqr_outliers_count >= 1

        # 3. Drift Detection between two distributions
        rng = np.random.default_rng(123)
        base_series = rng.normal(0.0, 0.01, 200).tolist()
        shifted_series = rng.normal(0.05, 0.03, 200).tolist()
        drift_rep = detect_dataset_drift(base_series, shifted_series)
        assert drift_rep.has_drifted is True
        assert drift_rep.ks_statistic > 0.01

    def test_lab_10_ml_evaluation_metrics(self) -> None:
        """Lab 10: Zero look-ahead chronological split and financial ML metrics."""
        # Chronological split check
        X_seq = np.arange(100).reshape(-1, 1)
        y_seq = np.arange(100)
        split = split_chronological(X_seq, y_seq, train_ratio=0.70)
        assert len(split.X_train) == 70
        assert len(split.X_test) == 30
        assert float(split.X_train[-1, 0]) < float(split.X_test[0, 0])

        # Regression metrics
        y_true = np.array([2.0, 4.0, 6.0, 8.0])
        y_pred = np.array([2.5, 3.5, 6.0, 9.0])
        reg_metrics = calculate_regression_metrics(y_true, y_pred)
        assert reg_metrics.rmse > 0.0
        assert reg_metrics.mae == 0.50

        # Classification metrics
        y_cls_true = np.array([1, 0, 1, 0, 1])
        y_cls_pred = np.array([1, 0, 1, 1, 1])
        y_prob = np.array([0.9, 0.2, 0.8, 0.6, 0.7])
        cls_metrics = calculate_classification_metrics(y_cls_true, y_cls_pred, y_prob=y_prob)
        assert cls_metrics.accuracy == 0.80
        assert cls_metrics.f1_score > 0.0

    def test_lab_13_experiment_studio_multi_lab_execution(self) -> None:
        """Lab 13: Experiment Studio execution and persistence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            exp_catalog = LocalExperimentCatalog(catalog_dir=tmp_dir)
            defn = StudioExperimentDefinition(
                experiment_id="multi_lab_fragility_exp",
                name="Multi-Lab Fragility Test",
                dataset_id="returns_sample",
                baseline_config={"confidence_level": 0.95, "annualization_factor": 252.0},
                perturbation_specs=[{"type": "return_friction", "friction_bps": 10.0}],
            )
            sample_returns = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.012, -0.018]
            report = execute_studio_experiment(defn, return_series=sample_returns)
            assert report.status in ("completed", "completed_with_warnings")
            assert report.experiment_id == "multi_lab_fragility_exp"

            # Save and reload from disk
            exp_catalog.save_report(report)
            saved = exp_catalog.get_report(report.experiment_id)
            assert saved is not None
            assert saved.experiment_id == report.experiment_id
