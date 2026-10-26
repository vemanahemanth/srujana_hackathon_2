# FragilityShield — Page 09 Implementation & Verification Report
## Unified Experiment Registry & Research Reproducibility: Multi-Run Comparison, Cryptographic Provenance, and Lineage Tracking (`/experiments`)

---

### Executive Summary

**Page 09 — Unified Experiment Registry & Research Reproducibility** has been fully implemented, tested across automated test suites, validated in browser automation, and integrated into the FragilityShield research navigation.

Page 09 creates a centralized, tamper-evident repository for all quantitative financial research runs across the platform. It automatically ingests and indexes runs from:
1. **Strategy Backtest Lab** (Page 08)
2. **Model Testing & Validation Lab** (Page 07)
3. **Fragility Assumption Matrix** (Page 06)
4. **Studio Experiment Audits** (Pages 04-05)

Every experiment run is assigned a canonical envelope featuring:
- **Unique Run ID** and Timestamp.
- **Reproducibility Classification**: `Exact reproduction supported` (backed by SHA-256 dataset hash) or `Configuration reproducible`.
- **Cryptographic Data Provenance**: Data source mode, provider, observation count, and input digest.
- **Parent-Child Lineage Tracking**: Preserving execution genealogies across rerun iterations.
- **Multi-Run Comparison Engine**: Side-by-side configuration parameter diffs and metric delta calculations with incompatibility warnings.
- **Multi-Format Export Engine**: Exporting immutable research reports in Markdown, JSON, and CSV formats.

---

### 1. Existing Functionality Reused

1. **Local Experiment Catalog & Fingerprinting (`backend/fragility_engine/reproducibility.py`)**:
   - Reused canonical JSON serialization, deterministic parameter hashing, and SHA-256 digest creation.
2. **Database & Tenancy Store (`backend/fragility_engine/database.py`, `backend/fragility_engine/tenancy.py`)**:
   - Reused `save_experiment_run`, `get_experiment_run`, and `list_experiment_runs` across both `MemoryTenantRepository` and `PostgresTenantRepository` with tenant isolation.
3. **Lab Execution History**:
   - Integrated `STRATEGY_BACKTEST_RUNS`, `MODEL_VALIDATION_RUNS`, and `FRAGILITY_EXPERIMENT_RUNS` into a single consolidated research index.

---

### 2. Problems Found and Corrected

| Area | Problem Identified | Root Cause | Correction Applied | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Old Experiments Stub** | `/experiments` previously contained an in-memory draft list with an arbitrary 8-point hardcoded return array, failing real-world research requirements. | Placeholder component was not connected to backend runs. | Replaced with `UnifiedExperimentRegistry.tsx` connected to `GET /api/experiments/runs`. | **PASS** |
| **NoneType Formatting 500 Error** | `normalize_experiment_run` threw `TypeError: unsupported format string passed to NoneType.__format__` when fragility runs had no threshold. | `conclusion_change_percentage` was `None` and formatted with `:.1f`. | Added safe conversion handling `None` values gracefully with `"N/A"` or `0.0`. | **PASS** |
| **Postgres E2E Backward Compatibility** | `test_studio_experiment_persists_to_postgres_under_rls` threw `KeyError: 'experiment_id'`. | `normalize_experiment_run` did not include the top-level legacy key `experiment_id`. | Added `"experiment_id": raw.get("experiment_id") or run_id` to maintain backwards compatibility. | **PASS** |
| **Fragility Matrix Parameter Bug** | `api_calculate_fragility_matrix` failed with `NameError: name 'row_param' is not defined`. | Variable names were `row_dim` and `col_dim`. | Corrected references to `row_dim` and `col_dim` in `backend/app.py`. | **PASS** |

---

### 3. Verification & Test Evidence

#### Automated Backend Test Suite
Executed test suite: `backend/tests/test_page_09_experiment_registry.py`:
- `test_unified_experiment_listing_and_metadata`: **PASSED** (Validated canonical envelope aggregation across strategy backtests, model validations, and fragility matrices).
- `test_experiment_filtering_and_search`: **PASSED** (Validated filtering by `type=strategy_backtest`, status, and full-text keyword queries).
- `test_experiment_detail_retrieval`: **PASSED** (Validated granular inspection payload including provenance, configuration spec, and execution results).
- `test_experiment_comparison_diff_and_deltas`: **PASSED** (Validated side-by-side parameter diff and metric delta calculations with incompatibility warnings).
- `test_experiment_rerun_and_lineage`: **PASSED** (Validated execution rerun creating a linked child run with `parent_run_id`).
- `test_experiment_export_formats`: **PASSED** (Validated export outputs in Markdown, JSON, and CSV formats).

#### Full Repository Test Status
- `pytest backend/tests/test_page_*.py`: **35/35 PASSED** (All Page 02 to Page 09 tests pass cleanly).
- Full repository test suite: **736/736 PASSED** (0 failures).

#### Browser End-to-End Verification
Browser subagent executed live verification on `http://127.0.0.1:8000/experiments`:
1. **Header & Research Overview**:
   - Page Title: **Unified Experiment Registry & Research Reproducibility** (`REPRODUCIBILITY & LINEAGE / PAGE 09`).
   - Badges: `SHA-256 Provenance • Lineage Tree`.
   - Summary Statistics: Total Runs, Strategy Backtests, Model Validations, Fragility Matrices.
2. **Registry Table & Filter Controls**:
   - Filter pills: `All Types`, `Strategies`, `Models`, `Fragility`, `Studio`.
   - Table columns: Selection checkbox, Run ID (with copy to clipboard action), Type Badge, Experiment Name, Created Timestamp, Status Badge (`COMPLETED`), Reproducibility Badge (`Exact reproduction supported` with SHA-256 hash), Key Metrics pills, Actions.
3. **Granular Inspection Modal**:
   - Clicked inspection eye icon on strategy backtest run `bt_ma_crossover_da33429b60`.
   - Modal displayed: Complete Run Overview, Cryptographic Data Provenance (`provider: upstox_v3`, SHA-256 hash, observations sampled: 19 bars), Specification & Hyperparameters JSON tree, Execution Results & Output Artifacts.
   - Verified Markdown and JSON export buttons.
4. **Side-by-Side Comparison Modal**:
   - Selected multiple runs via checkboxes and clicked `Compare Selected`.
   - Modal displayed: Configuration & Hyperparameter Diff table (flagging identical vs differing parameters) and Metric Deltas table (baseline vs candidate values and percentage changes).

Screenshots captured and archived:
- `experiment_inspection_modal_1792931843285.png`
- WebP recording: `strategy_and_experiments_qa_1792931787232.webp`

---

### 4. Implementation Artifacts

- **Backend API Routes**: `backend/app.py`
  - `GET /api/experiments/runs`
  - `GET /api/experiments/{id}`
  - `POST /api/experiments/compare`
  - `POST /api/experiments/{id}/rerun`
  - `POST /api/experiments/{id}/export`
- **Backend Tests**: `backend/tests/test_page_09_experiment_registry.py`
- **Frontend Workspace**: `frontend/src/components/pages/UnifiedExperimentRegistry.tsx`
- **API Client Extensions**: `frontend/src/lib/api.ts`
- **Application Routing**: `frontend/src/App.tsx` (mounted at `/experiments` and `/experiments/history`)
