"""Explainability and Risk Attribution Engine for FragilityShield.

Implements Euler Marginal Risk Allocation and Component Value-at-Risk (Component VaR):
- Decomposes total portfolio VaR into constituent asset and sector risk contributions.
- Proves Euler's homogeneity theorem: sum(ComponentVaR_i) == Total_Portfolio_VaR.
- Identifies risk drivers, hedges, and over-concentrated risk contributors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np

from fragility_engine.data_provenance import DataFreshnessStatus, DataProvenance, DataSourceMode
from fragility_engine.models import Portfolio
from fragility_engine.risk import calculate_historical_var


@dataclass(frozen=True)
class AssetRiskAttribution:
    """Marginal and component risk metrics for a single portfolio holding."""

    asset_id: str
    sector: str
    weight: float
    market_value: float
    asset_volatility: float
    beta_to_portfolio: float
    marginal_var: float
    component_var: float
    percentage_risk_contribution: float
    is_diversifier: bool
    marginal_volatility: float = 0.0
    component_volatility: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert holding attribution to serializable dictionary."""
        return {
            "asset_id": self.asset_id,
            "symbol": self.asset_id,
            "sector": self.sector,
            "weight": float(self.weight),
            "market_value": float(self.market_value),
            "asset_volatility": float(self.asset_volatility),
            "beta_to_portfolio": float(self.beta_to_portfolio),
            "marginal_var": float(self.marginal_var),
            "component_var": float(self.component_var),
            "marginal_volatility": float(self.marginal_volatility),
            "component_volatility": float(self.component_volatility),
            "percentage_risk_contribution": float(self.percentage_risk_contribution),
            "is_diversifier": bool(self.is_diversifier),
        }


@dataclass(frozen=True)
class PortfolioRiskAttributionReport:
    """Comprehensive Euler risk decomposition report for a portfolio."""

    portfolio_id: str
    total_valuation: float
    portfolio_volatility: float
    portfolio_var_95: float
    asset_attributions: Tuple[AssetRiskAttribution, ...]
    sector_risk_contributions: Mapping[str, float]
    euler_discrepancy: float
    methodology: str = "Euler Homogeneity Linear Covariance-Beta Allocation (Jorion Component VaR)"
    disclaimer: str = (
        "Component VaR evaluates marginal linear contribution to historical VaR. "
        "Non-linear tail dependencies and heavy-tailed distributions diverge from linear beta contributions."
    )
    methodology_type: str = "linear_covariance_beta_component_var"
    limitations: Tuple[str, ...] = (
        "Component VaR is derived using the linear covariance beta approximation (Jorion, 1996; Hallerbach, 2002).",
        "Exact tail quantile sensitivities under heavy-tailed (e.g. Student-t) or skewed distributions diverge from linear beta estimates.",
        "Historical tail conditional expectation (ES attribution) is not computed by this model.",
        "Holdings are constrained to long-only positions (quantity > 0.0); short positions are not supported.",
    )
    data_source_mode: str = "SYNTHETIC_TEST_DATA"
    data_provenance: Optional[Mapping[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to serializable dictionary."""
        return {
            "portfolio_id": self.portfolio_id,
            "total_valuation": float(self.total_valuation),
            "portfolio_volatility": float(self.portfolio_volatility),
            "total_portfolio_volatility": float(self.portfolio_volatility),
            "portfolio_var_95": float(self.portfolio_var_95),
            "total_portfolio_var": float(self.portfolio_var_95),
            "asset_attributions": [a.to_dict() for a in self.asset_attributions],
            "sector_risk_contributions": {k: float(v) for k, v in self.sector_risk_contributions.items()},
            "euler_discrepancy": float(self.euler_discrepancy),
            "methodology": self.methodology,
            "disclaimer": self.disclaimer,
            "methodology_type": self.methodology_type,
            "limitations": list(self.limitations),
            "data_source_mode": self.data_source_mode,
            "data_provenance": dict(self.data_provenance) if self.data_provenance else None,
        }


def calculate_portfolio_risk_attribution(
    portfolio: Portfolio,
    asset_returns_matrix: Optional[Mapping[str, Sequence[float]]] = None,
    confidence_level: float = 0.95,
    data_provenance: Optional[Mapping[str, Any]] = None,
) -> PortfolioRiskAttributionReport:
    """Calculate Euler marginal and component risk decomposition across portfolio holdings.

    Methodology:
        Component VaR is derived using the linear covariance beta approximation:
            beta_i = Cov(R_i, R_p) / Var(R_p)
            MarginalVaR_i = beta_i * VaR_p
            ComponentVaR_i = w_i * MarginalVaR_i
        Euler Homogeneity Guarantee: sum(ComponentVaR_i) == VaR_p holds algebraically
        because sum(w_i * beta_i) == 1.0 by definition.

    Limitations:
        - Exact under multivariate Gaussian return assumptions.
        - For non-Gaussian or heavy-tailed returns, true quantile sensitivity diverges from linear beta.
        - Holdings are strictly long-only (quantity > 0.0).

    Args:
        portfolio: Validated Portfolio instance.
        asset_returns_matrix: Optional dictionary mapping asset_id to historical return series.
                              If None, generates synthetic correlated returns calibrated to sectors.
        confidence_level: Target risk quantile (default 0.95).

    Returns:
        PortfolioRiskAttributionReport with exact Euler component reconciliation and methodology metadata.
    """
    if not isinstance(portfolio, Portfolio):
        raise TypeError(f"portfolio must be a Portfolio instance; got {type(portfolio).__name__}")
    if len(portfolio.holdings) == 0:
        raise ValueError("Cannot perform risk attribution on an empty portfolio")

    total_val = portfolio.total_value
    holdings = portfolio.holdings
    num_assets = len(holdings)
    asset_ids = [h.asset_id for h in holdings]
    weights = np.array([h.market_value / total_val for h in holdings], dtype=np.float64)

    # 1. Resolve or generate return matrix
    n_obs = 60
    if asset_returns_matrix is not None:
        ret_arrays = []
        for aid in asset_ids:
            if aid not in asset_returns_matrix:
                raise ValueError(f"Asset '{aid}' missing from provided asset_returns_matrix")
            arr_i = np.asarray(asset_returns_matrix[aid], dtype=np.float64)
            if not np.all(np.isfinite(arr_i)):
                raise ValueError(f"Asset '{aid}' returns contain non-finite values")
            ret_arrays.append(arr_i)
        # Verify length consistency
        lens = {len(a) for a in ret_arrays}
        if len(lens) > 1:
            raise ValueError(f"Inconsistent return series lengths across assets: {lens}")
        matrix = np.column_stack(ret_arrays)
    else:
        # Deterministic synthetic multi-asset correlated generator based on sectors
        rng = np.random.default_rng(42)
        market_factor = rng.normal(0.0005, 0.012, n_obs)
        matrix = np.empty((n_obs, num_assets), dtype=np.float64)
        for j, h in enumerate(holdings):
            # Sector-specific beta and idiosyncratic noise
            sec = (h.sector or "").lower()
            if "bank" in sec or "finance" in sec:
                beta_base = 1.25
                idio_vol = 0.015
            elif "tech" in sec or "it" in sec:
                beta_base = 1.10
                idio_vol = 0.014
            elif "fmcg" in sec or "health" in sec:
                beta_base = 0.75
                idio_vol = 0.009
            else:
                beta_base = 1.00
                idio_vol = 0.011

            idio_noise = rng.normal(0.0, idio_vol, n_obs)
            matrix[:, j] = beta_base * market_factor + idio_noise

    # 2. Portfolio return series R_p = sum(w_i * R_i)
    port_returns = matrix @ weights
    port_vol = float(np.std(port_returns, ddof=1)) * math.sqrt(252.0)
    port_var = calculate_historical_var(port_returns, confidence_level=confidence_level)

    # 3. Covariance matrix and Betas: beta_i = Cov(R_i, R_p) / Var(R_p)
    cov_matrix = np.cov(matrix, rowvar=False)
    # Ensure 2D covariance matrix even for single-asset portfolios
    if cov_matrix.ndim == 0:
        cov_matrix = np.array([[float(cov_matrix)]], dtype=np.float64)
    cov_with_portfolio = cov_matrix @ weights
    var_portfolio_daily = float(np.var(port_returns, ddof=1))

    if var_portfolio_daily > 1e-12:
        betas = cov_with_portfolio / var_portfolio_daily
    else:
        betas = np.zeros(num_assets, dtype=np.float64)

    # 4. Marginal VaR and Component VaR
    # MCR_i = beta_i * VaR_p
    # CVaR_i = w_i * MCR_i
    mcr = betas * port_var
    component_vars = weights * mcr

    # Percentage risk contributions: %CR_i = CVaR_i / VaR_p * 100
    if port_var > 1e-12:
        pct_contribs = (component_vars / port_var) * 100.0
    else:
        pct_contribs = weights * 100.0

    # Sector aggregations
    sector_contributions: Dict[str, float] = {}
    attributions: List[AssetRiskAttribution] = []

    for i, h in enumerate(holdings):
        sec = h.sector.strip() if h.sector and h.sector.strip() else "Unclassified"
        asset_vol_ann = float(np.std(matrix[:, i], ddof=1)) * math.sqrt(252.0)
        c_var_val = float(component_vars[i])
        sector_contributions[sec] = sector_contributions.get(sec, 0.0) + c_var_val

        m_vol = float(betas[i] * port_vol)
        c_vol = float(weights[i] * m_vol)
        attributions.append(
            AssetRiskAttribution(
                asset_id=h.asset_id,
                sector=sec,
                weight=float(weights[i]),
                market_value=float(h.market_value),
                asset_volatility=asset_vol_ann,
                beta_to_portfolio=float(betas[i]),
                marginal_var=float(mcr[i]),
                component_var=c_var_val,
                percentage_risk_contribution=float(pct_contribs[i]),
                is_diversifier=bool(betas[i] < 1.0),
                marginal_volatility=m_vol,
                component_volatility=c_vol,
            )
        )

    # Euler reconciliation check: sum(component_vars) vs port_var
    euler_sum = float(np.sum(component_vars))
    euler_discrepancy = abs(euler_sum - port_var)

    if data_provenance is not None:
        resolved_prov = dict(data_provenance)
        resolved_mode = resolved_prov.get("data_source_mode", DataSourceMode.USER_UPLOADED_DATA.value)
    elif asset_returns_matrix is not None:
        resolved_mode = DataSourceMode.USER_UPLOADED_DATA.value
        resolved_prov = DataProvenance.user_uploaded(
            source_name="User-provided asset returns matrix",
            sample_count=len(ret_arrays[0]),
        ).to_dict()
    else:
        resolved_mode = DataSourceMode.SYNTHETIC_TEST_DATA.value
        resolved_prov = DataProvenance.synthetic_demo(
            reason="Synthetic sector-calibrated covariance model (no live or historical asset price series provided). Illustrative simulation only.",
        ).to_dict()

    return PortfolioRiskAttributionReport(
        portfolio_id=portfolio.portfolio_id,
        total_valuation=total_val,
        portfolio_volatility=port_vol,
        portfolio_var_95=port_var,
        asset_attributions=tuple(attributions),
        sector_risk_contributions=sector_contributions,
        euler_discrepancy=euler_discrepancy,
        methodology="Euler Homogeneity Linear Covariance-Beta Allocation (Jorion Component VaR)",
        disclaimer=(
            "Component VaR evaluates marginal linear contribution to historical VaR. "
            "Non-linear tail dependencies and heavy-tailed distributions diverge from linear beta contributions."
        ),
        methodology_type="linear_covariance_beta_component_var",
        limitations=(
            "Component VaR is derived using the linear covariance beta approximation (Jorion, 1996; Hallerbach, 2002).",
            "Exact tail quantile sensitivities under heavy-tailed (e.g. Student-t) or skewed distributions diverge from linear beta estimates.",
            "Historical tail conditional expectation (ES attribution) is not computed by this model.",
            "Holdings are constrained to long-only positions (quantity > 0.0); short positions are not supported.",
        ),
        data_source_mode=resolved_mode,
        data_provenance=resolved_prov,
    )


def verify_attribution_finite_difference(
    portfolio: Portfolio,
    asset_returns_matrix: Mapping[str, Sequence[float]],
    confidence_level: float = 0.95,
    epsilon: float = 1e-4,
) -> Dict[str, Any]:
    """Audit Euler Marginal VaR using fixed-exposure finite differences without weight re-normalization.

    Computes numerical marginal VaR:
        dVaR / dw_k = [VaR(w + eps * e_k) - VaR(w)] / eps
    where other asset exposures w_j (j != k) remain strictly fixed.

    Under Gaussian return assumptions, dVaR / dw_k reconciles closely with beta_k * VaR_p.
    Under non-Gaussian heavy-tailed distributions (e.g. Student-t), the numerical derivative
    diverges from the linear covariance beta approximation.

    Args:
        portfolio: Validated Portfolio instance.
        asset_returns_matrix: Mapping of asset IDs to return sequences.
        confidence_level: VaR confidence level (default 0.95).
        epsilon: Exposure perturbation magnitude (default 1e-4).

    Returns:
        Dictionary with numerical marginal VaRs, beta-based marginal VaRs, and discrepancies.
    """
    if not isinstance(portfolio, Portfolio):
        raise TypeError(f"portfolio must be a Portfolio instance; got {type(portfolio).__name__}")
    if len(portfolio.holdings) == 0:
        raise ValueError("Cannot audit empty portfolio")

    total_val = portfolio.total_value
    holdings = portfolio.holdings
    num_assets = len(holdings)
    asset_ids = [h.asset_id for h in holdings]
    base_weights = np.array([h.market_value / total_val for h in holdings], dtype=np.float64)

    ret_arrays = []
    for aid in asset_ids:
        if aid not in asset_returns_matrix:
            raise ValueError(f"Asset '{aid}' missing from asset_returns_matrix")
        ret_arrays.append(np.asarray(asset_returns_matrix[aid], dtype=np.float64))
    matrix = np.column_stack(ret_arrays)

    base_port_returns = matrix @ base_weights
    base_var = calculate_historical_var(base_port_returns, confidence_level=confidence_level)

    cov_matrix = np.cov(matrix, rowvar=False)
    if cov_matrix.ndim == 0:
        cov_matrix = np.array([[float(cov_matrix)]], dtype=np.float64)
    cov_with_portfolio = cov_matrix @ base_weights
    var_p = float(np.var(base_port_returns, ddof=1))
    betas = cov_with_portfolio / var_p if var_p > 1e-12 else np.zeros(num_assets, dtype=np.float64)
    linear_mcr = betas * base_var

    numerical_mcr = np.zeros(num_assets, dtype=np.float64)
    for k in range(num_assets):
        perturbed_weights = base_weights.copy()
        perturbed_weights[k] += epsilon
        # Fixed exposure: evaluate returns directly with unnormalized perturbed weights
        perturbed_returns = matrix @ perturbed_weights
        perturbed_var = calculate_historical_var(perturbed_returns, confidence_level=confidence_level)
        numerical_mcr[k] = (perturbed_var - base_var) / epsilon

    max_discrepancy = float(np.max(np.abs(numerical_mcr - linear_mcr)))
    mean_discrepancy = float(np.mean(np.abs(numerical_mcr - linear_mcr)))

    return {
        "asset_ids": asset_ids,
        "base_var": float(base_var),
        "linear_marginal_var": linear_mcr.tolist(),
        "numerical_marginal_var": numerical_mcr.tolist(),
        "max_discrepancy": max_discrepancy,
        "mean_discrepancy": mean_discrepancy,
        "methodology_type": "fixed_exposure_finite_difference",
    }

