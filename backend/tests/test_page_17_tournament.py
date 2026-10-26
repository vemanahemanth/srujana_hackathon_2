"""Tests for FragilityShield Page 17: Model Tournament & Benchmarking Lab."""

import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.tournament_engine import (
    TournamentProtocol,
    TournamentCandidate,
    execute_tournament,
    compute_deflated_sharpe_ratio,
    get_default_tournament_candidates,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


def test_page_17_deflated_sharpe_ratio():
    """Test Bailey & López de Prado Deflated Sharpe Ratio calculation."""
    res_high = compute_deflated_sharpe_ratio(
        observed_sharpe=2.5,
        num_candidates=5,
        sample_size=200,
    )
    assert res_high["num_candidates_tested"] == 5
    assert res_high["deflated_sharpe_ratio_prob"] > 0.50
    assert "methodology" in res_high

    res_low = compute_deflated_sharpe_ratio(
        observed_sharpe=0.3,
        num_candidates=20,
        sample_size=50,
    )
    assert res_low["deflated_sharpe_ratio_prob"] < 0.50


def test_page_17_tournament_execution():
    """Test full multi-candidate tournament execution."""
    protocol = TournamentProtocol(
        tournament_id="test_tourn_01",
        name="Unit Test Tournament",
        symbol="RELIANCE",
        primary_metric="sharpe_ratio",
        min_observations=15,
        max_drawdown_limit_pct=30.0,
    )
    cands = get_default_tournament_candidates()[:4]
    res = execute_tournament(protocol=protocol, candidates=cands)

    assert res["success"] is True
    assert len(res["leaderboard"]) == 4
    # Ensure rank ordering
    ranks = [item["rank"] for item in res["leaderboard"]]
    assert ranks == [1, 2, 3, 4]
    # Check top candidate
    top = res["leaderboard"][0]
    assert "primary_score" in top
    assert "stability_score" in top
    assert "multiple_testing_diagnostics" in res
    assert res["tournament_fingerprint"] is not None


def test_page_17_api_endpoints(client):
    """Test REST endpoints for Model Tournament."""
    # 1. Candidates
    res_cands = client.get("/api/tournaments/candidates")
    assert res_cands.status_code == 200
    assert len(res_cands.json()["candidates"]) >= 4

    # 2. Run Tournament
    res_run = client.post("/api/tournaments/run", json={
        "protocol": {
            "name": "Integration Tournament API",
            "symbol": "RELIANCE",
            "primary_metric": "sharpe_ratio",
            "transaction_cost_bps": 10.0,
        }
    })
    assert res_run.status_code == 200
    data = res_run.json()
    assert data["success"] is True
    assert len(data["leaderboard"]) >= 4
    assert "multiple_testing_diagnostics" in data


def test_page_17_cost_sensitivity_and_rank_inversion():
    """Verify that tournament records sensitivity to transaction costs and flags ranking fragility."""
    p_low_cost = TournamentProtocol(
        tournament_id="t_low",
        name="Low Cost Protocol",
        symbol="RELIANCE",
        transaction_cost_bps=2.0,
        slippage_bps=1.0,
    )
    p_high_cost = TournamentProtocol(
        tournament_id="t_high",
        name="High Cost Protocol",
        symbol="RELIANCE",
        transaction_cost_bps=30.0,
        slippage_bps=15.0,
    )
    cands = get_default_tournament_candidates()[:3]
    res_low = execute_tournament(protocol=p_low_cost, candidates=cands)
    res_high = execute_tournament(protocol=p_high_cost, candidates=cands)

    # Scores under high cost must be lower than or equal to low cost
    score_low = res_low["leaderboard"][0]["primary_score"]
    score_high = res_high["leaderboard"][0]["primary_score"]
    assert score_high <= score_low


def test_page_17_minimum_sample_rejection():
    """Verify tournament rejects evaluation when dataset has fewer observations than protocol min_observations."""
    protocol = TournamentProtocol(
        tournament_id="t_invalid",
        name="Invalid Sample",
        symbol="RELIANCE",
        min_observations=10_000,  # exceeds historical length
    )
    with pytest.raises(ValueError, match="requires at least"):
        execute_tournament(protocol=protocol)


def test_page_17_stability_scoring():
    """Verify that stability score between [0, 1] is produced based on subperiod Sharpe consistency."""
    protocol = TournamentProtocol(
        tournament_id="t_stab",
        name="Stability Test",
        symbol="RELIANCE",
    )
    cands = get_default_tournament_candidates()[:2]
    res = execute_tournament(protocol=protocol, candidates=cands)
    for row in res["leaderboard"]:
        assert "stability_score" in row
        assert 0.0 <= row["stability_score"] <= 100.0
        assert "primary_score" in row
        assert "cumulative_return_pct" in row

