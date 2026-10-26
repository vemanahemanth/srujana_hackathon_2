"""FragilityShield — Isolated Experiment Execution Worker & Asynchronous Orchestration (Sprint 5).

Separates the HTTP request-response cycle from long-running quantitative model
executions, stress testing, and scenario simulations.

Key Architecture:
1. Concurrency-Safe Job Claiming:
   - PostgreSQL `FOR UPDATE SKIP LOCKED` transactional claiming.
   - Dynamic worker lease expiration with periodic heartbeats.
2. Robust Job Lifecycle:
   - Explicit state transitions: QUEUED -> CLAIMED -> RUNNING -> SUCCEEDED / FAILED / TIMED_OUT / CANCELLED.
   - Graceful cancellation handling (terminates sub-processes / containers).
3. Fail-Closed Workload Isolation:
   - Trusted local research vs. Approved isolated container.
   - Strictly fails closed if isolation runtime is missing in container mode.
4. Experiment Artifact Storage & Reproducibility Evidence:
   - Persists outputs and cryptographic SHA-256 reproducibility manifests to `ArtifactStorage`.
   - Records metadata in `artifacts` table under tenant-enforced Row-Level Security.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from fragility_engine.artifact_storage import (
    ArtifactStorageAdapter,
    get_artifact_storage,
)
from fragility_engine.database import get_active_repository
from fragility_engine.model_sandbox import (
    ModelCategory,
    ModelContractValidationError,
    ModelExecutionMode,
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelJobStatus,
    ModelResourceLimits,
    SandboxSecurityError,
    get_default_model_sandbox,
)
from fragility_engine.reproducibility import canonical_json_dumps
from fragility_engine.tenancy import (
    ROLE_PERMISSIONS,
    TenantContext,
    TenantRole,
    set_current_tenant_context,
)

logger = logging.getLogger("fragility_engine.worker")


@dataclass
class WorkerConfig:
    """Operational parameters governing the experiment worker."""
    worker_id: str = field(default_factory=lambda: f"worker_{secrets.token_hex(6)}")
    poll_interval_seconds: float = 0.5
    lease_duration_seconds: float = 30.0
    heartbeat_interval_seconds: float = 5.0
    max_memory_mb: int = 512
    max_concurrent_jobs: int = 1


@dataclass
class WorkerTelemetry:
    """Live operational diagnostics and metrics."""
    worker_id: str
    is_running: bool
    started_at: float
    total_claimed: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    total_timed_out: int = 0
    total_cancelled: int = 0
    active_jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_heartbeat_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "is_running": self.is_running,
            "uptime_seconds": round(time.time() - self.started_at, 2) if self.started_at else 0.0,
            "total_claimed": self.total_claimed,
            "total_succeeded": self.total_succeeded,
            "total_failed": self.total_failed,
            "total_timed_out": self.total_timed_out,
            "total_cancelled": self.total_cancelled,
            "active_jobs_count": len(self.active_jobs),
            "last_heartbeat_at": self.last_heartbeat_at,
        }


class FragilityExperimentWorker:
    """Asynchronous worker that polls, leases, isolates, and executes quantitative jobs."""

    def __init__(
        self,
        config: Optional[WorkerConfig] = None,
        storage: Optional[ArtifactStorageAdapter] = None,
    ) -> None:
        self.config = config or WorkerConfig()
        self.storage = storage or get_artifact_storage()
        self.telemetry = WorkerTelemetry(
            worker_id=self.config.worker_id,
            is_running=False,
            started_at=0.0,
        )
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Launch background worker daemon thread."""
        with self._lock:
            if self.telemetry.is_running:
                return
            self._stop_event.clear()
            self.telemetry.is_running = True
            self.telemetry.started_at = time.time()
            self._thread = threading.Thread(
                target=self._worker_loop,
                name=f"WorkerThread-{self.config.worker_id}",
                daemon=True,
            )
            self._thread.start()
            logger.info("Started FragilityExperimentWorker: %s", self.config.worker_id)

    def stop(self, timeout: float = 5.0) -> None:
        """Halt worker daemon gracefully."""
        with self._lock:
            if not self.telemetry.is_running:
                return
            self._stop_event.set()
            self.telemetry.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("Stopped FragilityExperimentWorker: %s", self.config.worker_id)

    def run_once(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Claim and execute a single pending job.

        Returns:
            Job result record if a job was processed, otherwise None.
        """
        repo = get_active_repository()
        if not hasattr(repo, "claim_next_job"):
            return None

        claimed = repo.claim_next_job(
            worker_id=self.config.worker_id,
            tenant_id=tenant_id,
            lease_duration_seconds=self.config.lease_duration_seconds,
        )
        if not claimed:
            return None

        with self._lock:
            self.telemetry.total_claimed += 1
            self.telemetry.active_jobs[claimed["job_id"]] = {
                "tenant_id": claimed["tenant_id"],
                "claimed_at": time.time(),
            }

        try:
            return self._process_claimed_job(claimed)
        finally:
            with self._lock:
                self.telemetry.active_jobs.pop(claimed["job_id"], None)

    def _worker_loop(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                processed = self.run_once()
                if not processed:
                    time.sleep(self.config.poll_interval_seconds)
            except Exception as exc:
                logger.error("Error in worker polling loop: %s", exc, exc_info=True)
                time.sleep(self.config.poll_interval_seconds)

    def _process_claimed_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a claimed job with heartbeats, timeout tracking, and artifact persistence."""
        job_id = job["job_id"]
        tenant_id = job["tenant_id"]
        payload = job.get("payload", {})
        timeout_seconds = float(job.get("timeout_seconds", 60.0))

        repo = get_active_repository()

        # Set up tenant security context for the worker execution
        worker_ctx = TenantContext(
            tenant_id=tenant_id,
            user_id="usr_system_worker",
            role=TenantRole.RESEARCHER,
            permissions=ROLE_PERMISSIONS[TenantRole.RESEARCHER],
        )
        set_current_tenant_context(worker_ctx)

        # Start periodic heartbeat thread
        heartbeat_stop = threading.Event()

        def _heartbeat_worker():
            while not heartbeat_stop.is_set():
                heartbeat_stop.wait(self.config.heartbeat_interval_seconds)
                if heartbeat_stop.is_set():
                    break
                try:
                    if hasattr(repo, "heartbeat_job"):
                        repo.heartbeat_job(
                            tenant_id=tenant_id,
                            job_id=job_id,
                            worker_id=self.config.worker_id,
                            lease_duration_seconds=self.config.lease_duration_seconds,
                        )
                    with self._lock:
                        self.telemetry.last_heartbeat_at = time.time()
                except Exception as hb_exc:
                    logger.warning("Heartbeat update failed for job %s: %s", job_id, hb_exc)

        hb_thread = threading.Thread(
            target=_heartbeat_worker,
            name=f"Heartbeat-{job_id}",
            daemon=True,
        )
        hb_thread.start()

        try:
            # Check for cancellation before starting work
            current_job = repo.get_job(job_id) if hasattr(repo, "get_job") else job
            if current_job and current_job.get("status") == "CANCEL_REQUESTED":
                if hasattr(repo, "complete_job"):
                    repo.complete_job(
                        tenant_id=tenant_id,
                        job_id=job_id,
                        worker_id=self.config.worker_id,
                        status="CANCELLED",
                        error_message="Job cancelled prior to execution.",
                    )
                with self._lock:
                    self.telemetry.total_cancelled += 1
                return {"job_id": job_id, "status": "CANCELLED"}

            # Execute Model or Experiment
            status, result, error_msg = self._execute_job_workload(job, timeout_seconds)

            # Persist artifacts and manifest if succeeded
            if status == "SUCCEEDED" and result:
                self._persist_job_artifacts_and_manifest(tenant_id, job_id, payload, result)

            # Atomically publish terminal status
            if hasattr(repo, "complete_job"):
                repo.complete_job(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    worker_id=self.config.worker_id,
                    status=status,
                    result=result,
                    error_message=error_msg,
                )

            with self._lock:
                if status == "SUCCEEDED":
                    self.telemetry.total_succeeded += 1
                elif status == "TIMED_OUT":
                    self.telemetry.total_timed_out += 1
                elif status == "CANCELLED":
                    self.telemetry.total_cancelled += 1
                else:
                    self.telemetry.total_failed += 1

            return {"job_id": job_id, "status": status, "result": result, "error": error_msg}

        except Exception as exc:
            logger.error("Unhandled exception during job %s execution: %s", job_id, exc, exc_info=True)
            if hasattr(repo, "complete_job"):
                repo.complete_job(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    worker_id=self.config.worker_id,
                    status="FAILED",
                    error_message=f"Worker exception: {str(exc)}",
                )
            with self._lock:
                self.telemetry.total_failed += 1
            return {"job_id": job_id, "status": "FAILED", "error": str(exc)}

        finally:
            heartbeat_stop.set()
            hb_thread.join(timeout=1.0)
            set_current_tenant_context(None)

    def _execute_job_workload(
        self,
        job: Dict[str, Any],
        timeout_seconds: float,
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        """Route and execute workload based on job type and isolation rules."""
        payload = job.get("payload", {})
        job_id = job["job_id"]
        tenant_id = job["tenant_id"]

        # Parse category & mode
        cat_str = payload.get("category", "risk_estimation")
        try:
            category = ModelCategory(cat_str)
        except ValueError:
            category = ModelCategory.RISK_ESTIMATION

        raw_mode = payload.get("execution_mode", "trusted_local_research")
        try:
            exec_mode = ModelExecutionMode(raw_mode)
        except ValueError:
            exec_mode = ModelExecutionMode.DISABLED

        model_id = str(payload.get("model_id", "custom_model"))
        input_data = payload.get("input", payload.get("input_payload", {}))

        # Check timeout configuration
        limits = ModelResourceLimits(
            timeout_seconds=timeout_seconds,
            max_memory_mb=self.config.max_memory_mb,
        )

        req = ModelExecutionRequest(
            request_id=f"req_{job_id}",
            tenant_id=tenant_id,
            user_id="usr_system_worker",
            model_id=model_id,
            category=category,
            model_version=str(payload.get("model_version", "1.0.0")),
            artifact_hash=hashlib.sha256(f"{model_id}:{payload.get('model_version')}".encode()).hexdigest(),
            dataset_fingerprint=hashlib.sha256(canonical_json_dumps(input_data).encode()).hexdigest() if input_data else "none",
            input_payload=input_data,
            limits=limits,
            execution_mode=exec_mode,
        )

        sandbox = get_default_model_sandbox()

        try:
            exec_res: ModelExecutionResult = sandbox.execute(req)
            if exec_res.status == ModelJobStatus.SUCCEEDED:
                return "SUCCEEDED", exec_res.to_dict(), None
            elif exec_res.status == ModelJobStatus.TIMED_OUT:
                return "TIMED_OUT", None, exec_res.error_message or "Execution timed out"
            elif exec_res.status == ModelJobStatus.CANCELLED:
                return "CANCELLED", None, "Execution was cancelled"
            else:
                return "FAILED", None, exec_res.error_message or "Execution failed"
        except SandboxSecurityError as sec_exc:
            return "FAILED", None, f"SandboxSecurityError: {sec_exc}"
        except ModelContractValidationError as val_exc:
            return "FAILED", None, f"ModelContractValidationError: {val_exc}"
        except Exception as exc:
            return "FAILED", None, str(exc)

    def _persist_job_artifacts_and_manifest(
        self,
        tenant_id: str,
        job_id: str,
        payload: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Store output artifact and versioned reproducibility manifest."""
        repo = get_active_repository()

        # 1. Output artifact
        output_bytes = json.dumps(result, indent=2).encode("utf-8")
        art_id = f"art_out_{job_id}"
        stored_out = self.storage.store_artifact(
            tenant_id=tenant_id,
            artifact_id=art_id,
            data=output_bytes,
            logical_type="model_output_json",
            media_type="application/json",
            job_id=job_id,
            metadata={"model_id": payload.get("model_id")},
        )
        if hasattr(repo, "create_artifact"):
            repo.create_artifact(
                artifact_id=stored_out.artifact_id,
                logical_type=stored_out.logical_type,
                storage_key=stored_out.storage_key,
                content_hash=stored_out.content_hash,
                size_bytes=stored_out.size_bytes,
                media_type=stored_out.media_type,
                job_id=job_id,
            )

        # 2. Versioned Reproducibility Manifest
        manifest_data = {
            "manifest_version": "1.0",
            "experiment_id": payload.get("experiment_id", job_id),
            "job_id": job_id,
            "tenant_id": tenant_id,
            "model_id": payload.get("model_id"),
            "model_version": payload.get("model_version", "1.0.0"),
            "category": payload.get("category"),
            "execution_mode": payload.get("execution_mode"),
            "input_hash": hashlib.sha256(canonical_json_dumps(payload.get("input", {})).encode()).hexdigest(),
            "output_hash": stored_out.content_hash,
            "output_artifact_id": stored_out.artifact_id,
            "worker_id": self.config.worker_id,
            "timestamp": time.time(),
        }
        manifest_str = canonical_json_dumps(manifest_data)
        manifest_bytes = manifest_str.encode("utf-8")
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_data["manifest_hash"] = manifest_hash

        man_art_id = f"art_man_{job_id}"
        stored_man = self.storage.store_artifact(
            tenant_id=tenant_id,
            artifact_id=man_art_id,
            data=json.dumps(manifest_data, indent=2).encode("utf-8"),
            logical_type="reproducibility_manifest",
            media_type="application/json",
            job_id=job_id,
            metadata={"manifest_hash": manifest_hash},
        )
        if hasattr(repo, "create_artifact"):
            repo.create_artifact(
                artifact_id=stored_man.artifact_id,
                logical_type=stored_man.logical_type,
                storage_key=stored_man.storage_key,
                content_hash=stored_man.content_hash,
                size_bytes=stored_man.size_bytes,
                media_type=stored_man.media_type,
                job_id=job_id,
            )


# ==============================================================================
# Worker Service Singleton / Factory
# ==============================================================================

_GLOBAL_WORKER: Optional[FragilityExperimentWorker] = None


def get_default_worker() -> FragilityExperimentWorker:
    """Resolve global default experiment execution worker."""
    global _GLOBAL_WORKER
    if _GLOBAL_WORKER is None:
        _GLOBAL_WORKER = FragilityExperimentWorker()
    return _GLOBAL_WORKER


def set_default_worker(worker: Optional[FragilityExperimentWorker]) -> None:
    global _GLOBAL_WORKER
    _GLOBAL_WORKER = worker
