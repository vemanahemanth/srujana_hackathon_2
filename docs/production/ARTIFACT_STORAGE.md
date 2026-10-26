# FragilityShield — Secure Artifact Storage Specification

## 1. Architectural Mission

Quantitative financial experiments produce critical data assets:
- Normalized price/returns matrix snapshots
- Model output parameters, weights, and forecast series
- Assumption sensitivity curves and stress scenarios
- Audit trail reports and JSON reproducibility manifests

These artifacts must be stored immutably, scoped strictly by tenant ownership, verified against tampering or bit-rot, and protected against unauthorized retrieval and path-traversal attacks.

---

## 2. Storage Abstraction Architecture

FragilityShield provides the `TenantArtifactStorage` interface (`backend/fragility_engine/artifact_storage.py`):

```python
class TenantArtifactStorage(abc.ABC):
    @abc.abstractmethod
    def store_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
        data: Union[bytes, BinaryIO],
        logical_type: str,
        media_type: str = "application/octet-stream",
        retention_days: Optional[int] = None,
    ) -> ArtifactMetadata: ...

    @abc.abstractmethod
    def get_artifact_stream(self, tenant_id: str, artifact_id: str) -> Iterator[bytes]: ...

    @abc.abstractmethod
    def verify_integrity(self, tenant_id: str, artifact_id: str) -> bool: ...

    @abc.abstractmethod
    def delete_artifact(self, tenant_id: str, artifact_id: str) -> bool: ...
```

---

## 3. Defense-in-Depth Security Controls

### 3.1 Strict Path Traversal & Identifier Validation
Artifact and tenant identifiers must match strict alphanumeric patterns `^[a-zA-Z0-9_\-]+$`.
Attempts to pass traversal sequences (`../`, `..\`, `/absolute`, or null bytes `\x00`) are rejected immediately with `ArtifactSecurityError` before any filesystem or storage operation executes.

### 3.2 Canonical Chroot Containment
When resolving file paths on local storage:
```python
resolved = (tenant_dir / filename).resolve()
if not resolved.is_relative_to(self.base_dir.resolve()):
    raise ArtifactSecurityError("Directory containment escape attempt detected.")
```
Artifacts can never be written or read outside `ARTIFACT_STORAGE_PATH`.

### 3.3 Streaming Checksum & Size Limits
Data is streamed in 64 KB chunks while incrementally updating a `hashlib.sha256()` accumulator. If incoming byte streams exceed `max_size_bytes` (default: 50 MB), the stream is aborted immediately with `ArtifactSizeLimitExceededError` and the temporary file is unlinked.

### 3.4 Atomic Write Strategy
Files are initially written to a unique `.tmp_{uuid}` file within the tenant directory, flushed, fsync'd, and atomically renamed to the final destination file `{artifact_id}.bin`. This guarantees readers never see partial or truncated artifact data.

### 3.5 Tamper & Bit-Rot Detection
The metadata file `{artifact_id}.meta.json` stores the computed SHA-256 digest. When `verify_integrity(tenant_id, artifact_id)` is invoked, the binary file is re-streamed and compared against the stored hash. Any mismatch raises `ArtifactIntegrityError`.

---

## 4. Multi-Tenant Authorization Matrix

Every artifact endpoint enforces five verification steps:
1. **Authentication:** Valid JWT bearer token signed with current `JWT_SECRET_KEY`.
2. **Tenant Scoping:** The authenticated `tenant_id` must match the artifact's owner in the database.
3. **Database RLS:** The query `SELECT * FROM artifacts WHERE artifact_id = :id` executes with `SET LOCAL app.current_tenant_id = :tenant_id`, guaranteeing cross-tenant isolation at the engine level.
4. **Lifecycle State:** Artifact must not be marked `status = 'DELETED'` or expired.
5. **Streaming Headers:** Downloads are served with `X-Content-Type-Options: nosniff` and `Content-Disposition: attachment; filename="{artifact_id}.bin"` to prevent browser MIME-confusion attacks.

---

## 5. Storage Directory Layout

```
data/artifacts/
├── ten_alpha_capital/
│   ├── art_alloc_run_01.bin
│   ├── art_alloc_run_01.meta.json
│   ├── art_manifest_01.bin
│   └── art_manifest_01.meta.json
└── ten_beta_hedge/
    ├── art_var_report_99.bin
    └── art_var_report_99.meta.json
```
Each tenant has an isolated subfolder. Permissions are locked down to `0700` (read/write/execute by worker user only).
