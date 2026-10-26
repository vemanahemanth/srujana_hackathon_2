"""FragilityShield — Official Python SDK (Phase 10 / Master Architecture).

This module implements the unified client-facing Python SDK for FragilityShield,
exposing all domain engines (Portfolio, Risk, Scenarios, Fragility, Allocation,
Validation, ML Model Testing, Market Data, Experiments, Plugins, Reports)
through a single, typed, plug-and-play `Client` interface.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union
import numpy as np

from fragility_engine.external_connectivity import (
    ExecutionEnvironment,
    ExternalArtifactRef,
    ExternalMetric,
    ExternalPrediction,
    ExternalRunSubmission,
    IngestionResult,
    get_ingestion_engine,
    SchemaValidationError,
    ArtifactValidationError,
    ExternalIngestionError,
)

from fragility_engine.allocation import (
    AllocationComparisonResult,
    AllocationResult,
    adjust_portfolio_weights,
    calculate_transaction_cost,
    calculate_turnover,
    compare_allocations,
    create_equal_weighted_portfolio,
    optimize_minimum_variance,
)
from fragility_engine.data_diagnostics import (
    audit_outliers,
    detect_dataset_drift,
    detect_train_test_contamination,
    screen_target_leakage,
    validate_financial_ohlcv,
    validate_tabular_dataset,
)
from fragility_engine.fragility import (
    FragilityAuditReport,
    FragilityExperimentResult,
    MetricSensitivityRanking,
    StressBoundaryResult,
    calculate_portfolio_liquidation_shock,
    perturb_correlation_matrix,
    rank_perturbation_sensitivities,
    run_confidence_level_perturbation,
    run_correlation_perturbation,
    run_fragility_audit,
    run_lookback_perturbation,
    run_missing_data_attack,
    run_outlier_sensitivity_attack,
    run_regime_shift_attack,
    run_return_friction_perturbation,
    run_stress_boundary_search,
    run_volatility_estimator_perturbation,
)
from fragility_engine.model_lab import (
    IntegrationTestResult,
    IntegrationTestStatus,
    ModelIntegrationReport,
    run_determinism_test,
    run_error_handling_test,
    run_input_contract_test,
    run_model_integration_suite,
    run_model_smoke_test,
    run_numeric_validity_test,
    run_output_contract_test,
    run_timeout_test,
    run_version_change_test,
)
from fragility_engine.projects import (
    ArtifactEntity,
    CapabilityItem,
    CapabilityReport,
    CapabilityStatus,
    DatasetRecord,
    ExperimentEntity,
    ModelFamily,
    ModelManifest,
    Project,
    ProjectCatalog,
    ResultEntity,
    RunEntity,
    RunStatus,
    check_model_capabilities,
)
from fragility_engine.market_data import (
    DataProvider,
    DataProviderRecord,
    DataProviderRegistry,
    NSEOfflineSampleDataProvider,
    NSETradingCalendar,
    ProviderCapability,
    ProviderLifecycleStatus,
    UnsupportedCapabilityError,
    calculate_indian_transaction_charges,
    get_default_provider_registry,
)
from fragility_engine.upstox import (
    CanonicalCandle,
    CanonicalQuote,
    UpstoxAuthStatus,
    UpstoxConfig,
    UpstoxInstrument,
    UpstoxMarketDataAdapter,
)
from fragility_engine.ml import (
    BaseMLModel,
    MLDataSplit,
    MLMetricsResult,
    MLRobustnessResult,
    calculate_classification_metrics,
    calculate_forecasting_metrics,
    calculate_regression_metrics,
    evaluate_ml_robustness,
    split_chronological,
)
from fragility_engine.models import Holding, Portfolio, PortfolioSnapshot
from fragility_engine.plugins import PluginManifest, PluginRegistry, get_global_registry
from fragility_engine.portfolio_loader import load_portfolio_from_csv, load_portfolio_from_json
from fragility_engine.risk import (
    RiskReport,
    calculate_annualized_volatility,
    calculate_beta,
    calculate_calmar_ratio,
    calculate_capture_ratios,
    calculate_correlation_matrix,
    calculate_covariance_matrix,
    calculate_downside_deviation,
    calculate_risk_report,
    calculate_rolling_volatility,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
)
from fragility_engine.scenarios import (
    ReverseStressResult,
    Scenario,
    ScenarioResult,
    apply_correlation_stress,
    execute_scenario,
    list_preset_scenarios,
    run_reverse_stress_test,
)
from fragility_engine.studio import (
    ExperimentReport,
    LocalExperimentCatalog,
    StudioComparisonReport,
    StudioExperimentDefinition,
    compare_experiment_reports,
    execute_studio_experiment,
)
from fragility_engine.validation import (
    ValidationRecord,
    ValidationSuiteReport,
    run_portfolio_consistency_tests,
    run_reference_value_tests,
)


class PortfolioManager:
    """Manages creation, loading, inspection, and local caching of portfolios."""

    def __init__(self, catalog_dir: Optional[str] = None) -> None:
        self._portfolios: Dict[str, Portfolio] = {}

    def create(
        self,
        portfolio_id: str,
        name: str,
        currency: str = "INR",
        holdings: Optional[Sequence[Union[Holding, Dict[str, Any]]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Portfolio:
        """Create a new validated Portfolio instance."""
        parsed_holdings: List[Holding] = []
        if holdings:
            for h in holdings:
                if isinstance(h, Holding):
                    parsed_holdings.append(h)
                elif isinstance(h, dict):
                    parsed_holdings.append(Holding.from_dict(h))
                else:
                    raise TypeError(f"Invalid holding type: {type(h)}")

        p = Portfolio(
            portfolio_id=portfolio_id,
            name=name,
            currency=currency,
            holdings=tuple(parsed_holdings),
            metadata=metadata or {},
        )
        self._portfolios[p.portfolio_id] = p
        return p

    def load_csv(self, filepath: str) -> Portfolio:
        """Load and validate portfolio from CSV file."""
        p = load_portfolio_from_csv(filepath)
        self._portfolios[p.portfolio_id] = p
        return p

    def load_json(self, filepath: str) -> Portfolio:
        """Load and validate portfolio from JSON file."""
        p = load_portfolio_from_json(filepath)
        self._portfolios[p.portfolio_id] = p
        return p

    def get(self, portfolio_id: str) -> Optional[Portfolio]:
        """Retrieve portfolio by ID from in-memory cache."""
        return self._portfolios.get(portfolio_id)

    def list(self) -> List[Portfolio]:
        """List all cached portfolios."""
        return list(self._portfolios.values())


class RiskManager:
    """Manages risk metric calculations, volatility estimators, and ratio analysis."""

    def calculate(
        self,
        returns: Sequence[float] | np.ndarray,
        portfolio: Optional[Portfolio] = None,
        annualization_factor: float = 252.0,
        risk_free_rate: float = 0.0,
    ) -> RiskReport:
        """Calculate comprehensive risk report for a return series."""
        return calculate_risk_report(
            returns=returns,
            annualization_factor=annualization_factor,
        )

    def rolling_volatility(
        self,
        returns: Sequence[float] | np.ndarray,
        window: int = 20,
        annualization_factor: float = 252.0,
    ) -> np.ndarray:
        """Calculate rolling annualized volatility."""
        return calculate_rolling_volatility(returns, window=window, annualization_factor=annualization_factor)

    def sharpe_ratio(
        self,
        returns: Sequence[float] | np.ndarray,
        risk_free_rate: float = 0.0,
        annualization_factor: float = 252.0,
    ) -> float:
        """Calculate annualized Sharpe ratio."""
        return calculate_sharpe_ratio(returns, risk_free_rate=risk_free_rate, annualization_factor=annualization_factor)

    def sortino_ratio(
        self,
        returns: Sequence[float] | np.ndarray,
        required_return: float = 0.0,
        annualization_factor: float = 252.0,
    ) -> float:
        """Calculate annualized Sortino ratio."""
        return calculate_sortino_ratio(returns, required_return=required_return, annualization_factor=annualization_factor)

    def calmar_ratio(
        self,
        returns: Sequence[float] | np.ndarray,
        annualization_factor: float = 252.0,
    ) -> float:
        """Calculate annualized Calmar ratio."""
        return calculate_calmar_ratio(returns, annualization_factor=annualization_factor)

    def covariance_matrix(self, returns_matrix: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
        """Calculate sample covariance matrix with ddof=1."""
        return calculate_covariance_matrix(returns_matrix)

    def correlation_matrix(self, returns_matrix: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
        """Calculate sample Pearson correlation matrix."""
        return calculate_correlation_matrix(returns_matrix)

    def beta(
        self,
        asset_returns: Sequence[float] | np.ndarray,
        benchmark_returns: Sequence[float] | np.ndarray,
    ) -> float:
        """Calculate single-factor market beta."""
        return calculate_beta(asset_returns, benchmark_returns)

    def capture_ratios(
        self,
        asset_returns: Sequence[float] | np.ndarray,
        benchmark_returns: Sequence[float] | np.ndarray,
    ) -> Dict[str, Optional[float]]:
        """Calculate upside, downside, and overall capture ratios."""
        return calculate_capture_ratios(asset_returns, benchmark_returns)


class ScenarioManager:
    """Manages scenario simulation, macroeconomic presets, and correlation stress."""

    def list_presets(self) -> List[Scenario]:
        """List all available standardized scenario presets."""
        return list_preset_scenarios()

    def execute(
        self,
        portfolio: Portfolio,
        asset_shocks: Optional[Mapping[str, float]] = None,
        sector_shocks: Optional[Mapping[str, float]] = None,
        scenario_id: str = "custom_scenario",
        name: str = "Custom Scenario",
        description: str = "",
    ) -> ScenarioResult:
        """Execute a custom scenario with exact P&L reconciliation."""
        scen = Scenario(
            scenario_id=scenario_id,
            name=name,
            description=description,
            asset_shocks=asset_shocks or {},
            sector_shocks=sector_shocks or {},
        )
        return execute_scenario(portfolio, scen)

    def execute_preset(self, portfolio: Portfolio, preset_id: str) -> ScenarioResult:
        """Execute one of the standardized presets by ID."""
        presets = {p.scenario_id: p for p in list_preset_scenarios()}
        if preset_id not in presets:
            raise KeyError(f"Unknown scenario preset: '{preset_id}'. Available: {list(presets.keys())}")
        return execute_scenario(portfolio, presets[preset_id])

    def stress_correlation(
        self,
        cov_matrix: np.ndarray,
        stress_correlation: float = 0.85,
        stress_factor: Optional[float] = None,
    ) -> np.ndarray:
        """Perturb correlation matrix while preserving positive semi-definiteness."""
        factor = stress_factor if stress_factor is not None else stress_correlation
        return apply_correlation_stress(cov_matrix, stress_correlation=factor)

    def run_reverse_stress(
        self,
        portfolio: Portfolio,
        target_loss_pct: float = 0.15,
        shock_target: str = "market",
        target_identifier: Optional[str] = None,
    ) -> ReverseStressResult:
        """Solve for the required shock magnitude reaching a target portfolio loss threshold (§5, §7)."""
        return run_reverse_stress_test(
            portfolio=portfolio,
            target_loss_pct=target_loss_pct,
            shock_target=shock_target,
            target_identifier=target_identifier,
        )


class FragilityManager:
    """Manages assumption testing, parameter perturbations, and sensitivity audits."""

    def run_audit(
        self,
        returns: Sequence[float] | np.ndarray,
        target_metric: str = "volatility_annualized",
        audit_id: str = "audit_sdk",
    ) -> FragilityAuditReport:
        """Execute a 5-attack fragility audit with automated sensitivity ranking."""
        return run_fragility_audit(returns, target_metric=target_metric, audit_id=audit_id)

    def run_lookback(
        self,
        returns: Sequence[float] | np.ndarray,
        perturbed_window: int,
        experiment_id: str = "exp_lookback",
    ) -> FragilityExperimentResult:
        """Evaluate sensitivity to lookback window length."""
        return run_lookback_perturbation(returns, perturbed_window=perturbed_window, experiment_id=experiment_id)

    def run_volatility_estimator(
        self,
        returns: Sequence[float] | np.ndarray,
        decay_factor: float = 0.94,
        experiment_id: str = "exp_estimator",
    ) -> FragilityExperimentResult:
        """Evaluate sensitivity to volatility estimator (sample vs EWMA)."""
        return run_volatility_estimator_perturbation(returns, decay_factor=decay_factor, experiment_id=experiment_id)

    def run_confidence_level(
        self,
        returns: Sequence[float] | np.ndarray,
        baseline_confidence: float = 0.95,
        perturbed_confidence: float = 0.99,
        experiment_id: str = "exp_conf",
    ) -> FragilityExperimentResult:
        """Evaluate tail risk expansion across confidence levels."""
        return run_confidence_level_perturbation(
            returns,
            baseline_confidence=baseline_confidence,
            perturbed_confidence=perturbed_confidence,
            experiment_id=experiment_id,
        )

    def run_friction(
        self,
        returns: Sequence[float] | np.ndarray,
        friction_bps: float = 15.0,
        experiment_id: str = "exp_friction",
    ) -> FragilityExperimentResult:
        """Evaluate impact of trading frictions and slippage on tail risk."""
        return run_return_friction_perturbation(returns, friction_bps=friction_bps, experiment_id=experiment_id)

    def run_outliers(
        self,
        returns: Sequence[float] | np.ndarray,
        trim_pct: float = 0.05,
        method: str = "winsorize",
        experiment_id: str = "exp_outliers",
    ) -> FragilityExperimentResult:
        """Evaluate vulnerability to extreme outlier tail returns."""
        return run_outlier_sensitivity_attack(returns, trim_pct=trim_pct, method=method, experiment_id=experiment_id)

    def run_missing_data(
        self,
        returns: Sequence[float] | np.ndarray,
        drop_rate: float = 0.05,
        impute_method: str = "forward_fill",
        experiment_id: str = "exp_missing_data",
    ) -> FragilityExperimentResult:
        """Evaluate robustness to missing observations and imputation policies."""
        return run_missing_data_attack(returns, drop_rate=drop_rate, impute_method=impute_method, experiment_id=experiment_id)

    def run_regime_shift(
        self,
        returns: Sequence[float] | np.ndarray,
        window_length: Optional[int] = None,
        experiment_id: str = "exp_regime_shift",
    ) -> FragilityExperimentResult:
        """Evaluate fragility under a market regime shift."""
        return run_regime_shift_attack(returns, window_length=window_length, experiment_id=experiment_id)

    def rank_sensitivities(
        self,
        experiments: Sequence[FragilityExperimentResult],
        target_metric: str,
    ) -> MetricSensitivityRanking:
        """Rank executed experiments by absolute impact on a designated metric."""
        return rank_perturbation_sensitivities(experiments, target_metric=target_metric)

    def search_stress_boundary(
        self,
        returns: Sequence[float] | np.ndarray,
        target_metric: str = "sharpe_ratio",
        failure_threshold: float = 0.0,
        attack_type: str = "transaction_friction",
        min_param: float = 0.0,
        max_param: float = 0.05,
        tolerance: float = 1e-4,
        max_iter: int = 30,
    ) -> StressBoundaryResult:
        """Search for the parameter threshold where a model crosses an acceptance failure boundary (§6, §8)."""
        return run_stress_boundary_search(
            returns=returns,
            target_metric=target_metric,
            failure_threshold=failure_threshold,
            attack_type=attack_type,
            min_param=min_param,
            max_param=max_param,
            tolerance=tolerance,
            max_iter=max_iter,
        )


class AllocationManager:
    """Manages portfolio rebalancing, turnover, cost estimation, and optimization."""

    def create_equal_weighted(self, portfolio: Portfolio) -> Portfolio:
        """Create an equal-weighted target portfolio."""
        return create_equal_weighted_portfolio(portfolio)

    def adjust_weights(self, portfolio: Portfolio, target_weights: Mapping[str, float]) -> Portfolio:
        """Adjust portfolio weights while preserving total valuation."""
        return adjust_portfolio_weights(portfolio, target_weights)

    def turnover(self, current_weights: Mapping[str, float], target_weights: Mapping[str, float]) -> float:
        """Calculate one-way turnover: 0.5 * sum(|w_new - w_old|)."""
        return calculate_turnover(current_weights, target_weights)

    def transaction_cost(
        self,
        current_weights: Mapping[str, float],
        target_weights: Mapping[str, float],
        total_value: float,
        cost_bps: float = 10.0,
    ) -> float:
        """Estimate rebalancing transaction cost in currency units."""
        return calculate_transaction_cost(current_weights, target_weights, total_value=total_value, cost_bps=cost_bps)

    def optimize_minimum_variance(
        self,
        cov_matrix: Sequence[Sequence[float]] | np.ndarray,
        asset_ids: Sequence[str],
        min_weight: float = 0.0,
        max_weight: float = 1.0,
    ) -> AllocationResult:
        """Perform long-only or box-constrained minimum variance quadratic optimization."""
        return optimize_minimum_variance(cov_matrix, asset_ids, min_weight=min_weight, max_weight=max_weight)

    def compare(
        self,
        original_portfolio: Portfolio,
        target: Union[Portfolio, Mapping[str, float]],
        asset_returns_matrix: Optional[np.ndarray] = None,
        cost_bps: float = 10.0,
        diagnostics: Optional[Any] = None,
    ) -> AllocationComparisonResult:
        """Comprehensive comparison of original vs target portfolio allocation."""
        if isinstance(target, Portfolio):
            adj_port = target
        else:
            adj_port = adjust_portfolio_weights(original_portfolio, target)
        return compare_allocations(
            original_portfolio=original_portfolio,
            adjusted_portfolio=adj_port,
            asset_returns_matrix=asset_returns_matrix,
            transaction_cost_bps=cost_bps,
            diagnostics=diagnostics,
        )


class ValidationManager:
    """Manages analytical validation suites, invariant checks, and consistency audits."""

    def run_reference_values(self) -> ValidationSuiteReport:
        """Execute the 5 analytical reference value tests against closed-form benchmarks."""
        return run_reference_value_tests()

    def run_portfolio_consistency(
        self,
        portfolio: Portfolio,
        returns: Optional[Sequence[float]] = None,
    ) -> ValidationSuiteReport:
        """Execute internal consistency tests on a portfolio."""
        return run_portfolio_consistency_tests(portfolio)


class MLManager:
    """Manages machine learning model evaluation, chronological splitting, and robustness attacks."""

    def split_chronological(
        self,
        X: Sequence[Any] | np.ndarray,
        y: Sequence[Any] | np.ndarray,
        train_ratio: float = 0.70,
    ) -> MLDataSplit:
        """Perform strictly ordered chronological train/validation/test split."""
        return split_chronological(X, y, train_ratio=train_ratio)

    def evaluate_regression(
        self,
        y_true: Sequence[float] | np.ndarray,
        y_pred: Sequence[float] | np.ndarray,
    ) -> MLMetricsResult:
        """Calculate regression validation metrics (MAE, RMSE, R2, MAPE)."""
        return calculate_regression_metrics(y_true, y_pred)

    def evaluate_classification(
        self,
        y_true: Sequence[int] | np.ndarray,
        y_pred: Sequence[int] | np.ndarray,
        y_prob: Optional[Sequence[float] | np.ndarray] = None,
    ) -> MLMetricsResult:
        """Calculate classification metrics (Accuracy, Precision, Recall, F1, ROC-AUC, Brier)."""
        return calculate_classification_metrics(y_true, y_pred, y_prob=y_prob)

    def evaluate_forecasting(
        self,
        y_true: Sequence[float] | np.ndarray,
        y_pred: Sequence[float] | np.ndarray,
        y_train: Optional[Sequence[float] | np.ndarray] = None,
    ) -> MLMetricsResult:
        """Calculate time-series forecasting metrics (MAE, RMSE, sMAE, MASE)."""
        return calculate_forecasting_metrics(y_true, y_pred, y_train=y_train)

    def evaluate_robustness(
        self,
        model: BaseMLModel,
        X_test: np.ndarray,
        y_test: np.ndarray,
        attack_type: Optional[str] = None,
        severity: Optional[float] = None,
        noise_stds: Sequence[float] = (0.01, 0.05, 0.10),
        missing_rates: Sequence[float] = (0.05, 0.10),
        random_seed: int = 42,
    ) -> Union[List[MLRobustnessResult], MLRobustnessResult]:
        """Stress-test a model under input noise or feature dropout perturbations."""
        if attack_type in ("gaussian_noise", "gaussian_noise_injection"):
            std = severity if severity is not None else 0.05
            results = evaluate_ml_robustness(
                model=model,
                X_test=X_test,
                y_test=y_test,
                noise_stds=(std,),
                missing_rates=(),
                seed=random_seed,
            )
            return results[0]
        elif attack_type in ("zero_dropout", "missing_masking"):
            rate = severity if severity is not None else 0.05
            results = evaluate_ml_robustness(
                model=model,
                X_test=X_test,
                y_test=y_test,
                noise_stds=(),
                missing_rates=(rate,),
                seed=random_seed,
            )
            return results[0]
        return evaluate_ml_robustness(
            model=model,
            X_test=X_test,
            y_test=y_test,
            noise_stds=noise_stds,
            missing_rates=missing_rates,
            seed=random_seed,
        )


class MarketDataManager:
    """Manages Indian market trading calendars, statutory charges, offline data, and Upstox market data."""

    def trading_calendar(self) -> NSETradingCalendar:
        """Get an NSE trading calendar instance."""
        return NSETradingCalendar()

    def transaction_charges(
        self,
        order_type: str,
        price: float,
        quantity: float,
    ) -> Dict[str, float]:
        """Calculate statutory Indian transaction taxes and charges (STT, GST, etc.)."""
        return calculate_indian_transaction_charges(order_type=order_type, price=price, quantity=quantity)

    def provider_registry(self) -> DataProviderRegistry:
        """Get the global DataProviderRegistry instance."""
        return get_default_provider_registry()

    def list_providers(self) -> List[DataProviderRecord]:
        """List registered market data providers with capabilities and lifecycle status."""
        return self.provider_registry().list_providers()

    def get_provider(self, provider_id: str) -> DataProvider:
        """Retrieve a registered provider by its identifier."""
        return self.provider_registry().get(provider_id)

    def verify_provider(self, provider_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Trigger an explicit verification check for a provider."""
        return self.provider_registry().verify_provider(provider_id=provider_id, timeout=timeout)

    def offline_sample_provider(self) -> NSEOfflineSampleDataProvider:
        """Get the deterministic offline sample data provider."""
        return NSEOfflineSampleDataProvider()

    def upstox_adapter(self, config: Optional[UpstoxConfig] = None) -> UpstoxMarketDataAdapter:
        """Get an Upstox V3 Market Data Adapter instance."""
        return UpstoxMarketDataAdapter(config=config)

    def upstox_status(self) -> UpstoxAuthStatus:
        """Check Upstox connection and authentication status."""
        return UpstoxMarketDataAdapter().check_connection()

    def resolve_upstox_instrument(self, symbol: str) -> UpstoxInstrument:
        """Resolve a human symbol or key to an UpstoxInstrument."""
        return UpstoxMarketDataAdapter().resolve_instrument(symbol)

    def get_upstox_candles(
        self,
        symbol: str,
        interval_unit: str = "days",
        interval: str = "1",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[CanonicalCandle]:
        """Fetch normalized historical OHLCV candles from Upstox."""
        return UpstoxMarketDataAdapter().get_historical_candles(
            symbol_or_key=symbol,
            interval_unit=interval_unit,
            interval=interval,
            from_date=from_date,
            to_date=to_date,
        )

    def get_upstox_quote(self, symbols: Sequence[str]) -> Dict[str, CanonicalQuote]:
        """Fetch market quotes from Upstox."""
        return UpstoxMarketDataAdapter().get_quote(symbols)

    def import_upstox_dataset(
        self,
        symbol: str,
        catalog: ProjectCatalog,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        dataset_name: Optional[str] = None,
    ) -> Any:
        """Fetch Upstox candles, validate OHLCV, and register in ProjectCatalog."""
        return UpstoxMarketDataAdapter().import_and_register_dataset(
            symbol_or_key=symbol,
            catalog=catalog,
            from_date=from_date,
            to_date=to_date,
            dataset_name=dataset_name,
        )


class ExperimentManager:
    """Manages reproducible experiment runs, persistence catalogs, and comparisons."""

    def __init__(self, catalog_dir: Optional[str] = None) -> None:
        cat_dir = catalog_dir or os.path.expanduser("~/.fragilityshield/experiments")
        self.catalog = LocalExperimentCatalog(catalog_dir=cat_dir)

    def run(
        self,
        definition: StudioExperimentDefinition,
        dataset: Optional[Sequence[float] | np.ndarray | Portfolio] = None,
        return_series: Optional[Sequence[float] | np.ndarray] = None,
        portfolio: Optional[Portfolio] = None,
    ) -> ExperimentReport:
        """Execute a structured studio experiment and record in the local catalog."""
        target_dataset = dataset if dataset is not None else (return_series if return_series is not None else portfolio)
        report = execute_studio_experiment(
            definition,
            dataset=target_dataset,
            return_series=return_series,
            portfolio=portfolio,
        )
        self.catalog.save_report(report, overwrite=True)
        return report

    def get(self, experiment_id: str) -> Optional[ExperimentReport]:
        """Retrieve an experiment report by ID."""
        try:
            return self.catalog.get_report(experiment_id)
        except (KeyError, FileNotFoundError):
            return None

    def list(self) -> List[Any]:
        """List all cataloged experiment records."""
        return self.catalog.list_reports()

    def compare(self, report_a: ExperimentReport, report_b: ExperimentReport) -> StudioComparisonReport:
        """Compare two experiment runs across datasets, baselines, and rankings."""
        return compare_experiment_reports(report_a, report_b)


class ReportManager:
    """Exports experiment reports to JSON, Markdown, and CSV."""

    def to_json(self, report: ExperimentReport) -> str:
        """Export report to canonical JSON."""
        return report.to_json()

    def to_markdown(self, report: ExperimentReport) -> str:
        """Export report to human-readable Markdown table."""
        return report.to_markdown()

    def to_csv(self, report: ExperimentReport) -> str:
        """Export report metrics to tabular CSV."""
        return report.to_csv()


class PluginManager:
    """Manages plugin discovery, registration, and inspection."""

    def __init__(self) -> None:
        self.registry: PluginRegistry = get_global_registry()

    def list(self) -> List[PluginManifest]:
        """List all registered plugins."""
        return self.registry.list_plugins()

    def get(self, plugin_id: str) -> Optional[PluginManifest]:
        """Get a registered plugin by ID."""
        return self.registry.get_plugin(plugin_id)


class ProjectManager:
    """Manages high-level research projects, asset universes, and experiment workspaces (Lab 1 & Blueprint §1)."""

    def __init__(self, catalog: Optional[ProjectCatalog] = None) -> None:
        self.catalog = catalog or ProjectCatalog()

    def create(
        self,
        project_id: str,
        name: str,
        description: str = "",
        objective: str = "Quantitative stress testing and model risk evaluation",
        asset_universe: Sequence[str] = ("NIFTY_50",),
        model_type: str = "portfolio",
    ) -> Project:
        """Create and register a new scientific research project workspace."""
        proj = Project(
            project_id=project_id,
            name=name,
            description=description,
            objective=objective,
            asset_universe=tuple(asset_universe),
            model_type=model_type,
        )
        self.catalog.save_project(proj)
        return proj

    def get(self, project_id: str) -> Optional[Project]:
        """Retrieve a project by ID."""
        return self.catalog.get_project(project_id)

    def list(self) -> List[Project]:
        """List all projects in the catalog."""
        return self.catalog.list_projects()


class DatasetManager:
    """Manages dataset registration, validation audits, and schema verification (Lab 1 & Blueprint §3)."""

    def __init__(self, catalog: Optional[ProjectCatalog] = None) -> None:
        self.catalog = catalog or ProjectCatalog()

    def register(
        self,
        dataset_id: str,
        name: str,
        version: str = "1.0.0",
        file_path: Optional[str] = None,
        format: str = "csv",
        row_count: int = 0,
        column_mapping: Optional[Mapping[str, str]] = None,
        symbols: Sequence[str] = (),
        timestamp_col: Optional[str] = None,
        frequency: str = "1D",
        currency: str = "INR",
        provenance: Optional[Mapping[str, Any]] = None,
        validation_summary: Optional[Mapping[str, Any]] = None,
    ) -> DatasetRecord:
        """Register a new observation dataset with schema mappings and provenance."""
        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            version=version,
            file_path=file_path,
            format=format,
            row_count=row_count,
            column_mapping=column_mapping or {},
            symbols=tuple(symbols),
            timestamp_col=timestamp_col,
            frequency=frequency,
            currency=currency,
            provenance=provenance or {},
            validation_summary=validation_summary or {},
        )
        self.catalog.save_dataset(record)
        return record

    def get(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Retrieve a dataset record by ID."""
        return self.catalog.get_dataset(dataset_id)

    def list(self) -> List[DatasetRecord]:
        """List all registered datasets."""
        return self.catalog.list_datasets()

    def validate_ohlcv(self, data: Any) -> Any:
        """Run strict financial OHLCV candlestick validation (non-positive prices, H<L, invalid volume)."""
        return validate_financial_ohlcv(data)

    def validate_tabular(
        self,
        data: Any,
        required_columns: Sequence[str],
        expected_numeric_columns: Optional[Sequence[str]] = None,
    ) -> Any:
        """Run tabular schema validation (missing values, types, duplicate rows)."""
        return validate_tabular_dataset(
            data,
            required_columns=required_columns,
            expected_numeric_columns=expected_numeric_columns,
        )

    def audit_outliers(
        self,
        series: Sequence[float],
        z_threshold: float = 3.0,
        iqr_factor: float = 1.5,
    ) -> Any:
        """Audit numerical outliers via Z-score and Tukey IQR fences."""
        return audit_outliers(series, z_threshold=z_threshold, iqr_factor=iqr_factor)

    def detect_drift(
        self,
        reference_series: Sequence[float],
        current_series: Sequence[float],
        p_value_threshold: float = 0.05,
    ) -> Any:
        """Detect dataset distribution drift using 2-sample Kolmogorov-Smirnov test."""
        return detect_dataset_drift(reference_series, current_series, p_value_threshold=p_value_threshold)

    def detect_contamination(
        self,
        train_samples: Sequence[Sequence[Any]],
        test_samples: Sequence[Sequence[Any]],
    ) -> Any:
        """Detect exact record contamination between train and test splits."""
        return detect_train_test_contamination(train_samples, test_samples)

    def screen_leakage(
        self,
        features_dict: Mapping[str, Sequence[float]],
        target: Sequence[float],
        correlation_threshold: float = 0.98,
    ) -> Any:
        """Screen features for suspicious target leakage."""
        return screen_target_leakage(features_dict, target, correlation_threshold=correlation_threshold)


class ModelLabManager:
    """Manages Lab 2 Model & Integration testing, capability verification, and contracts (Blueprint §2, §4)."""

    def __init__(self, catalog: Optional[ProjectCatalog] = None) -> None:
        self.catalog = catalog or ProjectCatalog()

    def register_manifest(self, manifest: ModelManifest) -> ModelManifest:
        """Register a model's common manifest and execution requirements."""
        self.catalog.save_model(manifest)
        return manifest

    def get_manifest(self, model_id: str) -> Optional[ModelManifest]:
        """Retrieve a model manifest by ID."""
        return self.catalog.get_model(model_id)

    def list_manifests(self) -> List[ModelManifest]:
        """List all registered model manifests."""
        return self.catalog.list_models()

    def check_capabilities(
        self,
        manifest: ModelManifest,
        target_lab: Optional[str] = None,
        test_name: Optional[str] = None,
    ) -> CapabilityReport:
        """Audit model capabilities against the canonical capability specification."""
        return check_model_capabilities(manifest, target_lab=target_lab, test_name=test_name)

    def run_integration_suite(
        self,
        model_callable: Any,
        manifest: ModelManifest,
        sample_input: Any,
        provided_columns: Optional[Sequence[str]] = None,
        malformed_inputs: Optional[Sequence[Any]] = None,
    ) -> ModelIntegrationReport:
        """Execute the comprehensive Lab 2 integration and contract verification suite."""
        return run_model_integration_suite(
            model_callable=model_callable,
            manifest=manifest,
            sample_input=sample_input,
            provided_columns=provided_columns,
            malformed_inputs=malformed_inputs,
        )


class ExternalConnectivityClient:
    """Universal external model and experiment connectivity client (§2).
    
    Enables external development environments to authenticate, register models and datasets,
    submit runs with metrics and predictions, upload verified artifacts, and inspect results:
    - Developer laptops (local scripts, CLI)
    - Google Colab notebooks
    - Jupyter notebooks
    - External Python research repositories
    - CI/CD workers & automated runners
    - Third-party model providers
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        workspace_id: str = "default_workspace",
        environment_type: str = "local_script",
        catalog: Optional[ProjectCatalog] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.api_url = (api_url or os.environ.get("FRAGILITYSHIELD_API_URL", "")).rstrip("/")
        self.api_token = api_token or os.environ.get("FRAGILITYSHIELD_API_TOKEN", "")
        self.workspace_id = workspace_id
        self.environment_type = environment_type
        self.catalog = catalog or ProjectCatalog()
        self.timeout = float(os.environ.get("FRAGILITYSHIELD_TIMEOUT", timeout))
        self.max_retries = int(os.environ.get("FRAGILITYSHIELD_MAX_RETRIES", max_retries))
        self._local_engine = get_ingestion_engine()

    def _execute_request(
        self,
        req: urllib.request.Request,
        is_idempotent: bool = False,
    ) -> bytes:
        """Execute HTTP request with connection timeout and bounded exponential backoff.
        
        Guarantees:
        - Strict timeout enforcement (default 30s).
        - Transient network/server errors (502, 503, 504, URLError) retried with jitter for idempotent operations.
        - Client errors (400, 401, 403, 404, 422) fail fast and are NEVER retried.
        """
        retries = self.max_retries if is_idempotent else 1
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                if 400 <= exc.code < 500:
                    raise
                if exc.code in (502, 503, 504) and attempt < retries - 1:
                    sleep_sec = 0.2 * (2 ** attempt) + random.uniform(0.01, 0.1)
                    time.sleep(sleep_sec)
                    continue
                raise
            except urllib.error.URLError as exc:
                last_exc = exc
                if attempt < retries - 1:
                    sleep_sec = 0.2 * (2 ** attempt) + random.uniform(0.01, 0.1)
                    time.sleep(sleep_sec)
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("Request failed without response.")

    def authenticate(self, api_token: str) -> None:
        """Authenticate using a scoped API credential (§2, §7)."""
        self.api_token = api_token.strip()

    def register_model(
        self,
        model_id: str,
        name: str,
        family: Union[ModelFamily, str] = ModelFamily.CUSTOM,
        version: str = "1.0.0",
        author: str = "external_researcher",
        description: str = "",
    ) -> ModelManifest:
        """Register or discover a model in the central platform (§2)."""
        fam = ModelFamily(family) if isinstance(family, str) else family
        manifest = ModelManifest(
            model_id=model_id,
            name=name,
            model_family=fam,
            version=version,
            owner=author,
        )
        self.catalog.save_model(manifest)
        return manifest

    def register_dataset(
        self,
        dataset_id: str,
        name: str,
        version: str = "1.0.0",
        file_path: Optional[str] = None,
        format: str = "csv",
        row_count: int = 0,
        symbols: Sequence[str] = (),
    ) -> DatasetRecord:
        """Register or select a dataset in the central platform (§2)."""
        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            version=version,
            file_path=file_path,
            format=format,
            row_count=row_count,
            symbols=tuple(symbols),
        )
        self.catalog.save_dataset(record)
        return record

    def submit_run(
        self,
        experiment_id: str,
        run_id: str,
        model_id: str,
        target_lab: str = "general",
        metrics: Optional[Sequence[Union[Dict[str, Any], ExternalMetric]]] = None,
        predictions: Optional[Sequence[Union[Dict[str, Any], ExternalPrediction]]] = None,
        artifacts: Optional[Sequence[Union[Dict[str, Any], ExternalArtifactRef]]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        run_status: str = "completed",
        error_message: Optional[str] = None,
        dataset_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
        model_version: str = "1.0.0",
        workspace_id: Optional[str] = None,
        environment: Optional[Union[Dict[str, Any], ExecutionEnvironment]] = None,
        auto_test_all: bool = False,
        test_profile_id: Optional[str] = None,
        returns: Optional[Sequence[float]] = None,
    ) -> IngestionResult:
        """Submit configuration, execution metadata, actual metrics, predictions, and optional auto test orchestrator (§2, §4)."""
        ws = workspace_id or self.workspace_id
        
        # Prepare environment
        if isinstance(environment, ExecutionEnvironment):
            env = environment
        elif isinstance(environment, dict):
            env = ExecutionEnvironment.from_dict(environment)
        else:
            py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            env = ExecutionEnvironment(
                environment_type=self.environment_type,
                python_version=py_ver,
            )

        # Convert metrics
        norm_metrics: List[Dict[str, Any]] = []
        if metrics:
            for m in metrics:
                if isinstance(m, ExternalMetric):
                    norm_metrics.append(m.to_dict())
                elif isinstance(m, dict):
                    norm_metrics.append(m)

        # Convert predictions
        norm_preds: List[Dict[str, Any]] = []
        if predictions:
            for p in predictions:
                if isinstance(p, ExternalPrediction):
                    norm_preds.append(p.to_dict())
                elif isinstance(p, dict):
                    norm_preds.append(p)

        # Convert artifacts
        norm_arts: List[Dict[str, Any]] = []
        if artifacts:
            for a in artifacts:
                if isinstance(a, ExternalArtifactRef):
                    norm_arts.append(a.to_dict())
                elif isinstance(a, dict):
                    norm_arts.append(a)

        payload = {
            "schema_version": "1.0.0",
            "workspace_id": ws,
            "experiment_id": experiment_id,
            "run_id": run_id,
            "model_id": model_id,
            "model_version": model_version,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "target_lab": target_lab,
            "run_status": run_status,
            "parameters": parameters or {},
            "metrics": norm_metrics,
            "predictions": norm_preds,
            "artifacts": norm_arts,
            "environment": env.to_dict(),
            "error_message": error_message,
            "auto_test_all": auto_test_all,
            "test_profile_id": test_profile_id,
        }
        if returns is not None:
            payload["returns"] = list(returns)

        if self.api_url:
            return self._http_submit_run(payload)

        return self._local_engine.ingest_run(payload)

    def _http_submit_run(self, payload: Dict[str, Any]) -> IngestionResult:
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Bypass-Tunnel-Reminder": "true",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        req = urllib.request.Request(
            f"{self.api_url}/api/ingest/runs",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            raw_bytes = self._execute_request(req, is_idempotent=False)
            res_data = json.loads(raw_bytes.decode("utf-8"))
            return IngestionResult(**res_data)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise ExternalIngestionError(f"HTTP {exc.code}: {err_body}")

    def upload_artifact(
        self,
        run_id: str,
        file_path: str,
        artifact_id: Optional[str] = None,
        name: Optional[str] = None,
        expected_sha256: Optional[str] = None,
    ) -> ExternalArtifactRef:
        """Upload a supported file artifact with SHA-256 validation (§2, §3)."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Artifact file not found: {file_path}")

        content_bytes = path.read_bytes()
        art_id = artifact_id or f"art_{int(time.time()*1000)}"
        art_name = name or path.name

        if self.api_url:
            return self._http_upload_artifact(run_id, art_id, art_name, content_bytes, expected_sha256)

        return self._local_engine.save_artifact_file(
            run_id=run_id,
            artifact_id=art_id,
            filename=art_name,
            content_bytes=content_bytes,
            expected_sha256=expected_sha256,
        )

    def _http_upload_artifact(
        self,
        run_id: str,
        artifact_id: str,
        name: str,
        content_bytes: bytes,
        expected_sha256: Optional[str],
    ) -> ExternalArtifactRef:
        url = f"{self.api_url}/api/ingest/artifacts?run_id={run_id}&artifact_id={artifact_id}&name={name}"
        if expected_sha256:
            url += f"&checksum_sha256={expected_sha256}"
        headers = {
            "Content-Type": "application/octet-stream",
            "Bypass-Tunnel-Reminder": "true",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        req = urllib.request.Request(url, data=content_bytes, headers=headers, method="POST")
        try:
            raw_bytes = self._execute_request(req, is_idempotent=False)
            data = json.loads(raw_bytes.decode("utf-8"))
            return ExternalArtifactRef.from_dict(data["artifact"])
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            raise ExternalIngestionError(f"HTTP {exc.code}: {err_body}")

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve execution details and results (§2)."""
        if self.api_url:
            headers = {"Bypass-Tunnel-Reminder": "true"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            req = urllib.request.Request(
                f"{self.api_url}/api/ingest/runs/{run_id}",
                headers=headers,
            )
            try:
                raw_bytes = self._execute_request(req, is_idempotent=True)
                data = json.loads(raw_bytes.decode("utf-8"))
                return data.get("run")
            except Exception:
                return None
        return self._local_engine.get_run(run_id)

    def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the applicable validation and processing status (§2)."""
        if self.api_url:
            headers = {"Bypass-Tunnel-Reminder": "true"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            req = urllib.request.Request(
                f"{self.api_url}/api/ingest/runs/{run_id}/status",
                headers=headers,
            )
            try:
                raw_bytes = self._execute_request(req, is_idempotent=True)
                return json.loads(raw_bytes.decode("utf-8"))
            except Exception:
                return None
        rec = self._local_engine.get_run(run_id)
        if not rec:
            return None
        return {
            "success": True,
            "run_id": run_id,
            "status": rec.get("status", "unknown"),
            "is_external": True,
            "lab": rec.get("lab", "general"),
            "has_recomputed_metrics": bool(rec.get("recomputed_metrics")),
            "error_message": rec.get("error_message"),
            "provenance_hash": rec.get("provenance_hash"),
        }

    def list_runs(
        self,
        workspace_id: Optional[str] = None,
        target_lab: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List ingested runs with optional filters."""
        if self.api_url:
            params = []
            if workspace_id:
                params.append(f"workspace_id={workspace_id}")
            if target_lab:
                params.append(f"target_lab={target_lab}")
            if status:
                params.append(f"status={status}")
            q = f"?{'&'.join(params)}" if params else ""
            headers = {"Bypass-Tunnel-Reminder": "true"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            req = urllib.request.Request(
                f"{self.api_url}/api/ingest/runs{q}",
                headers=headers,
            )
            try:
                raw_bytes = self._execute_request(req, is_idempotent=True)
                data = json.loads(raw_bytes.decode("utf-8"))
                return data.get("runs", [])
            except Exception:
                return []
        return self._local_engine.list_runs(workspace_id=workspace_id, target_lab=target_lab, status=status)


class OrchestratorClient:
    """FragilityShield Shared Test Orchestrator & Configuration Registry SDK Client (Phases 3, 5)."""

    def __init__(self, sdk_client: "Client") -> None:
        self._sdk = sdk_client
        self.api_url = sdk_client.external.api_url
        self.api_token = sdk_client.external.api_token

    def _request(self, endpoint: str, method: str = "GET", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_url:
            raise RuntimeError("API URL is required for remote orchestrator execution.")
        headers = {
            "Content-Type": "application/json",
            "Bypass-Tunnel-Reminder": "true",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            f"{self.api_url}{endpoint}",
            data=encoded_data,
            headers=headers,
            method=method,
        )
        is_idempotent = method in ("GET", "HEAD", "OPTIONS")
        raw_bytes = self._sdk.external._execute_request(req, is_idempotent=is_idempotent)
        return json.loads(raw_bytes.decode("utf-8"))

    def list_modules(self) -> List[Dict[str, Any]]:
        """List all registered quantitative test modules and metadata."""
        if self.api_url:
            res = self._request("/api/orchestrator/modules")
            return res.get("modules", [])
        from fragility_engine.orchestrator import get_test_orchestrator
        return get_test_orchestrator().list_registered_modules()

    def validate(
        self,
        experiment_type: str = "model",
        data: Optional[Dict[str, Any]] = None,
        profile_id: str = "test_all",
        selected_modules: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Validate candidate input dimensions against registered test modules."""
        payload = {
            "experiment_type": experiment_type,
            "data": data or {},
            "profile_id": profile_id,
            "selected_modules": selected_modules,
        }
        if self.api_url:
            return self._request("/api/orchestrator/validate", method="POST", data=payload)
        from fragility_engine.orchestrator import get_test_orchestrator, ExperimentType
        orch = get_test_orchestrator()
        try:
            exp_t = ExperimentType(experiment_type)
        except ValueError:
            exp_t = ExperimentType.MODEL
        app = orch.resolve_applicable_tests(
            experiment_type=exp_t,
            data_inputs=data or {},
            profile_id=profile_id,
            selected_modules=selected_modules,
        )
        return {
            "success": True,
            "applicable_count": len(app),
            "applicable_modules": app,
        }

    def test_all(
        self,
        experiment_id: str,
        run_id: Optional[str] = None,
        experiment_type: str = "model",
        target_identity: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute TEST ALL across all registered test modules supported by inputs."""
        return self.run_profile(
            profile_id="test_all",
            experiment_id=experiment_id,
            run_id=run_id,
            experiment_type=experiment_type,
            target_identity=target_identity,
            data=data,
            config_overrides=config_overrides,
            metadata=metadata,
        )

    def run_profile(
        self,
        profile_id: str,
        experiment_id: str,
        run_id: Optional[str] = None,
        experiment_type: str = "model",
        target_identity: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        selected_modules: Optional[List[str]] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a custom quantitative test profile."""
        sub_src = "colab_notebook" if self._sdk.external.environment_type == "google_colab" else "local_sdk"
        payload = {
            "experiment_id": experiment_id,
            "run_id": run_id or f"run_orch_{int(time.time()*1000)}",
            "submission_source": sub_src,
            "experiment_type": experiment_type,
            "target_identity": target_identity or {},
            "data": data or {},
            "profile_id": profile_id,
            "selected_modules": selected_modules,
            "config_overrides": config_overrides or {},
            "metadata": metadata or {},
        }
        if self.api_url:
            return self._request("/api/orchestrator/run", method="POST", data=payload)
        from fragility_engine.orchestrator import (
            get_test_orchestrator,
            ExperimentType,
            SubmissionSource,
        )
        orch = get_test_orchestrator()
        try:
            exp_t = ExperimentType(experiment_type)
        except ValueError:
            exp_t = ExperimentType.MODEL
        run = orch.execute_run(
            experiment_id=payload["experiment_id"],
            run_id=payload["run_id"],
            submission_source=SubmissionSource.LOCAL_SDK,
            experiment_type=exp_t,
            target_identity=payload["target_identity"],
            data_inputs=payload["data"],
            profile_id=profile_id,
            selected_modules=selected_modules,
            config_overrides=config_overrides,
            metadata=metadata,
        )
        return run.to_dict()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an orchestrated experiment run and test results."""
        if self.api_url:
            try:
                return self._request(f"/api/orchestrator/runs/{run_id}")
            except Exception:
                return None
        from fragility_engine.orchestrator import get_test_orchestrator
        run = get_test_orchestrator().get_run(run_id)
        return run.to_dict() if run else None

    def list_strategies(self) -> List[Dict[str, Any]]:
        if self.api_url:
            res = self._request("/api/configurations/strategies")
            return res.get("strategies", [])
        from fragility_engine.custom_configs import get_config_registry
        return [s.to_dict() for s in get_config_registry().list_strategies()]

    def save_strategy(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if self.api_url:
            return self._request("/api/configurations/strategies", method="POST", data=config)
        from fragility_engine.custom_configs import get_config_registry, CustomStrategyConfig
        cfg = CustomStrategyConfig(**config)
        get_config_registry().save_strategy(cfg)
        return {"success": True, "strategy": cfg.to_dict()}

    def list_scenarios(self) -> List[Dict[str, Any]]:
        if self.api_url:
            res = self._request("/api/configurations/scenarios")
            return res.get("scenarios", [])
        from fragility_engine.custom_configs import get_config_registry
        return [s.to_dict() for s in get_config_registry().list_scenarios()]

    def save_scenario(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if self.api_url:
            return self._request("/api/configurations/scenarios", method="POST", data=config)
        from fragility_engine.custom_configs import get_config_registry, CustomScenarioConfig
        cfg = CustomScenarioConfig(**config)
        get_config_registry().save_scenario(cfg)
        return {"success": True, "scenario": cfg.to_dict()}

    def list_profiles(self) -> List[Dict[str, Any]]:
        if self.api_url:
            res = self._request("/api/configurations/test-profiles")
            return res.get("profiles", [])
        from fragility_engine.custom_configs import get_config_registry
        return [p.to_dict() for p in get_config_registry().list_profiles()]

    def save_profile(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if self.api_url:
            return self._request("/api/configurations/test-profiles", method="POST", data=config)
        from fragility_engine.custom_configs import get_config_registry, CustomTestProfileConfig
        cfg = CustomTestProfileConfig(**config)
        get_config_registry().save_profile(cfg)
        return {"success": True, "profile": cfg.to_dict()}


class Client:
    """FragilityShield unified Python SDK Client.

    Example:
        >>> from fragility_engine.sdk import Client
        >>> client = Client()
        >>> proj = client.projects.create("p1", "NSE Alpha Research")
        >>> rep = client.risk.calculate([0.01, -0.02, 0.015, -0.005, 0.02])
        >>> audit = client.fragility.run_audit([0.01, -0.02, 0.015, -0.005, 0.02])
        >>> ext_sub = client.external.submit_run(
        ...     experiment_id="exp_01",
        ...     run_id="run_colab_01",
        ...     model_id="garch_vol",
        ...     metrics=[{"metric_name": "rmse", "observed_value": 0.0142}],
        ... )
        >>> test_all_run = client.orchestrator.test_all(
        ...     experiment_id="exp_01",
        ...     experiment_type="model",
        ...     data={"returns": [0.01, -0.02, 0.015, -0.005, 0.02]},
        ... )
    """

    def __init__(
        self,
        catalog_dir: Optional[str] = None,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        workspace_id: str = "default_workspace",
        environment_type: str = "local_script",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.catalog = ProjectCatalog(storage_dir=catalog_dir)
        self.projects = ProjectManager(catalog=self.catalog)
        self.datasets = DatasetManager(catalog=self.catalog)
        self.model_lab = ModelLabManager(catalog=self.catalog)
        self.portfolios = PortfolioManager(catalog_dir=catalog_dir)
        self.risk = RiskManager()
        self.scenarios = ScenarioManager()
        self.fragility = FragilityManager()
        self.allocation = AllocationManager()
        self.validation = ValidationManager()
        self.ml = MLManager()
        self.market_data = MarketDataManager()
        self.upstox = self.market_data.upstox_adapter()
        self.experiments = ExperimentManager(catalog_dir=catalog_dir)
        self.reports = ReportManager()
        self.plugins = PluginManager()
        self.external = ExternalConnectivityClient(
            api_url=api_url,
            api_token=api_token,
            workspace_id=workspace_id,
            environment_type=environment_type,
            catalog=self.catalog,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.orchestrator = OrchestratorClient(self)


FragilityShield = Client

