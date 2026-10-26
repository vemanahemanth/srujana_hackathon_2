import React, { useEffect, useState } from 'react';
import { api, Portfolio } from '@/lib/api';
import {
  ShieldAlert, Sliders, RefreshCw, Layers, Activity, AlertTriangle,
  ArrowRight, Download, CheckCircle2, ChevronRight, X, Info,
  TrendingDown, TrendingUp, BarChart2, FileText, Compass, CornerDownRight
} from 'lucide-react';

interface MatrixCell {
  row_index: number;
  col_index: number;
  row_value: number | string;
  col_value: number | string;
  value: number | null;
  baseline_value: number;
  absolute_change?: number;
  relative_change?: number;
  percentage_change?: number;
  sample_size?: number;
  status: 'completed' | 'insufficient_data' | 'failed';
  warning?: string | null;
}

interface MatrixDiagnostics {
  baseline_value: number;
  min_value: number;
  max_value: number;
  absolute_sensitivity_range: number;
  relative_sensitivity_range: number;
  completed_runs: number;
  failed_runs: number;
  insufficient_data_runs: number;
  conclusion_threshold?: number;
  conclusion_operator?: string;
  conclusion_breaches?: number;
  total_valid_runs?: number;
  conclusion_change_percentage?: number | null;
  conclusion_change_ratio?: string;
}

interface AssumptionCatalogItem {
  model_id: string;
  model_name: string;
  family: string;
  mathematical_formulation: string;
  distributional_assumption: string;
  temporal_assumption: string;
  sample_size_precondition: string;
  parameter_assumptions: string[];
  known_failure_regimes: string[];
  fragility_attack_vulnerabilities: string[];
}

interface FragilityAuditExperiment {
  experiment_id: string;
  perturbation_id: string;
  perturbation_name: string;
  description: string;
  configuration: Record<string, any>;
  baseline_metrics: Record<string, number>;
  perturbed_metrics: Record<string, number>;
  absolute_changes: Record<string, number>;
  relative_changes: Record<string, number>;
  percentage_changes: Record<string, number>;
  observations_used: number;
  warnings: string[];
  limitations: string;
}

export function FragilityAssumptionMatrix({
  navigate,
  notify,
}: {
  navigate: (path: string) => void;
  notify: (msg: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<'matrix' | 'challenge' | 'ranking' | 'catalogue' | 'history'>('matrix');
  const [loading, setLoading] = useState(false);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<string>('sample_nse_10l');
  const [activePortfolio, setActivePortfolio] = useState<Portfolio | null>(null);

  // Matrix configuration
  const [targetMetric, setTargetMetric] = useState<string>('var_95');
  const [rowDim, setRowDim] = useState<string>('lookback_window');
  const [colDim, setColDim] = useState<string>('confidence_level');
  const [conclusionThreshold, setConclusionThreshold] = useState<number>(0.025);
  const [conclusionOperator, setConclusionOperator] = useState<string>('>');

  // Matrix results
  const [rowValues, setRowValues] = useState<(number | string)[]>([30, 60, 120, 252]);
  const [colValues, setColValues] = useState<(number | string)[]>([0.90, 0.95, 0.975, 0.99]);
  const [matrixCells, setMatrixCells] = useState<MatrixCell[]>([]);
  const [matrixDiagnostics, setMatrixDiagnostics] = useState<MatrixDiagnostics | null>(null);
  const [selectedCell, setSelectedCell] = useState<MatrixCell | null>(null);

  // Challenge Experiment State
  const [challengeLookback, setChallengeLookback] = useState<number>(60);
  const [challengeConfidence, setChallengeConfidence] = useState<number>(0.99);
  const [challengeFriction, setChallengeFriction] = useState<number>(15);
  const [challengeResult, setChallengeResult] = useState<any>(null);
  const [challenging, setChallenging] = useState<boolean>(false);

  // Comprehensive Audit & Ranking State
  const [auditReport, setAuditReport] = useState<any>(null);
  const [auditLoading, setAuditLoading] = useState(false);

  // Catalogue
  const [catalogue, setCatalogue] = useState<AssumptionCatalogItem[]>([]);
  const [catSearch, setCatSearch] = useState('');
  const [catCategory, setCatCategory] = useState('ALL');
  const [selectedCatItem, setSelectedCatItem] = useState<AssumptionCatalogItem | null>(null);

  // Run history
  const [runHistory, setRunHistory] = useState<any[]>([]);

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const [portsRes, catRes] = await Promise.all([
        api.listPortfolios().catch(() => ({ portfolios: [] })),
        api.getAssumptionsCatalog().catch(() => ({ assumptions: [] })),
      ]);

      let portList: Portfolio[] = portsRes.portfolios || [];
      if (portList.length === 0) {
        const sampleRes = await api.getSamplePortfolio('nse_10l.json').catch(() => null);
        if (sampleRes) {
          portList = [sampleRes];
        }
      }

      setPortfolios(portList);
      if (portList.length > 0) {
        setActivePortfolio(portList[0]);
        setSelectedPortfolioId(portList[0].portfolio_id);
      }

      if (catRes.assumptions) {
        setCatalogue(catRes.assumptions);
      }

      // Initial sensitivity matrix run
      await executeMatrix(portList[0] || undefined);
    } catch (err: any) {
      notify(`Initialization failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const executeMatrix = async (overridePort?: Portfolio) => {
    const portToUse = overridePort || activePortfolio;
    try {
      setLoading(true);
      const payload: any = {
        target_metric: targetMetric,
        row_dim: rowDim,
        col_dim: colDim,
        conclusion_threshold: conclusionThreshold,
        conclusion_operator: conclusionOperator,
      };

      if (portToUse) {
        payload.portfolio = portToUse;
      } else {
        payload.symbol = 'NIFTY';
      }

      const res = await api.getFragilityMatrix(payload);
      if (res.success) {
        setRowValues(res.row_values || []);
        setColValues(res.col_values || []);
        setMatrixCells(res.cells || []);
        setMatrixDiagnostics(res.diagnostics || null);

        // Record run history item
        const runItem = {
          run_id: `frag_${Date.now().toString(36)}`,
          timestamp: new Date().toLocaleTimeString(),
          target_metric: targetMetric,
          row_dim: rowDim,
          col_dim: colDim,
          baseline: res.baseline_value,
          cells_count: (res.cells || []).length,
          sensitivity_range: res.diagnostics?.absolute_sensitivity_range,
        };
        setRunHistory(prev => [runItem, ...prev.slice(0, 9)]);
      }
    } catch (err: any) {
      notify(`Matrix computation error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const executeChallenge = async () => {
    try {
      setChallenging(true);
      const payload: any = {
        lookback_short: challengeLookback,
        lookback_long: 252,
        friction_bps: challengeFriction,
        decay_factor: 0.94,
      };

      if (activePortfolio) {
        payload.portfolio = activePortfolio;
      } else {
        payload.symbol = 'NIFTY';
      }

      const res = await api.runFragility(payload);
      if (res.success) {
        setChallengeResult(res);
        notify('Challenge experiment executed with authoritative recalculated metrics.');
      }
    } catch (err: any) {
      notify(`Challenge failed: ${err.message}`);
    } finally {
      setChallenging(false);
    }
  };

  const executeAuditBattery = async () => {
    try {
      setAuditLoading(true);
      const payload: any = {
        target_metric: targetMetric,
        conclusion_threshold: conclusionThreshold,
        conclusion_operator: conclusionOperator,
      };

      if (activePortfolio) {
        payload.portfolio = activePortfolio;
      } else {
        payload.symbol = 'NIFTY';
      }

      const res = await api.runFragilityAuditReport(payload);
      if (res.success) {
        setAuditReport(res);
        notify('Full fragility audit battery completed with formal sensitivity ranking.');
      }
    } catch (err: any) {
      notify(`Audit battery failed: ${err.message}`);
    } finally {
      setAuditLoading(false);
    }
  };

  const handlePortfolioSelect = (portId: string) => {
    setSelectedPortfolioId(portId);
    const found = portfolios.find(p => p.portfolio_id === portId);
    if (found) {
      setActivePortfolio(found);
      executeMatrix(found);
    }
  };

  const exportReport = (format: 'json' | 'csv' | 'markdown') => {
    if (!matrixDiagnostics) {
      notify('No computed matrix results to export.');
      return;
    }

    if (format === 'json') {
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify({
        portfolio_id: activePortfolio?.portfolio_id,
        target_metric: targetMetric,
        diagnostics: matrixDiagnostics,
        cells: matrixCells,
        audit_ranking: auditReport?.audit_report?.sensitivity_ranking,
      }, null, 2));
      const dlAnchor = document.createElement('a');
      dlAnchor.setAttribute('href', dataStr);
      dlAnchor.setAttribute('download', `fragility_audit_${targetMetric}.json`);
      dlAnchor.click();
      notify('Exported JSON audit report.');
    } else if (format === 'csv') {
      const headers = ['Row_Dim', 'Row_Val', 'Col_Dim', 'Col_Val', 'Value', 'Baseline', 'Abs_Change', 'Pct_Change', 'Status'];
      const rows = matrixCells.map(c => [
        rowDim,
        c.row_value,
        colDim,
        c.col_value,
        c.value !== null ? c.value : 'NA',
        c.baseline_value,
        c.absolute_change ?? 'NA',
        c.percentage_change ?? 'NA',
        c.status,
      ]);
      const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
      const dlAnchor = document.createElement('a');
      dlAnchor.setAttribute('href', encodeURI(csvContent));
      dlAnchor.setAttribute('download', `fragility_sensitivity_${targetMetric}.csv`);
      dlAnchor.click();
      notify('Exported CSV sensitivity matrix.');
    } else {
      const md = `# FragilityShield — Assumption Auditing & Sensitivity Report
**Target Portfolio**: ${activePortfolio?.name || 'Active Selection'} (${activePortfolio?.portfolio_id})
**Target Metric**: ${targetMetric.toUpperCase()}
**Baseline Value**: ${matrixDiagnostics.baseline_value}
**Sensitivity Range**: ${matrixDiagnostics.absolute_sensitivity_range} (${matrixDiagnostics.relative_sensitivity_range}%)
**Conclusion Breaches**: ${matrixDiagnostics.conclusion_change_ratio} (${matrixDiagnostics.conclusion_change_percentage ?? 0}%)

### Sensitivity Matrix (${rowDim} × ${colDim})
| ${rowDim} | ${colValues.map(c => `${colDim}=${c}`).join(' | ')} |
|---|${colValues.map(() => '---').join('|')}|
${rowValues.map(r => {
  const rowCells = matrixCells.filter(c => c.row_value === r);
  return `| ${r} | ${rowCells.map(c => c.value !== null ? `${c.value} (${c.percentage_change}%)` : 'N/A').join(' | ')} |`;
}).join('\n')}

### Primary Vulnerability
Most sensitive dimension: **${auditReport?.audit_report?.sensitivity_ranking?.most_sensitive_perturbation || rowDim}**
Max measured variation: ${auditReport?.audit_report?.sensitivity_ranking?.max_relative_change ? `${(auditReport.audit_report.sensitivity_ranking.max_relative_change * 100).toFixed(2)}%` : 'Evaluated'}
`;
      const dataStr = 'data:text/markdown;charset=utf-8,' + encodeURIComponent(md);
      const dlAnchor = document.createElement('a');
      dlAnchor.setAttribute('href', dataStr);
      dlAnchor.setAttribute('download', `fragility_report_${targetMetric}.md`);
      dlAnchor.click();
      notify('Exported Markdown report.');
    }
  };

  const getCellBg = (pct: number | undefined) => {
    if (pct === undefined) return 'bg-slate-900 text-slate-500';
    if (Math.abs(pct) < 5) return 'bg-emerald-950/40 text-emerald-300 border-emerald-800/40';
    if (Math.abs(pct) < 15) return 'bg-amber-950/40 text-amber-300 border-amber-800/40';
    return 'bg-rose-950/50 text-rose-300 border-rose-800/50';
  };

  const filteredCatalogue = catalogue.filter(item => {
    const matchesSearch =
      item.model_name.toLowerCase().includes(catSearch.toLowerCase()) ||
      item.model_id.toLowerCase().includes(catSearch.toLowerCase()) ||
      item.distributional_assumption.toLowerCase().includes(catSearch.toLowerCase());
    const matchesCat = catCategory === 'ALL' || item.family.toLowerCase().includes(catCategory.toLowerCase());
    return matchesSearch && matchesCat;
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header Workspace */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
              <ShieldAlert className="w-6 h-6" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight text-foreground">
                  Fragility Assumption Matrix
                </h1>
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-rose-900/40 text-rose-300 border border-rose-700/50">
                  PAGE 06
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-0.5">
                Exposing fragile financial conclusions: How much does reported risk change when underlying assumptions are challenged?
              </p>
            </div>
          </div>
        </div>

        {/* Action controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          <select
            value={selectedPortfolioId}
            onChange={(e) => handlePortfolioSelect(e.target.value)}
            className="bg-card border border-border text-foreground text-sm rounded-lg px-3 py-1.5 focus:ring-1 focus:ring-primary focus:outline-none"
          >
            {portfolios.map(p => (
              <option key={p.portfolio_id} value={p.portfolio_id}>
                {p.name} ({p.holdings?.length || 0} assets)
              </option>
            ))}
          </select>

          <button
            onClick={() => executeMatrix()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Run Audit
          </button>

          <div className="flex items-center rounded-lg border border-border bg-card p-0.5">
            <button
              onClick={() => exportReport('csv')}
              title="Export CSV"
              className="px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded transition-colors"
            >
              CSV
            </button>
            <button
              onClick={() => exportReport('markdown')}
              title="Export Markdown"
              className="px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded transition-colors"
            >
              MD
            </button>
            <button
              onClick={() => exportReport('json')}
              title="Export JSON"
              className="px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded transition-colors"
            >
              JSON
            </button>
          </div>
        </div>
      </div>

      {/* Top Diagnostics KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Authoritative Baseline</span>
            <Activity className="w-4 h-4 text-primary" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-foreground">
            {matrixDiagnostics ? matrixDiagnostics.baseline_value.toFixed(4) : '—'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {targetMetric.toUpperCase()} under baseline 252d lookback
          </div>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Sensitivity Range</span>
            <TrendingUp className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-amber-400">
            {matrixDiagnostics ? matrixDiagnostics.absolute_sensitivity_range.toFixed(4) : '—'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {matrixDiagnostics ? `Relative delta: ${matrixDiagnostics.relative_sensitivity_range.toFixed(1)}%` : 'Calculated across valid grid'}
          </div>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Conclusion Breaches</span>
            <AlertTriangle className="w-4 h-4 text-rose-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-rose-400">
            {matrixDiagnostics?.conclusion_change_percentage !== null && matrixDiagnostics?.conclusion_change_percentage !== undefined
              ? `${matrixDiagnostics.conclusion_change_percentage}%`
              : 'Rule Active'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {matrixDiagnostics?.conclusion_change_ratio} runs breach {conclusionOperator} {conclusionThreshold}
          </div>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Tested Configurations</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-foreground">
            {matrixDiagnostics?.completed_runs ?? 0}
            <span className="text-sm font-normal text-muted-foreground"> / {matrixCells.length}</span>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            0 synthetic interpolations
          </div>
        </div>

        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs font-medium">
            <span>Primary Vulnerability</span>
            <ShieldAlert className="w-4 h-4 text-purple-400" />
          </div>
          <div className="mt-2 text-sm font-bold truncate text-foreground">
            {auditReport?.audit_report?.sensitivity_ranking?.most_sensitive_perturbation || 'Lookback Truncation'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Produces highest measured output variance
          </div>
        </div>
      </div>

      {/* Workspace Tabs */}
      <div className="border-b border-border">
        <nav className="flex space-x-6">
          <button
            onClick={() => setActiveTab('matrix')}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'matrix'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sliders className="w-4 h-4" />
            2D Sensitivity Matrix
          </button>
          <button
            onClick={() => setActiveTab('challenge')}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'challenge'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Layers className="w-4 h-4" />
            Baseline vs Challenged
          </button>
          <button
            onClick={() => {
              setActiveTab('ranking');
              if (!auditReport) executeAuditBattery();
            }}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'ranking'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            Fragility Ranking & Battery
          </button>
          <button
            onClick={() => setActiveTab('catalogue')}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'catalogue'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileText className="w-4 h-4" />
            Assumption Catalogue
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'history'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Compass className="w-4 h-4" />
            Run History ({runHistory.length})
          </button>
        </nav>
      </div>

      {/* TAB 1: 2D SENSITIVITY MATRIX */}
      {activeTab === 'matrix' && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="p-4 rounded-xl border border-border bg-card/60 backdrop-blur space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Target Risk Metric
                </label>
                <select
                  value={targetMetric}
                  onChange={(e) => setTargetMetric(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="var_95">Value at Risk (95% VaR)</option>
                  <option value="expected_shortfall_95">Expected Shortfall (95% ES)</option>
                  <option value="volatility_annualized">Annualized Volatility</option>
                  <option value="sharpe_ratio">Sharpe Ratio (Rf=6.5%)</option>
                  <option value="max_drawdown">Maximum Drawdown</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Row Dimension (Y-Axis)
                </label>
                <select
                  value={rowDim}
                  onChange={(e) => setRowDim(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="lookback_window">Historical Lookback Window (Days)</option>
                  <option value="friction_bps">Transaction Friction Drag (bps)</option>
                  <option value="confidence_level">Confidence Level</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Column Dimension (X-Axis)
                </label>
                <select
                  value={colDim}
                  onChange={(e) => setColDim(e.target.value)}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="confidence_level">Confidence Level (Quantile)</option>
                  <option value="lookback_window">Historical Lookback Window</option>
                  <option value="friction_bps">Transaction Friction Drag</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Conclusion Rule Threshold
                </label>
                <div className="flex gap-2">
                  <select
                    value={conclusionOperator}
                    onChange={(e) => setConclusionOperator(e.target.value)}
                    className="w-20 bg-background border border-border rounded-lg px-2 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value=">">&gt; (Breach)</option>
                    <option value="<">&lt; (Below)</option>
                  </select>
                  <input
                    type="number"
                    step="0.005"
                    value={conclusionThreshold}
                    onChange={(e) => setConclusionThreshold(parseFloat(e.target.value) || 0)}
                    className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary font-mono"
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t border-border/50">
              <div className="flex items-center gap-2">
                <Info className="w-3.5 h-3.5 text-primary" />
                <span>Each cell is an isolated calculation from genuine Upstox historical returns. Click any cell for exact provenance.</span>
              </div>
              <button
                onClick={() => executeMatrix()}
                className="text-primary hover:underline font-medium"
              >
                Recompute Matrix
              </button>
            </div>
          </div>

          {/* Matrix Grid Card */}
          <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
            <div className="p-4 border-b border-border flex items-center justify-between bg-muted/20">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">
                  Interactive Sensitivity Grid: {rowDim} × {colDim}
                </h3>
                <span className="text-xs text-muted-foreground">
                  (Target: <span className="font-mono text-primary">{targetMetric}</span>)
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-emerald-500/80"></span> &lt;5% Delta</span>
                <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-amber-500/80"></span> 5-15% Delta</span>
                <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-rose-500/80"></span> &gt;15% Fragile</span>
              </div>
            </div>

            <div className="p-6 overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="p-3 text-left text-xs font-semibold text-muted-foreground border-b border-border bg-muted/40">
                      {rowDim} ↓ \ {colDim} →
                    </th>
                    {colValues.map((col, idx) => (
                      <th key={idx} className="p-3 text-center text-xs font-bold text-foreground border-b border-border bg-muted/40">
                        {typeof col === 'number' && col < 1 && col > 0 ? `${(col * 100).toFixed(1)}%` : col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rowValues.map((rowVal, rIdx) => (
                    <tr key={rIdx} className="border-b border-border/40 hover:bg-muted/10 transition-colors">
                      <td className="p-3 text-xs font-bold text-foreground bg-muted/20 font-mono">
                        {rowVal} {rowDim === 'lookback_window' ? 'Days' : rowDim === 'friction_bps' ? 'bps' : ''}
                      </td>
                      {colValues.map((colVal, cIdx) => {
                        const cell = matrixCells.find(c => c.row_value === rowVal && c.col_value === colVal);
                        if (!cell) {
                          return (
                            <td key={cIdx} className="p-3 text-center text-xs text-muted-foreground">
                              —
                            </td>
                          );
                        }

                        if (cell.status === 'insufficient_data') {
                          return (
                            <td key={cIdx} className="p-3 text-center text-xs text-muted-foreground bg-slate-900/40">
                              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                                Low N
                              </span>
                            </td>
                          );
                        }

                        const pct = cell.percentage_change;
                        const isBreached = cell.value !== null && (
                          conclusionOperator === '>' ? cell.value > conclusionThreshold : cell.value < conclusionThreshold
                        );

                        return (
                          <td
                            key={cIdx}
                            onClick={() => setSelectedCell(cell)}
                            className="p-2.5 text-center cursor-pointer transition-all hover:scale-105"
                          >
                            <div className={`p-2.5 rounded-lg border ${getCellBg(pct)} relative flex flex-col items-center justify-center gap-0.5 shadow-sm`}>
                              {isBreached && (
                                <span className="absolute -top-1.5 -right-1.5 w-3 h-3 rounded-full bg-rose-500 border-2 border-background" title="Breaches conclusion threshold!" />
                              )}
                              <span className="text-sm font-bold font-mono">
                                {cell.value !== null ? cell.value.toFixed(4) : '—'}
                              </span>
                              <span className="text-[11px] font-mono opacity-80">
                                {pct !== undefined ? (pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`) : ''}
                              </span>
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Matrix Footer Notes */}
            <div className="p-4 border-t border-border bg-muted/10 flex flex-col sm:flex-row items-center justify-between text-xs text-muted-foreground gap-2">
              <div>
                Authoritative Baseline: <strong className="text-foreground">{matrixDiagnostics?.baseline_value.toFixed(4)}</strong> |
                Range: <strong className="text-amber-400 font-mono">[{matrixDiagnostics?.min_value.toFixed(4)} .. {matrixDiagnostics?.max_value.toFixed(4)}]</strong>
              </div>
              <div>
                Conclusion Rule: <span className="font-mono text-rose-400">{targetMetric} {conclusionOperator} {conclusionThreshold}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: BASELINE VS CHALLENGED COMPARISON */}
      {activeTab === 'challenge' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Baseline Card */}
            <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-primary"></span>
                  <h3 className="font-semibold text-foreground text-sm">Authoritative Baseline Profile</h3>
                </div>
                <span className="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-mono">
                  IMMUTABLE
                </span>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between py-1.5 border-b border-border/50">
                  <span className="text-muted-foreground">Historical Lookback Window</span>
                  <span className="font-mono font-medium text-foreground">252 Trading Days (1 Year)</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border/50">
                  <span className="text-muted-foreground">Tail Risk Confidence Level</span>
                  <span className="font-mono font-medium text-foreground">95.0% (α = 0.05)</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border/50">
                  <span className="text-muted-foreground">Volatility Estimator</span>
                  <span className="font-mono font-medium text-foreground">Sample Volatility (ddof=1)</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border/50">
                  <span className="text-muted-foreground">Transaction Drag / Friction</span>
                  <span className="font-mono font-medium text-foreground">0 bps (Frictionless)</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-border/50">
                  <span className="text-muted-foreground">Data Provider</span>
                  <span className="font-mono font-medium text-foreground">Upstox V3 Market Data</span>
                </div>
              </div>
            </div>

            {/* Challenged Card */}
            <div className="p-6 rounded-xl border border-rose-500/30 bg-rose-950/10 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-rose-500/20 pb-3">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
                  <h3 className="font-semibold text-foreground text-sm">Challenged Hypothesis Profile</h3>
                </div>
                <span className="text-xs px-2 py-0.5 rounded bg-rose-900/40 text-rose-300 border border-rose-700/50 font-mono">
                  ACTIVE EXPERIMENT
                </span>
              </div>

              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Challenged Lookback Horizon</span>
                    <span className="font-mono font-bold text-foreground">{challengeLookback} Days</span>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="252"
                    step="5"
                    value={challengeLookback}
                    onChange={(e) => setChallengeLookback(parseInt(e.target.value))}
                    className="w-full accent-rose-500"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Challenged Confidence Level</span>
                    <span className="font-mono font-bold text-foreground">{(challengeConfidence * 100).toFixed(1)}%</span>
                  </div>
                  <select
                    value={challengeConfidence}
                    onChange={(e) => setChallengeConfidence(parseFloat(e.target.value))}
                    className="w-full bg-background border border-border rounded-lg px-2.5 py-1.5 text-xs text-foreground focus:outline-none"
                  >
                    <option value="0.90">90.0% (Fast screening)</option>
                    <option value="0.95">95.0% (Standard Basel II)</option>
                    <option value="0.99">99.0% (Basel III Extreme Tail)</option>
                    <option value="0.995">99.5% (Stress test quantile)</option>
                  </select>
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-muted-foreground">Friction / Slippage Drag</span>
                    <span className="font-mono font-bold text-foreground">{challengeFriction} bps</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="50"
                    step="5"
                    value={challengeFriction}
                    onChange={(e) => setChallengeFriction(parseInt(e.target.value))}
                    className="w-full accent-rose-500"
                  />
                </div>

                <button
                  onClick={executeChallenge}
                  disabled={challenging}
                  className="w-full py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-1.5 shadow"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${challenging ? 'animate-spin' : ''}`} />
                  Execute Challenge Experiment
                </button>
              </div>
            </div>
          </div>

          {/* Side by Side Recomputed Metrics Table */}
          {challengeResult && (
            <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
              <div className="p-4 border-b border-border bg-muted/20 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-foreground">
                  Recalculated Sensitivity Comparison
                </h3>
                <span className="text-xs text-muted-foreground font-mono">
                  Sample Size: {challengeResult.experiments?.[0]?.observations_used || '252'} observations
                </span>
              </div>

              <div className="p-4 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-left">
                      <th className="py-2.5 px-3">Perturbation Attack</th>
                      <th className="py-2.5 px-3">Baseline Metric</th>
                      <th className="py-2.5 px-3">Challenged Metric</th>
                      <th className="py-2.5 px-3">Absolute Shift</th>
                      <th className="py-2.5 px-3">Relative Fragility</th>
                      <th className="py-2.5 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(challengeResult.experiments || []).map((exp: any, idx: number) => {
                      const baseV = exp.baseline_metrics?.var_95 ?? exp.baseline_metrics?.volatility_annualized ?? 0;
                      const pertV = exp.perturbed_metrics?.var_95 ?? exp.perturbed_metrics?.volatility_annualized ?? 0;
                      const delta = exp.absolute_changes?.var_95 ?? exp.absolute_changes?.volatility_annualized ?? (pertV - baseV);
                      const pct = exp.percentage_changes?.var_95 ?? exp.percentage_changes?.volatility_annualized ?? ((delta / (baseV || 1)) * 100);

                      return (
                        <tr key={idx} className="border-b border-border/40 hover:bg-muted/10">
                          <td className="py-3 px-3 font-semibold text-foreground flex items-center gap-2">
                            <CornerDownRight className="w-3.5 h-3.5 text-muted-foreground" />
                            {exp.perturbation_name}
                          </td>
                          <td className="py-3 px-3 font-mono">{baseV.toFixed(4)}</td>
                          <td className="py-3 px-3 font-mono font-bold text-foreground">{pertV.toFixed(4)}</td>
                          <td className={`py-3 px-3 font-mono ${delta >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {delta >= 0 ? `+${delta.toFixed(4)}` : delta.toFixed(4)}
                          </td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded font-mono font-bold ${
                              Math.abs(pct) > 15 ? 'bg-rose-950/50 text-rose-400 border border-rose-800/40' : 'bg-emerald-950/40 text-emerald-400'
                            }`}>
                              {pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`}
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            <span className="text-[11px] text-emerald-400 flex items-center gap-1">
                              <CheckCircle2 className="w-3.5 h-3.5" /> Recomputed
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: FRAGILITY RANKING & BATTERY */}
      {activeTab === 'ranking' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between p-4 rounded-xl border border-border bg-card">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Standard Fragility Attack Battery</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                Executes formal perturbations (lookback, volatility model, tail quantile, friction drag, outlier winsorization) to rank which assumptions induce the highest model fragility.
              </p>
            </div>
            <button
              onClick={executeAuditBattery}
              disabled={auditLoading}
              className="px-4 py-2 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90 transition-colors shadow flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${auditLoading ? 'animate-spin' : ''}`} />
              Re-run Audit Battery
            </button>
          </div>

          {auditReport && (
            <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
              <div className="p-4 border-b border-border bg-muted/20 flex items-center justify-between">
                <span className="text-sm font-bold text-foreground">
                  Assumption Instability Ranking (Sorted by Impact on {targetMetric})
                </span>
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-purple-950/50 text-purple-300 border border-purple-800/40">
                  Audit ID: {auditReport.audit_id}
                </span>
              </div>

              <div className="p-4 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-left">
                      <th className="py-2.5 px-3">Rank</th>
                      <th className="py-2.5 px-3">Challenged Assumption</th>
                      <th className="py-2.5 px-3">Baseline</th>
                      <th className="py-2.5 px-3">Perturbed</th>
                      <th className="py-2.5 px-3">Absolute Shift</th>
                      <th className="py-2.5 px-3">Sensitivity %</th>
                      <th className="py-2.5 px-3">Fragility Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(auditReport.audit_report?.experiments || []).map((exp: any, idx: number) => {
                      const baseV = exp.baseline_metrics?.[targetMetric] ?? exp.baseline_metrics?.volatility_annualized ?? 0;
                      const pertV = exp.perturbed_metrics?.[targetMetric] ?? exp.perturbed_metrics?.volatility_annualized ?? 0;
                      const delta = Math.abs(pertV - baseV);
                      const pct = baseV > 0 ? (delta / baseV) * 100 : 0;
                      const isHigh = pct > 15;

                      return (
                        <tr key={idx} className="border-b border-border/40 hover:bg-muted/10">
                          <td className="py-3 px-3 font-mono font-bold text-muted-foreground">
                            #{idx + 1}
                          </td>
                          <td className="py-3 px-3 font-semibold text-foreground">
                            {exp.perturbation_name}
                          </td>
                          <td className="py-3 px-3 font-mono">{baseV.toFixed(4)}</td>
                          <td className="py-3 px-3 font-mono font-bold text-foreground">{pertV.toFixed(4)}</td>
                          <td className="py-3 px-3 font-mono text-amber-400">±{delta.toFixed(4)}</td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded font-mono font-bold ${
                              isHigh ? 'bg-rose-950/60 text-rose-400 border border-rose-800/50' : 'bg-emerald-950/40 text-emerald-400'
                            }`}>
                              {pct.toFixed(2)}%
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                              isHigh ? 'bg-rose-900/30 text-rose-300' : 'bg-slate-800 text-slate-300'
                            }`}>
                              {isHigh ? 'CRITICAL FRAGILITY' : 'STABLE ASSUMPTION'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: ASSUMPTION CATALOGUE */}
      {activeTab === 'catalogue' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card">
            <div className="relative flex-1 w-full sm:w-auto">
              <input
                type="text"
                placeholder="Search assumption registry (formula, failure regime, parameter)..."
                value={catSearch}
                onChange={(e) => setCatSearch(e.target.value)}
                className="w-full bg-background border border-border rounded-lg pl-3 pr-8 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
              {['ALL', 'Parametric', 'Non-parametric', 'Volatility', 'Regression'].map(cat => (
                <button
                  key={cat}
                  onClick={() => setCatCategory(cat)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                    catCategory === cat
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredCatalogue.map((item, idx) => (
              <div
                key={idx}
                onClick={() => setSelectedCatItem(item)}
                className="p-5 rounded-xl border border-border bg-card hover:border-primary/50 transition-all cursor-pointer shadow-sm flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground">
                      {item.model_id}
                    </span>
                    <span className="text-xs font-medium text-primary">
                      {item.family}
                    </span>
                  </div>
                  <h4 className="font-bold text-foreground text-sm mt-2">{item.model_name}</h4>
                  <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
                    {item.distributional_assumption}
                  </p>
                </div>

                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
                  <span>Precondition: {item.sample_size_precondition}</span>
                  <span className="text-primary font-medium flex items-center gap-1">
                    Details <ChevronRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 5: RUN HISTORY */}
      {activeTab === 'history' && (
        <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
          <div className="p-4 border-b border-border bg-muted/20 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Audit Execution Log</h3>
            <span className="text-xs text-muted-foreground">Reproducible Run IDs</span>
          </div>

          <div className="p-4">
            {runHistory.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                No previous sensitivity matrix runs recorded this session. Click "Run Audit" above.
              </div>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-left">
                    <th className="py-2 px-3">Run ID</th>
                    <th className="py-2 px-3">Timestamp</th>
                    <th className="py-2 px-3">Metric</th>
                    <th className="py-2 px-3">Dimensions</th>
                    <th className="py-2 px-3">Baseline</th>
                    <th className="py-2 px-3">Sensitivity Range</th>
                    <th className="py-2 px-3">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {runHistory.map((run, idx) => (
                    <tr key={idx} className="border-b border-border/40 hover:bg-muted/10 font-mono">
                      <td className="py-2.5 px-3 font-bold text-primary">{run.run_id}</td>
                      <td className="py-2.5 px-3 text-muted-foreground">{run.timestamp}</td>
                      <td className="py-2.5 px-3 text-foreground">{run.target_metric}</td>
                      <td className="py-2.5 px-3 text-muted-foreground">{run.row_dim} × {run.col_dim}</td>
                      <td className="py-2.5 px-3 text-foreground">{run.baseline?.toFixed(4)}</td>
                      <td className="py-2.5 px-3 text-amber-400">±{run.sensitivity_range?.toFixed(4)}</td>
                      <td className="py-2.5 px-3">
                        <button
                          onClick={() => executeMatrix()}
                          className="text-xs text-primary hover:underline font-sans"
                        >
                          Rerun
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Cell Drill-Down Modal */}
      {selectedCell && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <h3 className="font-bold text-foreground text-sm">
                  Sensitivity Cell Inspection
                </h3>
              </div>
              <button
                onClick={() => setSelectedCell(null)}
                className="p-1 rounded-md text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-muted/30">
                <div>
                  <span className="text-muted-foreground block">{rowDim}:</span>
                  <span className="font-bold font-mono text-foreground text-sm">{selectedCell.row_value}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block">{colDim}:</span>
                  <span className="font-bold font-mono text-foreground text-sm">{selectedCell.col_value}</span>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">Computed Metric Value:</span>
                  <span className="font-mono font-bold text-foreground">{selectedCell.value?.toFixed(6) ?? 'N/A'}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">Baseline Reference:</span>
                  <span className="font-mono text-muted-foreground">{selectedCell.baseline_value?.toFixed(6)}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">Absolute Shift:</span>
                  <span className="font-mono text-amber-400">
                    {selectedCell.absolute_change !== undefined ? `${selectedCell.absolute_change >= 0 ? '+' : ''}${selectedCell.absolute_change.toFixed(6)}` : '—'}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">Relative Change:</span>
                  <span className="font-mono font-bold text-rose-400">
                    {selectedCell.percentage_change !== undefined ? `${selectedCell.percentage_change >= 0 ? '+' : ''}${selectedCell.percentage_change.toFixed(2)}%` : '—'}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">Effective Sample Observations:</span>
                  <span className="font-mono text-foreground">{selectedCell.sample_size ?? 'N/A'} days</span>
                </div>
                <div className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">Calculation Status:</span>
                  <span className="font-semibold text-emerald-400 uppercase text-[10px]">{selectedCell.status}</span>
                </div>
              </div>

              {selectedCell.warning && (
                <div className="p-2.5 rounded bg-amber-950/40 border border-amber-800/40 text-amber-300 text-xs">
                  {selectedCell.warning}
                </div>
              )}
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedCell(null)}
                className="px-4 py-1.5 bg-secondary text-secondary-foreground text-xs font-semibold rounded-lg hover:bg-secondary/80"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Catalogue Item Modal */}
      {selectedCatItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div>
                <h3 className="font-bold text-foreground text-base">
                  {selectedCatItem.model_name}
                </h3>
                <span className="text-xs text-primary font-mono">{selectedCatItem.model_id}</span>
              </div>
              <button
                onClick={() => setSelectedCatItem(null)}
                className="p-1 rounded-md text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <span className="text-muted-foreground font-semibold block mb-1">Mathematical Formulation:</span>
                <div className="p-3 rounded-lg bg-muted/40 font-mono text-foreground">
                  {selectedCatItem.mathematical_formulation}
                </div>
              </div>

              <div>
                <span className="text-muted-foreground font-semibold block mb-1">Distributional Assumption:</span>
                <p className="text-foreground leading-relaxed">{selectedCatItem.distributional_assumption}</p>
              </div>

              <div>
                <span className="text-muted-foreground font-semibold block mb-1">Temporal Autocorrelation Assumption:</span>
                <p className="text-foreground leading-relaxed">{selectedCatItem.temporal_assumption}</p>
              </div>

              <div>
                <span className="text-muted-foreground font-semibold block mb-1">Sample Size Precondition:</span>
                <p className="font-mono text-amber-400">{selectedCatItem.sample_size_precondition}</p>
              </div>

              <div>
                <span className="text-rose-400 font-semibold block mb-1">Documented Failure Regimes:</span>
                <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                  {selectedCatItem.known_failure_regimes.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>

              <div>
                <span className="text-purple-400 font-semibold block mb-1">Fragility Attack Vulnerabilities:</span>
                <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                  {selectedCatItem.fragility_attack_vulnerabilities.map((v, i) => (
                    <li key={i}>{v}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedCatItem(null)}
                className="px-4 py-1.5 bg-primary text-primary-foreground text-xs font-semibold rounded-lg hover:bg-primary/90"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
