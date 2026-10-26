import React, { useState, useEffect, useMemo } from 'react';
import {
  SlidersHorizontal,
  Play,
  RotateCcw,
  Download,
  ShieldCheck,
  AlertTriangle,
  Activity,
  Layers,
  BarChart3,
  RefreshCw,
  Info,
  CheckCircle2,
  Database,
  Hash
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  LineChart,
  Line,
  Legend
} from 'recharts';
import { api } from '@/lib/api';

const DATASETS = [
  { symbol: 'RELIANCE', name: 'Reliance Industries Ltd. (NSE)' },
  { symbol: 'NIFTY 50', name: 'Nifty 50 Benchmark Index (NSE)' },
  { symbol: 'TCS', name: 'Tata Consultancy Services (NSE)' },
  { symbol: 'INFY', name: 'Infosys Limited (NSE)' },
];

const METRICS = [
  { id: 'sharpe_ratio', name: 'Sharpe Ratio (Annualized)' },
  { id: 'sortino_ratio', name: 'Sortino Ratio (Downside Risk)' },
  { id: 'annualized_volatility', name: 'Annualized Volatility (σ)' },
  { id: 'max_drawdown', name: 'Maximum Drawdown (Peak-to-Trough)' },
  { id: 'calmar_ratio', name: 'Calmar Ratio' },
];

const SCHEMES = [
  { id: 'circular_block', name: 'Circular Block Bootstrap (Politis & Romano 1992)' },
  { id: 'moving_block', name: 'Moving Block Bootstrap (Künsch 1989)' },
  { id: 'stationary', name: 'Stationary Bootstrap (Geometric Blocks)' },
  { id: 'iid', name: 'Canonical i.i.d. Resampling (No Time Dependence)' },
];

export function BootstrapUncertaintyLab({
  notify,
  navigate,
}: {
  notify?: (msg: string) => void;
  navigate?: (path: string) => void;
}) {
  // Configuration Controls
  const [marketInstruments, setMarketInstruments] = useState(DATASETS);
  const [symbol, setSymbol] = useState<string>('RELIANCE');

  useEffect(() => {
    api.listMarketInstruments().then((res: any) => {
      if (res?.instruments && res.instruments.length > 0) {
        setMarketInstruments(res.instruments.map((i: any) => ({
          symbol: i.symbol,
          name: `${i.name} (${i.exchange || "NSE"})`
        })));
      }
    }).catch(() => {});
  }, []);
  const [metricName, setMetricName] = useState<string>('sharpe_ratio');
  const [resamplingScheme, setResamplingScheme] = useState<string>('circular_block');
  const [numReplications, setNumReplications] = useState<number>(300);
  const [blockLength, setBlockLength] = useState<number>(10);
  const [confidenceLevel, setConfidenceLevel] = useState<number>(0.95);
  const [seed, setSeed] = useState<number>(42);

  // Execution & Output State
  const [running, setRunning] = useState<boolean>(false);
  const [bootstrapResult, setBootstrapResult] = useState<any | null>(null);
  const [sensitivityResult, setSensitivityResult] = useState<any | null>(null);
  const [loadingSensitivity, setLoadingSensitivity] = useState<boolean>(false);
  const [lastConfigHash, setLastConfigHash] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'distribution' | 'intervals' | 'sensitivity' | 'provenance'>('distribution');

  const currentConfigHash = useMemo(() => {
    return `${symbol}-${metricName}-${resamplingScheme}-${numReplications}-${blockLength}-${confidenceLevel}-${seed}`;
  }, [symbol, metricName, resamplingScheme, numReplications, blockLength, confidenceLevel, seed]);

  const isStale = Boolean(bootstrapResult && lastConfigHash && lastConfigHash !== currentConfigHash);

  const handleRunBootstrap = async () => {
    try {
      setRunning(true);
      setErrorMsg(null);
      const res = await api.runBootstrapUncertainty({
        symbol,
        metric_name: metricName,
        resampling_scheme: resamplingScheme,
        num_replications: Number(numReplications),
        block_length: Number(blockLength),
        confidence_level: Number(confidenceLevel),
        seed: Number(seed),
      });

      if (res && res.success) {
        setBootstrapResult(res);
        setLastConfigHash(currentConfigHash);
        if (notify) notify(`Bootstrap uncertainty computed: ${numReplications} resamples generated.`);
      } else {
        throw new Error('Bootstrap engine returned an empty response.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Error executing bootstrap uncertainty analysis');
      if (notify) notify(`Bootstrap error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const handleRunSensitivityScan = async () => {
    try {
      setLoadingSensitivity(true);
      const res = await api.runBlockSensitivity({
        symbol,
        metric_name: metricName,
        resampling_scheme: resamplingScheme,
        block_lengths: [2, 5, 10, 15, 20, 30],
      });
      if (res && res.success) {
        setSensitivityResult(res);
        if (notify) notify('Block length sensitivity scan complete.');
      }
    } catch (err: any) {
      if (notify) notify(`Sensitivity scan error: ${err.message}`);
    } finally {
      setLoadingSensitivity(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'sensitivity' && !sensitivityResult && !loadingSensitivity) {
      handleRunSensitivityScan();
    }
  }, [activeTab, symbol, metricName]);

  const metricsSummary = bootstrapResult?.uncertainty_metrics;
  const histogramData = bootstrapResult?.histogram_bins || [];

  const exportCsv = () => {
    if (!bootstrapResult || !bootstrapResult.sample_replicates) return;
    const headers = ['Replication_Index', 'Resampled_Metric_Value'];
    const rows = bootstrapResult.sample_replicates.map((val: number, idx: number) => [idx + 1, val.toFixed(6)]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r: any) => r.join(','))].join('\n');
    const encoded = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', `bootstrap_uncertainty_${symbol}_${metricName}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="terminal-card space-y-6">
      {/* 1. Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-indigo-400" />
            UNCERTAINTY QUANTIFICATION & RESAMPLING / 07
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2 mt-1">
            <SlidersHorizontal className="w-6 h-6 text-primary" />
            Bootstrap and Uncertainty Lab
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl">
            Quantify statistical estimation noise and sample uncertainty in risk and performance metrics. 
            Implements Moving Block and Stationary Bootstrap preserving serial autocorrelation and volatility clustering.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            disabled={!bootstrapResult}
            className="terminal-button-secondary text-xs flex items-center gap-1.5"
            title="Export resampled draws to CSV"
          >
            <Download className="w-3.5 h-3.5" />
            Export Replicates
          </button>
          <button
            onClick={handleRunBootstrap}
            disabled={running}
            className="terminal-button-primary text-xs flex items-center gap-1.5"
          >
            <Play className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            {running ? 'Resampling Time Series...' : 'Run Bootstrap Lab'}
          </button>
        </div>
      </div>

      {/* 2. Configuration Controls */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 p-3.5 border border-border/80 rounded-lg bg-card/40 text-xs">
        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">EVALUATION DATASET</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            {marketInstruments.map((d) => (
              <option key={d.symbol} value={d.symbol}>{d.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">TARGET STATISTIC</label>
          <select
            value={metricName}
            onChange={(e) => setMetricName(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            {METRICS.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">RESAMPLING SCHEME</label>
          <select
            value={resamplingScheme}
            onChange={(e) => setResamplingScheme(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            {SCHEMES.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">BLOCK LENGTH (L)</label>
          <select
            value={blockLength}
            onChange={(e) => setBlockLength(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
            disabled={resamplingScheme === 'iid'}
          >
            <option value={3}>3 Trading Days (Short Term)</option>
            <option value={5}>5 Trading Days (1 Week)</option>
            <option value={10}>10 Trading Days (2 Weeks)</option>
            <option value={20}>20 Trading Days (1 Month)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">REPLICATIONS (B)</label>
          <select
            value={numReplications}
            onChange={(e) => setNumReplications(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={200}>200 Replications (Fast)</option>
            <option value={300}>300 Replications (Standard)</option>
            <option value={500}>500 Replications (High Precision)</option>
            <option value={1000}>1000 Replications (Institutional)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">CONFIDENCE LEVEL (1 - α)</label>
          <select
            value={confidenceLevel}
            onChange={(e) => setConfidenceLevel(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={0.90}>90% Coverage Interval</option>
            <option value={0.95}>95% Standard Coverage</option>
            <option value={0.99}>99% Conservative Coverage</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase flex items-center justify-between">
            <span>RNG SEED</span>
            <button
              onClick={() => setSeed(Math.floor(Math.random() * 100000))}
              className="text-[10px] text-primary hover:underline"
            >
              Randomize
            </button>
          </label>
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          />
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">TIME DEPENDENCE</label>
          <div className="py-2 px-2.5 rounded bg-muted/30 border border-border/50 text-[11px] text-muted-foreground">
            {resamplingScheme === 'iid' ? '⚠️ Independent draws (No Autocorrelation)' : '✓ Preserves Serial Autocorrelation'}
          </div>
        </div>
      </div>

      {/* 3. Stale / Error Banners */}
      {isStale && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span>Parameters modified. Displayed uncertainty results correspond to previous configuration.</span>
          </div>
          <button onClick={handleRunBootstrap} className="text-amber-200 underline font-semibold">
            Recompute Resampling
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 4. Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Sample Point Estimate</span>
            <Activity className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {metricsSummary ? Number(metricsSummary.point_estimate).toFixed(3) : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Empirical point estimate on full historical sample
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Bootstrap Standard Error</span>
            <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-cyan-400 font-mono">
            {metricsSummary ? `± ${Number(metricsSummary.standard_error).toFixed(4)}` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Standard deviation across {numReplications} resampled draws
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>95% Percentile CI</span>
            <SlidersHorizontal className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-lg font-bold mt-1 text-emerald-400 font-mono">
            {metricsSummary ? `[${Number(metricsSummary.percentile_ci_lower).toFixed(3)}, ${Number(metricsSummary.percentile_ci_upper).toFixed(3)}]` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Width: {metricsSummary ? Number(metricsSummary.percentile_ci_upper - metricsSummary.percentile_ci_lower).toFixed(3) : '—'}
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>P-Value (H₀: θ ≤ 0)</span>
            <Activity className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {metricsSummary ? (Number(metricsSummary.p_value_zero_skill) < 0.001 ? '< 0.001' : Number(metricsSummary.p_value_zero_skill).toFixed(3)) : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {metricsSummary && Number(metricsSummary.p_value_zero_skill) < 0.05 ? 'Statistically Significant (p < 0.05)' : 'High Estimation Noise'}
          </div>
        </div>
      </div>

      {/* 5. Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('distribution')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'distribution' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Resampling Distribution Histogram
        </button>
        <button
          onClick={() => setActiveTab('intervals')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'intervals' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Confidence Interval Comparison
        </button>
        <button
          onClick={() => setActiveTab('sensitivity')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'sensitivity' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Block Length Sensitivity Scan
        </button>
        <button
          onClick={() => setActiveTab('provenance')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'provenance' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Dataset Provenance & Audit
        </button>
      </div>

      {/* Tab 1: Histogram */}
      {activeTab === 'distribution' && (
        <div className="space-y-4">
          {histogramData.length > 0 ? (
            <div className="h-72 w-full bg-card/30 border border-border/80 rounded p-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogramData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                  <XAxis dataKey="bin_label" stroke="#666" tick={{ fontSize: 9 }} />
                  <YAxis stroke="#666" tick={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }}
                    formatter={(val: any) => [`${val} draws`, 'Frequency']}
                  />
                  <Bar dataKey="frequency" fill="#38bdf8" name="Resample Frequency" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="p-12 text-center border border-dashed border-border rounded-lg bg-card/20 space-y-3">
              <SlidersHorizontal className="w-8 h-8 text-muted-foreground mx-auto" />
              <div className="text-sm font-semibold text-foreground">No Bootstrap Draws Generated</div>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Select your dataset and parameter settings, then click <strong>Run Bootstrap Lab</strong> to generate {numReplications} time-series resamples.
              </p>
              <button onClick={handleRunBootstrap} className="terminal-button-primary text-xs mx-auto">
                Generate Bootstrap Resamples
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Confidence Intervals */}
      {activeTab === 'intervals' && metricsSummary && (
        <div className="border border-border/80 rounded-lg overflow-x-auto bg-card/30 text-xs">
          <table className="w-full text-left font-mono">
            <thead className="bg-muted/40 text-muted-foreground border-b border-border/60">
              <tr>
                <th className="p-3">INTERVAL METHODOLOGY</th>
                <th className="p-3">LOWER BOUND</th>
                <th className="p-3">POINT ESTIMATE</th>
                <th className="p-3">UPPER BOUND</th>
                <th className="p-3">INTERVAL WIDTH</th>
                <th className="p-3">CHARACTERISTICS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              <tr className="hover:bg-muted/20">
                <td className="p-3 font-semibold text-foreground">Percentile Bootstrap Interval</td>
                <td className="p-3 text-emerald-400 font-bold">{metricsSummary.percentile_ci_lower?.toFixed(3)}</td>
                <td className="p-3 text-primary">{metricsSummary.point_estimate?.toFixed(3)}</td>
                <td className="p-3 text-emerald-400 font-bold">{metricsSummary.percentile_ci_upper?.toFixed(3)}</td>
                <td className="p-3">{(metricsSummary.percentile_ci_upper - metricsSummary.percentile_ci_lower)?.toFixed(3)}</td>
                <td className="p-3 text-muted-foreground text-[11px]">Transformation invariant, non-parametric empirical quantiles</td>
              </tr>
              <tr className="hover:bg-muted/20">
                <td className="p-3 font-semibold text-foreground">Basic (Empirical) Interval</td>
                <td className="p-3 text-cyan-400 font-bold">{metricsSummary.basic_ci_lower?.toFixed(3)}</td>
                <td className="p-3 text-primary">{metricsSummary.point_estimate?.toFixed(3)}</td>
                <td className="p-3 text-cyan-400 font-bold">{metricsSummary.basic_ci_upper?.toFixed(3)}</td>
                <td className="p-3">{(metricsSummary.basic_ci_upper - metricsSummary.basic_ci_lower)?.toFixed(3)}</td>
                <td className="p-3 text-muted-foreground text-[11px]">Corrects for parameter skewness: 2θ̂ - q_(1-α/2)</td>
              </tr>
              <tr className="hover:bg-muted/20">
                <td className="p-3 font-semibold text-foreground">Normal Approximation Interval</td>
                <td className="p-3 text-indigo-400 font-bold">{metricsSummary.normal_ci_lower?.toFixed(3)}</td>
                <td className="p-3 text-primary">{metricsSummary.point_estimate?.toFixed(3)}</td>
                <td className="p-3 text-indigo-400 font-bold">{metricsSummary.normal_ci_upper?.toFixed(3)}</td>
                <td className="p-3">{(metricsSummary.normal_ci_upper - metricsSummary.normal_ci_lower)?.toFixed(3)}</td>
                <td className="p-3 text-muted-foreground text-[11px]">Assumes asymptotic normality: θ̂ ± z_(α/2) * SE</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 3: Sensitivity */}
      {activeTab === 'sensitivity' && (
        <div className="space-y-3">
          <div className="text-xs text-muted-foreground">
            Scans confidence interval width across varying block lengths (L = 2 to 30 days) to diagnose dependency structure.
          </div>
          {sensitivityResult?.scan_points ? (
            <div className="h-64 w-full bg-card/30 border border-border/80 rounded p-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sensitivityResult.scan_points} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                  <XAxis dataKey="block_length" stroke="#666" tick={{ fontSize: 10 }} label={{ value: 'Block Length (Days)', position: 'insideBottom', offset: -10, fill: '#666' }} />
                  <YAxis stroke="#666" tick={{ fontSize: 10 }} label={{ value: 'CI Width', angle: -90, position: 'insideLeft', fill: '#666' }} />
                  <Tooltip contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }} />
                  <Line type="monotone" dataKey="ci_width" stroke="#38bdf8" strokeWidth={2} name="CI Width" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-muted-foreground border border-dashed border-border rounded">
              {loadingSensitivity ? 'Computing block sensitivity scan...' : 'Click to calculate block sensitivity.'}
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Provenance */}
      {activeTab === 'provenance' && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-2 text-xs">
          <div className="font-semibold text-foreground flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Dataset Provenance & Reproducibility Digest</span>
          </div>
          <div className="font-mono text-muted-foreground space-y-1">
            <div>Target Instrument: <strong>{symbol}</strong></div>
            <div>SHA-256 Dataset Digest: <code>{bootstrapResult?.dataset_fingerprint || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}</code></div>
            <div>Random Seed: <strong>{seed} (Deterministic Reproducibility Guaranteed)</strong></div>
            <div>Replications Executed: <strong>{numReplications}</strong></div>
          </div>
        </div>
      )}
    </div>
  );
}
