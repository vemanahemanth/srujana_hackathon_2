"""Domain models and contracts for FragilityShield.

Contains typed domain definitions for:
- Holding: asset identifier, quantity, and price/valuation representation.
- Portfolio: identifier, currency, holdings, and metadata.
- MetricResult: metric identifier, value, unit, methodology metadata, and warnings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Holding:
    """An individual asset holding within a portfolio.

    Attributes:
        asset_id: Stable, non-empty asset identifier (e.g. 'NSE:HDFCBANK').
        quantity: Non-zero, strictly finite positive quantity of units held.
        price: Strictly finite, positive unit price in portfolio currency.
        sector: Optional sector classification (e.g. 'Banking', 'Information Technology').
        metadata: Optional dictionary for asset attributes.
    """

    asset_id: str
    quantity: float
    price: float
    sector: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError(f"asset_id must be a non-empty string; got {self.asset_id!r}")

        try:
            qty = float(self.quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"quantity must be a finite float; got {self.quantity!r}") from exc

        if not math.isfinite(qty) or qty <= 0.0:
            raise ValueError(f"quantity must be strictly positive and finite; got {self.quantity!r}")

        try:
            px = float(self.price)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"price must be a finite float; got {self.price!r}") from exc

        if not math.isfinite(px) or px <= 0.0:
            raise ValueError(f"price must be strictly positive and finite; got {self.price!r}")

        if self.sector is not None:
            if not isinstance(self.sector, str) or not self.sector.strip():
                raise ValueError(f"sector must be None or a non-empty string; got {self.sector!r}")

    @property
    def market_value(self) -> float:
        """Computed market value: quantity * price."""
        return float(self.quantity) * float(self.price)

    def to_dict(self) -> Dict[str, Any]:
        """Convert holding to a serializable dictionary."""
        return {
            "asset_id": self.asset_id,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "market_value": self.market_value,
            "sector": self.sector,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Holding:
        """Instantiate a Holding from a dictionary."""
        return cls(
            asset_id=str(data["asset_id"]),
            quantity=float(data["quantity"]),
            price=float(data["price"]),
            sector=data.get("sector"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class Portfolio:
    """A collection of holdings representing an investment portfolio.

    Attributes:
        portfolio_id: Unique, non-empty identifier.
        name: Human-readable portfolio name.
        currency: Three-letter ISO currency code (e.g. 'INR', 'USD').
        holdings: Tuple of unique Holding instances.
        metadata: Optional portfolio-level metadata (e.g. benchmark, created_at).
    """

    portfolio_id: str
    name: str
    currency: str
    holdings: Tuple[Holding, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.portfolio_id, str) or not self.portfolio_id.strip():
            raise ValueError(f"portfolio_id must be a non-empty string; got {self.portfolio_id!r}")

        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"name must be a non-empty string; got {self.name!r}")

        if not isinstance(self.currency, str) or len(self.currency.strip()) != 3:
            raise ValueError(
                f"currency must be a 3-letter uppercase ISO currency code; got {self.currency!r}"
            )

        if not self.holdings or len(self.holdings) == 0:
            raise ValueError("portfolio must contain at least one holding")

        seen_assets: set[str] = set()
        for idx, h in enumerate(self.holdings):
            if not isinstance(h, Holding):
                raise TypeError(f"All holdings must be Holding instances; item at index {idx} is {type(h)}")
            norm_id = h.asset_id.strip().upper()
            if norm_id in seen_assets:
                raise ValueError(f"Duplicate asset_id {h.asset_id!r} found in portfolio holdings")
            seen_assets.add(norm_id)

    @property
    def total_value(self) -> float:
        """Sum of market values of all holdings."""
        return sum(h.market_value for h in self.holdings)

    @property
    def weights(self) -> Dict[str, float]:
        """Dictionary mapping asset_id to its proportion of total portfolio value."""
        tot = self.total_value
        if tot <= 0.0:
            raise ValueError("Total portfolio value must be positive to compute weights")
        return {h.asset_id: h.market_value / tot for h in self.holdings}

    @property
    def asset_ids(self) -> List[str]:
        """List of asset identifiers in the portfolio."""
        return [h.asset_id for h in self.holdings]

    def get_holding(self, asset_id: str) -> Optional[Holding]:
        """Retrieve holding by asset ID, case-insensitive match."""
        target = asset_id.strip().upper()
        for h in self.holdings:
            if h.asset_id.strip().upper() == target:
                return h
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert portfolio to a serializable dictionary."""
        return {
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "currency": self.currency.strip().upper(),
            "total_value": self.total_value,
            "holdings": [h.to_dict() for h in self.holdings],
            "weights": self.weights,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Portfolio:
        """Instantiate a Portfolio from a dictionary."""
        holdings_raw = data.get("holdings", [])
        holdings = tuple(Holding.from_dict(h) if isinstance(h, dict) else h for h in holdings_raw)
        return cls(
            portfolio_id=str(data["portfolio_id"]),
            name=str(data["name"]),
            currency=str(data["currency"]).strip().upper(),
            holdings=holdings,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class MetricResult:
    """The result of a quantitative risk, scenario, or model evaluation metric.

    Attributes:
        metric_id: Unique metric identifier (e.g. 'historical_var_95', 'volatility_annualized').
        value: Computed numeric value. Must be strictly finite.
        unit: Measurement unit (e.g. 'ratio', 'percentage', 'INR', 'days').
        methodology: Formal methodology explanation and reference citation.
        parameters: Input parameters used for computation (e.g. {'confidence': 0.95, 'window': 252}).
        warnings: List of diagnostic warnings or data caveats produced during calculation.
        timestamp: ISO 8601 UTC timestamp of calculation.
    """

    metric_id: str
    value: float
    unit: str
    methodology: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not isinstance(self.metric_id, str) or not self.metric_id.strip():
            raise ValueError(f"metric_id must be a non-empty string; got {self.metric_id!r}")

        try:
            val = float(self.value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"value must be a strictly finite float; got {self.value!r}") from exc

        if not math.isfinite(val):
            raise ValueError(f"value must be strictly finite (not NaN or Inf); got {self.value!r}")

        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError(f"unit must be a non-empty string; got {self.unit!r}")

        if not isinstance(self.methodology, str) or not self.methodology.strip():
            raise ValueError(f"methodology must be a non-empty string; got {self.methodology!r}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert metric result to a serializable dictionary."""
        return {
            "metric_id": self.metric_id,
            "value": float(self.value),
            "unit": self.unit,
            "methodology": self.methodology,
            "parameters": dict(self.parameters),
            "warnings": list(self.warnings),
            "timestamp": self.timestamp,
        }
