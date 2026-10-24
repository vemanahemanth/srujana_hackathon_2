"""FragilityShield — Application Interface & REST API Engine (Phase 9).

This module provides a production-grade, typed, and secure Starlette application
serving the FragilityShield interactive research workspace and REST API.

Key Design Principles:
1. Pure Presentation & Orchestration: Directly delegates all quantitative calculations
   to the core `fragility_engine`. Never duplicates financial formulas in the API layer.
2. Robust Error Handling: Structured JSON error responses with HTTP status codes.
3. Security & Containment: Path traversal prevention, finite float validation, and safe JSON parsing.
4. Static Asset Hosting: Mounts `frontend/` static assets for single-command local execution.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import numpy as np
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from fragility_engine.backtest import (
    BacktestReport,
    backtest_model_rolling,
    calculate_christoffersen_test,
    calculate_kupiec_pof_test,
    evaluate_var_breaches,
)
from fragility_engine.benchmarks import (
    BenchmarkReport,
    BenchmarkSpecification,
    execute_model_benchmark,
)
from fragility_engine.concentration import (
    calculate_hhi,
    calculate_portfolio_concentration,
)
from fragility_engine.fragility import (
    calculate_ewma_volatility,
    calculate_portfolio_liquidation_shock,
    rank_perturbation_sensitivities,
    run_confidence_level_perturbation,
    run_correlation_perturbation,
    run_lookback_perturbation,
    run_return_friction_perturbation,
    run_volatility_estimator_perturbation,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import get_default_registry
from fragility_engine.portfolio_loader import (
    export_portfolio_to_csv,
    load_portfolio_from_csv,
    load_portfolio_from_json,
)
from fragility_engine.risk import (
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)
from fragility_engine.scenarios import (
    ScenarioDefinition,
    apply_scenario,
    create_preset_scenario,
)
from fragility_engine.studio import (
    LocalExperimentCatalog,
    StudioExperimentDefinition,
    execute_studio_experiment,
)

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "sample_portfolios"
CATALOG_DIR = BASE_DIR / "data" / "experiments"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR = BASE_DIR / "frontend"


# ==============================================================================
# Helper Utilities & Request Parsing
# ==============================================================================

def json_error(message: str, status_code: int = 400, error_type: str = "validation_error", detail: Optional[Any] = None) -> JSONResponse:
    """Standardized JSON error envelope."""
    payload = {
        "success": False,
        "error": message,
        "type": error_type,
    }
    if detail is not None:
        payload["detail"] = detail
    return JSONResponse(payload, status_code=status_code)


def sanitize_filename(filename: str) -> str:
    """Prevent directory traversal attacks."""
    base = os.path.basename(filename)
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Unsafe filename detected: '{filename}'")
    return base


def parse_portfolio_from_dict(data: Mapping[str, Any]) -> Portfolio:
    """Parse and validate Portfolio domain object from dictionary."""
    if not isinstance(data, dict):
        raise TypeError("Portfolio data must be a JSON object")

    portfolio_id = str(data.get("portfolio_id", "custom_portfolio")).strip()
    name = str(data.get("name", "Custom Portfolio")).strip()
    currency = str(data.get("currency", "INR")).strip()
    holdings_raw = data.get("holdings", [])

    if not holdings_raw:
        raise ValueError("Portfolio must contain at least one holding")

    holdings: List[Holding] = []
    for idx, h in enumerate(holdings_raw):
        if not isinstance(h, dict):
            raise TypeError(f"Holding at index {idx} must be a dictionary")
        asset_id = str(h.get("asset_id", "")).strip()
        quantity = float(h.get("quantity", 0.0))
        price = float(h.get("price", 0.0))
        sector = str(h.get("sector", "")).strip() or None
        holdings.append(Holding(asset_id=asset_id, quantity=quantity, price=price, sector=sector))

    return Portfolio(
        portfolio_id=portfolio_id,
        name=name,
        currency=currency,
        holdings=holdings,
        metadata=dict(data.get("metadata", {})),
    )


def get_default_sample_returns() -> List[float]:
    """Deterministic synthetic benchmark returns fixture (60 days) for quick demonstrations."""
    np.random.seed(42)
    rets = np.random.normal(0.0006, 0.014, 60).tolist()
    return [round(r, 6) for r in rets]


# ==============================================================================
# API Endpoints
# ==============================================================================

async def api_health(request: Request) -> JSONResponse:
    """System health, engine versions, and capabilities discovery."""
    registry = get_default_registry()
    plugins_summary = [
        {
            "plugin_id": p.plugin_id,
            "name": p.name,
            "version": p.plugin_version,
            "capabilities": list(p.capabilities),
            "description": p.description,
        }
        for p in registry.list_plugins()
    ]

    sample_portfolios = []
    if DATA_DIR.exists():
        sample_portfolios = [f.name for f in DATA_DIR.glob("*") if f.is_file() and f.suffix in (".json", ".csv")]

    return JSONResponse({
        "success": True,
        "status": "healthy",
        "engine": "FragilityShield Quantitative Engine",
        "version": "0.1.0",
        "phase": "Phase 9 — Interactive Risk, Scenario & Fragility Lab",
        "registered_models": plugins_summary,
        "sample_portfolios": sample_portfolios,
        "preset_scenarios": ["banking_minus_20_it_minus_10"],
        "differentiator": "Investigates how risk estimates change when the assumptions behind them change.",
    })


async def api_load_sample_portfolio(request: Request) -> JSONResponse:
    """Load bundled sample portfolio fixtures."""
    sample_id = request.query_params.get("id", "nse_10l.json")
    try:
        clean_name = sanitize_filename(sample_id)
        target_path = DATA_DIR / clean_name
        if not target_path.exists():
            return json_error(f"Sample portfolio fixture '{clean_name}' not found", status_code=404)

        if target_path.suffix == ".json":
            portfolio = load_portfolio_from_json(target_path)
        elif target_path.suffix == ".csv":
            portfolio = load_portfolio_from_csv(target_path, portfolio_id="nse_10l_csv", name="NSE 10L CSV Portfolio")
        else:
            return json_error(f"Unsupported fixture format: '{target_path.suffix}'")

        concentration = calculate_portfolio_concentration(portfolio)
        return JSONResponse({
            "success": True,
            "portfolio": portfolio.to_dict(),
            "concentration": concentration.to_dict(),
        })
    except Exception as exc:
        return json_error(f"Failed to load sample portfolio: {exc}", status_code=400)


async def api_validate_portfolio(request: Request) -> JSONResponse:
    """Validate user-supplied portfolio JSON or CSV content."""
    try:
        body = await request.json()
        raw_format = body.get("format", "json").lower()
        raw_content = body.get("content")

        if not raw_content:
            if "holdings" in body:
                portfolio = parse_portfolio_from_dict(body)
            else:
                return json_error("Missing portfolio content or holdings list")
        elif raw_format == "json":
            data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            portfolio = parse_portfolio_from_dict(data)
        elif raw_format == "csv":
            stream = io.StringIO(raw_content)
            portfolio = load_portfolio_from_csv(stream, portfolio_id="uploaded_csv", name="Uploaded CSV Portfolio")
        else:
            return json_error(f"Unsupported format: '{raw_format}'. Must be 'json' or 'csv'.")

        concentration = calculate_portfolio_concentration(portfolio)
        return JSONResponse({
            "success": True,
            "portfolio": portfolio.to_dict(),
            "concentration": concentration.to_dict(),
        })
    except Exception as exc:
        return json_error(f"Portfolio validation error: {exc}", status_code=400)


async def api_calculate_concentration(request: Request) -> JSONResponse:
    """Calculate asset weights, sector allocations, HHI decimal, and HHI points."""
    try:
        body = await request.json()
        portfolio = parse_portfolio_from_dict(body.get("portfolio", body))
        conc = calculate_portfolio_concentration(portfolio)
        warnings = []
        if conc.asset_hhi_points > 2500:
            warnings.append("High asset concentration (HHI > 2500 points). Single-asset idiosyncratic risks dominate.")
        if conc.sector_hhi_points > 2500:
            warnings.append("High sector concentration (HHI > 2500 points). Sectoral shocks will strongly impact portfolio.")
        return JSONResponse({
            "success": True,
            "concentration": conc.to_dict(),
            "warnings": warnings,
        })
    except Exception as exc:
        return json_error(f"Concentration calculation error: {exc}", status_code=400)


async def api_calculate_risk(request: Request) -> JSONResponse:
    """Calculate risk report (Volatility, VaR 95/99, ES 95/99, Drawdowns) with explanation panels."""
    try:
        body = await request.json()
        raw_returns = body.get("returns")
        if not raw_returns:
            # Use deterministic sample returns if not provided
            raw_returns = get_default_sample_returns()

        arr = np.asarray(raw_returns, dtype=np.float64)
        if len(arr) < 4:
            return json_error(f"Risk calculation requires at least 4 return observations; got {len(arr)}")
        if not np.all(np.isfinite(arr)):
            return json_error("Return series contains non-finite values (NaN or Inf)")

        confidence_level = float(body.get("confidence_level", 0.95))
        annualization_factor = float(body.get("annualization_factor", 252.0))
        ddof = int(body.get("ddof", 1))

        report = calculate_risk_report(
            arr,
            annualization_factor=annualization_factor,
            ddof=ddof,
        )

        custom_var = calculate_historical_var(arr, confidence_level=confidence_level)
        custom_es = calculate_expected_shortfall(arr, confidence_level=confidence_level)

        # Build equity curve for visualization
        equity_curve = [1.0]
        for r in arr:
            equity_curve.append(round(equity_curve[-1] * (1.0 + float(r)), 6))

        dd_info = "No drawdown periods detected."
        if report.drawdown is not None:
            rec_dur = str(report.drawdown.recovery_duration) if report.drawdown.recovery_duration is not None else "Unrecovered"
            dd_info = f"Peak-to-trough: {report.drawdown.peak_to_trough_duration} periods, Recovery: {rec_dur} periods."

        explanation_panels = {
            "volatility": {
                "name": "Annualized Historical Volatility",
                "formula": r"\sigma_{ann} = \sqrt{\frac{1}{N-ddof}\sum (r_i - \bar{r})^2} \times \sqrt{252}",
                "unit": "decimal fraction / annualized",
                "interpretation": "Measures total return dispersion. Does not distinguish upside from downside volatility.",
            },
            "var": {
                "name": f"Value at Risk ({confidence_level*100:.0f}%)",
                "formula": r"\text{VaR}_\alpha(L) = \inf \{ l \in \mathbb{R} : P(L > l) \le 1 - \alpha \}",
                "loss_convention": "Positive loss fraction (L = -R). A VaR of 0.024 means a 2.4% maximum expected loss at stated confidence.",
                "interpretation": "Evaluates threshold loss. Does not describe the severity of losses beyond the threshold.",
            },
            "expected_shortfall": {
                "name": f"Expected Shortfall / CVaR ({confidence_level*100:.0f}%)",
                "formula": r"\text{ES}_\alpha(L) = \frac{1}{1-\alpha}\int_\alpha^1 \text{VaR}_u(L) du",
                "coherence": "Acerbi & Tasche (2002) fractional weighting guarantees sub-additivity and coherence: ES >= VaR.",
                "interpretation": "Average loss incurred when the VaR threshold is breached.",
            },
            "drawdown": {
                "name": "Maximum Drawdown & Duration",
                "formula": r"\text{MDD} = \max_{0 \le s \le t} \frac{P_s - P_t}{P_s}",
                "duration_metrics": dd_info,
            },
        }

        return JSONResponse({
            "success": True,
            "report": report.to_dict(),
            "confidence_level": confidence_level,
            "custom_var": float(custom_var),
            "custom_es": float(custom_es),
            "observations_count": len(arr),
            "equity_curve": equity_curve,
            "explanation_panels": explanation_panels,
        })
    except Exception as exc:
        return json_error(f"Risk calculation error: {exc}", status_code=400)



async def api_execute_scenario(request: Request) -> JSONResponse:
    """Stress-test portfolio against market or sector shocks with full P&L reconciliation."""
    try:
        body = await request.json()
        portfolio_raw = body.get("portfolio")
        if not portfolio_raw:
            return json_error("Missing 'portfolio' object in request")
        portfolio = parse_portfolio_from_dict(portfolio_raw)

        preset_id = body.get("preset_id")
        if preset_id:
            scenario = create_preset_scenario(preset_id)
        else:
            scenario_id = str(body.get("scenario_id", "custom_stress_scenario")).strip()
            name = str(body.get("name", "Custom Stress Scenario")).strip()
            description = str(body.get("description", "User-configured stress shock")).strip()
            sector_shocks = {str(k): float(v) for k, v in body.get("sector_shocks", {}).items()}
            asset_shocks = {str(k): float(v) for k, v in body.get("asset_shocks", {}).items()}
            scenario = ScenarioDefinition(
                scenario_id=scenario_id,
                name=name,
                description=description,
                sector_shocks=sector_shocks,
                asset_shocks=asset_shocks,
            )

        res = apply_scenario(portfolio, scenario)
        return JSONResponse({
            "success": True,
            "scenario_result": res.to_dict(),
            "disclaimer": "HYPOTHETICAL STRESS SCENARIO ONLY. Stressed valuations represent static sensitivity models and are NOT predictive forecasts of future market movements.",
        })
    except Exception as exc:
        return json_error(f"Scenario execution error: {exc}", status_code=400)


async def api_run_fragility(request: Request) -> JSONResponse:
    """Execute assumption attacks (lookback shifts, volatility estimators, friction, liquidation)."""
    try:
        body = await request.json()
        raw_returns = body.get("returns") or get_default_sample_returns()
        arr = np.asarray(raw_returns, dtype=np.float64)

        if len(arr) < 20:
            return json_error(f"Fragility analysis requires at least 20 return observations; got {len(arr)}")

        experiments = []

        # 1. Lookback Window Perturbation
        win_short = int(body.get("lookback_short", 20))
        win_long = int(body.get("lookback_long", min(len(arr), 60)))
        exp_lookback = run_lookback_perturbation(arr, perturbed_window=win_short, baseline_window=win_long)
        experiments.append(exp_lookback)

        # 2. Volatility Estimator (Sample vs RiskMetrics EWMA)
        decay = float(body.get("decay_factor", 0.94))
        exp_vol_est = run_volatility_estimator_perturbation(arr, decay_factor=decay)
        experiments.append(exp_vol_est)

        # 3. Transaction Friction Drag (e.g. 10 bps)
        friction_bps = float(body.get("friction_bps", 10.0))
        exp_friction = run_return_friction_perturbation(arr, friction_bps=friction_bps)
        experiments.append(exp_friction)

        # 4. Confidence Level Shift (95% vs 99%)
        exp_conf = run_confidence_level_perturbation(arr, perturbed_confidence=0.99, baseline_confidence=0.95)
        experiments.append(exp_conf)

        # 5. Optional Liquidation Shock if portfolio provided
        liquidation_result = None
        portfolio_raw = body.get("portfolio")
        if portfolio_raw:
            try:
                port = parse_portfolio_from_dict(portfolio_raw)
                liquidation_result = calculate_portfolio_liquidation_shock(port, cost_bps=25.0, turnover_fraction=1.0)
            except Exception:
                pass

        # Sensitivity ranking across experiments for volatility and VaR
        ranking_vol = rank_perturbation_sensitivities(experiments, target_metric="volatility_annualized")
        ranking_var = rank_perturbation_sensitivities(experiments, target_metric="var_95")

        return JSONResponse({
            "success": True,
            "experiments": [e.to_dict() for e in experiments],
            "sensitivity_rankings": {
                "volatility_annualized": ranking_vol.to_dict(),
                "var_95": ranking_var.to_dict(),
            },
            "liquidation_shock": liquidation_result,
            "differentiator_notice": "FRAGILITY DISCOVERY: Identifies which modeling assumptions produce the largest variance in reported risk estimates.",
        })
    except Exception as exc:
        return json_error(f"Fragility experiment error: {exc}", status_code=400)


async def api_list_benchmark_models(request: Request) -> JSONResponse:
    """List registered quantitative model plugins with capabilities and limitations."""
    registry = get_default_registry()
    models = [
        {
            "plugin_id": p.plugin_id,
            "name": p.name,
            "version": p.plugin_version,
            "supported_data_types": list(p.supported_data_types),
            "capabilities": list(p.capabilities),
            "description": p.description,
            "limitations": list(p.limitations),
        }
        for p in registry.list_plugins()
    ]
    return JSONResponse({"success": True, "models": models})


async def api_execute_benchmark(request: Request) -> JSONResponse:
    """Execute multi-model comparative benchmark with directional rankings and disclaimers."""
    try:
        body = await request.json()
        benchmark_id = str(body.get("benchmark_id", "bench_interactive")).strip()
        name = str(body.get("name", "Comparative Risk Benchmark")).strip()
        description = str(body.get("description", "Multi-model evaluation")).strip()
        plugin_ids = tuple(body.get("plugin_ids", ["builtin.parametric_gaussian", "builtin.historical_simulation", "builtin.ewma"]))
        metrics = tuple(body.get("metrics_to_compare", ["var_95", "volatility_annualized"]))
        ranking_direction = str(body.get("ranking_direction", "lower_is_better"))
        target_ranking_metric = body.get("target_ranking_metric", "var_95")
        evaluation_mode = str(body.get("evaluation_mode", "in_sample_descriptive"))

        spec = BenchmarkSpecification(
            benchmark_id=benchmark_id,
            name=name,
            description=description,
            dataset_id=str(body.get("dataset_id", "returns_sample")),
            plugin_ids=plugin_ids,
            metrics_to_compare=metrics,
            ranking_direction=ranking_direction,
            target_ranking_metric=target_ranking_metric,
            evaluation_mode=evaluation_mode,
        )

        dataset = body.get("dataset")
        if not dataset:
            dataset = get_default_sample_returns()

        report = execute_model_benchmark(spec, dataset)
        return JSONResponse({
            "success": True,
            "report": report.to_dict(),
            "markdown_preview": report.to_markdown(),
        })
    except Exception as exc:
        return json_error(f"Model benchmark error: {exc}", status_code=400)


async def api_run_backtest(request: Request) -> JSONResponse:
    """Execute out-of-sample rolling walk-forward VaR backtest with Kupiec and Christoffersen tests."""
    try:
        body = await request.json()
        model_id = str(body.get("model_id", "builtin.parametric_gaussian")).strip()
        returns_raw = body.get("returns")

        if not returns_raw:
            # Generate 90-day benchmark return series for backtesting
            np.random.seed(123)
            returns_raw = np.random.normal(0.0004, 0.015, 90).tolist()

        arr = np.asarray(returns_raw, dtype=np.float64)
        estimation_window = int(body.get("estimation_window", 40))
        confidence_level = float(body.get("confidence_level", 0.95))
        step_size = int(body.get("step_size", 1))

        if len(arr) < estimation_window + 5:
            return json_error(
                f"Backtest requires returns length >= estimation_window + 5 (minimum {estimation_window + 5}); got {len(arr)}"
            )

        report = backtest_model_rolling(
            model=model_id,
            returns=arr,
            estimation_window=estimation_window,
            confidence_level=confidence_level,
            step_size=step_size,
        )

        return JSONResponse({
            "success": True,
            "report": report.to_dict(),
            "markdown_preview": report.to_markdown(),
        })
    except Exception as exc:
        return json_error(f"Backtesting error: {exc}", status_code=400)


async def api_studio_catalog(request: Request) -> JSONResponse:
    """Retrieve catalog of saved experiments and comparison capabilities."""
    try:
        catalog = LocalExperimentCatalog(CATALOG_DIR)
        reports = catalog.list_reports()
        return JSONResponse({
            "success": True,
            "reports_count": len(reports),
            "reports": reports,
        })
    except Exception as exc:
        return json_error(f"Failed to query experiment catalog: {exc}", status_code=400)


async def api_execute_studio_experiment(request: Request) -> JSONResponse:
    """Execute unified Studio Experiment and record cryptographic reproducibility manifest."""
    try:
        body = await request.json()
        experiment_id = str(body.get("experiment_id", "studio_exp_01")).strip()
        name = str(body.get("name", "Studio Fragility Audit")).strip()
        description = str(body.get("description", "Interactive studio experiment")).strip()
        dataset_raw = body.get("dataset")
        if not dataset_raw:
            dataset_raw = get_default_sample_returns()

        arr = np.asarray(dataset_raw, dtype=np.float64)

        definition = StudioExperimentDefinition(
            experiment_id=experiment_id,
            name=name,
            description=description,
            dataset_id=str(body.get("dataset_id", "default_returns")),
            target_ranking_metric=str(body.get("target_ranking_metric", "var_95")),
            baseline_config={"confidence_level": 0.95, "annualization_factor": 252.0},
            perturbation_specs=[
                {
                    "type": "return_friction",
                    "experiment_id": f"{experiment_id}_fric_10bps",
                    "parameters": {"friction_bps": 10.0},
                },
                {
                    "type": "lookback_window",
                    "experiment_id": f"{experiment_id}_lookback_30",
                    "parameters": {"lookback_window": 30},
                },
            ],
        )

        report = execute_studio_experiment(definition, arr)
        catalog = LocalExperimentCatalog(CATALOG_DIR)
        catalog.save_report(report, overwrite=True)

        return JSONResponse({
            "success": True,
            "report": report.to_dict(),
            "markdown_preview": report.to_markdown(),
        })
    except Exception as exc:
        return json_error(f"Studio experiment error: {exc}", status_code=400)


async def api_export_report(request: Request) -> Response:
    """Export formatted report as JSON, Markdown, or CSV."""
    try:
        body = await request.json()
        report_type = body.get("type", "benchmark")
        export_format = body.get("format", "markdown").lower()
        report_data = body.get("report_data", {})

        if not report_data:
            return json_error("Missing report_data to export")

        if report_type == "benchmark":
            report_obj = BenchmarkReport.from_dict(report_data)
        elif report_type == "backtest":
            report_obj = BacktestReport.from_dict(report_data)
        else:
            return json_error(f"Unsupported report type: '{report_type}'")

        if export_format == "json":
            return Response(report_obj.to_json(indent=2), media_type="application/json")
        elif export_format == "markdown":
            return Response(report_obj.to_markdown(), media_type="text/markdown")
        else:
            return json_error(f"Format '{export_format}' not supported for this report type")
    except Exception as exc:
        return json_error(f"Export error: {exc}", status_code=400)


# ==============================================================================
# Application Factory
# ==============================================================================

def create_application() -> Starlette:
    """Build and configure the Starlette application with routes and middleware."""
    routes = [
        Route("/api/health", api_health, methods=["GET"]),
        Route("/api/portfolios/sample", api_load_sample_portfolio, methods=["GET"]),
        Route("/api/portfolios/validate", api_validate_portfolio, methods=["POST"]),
        Route("/api/portfolios/concentration", api_calculate_concentration, methods=["POST"]),
        Route("/api/risk/calculate", api_calculate_risk, methods=["POST"]),
        Route("/api/scenarios/execute", api_execute_scenario, methods=["POST"]),
        Route("/api/fragility/run", api_run_fragility, methods=["POST"]),
        Route("/api/benchmarks/models", api_list_benchmark_models, methods=["GET"]),
        Route("/api/benchmarks/execute", api_execute_benchmark, methods=["POST"]),
        Route("/api/backtest/run", api_run_backtest, methods=["POST"]),
        Route("/api/studio/catalog", api_studio_catalog, methods=["GET"]),
        Route("/api/studio/experiment", api_execute_studio_experiment, methods=["POST"]),
        Route("/api/export", api_export_report, methods=["POST"]),
    ]

    # Mount static frontend directory if it exists
    if FRONTEND_DIR.exists():
        routes.append(Mount("/", app=StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static"))

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )
    ]

    return Starlette(debug=False, routes=routes, middleware=middleware)


app = create_application()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
