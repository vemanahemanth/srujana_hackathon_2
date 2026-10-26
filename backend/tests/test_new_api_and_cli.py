"""Tests for New REST API Endpoints and CLI Workflows (Blueprint §1-§4, §13, §15)."""

import pytest
from starlette.testclient import TestClient

from backend.app import app
from fragility_engine.cli import main as cli_main


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)


def test_api_projects_lifecycle(api_client: TestClient) -> None:
    # 1. List initially
    resp = api_client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 2. Create new project
    create_payload = {
        "project_id": "test_proj_api_01",
        "name": "API Automated Test Project",
        "description": "Integration testing API endpoints",
        "objective": "Verify Lab 1-13 capabilities",
        "asset_universe": ["NIFTY_50"],
        "model_type": "portfolio",
    }
    resp = api_client.post("/api/projects", json=create_payload)
    assert resp.status_code == 201
    assert resp.json()["project"]["project_id"] == "test_proj_api_01"

    # 3. List should include new project
    resp = api_client.get("/api/projects")
    projs = resp.json()["projects"]
    assert any(p["project_id"] == "test_proj_api_01" for p in projs)


def test_api_datasets_lifecycle(api_client: TestClient) -> None:
    reg_payload = {
        "dataset_id": "dset_test_01",
        "name": "Nifty 50 Sample Returns",
        "version": "1.0.0",
        "row_count": 500,
        "frequency": "1D",
        "currency": "INR",
    }
    resp = api_client.post("/api/datasets", json=reg_payload)
    assert resp.status_code == 201
    assert resp.json()["dataset"]["dataset_id"] == "dset_test_01"

    resp = api_client.get("/api/datasets")
    assert resp.status_code == 200
    assert any(d["dataset_id"] == "dset_test_01" for d in resp.json()["datasets"])


def test_api_data_validation_endpoints(api_client: TestClient) -> None:
    # 1. OHLCV validation
    ohlcv_data = [
        {"timestamp": "2026-01-01", "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 5000},
        {"timestamp": "2026-01-02", "open": 102.0, "high": 108.0, "low": 101.0, "close": 107.0, "volume": 7500},
    ]
    resp = api_client.post("/api/data/validate-ohlcv", json={"data": ohlcv_data})
    assert resp.status_code == 200
    assert resp.json()["report"]["is_valid"] is True
    assert resp.json()["report"]["total_candles"] == 2

    # 2. Tabular validation
    tab_data = [
        {"feature_a": 1.2, "feature_b": 3.4, "target": 1},
        {"feature_a": 2.1, "feature_b": 4.5, "target": 0},
    ]
    resp = api_client.post(
        "/api/data/validate-tabular",
        json={"data": tab_data, "required_columns": ["feature_a", "feature_b", "target"]},
    )
    assert resp.status_code == 200
    assert resp.json()["report"]["is_schema_valid"] is True

    # 3. Outlier audit
    series = [10.0, 11.0, 10.5, 9.8, 10.2, 55.0]  # 55.0 is an outlier
    resp = api_client.post("/api/data/audit-outliers", json={"series": series, "z_threshold": 2.0})
    assert resp.status_code == 200
    assert resp.json()["report"]["zscore_outliers_count"] >= 1

    # 4. Drift detection
    ref = [1.0, 2.0, 1.5, 1.8, 2.2, 1.9]
    cur = [1.1, 2.1, 1.4, 1.9, 2.0, 1.8]
    resp = api_client.post("/api/data/detect-drift", json={"reference_series": ref, "current_series": cur})
    assert resp.status_code == 200
    assert resp.json()["report"]["has_drifted"] is False


def test_api_models_manifests_and_capabilities(api_client: TestClient) -> None:
    manifest_payload = {
        "model_id": "test_risk_model_api",
        "name": "API Test Risk Model",
        "version": "1.0.0",
        "model_family": "risk_estimator",
        "required_inputs": ["returns"],
        "supported_labs": ["risk", "fragility"],
        "supported_tests": ["historical_var"],
        "is_deterministic": True,
        "code_isolation_required": False,
    }
    resp = api_client.post("/api/models/manifests", json=manifest_payload)
    assert resp.status_code == 201
    assert resp.json()["model"]["model_id"] == "test_risk_model_api"

    # Capability check
    resp = api_client.post(
        "/api/models/check-capabilities",
        json={"manifest": manifest_payload, "target_lab": "risk", "test_name": "historical_var"},
    )
    assert resp.status_code == 200
    rep = resp.json()["report"]
    assert rep["is_executable"] is True
    assert rep["capabilities"]["Input schema"]["status"] == "Compatible"


def test_api_reverse_stress_and_boundary_search(api_client: TestClient) -> None:
    # 1. Reverse stress test
    rev_payload = {
        "target_loss_pct": 0.10,
        "shock_target": "market",
    }
    resp = api_client.post("/api/scenarios/reverse-stress", json=rev_payload)
    assert resp.status_code == 200
    assert resp.json()["reverse_stress"]["feasible"] is True
    assert resp.json()["reverse_stress"]["required_shock_pct"] == -0.10

    # 2. Stress-boundary search
    daily_returns = [0.002, 0.001, 0.0015, -0.0005, 0.0012, 0.0018]
    bound_payload = {
        "returns": daily_returns,
        "target_metric": "sharpe_ratio",
        "failure_threshold": 0.0,
        "attack_type": "transaction_friction",
    }
    resp = api_client.post("/api/fragility/search-boundary", json=bound_payload)
    assert resp.status_code == 200
    assert resp.json()["boundary_search"]["converged"] is True


def test_cli_new_commands(capsys: pytest.CaptureFixture[str]) -> None:
    # 1. Project create & list
    code = cli_main(["project", "create", "--id", "cli_proj_01", "--name", "CLI Project", "--objective", "CLI Test"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Project created successfully" in out

    code = cli_main(["project", "list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "cli_proj_01" in out

    # 2. Reverse stress command
    code = cli_main([
        "scenario", "reverse-stress",
        "--portfolio", "data/sample_portfolios/nse_10l.json",
        "--target-loss", "0.10",
        "--target-type", "market",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Reverse Stress Test" in out
    assert "Required Shock:      -10.00%" in out


def test_api_allocation_endpoints(api_client: TestClient) -> None:
    # 1. Optimize minimum variance
    opt_payload = {
        "covariance_matrix": [
            [0.0004, 0.0001],
            [0.0001, 0.0009],
        ],
        "asset_ids": ["NSE:HDFCBANK", "NSE:TCS"],
        "min_weight": 0.0,
        "max_weight": 1.0,
    }
    resp = api_client.post("/api/allocation/optimize", json=opt_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "weights" in data
    assert pytest.approx(sum(data["weights"].values()), abs=1e-4) == 1.0
    assert data["data_provenance"]["data_source_mode"] == "USER_UPLOADED_DATA"

    # 2. Compare allocations
    comp_payload = {
        "original_portfolio": {
            "portfolio_id": "port_orig",
            "name": "Orig",
            "currency": "INR",
            "holdings": [
                {"asset_id": "NSE:HDFCBANK", "quantity": 100, "price": 1500, "sector": "Banking"},
                {"asset_id": "NSE:TCS", "quantity": 50, "price": 3000, "sector": "IT"},
            ],
        },
        "adjusted_portfolio": {
            "portfolio_id": "port_adj",
            "name": "Adj",
            "currency": "INR",
            "holdings": [
                {"asset_id": "NSE:HDFCBANK", "quantity": 120, "price": 1500, "sector": "Banking"},
                {"asset_id": "NSE:TCS", "quantity": 40, "price": 3000, "sector": "IT"},
            ],
        },
    }
    resp = api_client.post("/api/allocation/compare", json=comp_payload)
    assert resp.status_code == 200
    comp_data = resp.json()
    assert comp_data["success"] is True
    assert "comparison" in comp_data
    assert comp_data["comparison"]["turnover"] > 0.0


def test_api_ml_endpoints(api_client: TestClient) -> None:
    # 1. Evaluate regression
    reg_payload = {
        "task_type": "regression",
        "y_true": [2.0, 4.0, 6.0, 8.0],
        "y_pred": [2.5, 3.5, 6.0, 9.0],
    }
    resp = api_client.post("/api/ml/evaluate", json=reg_payload)
    assert resp.status_code == 200
    reg_data = resp.json()
    assert reg_data["success"] is True
    assert reg_data["metrics"]["mae"] == 0.50
    assert reg_data["data_provenance"]["data_source_mode"] == "USER_UPLOADED_DATA"

    # 2. Evaluate classification
    cls_payload = {
        "task_type": "classification",
        "y_true": [1, 1, 0, 0, 1],
        "y_pred": [1, 0, 0, 0, 1],
        "y_prob": [0.9, 0.4, 0.1, 0.2, 0.8],
    }
    resp = api_client.post("/api/ml/evaluate", json=cls_payload)
    assert resp.status_code == 200
    cls_data = resp.json()
    assert cls_data["success"] is True
    assert cls_data["metrics"]["accuracy"] == 0.80

    # 3. Chronological split
    split_payload = {
        "X": [[float(i), float(i * 2)] for i in range(10)],
        "y": [float(i * 10) for i in range(10)],
        "train_ratio": 0.70,
    }
    resp = api_client.post("/api/ml/split", json=split_payload)
    assert resp.status_code == 200
    split_data = resp.json()
    assert split_data["success"] is True
    assert split_data["train_size"] == 7
    assert split_data["test_size"] == 3

