"""FragilityShield — Public Model & Strategy Contracts (SDK Core).

This module defines the official public contracts for extending FragilityShield with
user-defined quantitative models, forecasting algorithms, risk metrics,
Monte Carlo simulation engines, and trading strategies.

Key Guarantees:
1. Strict schema and numerical range validation (rejects NaN, Inf, and negative variances).
2. Explicit capability declarations (compatible labs can discover and test models).
3. Immutable parameter schemas with defaults, bounds, and type enforcement.
4. Framework-agnostic execution (pure Python / NumPy / SciPy / Pandas compatible).
"""

from __future__ import annotations

import abc
import enum
import math
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


class ModelCategory(str, enum.Enum):
    """Canonical functional categories of financial models in FragilityShield."""
    RISK_ESTIMATION = "risk_estimation"
    FORECASTING = "forecasting"
    CUSTOM_METRIC = "custom_metric"
    SIMULATION = "simulation"
    TRADING_STRATEGY = "trading_strategy"
    PORTFOLIO_ALLOCATION = "allocation"


class CapabilityStatus(str, enum.Enum):
    """Capability compatibility status."""
    COMPATIBLE = "Compatible"
    VALIDATED = "Validated"
    SUPPORTED = "Supported"
    NOT_APPLICABLE = "Not applicable"
    UNSUPPORTED = "Unsupported"
    REQUIRED = "Required before execution"


class ModelContractValidationError(ValueError):
    """Raised when model inputs, outputs, or parameters violate mathematical or schema invariants."""
    pass


# ==============================================================================
# 1. Parameter Definitions & Constraints
# ==============================================================================

@dataclass(frozen=True)
class ParameterDefinition:
    """Configurable parameter schema with validation constraints."""
    name: str
    param_type: str  # 'float', 'int', 'bool', 'choice', 'string'
    default: Any
    description: str = ""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Optional[Tuple[Any, ...]] = None

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Parameter name must be a non-empty string.")
        if self.param_type not in ("float", "int", "bool", "choice", "string"):
            raise ValueError(f"Unsupported parameter type: '{self.param_type}'")

    def validate(self, val: Any) -> Any:
        """Validate an input value against parameter constraints."""
        if val is None:
            return self.default

        if self.param_type == "float":
            try:
                f = float(val)
            except (ValueError, TypeError) as exc:
                raise ModelContractValidationError(f"Parameter '{self.name}' must be a float; got {val!r}") from exc
            if not math.isfinite(f):
                raise ModelContractValidationError(f"Parameter '{self.name}' must be finite; got {f}")
            if self.min_value is not None and f < self.min_value:
                raise ModelContractValidationError(f"Parameter '{self.name}' ({f}) below minimum {self.min_value}")
            if self.max_value is not None and f > self.max_value:
                raise ModelContractValidationError(f"Parameter '{self.name}' ({f}) exceeds maximum {self.max_value}")
            return f

        if self.param_type == "int":
            try:
                i = int(val)
            except (ValueError, TypeError) as exc:
                raise ModelContractValidationError(f"Parameter '{self.name}' must be an integer; got {val!r}") from exc
            if self.min_value is not None and i < int(self.min_value):
                raise ModelContractValidationError(f"Parameter '{self.name}' ({i}) below minimum {self.min_value}")
            if self.max_value is not None and i > int(self.max_value):
                raise ModelContractValidationError(f"Parameter '{self.name}' ({i}) exceeds maximum {self.max_value}")
            return i

        if self.param_type == "bool":
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return bool(val)

        if self.param_type == "choice":
            if self.choices and val not in self.choices:
                raise ModelContractValidationError(
                    f"Parameter '{self.name}' value {val!r} not in permitted choices: {self.choices}"
                )
            return val

        return str(val)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "param_type": self.param_type,
            "default": self.default,
            "description": self.description,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "choices": list(self.choices) if self.choices else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ParameterDefinition:
        choices = tuple(data["choices"]) if data.get("choices") is not None else None
        return cls(
            name=str(data["name"]),
            param_type=str(data.get("param_type", "float")),
            default=data.get("default"),
            description=str(data.get("description", "")),
            min_value=float(data["min_value"]) if data.get("min_value") is not None else None,
            max_value=float(data["max_value"]) if data.get("max_value") is not None else None,
            choices=choices,
        )


def FloatParam(name: str, default: float, description: str = "", min_value: Optional[float] = None, max_value: Optional[float] = None) -> ParameterDefinition:
    return ParameterDefinition(name=name, param_type="float", default=default, description=description, min_value=min_value, max_value=max_value)


def IntParam(name: str, default: int, description: str = "", min_value: Optional[int] = None, max_value: Optional[int] = None) -> ParameterDefinition:
    return ParameterDefinition(name=name, param_type="int", default=default, description=description, min_value=min_value, max_value=max_value)


def ChoiceParam(name: str, default: Any, choices: Sequence[Any], description: str = "") -> ParameterDefinition:
    return ParameterDefinition(name=name, param_type="choice", default=default, description=description, choices=tuple(choices))


def BoolParam(name: str, default: bool, description: str = "") -> ParameterDefinition:
    return ParameterDefinition(name=name, param_type="bool", default=default, description=description)


# ==============================================================================
# 2. Output Data Contracts
# ==============================================================================

@dataclass(frozen=True)
class RiskMetricsOutput:
    """Output contract for RiskModel evaluations."""
    var_95: float
    expected_shortfall_95: float
    annualized_volatility: float
    var_99: Optional[float] = None
    expected_shortfall_99: Optional[float] = None
    max_drawdown: Optional[float] = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    warnings: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key, val in [("var_95", self.var_95), ("expected_shortfall_95", self.expected_shortfall_95), ("annualized_volatility", self.annualized_volatility)]:
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ModelContractValidationError(f"Risk metric '{key}' must be a finite float; got {val!r}")
            if val < 0.0:
                raise ModelContractValidationError(f"Risk metric '{key}' cannot be negative; got {val}")

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "var_95": self.var_95,
            "expected_shortfall_95": self.expected_shortfall_95,
            "annualized_volatility": self.annualized_volatility,
            "var_99": self.var_99,
            "expected_shortfall_99": self.expected_shortfall_99,
            "max_drawdown": self.max_drawdown,
            "metrics": dict(self.metrics),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }
        d["metrics"]["var_95"] = self.var_95
        d["metrics"]["expected_shortfall_95"] = self.expected_shortfall_95
        d["metrics"]["annualized_volatility"] = self.annualized_volatility
        if self.var_99 is not None:
            d["metrics"]["var_99"] = self.var_99
        if self.expected_shortfall_99 is not None:
            d["metrics"]["expected_shortfall_99"] = self.expected_shortfall_99
        if self.max_drawdown is not None:
            d["metrics"]["max_drawdown"] = self.max_drawdown
        return d


@dataclass(frozen=True)
class ForecastOutput:
    """Output contract for ForecastingModel evaluations."""
    forecast: Tuple[float, ...]
    lower_ci: Tuple[float, ...]
    upper_ci: Tuple[float, ...]
    horizon: int
    metrics: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.forecast:
            raise ModelContractValidationError("Forecast output series cannot be empty.")
        if len(self.forecast) != len(self.lower_ci) or len(self.forecast) != len(self.upper_ci):
            raise ModelContractValidationError("Forecast, lower_ci, and upper_ci must have matching lengths.")
        for i, (f, l, u) in enumerate(zip(self.forecast, self.lower_ci, self.upper_ci)):
            if not (math.isfinite(f) and math.isfinite(l) and math.isfinite(u)):
                raise ModelContractValidationError(f"Forecast points at step {i} must be finite.")
            if l > u:
                raise ModelContractValidationError(f"Lower CI ({l}) exceeds upper CI ({u}) at step {i}.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "forecast": list(self.forecast),
            "lower_ci": list(self.lower_ci),
            "upper_ci": list(self.upper_ci),
            "horizon": self.horizon,
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MetricOutput:
    """Output contract for CustomMetric evaluations."""
    metric_name: str
    value: float
    unit: str = "fraction"
    display_name: str = ""
    interpretation: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ModelContractValidationError(f"Metric '{self.metric_name}' value must be finite; got {self.value}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "display_name": self.display_name or self.metric_name,
            "interpretation": self.interpretation,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SimulationOutput:
    """Output contract for SimulationEngine evaluations."""
    paths: Tuple[Tuple[float, ...], ...]
    terminal_values: Tuple[float, ...]
    mean_terminal: float
    median_terminal: float
    q05_terminal: float
    q95_terminal: float
    metrics: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.terminal_values:
            raise ModelContractValidationError("Simulation must produce non-empty terminal values.")
        for val in (self.mean_terminal, self.median_terminal, self.q05_terminal, self.q95_terminal):
            if not math.isfinite(val):
                raise ModelContractValidationError(f"Simulation summary statistics must be finite; got {val}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paths": [list(p) for p in self.paths[:20]],  # Cap sample paths in serialized envelope
            "terminal_values": list(self.terminal_values),
            "mean_terminal": self.mean_terminal,
            "median_terminal": self.median_terminal,
            "q05_terminal": self.q05_terminal,
            "q95_terminal": self.q95_terminal,
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StrategySignalsOutput:
    """Output contract for TradingStrategy evaluations."""
    target_weights: Mapping[str, float]
    signals: Mapping[str, float]
    turnover: float
    expected_return: Optional[float] = None
    expected_volatility: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        total_w = sum(self.target_weights.values())
        if abs(total_w - 1.0) > 0.05 and total_w != 0.0:
            # Allow zero total weight (all cash), otherwise weights must roughly sum to 1.0
            raise ModelContractValidationError(f"Strategy target weights must sum to 1.0; sum is {total_w:.4f}")
        for asset, w in self.target_weights.items():
            if not math.isfinite(w):
                raise ModelContractValidationError(f"Target weight for asset '{asset}' must be finite; got {w}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_weights": dict(self.target_weights),
            "signals": dict(self.signals),
            "turnover": self.turnover,
            "expected_return": self.expected_return,
            "expected_volatility": self.expected_volatility,
            "metadata": dict(self.metadata),
        }


# ==============================================================================
# 3. Model Metadata Contract
# ==============================================================================

@dataclass(frozen=True)
class ModelMetadata:
    """Immutable metadata and capability registration envelope for a user model."""
    model_id: str
    name: str
    category: ModelCategory
    version: str = "1.0.0"
    author: str = "quant_researcher"
    description: str = ""
    capabilities: Tuple[str, ...] = ()
    supported_labs: Tuple[str, ...] = ()
    parameters: Tuple[ParameterDefinition, ...] = ()
    is_enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.model_id or not isinstance(self.model_id, str):
            raise ValueError("model_id must be a non-empty string.")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", self.model_id):
            raise ValueError(f"Invalid model_id '{self.model_id}'. Only alphanumeric, _, -, and . permitted.")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "supported_labs": list(self.supported_labs),
            "parameters": [p.to_dict() for p in self.parameters],
            "is_enabled": self.is_enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelMetadata:
        params = tuple(ParameterDefinition.from_dict(p) for p in data.get("parameters", []))
        return cls(
            model_id=str(data["model_id"]),
            name=str(data["name"]),
            category=ModelCategory(data.get("category", "risk_estimation")),
            version=str(data.get("version", "1.0.0")),
            author=str(data.get("author", "quant_researcher")),
            description=str(data.get("description", "")),
            capabilities=tuple(data.get("capabilities", [])),
            supported_labs=tuple(data.get("supported_labs", [])),
            parameters=params,
            is_enabled=bool(data.get("is_enabled", True)),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


# ==============================================================================
# 4. Base Model & Domain Abstract Contracts
# ==============================================================================

class BaseModel(abc.ABC):
    """Abstract base class for all FragilityShield user models and extensions."""

    def __init__(
        self,
        model_id: str,
        name: str,
        category: ModelCategory,
        version: str = "1.0.0",
        author: str = "quant_researcher",
        description: str = "",
        capabilities: Optional[Sequence[str]] = None,
        supported_labs: Optional[Sequence[str]] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ) -> None:
        caps = tuple(capabilities or self.declare_capabilities())
        labs = tuple(supported_labs or self.declare_supported_labs())
        params = tuple(parameters or self.declare_parameters())
        self.metadata = ModelMetadata(
            model_id=model_id,
            name=name,
            category=category,
            version=version,
            author=author,
            description=description,
            capabilities=caps,
            supported_labs=labs,
            parameters=params,
        )

    @property
    def model_id(self) -> str:
        return self.metadata.model_id

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def category(self) -> ModelCategory:
        return self.metadata.category

    @abc.abstractmethod

    def declare_capabilities(self) -> Sequence[str]:
        """Declare metric and functional capabilities provided by this model."""
        return ()

    @abc.abstractmethod
    def declare_supported_labs(self) -> Sequence[str]:
        """Declare target labs compatible with this model."""
        return ()

    def declare_parameters(self) -> Sequence[ParameterDefinition]:
        """Declare configurable parameters and constraints."""
        return ()

    def resolve_parameters(self, user_params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Validate and resolve user parameter inputs against the parameter schema."""
        resolved: Dict[str, Any] = {}
        provided = dict(user_params or {})
        for param in self.metadata.parameters:
            val = provided.get(param.name, param.default)
            resolved[param.name] = param.validate(val)
        return resolved

    @abc.abstractmethod
    def validate_input(self, input_data: Any) -> None:
        """Validate that input data conforms to this model's required contract."""
        pass

    @abc.abstractmethod
    def execute(self, input_data: Any, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Execute the model and return a verified dictionary matching the category output contract."""
        pass

    def validate_contract(self) -> bool:
        """Validate that the model contract, parameters, and metadata are well-formed."""
        if not self.model_id or not isinstance(self.model_id, str):
            raise ModelContractValidationError("Model ID must be a non-empty string.")
        if not self.metadata.name:
            raise ModelContractValidationError("Model name must be declared.")
        for p in self.declare_parameters():
            if not isinstance(p, ParameterDefinition):
                raise ModelContractValidationError(f"Invalid parameter definition: {p}")
        return True

    def test_run(self, sample_input: Any, sample_params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Execute a local self-test and verify output conformity."""
        self.validate_input(sample_input)
        params = self.resolve_parameters(sample_params)
        start_t = time.perf_counter()
        result = self.execute(sample_input, params)
        exec_ms = (time.perf_counter() - start_t) * 1000.0
        if not isinstance(result, dict):
            raise ModelContractValidationError(f"Model output must be a dictionary; got {type(result).__name__}")
        return {
            "model_id": self.metadata.model_id,
            "version": self.metadata.version,
            "execution_time_ms": exec_ms,
            "result": result,
            "status": "VALIDATED",
        }


class RiskModel(BaseModel):
    """Abstract contract for custom quantitative risk models."""

    def __init__(
        self,
        model_id: str,
        name: str,
        version: str = "1.0.0",
        author: str = "quant_researcher",
        description: str = "",
        capabilities: Optional[Sequence[str]] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            name=name,
            category=ModelCategory.RISK_ESTIMATION,
            version=version,
            author=author,
            description=description,
            capabilities=capabilities,
            supported_labs=["risk", "scenarios", "model_validation", "tournament", "dashboards"],
            parameters=parameters,
        )

    def declare_capabilities(self) -> Sequence[str]:
        return ("var_95", "expected_shortfall_95", "annualized_volatility", "risk_metric")

    def declare_supported_labs(self) -> Sequence[str]:
        return ("risk", "scenarios", "model_validation", "tournament", "dashboards")

    def validate_input(self, input_data: Any) -> None:
        if isinstance(input_data, dict) and "returns" in input_data:
            series = input_data["returns"]
        elif isinstance(input_data, (list, tuple)):
            series = input_data
        else:
            raise ModelContractValidationError("RiskModel expects a list/tuple of returns or a dict with 'returns'.")
        if len(series) < 5:
            raise ModelContractValidationError(f"RiskModel requires at least 5 return observations; got {len(series)}")
        for x in series:
            if not isinstance(x, (int, float)) or not math.isfinite(x):
                raise ModelContractValidationError(f"Return observation must be a finite float; got {x!r}")

    @abc.abstractmethod
    def calculate_risk(self, returns: Sequence[float], parameters: Dict[str, Any]) -> RiskMetricsOutput:
        """User calculation method computing risk metrics."""
        pass

    def execute(self, input_data: Any, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = self.resolve_parameters(parameters)
        if isinstance(input_data, dict) and "returns" in input_data:
            rets = [float(x) for x in input_data["returns"]]
        else:
            rets = [float(x) for x in input_data]
        res = self.calculate_risk(rets, params)
        if not isinstance(res, RiskMetricsOutput):
            raise ModelContractValidationError(f"calculate_risk must return RiskMetricsOutput; got {type(res).__name__}")
        return res.to_dict()


class ForecastingModel(BaseModel):
    """Abstract contract for custom return and price forecasting models."""

    def __init__(
        self,
        model_id: str,
        name: str,
        version: str = "1.0.0",
        author: str = "quant_researcher",
        description: str = "",
        capabilities: Optional[Sequence[str]] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            name=name,
            category=ModelCategory.FORECASTING,
            version=version,
            author=author,
            description=description,
            capabilities=capabilities,
            supported_labs=["forecasting", "robustness", "tournament", "dashboards"],
            parameters=parameters,
        )

    def declare_capabilities(self) -> Sequence[str]:
        return ("point_forecast", "interval_forecast", "return_prediction")

    def declare_supported_labs(self) -> Sequence[str]:
        return ("forecasting", "robustness", "tournament", "dashboards")

    def validate_input(self, input_data: Any) -> None:
        if isinstance(input_data, dict) and "series" in input_data:
            series = input_data["series"]
        elif isinstance(input_data, (list, tuple)):
            series = input_data
        else:
            raise ModelContractValidationError("ForecastingModel expects a sequence of floats or dict with 'series'.")
        if len(series) < 10:
            raise ModelContractValidationError(f"Forecasting requires at least 10 observations; got {len(series)}")
        for x in series:
            if not isinstance(x, (int, float)) or not math.isfinite(x):
                raise ModelContractValidationError(f"Observation must be finite; got {x!r}")

    @abc.abstractmethod
    def generate_forecast(self, series: Sequence[float], horizon: int, parameters: Dict[str, Any]) -> ForecastOutput:
        """User forecasting method."""
        pass

    def execute(self, input_data: Any, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = self.resolve_parameters(parameters)
        horizon = int(params.get("horizon", 5))
        if isinstance(input_data, dict) and "series" in input_data:
            series = [float(x) for x in input_data["series"]]
            if "horizon" in input_data:
                horizon = int(input_data["horizon"])
        else:
            series = [float(x) for x in input_data]
        res = self.generate_forecast(series, horizon, params)
        if not isinstance(res, ForecastOutput):
            raise ModelContractValidationError(f"generate_forecast must return ForecastOutput; got {type(res).__name__}")
        return res.to_dict()


class CustomMetric(BaseModel):
    """Abstract contract for calculating custom financial risk, performance, or concentration metrics."""

    def __init__(
        self,
        model_id: str,
        name: str,
        version: str = "1.0.0",
        author: str = "quant_researcher",
        description: str = "",
        capabilities: Optional[Sequence[str]] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            name=name,
            category=ModelCategory.CUSTOM_METRIC,
            version=version,
            author=author,
            description=description,
            capabilities=capabilities,
            supported_labs=["risk", "dashboards", "reports"],
            parameters=parameters,
        )

    def declare_capabilities(self) -> Sequence[str]:
        return ("custom_metric", "portfolio_metric")

    def declare_supported_labs(self) -> Sequence[str]:
        return ("risk", "dashboards", "reports")

    def validate_input(self, input_data: Any) -> None:
        if not input_data:
            raise ModelContractValidationError("CustomMetric input data cannot be empty.")

    @abc.abstractmethod
    def evaluate_metric(self, data: Any, parameters: Dict[str, Any]) -> MetricOutput:
        """Compute the custom metric."""
        pass

    def execute(self, input_data: Any, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = self.resolve_parameters(parameters)
        res = self.evaluate_metric(input_data, params)
        if not isinstance(res, MetricOutput):
            raise ModelContractValidationError(f"evaluate_metric must return MetricOutput; got {type(res).__name__}")
        return res.to_dict()


class SimulationEngine(BaseModel):
    """Abstract contract for custom Monte Carlo path generators."""

    def __init__(
        self,
        model_id: str,
        name: str,
        version: str = "1.0.0",
        author: str = "quant_researcher",
        description: str = "",
        capabilities: Optional[Sequence[str]] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            name=name,
            category=ModelCategory.SIMULATION,
            version=version,
            author=author,
            description=description,
            capabilities=capabilities,
            supported_labs=["monte_carlo", "dashboards"],
            parameters=parameters,
        )

    def declare_capabilities(self) -> Sequence[str]:
        return ("monte_carlo_paths", "terminal_wealth_distribution", "simulation")

    def declare_supported_labs(self) -> Sequence[str]:
        return ("monte_carlo", "dashboards")

    def validate_input(self, input_data: Any) -> None:
        if isinstance(input_data, dict):
            init_val = input_data.get("initial_value", 100.0)
            if not isinstance(init_val, (int, float)) or init_val <= 0.0:
                raise ModelContractValidationError(f"initial_value must be strictly positive; got {init_val}")

    @abc.abstractmethod
    def generate_paths(self, initial_value: float, steps: int, paths: int, parameters: Dict[str, Any]) -> SimulationOutput:
        """Simulate asset paths."""
        pass

    def execute(self, input_data: Any, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = self.resolve_parameters(parameters)
        init_val = 1000000.0
        steps = int(params.get("steps", 30))
        paths = int(params.get("paths", 500))
        if isinstance(input_data, dict):
            init_val = float(input_data.get("initial_value", init_val))
            if "steps" in input_data:
                steps = int(input_data["steps"])
            if "paths" in input_data:
                paths = int(input_data["paths"])
        res = self.generate_paths(init_val, steps, paths, params)
        if not isinstance(res, SimulationOutput):
            raise ModelContractValidationError(f"generate_paths must return SimulationOutput; got {type(res).__name__}")
        return res.to_dict()


class TradingStrategy(BaseModel):
    """Abstract contract for custom algorithmic trading strategies."""

    def __init__(
        self,
        model_id: str,
        name: str,
        version: str = "1.0.0",
        author: str = "quant_researcher",
        description: str = "",
        capabilities: Optional[Sequence[str]] = None,
        parameters: Optional[Sequence[ParameterDefinition]] = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            name=name,
            category=ModelCategory.TRADING_STRATEGY,
            version=version,
            author=author,
            description=description,
            capabilities=capabilities,
            supported_labs=["strategies", "backtest", "dashboards"],
            parameters=parameters,
        )

    def declare_capabilities(self) -> Sequence[str]:
        return ("signal_generation", "portfolio_rebalancing", "strategy_backtest")

    def declare_supported_labs(self) -> Sequence[str]:
        return ("strategies", "backtest", "dashboards")

    def validate_input(self, input_data: Any) -> None:
        if not isinstance(input_data, dict):
            raise ModelContractValidationError("TradingStrategy input must be a dictionary of asset prices/returns.")

    @abc.abstractmethod
    def generate_signals(self, market_data: Dict[str, Any], parameters: Dict[str, Any]) -> StrategySignalsOutput:
        """Compute trading signals and portfolio target weights."""
        pass

    def execute(self, input_data: Any, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        params = self.resolve_parameters(parameters)
        res = self.generate_signals(input_data, params)
        if not isinstance(res, StrategySignalsOutput):
            raise ModelContractValidationError(f"generate_signals must return StrategySignalsOutput; got {type(res).__name__}")
        return res.to_dict()
