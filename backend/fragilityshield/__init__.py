"""FragilityShield — Official Public Python SDK.

The quantitative risk research, model testing, and assumption fragility laboratory.

Usage Example:
    >>> import fragilityshield as fs
    >>>
    >>> # Define custom risk model
    >>> class MyRiskModel(fs.RiskModel):
    ...     def calculate_risk(self, returns, parameters):
    ...         vol = np.std(returns) * np.sqrt(252)
    ...         var_95 = 1.645 * np.std(returns)
    ...         return fs.RiskMetricsOutput(
    ...             var_95=float(var_95),
    ...             expected_shortfall_95=float(var_95 * 1.25),
    ...             annualized_volatility=float(vol),
    ...         )
    >>>
    >>> # Register and execute
    >>> client = fs.Client()
    >>> model = MyRiskModel("my_model", "My Custom Model")
    >>> client.models.register(model)
    >>> result = client.models.execute("my_model", [0.01, -0.02, 0.015, -0.005, 0.02])
"""

from fragilityshield.contracts import (
    BaseModel,
    RiskModel,
    ForecastingModel,
    CustomMetric,
    SimulationEngine,
    TradingStrategy,
    RiskMetricsOutput,
    ForecastOutput,
    MetricOutput,
    SimulationOutput,
    StrategySignalsOutput,
    ParameterDefinition,
    FloatParam,
    IntParam,
    ChoiceParam,
    BoolParam,
    ModelCategory,
    ModelMetadata,
    ModelContractValidationError,
    CapabilityStatus,
)

from fragilityshield.client import (
    Client,
    ModelRegistryClient,
    DashboardClient,
)

__version__ = "1.0.0"
__all__ = [
    "Client",
    "ModelRegistryClient",
    "DashboardClient",
    "BaseModel",
    "RiskModel",
    "ForecastingModel",
    "CustomMetric",
    "SimulationEngine",
    "TradingStrategy",
    "RiskMetricsOutput",
    "ForecastOutput",
    "MetricOutput",
    "SimulationOutput",
    "StrategySignalsOutput",
    "ParameterDefinition",
    "FloatParam",
    "IntParam",
    "ChoiceParam",
    "BoolParam",
    "ModelCategory",
    "ModelMetadata",
    "ModelContractValidationError",
    "CapabilityStatus",
]
