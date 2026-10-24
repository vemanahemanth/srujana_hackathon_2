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
]
