import React, { useState, useEffect, useMemo } from 'react';
import {
  Activity,
  AlertOctagon,
  ArrowDownRight,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Cpu,
  Download,
  Filter,
  Flame,
  Gauge,
  Layers,
  Percent,
  Play,
  RefreshCw,
  Search,
  ShieldAlert,
  Sliders,
  TrendingDown,
  Zap,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  CartesianGrid,
  Cell,
  LineChart,
  Line,
  ReferenceLine,
} from 'recharts';
import { api } from '@/lib/api';

interface TailRiskLabProps {
  navigate: (path: string) => void;
  notify: (msg: string) => void;
}

export const TailRiskReverseStressLab: React.FC<TailRiskLabProps> = ({ navigate, notify }) => {
  // Primary State
  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE');
  const [targetLossPct, setTargetLossPct] = useState(0.20); // 20%
  const [dominantSector, setDominantSector] = useState('');
  const [assetOverride, setAssetOverride] = useState('');
  const [bootstrapReps, setBootstrapReps] = useState(250);
  const [activeTab, setActiveTab] = useState<'distribution' | 'comparison' | 'reverseStress' | 'surface'>('distribution');

  // Async Data State
  const [loading, setLoading] = useState(false);
  const [solving, setSolving] = useState(false);
  const [tailRisk, setTailRisk] = useState<any>(null);
  const [reverseSolution, setReverseSolution] = useState<any>(null);
  const [bootstrapData, setBootstrapData] = useState<any>(null);
  const [surfaceData, setSurfaceData] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Available real instruments
  const availableSymbols = [
    { id: 'RELIANCE', name: 'Reliance Industries Ltd.', sector: 'Energy' },
    { id: 'NIFTY 50', name: 'Nifty 50 Index', sector: 'Index' },
    { id: 'TCS', name: 'Tata Consultancy Services', sector: 'Technology' },
    { id: 'INFY', name: 'Infosys Ltd.', sector: 'Technology' },
    { id: 'HDFCBANK', name: 'HDFC Bank Ltd.', sector: 'Financials' },
    { id: 'ICICIBANK', name: 'ICICI Bank Ltd.', sector: 'Financials' },
  ];

  // Fetch initial tail risk metrics
  const loadTailRiskAnalysis = async (symbolToLoad = selectedSymbol) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const resp = await api.analyzeTailRisk({ symbol: symbolToLoad });
      if (resp.success && resp.tail_risk) {
        setTailRisk(resp.tail_risk);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to compute tail risk metrics');
      notify(`Tail risk error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Run Reverse Stress Solver
  const solveReverseStress = async (targetPct?: number) => {
    const effectivePct = targetPct !== undefined ? targetPct : targetLossPct;
    setSolving(true);
    try {
      const resp = await api.runReverseStress({
        target_loss_pct: effectivePct,
        dominant_sector: dominantSector || undefined,
        asset_id: assetOverride || undefined,
      });
      if (resp.success && resp.solution) {
        setReverseSolution(resp.solution);
        notify(`Solved reverse stress scenario for ${(effectivePct * 100).toFixed(0)}% loss: ${(resp.solution.market_shock * 100).toFixed(1)}% market shock`);
      }
    } catch (err: any) {
      notify(`Reverse stress solve failed: ${err.message}`);
    } finally {
      setSolving(false);
    }
  };

  // Run Block Bootstrap
  const runBootstrapSimulation = async () => {
    try {
      notify('Running stationary block bootstrap (seed=42)...');
      const resp = await api.runTailRiskBootstrap({
        symbol: selectedSymbol,
        replications: bootstrapReps,
        block_length: 5,
        confidence_level: 0.95,
      });
      if (resp.success && resp.bootstrap) {
        setBootstrapData(resp.bootstrap);
        notify('Block bootstrap simulation completed');
      }
    } catch (err: any) {
      notify(`Bootstrap error: ${err.message}`);
    }
  };

  // Load Sensitivity Surface
  const loadSensitivitySurface = async (targetPct?: number) => {
    const effectivePct = targetPct !== undefined ? targetPct : targetLossPct;
    try {
      const resp = await api.getReverseStressSensitivitySurface({
        target_loss_pct: effectivePct,
        grid_steps: 7,
      });
      if (resp.success && resp.surface) {
        setSurfaceData(resp.surface);
      }
    } catch (err: any) {
      notify(`Surface load error: ${err.message}`);
    }
  };

  // Initial load
  useEffect(() => {
    loadTailRiskAnalysis(selectedSymbol);
    solveReverseStress(targetLossPct);
    loadSensitivitySurface(targetLossPct);
  }, [selectedSymbol]);

  // When target loss changes, auto-refresh reverse stress and surface
  const handleTargetLossChange = (val: number) => {
    setTargetLossPct(val);
    solveReverseStress(val);
    loadSensitivitySurface(val);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Banner & Eyebrow */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--accent-primary)] mb-1">
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>RISK LABORATORY / 04</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            Tail Risk & Reverse Stress Testing Lab
          </h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Non-Gaussian extreme loss analytics, Hill tail index, Cornish-Fisher expansion, and multi-factor reverse stress search.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            className="input text-xs font-mono"
            value={selectedSymbol}
            onChange={(e) => {
              setSelectedSymbol(e.target.value);
            }}
          >
            {availableSymbols.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id} — {s.name} ({s.sector})
              </option>
            ))}
          </select>

          <button
            className="button secondary text-xs font-mono flex items-center gap-1.5"
            onClick={() => {
              loadTailRiskAnalysis();
              solveReverseStress();
              loadSensitivitySurface();
            }}
            disabled={loading || solving}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Recalculate</span>
          </button>
        </div>
      </div>

      {/* Target Loss Controller Bar */}
      <div className="card p-4 bg-[var(--bg-card)] border border-[var(--border-subtle)]">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center justify-between text-xs font-mono mb-1.5">
              <span className="text-[var(--text-secondary)]">Reverse Stress Loss Threshold:</span>
              <span className="font-bold text-[var(--accent-danger)] text-sm">
                {(targetLossPct * 100).toFixed(0)}% Drawdown
              </span>
            </div>
            <input
              type="range"
              min="0.05"
              max="0.45"
              step="0.05"
              value={targetLossPct}
              onChange={(e) => handleTargetLossChange(parseFloat(e.target.value))}
              className="w-full accent-[var(--accent-danger)] cursor-pointer"
            />
            <div className="flex justify-between text-[10px] font-mono text-[var(--text-muted)] mt-1">
              <span>5% (Minor correction)</span>
              <span>15% (Flash crash)</span>
              <span>25% (Bear market)</span>
              <span>35% (Liquidity crisis)</span>
              <span>45% (Catastrophic tail)</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              className="button primary text-xs font-mono flex items-center gap-1.5"
              onClick={() => solveReverseStress()}
              disabled={solving}
            >
              <Zap className={`w-3.5 h-3.5 ${solving ? 'animate-pulse' : ''}`} />
              <span>{solving ? 'Solving...' : 'Solve Reverse Stress'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Metric KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Annual Volatility</span>
          <div className="text-xl font-bold font-mono text-[var(--text-primary)] mt-1">
            {tailRisk ? `${(tailRisk.annualized_volatility * 100).toFixed(1)}%` : '—'}
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">Square-root-252 scale</span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Historical VaR (95%)</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-warning)] mt-1">
            {tailRisk?.var_metrics?.hist_95 ? `${(tailRisk.var_metrics.hist_95 * 100).toFixed(2)}%` : '—'}
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">1-Day horizon</span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Expected Shortfall (95%)</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-danger)] mt-1">
            {tailRisk?.es_metrics?.hist_95 ? `${(tailRisk.es_metrics.hist_95 * 100).toFixed(2)}%` : '—'}
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">Conditional VaR (CVaR)</span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Cornish-Fisher VaR</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-danger)] mt-1">
            {tailRisk?.var_metrics?.cf_95 ? `${(tailRisk.var_metrics.cf_95 * 100).toFixed(2)}%` : '—'}
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">Skew & kurtosis penalty</span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Hill Tail Index (α)</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-info)] mt-1">
            {tailRisk?.hill_tail_index ? tailRisk.hill_tail_index.toFixed(2) : '—'}
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">
            {tailRisk?.hill_tail_index < 3 ? 'Fat tail (leptokurtic)' : 'Near Gaussian'}
          </span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Skew / Kurtosis</span>
          <div className="text-base font-bold font-mono text-[var(--text-primary)] mt-1">
            {tailRisk ? `${tailRisk.skewness.toFixed(2)} / ${tailRisk.excess_kurtosis.toFixed(1)}` : '—'}
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">Fisher excess kurt</span>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-[var(--border-subtle)] text-xs font-mono">
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors ${
            activeTab === 'distribution'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('distribution')}
        >
          1. Distribution & Worst Days
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors ${
            activeTab === 'comparison'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('comparison')}
        >
          2. Multi-Method Comparison & Bootstrap
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors ${
            activeTab === 'reverseStress'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('reverseStress')}
        >
          3. Multi-Factor Reverse Stress Solution
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors ${
            activeTab === 'surface'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('surface')}
        >
          4. Sensitivity Surface & Frontier
        </button>
      </div>

      {/* Tab 1: Return Distribution & Worst Days */}
      {activeTab === 'distribution' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Histogram Chart */}
            <div className="lg:col-span-2 card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)]">
                  Daily Return Distribution & Tail Cutoff
                </span>
                <span className="text-[11px] font-mono text-[var(--text-muted)]">
                  Observations: {tailRisk?.sample_size || 0}
                </span>
              </div>

              <div className="h-64">
                {tailRisk?.distribution_histogram ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={tailRisk.distribution_histogram}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" opacity={0.4} />
                      <XAxis dataKey="bin_center" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} unit="%" />
                      <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                      <RechartsTooltip
                        contentStyle={{
                          backgroundColor: 'var(--bg-card)',
                          borderColor: 'var(--border-subtle)',
                          fontSize: '11px',
                        }}
                      />
                      <Bar dataKey="count" name="Frequency">
                        {tailRisk.distribution_histogram.map((entry: any, index: number) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={entry.is_tail_loss ? 'var(--accent-danger)' : 'var(--accent-primary)'}
                            opacity={entry.is_tail_loss ? 0.9 : 0.6}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-full text-xs font-mono text-[var(--text-muted)]">
                    Loading distribution histogram...
                  </div>
                )}
              </div>

              <div className="flex items-center justify-center gap-6 mt-3 text-xs font-mono text-[var(--text-secondary)]">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 bg-[var(--accent-danger)] rounded-sm" />
                  <span>Tail Loss (&lt; -VaR 95%)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 bg-[var(--accent-primary)] opacity-60 rounded-sm" />
                  <span>Central Distribution</span>
                </div>
              </div>
            </div>

            {/* Worst Historical Drawdowns & Summary */}
            <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] space-y-4">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)] block">
                Tail Summary & Max Drawdown
              </span>

              <div className="p-3 bg-[var(--bg-secondary)] rounded border border-[var(--border-subtle)] space-y-2 text-xs font-mono">
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">Maximum Peak-to-Trough:</span>
                  <span className="text-[var(--accent-danger)] font-bold">
                    {tailRisk?.worst_historical_drawdowns?.[0]?.max_drawdown_pct || 0}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">Drawdown Duration:</span>
                  <span className="text-[var(--text-primary)]">
                    {tailRisk?.worst_historical_drawdowns?.[0]?.duration_days || 0} trading sessions
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--text-secondary)]">Recovery Status:</span>
                  <span className="text-[var(--accent-success)]">
                    {tailRisk?.worst_historical_drawdowns?.[0]?.recovery_index ? 'Recovered' : 'Unrecovered'}
                  </span>
                </div>
              </div>

              <div className="text-xs text-[var(--text-secondary)] leading-relaxed">
                The Hill Tail Index estimate of <strong>{tailRisk?.hill_tail_index}</strong> indicates heavy-tailed
                behavior. Standard Gaussian assumptions will systematically underestimate both the frequency and magnitude
                of severe market drops.
              </div>
            </div>
          </div>

          {/* Worst Historical Single-Day Losses Table */}
          <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)] block mb-3">
              10 Worst Historical Daily Shocks ({selectedSymbol})
            </span>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)] text-left">
                    <th className="py-2 px-3">Rank</th>
                    <th className="py-2 px-3">Observation Date</th>
                    <th className="py-2 px-3">Return %</th>
                    <th className="py-2 px-3">Realized Loss %</th>
                    <th className="py-2 px-3">Severity vs VaR (95%)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {tailRisk?.worst_days?.map((d: any, idx: number) => {
                    const var95 = (tailRisk.var_metrics.hist_95 * 100);
                    const ratio = var95 > 0 ? (d.loss_pct / var95).toFixed(1) : '1.0';
                    return (
                      <tr key={idx} className="hover:bg-[var(--bg-secondary)] transition-colors">
                        <td className="py-2 px-3 font-bold text-[var(--accent-danger)]">#{idx + 1}</td>
                        <td className="py-2 px-3">{d.date}</td>
                        <td className="py-2 px-3 text-[var(--accent-danger)] font-bold">{d.return_pct.toFixed(2)}%</td>
                        <td className="py-2 px-3">{d.loss_pct.toFixed(2)}%</td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-950 text-red-300 border border-red-800">
                            {ratio}x VaR
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Multi-Method Comparison & Bootstrap */}
      {activeTab === 'comparison' && (
        <div className="space-y-6">
          <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)] block">
                  Methodology Comparison across Confidence Levels
                </span>
                <span className="text-xs text-[var(--text-secondary)]">
                  Side-by-side evaluation of Historical Simulation vs Parametric Gaussian vs Cornish-Fisher Expansion
                </span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)] text-left">
                    <th className="py-2 px-3">Confidence Level</th>
                    <th className="py-2 px-3">Historical VaR</th>
                    <th className="py-2 px-3">Parametric Normal VaR</th>
                    <th className="py-2 px-3">Cornish-Fisher VaR</th>
                    <th className="py-2 px-3">Historical ES (CVaR)</th>
                    <th className="py-2 px-3">Cornish-Fisher ES</th>
                    <th className="py-2 px-3">Non-Gaussian Delta</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {[
                    { label: '90.0%', h_var: 'hist_90', p_var: 'param_90', cf_var: 'cf_90', h_es: 'hist_90', cf_es: 'cf_90' },
                    { label: '95.0%', h_var: 'hist_95', p_var: 'param_95', cf_var: 'cf_95', h_es: 'hist_95', cf_es: 'cf_95' },
                    { label: '97.5%', h_var: 'hist_97_5', p_var: 'param_97_5', cf_var: 'cf_97_5', h_es: 'hist_97_5', cf_es: 'cf_97_5' },
                    { label: '99.0%', h_var: 'hist_99', p_var: 'param_99', cf_var: 'cf_99', h_es: 'hist_99', cf_es: 'cf_99' },
                  ].map((row, idx) => {
                    const h_v = tailRisk?.var_metrics?.[row.h_var] ? (tailRisk.var_metrics[row.h_var] * 100).toFixed(2) : '—';
                    const p_v = tailRisk?.var_metrics?.[row.p_var] ? (tailRisk.var_metrics[row.p_var] * 100).toFixed(2) : '—';
                    const cf_v = tailRisk?.var_metrics?.[row.cf_var] ? (tailRisk.var_metrics[row.cf_var] * 100).toFixed(2) : '—';
                    const h_e = tailRisk?.es_metrics?.[row.h_es] ? (tailRisk.es_metrics[row.h_es] * 100).toFixed(2) : '—';
                    const cf_e = tailRisk?.es_metrics?.[row.cf_es] ? (tailRisk.es_metrics[row.cf_es] * 100).toFixed(2) : '—';
                    const delta = (parseFloat(cf_v) - parseFloat(p_v)).toFixed(2);
                    return (
                      <tr key={idx} className="hover:bg-[var(--bg-secondary)] transition-colors">
                        <td className="py-2.5 px-3 font-bold text-[var(--accent-primary)]">{row.label}</td>
                        <td className="py-2.5 px-3">{h_v}%</td>
                        <td className="py-2.5 px-3 text-[var(--text-muted)]">{p_v}%</td>
                        <td className="py-2.5 px-3 font-bold text-[var(--accent-warning)]">{cf_v}%</td>
                        <td className="py-2.5 px-3 text-[var(--accent-danger)]">{h_e}%</td>
                        <td className="py-2.5 px-3 text-[var(--accent-danger)] font-bold">{cf_e}%</td>
                        <td className="py-2.5 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${parseFloat(delta) >= 0 ? 'bg-amber-950 text-amber-300' : 'bg-slate-800 text-slate-300'}`}>
                            {parseFloat(delta) > 0 ? `+${delta}%` : `${delta}%`}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Stationary Block Bootstrap Card */}
          <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)] block">
                  Stationary Block Bootstrap Resampling
                </span>
                <span className="text-xs text-[var(--text-secondary)]">
                  Empirical confidence intervals preserving autocorrelation and volatility clustering
                </span>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="50"
                  max="1000"
                  step="50"
                  value={bootstrapReps}
                  onChange={(e) => setBootstrapReps(parseInt(e.target.value) || 250)}
                  className="input w-24 text-xs font-mono"
                />
                <button
                  className="button secondary text-xs font-mono flex items-center gap-1.5"
                  onClick={runBootstrapSimulation}
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>Run Bootstrap</span>
                </button>
              </div>
            </div>

            {bootstrapData ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-[var(--bg-secondary)] rounded border border-[var(--border-subtle)] font-mono text-xs">
                <div>
                  <span className="text-[var(--text-secondary)] block mb-1">Bootstrap 95% VaR:</span>
                  <div className="text-lg font-bold text-[var(--accent-warning)]">
                    {(bootstrapData.bootstrap_var_95.median * 100).toFixed(2)}%
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">
                    95% CI: [{(bootstrapData.bootstrap_var_95.ci_lower_95 * 100).toFixed(2)}%, {(bootstrapData.bootstrap_var_95.ci_upper_95 * 100).toFixed(2)}%]
                  </span>
                </div>

                <div>
                  <span className="text-[var(--text-secondary)] block mb-1">Bootstrap 95% ES:</span>
                  <div className="text-lg font-bold text-[var(--accent-danger)]">
                    {(bootstrapData.bootstrap_es_95.median * 100).toFixed(2)}%
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">
                    95% CI: [{(bootstrapData.bootstrap_es_95.ci_lower_95 * 100).toFixed(2)}%, {(bootstrapData.bootstrap_es_95.ci_upper_95 * 100).toFixed(2)}%]
                  </span>
                </div>

                <div>
                  <span className="text-[var(--text-secondary)] block mb-1">Bootstrap Annual Volatility:</span>
                  <div className="text-lg font-bold text-[var(--text-primary)]">
                    {(bootstrapData.bootstrap_volatility.mean * 100).toFixed(2)}%
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">
                    95% CI: [{(bootstrapData.bootstrap_volatility.ci_lower_95 * 100).toFixed(2)}%, {(bootstrapData.bootstrap_volatility.ci_upper_95 * 100).toFixed(2)}%]
                  </span>
                </div>
              </div>
            ) : (
              <div className="p-6 text-center text-xs font-mono text-[var(--text-muted)] border border-dashed border-[var(--border-subtle)] rounded">
                Click &quot;Run Bootstrap&quot; to execute 250+ block resamples and compute empirical confidence bands.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Multi-Factor Reverse Stress Solution */}
      {activeTab === 'reverseStress' && (
        <div className="space-y-6">
          {reverseSolution ? (
            <div className="space-y-6">
              {/* Solution Overview Card */}
              <div className="card p-5 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border-subtle)] pb-4 mb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${
                        reverseSolution.is_feasible
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : 'bg-red-950 text-red-300 border border-red-800'
                      }`}>
                        {reverseSolution.is_feasible ? 'FEASIBLE REVERSE SOLUTION' : 'INFEASIBLE BOUNDARY'}
                      </span>
                      <span className="text-xs font-mono text-[var(--text-secondary)]">
                        Target Loss: {(reverseSolution.target_loss_pct * 100).toFixed(1)}% (₹{reverseSolution.target_loss_amount.toLocaleString()})
                      </span>
                    </div>
                    <div className="text-lg font-bold font-mono text-[var(--accent-danger)]">
                      Realized Stress Loss: {(reverseSolution.realized_loss_pct * 100).toFixed(2)}% (₹{reverseSolution.realized_loss_amount.toLocaleString()})
                    </div>
                  </div>

                  <div className="text-right font-mono">
                    <span className="text-xs text-[var(--text-secondary)] block">Statistical Plausibility Score</span>
                    <span className="text-2xl font-bold text-[var(--accent-warning)]">
                      {reverseSolution.plausibility_score} / 100
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)] block">
                      Joint severity: {reverseSolution.joint_sigma_distance}σ Mahalanobis distance
                    </span>
                  </div>
                </div>

                <p className="text-xs font-mono text-[var(--text-secondary)] leading-relaxed bg-[var(--bg-secondary)] p-3 rounded border border-[var(--border-subtle)]">
                  {reverseSolution.explanation}
                </p>
              </div>

              {/* Decomposed Factor Shocks */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] font-mono">
                  <span className="text-[10px] uppercase text-[var(--text-secondary)]">Systematic Market Shock</span>
                  <div className="text-xl font-bold text-[var(--accent-danger)] mt-1">
                    {(reverseSolution.market_shock * 100).toFixed(2)}%
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">NIFTY 50 Broad Index shift</span>
                </div>

                <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] font-mono">
                  <span className="text-[10px] uppercase text-[var(--text-secondary)]">
                    Dominant Sector Shock ({reverseSolution.dominant_sector})
                  </span>
                  <div className="text-xl font-bold text-[var(--accent-warning)] mt-1">
                    {(reverseSolution.sector_shock * 100).toFixed(2)}%
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">Concentrated sector drag</span>
                </div>

                <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] font-mono">
                  <span className="text-[10px] uppercase text-[var(--text-secondary)]">
                    Idiosyncratic Shock ({reverseSolution.idiosyncratic_asset})
                  </span>
                  <div className="text-xl font-bold text-[var(--accent-info)] mt-1">
                    {(reverseSolution.asset_shock * 100).toFixed(2)}%
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">Single holding liquidity shock</span>
                </div>

                <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] font-mono">
                  <span className="text-[10px] uppercase text-[var(--text-secondary)]">Stressed Vol Multiplier</span>
                  <div className="text-xl font-bold text-[var(--text-primary)] mt-1">
                    {reverseSolution.volatility_multiplier.toFixed(2)}x
                  </div>
                  <span className="text-[10px] text-[var(--text-muted)]">Dynamic volatility expansion</span>
                </div>
              </div>

              {/* Holding Loss Attribution Table */}
              <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)] block mb-3">
                  Holding-Level Reverse Stress Impact Attribution
                </span>

                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono">
                    <thead>
                      <tr className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)] text-left">
                        <th className="py-2 px-3">Asset ID</th>
                        <th className="py-2 px-3">Sector</th>
                        <th className="py-2 px-3">Portfolio Weight</th>
                        <th className="py-2 px-3">Market Value</th>
                        <th className="py-2 px-3">Combined Shock</th>
                        <th className="py-2 px-3">Holding Loss (INR)</th>
                        <th className="py-2 px-3">Loss Contribution</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border-subtle)]">
                      {reverseSolution.holding_attributions.map((h: any, idx: number) => (
                        <tr key={idx} className="hover:bg-[var(--bg-secondary)] transition-colors">
                          <td className="py-2.5 px-3 font-bold text-[var(--text-primary)]">{h.asset_id}</td>
                          <td className="py-2.5 px-3 text-[var(--text-secondary)]">{h.sector}</td>
                          <td className="py-2.5 px-3">{(h.weight * 100).toFixed(1)}%</td>
                          <td className="py-2.5 px-3">₹{h.market_value.toLocaleString()}</td>
                          <td className="py-2.5 px-3 font-bold text-[var(--accent-danger)]">{h.combined_shock_pct.toFixed(2)}%</td>
                          <td className="py-2.5 px-3 text-[var(--accent-danger)]">₹{h.holding_loss_inr.toLocaleString()}</td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <span className="w-12 text-right">{h.loss_contribution_pct.toFixed(1)}%</span>
                              <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-[var(--accent-danger)] rounded-full"
                                  style={{ width: `${Math.min(100, h.loss_contribution_pct)}%` }}
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center font-mono text-xs text-[var(--text-muted)] border border-dashed border-[var(--border-subtle)] rounded">
              No solution loaded. Click &quot;Solve Reverse Stress&quot; to execute search.
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Sensitivity Surface & Frontier */}
      {activeTab === 'surface' && (
        <div className="space-y-6">
          <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-xs font-mono font-bold uppercase tracking-wider text-[var(--text-primary)] block">
                  2D Reverse Stress Sensitivity Surface
                </span>
                <span className="text-xs text-[var(--text-secondary)]">
                  Simultaneous variation of Market Shock (X-axis) vs {surfaceData?.dominant_sector || 'Sector'} Shock (Y-axis) towards the {(targetLossPct * 100).toFixed(0)}% loss frontier
                </span>
              </div>
            </div>

            {surfaceData ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-center border-collapse">
                  <thead>
                    <tr>
                      <th className="p-2 border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                        Sector \ Market
                      </th>
                      {surfaceData.market_shocks.map((ms: number, idx: number) => (
                        <th key={idx} className="p-2 border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                          {(ms * 100).toFixed(1)}%
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {surfaceData.sector_shocks.map((ss: number, sIdx: number) => (
                      <tr key={sIdx}>
                        <td className="p-2 border border-[var(--border-subtle)] text-[var(--text-secondary)] font-bold text-left">
                          {(ss * 100).toFixed(1)}%
                        </td>
                        {surfaceData.market_shocks.map((ms: number, mIdx: number) => {
                          const cell = surfaceData.cells.find(
                            (c: any) => Math.abs(c.market_shock - ms) < 1e-4 && Math.abs(c.sector_shock - ss) < 1e-4
                          );
                          const lossPct = cell ? (cell.loss_pct * 100) : 0;
                          const breaches = cell?.breaches_target;
                          return (
                            <td
                              key={mIdx}
                              className={`p-2 border border-[var(--border-subtle)] font-bold transition-all ${
                                breaches
                                  ? 'bg-red-950/80 text-red-200 border-red-700'
                                  : lossPct >= targetLossPct * 80
                                  ? 'bg-amber-950/50 text-amber-200'
                                  : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]'
                              }`}
                            >
                              {lossPct.toFixed(1)}%
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-6 text-center text-xs font-mono text-[var(--text-muted)]">
                Loading sensitivity surface...
              </div>
            )}

            <div className="flex items-center justify-center gap-6 mt-4 text-xs font-mono text-[var(--text-secondary)]">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-red-900 border border-red-600 rounded-sm" />
                <span>Breaches {(targetLossPct * 100).toFixed(0)}% Loss Frontier</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-amber-900 border border-amber-600 rounded-sm" />
                <span>Near Threshold (&gt;80% of target)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-slate-800 border border-slate-700 rounded-sm" />
                <span>Sub-Threshold</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
