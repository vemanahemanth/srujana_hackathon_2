# FragilityShield — Universal External Connectivity & Experiment Ingestion API Reference

**Specification Version:** `1.0.0`  
**Protocol:** REST over HTTP / JSON  
**Platform Release:** Sprint 9 Extension  

---

## 1. Overview & Architectural Boundaries

FragilityShield serves as a central, API-first quantitative analysis, model validation, and fragility evaluation platform. External development environments (developer laptops, Google Colab notebooks, Jupyter environments, external Python research repositories, CI/CD workers, and third-party model providers) communicate with FragilityShield via this REST API contract.

### Architectural Invariants:
1. **Zero Unsolicited Probing:** FragilityShield never initiates outbound connections to developer laptops or notebook instances. Every environment explicitly authenticates and submits payloads over standard HTTPS/REST.
2. **Dual-Layer Metric Distinction:** FragilityShield clearly separates externally self-reported metrics from metrics independently re-computed and verified by the FragilityShield calculation engine.
3. **Fail-Closed Security & Code Isolation:** Arbitrary uploaded code is never executed on the main server. Artifacts are strictly verified via SHA-256 and bounded to safe directories.
4. **Unified Registry Integration:** Accepted external runs seamlessly populate the Page 9 Central Experiment Registry, Model Comparison Lab, and relevant quantitative dashboards.

---

## 2. Authentication & Scoped Credentials

All REST API endpoints support authentication via scoped JWT bearer tokens or API credentials.

```http
Authorization: Bearer <your_scoped_jwt_token>
```

To acquire a bearer token programmatically:

```bash
curl -X POST "http://127.0.0.1:8000/api/auth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "quant_researcher",
    "password": "your_secure_password",
    "tenant_id": "ten_default"
  }'
```

---

## 3. Endpoints

### 3.1. Submit External Model Execution Run

`POST /api/ingest/runs`

Submits an external model execution record, parameters, environment metadata, metrics, predictions, and artifact references.

#### Resource Bounds & Limits:
- **Max JSON Payload Size:** 15 MB (`413 Payload Too Large` returned if exceeded).
- **Identifier Format:** `[a-zA-Z0-9_\-\.]+` (alphanumeric, dot, dash, underscore).

#### Request Body Schema (`v1`):

```json
{
  "schema_version": "1.0.0",
  "workspace_id": "ws_alpha_research",
  "experiment_id": "exp_volatility_clustering_01",
  "run_id": "ext_run_20261026_01",
  "model_id": "garch_vol_forecaster",
  "model_version": "1.2.0",
  "dataset_id": "ds_nifty50_hourly",
  "dataset_version": "1.0.0",
  "target_lab": "forecasting",
  "run_status": "completed",
  "parameters": {
    "p": 1,
    "q": 1,
    "distribution": "student_t"
  },
  "metrics": [
    {
      "metric_name": "rmse",
      "observed_value": 0.00369,
      "unit": "pct",
      "sample_count": 50,
      "is_externally_reported": true
    },
    {
      "metric_name": "mae",
      "observed_value": 0.00304,
      "unit": "pct",
      "sample_count": 50,
      "is_externally_reported": true
    }
  ],
  "predictions": [
    {
      "timestamp": "2026-10-25T15:30:00+05:30",
      "target": "NIFTY_RETURN",
      "predicted_value": 0.0012,
      "actual_value": 0.0011,
      "horizon": "1D",
      "confidence_lower": 0.0006,
      "confidence_upper": 0.0018
    }
  ],
  "artifacts": [
    {
      "artifact_id": "art_model_weights_01",
      "name": "model_weights.json",
      "artifact_type": "report_json",
      "checksum_sha256": "dc11567e0f612d93e2b260cf88c9dfd04899c75908b8b1db55c1ff94efc28ce1",
      "size_bytes": 1024
    }
  ],
  "environment": {
    "environment_type": "google_colab",
    "python_version": "3.11.4",
    "hostname": "colab-worker-gpu-04",
    "frameworks": {
      "numpy": "1.26.0",
      "torch": "2.2.0"
    }
  },
  "error_message": null
}
```

#### Response (`201 Created`):

```json
{
  "success": true,
  "submission_id": "sub_1792953161539_ext_run_",
  "run_id": "ext_run_20261026_01",
  "status": "completed",
  "received_metrics_count": 2,
  "received_predictions_count": 1,
  "received_artifacts_count": 1,
  "target_lab_routed": "forecasting",
  "validation_warnings": [],
  "recomputed_metrics": {
    "independent_rmse": 0.0001,
    "independent_mae": 0.0001,
    "independent_directional_accuracy": 1.0,
    "evaluated_sample_count": 1,
    "verification_status": "INDEPENDENTLY_VERIFIED"
  },
  "provenance_hash": "bb06596e5655c493c8abfb225620fea6f0810c5b3741b1f7071cf77d02ecfcee",
  "ingested_at": "2026-10-25T18:32:41.539731+00:00"
}
```

---

### 3.2. List Ingested Runs

`GET /api/ingest/runs`

#### Query Parameters:
- `workspace_id` *(optional)*: Filter by workspace/project.
- `target_lab` *(optional)*: Filter by target lab (`forecasting`, `risk`, `robustness`, `allocation`, `general`).
- `status` *(optional)*: Filter by execution status (`completed`, `failed`, `running`, `accepted`).

#### Response (`200 OK`):

```json
{
  "success": true,
  "count": 1,
  "runs": [
    {
      "run_id": "ext_run_20261026_01",
      "display_name": "garch_vol_forecaster on exp_volatility_clustering_01",
      "run_type": "external_forecasting",
      "status": "completed",
      "created_at": "2026-10-25T18:32:41.539731+00:00",
      "lab": "forecasting",
      "is_external": true,
      "source_environment": "google_colab",
      "model_id": "garch_vol_forecaster",
      "metrics": {
        "rmse": 0.00369,
        "mae": 0.00304
      },
      "recomputed_metrics": {
        "independent_rmse": 0.0001,
        "verification_status": "INDEPENDENTLY_VERIFIED"
      },
      "provenance_hash": "bb06596e5655c493c8abfb225620fea6f0810c5b3741b1f7071cf77d02ecfcee"
    }
  ]
}
```

---

### 3.3. Get Ingested Run Inspection Details

`GET /api/ingest/runs/{id}`

Returns the full canonical record for an externally submitted run.

#### Response (`200 OK`):

```json
{
  "success": true,
  "run": {
    "run_id": "ext_run_20261026_01",
    "display_name": "garch_vol_forecaster on exp_volatility_clustering_01",
    "run_type": "external_forecasting",
    "status": "completed",
    "created_at": "2026-10-25T18:32:41.539731+00:00",
    "completed_at": null,
    "lab": "forecasting",
    "is_external": true,
    "source_environment": "google_colab",
    "model_id": "garch_vol_forecaster",
    "dataset_id": "ds_nifty50_hourly",
    "metrics": {
      "rmse": 0.00369,
      "mae": 0.00304
    },
    "recomputed_metrics": {
      "independent_rmse": 0.0001,
      "independent_mae": 0.0001,
      "independent_directional_accuracy": 1.0,
      "evaluated_sample_count": 1,
      "verification_status": "INDEPENDENTLY_VERIFIED"
    },
    "parameters": {
      "p": 1,
      "q": 1,
      "distribution": "student_t"
    },
    "predictions_count": 1,
    "artifacts_count": 1,
    "provenance_hash": "bb06596e5655c493c8abfb225620fea6f0810c5b3741b1f7071cf77d02ecfcee"
  }
}
```

---

### 3.4. Get Ingested Run Processing & Validation Status

`GET /api/ingest/runs/{id}/status`

High-speed polling endpoint to monitor submission lifecycle status without transferring heavy metrics/prediction payloads.

#### Response (`200 OK`):

```json
{
  "success": true,
  "run_id": "ext_run_20261026_01",
  "status": "completed",
  "is_external": true,
  "lab": "forecasting",
  "has_recomputed_metrics": true,
  "error_message": null,
  "provenance_hash": "bb06596e5655c493c8abfb225620fea6f0810c5b3741b1f7071cf77d02ecfcee"
}
```

---

### 3.5. Upload External File Artifact

`POST /api/ingest/artifacts`

Accepts multipart form uploads or raw octet-streams with SHA-256 verification.

#### Limits:
- **Max File Size:** 25 MB (`400 Bad Request` if exceeded).
- **Checksum Verification:** Strict SHA-256 match. Rejects with `400 Bad Request` if the computed hash does not match `checksum_sha256`.

#### Option A: Multipart Form Data

```bash
curl -X POST "http://127.0.0.1:8000/api/ingest/artifacts" \
  -H "Authorization: Bearer <token>" \
  -F "run_id=ext_run_20261026_01" \
  -F "artifact_id=art_weights_v1" \
  -F "name=model_weights.json" \
  -F "checksum_sha256=dc11567e0f612d93e2b260cf88c9dfd04899c75908b8b1db55c1ff94efc28ce1" \
  -F "file=@model_weights.json"
```

#### Option B: Binary Octet-Stream

```bash
curl -X POST "http://127.0.0.1:8000/api/ingest/artifacts?run_id=ext_run_20261026_01&artifact_id=art_weights_v1&name=model_weights.json&checksum_sha256=dc11567e0f612d93e2b260cf88c9dfd04899c75908b8b1db55c1ff94efc28ce1" \
  -H "Content-Type: application/octet-stream" \
  -H "Authorization: Bearer <token>" \
  --data-binary "@model_weights.json"
```

#### Response (`201 Created`):

```json
{
  "success": true,
  "artifact": {
    "artifact_id": "art_weights_v1",
    "name": "model_weights.json",
    "artifact_type": "uploaded_file",
    "checksum_sha256": "dc11567e0f612d93e2b260cf88c9dfd04899c75908b8b1db55c1ff94efc28ce1",
    "size_bytes": 1024,
    "uri_or_path": "/Users/.../data/artifacts/ext_run_20261026_01/model_weights.json",
    "created_at": "2026-10-25T18:32:41.982110+00:00"
  }
}
```

---

## 4. Error Codes & Consistent Error Envelopes

Every error response follows the standard FragilityShield error schema:

```json
{
  "error": "Human readable description of the error condition",
  "status_code": 400,
  "error_type": "schema_validation_error"
}
```

| HTTP Status | Error Type | Cause |
|---|---|---|
| `400 Bad Request` | `schema_validation_error` | Missing required fields, invalid identifier characters, non-finite values (NaN/inf). |
| `400 Bad Request` | `artifact_validation_error` | SHA-256 checksum mismatch, empty payload, or file size > 25 MB. |
| `401 Unauthorized` | `authentication_error` | Missing or invalid Bearer JWT token. |
| `403 Forbidden` | `authorization_error` | User does not have access to requested workspace or tenant. |
| `404 Not Found` | `not_found` | Specified `run_id` or `artifact_id` does not exist. |
| `413 Payload Too Large` | `payload_too_large` | Ingestion JSON payload > 15 MB. |
| `422 Unprocessable` | `ingestion_error` | Ingestion domain validation failed. |
