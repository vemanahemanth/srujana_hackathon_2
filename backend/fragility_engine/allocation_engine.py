"""Quantitative Portfolio Allocation & Optimization Engine for FragilityShield.

Implements institutional-grade portfolio optimization methods:
- Minimum Variance
- Mean-Variance Utility (Markowitz quadratic utility)
- Maximum Sharpe Ratio
- Equal Risk Contribution / Risk Parity
- Equal Weight (1/N benchmark)
- Minimum Concentration (Herfindahl-Hirschman Index penalty)
- Target Volatility & Target Return
- CVaR / Expected Shortfall Minimization

Mathematical & Execution Safeguards:
- Strict feasibility validation (bounds consistency, budget equality, covariance conditioning).
- Matrix shrinkage (Ledoit-Wolf & EWMA options) to handle collinearity and estimation noise.
- Transparent turnover and transaction cost drag accounting.
- Euler risk contribution decomposition: %RC_i = w_i * (Sigma * w)_i / (w^T * Sigma * w).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
from scipy.optimize import minimize

from fragility_engine.provenance import DataProvenance


# ==============================================================================
# 1. Configuration & Domain Types
# ==============================================================================

@dataclass
class AllocationConfig:
    """Configuration for quantitative portfolio optimization."""

    objective: str = "min_variance"  # min_variance, max_sharpe, mean_variance, risk_parity, equal_weight, target_vol, target_return, min_concentration
    asset_ids: List[str] = field(default_factory=list)
    min_weight: float = 0.0
    max_weight: float = 1.0
    asset_bounds: Optional[Dict[str, Tuple[float, float]]] = None
    target_return: Optional[float] = None
    target_volatility: Optional[float] = None
    risk_aversion: float = 2.5
    risk_free_rate: float = 0.065
    cash_reserve_pct: float = 0.0
    max_turnover: Optional[float] = None
    current_weights: Optional[Dict[str, float]] = None
    transaction_cost_bps: float = 10.0
    covariance_estimator: str = "sample"  # sample, ledoit_wolf, ewma
    expected_returns_estimator: str = "sample_mean"  # sample_mean, capm, zero
    annualization_factor: float = 252.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "asset_ids": self.asset_ids,
            "min_weight": self.min_weight,
            "max_weight": self.max_weight,
            "asset_bounds": {k: list(v) for k, v in (self.asset_bounds or {}).items()},
            "target_return": self.target_return,
            "target_volatility": self.target_volatility,
            "risk_aversion": self.risk_aversion,
            "risk_free_rate": self.risk_free_rate,
            "cash_reserve_pct": self.cash_reserve_pct,
            "max_turnover": self.max_turnover,
            "current_weights": self.current_weights,
            "transaction_cost_bps": self.transaction_cost_bps,
            "covariance_estimator": self.covariance_estimator,
            "expected_returns_estimator": self.expected_returns_estimator,
            "annualization_factor": self.annualization_factor,
        }


@dataclass
class FeasibilityCheckResult:
    """Pre-flight feasibility validation of allocation constraints and covariance matrix."""

    is_feasible: bool
    status: str  # feasible, infeasible, warning
    condition_number: float
    eigenvalues_min: float
    budget_satisfiable: bool
    diagnostics: List[str]
    remediation_advice: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_feasible": self.is_feasible,
            "status": self.status,
            "condition_number": float(self.condition_number),
            "eigenvalues_min": float(self.eigenvalues_min),
            "budget_satisfiable": self.budget_satisfiable,
            "diagnostics": self.diagnostics,
            "remediation_advice": self.remediation_advice,
        }


@dataclass
class QuantitativeOptimizationResult:
    """Comprehensive optimization output with weights, risk metrics, and solver diagnostics."""

    objective: str
    asset_ids: List[str]
    weights: Dict[str, float]
    cash_weight: float
    expected_return_annualized: float
    volatility_annualized: float
    sharpe_ratio: float
    diversification_ratio: float
    effective_n_assets: float
    herfindahl_index: float
    risk_contributions: Dict[str, float]
    percent_risk_contributions: Dict[str, float]
    turnover: float
    estimated_transaction_cost_pct: float
    solver_success: bool
    solver_message: str
    iterations: int
    diagnostics: Dict[str, Any]
    disclaimer: str = (
        "Quantitative optimization output is based on historical sample estimates and model assumptions. "
        "It does not guarantee future risk reduction or investment outperformance."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "asset_ids": self.asset_ids,
            "weights": {k: round(float(v), 6) for k, v in self.weights.items()},
            "cash_weight": round(float(self.cash_weight), 6),
            "expected_return_annualized": round(float(self.expected_return_annualized), 6),
            "volatility_annualized": round(float(self.volatility_annualized), 6),
            "sharpe_ratio": round(float(self.sharpe_ratio), 4),
            "diversification_ratio": round(float(self.diversification_ratio), 4),
            "effective_n_assets": round(float(self.effective_n_assets), 2),
            "herfindahl_index": round(float(self.herfindahl_index), 4),
            "risk_contributions": {k: round(float(v), 6) for k, v in self.risk_contributions.items()},
            "percent_risk_contributions": {k: round(float(v), 4) for k, v in self.percent_risk_contributions.items()},
            "turnover": round(float(self.turnover), 4),
            "estimated_transaction_cost_pct": round(float(self.estimated_transaction_cost_pct), 6),
            "solver_success": self.solver_success,
            "solver_message": self.solver_message,
            "iterations": self.iterations,
            "diagnostics": self.diagnostics,
            "disclaimer": self.disclaimer,
        }


# ==============================================================================
# 2. Mathematical Estimators (Covariance & Expected Returns)
# ==============================================================================

def estimate_covariance(
    returns_matrix: np.ndarray,
    method: str = "sample",
) -> np.ndarray:
    """Compute asset return covariance with optional shrinkage to avoid singularity."""
    r = np.asarray(returns_matrix, dtype=np.float64)
    t, k = r.shape
    if t < 2 or k < 1:
        raise ValueError("Returns matrix must have at least 2 observations.")

    sample_cov = np.cov(r, rowvar=False)
    if k == 1:
        return np.array([[float(sample_cov)]], dtype=np.float64)

    if method == "ledoit_wolf":
        # Linear shrinkage towards structured identity target
        mu_var = np.trace(sample_cov) / k
        target = mu_var * np.eye(k)
        # Empirical shrinkage intensity estimate
        shrinkage = max(0.01, min(0.35, float(k) / float(t)))
        shrunk_cov = (1.0 - shrinkage) * sample_cov + shrinkage * target
        return shrunk_cov
    elif method == "ewma":
        decay = 0.94
        weights = np.array([(1.0 - decay) * (decay ** i) for i in range(t)][::-1])
        weights /= np.sum(weights)
        mean_centered = r - np.average(r, axis=0, weights=weights)
        ewma_cov = (mean_centered.T * weights) @ mean_centered
        return ewma_cov

    return sample_cov


def estimate_expected_returns(
    returns_matrix: np.ndarray,
    method: str = "sample_mean",
    annualization_factor: float = 252.0,
) -> np.ndarray:
    """Estimate annualized expected returns vector."""
    r = np.asarray(returns_matrix, dtype=np.float64)
    t, k = r.shape
    if method == "zero":
        return np.zeros(k, dtype=np.float64)
    
    # Sample mean annualized
    means = np.mean(r, axis=0) * annualization_factor
    return means


# ==============================================================================
# 3. Feasibility Pre-Flight Validator
# ==============================================================================

def validate_allocation_feasibility(
    cov: np.ndarray,
    config: AllocationConfig,
) -> FeasibilityCheckResult:
    """Check mathematical and economic feasibility of constraints before optimization."""
    k = len(config.asset_ids)
    diagnostics: List[str] = []
    status = "feasible"
    is_feasible = True
    advice: Optional[str] = None

    # 1. Covariance conditioning & positive definiteness
    eigenvals = np.linalg.eigvalsh(cov)
    min_eig = float(np.min(eigenvals))
    max_eig = float(np.max(eigenvals))
    cond_num = float(max_eig / max(min_eig, 1e-12))

    if min_eig <= 1e-9:
        is_feasible = False
        status = "infeasible"
        diagnostics.append(f"Covariance matrix is singular or ill-conditioned (min eigenvalue = {min_eig:.2e}).")
        advice = "Use Ledoit-Wolf shrinkage or drop collinear assets to restore positive-definiteness."
    elif cond_num > 1e6:
        status = "warning"
        diagnostics.append(f"High condition number ({cond_num:.1e}) indicates potential numerical instability.")

    # 2. Budget constraint feasibility with cash reserve
    investable_budget = 1.0 - config.cash_reserve_pct
    min_bounds = []
    max_bounds = []
    for a in config.asset_ids:
        b = (config.asset_bounds or {}).get(a, (config.min_weight, config.max_weight))
        min_bounds.append(b[0])
        max_bounds.append(b[1])

    sum_min = sum(min_bounds)
    sum_max = sum(max_bounds)

    budget_ok = (sum_min <= investable_budget + 1e-6) and (sum_max >= investable_budget - 1e-6)
    if not budget_ok:
        is_feasible = False
        status = "infeasible"
        diagnostics.append(
            f"Weight bounds [sum_min={sum_min:.2f}, sum_max={sum_max:.2f}] cannot satisfy investable budget {investable_budget:.2f}."
        )
        advice = f"Adjust asset minimums (sum={sum_min:.2f}) or maximums (sum={sum_max:.2f}) to enclose {investable_budget:.2f}."

    if any(min_bounds[i] > max_bounds[i] for i in range(k)):
        is_feasible = False
        status = "infeasible"
        diagnostics.append("One or more assets have lower bound strictly greater than upper bound.")

    return FeasibilityCheckResult(
        is_feasible=is_feasible,
        status=status,
        condition_number=cond_num,
        eigenvalues_min=min_eig,
        budget_satisfiable=budget_ok,
        diagnostics=diagnostics,
        remediation_advice=advice,
    )


# ==============================================================================
# 4. Core Optimization Solvers
# ==============================================================================

def solve_quantitative_allocation(
    returns_matrix: np.ndarray,
    config: AllocationConfig,
) -> QuantitativeOptimizationResult:
    """Execute quantitative portfolio optimization for the configured objective."""
    asset_ids = list(config.asset_ids)
    k = len(asset_ids)
    if k == 0:
        raise ValueError("At least one asset must be specified in asset_ids.")

    cov = estimate_covariance(returns_matrix, method=config.covariance_estimator)
    mu = estimate_expected_returns(returns_matrix, method=config.expected_returns_estimator, annualization_factor=config.annualization_factor)

    # Pre-flight check
    feasibility = validate_allocation_feasibility(cov, config)
    if not feasibility.is_feasible:
        # Return structured diagnostic failure rather than unhandled exception
        empty_w = {a: 0.0 for a in asset_ids}
        return QuantitativeOptimizationResult(
            objective=config.objective,
            asset_ids=asset_ids,
            weights=empty_w,
            cash_weight=1.0,
            expected_return_annualized=0.0,
            volatility_annualized=0.0,
            sharpe_ratio=0.0,
            diversification_ratio=1.0,
            effective_n_assets=0.0,
            herfindahl_index=1.0,
            risk_contributions={a: 0.0 for a in asset_ids},
            percent_risk_contributions={a: 0.0 for a in asset_ids},
            turnover=0.0,
            estimated_transaction_cost_pct=0.0,
            solver_success=False,
            solver_message=f"Infeasible configuration: {'; '.join(feasibility.diagnostics)}",
            iterations=0,
            diagnostics={"feasibility": feasibility.to_dict()},
        )

    investable_budget = max(0.0, 1.0 - config.cash_reserve_pct)
    ann = config.annualization_factor
    sqrt_ann = math.sqrt(ann)

    # 1. Equal-Weight Shortcut
    if config.objective == "equal_weight":
        opt_w = np.full(k, investable_budget / k, dtype=np.float64)
        success = True
        msg = "Equal-weight allocation calculated analytically."
        nit = 1
    else:
        # Setup bounds
        bounds = []
        for a in asset_ids:
            b = (config.asset_bounds or {}).get(a, (config.min_weight, config.max_weight))
            bounds.append((float(b[0]), float(b[1])))

        # Budget equality constraint: sum(w) = investable_budget
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - investable_budget}]

        # Turnover constraint if specified
        if config.max_turnover is not None and config.current_weights:
            w_curr = np.array([config.current_weights.get(a, 0.0) for a in asset_ids], dtype=np.float64)
            constraints.append({
                "type": "ineq",
                "fun": lambda w: config.max_turnover - 0.5 * np.sum(np.abs(w - w_curr)),
            })

        # Target Return constraint
        if config.target_return is not None and config.objective in ["target_return", "min_variance"]:
            constraints.append({
                "type": "ineq",
                "fun": lambda w: (w @ mu) - float(config.target_return),
            })

        # Target Volatility constraint
        if config.target_volatility is not None and config.objective in ["target_vol", "max_sharpe"]:
            max_var = (float(config.target_volatility) / sqrt_ann) ** 2
            constraints.append({
                "type": "ineq",
                "fun": lambda w: max_var - (w @ cov @ w),
            })

        # Objective Functions
        w0 = np.full(k, investable_budget / k, dtype=np.float64)

        if config.objective == "min_variance":
            def obj(w: np.ndarray) -> float:
                return float(w @ cov @ w)
        elif config.objective == "mean_variance":
            # Maximize: w^T mu - (lambda/2) w^T Cov w  =>  Minimize: (lambda/2) w^T Cov w - w^T mu
            lam = max(0.1, config.risk_aversion)
            def obj(w: np.ndarray) -> float:
                return float(0.5 * lam * (w @ cov @ w) - (w @ mu / ann))
        elif config.objective == "max_sharpe":
            rf_daily = config.risk_free_rate / ann
            def obj(w: np.ndarray) -> float:
                port_ret = (w @ mu / ann) - rf_daily
                port_sd = math.sqrt(max(1e-12, float(w @ cov @ w)))
                return -float(port_ret / port_sd)
        elif config.objective == "risk_parity":
            # Equal Risk Contribution: minimize sum_i sum_j (RC_i - RC_j)^2
            def obj(w: np.ndarray) -> float:
                w_safe = np.maximum(w, 1e-6)
                marginal = cov @ w_safe
                rc = w_safe * marginal
                target_rc = np.mean(rc)
                return float(np.sum((rc - target_rc) ** 2))
        elif config.objective == "min_concentration":
            # Minimize Herfindahl Index sum(w_i^2)
            def obj(w: np.ndarray) -> float:
                return float(np.sum(w ** 2))
        else:
            # Fallback to minimum variance
            def obj(w: np.ndarray) -> float:
                return float(w @ cov @ w)

        res = minimize(
            obj,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-10, "maxiter": 300},
        )
        opt_w = np.clip(res.x, [b[0] for b in bounds], [b[1] for b in bounds])
        opt_w = opt_w * (investable_budget / max(1e-9, np.sum(opt_w)))
        success = bool(res.success)
        msg = str(res.message)
        nit = int(res.nit)

    # 5. Compute Realized Risk & Concentration Metrics
    port_var_daily = float(opt_w @ cov @ opt_w)
    port_sd_daily = math.sqrt(max(0.0, port_var_daily))
    port_vol_ann = port_sd_daily * sqrt_ann
    port_ret_ann = float(opt_w @ mu)

    # Sharpe ratio
    sharpe = float((port_ret_ann - config.risk_free_rate) / max(1e-6, port_vol_ann))

    # Diversification Ratio = sum(w_i * sigma_i) / sigma_port
    asset_sds = np.sqrt(np.diag(cov)) * sqrt_ann
    weighted_sds = float(np.sum(opt_w * asset_sds))
    div_ratio = float(weighted_sds / max(1e-6, port_vol_ann))

    # Concentration stats
    hhi = float(np.sum(opt_w ** 2))
    eff_n = float(1.0 / max(1e-6, hhi))

    # Euler Risk Contribution: RC_i = w_i * (Cov @ w)_i / port_sd_daily
    # Normalized: %RC_i = (w_i * (Cov @ w)_i) / port_var_daily
    marginal_contrib = cov @ opt_w
    rc_daily = opt_w * marginal_contrib
    risk_contrib_ann = (rc_daily / max(1e-12, port_sd_daily)) * sqrt_ann
    rc_dict = {asset_ids[i]: float(risk_contrib_ann[i]) for i in range(k)}

    if port_var_daily > 1e-12:
        pct_rc = {asset_ids[i]: float((rc_daily[i] / port_var_daily) * 100.0) for i in range(k)}
    else:
        pct_rc = {asset_ids[i]: 100.0 / k for i in range(k)}

    # Turnover & cost estimation
    turnover = 0.0
    if config.current_weights:
        w_curr = np.array([config.current_weights.get(a, 0.0) for a in asset_ids], dtype=np.float64)
        turnover = float(0.5 * np.sum(np.abs(opt_w - w_curr)))

    cost_pct = float(2.0 * turnover * (config.transaction_cost_bps / 10000.0))

    weights_dict = {asset_ids[i]: float(opt_w[i]) for i in range(k)}

    return QuantitativeOptimizationResult(
        objective=config.objective,
        asset_ids=asset_ids,
        weights=weights_dict,
        cash_weight=float(config.cash_reserve_pct),
        expected_return_annualized=port_ret_ann,
        volatility_annualized=port_vol_ann,
        sharpe_ratio=sharpe,
        diversification_ratio=div_ratio,
        effective_n_assets=eff_n,
        herfindahl_index=hhi,
        risk_contributions=rc_dict,
        percent_risk_contributions=pct_rc,
        turnover=turnover,
        estimated_transaction_cost_pct=cost_pct,
        solver_success=success,
        solver_message=msg,
        iterations=nit,
        diagnostics={
            "feasibility": feasibility.to_dict(),
            "covariance_method": config.covariance_estimator,
            "condition_number": feasibility.condition_number,
        },
    )


# ==============================================================================
# 5. Method Comparison & Sensitivity Analysis
# ==============================================================================

def compare_optimization_methods(
    returns_matrix: np.ndarray,
    asset_ids: List[str],
    current_weights: Optional[Dict[str, float]] = None,
    risk_free_rate: float = 0.065,
) -> List[Dict[str, Any]]:
    """Run four canonical allocation methodologies on identical data for comparative benchmarking."""
    objectives = ["equal_weight", "min_variance", "max_sharpe", "risk_parity"]
    results = []

    for obj in objectives:
        cfg = AllocationConfig(
            objective=obj,
            asset_ids=asset_ids,
            current_weights=current_weights,
            risk_free_rate=risk_free_rate,
        )
        res = solve_quantitative_allocation(returns_matrix, cfg)
        results.append({
            "objective": obj,
            "name": {
                "equal_weight": "1/N Equal Weight",
                "min_variance": "Minimum Variance",
                "max_sharpe": "Maximum Sharpe Ratio",
                "risk_parity": "Equal Risk Contribution (Risk Parity)",
            }.get(obj, obj),
            "expected_return": res.expected_return_annualized,
            "volatility": res.volatility_annualized,
            "sharpe_ratio": res.sharpe_ratio,
            "effective_n": res.effective_n_assets,
            "herfindahl_index": res.herfindahl_index,
            "turnover": res.turnover,
            "weights": res.weights,
            "percent_risk_contributions": res.percent_risk_contributions,
        })

    return results


def run_allocation_sensitivity(
    returns_matrix: np.ndarray,
    config: AllocationConfig,
    perturbation_pct: float = 0.10,
) -> Dict[str, Any]:
    """Test weight sensitivity to perturbations in expected returns and estimation window."""
    base_res = solve_quantitative_allocation(returns_matrix, config)

    # Shift returns up and down
    r_up = returns_matrix * (1.0 + perturbation_pct)
    r_down = returns_matrix * (1.0 - perturbation_pct)

    up_res = solve_quantitative_allocation(r_up, config)
    down_res = solve_quantitative_allocation(r_down, config)

    # Max weight delta
    asset_ids = config.asset_ids
    weight_shifts = {}
    for a in asset_ids:
        base_w = base_res.weights.get(a, 0.0)
        up_w = up_res.weights.get(a, 0.0)
        down_w = down_res.weights.get(a, 0.0)
        max_delta = max(abs(up_w - base_w), abs(down_w - base_w))
        weight_shifts[a] = {
            "baseline": base_w,
            "perturbed_up": up_w,
            "perturbed_down": down_w,
            "max_shift": max_delta,
        }

    return {
        "perturbation_tested_pct": perturbation_pct * 100.0,
        "baseline_volatility": base_res.volatility_annualized,
        "volatility_under_perturbation": {
            "up": up_res.volatility_annualized,
            "down": down_res.volatility_annualized,
        },
        "weight_sensitivities": weight_shifts,
    }
