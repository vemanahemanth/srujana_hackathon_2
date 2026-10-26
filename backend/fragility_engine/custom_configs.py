"""FragilityShield — Configuration-Driven Customizable Strategies, Scenarios & Test Profiles.

Enables researchers and quants to customize strategies, macro shocks, and evaluation suites
via declarative JSON configurations with strict type validation, parameter boundaries, and
reproducibility hashing.

Safety Guarantee:
- Zero `eval()`, `exec()`, or dynamic code compilation.
- Declarative rule evaluation engine.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fragility_engine.reproducibility import canonical_json_dumps

logger = logging.getLogger("fragility_engine.custom_configs")


class ConfigValidationError(Exception):
    """Raised when declarative configuration fails structural or range validation."""
    pass


# ==============================================================================
# 1. Customizable Strategy Configuration
# ==============================================================================

@dataclass
class ParameterSpec:
    name: str
    param_type: str  # "float", "int", "bool", "str"
    default_value: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None
    description: str = ""

    def validate(self, value: Any) -> Any:
        if self.param_type == "int":
            try:
                v = int(value)
            except (ValueError, TypeError):
                raise ConfigValidationError(f"Parameter '{self.name}' must be an integer, got {value}.")
            if self.min_value is not None and v < self.min_value:
                raise ConfigValidationError(f"Parameter '{self.name}' ({v}) below minimum {self.min_value}.")
            if self.max_value is not None and v > self.max_value:
                raise ConfigValidationError(f"Parameter '{self.name}' ({v}) above maximum {self.max_value}.")
            return v
        elif self.param_type == "float":
            try:
                v = float(value)
            except (ValueError, TypeError):
                raise ConfigValidationError(f"Parameter '{self.name}' must be a float, got {value}.")
            if self.min_value is not None and v < self.min_value:
                raise ConfigValidationError(f"Parameter '{self.name}' ({v}) below minimum {self.min_value}.")
            if self.max_value is not None and v > self.max_value:
                raise ConfigValidationError(f"Parameter '{self.name}' ({v}) above maximum {self.max_value}.")
            return v
        elif self.param_type == "bool":
            return bool(value)
        elif self.param_type == "str":
            v = str(value)
            if self.options and v not in self.options:
                raise ConfigValidationError(f"Parameter '{self.name}' value '{v}' must be one of {self.options}.")
            return v
        return value


@dataclass
class CustomStrategyConfig:
    strategy_id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "researcher"
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cost_model: Dict[str, float] = field(default_factory=lambda: {"fee_bps": 5.0, "slippage_bps": 2.5})
    position_sizing: Dict[str, Any] = field(default_factory=lambda: {"method": "fixed_pct", "value": 0.10, "max_leverage": 1.0})
    risk_limits: Dict[str, float] = field(default_factory=lambda: {"stop_loss_pct": 3.0, "max_drawdown_limit": 15.0})
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("created_at", None)
        return hashlib.sha256(canonical_json_dumps(d).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["config_hash"] = self.compute_hash()
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomStrategyConfig:
        sid = data.get("strategy_id") or data.get("id")
        if not sid or not data.get("name"):
            raise ConfigValidationError("Missing required fields 'strategy_id' and 'name'.")
        return cls(
            strategy_id=str(sid),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            version=str(data.get("version", "1.0.0")),
            author=str(data.get("author", "researcher")),
            parameters=data.get("parameters", {}),
            cost_model=data.get("cost_model", {"fee_bps": 5.0, "slippage_bps": 2.5}),
            position_sizing=data.get("position_sizing", {"method": "fixed_pct", "value": 0.10, "max_leverage": 1.0}),
            risk_limits=data.get("risk_limits", {"stop_loss_pct": 3.0, "max_drawdown_limit": 15.0}),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


# ==============================================================================
# 2. Customizable Scenario & Stress Configuration
# ==============================================================================

@dataclass
class CustomScenarioConfig:
    scenario_id: str
    name: str
    description: str
    shocks: Dict[str, float] = field(default_factory=dict)  # Symbol or Factor -> shock fraction (e.g. -0.20)
    liquidity_haircut_pct: float = 0.0
    correlation_multiplier: float = 1.0
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("created_at", None)
        return hashlib.sha256(canonical_json_dumps(d).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["config_hash"] = self.compute_hash()
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomScenarioConfig:
        if not data.get("scenario_id") or not data.get("name"):
            raise ConfigValidationError("Missing required fields 'scenario_id' and 'name'.")
        shocks = data.get("shocks", {})
        if not isinstance(shocks, dict):
            raise ConfigValidationError("'shocks' must be a dictionary of factor/symbol shocks.")
        for k, v in shocks.items():
            if not isinstance(v, (int, float)):
                raise ConfigValidationError(f"Shock for '{k}' must be a numeric value, got {v}.")

        return cls(
            scenario_id=str(data["scenario_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            shocks={str(k): float(v) for k, v in shocks.items()},
            liquidity_haircut_pct=float(data.get("liquidity_haircut_pct", 0.0)),
            correlation_multiplier=float(data.get("correlation_multiplier", 1.0)),
            version=str(data.get("version", "1.0.0")),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


# ==============================================================================
# 3. Customizable Test Profile Configuration
# ==============================================================================

@dataclass
class CustomTestProfileConfig:
    profile_id: str
    name: str
    description: str
    selected_modules: List[str]
    parameter_overrides: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        d = asdict(self)
        d.pop("created_at", None)
        return hashlib.sha256(canonical_json_dumps(d).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["config_hash"] = self.compute_hash()
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomTestProfileConfig:
        if not data.get("profile_id") or not data.get("name"):
            raise ConfigValidationError("Missing required fields 'profile_id' and 'name'.")
        modules = data.get("selected_modules", [])
        if not isinstance(modules, list) or len(modules) == 0:
            raise ConfigValidationError("'selected_modules' must be a non-empty list of test module IDs.")

        return cls(
            profile_id=str(data["profile_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            selected_modules=[str(m) for m in modules],
            parameter_overrides=data.get("parameter_overrides", {}),
            version=str(data.get("version", "1.0.0")),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


# ==============================================================================
# 4. In-Memory Registry for Custom Configs
# ==============================================================================

class ConfigurationRegistry:
    """Manages persistent custom strategy, scenario, and test profile definitions."""

    def __init__(self) -> None:
        self.strategies: Dict[str, CustomStrategyConfig] = {}
        self.scenarios: Dict[str, CustomScenarioConfig] = {}
        self.profiles: Dict[str, CustomTestProfileConfig] = {}
        self._seed_default_configs()

    def _seed_default_configs(self) -> None:
        # 1. Default Strategies
        self.strategies["strat_moving_average_crossover"] = CustomStrategyConfig(
            strategy_id="strat_moving_average_crossover",
            name="Dual Moving Average Trend Follower",
            description="Executes long/short positions on EMA 20 / EMA 50 signal cross with trailing stop-loss.",
            version="1.0.0",
            parameters={"fast_period": 20, "slow_period": 50, "risk_fraction": 0.05},
        )
        self.strategies["strat_mean_reversion_bollinger"] = CustomStrategyConfig(
            strategy_id="strat_mean_reversion_bollinger",
            name="Bollinger Band Mean Reversion",
            description="Mean reversion engine triggered on 2-sigma boundary breach with volume confirmation.",
            version="1.0.0",
            parameters={"window": 20, "std_devs": 2.0, "exit_at_mean": True},
        )

        # 2. Default Scenarios
        self.scenarios["sc_gfc_2008"] = CustomScenarioConfig(
            scenario_id="sc_gfc_2008",
            name="2008 Global Financial Crisis",
            description="Severe credit contraction and global equity index crash.",
            shocks={"EQUITY": -0.385, "FINANCIALS": -0.520, "VOLATILITY": +1.20},
            liquidity_haircut_pct=15.0,
        )
        self.scenarios["sc_covid_2020"] = CustomScenarioConfig(
            scenario_id="sc_covid_2020",
            name="2020 Pandemic Liquidity Shock",
            description="Rapid multi-asset liquidation and cross-asset correlation spike.",
            shocks={"EQUITY": -0.282, "CRUDE_OIL": -0.550, "VOLATILITY": +0.95},
            correlation_multiplier=1.4,
        )
        self.scenarios["sc_rates_inflation_shock"] = CustomScenarioConfig(
            scenario_id="sc_rates_inflation_shock",
            name="Aggressive Rate Hike & Currency Plunge",
            description="Central bank shock +300bps rate hike with currency devaluation.",
            shocks={"BONDS": -0.180, "TECH": -0.220, "CURRENCY": -0.085},
        )

        # 3. Default Profiles
        self.profiles["test_all"] = CustomTestProfileConfig(
            profile_id="test_all",
            name="Full Quantitative Laboratory Suite (Test All)",
            description="Executes all applicable test modules: Risk, Scenarios, EVT, Fragility, Monte Carlo, and Bootstrap.",
            selected_modules=[
                "data_diagnostics",
                "risk_analytics",
                "scenario_stress",
                "tail_risk_reverse_stress",
                "fragility_assumption_matrix",
                "monte_carlo_simulation",
                "bootstrap_uncertainty",
                "model_validation",
            ],
        )
        self.profiles["regulatory_basel_pack"] = CustomTestProfileConfig(
            profile_id="regulatory_basel_pack",
            name="Basel Regulatory Stress Pack",
            description="Focuses on Kupiec POF backtesting, 99% Expected Shortfall, and Extreme Value Theory.",
            selected_modules=["data_diagnostics", "risk_analytics", "model_validation", "tail_risk_reverse_stress"],
            parameter_overrides={"confidence_level": 0.99, "target_loss_boundary": 0.15},
        )
        self.profiles["quick_risk_screen"] = CustomTestProfileConfig(
            profile_id="quick_risk_screen",
            name="Rapid Model Screening",
            description="Fast sanity check: Historical VaR, CVaR, and Stationarity diagnostics.",
            selected_modules=["data_diagnostics", "risk_analytics"],
        )

    def save_strategy(self, config: CustomStrategyConfig) -> None:
        self.strategies[config.strategy_id] = config

    def get_strategy(self, strategy_id: str) -> Optional[CustomStrategyConfig]:
        return self.strategies.get(strategy_id)

    def list_strategies(self) -> List[CustomStrategyConfig]:
        return list(self.strategies.values())

    def save_scenario(self, config: CustomScenarioConfig) -> None:
        self.scenarios[config.scenario_id] = config

    def get_scenario(self, scenario_id: str) -> Optional[CustomScenarioConfig]:
        return self.scenarios.get(scenario_id)

    def list_scenarios(self) -> List[CustomScenarioConfig]:
        return list(self.scenarios.values())

    def save_profile(self, config: CustomTestProfileConfig) -> None:
        self.profiles[config.profile_id] = config

    def get_profile(self, profile_id: str) -> Optional[CustomTestProfileConfig]:
        return self.profiles.get(profile_id)

    def list_profiles(self) -> List[CustomTestProfileConfig]:
        return list(self.profiles.values())


# Global singleton
_CONFIG_REGISTRY_INSTANCE: Optional[ConfigurationRegistry] = None

def get_config_registry() -> ConfigurationRegistry:
    global _CONFIG_REGISTRY_INSTANCE
    if _CONFIG_REGISTRY_INSTANCE is None:
        _CONFIG_REGISTRY_INSTANCE = ConfigurationRegistry()
    return _CONFIG_REGISTRY_INSTANCE
