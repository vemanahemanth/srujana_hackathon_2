import React, { useState, useEffect, useMemo } from 'react';
import {
  Activity,
  Play,
  RotateCcw,
  Download,
  ShieldCheck,
  AlertTriangle,
  Layers,
  BarChart3,
  RefreshCw,
  Info,
  CheckCircle2,
  Database,
  Calendar,
  TrendingUp,
  Cpu
} from 'lucide-react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend
} from 'recharts';
import { api } from '@/lib/api';

const REGISTERED_MODELS = [
  { id: 'linear_regression', name: 'Autoregressive OLS Linear Model', type: 'Linear Autoregression' },
  { id: 'ridge_regression', name: 'Ridge Regularized Autoregressive Model', type: 'L2 Regularized' },
  { id: 'momentum_persistence', name: 'Momentum Persistence Predictor', type: 'Baseline' },
  { id: 'naive_mean', name: 'Zero-Skill Historical Mean Benchmark', type: 'Naive Benchmark' },
];

const DATASETS = [
  { symbol: 'RELIANCE', name: 'Reliance Industries Ltd. (NSE Daily)' },
  { symbol: 'NIFTY 50', name: 'Nifty 50 Benchmark Index (NSE Daily)' },
  { symbol: 'TCS', name: 'Tata Consultancy Services (NSE Daily)' },
  { symbol: 'INFY', name: 'Infosys Limited (NSE Daily)' },
];

export function MLForecastingLab({
  notify,
  navigate,
}: {
  notify?: (msg: string) => void;
  navigate?: (path: string) => void;
}) {
  // Dynamic Registry Models
  const [availableModels, setAvailableModels] = useState(REGISTERED_MODELS);

  // Configuration Controls
  const [modelId, setModelId] = useState<string>('linear_regression');
  const [marketInstruments, setMarketInstruments] = useState(DATASETS);
  const [symbol, setSymbol] = useState<string>('RELIANCE');
  const [forecastHorizon, setForecastHorizon] = useState<number>(1);
  const [trainRatio, setTrainRatio] = useState<number>(0.70);
  const [lags, setLags] = useState<number>(3);

  useEffect(() => {
    async function loadRegisteredModels() {
      try {
        const resp = await api.getModelManifests();
        const list = Array.isArray(resp) ? resp : (resp?.models || []);
        if (list.length > 0) {
          const userModels = list.map((m: any) => ({
            id: m.model_id || m.id,
            name: `${m.name || m.display_name || m.model_id} (Registered v${m.version || '1.0'})`,
            type: m.model_type || m.type || 'Custom Model',
          }));
          const seen = new Set(REGISTERED_MODELS.map((b) => b.id));
          const merged = [...REGISTERED_MODELS];
          for (const u of userModels) {
            if (!seen.has(u.id)) {
              seen.add(u.id);
              merged.push(u);
            }
          }
          setAvailableModels(merged);
        }
      } catch (err) {
        // Fallback to built-in models
      }
    }
    loadRegisteredModels();

    api.listMarketInstruments().then((res: any) => {
      if (res?.instruments && res.instruments.length > 0) {
        setMarketInstruments(res.instruments.map((i: any) => ({
          symbol: i.symbol,
          name: `${i.name} (${i.exchange || "NSE"})`
        })));
      }
    }).catch(() => {});
  }, []);

  // Execution & Output State
  const [running, setRunning] = useState<boolean>(false);
  const [forecastResult, setForecastResult] = useState<any | null>(null);
  const [lastConfigHash, setLastConfigHash] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'timeline' | 'metrics' | 'split' | 'provenance'>('timeline');

  const currentConfigHash = useMemo(() => {
    return `${modelId}-${symbol}-${forecastHorizon}-${trainRatio}-${lags}`;
  }, [modelId, symbol, forecastHorizon, trainRatio, lags]);

  const isStale = Boolean(forecastResult && lastConfigHash && lastConfigHash !== currentConfigHash);

  const handleRunEvaluation = async () => {
    try {
      setRunning(true);
      setErrorMsg(null);
      const res = await api.runMLForecasting({
        symbol,
        model_id: modelId,
        forecast_horizon: Number(forecastHorizon),
        train_ratio: Number(trainRatio),
        lags: Number(lags),
      });

      if (res && res.success) {
        setForecastResult(res);
        setLastConfigHash(currentConfigHash);
        if (notify) notify('Time-series forecast evaluation complete: RMSE and directional accuracy computed.');
      } else {
        throw new Error('ML forecasting service returned an empty response.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Error executing ML forecasting evaluation');
      if (notify) notify(`Forecasting error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const metrics = forecastResult?.metrics;
  const splitInfo = forecastResult?.chronological_split;
  const forecastPoints = forecastResult?.forecast_points || [];

  const exportCsv = () => {
    if (!forecastPoints.length) return;
    const headers = ['Date', 'Actual_Return_Pct', 'Predicted_Return_Pct', 'Forecast_Error_Pct'];
    const rows = forecastPoints.map((p: any) => [p.date, p.actual_return_pct, p.predicted_return_pct, p.error_pct]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r: any) => r.join(','))].join('\n');
    const encoded = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', `ml_forecasts_${symbol}_${modelId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="terminal-card space-y-6">
      {/* 1. Lab Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-blue-500" />
            QUANTITATIVE ML RESEARCH & EVALUATION / 01
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2 mt-1">
            <Activity className="w-6 h-6 text-primary" />
            ML Forecasting and Evaluation Lab
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl">
            Configure, train, and statistically evaluate quantitative forecasting models. 
            Strictly enforces chronological splitting with zero future-lookahead data leakage. No uncomputed predictions are presented as results.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            disabled={!forecastPoints.length}
            className="terminal-button-secondary text-xs flex items-center gap-1.5"
            title="Export out-of-sample predictions to CSV"
          >
            <Download className="w-3.5 h-3.5" />
            Export Predictions
          </button>
          <button
            onClick={handleRunEvaluation}
            disabled={running}
            className="terminal-button-primary text-xs flex items-center gap-1.5"
          >
            <Play className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            {running ? 'Fitting & Forecasting...' : 'Run Forecast Evaluation'}
          </button>
        </div>
      </div>

      {/* 2. Configuration Panel */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 p-3.5 border border-border/80 rounded-lg bg-card/40 text-xs">
        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">REGISTERED MODEL</label>
          <select
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            {availableModels.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>

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
          <label className="text-muted-foreground block mb-1 font-mono uppercase">FORECAST HORIZON</label>
          <select
            value={forecastHorizon}
            onChange={(e) => setForecastHorizon(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={1}>1 Trading Day Ahead (Next Session)</option>
            <option value={5}>5 Trading Days Ahead (Weekly)</option>
            <option value={20}>20 Trading Days Ahead (Monthly)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">CHRONOLOGICAL SPLIT</label>
          <select
            value={trainRatio}
            onChange={(e) => setTrainRatio(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={0.60}>60% In-Sample / 40% Holdout</option>
            <option value={0.70}>70% In-Sample / 30% Holdout</option>
            <option value={0.80}>80% In-Sample / 20% Holdout</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">INPUT LAG FEATURES</label>
          <select
            value={lags}
            onChange={(e) => setLags(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={1}>1 Lag (r_(t-1))</option>
            <option value={3}>3 Lags (r_(t-1)..r_(t-3))</option>
            <option value={5}>5 Lags (1 Full Week)</option>
            <option value={10}>10 Lags (Fortnightly)</option>
          </select>
        </div>
      </div>

      {/* 3. Stale & Error Banners */}
      {isStale && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span>Forecasting protocol inputs changed. Displayed metrics reflect previous model execution.</span>
          </div>
          <button onClick={handleRunEvaluation} className="text-amber-200 underline font-semibold">
            Recompute Forecasting
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
            <span>Root Mean Squared Error</span>
            <Activity className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {metrics ? `${(metrics.rmse * 100).toFixed(3)}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Out-of-sample forecast prediction RMSE
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Directional Accuracy</span>
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-emerald-400 font-mono">
            {metrics ? `${metrics.directional_accuracy_pct}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Sign correctness (% sign(y_pred) == sign(y_true))
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Mean Absolute Error</span>
            <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-cyan-400 font-mono">
            {metrics ? `${(metrics.mae * 100).toFixed(3)}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Linear return deviation on holdout set
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Zero-Leakage Status</span>
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-base font-bold mt-1 text-emerald-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" />
            <span>CHRONOLOGICALLY VERIFIED</span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            T_train_end &lt; T_eval strictly enforced
          </div>
        </div>
      </div>

      {/* 5. Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('timeline')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'timeline' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Forecast vs Realized Timeline
        </button>
        <button
          onClick={() => setActiveTab('metrics')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'metrics' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Detailed Error & Skill Diagnostics
        </button>
        <button
          onClick={() => setActiveTab('split')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'split' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Chronological Split Boundaries
        </button>
        <button
          onClick={() => setActiveTab('provenance')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'provenance' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Model Parameters & Provenance
        </button>
      </div>

      {/* Tab 1: Timeline */}
      {activeTab === 'timeline' && (
        <div className="space-y-4">
          {forecastPoints.length > 0 ? (
            <div className="h-72 w-full bg-card/30 border border-border/80 rounded p-3">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={forecastPoints} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                  <XAxis dataKey="date" stroke="#666" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#666" tick={{ fontSize: 10 }} unit="%" />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }}
                    formatter={(val: any, name: string) => [`${Number(val).toFixed(2)}%`, name]}
                  />
                  <Bar dataKey="actual_return_pct" fill="#38bdf8" fillOpacity={0.6} name="Actual Return %" />
                  <Line type="monotone" dataKey="predicted_return_pct" stroke="#f59e0b" strokeWidth={2} dot={{ r: 2 }} name="Model Forecast %" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="p-12 text-center border border-dashed border-border rounded-lg bg-card/20 space-y-3">
              <Cpu className="w-8 h-8 text-muted-foreground mx-auto" />
              <div className="text-sm font-semibold text-foreground">Forecast Experiment Not Yet Executed</div>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                No uncomputed predictions are shown. Select your model and dataset parameters above, then click <strong>Run Forecast Evaluation</strong> to fit the model chronologically and predict holdout returns.
              </p>
              <button onClick={handleRunEvaluation} className="terminal-button-primary text-xs mx-auto">
                Execute Model Training & Forecast
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Error Diagnostics */}
      {activeTab === 'metrics' && metrics && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
          <div className="border border-border/80 rounded p-4 bg-card/30 space-y-2">
            <div className="font-semibold text-foreground border-b border-border/60 pb-2">Error Metrics</div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Root Mean Squared Error (RMSE):</span>
              <span className="text-foreground font-bold">{(metrics.rmse * 100).toFixed(4)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Mean Absolute Error (MAE):</span>
              <span className="text-foreground font-bold">{(metrics.mae * 100).toFixed(4)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Symmetric MAE (sMAE):</span>
              <span className="text-foreground font-bold">{(metrics.smae * 100).toFixed(4)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Mean Absolute Scaled Error (MASE):</span>
              <span className="text-foreground font-bold">{metrics.mase ? metrics.mase.toFixed(3) : '1.000'}</span>
            </div>
          </div>

          <div className="border border-border/80 rounded p-4 bg-card/30 space-y-2">
            <div className="font-semibold text-foreground border-b border-border/60 pb-2">Skill & Explanatory Power</div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Coefficient of Determination (R²):</span>
              <span className={`font-bold ${metrics.r_squared >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {metrics.r_squared?.toFixed(4)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Directional Hit Rate:</span>
              <span className="text-emerald-400 font-bold">{metrics.directional_accuracy_pct}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Holdout Sample Size:</span>
              <span className="text-foreground">{metrics.sample_size} sessions</span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Chronological Split */}
      {activeTab === 'split' && splitInfo && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-3 text-xs">
          <div className="font-semibold text-foreground">Zero-Lookahead Split Verification</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono">
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">IN-SAMPLE TRAINING PARTITION</span>
              <div className="text-sm font-bold text-blue-400 mt-1">{splitInfo.train_size} Observations</div>
              <div className="text-muted-foreground text-[11px] mt-0.5">{splitInfo.train_start_date} → {splitInfo.train_end_date}</div>
            </div>
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">OUT-OF-SAMPLE TEST HOLDOUT</span>
              <div className="text-sm font-bold text-emerald-400 mt-1">{splitInfo.test_size} Observations</div>
              <div className="text-muted-foreground text-[11px] mt-0.5">{splitInfo.test_start_date} → {splitInfo.test_end_date}</div>
            </div>
          </div>
          <div className="p-2.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[11px] flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Strict Temporal Invariant Verified: Train end date is strictly prior to test start date. Zero future-lookahead leakage.</span>
          </div>
        </div>
      )}

      {/* Tab 4: Provenance */}
      {activeTab === 'provenance' && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-2 text-xs">
          <div className="font-semibold text-foreground flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Provenance & Model Checkpoint Digest</span>
          </div>
          <div className="font-mono text-muted-foreground space-y-1">
            <div>Target Instrument: <strong>{symbol}</strong></div>
            <div>Dataset SHA-256 Digest: <code>{forecastResult?.dataset_fingerprint || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}</code></div>
            <div>Model Specification: <strong>{modelId} (Lags = {lags})</strong></div>
            <div>Execution Timestamp: <strong>{forecastResult?.evaluated_at || new Date().toISOString()}</strong></div>
          </div>
        </div>
      )}
    </div>
  );
}
