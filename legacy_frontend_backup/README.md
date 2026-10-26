# FragilityShield Frontend

## Planned Role & Architecture

This directory is reserved for the FragilityShield interactive research and model-testing dashboard, to be scaffolded and implemented in a subsequent phase.

### Key Objectives
1. **No Formula Reimplementation:** The frontend strictly acts as a presentation and interaction layer. It consumes REST API endpoints from the backend and **never** duplicates financial risk calculations, volatility formulas, or scenario algorithms.
2. **Planned Technology Stack:**
   - **Framework:** React 18+ with TypeScript, bundled using Vite.
   - **Design System:** Bespoke dark-mode aesthetic utilizing modern typography (`Outfit` / `Inter`), glassmorphism cards, and curated high-contrast tokens.
   - **Visualizations:** Interactive charts for return series, drawdown cones, sector allocations, and fragility impact sensitivity bars.
   - **Active Context Bar:** Persistent portfolio context selector showing current total value, currency, holding count, and valuation date across all pages.
3. **Target Pages:**
   - **Overview:** Executive summary, recent experiments, active portfolio KPI cards.
   - **Portfolio Lab:** Portfolio CRUD, CSV import, holdings inspection, asset allocation, and HHI concentration analysis.
   - **Risk Lab:** Volatility, Historical VaR, Expected Shortfall (CVaR), and Maximum Drawdown.
   - **Scenario Lab:** Preset market shocks (Banking -20%, IT -10%) and sector loss attribution.
   - **Fragility Lab:** Assumption attack execution, ranking of parameter sensitivities, and delta comparisons.
   - **Validation Lab:** Conformance testing, formula reference checks, and reproducibility validation.
   - **Experiment Studio:** Run configuration, historical run logs, and HTML/CSV report exports.
