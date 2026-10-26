"""FragilityShield — Page 17: Model Tournament & Benchmarking Engine.

Implements fair, auditable tournament evaluation across quantitative models and trading
strategies under a shared evaluation protocol, common transaction costs, multi-testing bias
corrections (Deflated Sharpe Ratio / Bonferroni), and rank stability analysis.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
import scipy.stats as stats

from fragility_engine.strategy_engine import (
    StrategyConfig,
    simulate_strategy_execution,
    calculate_strategy_metrics,
    load_strategy_candles,
    list_default_strategy_templates,
)
from fragility_engine.reproducibility import compute_canonical_hash


@dataclass
class TournamentCandidate:
    """Specification of an individual tournament participant."""

    candidate_id: str
    name: str
    candidate_type: str  # 'strategy' or 'risk_model'
    strategy_type: str = "ma_crossover"
    parameters: Dict[str, Any] = field(default_factory=dict)
    family: str = "Trend Following"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "name": self.name,
            "candidate_type": self.candidate_type,
            "strategy_type": self.strategy_type,
            "parameters": self.parameters,
            "family": self.family,
        }


@dataclass
class TournamentProtocol:
    """Explicit, inspectable tournament evaluation protocol."""

    tournament_id: str
    name: str
    symbol: str = "RELIANCE"
    benchmark_symbol: str = "NIFTY 50"
    primary_metric: str = "sharpe_ratio"  # 'sharpe_ratio', 'cumulative_return', 'calmar_ratio', 'sortino_ratio'
    secondary_metrics: List[str] = field(default_factory=lambda: ["cumulative_return", "annualized_volatility", "max_drawdown", "win_rate"])
    transaction_cost_bps: float = 10.0
    slippage_bps: float = 5.0
    max_drawdown_limit_pct: float = 25.0
    min_observations: int = 15
    tie_breaker: str = "lowest_max_drawdown"
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tournament_id": self.tournament_id,
            "name": self.name,
            "symbol": self.symbol,
            "benchmark_symbol": self.benchmark_symbol,
            "primary_metric": self.primary_metric,
            "secondary_metrics": self.secondary_metrics,
            "transaction_cost_bps": self.transaction_cost_bps,
            "slippage_bps": self.slippage_bps,
            "max_drawdown_limit_pct": self.max_drawdown_limit_pct,
            "min_observations": self.min_observations,
            "tie_breaker": self.tie_breaker,
            "version": self.version,
        }


def get_default_tournament_candidates() -> List[TournamentCandidate]:
    """Default verified candidate roster for the Model Tournament."""
    return [
        TournamentCandidate(
            candidate_id="cand_ma_crossover_fast",
            name="MA Crossover Aggressive (10/30)",
            candidate_type="strategy",
            strategy_type="ma_crossover",
            parameters={"fast_period": 10, "slow_period": 30, "stop_loss_pct": 3.0},
            family="Trend Following",
        ),
        TournamentCandidate(
            candidate_id="cand_ma_crossover_standard",
            name="Dual MA Crossover Standard (20/50)",
            candidate_type="strategy",
            strategy_type="ma_crossover",
            parameters={"fast_period": 20, "slow_period": 50, "stop_loss_pct": 3.5},
            family="Trend Following",
        ),
        TournamentCandidate(
            candidate_id="cand_rsi_momentum",
            name="RSI Momentum Reversal (14 / 30-70)",
            candidate_type="strategy",
            strategy_type="rsi_momentum",
            parameters={"rsi_period": 14, "rsi_oversold": 30.0, "rsi_overbought": 70.0, "stop_loss_pct": 4.0},
            family="Momentum",
        ),
        TournamentCandidate(
            candidate_id="cand_bollinger_mean_revert",
            name="Bollinger Band Mean Reversion (20 / 2.0)",
            candidate_type="strategy",
            strategy_type="bollinger_reversion",
            parameters={"bollinger_period": 20, "bollinger_std": 2.0, "stop_loss_pct": 3.0},
            family="Mean Reversion",
        ),
        TournamentCandidate(
            candidate_id="cand_vol_target",
            name="Volatility-Targeted Asset Allocator (15% Vol)",
            candidate_type="strategy",
            strategy_type="vol_target",
            parameters={"target_vol": 0.15, "stop_loss_pct": 5.0},
            family="Risk Managed",
        ),
        TournamentCandidate(
            candidate_id="cand_buy_and_hold",
            name="Passive Benchmark Buy & Hold Baseline",
            candidate_type="strategy",
            strategy_type="buy_and_hold",
            parameters={},
            family="Benchmark Passive",
        ),
    ]


def compute_deflated_sharpe_ratio(
    observed_sharpe: float,
    num_candidates: int,
    sample_size: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> Dict[str, Any]:
    """Compute Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) diagnostic.
    
    Adjusts standard Sharpe for multiple testing selection bias across N candidates.
    """
    n = max(sample_size, 10)
    k = max(num_candidates, 1)

    # Expected maximum Sharpe of K uncorrelated standard normals
    euler_mascheroni = 0.5772156649
    if k > 1:
        ln_k = math.log(k)
        term1 = math.sqrt(2.0 * ln_k)
        term2 = (euler_mascheroni / math.sqrt(2.0 * ln_k)) if ln_k > 0 else 0.0
        expected_max_sr = term1 + term2
    else:
        expected_max_sr = 0.0

    # Variance of Sharpe ratio estimator under non-normality (Mertens 2002)
    sr = observed_sharpe
    var_sr = (1.0 + 0.5 * (sr ** 2) - skewness * sr + ((kurtosis - 3.0) / 4.0) * (sr ** 2)) / n
    std_sr = math.sqrt(max(var_sr, 1e-6))

    # Standardized test statistic
    z_stat = (sr - expected_max_sr) / std_sr if std_sr > 0 else 0.0
    dsr_prob = float(stats.norm.cdf(z_stat))

    # Bonferroni multiple testing correction on p-value
    nominal_p = float(1.0 - stats.norm.cdf(sr * math.sqrt(n))) if std_sr > 0 else 1.0
    bonferroni_p = min(1.0, nominal_p * k)

    return {
        "observed_sharpe": round(observed_sharpe, 3),
        "num_candidates_tested": k,
        "sample_size": n,
        "expected_max_sharpe_null": round(expected_max_sr, 3),
        "deflated_sharpe_ratio_prob": round(dsr_prob, 4),
        "bonferroni_adjusted_p_value": round(bonferroni_p, 5),
        "selection_bias_verdict": "SIGNIFICANT_SKILL" if dsr_prob >= 0.95 else ("BORDERLINE" if dsr_prob >= 0.80 else "POTENTIAL_OVERFIT"),
        "methodology": "Bailey & López de Prado (2014) Deflated Sharpe Ratio with Bonferroni multiple testing adjustment",
    }


def execute_tournament(
    protocol: TournamentProtocol,
    candidates: Optional[List[TournamentCandidate]] = None,
    candles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute multi-candidate tournament under common protocol and shared observation window."""
    if candidates is None:
        candidates = get_default_tournament_candidates()

    if candles is None or len(candles) < protocol.min_observations:
        candles, _ = load_strategy_candles(protocol.symbol)

    n_sessions = len(candles)
    if n_sessions < protocol.min_observations:
        raise ValueError(f"Dataset has {n_sessions} observations, but tournament protocol requires at least {protocol.min_observations}.")

    dates = [str(c["timestamp"]).split("T")[0] for c in candles]
    shared_window = {"start": dates[0], "end": dates[-1], "total_sessions": n_sessions}

    # Evaluate all candidates over identical candles
    leaderboard = []
    sharpe_scores = []

    for cand in candidates:
        cfg = StrategyConfig(
            strategy_id=cand.candidate_id,
            name=cand.name,
            strategy_type=cand.strategy_type,
            symbol=protocol.symbol,
            benchmark_symbol=protocol.benchmark_symbol,
            family=cand.family,
            transaction_cost_bps=protocol.transaction_cost_bps,
            slippage_bps=protocol.slippage_bps,
            fast_period=int(cand.parameters.get("fast_period", 20)),
            slow_period=int(cand.parameters.get("slow_period", 50)),
            rsi_period=int(cand.parameters.get("rsi_period", 14)),
            rsi_oversold=float(cand.parameters.get("rsi_oversold", 30.0)),
            rsi_overbought=float(cand.parameters.get("rsi_overbought", 70.0)),
            bollinger_period=int(cand.parameters.get("bollinger_period", 20)),
            bollinger_std=float(cand.parameters.get("bollinger_std", 2.0)),
            target_vol=float(cand.parameters.get("target_vol", 0.15)),
            stop_loss_pct=float(cand.parameters.get("stop_loss_pct", 3.5)) if cand.parameters.get("stop_loss_pct") else None,
        )

        try:
            sim = simulate_strategy_execution(candles, cfg)
            m = calculate_strategy_metrics(
                sim["equity_values"],
                sim["benchmark_values"],
                sim["trades"],
                cfg.initial_capital,
                cfg.risk_free_rate,
            )

            # Subperiod stability check: split in half and evaluate Sharpe drift
            mid = n_sessions // 2
            sim_h1 = simulate_strategy_execution(candles[:mid], cfg)
            sim_h2 = simulate_strategy_execution(candles[mid:], cfg)
            m_h1 = calculate_strategy_metrics(sim_h1["equity_values"], sim_h1["benchmark_values"], sim_h1["trades"], cfg.initial_capital)
            m_h2 = calculate_strategy_metrics(sim_h2["equity_values"], sim_h2["benchmark_values"], sim_h2["trades"], cfg.initial_capital)

            sr1 = m_h1.get("sharpe_ratio", 0.0)
            sr2 = m_h2.get("sharpe_ratio", 0.0)
            sharpe_diff = abs(sr2 - sr1)
            # Stability score 0-100: penalize large divergence between halves
            stability_score = max(0.0, min(100.0, 100.0 - (sharpe_diff * 35.0)))

            # Observations, trading activity, and risk limits check
            max_dd_pct = abs(m.get("max_drawdown", 0.0)) * 100.0
            total_trades = m.get("total_trades", 0)

            if n_sessions < protocol.min_observations:
                status = "INSUFFICIENT_OBSERVATIONS"
                disqualification_reason = f"Candidate evaluated on {n_sessions} sessions, below protocol minimum of {protocol.min_observations}."
            elif total_trades == 0:
                status = "ZERO_TRADES_INACTIVE"
                disqualification_reason = "No trades executed during the evaluation horizon; strategy remained inactive."
            elif max_dd_pct > protocol.max_drawdown_limit_pct:
                status = "RISK_LIMIT_BREACHED"
                disqualification_reason = f"Max drawdown ({max_dd_pct:.1f}%) exceeds protocol limit of {protocol.max_drawdown_limit_pct}%."
            else:
                status = "QUALIFIED"
                disqualification_reason = ""

            primary_val = m.get(protocol.primary_metric, 0.0)
            sharpe_scores.append(m.get("sharpe_ratio", 0.0))

            leaderboard.append({
                "candidate_id": cand.candidate_id,
                "name": cand.name,
                "family": cand.family,
                "candidate_type": cand.candidate_type,
                "status": status,
                "disqualification_reason": disqualification_reason,
                "primary_metric_name": protocol.primary_metric,
                "primary_score": round(primary_val, 4),
                "cumulative_return_pct": round(m.get("cumulative_return", 0.0) * 100.0, 2),
                "annualized_return_pct": round(m.get("cagr", 0.0) * 100.0, 2),
                "annualized_volatility_pct": round(m.get("annualized_volatility", 0.0) * 100.0, 2),
                "sharpe_ratio": round(m.get("sharpe_ratio", 0.0), 3),
                "sortino_ratio": round(m.get("sortino_ratio", 0.0), 3),
                "max_drawdown_pct": round(max_dd_pct, 2),
                "win_rate_pct": round(m.get("win_rate", 0.0) * 100.0, 1),
                "total_trades": m.get("total_trades", 0),
                "profit_factor": round(m.get("profit_factor", 0.0), 2),
                "stability_score": round(stability_score, 1),
                "equity_final": sim["final_equity"],
                "equity_curve_sample": [
                    {"date": e["date"], "equity": e["equity"]}
                    for e in sim["equity_curve"][::max(1, len(sim["equity_curve"]) // 20)]
                ],
            })
        except Exception as exc:
            leaderboard.append({
                "candidate_id": cand.candidate_id,
                "name": cand.name,
                "family": cand.family,
                "candidate_type": cand.candidate_type,
                "status": "FAILED",
                "disqualification_reason": f"Execution error: {str(exc)}",
                "primary_metric_name": protocol.primary_metric,
                "primary_score": -999.0,
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "annualized_volatility_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate_pct": 0.0,
                "total_trades": 0,
                "profit_factor": 0.0,
                "stability_score": 0.0,
                "equity_final": 0.0,
                "equity_curve_sample": [],
            })

    # Sort leaderboard by qualification, then primary score descending, tiebreaker by lowest max drawdown
    def sort_key(item: Dict[str, Any]) -> Tuple[int, float, float]:
        qual_rank = 0 if item["status"] == "QUALIFIED" else 1
        return (qual_rank, -item["primary_score"], item["max_drawdown_pct"])

    leaderboard.sort(key=sort_key)
    for rank_idx, item in enumerate(leaderboard, 1):
        item["rank"] = rank_idx

    # Multiple testing analysis for qualified champion
    qualified_candidates = [c for c in leaderboard if c.get("status") == "QUALIFIED"]
    has_qualified = len(qualified_candidates) > 0
    champion = qualified_candidates[0] if has_qualified else None
    top_sharpe = champion.get("sharpe_ratio", 0.0) if champion else 0.0

    multiple_testing_diag = compute_deflated_sharpe_ratio(
        observed_sharpe=top_sharpe,
        num_candidates=len(candidates),
        sample_size=n_sessions,
    )

    fingerprint_payload = {
        "protocol": protocol.to_dict(),
        "n_candidates": len(candidates),
        "shared_window": shared_window,
        "winner_id": champion.get("candidate_id") if champion else None,
        "has_qualified_winner": has_qualified,
    }
    tournament_fingerprint = compute_canonical_hash(fingerprint_payload)

    return {
        "success": True,
        "tournament_id": protocol.tournament_id,
        "name": protocol.name,
        "run_timestamp": datetime.now().isoformat(),
        "protocol": protocol.to_dict(),
        "shared_window": shared_window,
        "champion": champion,
        "has_qualified_champion": has_qualified,
        "leaderboard": leaderboard,
        "multiple_testing_diagnostics": multiple_testing_diag,
        "tournament_fingerprint": tournament_fingerprint,
        "data_provenance": {
            "source": "Upstox V3 Market Data",
            "symbol": protocol.symbol,
            "benchmark_symbol": protocol.benchmark_symbol,
            "sessions_evaluated": n_sessions,
            "zero_synthetic_data": True,
        },
    }
