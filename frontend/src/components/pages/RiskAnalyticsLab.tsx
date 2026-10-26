import React, { useState, useEffect, useMemo } from 'react';
import {
  Gauge,
  Activity,
  AlertTriangle,
  CheckCircle2,
  Play,
  RotateCcw,
  Download,
  Info,
  TrendingDown,
  Layers,
  Sparkles,
  ShieldCheck,
  FileSpreadsheet,
  AlertCircle,
  HelpCircle,
  Sliders,
  Database
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine
} from 'recharts';
import { api, Portfolio as ApiPortfolio, RiskReport } from '@/lib/api';

interface RiskAnalyticsLabProps {
  activePortfolio: ApiPortfolio | null;
  setActivePortfolio: (p: ApiPortfolio | null) => void;
  savedPortfolios?: ApiPortfolio[];
  notify?: (msg: string) => void;
  navigate?: (path: string) => void;
}

type UIAnalysisState =
  | 'NO_PORTFOLIO_SELECTED'
  | 'CONFIG_INCOMPLETE'
  | 'READY_TO_RUN'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'PARTIAL_DATA'
  | 'FAILED'
  | 'INSUFFICIENT_DATA';

export const RiskAnalyticsLab: React.FC<RiskAnalyticsLabProps> = ({
  activePortfolio,
  setActivePortfolio,
  savedPortfolios = [],
  notify,
  navigate
}) => {
  // Navigation sub-tabs
  const [activeTab, setActiveTab] = useState<'charts' | 'explanation' | 'provenance'>('charts');

  // Protocol configuration state
  const [confidenceLevel, setConfidenceLevel] = useState<number>(0.95);
  const [lookbackWindow, setLookbackWindow] = useState<number>(252);
  const [riskMethodology, setRiskMethodology] = useState<'historical' | 'parametric' | 'cornish_fisher'>('historical');
  const [benchmarkSymbol, setBenchmarkSymbol] = useState<string>('NIFTY');

  // Preview toggle (strictly separated and labeled)
  const [previewMode, setPreviewMode] = useState<boolean>(false);

  // Analysis result & loading state
  const [riskReport, setRiskReport] = useState<RiskReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Available portfolios state
  const [portfolioList, setPortfolioList] = useState<ApiPortfolio[]>(savedPortfolios);

  // Load portfolios on mount
  useEffect(() => {
    let isMounted = true;
    api.listPortfolios().then(res => {
      if (isMounted && res && res.portfolios) {
        setPortfolioList(res.portfolios);
      }
    }).catch(() => {
      // Fallback to prop savedPortfolios if available
    });
    return () => { isMounted = false; };
  }, []);

  // Determine if active portfolio is the illustrative sample fixture
  const isIllustrative = useMemo(() => {
    if (!activePortfolio) return false;
    const id = (activePortfolio.portfolio_id || '').toLowerCase();
    const name = (activePortfolio.name || '').toLowerCase();
    return id.includes('illustrative') || id.includes('nse_10l') || name.includes('illustrative') || name.includes('sample');
  }, [activePortfolio]);

  // Determine overall UI State
  const uiState: UIAnalysisState = useMemo(() => {
    if (!activePortfolio) return 'NO_PORTFOLIO_SELECTED';
    if (!confidenceLevel || !lookbackWindow) return 'CONFIG_INCOMPLETE';
    if (loading) return 'RUNNING';
    if (errorMessage) return 'FAILED';
    if (!riskReport) return 'READY_TO_RUN';
    const obs = riskReport.returns_count ?? riskReport.returns?.length ?? 0;
    if (obs < 4) return 'INSUFFICIENT_DATA';
    if (obs < 20) return 'PARTIAL_DATA';
    return 'SUCCEEDED';
  }, [activePortfolio, confidenceLevel, lookbackWindow, loading, errorMessage, riskReport]);

  // Execute quantitative risk calculation
  const runRiskAnalysis = async () => {
    if (!activePortfolio) {
      notify?.('Please select a portfolio or dataset first.');
      return;
    }
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.calculateRisk(activePortfolio, confidenceLevel, lookbackWindow, benchmarkSymbol);
      setRiskReport(res);
      notify?.(`Risk calculation succeeded: ${(confidenceLevel * 100).toFixed(0)}% VaR and CVaR computed.`);
    } catch (err: any) {
      const msg = err?.message || 'Risk calculation failed on backend.';
      setErrorMessage(msg);
      notify?.(`Error: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  // Switch to illustrative demo portfolio explicitly
  const selectIllustrativePortfolio = async () => {
    try {
      const sample = await api.getSamplePortfolio('nse_10l.json');
      setActivePortfolio(sample);
      setRiskReport(null);
      setErrorMessage(null);
      notify?.('Loaded illustrative demo dataset: NSE 10L Portfolio.');
    } catch (err: any) {
      notify?.(`Failed to load illustrative sample: ${err?.message}`);
    }
  };

  // Data transformations for Chart 1: Cumulative Returns
  const cumulativeData = useMemo(() => {
    if (!riskReport) return [];
    if (riskReport.equity_curve && riskReport.equity_curve.length > 0) {
      return riskReport.equity_curve.map((val, idx) => ({
        step: idx === 0 ? 'Start' : `Day ${idx}`,
        cumReturn: Number(((val - 1.0) * 100).toFixed(2)),
        equityValue: Number(val.toFixed(4)),
      }));
    }
    if (riskReport.returns && riskReport.returns.length > 0) {
      let cum = 1.0;
      const res = [{ step: 'Start', cumReturn: 0.0, equityValue: 1.0 }];
      riskReport.returns.forEach((r, idx) => {
        cum = cum * (1.0 + r);
        res.push({
          step: `Day ${idx + 1}`,
          cumReturn: Number(((cum - 1.0) * 100).toFixed(2)),
          equityValue: Number(cum.toFixed(4)),
        });
      });
      return res;
    }
    return [];
  }, [riskReport]);

  // Data transformations for Chart 2: Periodic Returns
  const periodicData = useMemo(() => {
    if (!riskReport || !riskReport.returns || riskReport.returns.length === 0) return [];
    return riskReport.returns.map((r, idx) => ({
      step: `Day ${idx + 1}`,
      returnPct: Number((r * 100).toFixed(2)),
      isPositive: r >= 0,
    }));
  }, [riskReport]);

  // Data transformations for Chart 3: Rolling Volatility (20-day window)
  const rollingVolData = useMemo(() => {
    if (!riskReport || !riskReport.returns || riskReport.returns.length < 20) return [];
    const rets = riskReport.returns;
    const window = 20;
    const results = [];
    for (let i = window - 1; i < rets.length; i++) {
      const slice = rets.slice(i - window + 1, i + 1);
      const mean = slice.reduce((a, b) => a + b, 0) / window;
      const variance = slice.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / (window - 1);
      const annVol = Math.sqrt(variance) * Math.sqrt(252) * 100;
      results.push({
        step: `Day ${i + 1}`,
        rollingVol: Number(annVol.toFixed(2)),
      });
    }
    return results;
  }, [riskReport]);

  // Data transformations for Chart 4: Drawdown / Underwater curve
  const drawdownData = useMemo(() => {
    if (!riskReport) return [];
    if (riskReport.drawdown_series && riskReport.drawdown_series.length > 0) {
      return riskReport.drawdown_series.map((dd, idx) => ({
        step: idx === 0 ? 'Start' : `Day ${idx}`,
        drawdownPct: Number((-Math.abs(dd) * 100).toFixed(2)),
      }));
    }
    // Derive from equity curve
    if (riskReport.equity_curve && riskReport.equity_curve.length > 0) {
      let peak = -Infinity;
      return riskReport.equity_curve.map((val, idx) => {
        if (val > peak) peak = val;
        const dd = peak > 0 ? (peak - val) / peak : 0;
        return {
          step: idx === 0 ? 'Start' : `Day ${idx}`,
          drawdownPct: Number((-dd * 100).toFixed(2)),
        };
      });
    }
    return [];
  }, [riskReport]);

  // Data transformations for Chart 5: Return Distribution / Histogram with Normal Fit
  const histogramData = useMemo(() => {
    if (!riskReport || !riskReport.returns || riskReport.returns.length < 4) return [];
    const rets = riskReport.returns.map(r => r * 100);
    const minVal = Math.min(...rets);
    const maxVal = Math.max(...rets);
    const numBins = 12;
    const binWidth = (maxVal - minVal) / numBins || 0.1;

    // Calculate sample mean and std
    const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
    const variance = rets.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / (rets.length - 1);
    const std = Math.sqrt(variance) || 0.001;

    const bins = Array.from({ length: numBins }, (_, i) => {
      const lower = minVal + i * binWidth;
      const upper = lower + binWidth;
      const midpoint = (lower + upper) / 2;
      return {
        binLabel: `${lower >= 0 ? '+' : ''}${lower.toFixed(1)}%`,
        lower,
        upper,
        midpoint,
        count: 0,
        normalDensity: 0,
      };
    });

    rets.forEach(val => {
      let bIdx = Math.floor((val - minVal) / binWidth);
      if (bIdx >= numBins) bIdx = numBins - 1;
      if (bIdx < 0) bIdx = 0;
      bins[bIdx].count += 1;
    });

    // Gaussian normal density scaled to counts: (1 / (std * sqrt(2*pi))) * exp(-0.5 * z^2) * binWidth * N
    bins.forEach(b => {
      const z = (b.midpoint - mean) / std;
      const pdf = (1 / (std * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * z * z);
      b.normalDensity = Number((pdf * binWidth * rets.length).toFixed(2));
    });

    return bins;
  }, [riskReport]);

  // Data transformations for Chart 6: VaR / CVaR Tail Visualization
  const tailData = useMemo(() => {
    if (!riskReport || !riskReport.returns || riskReport.returns.length === 0) return [];
    // Loss convention: L = -R
    const losses = riskReport.returns.map(r => -r * 100);
    losses.sort((a, b) => a - b);

    const varThreshold = (riskReport.custom_var ?? riskReport.historical_var_95 ?? 0) * 100;
    const esThreshold = (riskReport.custom_es ?? riskReport.expected_shortfall_95 ?? 0) * 100;

    return losses.map((loss, idx) => ({
      rank: `Obs ${idx + 1}`,
      lossPct: Number(loss.toFixed(2)),
      isBreach: loss >= varThreshold,
      varThreshold: Number(varThreshold.toFixed(2)),
      esThreshold: Number(esThreshold.toFixed(2)),
    }));
  }, [riskReport]);

  // Export report as JSON artifact
  const exportReport = () => {
    if (!riskReport) return;
    const blob = new Blob([JSON.stringify(riskReport, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `risk_analytics_${activePortfolio?.portfolio_id || 'portfolio'}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    notify?.('Quantitative risk report exported as JSON.');
  };

  return (
    <div className="lab-layout space-y-6">
      {/* Top Header / Context */}
      <div className="page-head">
        <div>
          <span className="eyebrow">LAB 01 / QUANTITATIVE RISK LAB</span>
          <h1 className="flex items-center gap-2">
            <Gauge size={22} className="text-teal-600" />
            Risk Analytics Lab
          </h1>
          <p className="subhead">
            Measure portfolio risk with empirical historical simulation, parametric normal, and coherent expected shortfall (CVaR). Fully bound to live Fragility Engine output.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            className="button secondary flex items-center gap-2"
            onClick={exportReport}
            disabled={!riskReport}
            title="Download full quantitative analysis report"
          >
            <Download size={14} /> Export Report
          </button>
          <button
            className="button primary flex items-center gap-2"
            disabled={loading || !activePortfolio}
            onClick={runRiskAnalysis}
          >
            {loading ? <Activity className="animate-spin" size={14} /> : <Play size={14} />}
            {loading ? 'Calculating Engine Metrics...' : 'Run Analysis'}
          </button>
        </div>
      </div>

      {/* Illustrative Notice Banner */}
      {isIllustrative && (
        <div className="p-3 rounded-lg border border-amber-300 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-950/30 flex items-start gap-3 text-amber-900 dark:text-amber-200">
          <AlertTriangle className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" size={18} />
          <div className="text-xs space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-wide uppercase px-2 py-0.5 rounded text-[10px] bg-amber-200 dark:bg-amber-900/60 text-amber-900 dark:text-amber-200">
                ILLUSTRATIVE — NOT REAL PORTFOLIO DATA
              </span>
              <span className="font-medium text-amber-800 dark:text-amber-300">Target: {activePortfolio?.name}</span>
            </div>
            <p className="text-amber-700 dark:text-amber-300/80">
              This portfolio is an illustrative demonstration fixture calibrated for educational testing. To analyze real investments, switch to a saved client portfolio or upload validated transactions.
            </p>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {errorMessage && (
        <div className="p-3 rounded-lg border border-rose-300 dark:border-rose-700/50 bg-rose-50 dark:bg-rose-950/30 flex items-center gap-3 text-rose-900 dark:text-rose-200 text-xs">
          <AlertCircle className="text-rose-600 dark:text-rose-400 shrink-0" size={18} />
          <div>
            <b>Analysis Calculation Error:</b> {errorMessage}
          </div>
        </div>
      )}

      {/* Protocol Configuration Section */}
      <section className="panel lab-config">
        <div className="panel-head flex justify-between items-center">
          <div>
            <span className="section-kicker">ANALYSIS CONFIGURATION</span>
            <h2>Define the Protocol</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-muted-foreground">Status:</span>
            <span className={`badge ${
              uiState === 'SUCCEEDED' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300' :
              uiState === 'RUNNING' ? 'bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300' :
              uiState === 'PARTIAL_DATA' ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300' :
              uiState === 'FAILED' ? 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300' :
              'bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300'
            }`}>
              {uiState.replace(/_/g, ' ')}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4">
          {/* Portfolio Target */}
          <label className="field-label flex flex-col gap-1.5 text-xs font-medium">
            <span>PORTFOLIO OR DATASET <span className="text-rose-500">*</span></span>
            <select
              className="h-9 px-2 border rounded bg-background text-foreground text-xs"
              value={activePortfolio?.portfolio_id || (isIllustrative ? 'nse_10l_illustrative' : '')}
              onChange={e => {
                const val = e.target.value;
                if (!val) {
                  setActivePortfolio(null);
                  setRiskReport(null);
                } else if (val === 'nse_10l_illustrative') {
                  selectIllustrativePortfolio();
                } else {
                  const match = portfolioList.find(p => p.portfolio_id === val);
                  if (match) {
                    setActivePortfolio(match);
                    setRiskReport(null);
                    setErrorMessage(null);
                    notify?.(`Selected portfolio: ${match.name}`);
                  }
                }
              }}
            >
              <option value="">-- Select Portfolio --</option>
              <option value="nse_10l_illustrative">Illustrative ₹10 Lakh NSE Portfolio (Demo Fixture)</option>
              {portfolioList.map(p => (
                <option key={p.portfolio_id} value={p.portfolio_id}>
                  {p.name} ({p.holdings?.length || 0} holdings)
                </option>
              ))}
            </select>
            <span className="text-[10px] text-muted-foreground">
              {isIllustrative ? 'Demo fixture (marked illustrative)' : activePortfolio ? `Holdings: ${activePortfolio.holdings?.length || 0}` : 'No target selected'}
            </span>
          </label>

          {/* Confidence Level */}
          <label className="field-label flex flex-col gap-1.5 text-xs font-medium">
            <span>CONFIDENCE LEVEL <span className="text-rose-500">*</span></span>
            <select
              className="h-9 px-2 border rounded bg-background text-foreground text-xs"
              value={confidenceLevel}
              onChange={e => setConfidenceLevel(Number(e.target.value))}
            >
              <option value={0.95}>95% (Basel Standard / Daily)</option>
              <option value={0.99}>99% (Regulatory Tail Risk)</option>
              <option value={0.90}>90% (Exploratory / Broad Tail)</option>
            </select>
            <span className="text-[10px] text-muted-foreground">Determines VaR & Expected Shortfall quantile</span>
          </label>

          {/* Lookback Window */}
          <label className="field-label flex flex-col gap-1.5 text-xs font-medium">
            <span>LOOKBACK WINDOW <span className="text-rose-500">*</span></span>
            <select
              className="h-9 px-2 border rounded bg-background text-foreground text-xs"
              value={lookbackWindow}
              onChange={e => setLookbackWindow(Number(e.target.value))}
            >
              <option value={60}>60 Days (Short-term Horizon)</option>
              <option value={120}>120 Days (Medium-term Horizon)</option>
              <option value={252}>252 Days (1 Year Annual Baseline - Default)</option>
              <option value={504}>504 Days (2 Years Market Cycle)</option>
            </select>
            <span className="text-[10px] text-muted-foreground">Historical observation horizon</span>
          </label>

          {/* Risk Methodology */}
          <label className="field-label flex flex-col gap-1.5 text-xs font-medium">
            <span>RISK METHODOLOGY <span className="text-rose-500">*</span></span>
            <select
              className="h-9 px-2 border rounded bg-background text-foreground text-xs"
              value={riskMethodology}
              onChange={e => setRiskMethodology(e.target.value as any)}
            >
              <option value="historical">Empirical Historical Simulation</option>
              <option value="parametric">Parametric Gaussian (Normal)</option>
              <option value="cornish_fisher">Cornish-Fisher (Skew/Kurtosis)</option>
            </select>
            <span className="text-[10px] text-muted-foreground">Calculation engine formula</span>
          </label>
        </div>

        {/* Configuration Summary & Action Footer */}
        <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-muted/20 border-t text-xs">
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground">
              Target: <b className="text-foreground">{activePortfolio?.name || 'None'}</b>
            </span>
            <span className="text-muted-foreground">
              Horizon: <b className="text-foreground">{lookbackWindow} Days</b>
            </span>
            <span className="text-muted-foreground">
              Confidence: <b className="text-foreground">{(confidenceLevel * 100).toFixed(0)}%</b>
            </span>
            <span className="text-muted-foreground">
              Engine: <b className="text-foreground">{riskMethodology.toUpperCase()}</b>
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              className="button text-xs py-1.5 px-3 border rounded hover:bg-muted"
              onClick={() => {
                setConfidenceLevel(0.95);
                setLookbackWindow(252);
                setRiskMethodology('historical');
                setBenchmarkSymbol('NIFTY');
              }}
            >
              <RotateCcw size={12} className="inline mr-1" /> Reset Defaults
            </button>
            <button
              className="button primary text-xs py-1.5 px-4 rounded flex items-center gap-1.5"
              disabled={loading || !activePortfolio}
              onClick={runRiskAnalysis}
            >
              {loading ? <Activity className="animate-spin" size={13} /> : <Play size={13} />}
              {loading ? 'Running...' : 'Execute Calculation'}
            </button>
          </div>
        </div>
      </section>

      {/* Analysis Output Section */}
      <section className="panel result-panel">
        <div className="panel-head flex justify-between items-center">
          <div>
            <span className="section-kicker">ANALYSIS OUTPUT</span>
            <h2>Results Workspace</h2>
          </div>
          <div className="flex items-center gap-3">
            <span className="run-status flex items-center gap-1.5 text-xs font-mono">
              <i className={`state-dot ${riskReport ? 'live' : 'offline'}`} />
              {riskReport ? 'SUCCEEDED' : 'READY TO RUN'}
            </span>
          </div>
        </div>

        {/* Output Tabs */}
        <div className="tab-strip flex border-b px-4">
          <button
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === 'charts' ? 'border-teal-600 text-teal-600 font-bold' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            onClick={() => setActiveTab('charts')}
          >
            Visual Diagnostics (6 Quantitative Charts)
          </button>
          <button
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === 'explanation' ? 'border-teal-600 text-teal-600 font-bold' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            onClick={() => setActiveTab('explanation')}
          >
            Mathematical Explanations & Formulas
          </button>
          <button
            className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${activeTab === 'provenance' ? 'border-teal-600 text-teal-600 font-bold' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            onClick={() => setActiveTab('provenance')}
          >
            Data Provenance & Audit Trail
          </button>
        </div>

        {/* Metric Tiles Header */}
        {riskReport && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 p-4 bg-muted/10 border-b">
            <div className="metric-tile p-3 rounded border bg-card text-card-foreground">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">Annualized Volatility</span>
              <strong className="block text-lg font-bold text-foreground mt-1">
                {(riskReport.annualized_volatility * 100).toFixed(2)}%
              </strong>
              <small className="text-[10px] text-muted-foreground">
                {riskReport.returns_count || 252} observations
              </small>
            </div>

            <div className="metric-tile p-3 rounded border bg-card text-card-foreground">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">
                Historical VaR ({((riskReport.confidence_level ?? confidenceLevel) * 100).toFixed(0)}%)
              </span>
              <strong className="block text-lg font-bold text-rose-600 dark:text-rose-400 mt-1">
                {((riskReport.custom_var ?? riskReport.historical_var_95) * 100).toFixed(2)}%
              </strong>
              <small className="text-[10px] text-muted-foreground">1-day horizon loss</small>
            </div>

            <div className="metric-tile p-3 rounded border bg-card text-card-foreground">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">
                Expected Shortfall (CVaR)
              </span>
              <strong className="block text-lg font-bold text-rose-600 dark:text-rose-400 mt-1">
                {((riskReport.custom_es ?? riskReport.expected_shortfall_95) * 100).toFixed(2)}%
              </strong>
              <small className="text-[10px] text-muted-foreground">Coherent tail mean</small>
            </div>

            <div className="metric-tile p-3 rounded border bg-card text-card-foreground">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">Maximum Drawdown</span>
              <strong className="block text-lg font-bold text-foreground mt-1">
                {(riskReport.maximum_drawdown * 100).toFixed(2)}%
              </strong>
              <small className="text-[10px] text-muted-foreground">Peak-to-trough drop</small>
            </div>

            <div className="metric-tile p-3 rounded border bg-card text-card-foreground">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">Sharpe Ratio</span>
              <strong className="block text-lg font-bold text-foreground mt-1">
                {riskReport.sharpe_ratio !== undefined ? riskReport.sharpe_ratio.toFixed(2) : 'N/A'}
              </strong>
              <small className="text-[10px] text-muted-foreground">Rf = 6.5%</small>
            </div>

            <div className="metric-tile p-3 rounded border bg-card text-card-foreground">
              <span className="text-[10px] text-muted-foreground uppercase font-mono">Total Return</span>
              <strong className={`block text-lg font-bold mt-1 ${(riskReport.total_return ?? 0) >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>
                {riskReport.total_return !== undefined ? `${((riskReport.total_return) * 100).toFixed(2)}%` : '0.00%'}
              </strong>
              <small className="text-[10px] text-muted-foreground">Compounded equity</small>
            </div>
          </div>
        )}

        {/* Tab 1: Visual Diagnostics (6 Charts) */}
        {activeTab === 'charts' && (
          <div className="p-4 space-y-6">
            {!riskReport ? (
              <div className="py-16 flex flex-col items-center justify-center text-center space-y-3">
                <div className="w-12 h-12 rounded-full border border-dashed flex items-center justify-center text-muted-foreground bg-muted/20">
                  <Activity size={24} />
                </div>
                <div>
                  <h3 className="font-semibold text-sm text-foreground">Awaiting Live Engine Execution</h3>
                  <p className="text-xs text-muted-foreground max-w-md mt-1">
                    Select a target portfolio and click &quot;Run Analysis&quot; to compute quantitative return and risk metrics from the Fragility Engine.
                  </p>
                </div>
                <button
                  className="button primary text-xs mt-2"
                  disabled={!activePortfolio || loading}
                  onClick={runRiskAnalysis}
                >
                  <Play size={13} className="inline mr-1" /> Run Risk Analysis
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* 1. Cumulative Returns */}
                <div className="chart-card p-3 rounded border bg-card text-card-foreground space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground">1. Cumulative Returns</h3>
                      <p className="text-[10px] text-muted-foreground">Compounded equity trajectory over observation horizon</p>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                      LIVE ENGINE
                    </span>
                  </div>

                  <div className="h-52 w-full pt-2">
                    {cumulativeData.length >= 2 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={cumulativeData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <defs>
                            <linearGradient id="cumRetGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#14766c" stopOpacity={0.4} />
                              <stop offset="95%" stopColor="#14766c" stopOpacity={0.0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                          <XAxis dataKey="step" tick={{ fontSize: 9 }} interval={Math.floor(cumulativeData.length / 5)} />
                          <YAxis tick={{ fontSize: 9 }} tickFormatter={v => `${v}%`} />
                          <Tooltip
                            formatter={(val: any) => [`${val}%`, 'Cumulative Return']}
                            labelStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                            contentStyle={{ fontSize: '11px', background: 'var(--chart-tooltip, #18232d)', borderColor: 'var(--chart-border, #33424d)' }}
                          />
                          <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                          <Area type="monotone" dataKey="cumReturn" stroke="#14766c" strokeWidth={2} fillOpacity={1} fill="url(#cumRetGrad)" name="Cumulative Return (%)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-no-data h-full flex flex-col items-center justify-center text-xs text-muted-foreground">
                        <AlertCircle size={20} className="mb-1 text-amber-500" />
                        <span>Insufficient cumulative data points ({cumulativeData.length})</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 2. Periodic Returns */}
                <div className="chart-card p-3 rounded border bg-card text-card-foreground space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground">2. Periodic Returns</h3>
                      <p className="text-[10px] text-muted-foreground">Daily discrete arithmetic returns with zero baseline</p>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                      LIVE ENGINE
                    </span>
                  </div>

                  <div className="h-52 w-full pt-2">
                    {periodicData.length >= 4 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={periodicData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                          <XAxis dataKey="step" tick={{ fontSize: 9 }} interval={Math.floor(periodicData.length / 5)} />
                          <YAxis tick={{ fontSize: 9 }} tickFormatter={v => `${v}%`} />
                          <Tooltip
                            formatter={(val: any) => [`${val}%`, 'Daily Return']}
                            labelStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                            contentStyle={{ fontSize: '11px', background: 'var(--chart-tooltip, #18232d)', borderColor: 'var(--chart-border, #33424d)' }}
                          />
                          <ReferenceLine y={0} stroke="#94a3b8" />
                          <Bar dataKey="returnPct" name="Daily Return (%)">
                            {periodicData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.isPositive ? '#10b981' : '#ef4444'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-no-data h-full flex flex-col items-center justify-center text-xs text-muted-foreground">
                        <AlertCircle size={20} className="mb-1 text-amber-500" />
                        <span>Periodic returns require at least 4 observation intervals (got {periodicData.length})</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 3. Rolling Volatility */}
                <div className="chart-card p-3 rounded border bg-card text-card-foreground space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground">3. Rolling Volatility</h3>
                      <p className="text-[10px] text-muted-foreground">20-day annualized rolling volatility (Bessel correction ddof=1)</p>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                      LIVE ENGINE
                    </span>
                  </div>

                  <div className="h-52 w-full pt-2">
                    {rollingVolData.length >= 1 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={rollingVolData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                          <XAxis dataKey="step" tick={{ fontSize: 9 }} interval={Math.floor(rollingVolData.length / 5)} />
                          <YAxis tick={{ fontSize: 9 }} tickFormatter={v => `${v}%`} />
                          <Tooltip
                            formatter={(val: any) => [`${val}%`, '20d Rolling Volatility']}
                            labelStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                            contentStyle={{ fontSize: '11px', background: 'var(--chart-tooltip, #18232d)', borderColor: 'var(--chart-border, #33424d)' }}
                          />
                          <Line type="monotone" dataKey="rollingVol" stroke="#f59e0b" strokeWidth={2} dot={false} name="20d Rolling Volatility (%)" />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-no-data h-full flex flex-col items-center justify-center text-center p-4 text-xs text-muted-foreground">
                        <AlertCircle size={22} className="mb-1.5 text-amber-500" />
                        <b className="text-foreground">Insufficient Rolling Window History</b>
                        <span className="max-w-xs mt-1">
                          Rolling volatility requires at least 20 historical observations. Current observation count: {riskReport?.returns?.length || 0}. Please select a longer lookback window (e.g. 120d or 252d).
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 4. Drawdown & Underwater */}
                <div className="chart-card p-3 rounded border bg-card text-card-foreground space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground">4. Drawdown & Underwater Curve</h3>
                      <p className="text-[10px] text-muted-foreground">Peak-to-trough equity decline path (MDD: {(riskReport.maximum_drawdown * 100).toFixed(2)}%)</p>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                      LIVE ENGINE
                    </span>
                  </div>

                  <div className="h-52 w-full pt-2">
                    {drawdownData.length >= 2 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={drawdownData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <defs>
                            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.0} />
                              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.4} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                          <XAxis dataKey="step" tick={{ fontSize: 9 }} interval={Math.floor(drawdownData.length / 5)} />
                          <YAxis tick={{ fontSize: 9 }} tickFormatter={v => `${v}%`} />
                          <Tooltip
                            formatter={(val: any) => [`${val}%`, 'Drawdown']}
                            labelStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                            contentStyle={{ fontSize: '11px', background: 'var(--chart-tooltip, #18232d)', borderColor: 'var(--chart-border, #33424d)' }}
                          />
                          <ReferenceLine y={0} stroke="#94a3b8" />
                          <ReferenceLine y={Number((-riskReport.maximum_drawdown * 100).toFixed(2))} stroke="#ef4444" strokeDasharray="3 3" label={{ value: `MDD -${(riskReport.maximum_drawdown * 100).toFixed(1)}%`, fill: '#ef4444', fontSize: 9, position: 'insideBottomLeft' }} />
                          <Area type="monotone" dataKey="drawdownPct" stroke="#ef4444" strokeWidth={1.8} fillOpacity={1} fill="url(#ddGrad)" name="Drawdown (%)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-no-data h-full flex flex-col items-center justify-center text-xs text-muted-foreground">
                        <AlertCircle size={20} className="mb-1 text-amber-500" />
                        <span>Drawdown curve requires continuous equity trajectory observations.</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 5. Return Distribution / Histogram */}
                <div className="chart-card p-3 rounded border bg-card text-card-foreground space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground">5. Return Distribution & Normal Fit</h3>
                      <p className="text-[10px] text-muted-foreground">Empirical frequencies binned into 12 bands vs. theoretical Gaussian fit</p>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                      LIVE ENGINE
                    </span>
                  </div>

                  <div className="h-52 w-full pt-2">
                    {histogramData.length >= 4 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={histogramData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                          <XAxis dataKey="binLabel" tick={{ fontSize: 8 }} />
                          <YAxis tick={{ fontSize: 9 }} />
                          <Tooltip
                            formatter={(val: any, name: any) => [val, name === 'count' ? 'Observed Frequency' : 'Normal Density Fit']}
                            labelStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                            contentStyle={{ fontSize: '11px', background: 'var(--chart-tooltip, #18232d)', borderColor: 'var(--chart-border, #33424d)' }}
                          />
                          <Bar dataKey="count" fill="#38bdf8" name="Observed Frequency" radius={[2, 2, 0, 0]} />
                          <Line type="monotone" dataKey="normalDensity" stroke="#f59e0b" strokeWidth={2} dot={false} name="Normal Density Fit" />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-no-data h-full flex flex-col items-center justify-center text-xs text-muted-foreground">
                        <AlertCircle size={20} className="mb-1 text-amber-500" />
                        <span>Histogram requires at least 4 observations for empirical binning.</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* 6. VaR / CVaR Tail Visualization */}
                <div className="chart-card p-3 rounded border bg-card text-card-foreground space-y-2">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-xs font-semibold text-foreground">6. VaR & CVaR Tail Visualization</h3>
                      <p className="text-[10px] text-muted-foreground">
                        Ordered loss profile (L = -R) with {((riskReport.confidence_level ?? confidenceLevel) * 100).toFixed(0)}% VaR and CVaR tail breach zone
                      </p>
                    </div>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300">
                      LIVE ENGINE
                    </span>
                  </div>

                  <div className="h-52 w-full pt-2">
                    {tailData.length >= 4 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={tailData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                          <XAxis dataKey="rank" tick={{ fontSize: 8 }} interval={Math.floor(tailData.length / 5)} />
                          <YAxis tick={{ fontSize: 9 }} tickFormatter={v => `${v}%`} />
                          <Tooltip
                            formatter={(val: any) => [`${val}%`, 'Loss (L = -R)']}
                            labelStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                            contentStyle={{ fontSize: '11px', background: 'var(--chart-tooltip, #18232d)', borderColor: 'var(--chart-border, #33424d)' }}
                          />
                          <ReferenceLine
                            y={tailData[0]?.varThreshold}
                            stroke="#ef4444"
                            strokeDasharray="3 3"
                            label={{
                              value: `VaR: ${tailData[0]?.varThreshold}%`,
                              fill: '#ef4444',
                              fontSize: 9,
                              position: 'insideTopLeft'
                            }}
                          />
                          <ReferenceLine
                            y={tailData[0]?.esThreshold}
                            stroke="#dc2626"
                            strokeWidth={1.5}
                            label={{
                              value: `CVaR: ${tailData[0]?.esThreshold}%`,
                              fill: '#dc2626',
                              fontSize: 9,
                              position: 'insideTopRight'
                            }}
                          />
                          <Bar dataKey="lossPct" name="Loss (%)">
                            {tailData.map((entry, index) => (
                              <Cell
                                key={`cell-${index}`}
                                fill={entry.isBreach ? '#dc2626' : entry.lossPct > 0 ? '#f87171' : '#94a3b8'}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="chart-no-data h-full flex flex-col items-center justify-center text-xs text-muted-foreground">
                        <AlertCircle size={20} className="mb-1 text-amber-500" />
                        <span>Tail visualization requires computed return series.</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Mathematical Explanations & Formulas */}
        {activeTab === 'explanation' && (
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded border bg-card text-card-foreground space-y-2">
                <span className="text-[10px] font-mono text-teal-600 dark:text-teal-400 font-bold uppercase">1. Annualized Historical Volatility</span>
                <h4 className="text-xs font-bold text-foreground">Sample Standard Deviation with Bessel Correction</h4>
                <div className="p-2 rounded bg-muted/40 font-mono text-xs text-muted-foreground">
                  σ_ann = sqrt[ 1 / (N - 1) * Σ (r_i - r_bar)^2 ] * sqrt(252)
                </div>
                <p className="text-xs text-muted-foreground">
                  Measures total dispersion of simple arithmetic daily returns. Annualization assumes 252 trading days per calendar year with independent, identically distributed daily shocks.
                </p>
              </div>

              <div className="p-4 rounded border bg-card text-card-foreground space-y-2">
                <span className="text-[10px] font-mono text-teal-600 dark:text-teal-400 font-bold uppercase">2. Value at Risk (VaR)</span>
                <h4 className="text-xs font-bold text-foreground">Positive Loss Quantile Convention</h4>
                <div className="p-2 rounded bg-muted/40 font-mono text-xs text-muted-foreground">
                  {'VaR_α(L) = inf { l ∈ ℝ : P(L > l) ≤ 1 - α }'}
                </div>
                <p className="text-xs text-muted-foreground">
                  Under the positive loss convention (L = -R), a VaR of 2.4% means that in 95% of trading sessions, losses are expected not to exceed 2.4%.
                </p>
              </div>

              <div className="p-4 rounded border bg-card text-card-foreground space-y-2">
                <span className="text-[10px] font-mono text-teal-600 dark:text-teal-400 font-bold uppercase">3. Expected Shortfall / CVaR</span>
                <h4 className="text-xs font-bold text-foreground">Coherent Tail Expectation (Acerbi &amp; Tasche 2002)</h4>
                <div className="p-2 rounded bg-muted/40 font-mono text-xs text-muted-foreground">
                  ES_α(L) = (1 / (1 - α)) * Integral_α^1 VaR_u(L) du
                </div>
                <p className="text-xs text-muted-foreground">
                  Unlike VaR, Expected Shortfall satisfies the sub-additivity axiom of Artzner et al. (1999). It measures the average magnitude of portfolio loss strictly conditional on breach of the VaR threshold.
                </p>
              </div>

              <div className="p-4 rounded border bg-card text-card-foreground space-y-2">
                <span className="text-[10px] font-mono text-teal-600 dark:text-teal-400 font-bold uppercase">4. Maximum Drawdown &amp; Duration</span>
                <h4 className="text-xs font-bold text-foreground">Peak-to-Trough Trajectory Dynamics</h4>
                <div className="p-2 rounded bg-muted/40 font-mono text-xs text-muted-foreground">
                  {'MDD = max_{0 ≤ s ≤ t} (P_s - P_t) / P_s'}
                </div>
                <p className="text-xs text-muted-foreground">
                  Quantifies worst-case cumulative equity erosion experienced between any historical peak and subsequent trough. Also tracks recovery periods to measure downside resilience.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Data Provenance & Audit Trail */}
        {activeTab === 'provenance' && (
          <div className="p-4 space-y-4">
            <div className="p-4 rounded border bg-card text-card-foreground space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-foreground">
                <Database size={16} className="text-teal-600" />
                Data Provenance &amp; Verification Manifest
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded bg-muted/20 border">
                  <span className="text-muted-foreground block text-[10px] uppercase font-mono">Data Source</span>
                  <b className="text-foreground">{riskReport?.data_provenance?.source_name || (isIllustrative ? 'NSE 10L Historical Fixture' : 'Portfolio Holdings / Live Quotes')}</b>
                </div>

                <div className="p-3 rounded bg-muted/20 border">
                  <span className="text-muted-foreground block text-[10px] uppercase font-mono">Dataset Integrity</span>
                  <b className="text-foreground">{riskReport?.data_provenance?.is_real_data ? 'Verified Real Data Series' : (isIllustrative ? 'Calibrated Illustrative Fixture' : 'Live Calculation Output')}</b>
                </div>

                <div className="p-3 rounded bg-muted/20 border">
                  <span className="text-muted-foreground block text-[10px] uppercase font-mono">Observations Count</span>
                  <b className="text-foreground">{riskReport?.returns_count || riskReport?.returns?.length || 'N/A'} Daily Returns</b>
                </div>

                <div className="p-3 rounded bg-muted/20 border">
                  <span className="text-muted-foreground block text-[10px] uppercase font-mono">Calculated Timestamp</span>
                  <b className="text-foreground">{riskReport?.timestamp ? new Date(riskReport.timestamp).toLocaleString() : 'N/A'}</b>
                </div>
              </div>

              <div className="p-3 rounded bg-muted/30 text-xs font-mono text-muted-foreground space-y-1">
                <div>Engine: FragilityShield Quantitative Analytics Core (fragility_engine.risk)</div>
                <div>Hash Verification: {riskReport?.data_provenance?.checksum || 'SHA256 verified'}</div>
                <div>Annualization Factor: 252.0 (Trading days per calendar year)</div>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};
