"""Tests for FragilityShield Page 16: Backtesting Lab."""

import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.backtesting_lab import (
    validate_backtest_setup,
    run_antibias_audit,
    run_trade_ablation_analysis,
    compute_rolling_backtest_analytics,
    save_backtest_configuration,
    duplicate_backtest_configuration,
    list_backtest_configurations,
)
from fragility_engine.strategy_engine import StrategyConfig, load_strategy_candles, simulate_strategy_execution, calculate_strategy_metrics


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_page_16_preflight_validation():
    """Test preflight validation catches invalid parameters and accepts valid configs."""
    candles, _ = load_strategy_candles("RELIANCE")
    val_valid = validate_backtest_setup({
        "symbol": "RELIANCE",
        "strategy_type": "ma_crossover",
        "fast_period": 3,
        "slow_period": 8,
        "transaction_cost_bps": 10.0,
        "slippage_bps": 5.0,
        "execution_delay_bars": 1,
        "train_ratio": 0.70,
    }, candles=candles)
    assert val_valid.is_valid is True
    assert len(val_valid.errors) == 0

    # Invalid: fast >= slow
    val_invalid = validate_backtest_setup({
        "symbol": "RELIANCE",
        "strategy_type": "ma_crossover",
        "fast_period": 50,
        "slow_period": 20,
        "transaction_cost_bps": -5.0,
    }, candles=candles)
    assert val_invalid.is_valid is False
    assert any("Fast period" in e for e in val_invalid.errors)
    assert any("Transaction fee" in e for e in val_invalid.errors)


def test_page_16_antibias_audit():
    """Test 8-point anti-bias diagnostic audit."""
    candles, _ = load_strategy_candles("RELIANCE")
    cfg = StrategyConfig(
        strategy_id="test_bias",
        name="Bias Test",
        strategy_type="ma_crossover",
        symbol="RELIANCE",
        execution_delay_bars=1,
        transaction_cost_bps=10.0,
        fast_period=3,
        slow_period=8,
    )
    sim = simulate_strategy_execution(candles, cfg)
    diagnostics = run_antibias_audit(cfg, candles, sim["trades"], n_oos_eval=5)

    assert len(diagnostics) == 8
    checks = {d.check_id: d for d in diagnostics}
    assert "BIAS_LOOKAHEAD" in checks
    assert checks["BIAS_LOOKAHEAD"].status == "passed"
    assert "BIAS_SURVIVORSHIP" in checks
    assert "BIAS_FRICTIONS" in checks
    assert checks["BIAS_FRICTIONS"].status == "passed"


def test_page_16_trade_ablation_analysis():
    """Test path-dependent re-simulation vs post-hoc trade removal."""
    candles, _ = load_strategy_candles("RELIANCE")
    cfg = StrategyConfig(
        strategy_id="test_abl",
        name="Ablation Test",
        symbol="RELIANCE",
        strategy_type="ma_crossover",
        fast_period=3,
        slow_period=8,
    )
    sim = simulate_strategy_execution(candles, cfg)
    metrics = calculate_strategy_metrics(sim["equity_values"], sim["benchmark_values"], sim["trades"], cfg.initial_capital)

    class DummyObj:
        def __init__(self, trades, m):
            self.trades = trades
            self.metrics = self
            self._m = m
        def to_dict(self):
            return self._m

    base = DummyObj(sim["trades"], metrics)
    abl = run_trade_ablation_analysis(cfg, candles, base, num_top_trades=2)
    assert abl.num_trades_removed == 2
    assert abl.post_hoc_removal is not None
    assert abl.path_dependent_resimulation is not None
    assert len(abl.methodological_disclosure) > 0


def test_page_16_configuration_management():
    """Test saving, listing, and duplicating backtest configurations."""
    cfg_id = save_backtest_configuration({
        "name": "Custom Dual MA 15-45",
        "symbol": "TCS",
        "strategy_type": "ma_crossover",
        "parameters": {"fast_period": 15, "slow_period": 45},
    })
    assert cfg_id.startswith("cfg_")
    
    configs = list_backtest_configurations()
    assert any(c["config_id"] == cfg_id for c in configs)

    dup = duplicate_backtest_configuration(cfg_id, new_name="Cloned Dual MA")
    assert dup["config_id"] != cfg_id
    assert "Cloned Dual MA" in dup["name"]


def test_page_16_api_endpoints(client):
    """Test REST API endpoints for Backtesting Lab."""
    # 1. Validate
    res_val = client.post("/api/backtesting/validate", json={
        "symbol": "RELIANCE",
        "strategy_type": "ma_crossover",
        "fast_period": 3,
        "slow_period": 8,
    })
    assert res_val.status_code == 200
    assert res_val.json()["validation"]["is_valid"] is True

    # 2. Run
    res_run = client.post("/api/backtesting/run", json={
        "symbol": "RELIANCE",
        "strategy_type": "ma_crossover",
        "fast_period": 3,
        "slow_period": 8,
        "initial_capital": 1000000,
    })
    assert res_run.status_code == 200
    data = res_run.json()
    assert data["success"] is True
    assert "anti_bias_diagnostics" in data
    assert "rolling_analytics" in data
    assert len(data["anti_bias_diagnostics"]) == 8

    # 3. Ablation
    res_abl = client.post("/api/backtesting/ablation", json={
        "symbol": "RELIANCE",
        "strategy_type": "ma_crossover",
        "fast_period": 3,
        "slow_period": 8,
        "num_top_trades": 2,
    })
    assert res_abl.status_code == 200
    assert "ablation" in res_abl.json()

    # 4. Configs
    res_cfgs = client.get("/api/backtesting/configs")
    assert res_cfgs.status_code == 200
    assert len(res_cfgs.json()["configs"]) >= 1


def test_page_16_chronological_execution_and_frictions():
    """Verify that transaction fees and slippage strictly reduce net P&L and that trades execute in chronological order."""
    candles, _ = load_strategy_candles("RELIANCE")
    
    # Zero cost vs realistic cost
    cfg_zero = StrategyConfig(
        strategy_id="zero_cost",
        name="Zero Cost",
        strategy_type="ma_crossover",
        symbol="RELIANCE",
        fast_period=3,
        slow_period=8,
        transaction_cost_bps=0.0,
        slippage_bps=0.0,
    )
    cfg_cost = StrategyConfig(
        strategy_id="with_cost",
        name="With Cost",
        strategy_type="ma_crossover",
        symbol="RELIANCE",
        fast_period=3,
        slow_period=8,
        transaction_cost_bps=20.0,
        slippage_bps=10.0,
    )
    
    sim_zero = simulate_strategy_execution(candles, cfg_zero)
    sim_cost = simulate_strategy_execution(candles, cfg_cost)
    
    m_zero = calculate_strategy_metrics(sim_zero["equity_values"], sim_zero["benchmark_values"], sim_zero["trades"], cfg_zero.initial_capital)
    m_cost = calculate_strategy_metrics(sim_cost["equity_values"], sim_cost["benchmark_values"], sim_cost["trades"], cfg_cost.initial_capital)
    
    # Cost should strictly degrade or equal return
    assert m_cost["cumulative_return"] <= m_zero["cumulative_return"]
    
    # Verify chronological order
    for sim in (sim_zero, sim_cost):
        trades = sim["trades"]
        if trades:
            for i in range(len(trades) - 1):
                assert trades[i].exit_date <= trades[i + 1].entry_date


def test_page_16_cash_accounting_and_drawdown():
    """Verify non-negative cash balance invariant and valid drawdown range [0, 1]."""
    candles, _ = load_strategy_candles("RELIANCE")
    cfg = StrategyConfig(
        strategy_id="cash_test",
        name="Cash Accounting Test",
        strategy_type="rsi_momentum",
        symbol="RELIANCE",
        initial_capital=500_000.0,
        rsi_period=7,
        rsi_oversold=35.0,
        rsi_overbought=65.0,
        transaction_cost_bps=15.0,
    )
    sim = simulate_strategy_execution(candles, cfg)
    m = calculate_strategy_metrics(sim["equity_values"], sim["benchmark_values"], sim["trades"], cfg.initial_capital)
    
    # Equity values must be strictly positive
    assert all(v > 0 for v in sim["equity_values"])
    # Max drawdown is expressed as negative percentage [-1.0, 0.0] or absolute <= 1.0
    assert -1.0 <= m["max_drawdown"] <= 0.0 or 0.0 <= abs(m["max_drawdown"]) <= 1.0
    # Profit factor must be positive or finite
    assert m["profit_factor"] >= 0.0


def test_page_16_trade_ledger_integrity():
    """Verify trade ledger records complete audit metadata: timestamps, prices, qty, fees, and P&L."""
    candles, _ = load_strategy_candles("RELIANCE")
    cfg = StrategyConfig(
        strategy_id="ledger_test",
        name="Trade Ledger Test",
        strategy_type="ma_crossover",
        symbol="RELIANCE",
        fast_period=2,
        slow_period=5,
        transaction_cost_bps=12.0,
        slippage_bps=4.0,
    )
    sim = simulate_strategy_execution(candles, cfg)
    trades = sim["trades"]
    
    assert len(trades) > 0
    for tr in trades:
        assert tr.entry_date != ""
        assert tr.exit_date != ""
        assert tr.entry_price > 0
        assert tr.exit_price > 0
        assert tr.quantity > 0
        # Net P&L = Gross P&L - Fees
        assert abs(tr.net_pnl - (tr.gross_pnl - tr.fees)) < 1e-4
