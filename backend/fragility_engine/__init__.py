"""FragilityShield Quantitative Engine.

Core calculations, domain contracts, and testing harness for financial and ML models.
"""

from fragility_engine.concentration import (
    ConcentrationAnalysis,
    calculate_hhi,
    calculate_portfolio_concentration,
    calculate_sector_allocations,
)
from fragility_engine.models import Holding, MetricResult, Portfolio
from fragility_engine.portfolio_loader import (
    REQUIRED_CSV_COLUMNS,
    export_portfolio_to_csv,
    load_portfolio_from_csv,
    load_portfolio_from_json,
)
from fragility_engine.returns import compute_simple_returns
from fragility_engine.risk import (
    DrawdownResult,
    RiskMetricsReport,
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)
from fragility_engine.scenarios import (
    HoldingScenarioResult,
    ScenarioDefinition,
    ScenarioResult,
    SectorScenarioResult,
    apply_scenario,
    create_preset_scenario,
    validate_scenario_against_portfolio,
)
from fragility_engine.fragility import (
    FragilityExperimentResult,
    MetricSensitivityRanking,
    PerturbationImpact,
    calculate_ewma_volatility,
    calculate_portfolio_liquidation_shock,
    compute_changes,
    perturb_correlation_matrix,
    rank_perturbation_sensitivities,
    run_confidence_level_perturbation,
    run_correlation_perturbation,
    run_lookback_perturbation,
    run_return_friction_perturbation,
    run_volatility_estimator_perturbation,
)

from fragility_engine.reproducibility import (
    DriftReport,
    ExperimentSpecification,
    InvariantCheckReport,
    ReproducibilityManifest,
    ReproducibilityRunResult,
    canonical_json_dumps,
    compare_experiment_runs,
    compute_canonical_hash,
    compute_dataset_hash,
    run_reproducible_experiment,
    verify_experiment_invariants,
)

__version__ = "0.1.0"
__all__ = [
    # Domain Models
    "Holding",
    "Portfolio",
    "MetricResult",
    # Return Calculations
    "compute_simple_returns",
    # Portfolio Loader & Exporter
    "load_portfolio_from_json",
    "load_portfolio_from_csv",
    "export_portfolio_to_csv",
    "REQUIRED_CSV_COLUMNS",
    # Portfolio Allocation & Concentration
    "ConcentrationAnalysis",
    "calculate_hhi",
    "calculate_sector_allocations",
    "calculate_portfolio_concentration",
    # Risk Calculation Engine
    "DrawdownResult",
    "RiskMetricsReport",
    "calculate_annualized_volatility",
    "calculate_historical_var",
    "calculate_expected_shortfall",
    "calculate_maximum_drawdown",
    "calculate_risk_report",
    # Scenario Lab Engine
    "ScenarioDefinition",
    "HoldingScenarioResult",
    "SectorScenarioResult",
    "ScenarioResult",
    "validate_scenario_against_portfolio",
    "apply_scenario",
    "create_preset_scenario",
    # Fragility Lab Engine
    "PerturbationImpact",
    "FragilityExperimentResult",
    "MetricSensitivityRanking",
    "compute_changes",
    "run_lookback_perturbation",
    "calculate_ewma_volatility",
    "run_volatility_estimator_perturbation",
    "run_return_friction_perturbation",
    "calculate_portfolio_liquidation_shock",
    "perturb_correlation_matrix",
    "run_correlation_perturbation",
    "run_confidence_level_perturbation",
    "rank_perturbation_sensitivities",
    # Validation & Reproducibility Lab Engine (Phase 6)
    "canonical_json_dumps",
    "compute_canonical_hash",
    "compute_dataset_hash",
    "ExperimentSpecification",
    "ReproducibilityManifest",
    "InvariantCheckReport",
    "verify_experiment_invariants",
    "ReproducibilityRunResult",
    "run_reproducible_experiment",
    "DriftReport",
    "compare_experiment_runs",
]
