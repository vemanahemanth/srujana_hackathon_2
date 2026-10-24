"""FragilityShield — Scenario Lab Engine (Phase 4).

This module provides a pure, deterministic scenario stress-testing engine that
applies instantaneous price shocks to an existing portfolio snapshot.

Key quantitative and structural characteristics:
- Deterministic, framework-agnostic arithmetic (unrounded internal IEEE 754 float math).
- Explicit conflict rejection: if a sector-level shock and an asset-specific shock
  target the same holding, the execution is rejected by default.
- Strict validation: non-finite shocks, non-positive resulting prices, unknown
  asset/sector references, and empty portfolios are rejected.
- Comprehensive attribution: holding-level, sector-level, and portfolio-level P&L
  reconciliation with positive loss reporting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from fragility_engine.models import Holding, Portfolio


@dataclass(frozen=True)
class ScenarioDefinition:
    """Deterministic scenario specification for portfolio stress testing.

    Attributes:
        scenario_id: Unique, non-empty identifier for the scenario.
        name: Human-readable scenario name.
        description: Detailed narrative of the stress narrative or hypothesis.
        sector_shocks: Mapping of sector name to decimal price return (e.g. -0.20 for -20%).
        asset_shocks: Mapping of asset ID to decimal price return.
        metadata: Optional additional metadata (e.g. author, regulatory tags).
        version: Scenario specification version string (defaults to "1.0").
    """

    scenario_id: str
    name: str
    description: str = ""
    sector_shocks: Mapping[str, float] = field(default_factory=dict)
    asset_shocks: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: str = "1.0"

    def __post_init__(self) -> None:
        """Validate scenario parameters upon instantiation."""
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id must be a non-empty string.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string.")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string.")

        # Validate sector shocks
        for sector, shock in self.sector_shocks.items():
            if not isinstance(sector, str) or not sector.strip():
                raise ValueError("Sector names in sector_shocks must be non-empty strings.")
            if not isinstance(shock, (int, float)) or isinstance(shock, bool) or not math.isfinite(shock):
                raise ValueError(f"Sector shock for '{sector}' must be a finite numeric value, got: {shock}")
            if shock <= -1.0:
                raise ValueError(
                    f"Sector shock for '{sector}' is {shock}, which produces zero or negative prices (must be > -1.0)."
                )

        # Validate asset shocks
        for asset, shock in self.asset_shocks.items():
            if not isinstance(asset, str) or not asset.strip():
                raise ValueError("Asset IDs in asset_shocks must be non-empty strings.")
            if not isinstance(shock, (int, float)) or isinstance(shock, bool) or not math.isfinite(shock):
                raise ValueError(f"Asset shock for '{asset}' must be a finite numeric value, got: {shock}")
            if shock <= -1.0:
                raise ValueError(
                    f"Asset shock for '{asset}' is {shock}, which produces zero or negative prices (must be > -1.0)."
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert scenario definition to JSON-serializable dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "sector_shocks": dict(self.sector_shocks),
            "asset_shocks": dict(self.asset_shocks),
            "metadata": dict(self.metadata),
            "version": self.version,
        }


@dataclass(frozen=True)
class HoldingScenarioResult:
    """Calculated scenario impact on an individual holding.

    Attributes:
        asset_id: Unique asset identifier.
        sector: Economic sector of the holding.
        quantity: Original holding quantity.
        original_price: Original asset market price.
        original_market_value: Original holding market value.
        applied_shock: Decimal return applied (0.0 if unshocked).
        shock_source: Source of the shock ('sector', 'asset', or 'none').
        stressed_price: Price after scenario shock.
        stressed_market_value: Market value after scenario shock.
        pnl_contribution: Monetary profit and loss contribution (stressed - original).
    """

    asset_id: str
    sector: str
    quantity: float
    original_price: float
    original_market_value: float
    applied_shock: float
    shock_source: str
    stressed_price: float
    stressed_market_value: float
    pnl_contribution: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert holding scenario result to dictionary."""
        return {
            "asset_id": self.asset_id,
            "sector": self.sector,
            "quantity": self.quantity,
            "original_price": self.original_price,
            "original_market_value": self.original_market_value,
            "applied_shock": self.applied_shock,
            "shock_source": self.shock_source,
            "stressed_price": self.stressed_price,
            "stressed_market_value": self.stressed_market_value,
            "pnl_contribution": self.pnl_contribution,
        }


@dataclass(frozen=True)
class SectorScenarioResult:
    """Calculated scenario impact aggregated at the sector level.

    Attributes:
        sector: Sector name.
        original_value: Aggregate original market value of holdings in this sector.
        stressed_value: Aggregate stressed market value of holdings in this sector.
        pnl_contribution: Monetary P&L contribution from this sector.
        percentage_return: Return percentage for the sector under stress.
    """

    sector: str
    original_value: float
    stressed_value: float
    pnl_contribution: float
    percentage_return: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert sector scenario result to dictionary."""
        return {
            "sector": self.sector,
            "original_value": self.original_value,
            "stressed_value": self.stressed_value,
            "pnl_contribution": self.pnl_contribution,
            "percentage_return": self.percentage_return,
        }


@dataclass(frozen=True)
class ScenarioResult:
    """Comprehensive portfolio-level stress testing result.

    Attributes:
        scenario_id: Identifier of the executed scenario.
        scenario_name: Name of the executed scenario.
        version: Scenario specification version.
        original_portfolio_value: Total original portfolio market value.
        stressed_portfolio_value: Total portfolio market value under stress.
        total_pnl: Monetary net profit or loss (stressed - original).
        scenario_return: Net return percentage (total_pnl / original_portfolio_value).
        loss_magnitude: Positive monetary loss magnitude (abs(total_pnl) if total_pnl < 0 else 0.0).
        holding_results: Tuple of HoldingScenarioResult for all holdings.
        sector_results: Tuple of SectorScenarioResult for all portfolio sectors.
        unshocked_assets: Tuple of asset IDs that experienced 0.0 shock.
        applied_assumptions: Dictionary of applied assumptions and shock parameters.
        metadata: Scenario metadata passed from definition.
    """

    scenario_id: str
    scenario_name: str
    version: str
    original_portfolio_value: float
    stressed_portfolio_value: float
    total_pnl: float
    scenario_return: float
    loss_magnitude: float
    holding_results: Tuple[HoldingScenarioResult, ...]
    sector_results: Tuple[SectorScenarioResult, ...]
    unshocked_assets: Tuple[str, ...]
    applied_assumptions: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert portfolio scenario result to dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "version": self.version,
            "original_portfolio_value": self.original_portfolio_value,
            "stressed_portfolio_value": self.stressed_portfolio_value,
            "total_pnl": self.total_pnl,
            "scenario_return": self.scenario_return,
            "loss_magnitude": self.loss_magnitude,
            "holding_results": [h.to_dict() for h in self.holding_results],
            "sector_results": [s.to_dict() for s in self.sector_results],
            "unshocked_assets": list(self.unshocked_assets),
            "applied_assumptions": dict(self.applied_assumptions),
            "metadata": dict(self.metadata),
        }


def validate_scenario_against_portfolio(
    scenario: ScenarioDefinition,
    portfolio: Portfolio,
) -> None:
    """Validate a scenario against an existing portfolio.

    Rules enforced:
    1. Portfolio must be a valid, non-empty Portfolio instance.
    2. Scenario must be a ScenarioDefinition instance.
    3. All sectors specified in sector_shocks must exist in the portfolio.
    4. All assets specified in asset_shocks must exist in the portfolio.
    5. Conflict rejection: If any holding's sector has a sector-level shock AND
       the holding's asset ID has an asset-specific shock, the execution is rejected.
       Silent precedence or combination of shocks is strictly prohibited.
    6. Shocks producing non-positive prices (<= 0) are rejected.

    Args:
        scenario: The ScenarioDefinition to validate.
        portfolio: The Portfolio instance to validate against.

    Raises:
        TypeError: If inputs are of incorrect type.
        ValueError: If unknown sectors, unknown assets, conflicts, or invalid shocks are found.
    """
    if not isinstance(portfolio, Portfolio):
        raise TypeError(f"portfolio must be an instance of Portfolio, got: {type(portfolio).__name__}")
    if not portfolio.holdings or len(portfolio.holdings) == 0:
        raise ValueError("Portfolio must contain at least one holding.")
    if not isinstance(scenario, ScenarioDefinition):
        raise TypeError(f"scenario must be an instance of ScenarioDefinition, got: {type(scenario).__name__}")

    portfolio_sectors = {h.sector for h in portfolio.holdings if h.sector}
    portfolio_assets = set(portfolio.asset_ids)

    # Check unknown sectors
    for sector in scenario.sector_shocks:
        if sector not in portfolio_sectors:
            raise ValueError(
                f"Unknown sector in scenario: '{sector}'. "
                f"Portfolio contains only: {sorted(portfolio_sectors)}"
            )

    # Check unknown assets
    for asset in scenario.asset_shocks:
        if asset not in portfolio_assets:
            raise ValueError(
                f"Unknown asset in scenario: '{asset}'. "
                f"Portfolio contains only: {sorted(portfolio_assets)}"
            )

    # Check rule conflicts on individual holdings
    for holding in portfolio.holdings:
        has_sector_shock = bool(holding.sector and holding.sector in scenario.sector_shocks)
        has_asset_shock = holding.asset_id in scenario.asset_shocks

        if has_sector_shock and has_asset_shock:
            sector_shock_val = scenario.sector_shocks[holding.sector]
            asset_shock_val = scenario.asset_shocks[holding.asset_id]
            raise ValueError(
                f"Conflicting scenario rules targeting holding '{holding.asset_id}': "
                f"Sector shock for '{holding.sector}' ({sector_shock_val:+.2%}) and "
                f"Asset shock for '{holding.asset_id}' ({asset_shock_val:+.2%}) both apply. "
                "Conflicting shocks are rejected by default."
            )

        # Check resulting price strictly positive
        applied_shock = 0.0
        if has_asset_shock:
            applied_shock = scenario.asset_shocks[holding.asset_id]
        elif has_sector_shock:
            applied_shock = scenario.sector_shocks[holding.sector]

        stressed_price = holding.price * (1.0 + applied_shock)
        if stressed_price <= 0.0 or not math.isfinite(stressed_price):
            raise ValueError(
                f"Shock {applied_shock:+.4f} on holding '{holding.asset_id}' yields "
                f"invalid non-positive price: {stressed_price:.4f}."
            )


def apply_scenario(
    portfolio: Portfolio,
    scenario: ScenarioDefinition,
) -> ScenarioResult:
    """Apply deterministic scenario stress shocks to a portfolio snapshot.

    Formulas:
        stressed_price = original_price * (1 + shock)
        stressed_holding_value = quantity * stressed_price
        holding_pnl = stressed_holding_value - original_holding_value
        portfolio_pnl = stressed_portfolio_value - original_portfolio_value
        scenario_return = portfolio_pnl / original_portfolio_value
        loss_magnitude = -portfolio_pnl if portfolio_pnl < 0 else 0.0

    Args:
        portfolio: Valid Portfolio instance (unmodified).
        scenario: Valid ScenarioDefinition instance.

    Returns:
        Comprehensive ScenarioResult object.
    """
    validate_scenario_against_portfolio(scenario, portfolio)

    holding_results: List[HoldingScenarioResult] = []
    unshocked_assets: List[str] = []

    for holding in portfolio.holdings:
        holding_sector = holding.sector or ""
        if holding.asset_id in scenario.asset_shocks:
            shock = float(scenario.asset_shocks[holding.asset_id])
            source = "asset"
        elif holding_sector and holding_sector in scenario.sector_shocks:
            shock = float(scenario.sector_shocks[holding_sector])
            source = "sector"
        else:
            shock = 0.0
            source = "none"
            unshocked_assets.append(holding.asset_id)

        # Unrounded exact calculations
        stressed_price = holding.price * (1.0 + shock)
        stressed_holding_value = holding.quantity * stressed_price
        original_holding_value = holding.market_value
        holding_pnl = stressed_holding_value - original_holding_value

        holding_results.append(
            HoldingScenarioResult(
                asset_id=holding.asset_id,
                sector=holding_sector,
                quantity=holding.quantity,
                original_price=holding.price,
                original_market_value=original_holding_value,
                applied_shock=shock,
                shock_source=source,
                stressed_price=stressed_price,
                stressed_market_value=stressed_holding_value,
                pnl_contribution=holding_pnl,
            )
        )

    # Portfolio level aggregates
    original_portfolio_value = portfolio.total_value
    stressed_portfolio_value = sum(h.stressed_market_value for h in holding_results)
    total_pnl = stressed_portfolio_value - original_portfolio_value
    scenario_return = (
        total_pnl / original_portfolio_value if original_portfolio_value > 0.0 else 0.0
    )
    loss_magnitude = -total_pnl if total_pnl < 0.0 else 0.0

    # Sector level reconciliation
    unique_sectors = sorted(
        {h.sector.strip() if h.sector and h.sector.strip() else "Unclassified" for h in portfolio.holdings}
    )
    sector_results: List[SectorScenarioResult] = []
    for sector in unique_sectors:
        sector_holdings = [
            h
            for h in holding_results
            if (h.sector.strip() if h.sector and h.sector.strip() else "Unclassified") == sector
        ]
        sector_orig = sum(h.original_market_value for h in sector_holdings)
        sector_stressed = sum(h.stressed_market_value for h in sector_holdings)
        sector_pnl = sector_stressed - sector_orig
        sector_ret = sector_pnl / sector_orig if sector_orig > 0.0 else 0.0

        sector_results.append(
            SectorScenarioResult(
                sector=sector,
                original_value=sector_orig,
                stressed_value=sector_stressed,
                pnl_contribution=sector_pnl,
                percentage_return=sector_ret,
            )
        )

    # Verify mathematical P&L reconciliation
    holdings_pnl_sum = sum(h.pnl_contribution for h in holding_results)
    if not math.isclose(total_pnl, holdings_pnl_sum, rel_tol=1e-12, abs_tol=1e-9):
        raise RuntimeError(
            f"P&L reconciliation failure: Portfolio P&L ({total_pnl}) != "
            f"Sum of holding P&Ls ({holdings_pnl_sum})"
        )

    sector_pnl_sum = sum(s.pnl_contribution for s in sector_results)
    if not math.isclose(total_pnl, sector_pnl_sum, rel_tol=1e-12, abs_tol=1e-9):
        raise RuntimeError(
            f"Sector P&L reconciliation failure: Portfolio P&L ({total_pnl}) != "
            f"Sum of sector P&Ls ({sector_pnl_sum})"
        )

    applied_assumptions = {
        "sector_shocks": dict(scenario.sector_shocks),
        "asset_shocks": dict(scenario.asset_shocks),
        "shock_model": "instantaneous_deterministic_price_shock",
        "conflict_policy": "strict_rejection",
    }

    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        version=scenario.version,
        original_portfolio_value=original_portfolio_value,
        stressed_portfolio_value=stressed_portfolio_value,
        total_pnl=total_pnl,
        scenario_return=scenario_return,
        loss_magnitude=loss_magnitude,
        holding_results=tuple(holding_results),
        sector_results=tuple(sector_results),
        unshocked_assets=tuple(unshocked_assets),
        applied_assumptions=applied_assumptions,
        metadata=dict(scenario.metadata),
    )


def create_preset_scenario(
    preset_id: str,
    it_sector_name: str = "Information Technology",
) -> ScenarioDefinition:
    """Retrieve pre-configured benchmark scenario definitions.

    Available presets:
        - "banking_minus_20_it_minus_10": Simultaneous 20% decline in Banking and
          10% decline in IT / Information Technology sector assets.

    Args:
        preset_id: Identifier of the benchmark preset scenario.
        it_sector_name: Sector name for IT in the target portfolio (default "Information Technology").

    Returns:
        ScenarioDefinition configured for the specified preset.
    """
    if preset_id == "banking_minus_20_it_minus_10":
        return ScenarioDefinition(
            scenario_id="banking_minus_20_it_minus_10",
            name="Banking -20% & IT -10% Stress Scenario",
            description=(
                "Standard fragility benchmark scenario: -20% instantaneous shock on all "
                "Banking sector assets and -10% instantaneous shock on all IT sector assets."
            ),
            sector_shocks={"Banking": -0.20, it_sector_name: -0.10},
            asset_shocks={},
            metadata={"category": "sector_stress", "benchmark": True},
            version="1.0",
        )
    raise ValueError(f"Unknown preset scenario ID: '{preset_id}'")
