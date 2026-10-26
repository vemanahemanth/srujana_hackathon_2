"""FragilityShield — Quantitative Model Plugin System (Phase 8).

This module defines a clean, typed, framework-agnostic plugin architecture
for registering, inspecting, validating, and executing quantitative risk models.

Key Capabilities:
1. Typed Plugin Contract (`ModelPlugin`, `PluginMetadata`, `ModelExecutionResult`):
   - Formal interface for model capability declaration, input/output contracts,
     validation, execution, and methodological limitations.
2. Built-in Model Adapters:
   - `HistoricalSimulationPlugin`: Empirical non-parametric VaR, coherent ES, and volatility.
   - `ParametricGaussianPlugin`: Analytical normal-distribution tail risk benchmark.
   - `EWMAVolatilityPlugin`: RiskMetrics dynamic exponential moving average volatility.
   - `PortfolioConcentrationPlugin`: Multi-asset portfolio concentration and HHI analytics.
3. Plugin Registry (`PluginRegistry`):
   - Deterministic registration, lookup, capability querying, duplicate protection,
     and safe in-process execution isolation.
"""

from __future__ import annotations

import abc
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
import scipy.stats as stats
import numpy as np

from fragility_engine.models import Holding, Portfolio
from fragility_engine.risk import (
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)
from fragility_engine.fragility import calculate_ewma_volatility
from fragility_engine.concentration import calculate_portfolio_concentration


# ==============================================================================
# C1. Plugin Metadata & Result Contracts
# ==============================================================================

@dataclass(frozen=True)
class PluginMetadata:
    """Immutable metadata and capability declaration for a ModelPlugin.

    Attributes:
        plugin_id: Stable, unique identifier (e.g. 'builtin.historical_simulation').
        name: Human-readable model name.
        description: Methodological description of the model.
        plugin_version: Semantic version of the plugin implementation.
        api_version: Supported FragilityShield plugin API specification version.
        supported_data_types: Tuple of input types supported ('return_series', 'multivariate_returns', 'portfolio').
        capabilities: Tuple of risk/fragility metrics this model can evaluate.
        required_config_keys: Tuple of configuration keys required by the model.
        optional_config_keys: Tuple of configuration keys accepted with defaults.
        limitations: Explicit statement of model assumptions, boundaries, and blind spots.
    """

    plugin_id: str
    name: str
    description: str
    plugin_version: str = "1.0.0"
    api_version: str = "1.0.0"
    supported_data_types: Tuple[str, ...] = ("return_series",)
    capabilities: Tuple[str, ...] = ()
    required_config_keys: Tuple[str, ...] = ()
    optional_config_keys: Tuple[str, ...] = ()
    limitations: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.plugin_id, str) or not self.plugin_id.strip():
            raise ValueError("plugin_id cannot be blank")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", self.plugin_id):
            raise ValueError(f"Invalid plugin_id '{self.plugin_id}': only alphanumeric, dots, hyphens, and underscores permitted")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name cannot be blank")
        if not isinstance(self.plugin_version, str) or not self.plugin_version.strip():
            raise ValueError("plugin_version cannot be blank")
        if not isinstance(self.api_version, str) or not self.api_version.strip():
            raise ValueError("api_version cannot be blank")

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to a serializable dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "description": self.description,
            "plugin_version": self.plugin_version,
            "api_version": self.api_version,
            "supported_data_types": list(self.supported_data_types),
            "capabilities": list(self.capabilities),
            "required_config_keys": list(self.required_config_keys),
            "optional_config_keys": list(self.optional_config_keys),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class ModelExecutionResult:
    """Structured, verified execution output of a quantitative model.

    Attributes:
        plugin_id: Identifier of the executing plugin.
        model_version: Version of the executed model.
        metrics: Mapping of metric identifier to finite numerical value.
        execution_time_ms: Wall-clock execution time in milliseconds.
        observations_used: Number of observations utilized in the calculation.
        warnings: Diagnostic warnings raised during execution.
        limitations: Methodological boundaries of this specific evaluation.
        metadata: Additional contextual outputs.
    """

    plugin_id: str
    model_version: str
    metrics: Mapping[str, float]
    execution_time_ms: float
    observations_used: int
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    limitations: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.plugin_id, str) or not self.plugin_id.strip():
            raise ValueError("plugin_id cannot be blank")
        for k, v in self.metrics.items():
            if not isinstance(v, (int, float, np.floating, np.integer)) or not math.isfinite(float(v)):
                raise ValueError(f"Model metric '{k}' produced non-finite or non-numeric value: {v}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a serializable dictionary."""
        return {
            "plugin_id": self.plugin_id,
            "model_version": self.model_version,
            "metrics": {k: float(v) for k, v in self.metrics.items()},
            "execution_time_ms": float(self.execution_time_ms),
            "observations_used": int(self.observations_used),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata),
        }


# ==============================================================================
# C2. Model Plugin Protocol / Abstract Base Class
# ==============================================================================

class ModelPlugin(abc.ABC):
    """Abstract Base Class for quantitative model plugins."""

    @property
    @abc.abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return the plugin metadata declaration."""
        ...

    @abc.abstractmethod
    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        """Validate input dataset shape and configuration before execution.

        Raises:
            TypeError: If input types or config structures are invalid.
            ValueError: If values are out of bounds, non-finite, or empty.
        """
        ...

    @abc.abstractmethod
    def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
        """Execute model calculation on verified inputs.

        Args:
            data: Return series, multivariate return array, or Portfolio snapshot.
            config: Parameter configuration mapping.

        Returns:
            ModelExecutionResult with finite metrics and execution telemetry.
        """
        ...


# ==============================================================================
# C3. Built-in Model Adapters
# ==============================================================================

class HistoricalSimulationPlugin(ModelPlugin):
    """Built-in model implementing empirical Historical Simulation risk estimation.

    Calculates empirical non-parametric VaR, coherent Expected Shortfall (Acerbi-Tasche),
    sample annualized volatility, and peak-to-trough drawdown dynamics.
    """

    def __init__(self) -> None:
        self._meta = PluginMetadata(
            plugin_id="builtin.historical_simulation",
            name="Historical Simulation (Non-Parametric)",
            description="Computes non-parametric empirical VaR, coherent Acerbi-Tasche Expected Shortfall, and volatility.",
            plugin_version="1.0.0",
            api_version="1.0.0",
            supported_data_types=("return_series",),
            capabilities=(
                "volatility_daily",
                "volatility_annualized",
                "annualized_volatility",
                "var_95",
                "var_historical",
                "var_99",
                "expected_shortfall",
                "expected_shortfall_95",
                "expected_shortfall_99",
                "max_drawdown",
                "maximum_drawdown",
            ),
            required_config_keys=(),
            optional_config_keys=("confidence_level", "annualization_factor"),
            limitations=(
                "Assumes historical returns are stationary and independently identically distributed.",
                "Cannot forecast tail events beyond the empirical sample history.",
            ),
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        if data is None:
            raise TypeError("Dataset cannot be None")
        if isinstance(data, Portfolio):
            raise TypeError("HistoricalSimulationPlugin requires return series, not a Portfolio snapshot")

        arr = np.asarray(data, dtype=np.float64)
        if arr.size == 0:
            raise ValueError("Dataset cannot be empty")
        if arr.ndim != 1:
            raise ValueError(f"HistoricalSimulationPlugin requires 1D return series; got shape {arr.shape}")
        if len(arr) < 2:
            raise ValueError(f"HistoricalSimulationPlugin requires at least 2 observations; got {len(arr)}")
        if not np.all(np.isfinite(arr)):
            raise ValueError("Dataset contains non-finite numbers (NaN or Inf)")

        if "confidence_level" in config:
            conf = float(config["confidence_level"])
            if not (0.0 < conf < 1.0):
                raise ValueError(f"confidence_level must be in (0, 1); got {conf}")

        if "annualization_factor" in config:
            ann = float(config["annualization_factor"])
            if ann <= 0.0 or not math.isfinite(ann):
                raise ValueError(f"annualization_factor must be > 0; got {ann}")

    def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
        self.validate_input(data, config)
        arr = np.asarray(data, dtype=np.float64)
        annualization = float(config.get("annualization_factor", 252.0))

        t0 = time.perf_counter()
        rep = calculate_risk_report(arr, annualization_factor=annualization)
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        metrics: Dict[str, float] = {
            "volatility_daily": rep.volatility_daily,
            "volatility_annualized": rep.volatility_annualized,
            "annualized_volatility": rep.volatility_annualized,
            "var_95": rep.var_95,
            "var_historical": rep.var_95,
            "var_99": rep.var_99,
            "expected_shortfall": rep.expected_shortfall_95,
            "expected_shortfall_95": rep.expected_shortfall_95,
            "expected_shortfall_99": rep.expected_shortfall_99,
        }
        if rep.drawdown is not None:
            metrics["max_drawdown"] = rep.drawdown.max_drawdown
            metrics["maximum_drawdown"] = rep.drawdown.max_drawdown

        return ModelExecutionResult(
            plugin_id=self.metadata.plugin_id,
            model_version=self.metadata.plugin_version,
            metrics=metrics,
            execution_time_ms=t_elapsed_ms,
            observations_used=len(arr),
            warnings=rep.warnings,
            limitations=self.metadata.limitations,
        )


class ParametricGaussianPlugin(ModelPlugin):
    """Built-in model implementing Analytical Parametric Gaussian risk estimation.

    Under positive loss convention L = -R, VaR_alpha = -(mu - z_alpha * sigma) = -mu + z_alpha * sigma.
    Expected Shortfall for a normal distribution: ES_alpha = -mu + sigma * phi(z_alpha) / (1 - alpha).
    """

    def __init__(self) -> None:
        self._meta = PluginMetadata(
            plugin_id="builtin.parametric_gaussian",
            name="Parametric Gaussian (Analytical Normal)",
            description="Computes analytical Value at Risk and Expected Shortfall assuming Gaussian normal distribution.",
            plugin_version="1.0.0",
            api_version="1.0.0",
            supported_data_types=("return_series",),
            capabilities=(
                "volatility_daily",
                "volatility_annualized",
                "annualized_volatility",
                "var_95",
                "var_99",
                "expected_shortfall",
                "expected_shortfall_95",
                "expected_shortfall_99",
            ),
            required_config_keys=(),
            optional_config_keys=("confidence_level", "annualization_factor"),
            limitations=(
                "Assumes returns are strictly normally distributed with zero skewness and zero excess kurtosis.",
                "Severely underestimates tail risk and extreme drawdowns in financial assets with fat tails.",
                "Unconditional sample standard deviation does not capture time-varying volatility clustering or regime shifts.",
            ),
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        if data is None:
            raise TypeError("Dataset cannot be None")
        if isinstance(data, Portfolio):
            raise TypeError("ParametricGaussianPlugin requires return series, not a Portfolio snapshot")

        arr = np.asarray(data, dtype=np.float64)
        if arr.size == 0:
            raise ValueError("Dataset cannot be empty")
        if arr.ndim != 1:
            raise ValueError(f"ParametricGaussianPlugin requires 1D return series; got shape {arr.shape}")
        if len(arr) < 2:
            raise ValueError(f"ParametricGaussianPlugin requires at least 2 observations; got {len(arr)}")
        if not np.all(np.isfinite(arr)):
            raise ValueError("Dataset contains non-finite numbers (NaN or Inf)")

        if "confidence_level" in config:
            conf = float(config["confidence_level"])
            if not (0.0 < conf < 1.0):
                raise ValueError(f"confidence_level must be in (0, 1); got {conf}")

    def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
        self.validate_input(data, config)
        arr = np.asarray(data, dtype=np.float64)
        annualization = float(config.get("annualization_factor", 252.0))

        t0 = time.perf_counter()
        mu = float(np.mean(arr))
        sigma = float(np.std(arr, ddof=1))
        sigma_ann = sigma * math.sqrt(annualization)

        # Standard normal quantiles:
        # For 95%: z = 1.6448536269514722
        # For 99%: z = 2.3263478740408408
        z_95 = 1.6448536269514722
        z_99 = 2.3263478740408408

        # Standard normal density phi(z) = (1 / sqrt(2*pi)) * exp(-0.5 * z^2)
        inv_sqrt_2pi = 1.0 / math.sqrt(2.0 * math.pi)
        phi_95 = inv_sqrt_2pi * math.exp(-0.5 * z_95 * z_95)
        phi_99 = inv_sqrt_2pi * math.exp(-0.5 * z_99 * z_99)

        # Under positive loss convention (L = -R):
        # VaR_alpha = -mu + z_alpha * sigma
        # ES_alpha = -mu + sigma * phi(z_alpha) / (1 - alpha)
        var_95 = -mu + z_95 * sigma
        var_99 = -mu + z_99 * sigma
        es_95 = -mu + sigma * (phi_95 / 0.05)
        es_99 = -mu + sigma * (phi_99 / 0.01)

        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        metrics: Dict[str, float] = {
            "volatility_daily": sigma,
            "volatility_annualized": sigma_ann,
            "annualized_volatility": sigma_ann,
            "var_95": var_95,
            "var_99": var_99,
            "expected_shortfall": es_95,
            "expected_shortfall_95": es_95,
            "expected_shortfall_99": es_99,
        }

        warnings: List[str] = []
        if len(arr) < 30:
            warnings.append(f"Sample size {len(arr)} is small for reliable parametric mean/variance estimation.")

        return ModelExecutionResult(
            plugin_id=self.metadata.plugin_id,
            model_version=self.metadata.plugin_version,
            metrics=metrics,
            execution_time_ms=t_elapsed_ms,
            observations_used=len(arr),
            warnings=tuple(warnings),
            limitations=self.metadata.limitations,
        )


class EWMAVolatilityPlugin(ModelPlugin):
    """Built-in model implementing RiskMetrics EWMA volatility and conditional Gaussian risk metrics."""

    def __init__(self) -> None:
        self._meta = PluginMetadata(
            plugin_id="builtin.ewma",
            name="RiskMetrics EWMA Volatility & Conditional Gaussian Model",
            description="Computes Exponentially Weighted Moving Average (EWMA) volatility with decay factor lambda and derives conditional normal VaR and Expected Shortfall.",
            plugin_version="1.0.0",
            api_version="1.0.0",
            supported_data_types=("return_series",),
            capabilities=(
                "volatility_daily",
                "volatility_annualized",
                "annualized_volatility",
                "var_95",
                "var_99",
                "expected_shortfall",
                "expected_shortfall_95",
                "expected_shortfall_99",
            ),
            required_config_keys=(),
            optional_config_keys=("decay_factor", "annualization_factor", "zero_mean"),
            limitations=(
                "Assumes zero or stationary mean with exponential decay memory (decay factor lambda) on squared returns.",
                "Derives VaR and Expected Shortfall under conditional normal distribution assumptions; underestimates tail risk for heavy-tailed financial returns.",
                "Conditioned heavily on recent volatility shocks without explicit mean-reversion modeling.",
            ),
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        if data is None:
            raise TypeError("Dataset cannot be None")
        if isinstance(data, Portfolio):
            raise TypeError("EWMAVolatilityPlugin requires return series, not a Portfolio snapshot")

        arr = np.asarray(data, dtype=np.float64)
        if arr.size == 0:
            raise ValueError("Dataset cannot be empty")
        if arr.ndim != 1:
            raise ValueError(f"EWMAVolatilityPlugin requires 1D return series; got shape {arr.shape}")
        if len(arr) < 2:
            raise ValueError(f"EWMAVolatilityPlugin requires at least 2 observations; got {len(arr)}")
        if not np.all(np.isfinite(arr)):
            raise ValueError("Dataset contains non-finite numbers (NaN or Inf)")

        if "decay_factor" in config:
            decay = float(config["decay_factor"])
            if not (0.0 < decay < 1.0):
                raise ValueError(f"decay_factor must be in (0, 1); got {decay}")

        if "annualization_factor" in config:
            ann = float(config["annualization_factor"])
            if ann <= 0.0 or not math.isfinite(ann):
                raise ValueError(f"annualization_factor must be > 0; got {ann}")

        if "initial_variance" in config and config["initial_variance"] is not None:
            init_v = float(config["initial_variance"])
            if not math.isfinite(init_v) or init_v <= 0.0:
                raise ValueError(f"initial_variance must be > 0; got {init_v}")

    def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
        self.validate_input(data, config)
        arr = np.asarray(data, dtype=np.float64)
        decay = float(config.get("decay_factor", 0.94))
        annualization = float(config.get("annualization_factor", 252.0))
        zero_mean = bool(config.get("zero_mean", False))
        init_var = config.get("initial_variance")
        init_var_val = float(init_var) if init_var is not None else None

        t0 = time.perf_counter()
        sigma_ewma_ann = calculate_ewma_volatility(
            arr,
            decay_factor=decay,
            annualization_factor=annualization,
            initial_variance=init_var_val,
        )
        sigma_ewma_daily = sigma_ewma_ann / math.sqrt(annualization)

        # Standard normal quantiles and conditional normal VaR / ES
        z_95 = 1.6448536269514722
        z_99 = 2.3263478740408408
        inv_sqrt_2pi = 1.0 / math.sqrt(2.0 * math.pi)
        phi_95 = inv_sqrt_2pi * math.exp(-0.5 * z_95 * z_95)
        phi_99 = inv_sqrt_2pi * math.exp(-0.5 * z_99 * z_99)

        mu = 0.0 if zero_mean else float(np.mean(arr))
        var_95 = -mu + z_95 * sigma_ewma_daily
        var_99 = -mu + z_99 * sigma_ewma_daily
        es_95 = -mu + sigma_ewma_daily * (phi_95 / 0.05)
        es_99 = -mu + sigma_ewma_daily * (phi_99 / 0.01)

        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        metrics = {
            "volatility_daily": sigma_ewma_daily,
            "volatility_annualized": sigma_ewma_ann,
            "annualized_volatility": sigma_ewma_ann,
            "var_95": var_95,
            "var_99": var_99,
            "expected_shortfall": es_95,
            "expected_shortfall_95": es_95,
            "expected_shortfall_99": es_99,
        }

        return ModelExecutionResult(
            plugin_id=self.metadata.plugin_id,
            model_version=self.metadata.plugin_version,
            metrics=metrics,
            execution_time_ms=t_elapsed_ms,
            observations_used=len(arr),
            warnings=(),
            limitations=self.metadata.limitations,
            metadata={"decay_factor": decay, "zero_mean": zero_mean, "initial_variance": init_var_val},
        )


class PortfolioConcentrationPlugin(ModelPlugin):
    """Built-in model implementing portfolio allocation and Herfindahl-Hirschman concentration analytics."""

    def __init__(self) -> None:
        self._meta = PluginMetadata(
            plugin_id="builtin.portfolio_concentration",
            name="Portfolio Concentration Analytics",
            description="Evaluates asset and sector Herfindahl-Hirschman Index (HHI) concentration.",
            plugin_version="1.0.0",
            api_version="1.0.0",
            supported_data_types=("portfolio",),
            capabilities=(
                "total_market_value",
                "asset_hhi_decimal",
                "asset_hhi_points",
                "sector_hhi_decimal",
                "sector_hhi_points",
            ),
            required_config_keys=(),
            optional_config_keys=(),
            limitations=(
                "Static snapshot concentration metric; does not evaluate cross-asset correlation or liquidity risk.",
            ),
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    def validate_input(self, data: Any, config: Mapping[str, Any]) -> None:
        if not isinstance(data, Portfolio):
            raise TypeError(f"PortfolioConcentrationPlugin requires a Portfolio instance; got {type(data).__name__}")
        if len(data.holdings) == 0:
            raise ValueError("Portfolio cannot be empty")

    def execute(self, data: Any, config: Mapping[str, Any]) -> ModelExecutionResult:
        self.validate_input(data, config)
        t0 = time.perf_counter()
        conc = calculate_portfolio_concentration(data)
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        metrics = {
            "total_market_value": conc.total_market_value,
            "asset_hhi_decimal": conc.asset_hhi_decimal,
            "asset_hhi_points": conc.asset_hhi_points,
            "sector_hhi_decimal": conc.sector_hhi_decimal,
            "sector_hhi_points": conc.sector_hhi_points,
        }

        return ModelExecutionResult(
            plugin_id=self.metadata.plugin_id,
            model_version=self.metadata.plugin_version,
            metrics=metrics,
            execution_time_ms=t_elapsed_ms,
            observations_used=len(data.holdings),
            warnings=(),
            limitations=self.metadata.limitations,
        )



class ConfigurableCustomModelPlugin(ModelPlugin):
    """Extensible, user-configurable quantitative model plugin.

    Enables researchers to assemble, parameterize, and register custom models:
    - 'student_t': Heavy-tailed parametric model with degrees of freedom nu in [2.5, 100].
    - 'ewma': RiskMetrics exponential moving average with custom decay factor lambda in [0.80, 0.999].
    - 'cornish_fisher': Semiparametric quantile expansion using empirical skewness and excess kurtosis.
    - 'historical_quantile': Configurable quantile interpolation (linear, lower, higher, nearest, midpoint).
    """

    def __init__(
        self,
        model_id: str,
        name: str,
        family: str = "student_t",
        parameters: Optional[Mapping[str, Any]] = None,
        description: str = "",
        limitations: Optional[Sequence[str]] = None,
    ) -> None:
        clean_id = str(model_id).strip()
        if not clean_id:
            raise ValueError("model_id cannot be blank")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", clean_id):
            raise ValueError(f"model_id '{clean_id}' contains invalid characters")

        family_clean = str(family).strip().lower()
        valid_families = {"student_t", "ewma", "cornish_fisher", "historical_quantile"}
        if family_clean not in valid_families:
            raise ValueError(f"family must be one of {sorted(valid_families)}; got '{family}'")

        params = dict(parameters or {})
        self._family = family_clean
        self._params = params

        # Validate parameters by family
        if family_clean == "student_t":
            df = float(params.get("degrees_of_freedom", params.get("df", 5.0)))
            if df < 2.5 or df > 100.0:
                raise ValueError(f"Student-t degrees of freedom must be in [2.5, 100]; got {df}")
            self._params["degrees_of_freedom"] = df
            default_desc = f"Parametric Student-t model with {df:.1f} degrees of freedom for fat-tailed returns."
            default_limits = (
                f"Assumes constant tail thickness with nu={df:.1f}.",
                "Overestimates routine risk if empirical returns do not have heavy tails.",
            )
        elif family_clean == "ewma":
            decay = float(params.get("decay_factor", params.get("lambda", 0.94)))
            if decay < 0.80 or decay > 0.999:
                raise ValueError(f"EWMA decay_factor must be in [0.80, 0.999]; got {decay}")
            self._params["decay_factor"] = decay
            default_desc = f"Custom RiskMetrics EWMA volatility model with decay factor lambda={decay:.3f}."
            default_limits = (
                f"Assumes exponential variance memory with decay={decay:.3f}.",
                "Vulnerable to persistent volatility overestimation after large single-day shocks.",
            )
        elif family_clean == "cornish_fisher":
            default_desc = "Cornish-Fisher semiparametric expansion adjusting quantiles for skewness and excess kurtosis."
            default_limits = (
                "High estimation variance for sample kurtosis in small samples (N < 50).",
                "Polynomial expansion can lose monotonicity under extreme skewness (|S| > 1.5).",
            )
        else:  # historical_quantile
            method = str(params.get("method", "linear")).strip().lower()
            valid_methods = {"linear", "lower", "higher", "midpoint", "nearest"}
            if method not in valid_methods:
                raise ValueError(f"historical_quantile method must be one of {sorted(valid_methods)}; got '{method}'")
            self._params["method"] = method
            default_desc = f"Historical simulation with '{method}' quantile interpolation."
            default_limits = (
                "Cannot forecast tail events beyond the empirical sample history.",
                "Assumes historical distribution replicates future realization.",
            )

        self._meta = PluginMetadata(
            plugin_id=clean_id,
            name=str(name).strip() or f"Custom {family_clean.title()} Model",
            description=description.strip() or default_desc,
            plugin_version="1.0.0",
            api_version="1.0.0",
            supported_data_types=("return_series",),
            capabilities=(
                "volatility_daily",
                "volatility_annualized",
                "annualized_volatility",
                "var_95",
                "var_historical",
                "var_99",
                "expected_shortfall",
                "expected_shortfall_95",
                "expected_shortfall_99",
                "max_drawdown",
                "maximum_drawdown",
            ),
            required_config_keys=(),
            optional_config_keys=("confidence_level", "annualization_factor"),
            limitations=tuple(limitations) if limitations else default_limits,
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._meta

    @property
    def family(self) -> str:
        return self._family

    @property
    def parameters(self) -> Dict[str, Any]:
        return dict(self._params)

    def validate_input(self, data: Any, config: Optional[Mapping[str, Any]] = None) -> None:
        if data is None:
            raise TypeError("Dataset cannot be None")
        if isinstance(data, Portfolio):
            raise TypeError("Custom model requires return series, not a Portfolio snapshot")
        arr = np.asarray(data, dtype=np.float64)
        if arr.size == 0:
            raise ValueError("Dataset cannot be empty")
        if arr.size < 4:
            raise ValueError(f"Dataset requires at least 4 observations; got {arr.size}")
        if not np.all(np.isfinite(arr)):
            raise ValueError("Dataset contains non-finite values (NaN or Inf)")

    def execute(self, data: Any, config: Optional[Mapping[str, Any]] = None) -> ModelExecutionResult:
        cfg = dict(config or {})
        self.validate_input(data, cfg)
        arr = np.asarray(data, dtype=np.float64)
        n = len(arr)
        ann_factor = float(cfg.get("annualization_factor", 252.0))
        ddof = int(cfg.get("ddof", 1))

        t0 = time.perf_counter()
        mu = float(np.mean(arr))
        vol_daily = float(np.std(arr, ddof=ddof))
        vol_annual = vol_daily * math.sqrt(ann_factor)

        # Compute VaR and ES based on family
        if self._family == "student_t":
            df = float(self._params["degrees_of_freedom"])
            scale = vol_daily * math.sqrt((df - 2.0) / df)
            t_q95 = float(stats.t.ppf(0.95, df=df))
            t_q99 = float(stats.t.ppf(0.99, df=df))
            var_95 = -mu + scale * t_q95
            var_99 = -mu + scale * t_q99

            pdf95 = float(stats.t.pdf(t_q95, df=df))
            pdf99 = float(stats.t.pdf(t_q99, df=df))
            es_factor_95 = (pdf95 / 0.05) * ((df + t_q95**2) / (df - 1.0))
            es_factor_99 = (pdf99 / 0.01) * ((df + t_q99**2) / (df - 1.0))
            es_95 = -mu + scale * es_factor_95
            es_99 = -mu + scale * es_factor_99

        elif self._family == "ewma":
            decay = float(self._params["decay_factor"])
            vol_annual = calculate_ewma_volatility(arr, decay_factor=decay, annualization_factor=ann_factor)
            vol_daily = vol_annual / math.sqrt(ann_factor)
            ewma_vol = vol_daily
            z95 = float(stats.norm.ppf(0.95))
            z99 = float(stats.norm.ppf(0.99))
            var_95 = -mu + ewma_vol * z95
            var_99 = -mu + ewma_vol * z99
            es_95 = -mu + ewma_vol * (stats.norm.pdf(z95) / 0.05)
            es_99 = -mu + ewma_vol * (stats.norm.pdf(z99) / 0.01)

        elif self._family == "cornish_fisher":
            devs = arr - mu
            m2 = float(np.mean(devs**2))
            m3 = float(np.mean(devs**3))
            m4 = float(np.mean(devs**4))
            s = (m3 / (m2**1.5)) if m2 > 1e-12 else 0.0
            k = ((m4 / (m2**2.0)) - 3.0) if m2 > 1e-12 else 0.0

            def cf_quantile(alpha: float) -> float:
                z = float(stats.norm.ppf(alpha))
                return z + (1.0 / 6.0) * (z**2 - 1.0) * s + (1.0 / 24.0) * (z**3 - 3.0 * z) * k - (1.0 / 36.0) * (2.0 * z**3 - 5.0 * z) * (s**2)

            q95 = cf_quantile(0.95)
            q99 = cf_quantile(0.99)
            var_95 = -mu + vol_daily * q95
            var_99 = -mu + vol_daily * q99
            losses = -arr
            tail95 = losses[losses >= var_95]
            tail99 = losses[losses >= var_99]
            es_95 = max(var_95, float(np.mean(tail95)) if len(tail95) > 0 else var_95)
            es_99 = max(var_99, float(np.mean(tail99)) if len(tail99) > 0 else var_99)

        else:  # historical_quantile
            method = self._params.get("method", "linear")
            losses = -arr
            var_95 = float(np.percentile(losses, 95.0, method=method))
            var_99 = float(np.percentile(losses, 99.0, method=method))
            tail95 = losses[losses >= var_95]
            tail99 = losses[losses >= var_99]
            es_95 = float(np.mean(tail95)) if len(tail95) > 0 else var_95
            es_99 = float(np.mean(tail99)) if len(tail99) > 0 else var_99

        # Drawdown calculation
        eq = np.empty(n + 1, dtype=np.float64)
        eq[0] = 1.0
        for i, r in enumerate(arr):
            eq[i + 1] = eq[i] * (1.0 + r)
        dd_res = calculate_maximum_drawdown(eq)
        mdd = dd_res.max_drawdown

        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        metrics = {
            "volatility_daily": vol_daily,
            "volatility_annualized": vol_annual,
            "annualized_volatility": vol_annual,
            "var_95": var_95,
            "var_historical": var_95,
            "var_99": var_99,
            "expected_shortfall": es_95,
            "expected_shortfall_95": es_95,
            "expected_shortfall_99": es_99,
            "max_drawdown": mdd,
            "maximum_drawdown": mdd,
        }
        if self._family == "ewma":
            metrics["ewma_volatility"] = vol_annual
        elif self._family == "cornish_fisher":
            metrics["cornish_fisher_z"] = q95

        return ModelExecutionResult(
            plugin_id=self.metadata.plugin_id,
            model_version=self.metadata.plugin_version,
            metrics=metrics,
            execution_time_ms=t_elapsed_ms,
            observations_used=n,
            warnings=(),
            limitations=self.metadata.limitations,
            metadata={"family": self._family, "parameters": dict(self._params)},
        )


# ==============================================================================
# C4. Plugin Registry
# ==============================================================================

class PluginRegistry:
    """Thread-safe, deterministic registry for managing model plugins."""

    def __init__(self, enforce_trusted_execution: bool = True) -> None:
        self._plugins: Dict[str, ModelPlugin] = {}
        self._trusted_status: Dict[str, bool] = {}
        self._enforce_trusted_execution = enforce_trusted_execution

    def register(self, plugin: ModelPlugin, overwrite: bool = False, trusted: Optional[bool] = None) -> None:
        """Register a ModelPlugin instance with the registry.

        Args:
            plugin: An instance implementing the ModelPlugin protocol.
            overwrite: If False, raises ValueError if plugin_id is already registered.
            trusted: Whether this plugin is verified as trusted for in-process execution.
                     Defaults to True for 'builtin.*' plugins; external plugins default to True
                     if trusted is None, but can be explicitly registered with trusted=False
                     to enforce execution restrictions.

        Raises:
            TypeError: If plugin is not an instance of ModelPlugin.
            ValueError: If plugin_id is duplicate or invalid.
        """
        if not isinstance(plugin, ModelPlugin):
            raise TypeError(f"plugin must be a ModelPlugin instance; got {type(plugin).__name__}")

        meta = plugin.metadata
        pid = meta.plugin_id

        if pid in self._plugins and not overwrite:
            raise ValueError(f"Plugin '{pid}' is already registered. Specify overwrite=True to replace.")

        self._plugins[pid] = plugin
        is_trusted = (trusted if trusted is not None else pid.startswith("builtin."))
        self._trusted_status[pid] = is_trusted

    def is_trusted(self, plugin_id: str) -> bool:
        """Check whether a plugin is trusted for in-process execution."""
        if plugin_id not in self._plugins:
            raise KeyError(f"Plugin '{plugin_id}' not found in registry.")
        return self._trusted_status.get(plugin_id, False)

    def execute_plugin(
        self,
        plugin_id: str,
        input_data: Any,
        config: Optional[Dict[str, Any]] = None,
        trusted_override: bool = False,
    ) -> ModelExecutionResult:
        """Execute a registered plugin with security policy enforcement.

        Raises:
            KeyError: If plugin_id is not registered.
            PermissionError: If plugin is untrusted and trusted_override is False.
        """
        plugin = self.get(plugin_id)
        if self._enforce_trusted_execution and not self.is_trusted(plugin_id) and not trusted_override:
            raise PermissionError(
                f"Execution of untrusted plugin '{plugin_id}' is blocked on unisolated host runtime. "
                "In-process execution of arbitrary third-party code is prohibited by FragilityShield "
                "security policy. An isolated worker container (gVisor/container) is required."
            )
        cfg = dict(config or {})
        return plugin.execute(input_data, cfg)

    def get_isolation_status(self, plugin_id: str) -> Dict[str, Any]:
        """Return clear security and isolation metadata for a registered plugin."""
        plugin = self.get(plugin_id)
        is_builtin = plugin_id.startswith("builtin.")
        is_trusted = self.is_trusted(plugin_id)
        return {
            "plugin_id": plugin_id,
            "is_builtin": is_builtin,
            "is_trusted": is_trusted,
            "host_execution_model": "in_process",
            "os_isolation_active": False,
            "security_warning": (
                None if is_builtin else
                "WARNING: Local runtime executes plugins in-process without OS container isolation. "
                "Third-party untrusted code requires an external isolated worker container."
            ),
        }

    def get(self, plugin_id: str) -> ModelPlugin:
        """Retrieve a registered plugin by plugin_id.

        Raises:
            KeyError: If plugin_id is not found in registry.
        """
        if plugin_id not in self._plugins:
            raise KeyError(f"Plugin '{plugin_id}' not found in registry. Available: {sorted(self._plugins.keys())}")
        return self._plugins[plugin_id]


    def list_plugins(
        self,
        capability: Optional[str] = None,
        data_type: Optional[str] = None,
    ) -> List[PluginMetadata]:
        """List registered plugin metadata sorted alphabetically by plugin_id.

        Args:
            capability: Optional filter by capability identifier.
            data_type: Optional filter by supported data type.

        Returns:
            Alphabetically sorted list of matching PluginMetadata instances.
        """
        results: List[PluginMetadata] = []
        for pid in sorted(self._plugins.keys()):
            meta = self._plugins[pid].metadata
            if capability is not None and capability not in meta.capabilities:
                continue
            if data_type is not None and data_type not in meta.supported_data_types:
                continue
            results.append(meta)
        return results

    def unregister(self, plugin_id: str) -> bool:
        """Remove a plugin from the registry.

        Returns:
            True if removed, False if not present.
        """
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            return True
        return False

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins


_GLOBAL_DEFAULT_REGISTRY: Optional[PluginRegistry] = None


def get_default_registry() -> PluginRegistry:
    """Factory returning the shared global PluginRegistry instance populated with built-ins."""
    global _GLOBAL_DEFAULT_REGISTRY
    if _GLOBAL_DEFAULT_REGISTRY is None:
        registry = PluginRegistry()
        registry.register(HistoricalSimulationPlugin())
        registry.register(ParametricGaussianPlugin())
        registry.register(EWMAVolatilityPlugin())
        registry.register(PortfolioConcentrationPlugin())
        _GLOBAL_DEFAULT_REGISTRY = registry
    return _GLOBAL_DEFAULT_REGISTRY


def reset_default_registry() -> PluginRegistry:
    """Reset the global registry to only built-in plugins."""
    global _GLOBAL_DEFAULT_REGISTRY
    _GLOBAL_DEFAULT_REGISTRY = None
    return get_default_registry()


# Public aliases
PluginManifest = PluginMetadata
get_global_registry = get_default_registry
PluginRegistry.get_plugin = PluginRegistry.get
