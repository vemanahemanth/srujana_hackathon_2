# FragilityShield — Phase 7: Issue Review Report

**Date:** 2026-10-24  
**Auditor / Reviewer:** Principal Software Architect, Quantitative Risk Engineer & Test Engineer  
**Baseline Git Commit:** `5435ee4`  
**Scope:** Architecture and issue review for Phase 7 Experiment Studio, structured reporting (JSON, Markdown, CSV), cross-experiment comparison, and local catalog indexing.

---

## 1. Carried-Forward Issues from Phase 6 Verification

| Issue ID | Domain / Area | Previous Hypothesis / Limitation | Phase 7 Architectural Resolution | Status |
| :--- | :--- | :--- | :--- | :--- |
| **ISSUE-6-LIM-1** | **Dataset Provenance vs Storage** | SHA-256 input fingerprints verify dataset identity and detect drift, but cannot reconstruct a missing or deleted dataset. | Handled. `StudioExperimentDefinition` and `ExperimentReport` include explicit `dataset_id`, optional `dataset_provenance` (source URI, ingestion timestamp, commit), and document the data boundary limitation in report exports. | **Documented & Handled** |
| **ISSUE-6-LIM-2** | **Cross-Platform Float Divergence** | Slight IEEE 754 differences between architectures (e.g. ARM64 NEON vs x86-64 AVX) or BLAS libraries can produce minor drift at machine epsilon ($10^{-16}$). | Handled. `compare_experiment_reports` and `compare_experiment_runs` support configurable comparison tolerance (default $\epsilon = 10^{-6}$), isolating floating-point rounding from genuine model drift. | **Configurable Tolerance** |

---

## 2. Phase 7 Engineering & Security Issues Addressed

| Issue ID | Domain / Area | Technical Challenge / Vulnerability | Review Finding & Engineering Resolution | Final Status |
| :--- | :--- | :--- | :--- | :--- |
| **ISSUE-7-A** | **Path Traversal in Experiment Identifiers** | Experiment IDs supplied by users or external systems can be formatted as filenames (`../../etc/passwd` or `dir/file`). | Resolved. Implemented strict path-traversal sanitization in both `StudioExperimentDefinition` and `LocalExperimentCatalog`. Disallows `..`, `/`, `\`, null bytes, and path delimiters. Rejects unsafe identifiers with explicit `ValueError`. | **Resolved & Tested** |
| **ISSUE-7-B** | **Unit & Sign Preservation Across Formats** | Financial metrics have varied unit dimensions: HHI (points $0-10000$ vs decimal $0-1$), VaR/ES/Volatility/MDD (decimal fraction vs percentage), and P&L/Costs (currency). Exporting flattened strings causes ambiguity. | Resolved. Implemented explicit unit categorization (`points (0-10000)`, `decimal fraction`, `currency`, `ratio`) in `_format_metric_unit` and `_format_metric_value`. CSV export maintains dedicated `unit` column; Markdown tables display both decimal and percentage representations. | **Resolved & Tested** |
| **ISSUE-7-C** | **Honest Failure & Partial Result Isolation** | If a perturbation fails or data is missing, naive orchestrators either crash unhandled or swallow errors and mark the run as successful. | Resolved. Implemented explicit 4-state status machine in `execute_studio_experiment`: `completed`, `completed_with_warnings`, `failed_validation`, and `failed_execution`. Errors in perturbations are isolated, logged under `warnings`, and partial results are flagged honestly without masking. | **Resolved & Tested** |
| **ISSUE-7-D** | **Cross-Experiment Comparability Semantics** | Comparing experiments executed on different datasets or different calculation methods without warning produces misleading risk signals. | Resolved. Implemented `StudioComparisonReport` via `compare_experiment_reports`. Formally validates comparability by verifying matching `dataset_id` and input fingerprints. Incompatible runs are flagged with explicit `non_comparable_reasons` while still itemizing baseline differences. | **Resolved & Tested** |
| **ISSUE-7-E** | **Local Catalog Safety & Overwrite Protection** | Storing reports in local filesystems can risk accidental overwrites of prior audit trails or crash on corrupted JSON files. | Resolved. Implemented `LocalExperimentCatalog`: enforces `overwrite=False` by default (raising `FileExistsError`); handles corrupted JSON gracefully by skipping in listings and reporting a detailed diagnostic on direct retrieval; includes safe path-sanitized deletion. | **Resolved & Tested** |

---

## 3. Architecture & Design Principles

1. **Pure Framework Independence:**
   No external web servers, web frameworks, external databases, cloud connectors, or UI components were introduced. The engine operates purely using standard Python 3.14 + NumPy.
2. **Deterministic Serialization:**
   All reports serialize to RFC 8259-compliant JSON using canonical alphabetical key sorting and float precision control, guaranteeing idempotent round-trips.
3. **Immutability & Audit Trail:**
   `StudioExperimentDefinition`, `ExperimentReport`, and `StudioComparisonReport` are immutable dataclasses. Reproducibility manifests are embedded inside every generated report.
