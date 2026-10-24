# FragilityShield — Phase 7: Issue Review Amendment

**Date:** 2026-10-24  
**Auditor / Reviewer:** Principal Software Architect, Quantitative Risk Engineer & Test Automation Engineer  
**Baseline Git Commit:** `ec1997e`  
**Referenced Documents:** `docs/phase-7-report.md`, `docs/phase-7-issue-review.md`

---

## 1. Executive Summary

During the pre-implementation audit for Phase 8 (Stage B: Inherited Issues), an independent line-by-line inspection of `backend/fragility_engine/reproducibility.py`, `studio.py`, and related modules revealed three concrete technical defects inherited from Phases 6 and 7.

All three defects have been reproduced, fixed, and regression-tested. This amendment documents the root cause, risk impact, resolution, and verification evidence for each issue.

---

## 2. Inherited Defect Inventory & Resolutions

### Defect 1: RFC 8259 Non-Finite Float Leniency in Canonical Serialization (`reproducibility.py`)
- **Location:** `backend/fragility_engine/reproducibility.py`, `canonical_json_dumps`
- **Root Cause:** Standard Python `json.dumps()` defaults to `allow_nan=True`, serializing Python `float('nan')` and `float('inf')` to JavaScript-illegal tokens (`NaN`, `Infinity`, `-Infinity`). While `canonical_json_dumps` inspected top-level types, nested floats could bypass validation and yield non-deterministic or invalid RFC 8259 JSON strings.
- **Risk Impact:** Masking undefined calculations, producing invalid JSON exports, and causing fingerprint collisions across differing platforms.
- **Resolution:** Explicitly configured `json.dumps(..., allow_nan=False)`. Added pre-flight recursive type validation that explicitly checks `math.isfinite()` on all numeric values and raises `ValueError("Non-finite float ...")`.
- **Verification:** Tested in `test_canonical_json_dumps_rejects_nan_and_inf`.

---

### Defect 2: Boolean `0.0` Truthiness Trap in Independent Invariant Verification (`reproducibility.py`)
- **Location:** `backend/fragility_engine/reproducibility.py`, `verify_experiment_invariants`
- **Root Cause:** The invariant checker evaluated metric presence using Python truthiness:
  ```python
  # Defective pattern:
  mdd = baseline_metrics.get("max_drawdown")
  if not mdd:
      # Handled as missing metric!
  ```
  In Python, `0.0` evaluates to `False`. When an equity curve experienced zero drawdown (a legitimate financial outcome for monotonic non-negative returns), `max_drawdown = 0.0` triggered the "missing metric" branch or caused invalid invariant failure.
- **Risk Impact:** False-positive invariant failures for portfolios or return series with zero loss or zero drawdown.
- **Resolution:** Refactored all metric presence checks to explicit key membership and `is None` checks:
  ```python
  # Corrected pattern:
  if "max_drawdown" not in baseline_metrics or baseline_metrics["max_drawdown"] is None:
      ...
  ```
- **Verification:** Tested in `test_verify_invariants_zero_drawdown_valid`.

---

### Defect 3: Non-Atomic Writes and Symlink Escape Vulnerability in `LocalExperimentCatalog` (`studio.py`)
- **Location:** `backend/fragility_engine/studio.py`, `LocalExperimentCatalog.save`
- **Root Cause:**
  1. `save()` opened the target file directly with `open(path, "w")`. A crash, out-of-disk condition, or process kill during serialization wrote truncated/corrupt files to the catalog.
  2. Path traversal checks only checked string components for `..` and `/`, but did not resolve symbolic links against `catalog_dir.resolve()`.
- **Risk Impact:** Catalog database corruption and possible symlink-based filesystem escape.
- **Resolution:**
  1. Implemented atomic file replacement: writes to a hidden temporary file in the catalog root (`.tmp_{id}_{uuid}`), flushes to disk using `f.flush()` and `os.fsync(f.fileno())`, and atomically replaces the destination via `os.replace()`.
  2. Added realpath / symlink resolution check: verifies `target_path.resolve().is_relative_to(catalog_dir.resolve())`.
- **Verification:** Tested in `test_catalog_atomic_write_durability` and `test_catalog_symlink_escape_rejected`.

---

## 3. Coverage Metric Clarification (Phase 6 vs Phase 7 vs Phase 8)

Previous documentation reported:
- Phase 6: 93.8% statement coverage, 87.3% branch coverage.
- Phase 7: 94.0% statement coverage, 87.4% branch coverage.

**Current Phase 8 Execution Measurement:**
- Total Statements: 2,283 (145 missed) $\rightarrow$ **93.65% Statement Coverage**
- Total Branches: 890 (116 missed) $\rightarrow$ **86.97% Branch Coverage**
- Pytest-Cov Combined Coverage: $\frac{2,138 + 774}{2,283 + 890} = \frac{2,912}{3,173} = \mathbf{91.77\% \approx 92\%}$
- Total Test Count: **323 passed**, 0 failed, 0 skipped.

All figures are grounded in actual test session execution outputs.
