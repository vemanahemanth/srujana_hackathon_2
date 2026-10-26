#!/usr/bin/env python3
"""FragilityShield — External Experiment & Model Client (Sprint 9 Extension).

Universal CLI and programmatic client for submitting quantitative model executions,
metrics, predictions, datasets, and file artifacts to FragilityShield from external
environments (developer laptops, research workstations, CI/CD workers).

Usage:
    export FRAGILITYSHIELD_API_URL="http://127.0.0.1:8000"
    export FRAGILITYSHIELD_API_TOKEN="your_scoped_jwt_or_api_token"
    python external_experiment_client.py --model-id nifty_gbm_vol --workspace ws_research_alpha
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from typing import Any, Dict, List

# Add parent directory to path if running inside repository
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
backend_path = os.path.join(repo_root, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from fragility_engine.sdk import Client
from fragility_engine.external_connectivity import (
    ExecutionEnvironment,
    ExternalMetric,
    ExternalPrediction,
)


def generate_synthetic_volatility_experiment() -> Dict[str, Any]:
    """Generate deterministic sample quantitative model results for demonstration."""
    import numpy as np

    # Deterministic seed for reproducible testing
    rng = np.random.RandomState(42)
    n_samples = 30
    
    # Simulate return predictions vs actual returns
    actual_returns = rng.normal(loc=0.0008, scale=0.015, size=n_samples)
    noise = rng.normal(loc=0.0, scale=0.004, size=n_samples)
    predicted_returns = actual_returns + noise

    # Externally calculated metrics
    residuals = predicted_returns - actual_returns
    rmse = float(np.sqrt(np.mean(residuals ** 2)))
    mae = float(np.mean(np.abs(residuals)))
    dir_acc = float(np.mean(np.sign(predicted_returns) == np.sign(actual_returns)))

    timestamps = [
        f"2026-10-{i+1:02d}T15:30:00+05:30" for i in range(n_samples)
    ]

    predictions = [
        ExternalPrediction(
            timestamp=timestamps[i],
            target="NIFTY_RETURN",
            predicted_value=round(float(predicted_returns[i]), 6),
            actual_value=round(float(actual_returns[i]), 6),
            horizon="1D",
            confidence_lower=round(float(predicted_returns[i] - 1.96 * 0.004), 6),
            confidence_upper=round(float(predicted_returns[i] + 1.96 * 0.004), 6),
        )
        for i in range(n_samples)
    ]

    metrics = [
        ExternalMetric(
            metric_name="rmse",
            observed_value=round(rmse, 6),
            unit="pct_variance",
            sample_count=n_samples,
            is_externally_reported=True,
        ),
        ExternalMetric(
            metric_name="mae",
            observed_value=round(mae, 6),
            unit="pct",
            sample_count=n_samples,
            is_externally_reported=True,
        ),
        ExternalMetric(
            metric_name="directional_accuracy",
            observed_value=round(dir_acc, 4),
            unit="ratio",
            sample_count=n_samples,
            is_externally_reported=True,
        ),
        ExternalMetric(
            metric_name="max_residual",
            observed_value=round(float(np.max(np.abs(residuals))), 6),
            unit="pct",
            sample_count=n_samples,
            is_externally_reported=True,
        ),
    ]

    return {
        "metrics": metrics,
        "predictions": predictions,
        "parameters": {
            "model_type": "GradientBoostingForecaster",
            "lookback_window": 60,
            "learning_rate": 0.05,
            "max_depth": 3,
            "n_estimators": 100,
            "loss_function": "huber",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="FragilityShield External Experiment Client")
    parser.add_argument("--api-url", default=os.environ.get("FRAGILITYSHIELD_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-token", default=os.environ.get("FRAGILITYSHIELD_API_TOKEN", ""))
    parser.add_argument("--workspace", default="ws_quant_research_alpha")
    parser.add_argument("--model-id", default="nifty_gbm_forecaster")
    parser.add_argument("--experiment-id", default=f"exp_{int(time.time())}")
    parser.add_argument("--run-id", default=f"ext_run_{int(time.time())}")
    parser.add_argument("--target-lab", default="forecasting", choices=["general", "forecasting", "risk", "robustness", "allocation"])
    args = parser.parse_args()

    print(f"Connecting to FragilityShield at: {args.api_url}")
    print(f"Workspace: {args.workspace} | Model: {args.model_id} | Run: {args.run_id}")

    # Initialize typed SDK Client
    client = Client(
        api_url=args.api_url,
        api_token=args.api_token,
        workspace_id=args.workspace,
        environment_type="local_script",
    )

    # 1. Register Model Manifest
    print("1. Registering Model Manifest...")
    client.external.register_model(
        model_id=args.model_id,
        name="NSE Nifty Gradient Boosting Forecaster",
        version="1.2.0",
        author="quant_researcher",
        description="Daily return direction and volatility forecast on NSE Nifty 50 constituents.",
    )
    print(f"   Model '{args.model_id}' registered successfully.")

    # 2. Register Dataset
    print("2. Registering Source Dataset...")
    client.external.register_dataset(
        dataset_id="ds_nifty50_daily_2026",
        name="Nifty 50 Historical EOD 2026",
        version="1.0.0",
        format="csv",
        symbols=["NIFTY_50", "RELIANCE", "TCS", "HDFCBANK"],
    )
    print("   Dataset 'ds_nifty50_daily_2026' registered.")

    # 3. Create Sample Artifact (e.g. Model Checkpoint / Diagnostic Report)
    print("3. Generating Artifact...")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        artifact_data = {
            "model_id": args.model_id,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "feature_importance": {"momentum_10d": 0.35, "rsi_14d": 0.28, "volatility_20d": 0.37},
        }
        json.dump(artifact_data, tmp, indent=2)
        artifact_path = tmp.name

    artifact_bytes = open(artifact_path, "rb").read()
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    print(f"   Artifact file ready: {artifact_path} (SHA-256: {artifact_sha[:12]}...)")

    # 4. Generate Synthetic Execution Results
    print("4. Computing Local Predictions & Metrics...")
    sim_data = generate_synthetic_volatility_experiment()

    # 5. Submit Run to FragilityShield
    print("5. Submitting Run to Central FragilityShield Platform...")
    ingestion_result = client.external.submit_run(
        experiment_id=args.experiment_id,
        run_id=args.run_id,
        model_id=args.model_id,
        target_lab=args.target_lab,
        dataset_id="ds_nifty50_daily_2026",
        parameters=sim_data["parameters"],
        metrics=sim_data["metrics"],
        predictions=sim_data["predictions"],
        run_status="completed",
        environment={
            "environment_type": "local_script",
            "hostname": os.uname().nodename if hasattr(os, "uname") else "external_host",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
    )

    print("\n================ INGESTION SUMMARY ================")
    print(f"Status:                    {ingestion_result.status.upper()}")
    print(f"Submission ID:             {ingestion_result.submission_id}")
    print(f"Run ID:                    {ingestion_result.run_id}")
    print(f"Target Lab Routed:         {ingestion_result.target_lab_routed}")
    print(f"Received Metrics:          {ingestion_result.received_metrics_count}")
    print(f"Received Predictions:      {ingestion_result.received_predictions_count}")
    print(f"Provenance Hash:           {ingestion_result.provenance_hash}")
    print("\nIndependent Re-computations by FragilityShield:")
    for k, v in ingestion_result.recomputed_metrics.items():
        print(f"  • {k}: {v}")
    print("====================================================\n")

    # 6. Upload Artifact with SHA-256 Checksum
    print("6. Uploading Artifact...")
    art_ref = client.external.upload_artifact(
        run_id=args.run_id,
        file_path=artifact_path,
        artifact_id="art_feature_weights_v1",
        name="feature_importance.json",
        expected_sha256=artifact_sha,
    )
    print(f"   Artifact uploaded: {art_ref.name} (SHA: {art_ref.checksum_sha256[:12]}...)")

    # Clean up local temp file
    try:
        os.remove(artifact_path)
    except OSError:
        pass

    # 7. Query Run Inspection Record from Central Platform
    print("7. Querying Central Record...")
    retrieved_run = client.external.get_run(args.run_id)
    if retrieved_run:
        print(f"   Retrieved Run Display Name: {retrieved_run.get('display_name')}")
        print(f"   Artifacts Count:            {retrieved_run.get('artifacts_count')}")
    else:
        print("   Warning: Run could not be retrieved from central index.")

    print("\nUniversal External Experiment Submission Complete!")


if __name__ == "__main__":
    main()
