"""Unit tests for FragilityShield Python SDK and CLI."""

from __future__ import annotations

import io
import sys
from typing import List
import numpy as np
import pytest

from fragility_engine.cli import main as cli_main
from fragility_engine.models import Holding, Portfolio
from fragility_engine.sdk import Client


@pytest.fixture
def sample_client() -> Client:
    """Fixture providing an instantiated FragilityShield Client."""
    return Client()


@pytest.fixture
def sample_portfolio_holdings() -> list[Holding]:
    """Two-asset portfolio holdings."""
    return [
        Holding("INFY", 50.0, 1600.0, "Information Technology"),
        Holding("HDFCBANK", 50.0, 1600.0, "Banking"),
    ]


@pytest.fixture
def sample_returns() -> list[float]:
    """Synthetic returns series."""
    return [
        0.012, -0.015, 0.008, 0.018, -0.022,
        0.005, -0.009, 0.011, -0.035, 0.014,
        -0.011, 0.017, -0.004, 0.003, -0.010,
        0.019, -0.006, 0.002, -0.014, 0.009,
    ]


def test_sdk_portfolio_lifecycle(sample_client: Client, sample_portfolio_holdings: list[Holding]) -> None:
    p = sample_client.portfolios.create(
        portfolio_id="sdk_p1",
        name="SDK Test Port",
        currency="INR",
        holdings=sample_portfolio_holdings,
    )
    assert p.portfolio_id == "sdk_p1"
    assert p.total_valuation() == 160_000.0

    retrieved = sample_client.portfolios.get("sdk_p1")
    assert retrieved == p
    assert len(sample_client.portfolios.list()) == 1


def test_sdk_risk_calculations(sample_client: Client, sample_returns: list[float]) -> None:
    rep = sample_client.risk.calculate(sample_returns)
    assert rep.volatility_annualized > 0.0
    assert rep.var_95 > 0.0

    roll_vol = sample_client.risk.rolling_volatility(sample_returns, window=10)
    assert len(roll_vol) == len(sample_returns) - 10 + 1

    sharpe = sample_client.risk.sharpe_ratio(sample_returns)
    assert isinstance(sharpe, float)

    sortino = sample_client.risk.sortino_ratio(sample_returns)
    assert isinstance(sortino, float)


def test_sdk_scenario_execution(sample_client: Client, sample_portfolio_holdings: list[Holding]) -> None:
    p = sample_client.portfolios.create("p_scen", "Scenario Port", "INR", holdings=sample_portfolio_holdings)
    presets = sample_client.scenarios.list_presets()
    assert len(presets) >= 4

    res = sample_client.scenarios.execute_preset(p, "banking_minus_20_it_minus_10")
    # INFY is IT (-10%), HDFCBANK is Banking (-20%)
    # Equal 50% weights: 0.50 * -0.10 + 0.50 * -0.20 = -0.15 (-15%)
    assert res.percentage_change == pytest.approx(-0.15, abs=1e-5)
    assert res.stressed_value < res.baseline_value


def test_sdk_fragility_audit(sample_client: Client, sample_returns: list[float]) -> None:
    audit = sample_client.fragility.run_audit(sample_returns, target_metric="volatility_annualized")
    assert audit.audit_id == "audit_sdk"
    assert len(audit.experiments) == 5
    assert audit.sensitivity_ranking.most_sensitive_perturbation is not None


def test_sdk_allocation_and_optimization(sample_client: Client, sample_portfolio_holdings: list[Holding]) -> None:
    p = sample_client.portfolios.create("p_alloc", "Alloc Port", "INR", holdings=sample_portfolio_holdings)
    eq_port = sample_client.allocation.create_equal_weighted(p)
    assert eq_port.total_valuation() == p.total_valuation()

    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    opt = sample_client.allocation.optimize_minimum_variance(cov, ["A", "B"])
    assert opt.weights["A"] > opt.weights["B"]  # lower variance asset gets higher weight


def test_sdk_validation_suites(sample_client: Client, sample_portfolio_holdings: list[Holding]) -> None:
    ref_rep = sample_client.validation.run_reference_values()
    assert ref_rep.passed is True

    p = sample_client.portfolios.create("p_val", "Val Port", "INR", holdings=sample_portfolio_holdings)
    cons_rep = sample_client.validation.run_portfolio_consistency(p)
    assert cons_rep.passed is True


def test_sdk_ml_evaluation(sample_client: Client) -> None:
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred = np.array([11.0, 19.0, 31.0, 39.0])
    reg_metrics = sample_client.ml.evaluate_regression(y_true, y_pred)
    assert reg_metrics.mae == pytest.approx(1.0)


def test_sdk_market_data_charges(sample_client: Client) -> None:
    charges = sample_client.market_data.transaction_charges(
        order_type="delivery_equity",
        price=1000.0,
        quantity=100.0,
    )
    assert charges["turnover"] == 100_000.0
    assert charges["total_charges"] > 0.0


def test_cli_risk_calculation(capsys: pytest.CaptureFixture[str]) -> None:
    returns_arg = "0.01,-0.02,0.015,-0.005,0.02"
    ret_code = cli_main(["risk", "--returns", returns_arg])
    assert ret_code == 0
    captured = capsys.readouterr()
    assert "FragilityShield Risk Report" in captured.out
    assert "Annualized Volatility" in captured.out


def test_cli_fragility_audit(capsys: pytest.CaptureFixture[str]) -> None:
    returns_arg = "0.01,-0.02,0.015,-0.005,0.02,0.01,-0.01,0.005,-0.015,0.02"
    ret_code = cli_main(["fragility", "--returns", returns_arg])
    assert ret_code == 0
    captured = capsys.readouterr()
    assert "Assumption Audit Report" in captured.out
    assert "Ranked Sensitivities" in captured.out


def test_cli_validation_reference(capsys: pytest.CaptureFixture[str]) -> None:
    ret_code = cli_main(["validation", "reference"])
    assert ret_code == 0
    captured = capsys.readouterr()
    assert "Reference Value Validation Suite" in captured.out
    assert "PASS" in captured.out


def test_cli_plugins_list(capsys: pytest.CaptureFixture[str]) -> None:
    ret_code = cli_main(["plugins", "list"])
    assert ret_code == 0
    captured = capsys.readouterr()
    assert "Registered FragilityShield Plugins" in captured.out


def test_cli_charges(capsys: pytest.CaptureFixture[str]) -> None:
    ret_code = cli_main(["charges", "--order-type", "delivery_equity", "--price", "1000", "--quantity", "50"])
    assert ret_code == 0
    captured = capsys.readouterr()
    assert "Indian Statutory Transaction Charges" in captured.out
    assert "Turnover:           50,000.00" in captured.out
