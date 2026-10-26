"""Integration and Contract Tests for Sprint 9 Extension: Universal External Connectivity.

Verifies all 8 requirements specified in Section 8:
1. Starts with a clearly identified test workspace and test model.
2. Registers the model through the actual SDK or REST API.
3. Submits an actual test execution and its results.
4. Validates the received schema and independent metric re-computations.
5. Persists the execution and provenance.
6. Verifies that the corresponding dashboard data source returns the submitted results.
7. Confirms that invalid or unauthorized submissions are rejected.
8. Confirms that a failed processing job is not presented as completed.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.app import app
from fragility_engine.external_connectivity import (
    MAX_ARTIFACT_FILE_BYTES,
    MAX_INGESTION_PAYLOAD_BYTES,
    ArtifactValidationError,
    ExecutionEnvironment,
    ExternalArtifactRef,
    ExternalIngestionEngine,
    ExternalMetric,
    ExternalPrediction,
    ExternalRunSubmission,
    SchemaValidationError,
    get_ingestion_engine,
)
from fragility_engine.projects import ModelFamily
from fragility_engine.sdk import Client


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Starlette test client initialized against main application."""
    return TestClient(app)


@pytest.fixture
def test_workspace_id() -> str:
    """Requirement 1: Clearly identified test workspace."""
    return f"ws_test_sprint9_{int(time.time()*1000)}"


@pytest.fixture
def test_model_id() -> str:
    """Requirement 1: Clearly identified test model."""
    return f"model_nifty_gbm_{int(time.time()*1000)}"


# ==============================================================================
# Requirement 1 & 2: Test Workspace, Test Model, and Model Registration
# ==============================================================================

def test_req1_and_req2_register_model_and_dataset(test_workspace_id: str, test_model_id: str) -> None:
    """Requirement 1 & 2: Starts with test workspace & registers model via actual SDK."""
    sdk_client = Client(workspace_id=test_workspace_id, environment_type="jupyter_notebook")

    # Register Model Manifest
    manifest = sdk_client.external.register_model(
        model_id=test_model_id,
        name="NSE Nifty Gradient Boosting Machine",
        family=ModelFamily.REGRESSION_MODEL,
        version="2.1.0",
        author="quant_test_suite",
        description="Daily return direction and volatility forecast on NSE Nifty 50 constituents.",
    )

    assert manifest.model_id == test_model_id
    assert manifest.name == "NSE Nifty Gradient Boosting Machine"
    assert manifest.model_family == ModelFamily.REGRESSION_MODEL

    # Register Dataset Record
    dataset = sdk_client.external.register_dataset(
        dataset_id="ds_test_nifty_hourly",
        name="NIFTY 50 Intraday Hourly Benchmark",
        version="1.0.0",
        symbols=["NIFTY_50", "RELIANCE"],
    )

    assert dataset.dataset_id == "ds_test_nifty_hourly"
    assert "NIFTY_50" in dataset.symbols


# ==============================================================================
# Requirement 3 & 4: Submit Execution, Validate Schema & Independent Recomputations
# ==============================================================================

def test_req3_and_req4_submit_execution_and_verify_independent_metrics(
    client: TestClient,
    test_workspace_id: str,
    test_model_id: str,
) -> None:
    """Requirement 3 & 4: Submits test execution and verifies independent RMSE/MAE calculation."""
    run_id = f"ext_run_test_{int(time.time()*1000)}"
    exp_id = f"exp_test_{int(time.time()*1000)}"

    # Generate synthetic test predictions and actuals
    n_samples = 20
    actuals = [0.01, -0.015, 0.02, 0.005, -0.008, 0.012, -0.003, 0.007, -0.011, 0.018] * 2
    preds = [0.009, -0.014, 0.018, 0.006, -0.007, 0.011, -0.002, 0.008, -0.009, 0.017] * 2

    predictions = [
        {
            "timestamp": f"2026-10-{i+1:02d}T15:30:00+05:30",
            "target": "NIFTY_RETURN",
            "predicted_value": preds[i],
            "actual_value": actuals[i],
            "horizon": "1D",
        }
        for i in range(n_samples)
    ]

    # Externally reported metrics (reported by developer's script)
    metrics = [
        {"metric_name": "reported_rmse", "observed_value": 0.0014, "unit": "pct", "is_externally_reported": True},
        {"metric_name": "reported_mae", "observed_value": 0.0012, "unit": "pct", "is_externally_reported": True},
    ]

    payload = {
        "schema_version": "1.0.0",
        "workspace_id": test_workspace_id,
        "experiment_id": exp_id,
        "run_id": run_id,
        "model_id": test_model_id,
        "model_version": "2.1.0",
        "target_lab": "forecasting",
        "run_status": "completed",
        "parameters": {"n_estimators": 50, "max_depth": 3},
        "metrics": metrics,
        "predictions": predictions,
        "environment": {
            "environment_type": "google_colab",
            "python_version": "3.11.4",
            "hostname": "colab-kernel-01",
        },
    }

    # Transmit via REST API
    resp = client.post("/api/ingest/runs", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["success"] is True
    assert data["run_id"] == run_id
    assert data["status"] == "completed"
    assert data["received_metrics_count"] == 2
    assert data["received_predictions_count"] == 20
    assert len(data["provenance_hash"]) == 64

    # Requirement 4 Invariant: Verify independent metric re-computation
    recomp = data["recomputed_metrics"]
    assert recomp["verification_status"] == "INDEPENDENTLY_VERIFIED"
    assert recomp["evaluated_sample_count"] == 20
    assert recomp["independent_rmse"] > 0
    assert recomp["independent_mae"] > 0
    assert recomp["independent_directional_accuracy"] == 1.0  # Same sign on all pairs


# ==============================================================================
# Requirement 5: Persistence & Cryptographic Provenance
# ==============================================================================

def test_req5_persistence_and_provenance_verification(
    client: TestClient,
    test_workspace_id: str,
    test_model_id: str,
) -> None:
    """Requirement 5: Persists the execution and cryptographic provenance hash."""
    run_id = f"ext_run_prov_{int(time.time()*1000)}"
    exp_id = f"exp_prov_{int(time.time()*1000)}"

    payload = {
        "schema_version": "1.0.0",
        "workspace_id": test_workspace_id,
        "experiment_id": exp_id,
        "run_id": run_id,
        "model_id": test_model_id,
        "target_lab": "risk",
        "run_status": "completed",
        "metrics": [{"metric_name": "var_95", "observed_value": -0.0215, "unit": "pct"}],
    }

    # Submit
    resp = client.post("/api/ingest/runs", json=payload)
    assert resp.status_code == 201
    prov_hash = resp.json()["provenance_hash"]

    # Verify persistent retrieval via GET /api/ingest/runs/{id}
    detail_resp = client.get(f"/api/ingest/runs/{run_id}")
    assert detail_resp.status_code == 200
    rec = detail_resp.json()["run"]

    assert rec["run_id"] == run_id
    assert rec["provenance_hash"] == prov_hash
    assert rec["is_external"] is True


# ==============================================================================
# Requirement 6: Dashboard Integration & Data Source Retrieval
# ==============================================================================

def test_req6_unified_experiment_registry_dashboard_integration(
    client: TestClient,
    test_workspace_id: str,
    test_model_id: str,
) -> None:
    """Requirement 6: Verifies corresponding dashboard data source returns submitted results."""
    run_id = f"ext_run_dash_{int(time.time()*1000)}"
    exp_id = f"exp_dash_{int(time.time()*1000)}"

    payload = {
        "schema_version": "1.0.0",
        "workspace_id": test_workspace_id,
        "experiment_id": exp_id,
        "run_id": run_id,
        "model_id": test_model_id,
        "target_lab": "forecasting",
        "run_status": "completed",
        "metrics": [{"metric_name": "rmse", "observed_value": 0.0142, "unit": "pct"}],
        "predictions": [
            {"timestamp": "2026-10-25T15:30:00+05:30", "target": "RET", "predicted_value": 0.015, "actual_value": 0.012},
            {"timestamp": "2026-10-26T15:30:00+05:30", "target": "RET", "predicted_value": -0.005, "actual_value": -0.006},
        ],
    }

    sub_resp = client.post("/api/ingest/runs", json=payload)
    assert sub_resp.status_code == 201

    # 1. Verify Unified Experiment Registry (Page 9) endpoint: GET /api/experiments/runs
    reg_resp = client.get("/api/experiments/runs")
    assert reg_resp.status_code == 200
    all_runs = reg_resp.json().get("runs", [])
    matching = [r for r in all_runs if r.get("run_id") == run_id]
    assert len(matching) == 1, f"Expected run {run_id} to be returned in unified experiment registry"

    norm_run = matching[0]
    assert norm_run["run_type"] == "external_forecasting"
    assert norm_run["is_external"] is True
    assert norm_run["metrics_summary"]["verification"] == "INDEPENDENTLY_VERIFIED"

    # 2. Verify Single Experiment Detail endpoint: GET /api/experiments/{id}
    detail_resp = client.get(f"/api/experiments/{run_id}")
    assert detail_resp.status_code == 200
    exp_detail = detail_resp.json()["experiment"]
    assert exp_detail["run_id"] == run_id
    assert exp_detail["display_name"] == f"{test_model_id} on {exp_id}"


# ==============================================================================
# Requirement 7: Reject Invalid or Unauthorized Submissions
# ==============================================================================

def test_req7_reject_malformed_and_unauthorized_submissions(client: TestClient) -> None:
    """Requirement 7: Confirms invalid or unauthorized submissions are rejected."""
    # 7a. Missing required fields
    bad_resp1 = client.post("/api/ingest/runs", json={"schema_version": "1.0.0"})
    assert bad_resp1.status_code == 400
    assert "required" in bad_resp1.json()["error"]

    # 7b. Malformed run_id containing invalid characters (spaces / script injection)
    bad_resp2 = client.post("/api/ingest/runs", json={
        "workspace_id": "ws_alpha",
        "experiment_id": "exp_1",
        "run_id": "run with spaces <script>",
        "model_id": "model_1",
    })
    assert bad_resp2.status_code == 400
    assert "Invalid character" in bad_resp2.json()["error"]

    # 7c. Non-finite values (NaN / Inf) rejected by schema validation
    with pytest.raises(SchemaValidationError, match="finite"):
        ExternalMetric.from_dict({"metric_name": "rmse", "observed_value": float("nan")})

    with pytest.raises(SchemaValidationError, match="finite"):
        ExternalMetric.from_dict({"metric_name": "rmse", "observed_value": float("inf")})

    # Test malformed raw JSON rejection over HTTP
    raw_bad_json = '{"workspace_id": "ws_1", "experiment_id": "exp_1", "run_id": "run_1", "model_id": "m1", invalid_json}'
    bad_resp3 = client.post("/api/ingest/runs", content=raw_bad_json, headers={"Content-Type": "application/json"})
    assert bad_resp3.status_code == 400

    # 7d. Unauthorized Bearer token
    unauth_resp = client.post(
        "/api/ingest/runs",
        json={"workspace_id": "ws_1", "experiment_id": "exp_1", "run_id": "run_1", "model_id": "m1"},
        headers={"Authorization": "Bearer malformed_invalid_jwt_token_forged"},
    )
    assert unauth_resp.status_code == 401


# ==============================================================================
# Requirement 8: Failed Processing Job Is Not Presented As Completed
# ==============================================================================

def test_req8_failed_job_integrity_not_presented_as_completed(
    client: TestClient,
    test_workspace_id: str,
    test_model_id: str,
) -> None:
    """Requirement 8: Confirms a failed processing job is accurately presented as 'failed'."""
    failed_run_id = f"ext_run_fail_{int(time.time()*1000)}"

    payload = {
        "schema_version": "1.0.0",
        "workspace_id": test_workspace_id,
        "experiment_id": "exp_failure_handling",
        "run_id": failed_run_id,
        "model_id": test_model_id,
        "target_lab": "risk",
        "run_status": "failed",
        "error_message": "ConvergenceError: L-BFGS-B failed to converge after 1000 iterations (gradient norm > 1e-4).",
    }

    resp = client.post("/api/ingest/runs", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    # Must be 'failed', NEVER 'completed'
    assert data["status"] == "failed"

    # Query Status API endpoint
    status_resp = client.get(f"/api/ingest/runs/{failed_run_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "failed"
    assert "ConvergenceError" in status_data["error_message"]

    # Query Central Registry
    reg_resp = client.get("/api/experiments/runs")
    all_runs = reg_resp.json().get("runs", [])
    matching = [r for r in all_runs if r.get("run_id") == failed_run_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "failed"


# ==============================================================================
# Artifact Handling: Checksum Match & Mismatch Rejection (§3, §7)
# ==============================================================================

def test_artifact_upload_sha256_verification_and_mismatch_rejection(
    client: TestClient,
    test_workspace_id: str,
    test_model_id: str,
) -> None:
    """Verifies that uploaded artifacts enforce SHA-256 integrity and reject tampered files."""
    run_id = f"ext_run_art_{int(time.time()*1000)}"

    # 1. Submit base run
    client.post("/api/ingest/runs", json={
        "workspace_id": test_workspace_id,
        "experiment_id": "exp_art_test",
        "run_id": run_id,
        "model_id": test_model_id,
    })

    file_content = b'{"weights": [0.12, 0.45, 0.43], "trained_epochs": 100}'
    true_sha = hashlib.sha256(file_content).hexdigest()

    # 2. Upload with valid SHA-256 via stream
    ok_resp = client.post(
        f"/api/ingest/artifacts?run_id={run_id}&artifact_id=art_weights&name=weights.json&checksum_sha256={true_sha}",
        content=file_content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert ok_resp.status_code == 201
    art_info = ok_resp.json()["artifact"]
    assert art_info["checksum_sha256"] == true_sha
    assert art_info["name"] == "weights.json"

    # 3. Upload with tampered / mismatched SHA-256 -> MUST reject with 400
    bad_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    mismatch_resp = client.post(
        f"/api/ingest/artifacts?run_id={run_id}&artifact_id=art_weights_bad&name=weights.json&checksum_sha256={bad_sha}",
        content=file_content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert mismatch_resp.status_code == 400
    assert "SHA-256 mismatch" in mismatch_resp.json()["error"]
