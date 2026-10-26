import React, { useState, useEffect } from 'react';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ReferenceLine, Scatter, ComposedChart,
} from 'recharts';
import {
  ShieldCheck, ShieldAlert, Activity, CheckCircle2, AlertTriangle, XCircle,
  RefreshCw, Download, ArrowRight, Layers, Sliders, BarChart3, Database,
  TrendingDown, Info, ExternalLink, Calendar, Scale,
} from 'lucide-react';
import { api } from '@/lib/api';

interface RiskModelValidationLabProps {
  navigate?: (path: string) => void;
  notify?: (message: string, type?: 'info' | 'success' | 'warning' | 'error') => void;
}

export const RiskModelValidationLab: React.FC<RiskModelValidationLabProps> = ({
  navigate,
  notify,
}) => {
  const [symbol, setSymbol] = useState('RELIANCE');
  const [modelId, setModelId] = useState('historical_simulation');
  const [confidenceLevel, setConfidenceLevel] = useState(0.95);
  const [trainingWindow, setTrainingWindow] = useState(120);
  const [reEstimationStep, setReEstimationStep] = useState(1);
  const [activeTab, setActiveTab] = useState<'timeline' | 'tests' | 'comparison' | 'log'>('timeline');

  const [loading, setLoading] = useState(false);
  const [validation, setValidation] = useState<any>(null);
  const [comparison, setComparison] = useState<any[]>([]);
  const [comparing, setComparing] = useState(false);

  const loadValidation = async () => {
    setLoading(true);
    try {
      const resp = await api.runRiskModelValidation({
        symbol,
        model_id: modelId,
        confidence_level: confidenceLevel,
        training_window: trainingWindow,
        re_estimation_step: reEstimationStep,
      });
      if (resp && resp.success && resp.validation) {
        setValidation(resp.validation);
      }
    } catch (err: any) {
      if (notify) notify(err.message || 'Validation backtest failed.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadComparison = async () => {
    setComparing(true);
    try {
      const resp = await api.compareRiskModels({
        symbol,
        confidence_level: confidenceLevel,
        training_window: trainingWindow,
      });
      if (resp && resp.success && resp.comparison) {
        setComparison(resp.comparison);
      }
    } catch (err: any) {
      if (notify) notify(err.message || 'Model comparison failed.', 'error');
    } finally {
      setComparing(false);
    }
  };

  useEffect(() => {
    loadValidation();
  }, [symbol, modelId, confidenceLevel, trainingWindow, reEstimationStep]);

  useEffect(() => {
    if (activeTab === 'comparison') {
      loadComparison();
    }
  }, [activeTab, symbol, confidenceLevel, trainingWindow]);

  const kupiec = validation?.kupiec_unconditional_coverage;
  const christoffersen = validation?.christoffersen_conditional_coverage;
  const esTest = validation?.expected_shortfall_validation;
  const forecasts = validation?.forecast_sample || [];

  // Filter breaches for log
  const breachList = forecasts.filter((f: any) => f.is_breach);

  // Prepare chart data with loss % and VaR %
  const chartData = forecasts.map((f: any) => ({
    date: f.date,
    lossPct: Number((f.realized_loss * 100).toFixed(2)),
    varPct: Number((f.predicted_var * 100).toFixed(2)),
    esPct: Number((f.predicted_es * 100).toFixed(2)),
    isBreach: f.is_breach,
    breachLoss: f.is_breach ? Number((f.realized_loss * 100).toFixed(2)) : null,
  }));

  const exportBreachCsv = () => {
    if (!breachList.length) {
      if (notify) notify('No breaches to export.', 'info');
      return;
    }
    const headers = ['date', 'realized_loss_pct', 'predicted_var_pct', 'predicted_es_pct', 'train_window_start', 'train_window_end'];
    const rows = breachList.map((b: any) => [
      b.date,
      (b.realized_loss * 100).toFixed(3),
      (b.predicted_var * 100).toFixed(3),
      (b.predicted_es * 100).toFixed(3),
      b.train_start_date,
      b.train_end_date,
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `var_breaches_${symbol}_${modelId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    if (notify) notify(`Exported ${breachList.length} breaches to CSV.`, 'success');
  };

  return (
    <div className="terminal-card space-y-6">
      {/* 1. Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            STATISTICAL RESEARCH & BACKTESTING / 03
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2 mt-1">
            <Scale className="w-6 h-6 text-primary" />
            Risk Model Validation & Backtesting Observatory
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl">
            Statistically evaluate whether quantitative risk model forecasts align with subsequently realized outcomes.
            Implements Kupiec unconditional coverage, Christoffersen Markov independence, and Expected Shortfall tail residual validation.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => loadValidation()}
            disabled={loading}
            className="terminal-button-secondary text-xs flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Rerun Validation
          </button>
          <button
            onClick={exportBreachCsv}
            disabled={!breachList.length}
            className="terminal-button-secondary text-xs flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Export Breaches
          </button>
        </div>
      </div>

      {/* 2. Top Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Model Spec */}
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Model Evaluated</span>
            <Layers className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="text-base font-semibold mt-1 truncate">
            {validation?.model_name || 'Historical Simulation'}
          </div>
          <div className="text-xs text-muted-foreground mt-1 flex items-center gap-2">
            <span>Conf: {confidenceLevel * 100}%</span>
            <span>•</span>
            <span>Window: {validation?.training_window_size || trainingWindow}d</span>
          </div>
        </div>

        {/* Kupiec POF */}
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Kupiec POF Test</span>
            {kupiec?.decision === 'ACCEPT' ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />
            )}
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className={`text-base font-bold ${kupiec?.decision === 'ACCEPT' ? 'text-emerald-400' : 'text-rose-400'}`}>
              {kupiec?.decision === 'ACCEPT' ? 'ACCEPTED (PASS)' : kupiec?.decision || 'RUNNING'}
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Rate: {((kupiec?.empirical_rate || 0) * 100).toFixed(2)}% (Nominal: {((kupiec?.expected_rate || 0) * 100).toFixed(1)}%) • p={kupiec?.p_value?.toFixed(4) || '—'}
          </div>
        </div>

        {/* Christoffersen Independence */}
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Independence Test</span>
            {christoffersen?.independence_test?.decision === 'ACCEPT' ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            )}
          </div>
          <div className="text-base font-bold mt-1 text-foreground">
            {christoffersen?.independence_test?.decision === 'ACCEPT' ? 'NO CLUSTERING (PASS)' : 'CLUSTERED'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            LR: {christoffersen?.independence_test?.lr_stat?.toFixed(2) || '0.00'} • p={christoffersen?.independence_test?.p_value?.toFixed(4) || '1.000'}
          </div>
        </div>

        {/* Expected Shortfall */}
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>ES Tail Residuals</span>
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-base font-bold mt-1 text-foreground">
            {esTest?.status === 'PASS' ? 'CALIBRATED (PASS)' : esTest?.status === 'INSUFFICIENT_EVIDENCE' ? 'INSUFFICIENT DATA' : 'UNDERESTIMATED'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Exceptions: {esTest?.n_tail_losses || 0} • Excess: {((esTest?.mean_excess_ratio || 0) * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {/* 3. Parameter Controls */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 p-3 border border-border/60 rounded bg-card/40 text-xs">
        <div>
          <label className="text-muted-foreground block mb-1 font-mono">INSTRUMENT / ASSET</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value="RELIANCE">RELIANCE (Reliance Ind.)</option>
            <option value="NIFTY 50">NIFTY 50 (Benchmark)</option>
            <option value="TCS">TCS (Tata Consultancy)</option>
            <option value="INFY">INFY (Infosys Ltd.)</option>
            <option value="HDFCBANK">HDFCBANK (HDFC Bank)</option>
            <option value="ICICIBANK">ICICIBANK (ICICI Bank)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono">RISK MODEL FAMILY</label>
          <select
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value="historical_simulation">Historical Simulation VaR</option>
            <option value="parametric_gaussian">Parametric Gaussian VaR</option>
            <option value="cornish_fisher">Cornish-Fisher Skew/Kurt VaR</option>
            <option value="ewma">RiskMetrics EWMA Volatility VaR</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono">CONFIDENCE LEVEL</label>
          <select
            value={confidenceLevel}
            onChange={(e) => setConfidenceLevel(parseFloat(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={0.95}>95% Daily VaR (p = 0.05)</option>
            <option value={0.99}>99% Daily VaR (p = 0.01)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono">TRAINING WINDOW</label>
          <select
            value={trainingWindow}
            onChange={(e) => setTrainingWindow(parseInt(e.target.value, 10))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={60}>60 Sessions (Quarterly)</option>
            <option value={120}>120 Sessions (Semi-Annual)</option>
            <option value={252}>252 Sessions (Annual Standard)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono">RE-ESTIMATION STEP</label>
          <select
            value={reEstimationStep}
            onChange={(e) => setReEstimationStep(parseInt(e.target.value, 10))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={1}>Every 1 Day (Daily Rolling)</option>
            <option value={5}>Every 5 Days (Weekly Re-estimate)</option>
            <option value={20}>Every 20 Days (Monthly Re-estimate)</option>
          </select>
        </div>
      </div>

      {/* 4. Tab Navigation */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('timeline')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'timeline'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Forecast vs Realized Timeline
        </button>
        <button
          onClick={() => setActiveTab('tests')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'tests'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Statistical Test Battery (Kupiec & Christoffersen)
        </button>
        <button
          onClick={() => setActiveTab('comparison')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'comparison'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Multi-Model Side-by-Side Comparison
        </button>
        <button
          onClick={() => setActiveTab('log')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors flex items-center gap-1.5 ${
            activeTab === 'log'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Exceptions & Breach Log
          <span className="px-1.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 text-[10px]">
            {breachList.length}
          </span>
        </button>
      </div>

      {/* Tab 1: Forecast vs Realized Timeline */}
      {activeTab === 'timeline' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs">
            <span className="font-mono text-muted-foreground">
              Realized Loss (%) vs Model Predicted VaR & Expected Shortfall Thresholds
            </span>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 text-muted-foreground">
                <span className="inline-block w-2.5 h-2.5 bg-sky-500 rounded-sm" /> Realized Loss %
              </span>
              <span className="flex items-center gap-1 text-muted-foreground">
                <span className="inline-block w-2.5 h-0.5 bg-amber-400" /> Predicted VaR {confidenceLevel * 100}%
              </span>
              <span className="flex items-center gap-1 text-muted-foreground">
                <span className="inline-block w-2.5 h-0.5 bg-rose-500" /> Predicted ES
              </span>
              <span className="flex items-center gap-1 text-rose-400 font-semibold">
                ● Breach Point ({breachList.length})
              </span>
            </div>
          </div>

          <div className="h-80 w-full bg-card/40 border border-border/80 rounded p-3">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                <XAxis dataKey="date" stroke="#666" tick={{ fontSize: 10 }} />
                <YAxis stroke="#666" tick={{ fontSize: 10 }} unit="%" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }}
                  formatter={(val: any, name: string) => [`${Number(val).toFixed(2)}%`, name]}
                />
                <Bar dataKey="lossPct" fill="#0284c7" fillOpacity={0.6} name="Realized Loss" />
                <Line type="stepAfter" dataKey="varPct" stroke="#f59e0b" strokeWidth={2} dot={false} name="VaR Threshold" />
                <Line type="stepAfter" dataKey="esPct" stroke="#f43f5e" strokeWidth={1.5} strokeDasharray="3 3" dot={false} name="Expected Shortfall" />
                <Scatter dataKey="breachLoss" fill="#ef4444" name="Breach Occurred" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Provenance and Timeline Audit Strip */}
          <div className="p-3 border border-border/70 rounded bg-card/30 flex flex-col md:flex-row md:items-center justify-between text-xs gap-2">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-emerald-400" />
              <span className="text-muted-foreground">SHA-256 Dataset Fingerprint:</span>
              <code className="text-emerald-400 font-mono text-[11px] truncate max-w-xs">
                {validation?.dataset_fingerprint || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
              </code>
            </div>

            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span className="text-muted-foreground">Zero-Lookahead Audit:</span>
              <span className="text-emerald-400 font-semibold">
                {validation?.leakage_check_passed ? 'VERIFIED (Train End < Eval Date)' : 'LEAKAGE DETECTED'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Statistical Test Battery */}
      {activeTab === 'tests' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          {/* Kupiec Unconditional Test Detail */}
          <div className="border border-border/80 rounded p-4 bg-card/40 space-y-3">
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <h3 className="font-semibold text-foreground text-sm flex items-center gap-1.5">
                <Scale className="w-4 h-4 text-primary" />
                Kupiec POF Unconditional Coverage Test
              </h3>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                kupiec?.decision === 'ACCEPT' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'
              }`}>
                {kupiec?.decision}
              </span>
            </div>

            <p className="text-muted-foreground text-[11px]">
              Tests null hypothesis H0: E[I_t] = p. Likelihood Ratio asymptotically follows Chi²(1).
            </p>

            <div className="grid grid-cols-2 gap-2 font-mono">
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">EVALUATED OBS</span>
                <span className="text-sm font-bold text-foreground">{kupiec?.n_observations}</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">TOTAL EXCEPTIONS</span>
                <span className="text-sm font-bold text-foreground">{kupiec?.n_exceptions}</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">EMPIRICAL RATE</span>
                <span className="text-sm font-bold text-primary">{((kupiec?.empirical_rate || 0) * 100).toFixed(2)}%</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">NOMINAL RATE</span>
                <span className="text-sm font-bold text-foreground">{((kupiec?.expected_rate || 0) * 100).toFixed(2)}%</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">LR STATISTIC</span>
                <span className="text-sm font-bold text-foreground">{kupiec?.lr_stat?.toFixed(4)}</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">P-VALUE (Chi²(1))</span>
                <span className={`text-sm font-bold ${(kupiec?.p_value || 0) > 0.05 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {kupiec?.p_value?.toFixed(5)}
                </span>
              </div>
            </div>

            <div className="text-[11px] text-muted-foreground bg-background/40 p-2.5 rounded border border-border/40">
              <span className="font-semibold text-foreground">95% Clopper-Pearson CI: </span>
              [{((kupiec?.ci_lower || 0) * 100).toFixed(2)}%, {((kupiec?.ci_upper || 0) * 100).toFixed(2)}%]
            </div>
          </div>

          {/* Christoffersen Independence Test Detail */}
          <div className="border border-border/80 rounded p-4 bg-card/40 space-y-3">
            <div className="flex items-center justify-between border-b border-border/60 pb-2">
              <h3 className="font-semibold text-foreground text-sm flex items-center gap-1.5">
                <TrendingDown className="w-4 h-4 text-cyan-400" />
                Christoffersen Independence & Joint Test
              </h3>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                christoffersen?.independence_test?.decision === 'ACCEPT'
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : 'bg-amber-500/20 text-amber-300'
              }`}>
                {christoffersen?.independence_test?.decision}
              </span>
            </div>

            <p className="text-muted-foreground text-[11px]">
              Tests for temporal clustering of risk breaches via 1st-order Markov transitions.
            </p>

            <div className="grid grid-cols-2 gap-2 font-mono">
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">NO BREACH → NO BREACH (n00)</span>
                <span className="text-sm font-bold text-foreground">{christoffersen?.contingency_table?.n00_no_to_no}</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">NO BREACH → BREACH (n01)</span>
                <span className="text-sm font-bold text-foreground">{christoffersen?.contingency_table?.n01_no_to_exception}</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">BREACH → NO BREACH (n10)</span>
                <span className="text-sm font-bold text-foreground">{christoffersen?.contingency_table?.n10_exception_to_no}</span>
              </div>
              <div className="bg-background/80 p-2 rounded border border-border/40">
                <span className="text-muted-foreground text-[10px] block">CONSECUTIVE BREACHES (n11)</span>
                <span className={`text-sm font-bold ${(christoffersen?.contingency_table?.n11_exception_to_exception || 0) > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {christoffersen?.contingency_table?.n11_exception_to_exception || 0}
                </span>
              </div>
            </div>

            <div className="bg-background/80 p-2.5 rounded border border-border/40 space-y-1 text-[11px]">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Independence LR Stat (Chi²(1)):</span>
                <span className="font-mono font-bold text-foreground">{christoffersen?.independence_test?.lr_stat?.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Independence P-Value:</span>
                <span className="font-mono font-bold text-foreground">{christoffersen?.independence_test?.p_value?.toFixed(5)}</span>
              </div>
              <div className="flex justify-between border-t border-border/40 pt-1">
                <span className="text-muted-foreground">Joint Conditional Coverage (LR_cc ~ Chi²(2)):</span>
                <span className="font-mono font-bold text-primary">{christoffersen?.conditional_coverage_test?.lr_stat?.toFixed(4)} (p={christoffersen?.conditional_coverage_test?.p_value?.toFixed(5)})</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Multi-Model Comparison Table */}
      {activeTab === 'comparison' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              Comparative backtest over identical historical return windows ({validation?.evaluation_window_size} sessions)
            </span>
            <button
              onClick={loadComparison}
              disabled={comparing}
              className="terminal-button-secondary text-xs flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${comparing ? 'animate-spin' : ''}`} />
              Re-evaluate All Models
            </button>
          </div>

          <div className="border border-border/80 rounded overflow-x-auto bg-card/30">
            <table className="w-full text-xs text-left">
              <thead className="bg-muted/40 font-mono text-muted-foreground border-b border-border/60">
                <tr>
                  <th className="p-3">MODEL SPECIFICATION</th>
                  <th className="p-3">OBS</th>
                  <th className="p-3">EXCEPTIONS</th>
                  <th className="p-3">EMPIRICAL RATE</th>
                  <th className="p-3">KUPIEC LR</th>
                  <th className="p-3">KUPIEC P-VAL</th>
                  <th className="p-3">INDEPENDENCE P-VAL</th>
                  <th className="p-3">ES STATUS</th>
                  <th className="p-3">VERDICT</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono">
                {comparison.map((c: any) => (
                  <tr key={c.model_id} className="hover:bg-muted/20">
                    <td className="p-3 font-semibold text-foreground flex items-center gap-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-primary" />
                      {c.model_name}
                    </td>
                    <td className="p-3">{c.n_observations}</td>
                    <td className="p-3 font-bold text-foreground">{c.n_exceptions}</td>
                    <td className="p-3">{(c.empirical_rate * 100).toFixed(2)}%</td>
                    <td className="p-3">{c.kupiec_lr?.toFixed(3)}</td>
                    <td className="p-3">
                      <span className={c.kupiec_p_value > 0.05 ? 'text-emerald-400' : 'text-rose-400 font-bold'}>
                        {c.kupiec_p_value?.toFixed(4)}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={c.christoffersen_p_value > 0.05 ? 'text-emerald-400' : 'text-amber-400 font-bold'}>
                        {c.christoffersen_p_value?.toFixed(4)}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="text-[11px] text-muted-foreground">{c.es_validation_status}</span>
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        c.kupiec_decision === 'ACCEPT'
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}>
                        {c.kupiec_decision}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 4: Exceptions & Breach Log */}
      {activeTab === 'log' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              Total {breachList.length} exceptions observed out of {forecasts.length} evaluation sessions.
            </span>
            <button
              onClick={exportBreachCsv}
              className="terminal-button-secondary text-xs flex items-center gap-1.5"
            >
              <Download className="w-3.5 h-3.5" />
              Download Breach CSV
            </button>
          </div>

          <div className="border border-border/80 rounded overflow-x-auto bg-card/30">
            <table className="w-full text-xs text-left">
              <thead className="bg-muted/40 font-mono text-muted-foreground border-b border-border/60">
                <tr>
                  <th className="p-2.5">BREACH DATE</th>
                  <th className="p-2.5">REALIZED LOSS</th>
                  <th className="p-2.5">PREDICTED VAR</th>
                  <th className="p-2.5">PREDICTED ES</th>
                  <th className="p-2.5">EXCESS OVER VAR</th>
                  <th className="p-2.5">IN-SAMPLE TRAINING WINDOW</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono">
                {breachList.map((b: any, idx: number) => {
                  const excess = (b.realized_loss - b.predicted_var) * 100;
                  return (
                    <tr key={idx} className="hover:bg-rose-500/5">
                      <td className="p-2.5 font-bold text-rose-400 flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {b.date}
                      </td>
                      <td className="p-2.5 text-foreground font-semibold">{(b.realized_loss * 100).toFixed(2)}%</td>
                      <td className="p-2.5 text-amber-400">{(b.predicted_var * 100).toFixed(2)}%</td>
                      <td className="p-2.5 text-muted-foreground">{(b.predicted_es * 100).toFixed(2)}%</td>
                      <td className="p-2.5 text-rose-300 font-bold">+{excess.toFixed(2)}%</td>
                      <td className="p-2.5 text-muted-foreground text-[11px]">
                        {b.train_start_date} → {b.train_end_date}
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
  );
};
