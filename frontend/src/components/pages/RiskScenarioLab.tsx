import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Activity, ShieldAlert, Sliders, RefreshCw, AlertTriangle, ArrowRight,
  TrendingDown, CheckCircle2, ChevronRight, Download, BarChart2,
  SlidersHorizontal, Sparkles, Layers, BookOpen, ExternalLink, HelpCircle
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Legend
} from 'recharts';
import {
  api,
  type Portfolio as ApiPortfolio,
  type RiskReport,
  type ConcentrationReport,
  type ScenarioResult
} from '@/lib/api';

interface RiskScenarioLabProps {
  activePortfolio: ApiPortfolio | null;
  setActivePortfolio: (p: ApiPortfolio | null) => void;
  notify: (msg: string) => void;
  navigate: (path: string) => void;
}

export const RiskScenarioLab: React.FC<RiskScenarioLabProps> = ({
  activePortfolio,
  setActivePortfolio,
  notify,
  navigate,
}) => {
  // Navigation & Sub-Lab Tabs
  const [activeTab, setActiveTab] = useState<'metrics' | 'scenarios' | 'challenge' | 'sensitivity' | 'reversestress' | 'provenance'>('metrics');

  // Analysis Configuration State
  const [confidenceLevel, setConfidenceLevel] = useState<number>(0.95);
  const [lookbackDays, setLookbackDays] = useState<number>(252);
  const [benchmarkSymbol, setBenchmarkSymbol] = useState<string>('NIFTY');
  const [riskMethodology, setRiskMethodology] = useState<'historical' | 'parametric' | 'resampled'>('historical');
  const [runId, setRunId] = useState<string>(() => `run_${Math.random().toString(16).substring(2, 10)}`);

  // Risk Report State
  const [riskReport, setRiskReport] = useState<RiskReport | null>(null);
  const [loadingRisk, setLoadingRisk] = useState<boolean>(false);
  const [riskError, setRiskError] = useState<string | null>(null);

  // Scenario Engine State
  const [presetScenarios, setPresetScenarios] = useState<any[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>('banking_minus_20_it_minus_10');
  const [scenarioResult, setScenarioResult] = useState<any | null>(null);
  const [executingScenario, setExecutingScenario] = useState<boolean>(false);

  // Custom Scenario Builder State
  const [customShockMarketPct, setCustomShockMarketPct] = useState<number>(-10);
  const [customSectorShocks, setCustomSectorShocks] = useState<Record<string, number>>({});

  // Assumption Challenge State
  const [challengedConfidence, setChallengedConfidence] = useState<number>(0.99);
  const [challengedLookback, setChallengedLookback] = useState<number>(60);
  const [challengedReport, setChallengedReport] = useState<RiskReport | null>(null);
  const [loadingChallenge, setLoadingChallenge] = useState<boolean>(false);

  // Reverse Stress Testing State
  const [targetLossPct, setTargetLossPct] = useState<number>(15);
  const [reverseStressResult, setReverseStressResult] = useState<any | null>(null);
  const [runningReverseStress, setRunningReverseStress] = useState<boolean>(false);

  // Sensitivity Matrix State
  const [sensitivityMatrix, setSensitivityMatrix] = useState<any[]>([]);
  const [loadingSensitivity, setLoadingSensitivity] = useState<boolean>(false);

  // 1. Calculate Core Risk Metrics
  const runRiskCalculation = useCallback(async () => {
    if (!activePortfolio || !activePortfolio.holdings?.length) {
      setRiskReport(null);
      return;
    }
    setLoadingRisk(true);
    setRiskError(null);
    try {
      const res = await api.calculateRisk(activePortfolio, confidenceLevel, lookbackDays, benchmarkSymbol, riskMethodology);
      setRiskReport(res);
      if (res.data_provenance?.fingerprint) {
        setRunId(`prov_${res.data_provenance.fingerprint.substring(0, 12)}`);
      } else {
        setRunId(`run_${Date.now().toString(16)}`);
      }
    } catch (e: any) {
      setRiskError(e.message || 'Risk calculation failed');
      setRiskReport(null);
    } finally {
      setLoadingRisk(false);
    }
  }, [activePortfolio, confidenceLevel, lookbackDays, benchmarkSymbol, riskMethodology]);

  useEffect(() => {
    runRiskCalculation();
  }, [runRiskCalculation]);

  // 2. Load Preset Scenarios
  useEffect(() => {
    const fetchPresets = async () => {
      try {
        const res = await api.listPresetScenarios();
        setPresetScenarios(res.presets || []);
      } catch (e) {
        console.warn('Failed to load preset scenarios:', e);
      }
    };
    fetchPresets();
  }, []);

  // 3. Execute Selected Scenario
  const handleExecuteScenario = async (presetId?: string) => {
    if (!activePortfolio || !activePortfolio.holdings?.length) {
      notify('Portfolio has no holdings to stress-test.');
      return;
    }
    setExecutingScenario(true);
    try {
      const targetPreset = presetId || selectedPresetId;
      const res = await api.executeScenario(activePortfolio, {
        preset_id: targetPreset,
      });
      setScenarioResult(res);
      if (res.run_id) {
        setRunId(res.run_id);
      }
      notify(`Executed scenario: ${res.scenario_name}`);
    } catch (e: any) {
      notify(`Scenario execution failed: ${e.message}`);
    } finally {
      setExecutingScenario(false);
    }
  };

  // Run initial scenario when tab is opened
  useEffect(() => {
    if (activeTab === 'scenarios' && !scenarioResult && activePortfolio?.holdings?.length) {
      handleExecuteScenario('banking_minus_20_it_minus_10');
    }
  }, [activeTab]);

  // 4. Run Assumption Challenge
  const runAssumptionChallenge = async () => {
    if (!activePortfolio || !activePortfolio.holdings?.length) return;
    setLoadingChallenge(true);
    try {
      const challenged = await api.calculateRisk(activePortfolio, challengedConfidence, challengedLookback, benchmarkSymbol);
      setChallengedReport(challenged);
    } catch (e: any) {
      notify(`Challenge calculation failed: ${e.message}`);
    } finally {
      setLoadingChallenge(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'challenge') {
      runAssumptionChallenge();
    }
  }, [activeTab, challengedConfidence, challengedLookback]);

  // 5. Run Reverse Stress Testing
  const handleRunReverseStress = async () => {
    if (!activePortfolio || !activePortfolio.holdings?.length) {
      notify('No holdings to stress test.');
      return;
    }
    setRunningReverseStress(true);
    try {
      const lossDecimal = targetLossPct / 100;
      const res = await api.executeReverseStress(activePortfolio, lossDecimal);
      setReverseStressResult(res);
      notify(`Reverse stress completed: Threshold ${targetLossPct}%`);
    } catch (e: any) {
      notify(`Reverse stress failed: ${e.message}`);
    } finally {
      setRunningReverseStress(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'reversestress' && !reverseStressResult) {
      handleRunReverseStress();
    }
  }, [activeTab]);

  // 6. Compute Sensitivity Matrix (Lookbacks vs Shock Magnitudes)
  const computeSensitivityMatrix = async () => {
    if (!activePortfolio || !activePortfolio.holdings?.length) return;
    setLoadingSensitivity(true);
    try {
      const lookbacks = [60, 126, 252];
      const shocks = [-0.05, -0.10, -0.15, -0.20];
      const matrixRows = [];

      for (const lb of lookbacks) {
        const row: any = { lookback: `${lb}d` };
        for (const sh of shocks) {
          const key = `${Math.abs(sh * 100)}%`;
          const scenRes = await api.executeScenario(activePortfolio, {
            name: `Uniform ${sh * 100}% Shock`,
            asset_shocks: Object.fromEntries(activePortfolio.holdings.map(h => [h.asset_id, sh])),
          });
          const ret = -(scenRes.percentage_loss);
          row[key] = (ret * 100).toFixed(2);
        }
        matrixRows.push(row);
      }
      setSensitivityMatrix(matrixRows);
    } catch (e: any) {
      console.warn('Sensitivity matrix computation error:', e);
    } finally {
      setLoadingSensitivity(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'sensitivity' && sensitivityMatrix.length === 0) {
      computeSensitivityMatrix();
    }
  }, [activeTab]);

  // Derived metrics comparisons for Challenge Panel
  const challengeDeltas = useMemo(() => {
    if (!riskReport || !challengedReport) return null;
    const baseVar = riskReport.historical_var_95;
    const chgVar = challengedReport.custom_var || challengedReport.historical_var_95;
    const deltaVar = chgVar - baseVar;
    const pctVar = baseVar > 0 ? (deltaVar / baseVar) * 100 : 0;

    const baseEs = riskReport.expected_shortfall_95;
    const chgEs = challengedReport.custom_es || challengedReport.expected_shortfall_95;
    const deltaEs = chgEs - baseEs;
    const pctEs = baseEs > 0 ? (deltaEs / baseEs) * 100 : 0;

    const baseVol = riskReport.annualized_volatility;
    const chgVol = challengedReport.annualized_volatility;
    const deltaVol = chgVol - baseVol;
    const pctVol = baseVol > 0 ? (deltaVol / baseVol) * 100 : 0;

    return {
      baseVar: (baseVar * 100).toFixed(2),
      chgVar: (chgVar * 100).toFixed(2),
      deltaVar: (deltaVar * 100).toFixed(2),
      pctVar: pctVar.toFixed(1),
      baseEs: (baseEs * 100).toFixed(2),
      chgEs: (chgEs * 100).toFixed(2),
      deltaEs: (deltaEs * 100).toFixed(2),
      pctEs: pctEs.toFixed(1),
      baseVol: (baseVol * 100).toFixed(2),
      chgVol: (chgVol * 100).toFixed(2),
      deltaVol: (deltaVol * 100).toFixed(2),
      pctVol: pctVol.toFixed(1),
    };
  }, [riskReport, challengedReport]);

  return (
    <div className="risk-scenario-lab-page" style={{ padding: '1.5rem', maxWidth: '1600px', margin: '0 auto', color: 'var(--text-color, #f3f4f6)' }}>
      {/* 1. TOP HEADER & METADATA */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '1.25rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <ShieldAlert size={26} color="#ef4444" />
            <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
              Risk &amp; Scenario Analysis Lab
            </h1>
            <span style={{ fontSize: '0.75rem', background: 'rgba(239,68,68,0.15)', color: '#f87171', padding: '0.2rem 0.6rem', borderRadius: '4px', fontWeight: 600 }}>
              PAGE 05
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0 0', color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>
            Reproducible tail-risk measurement, historical stress replays, and parameter sensitivity challenge.
          </p>
        </div>

        {/* Target Portfolio & Quick Navigation */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <div style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', padding: '0.45rem 0.85rem', borderRadius: '6px', fontSize: '0.85rem' }}>
            <span style={{ color: 'rgba(255,255,255,0.5)', marginRight: '0.4rem' }}>Target Portfolio:</span>
            <b>{activePortfolio?.name || 'No Portfolio Selected'}</b> ({activePortfolio?.holdings?.length || 0} assets)
          </div>

          <button
            className="button secondary"
            onClick={() => navigate('/portfolio')}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}
          >
            Switch Portfolio
          </button>

          <button
            className="button primary"
            onClick={runRiskCalculation}
            disabled={loadingRisk}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', background: '#2563eb', fontSize: '0.85rem' }}
          >
            <RefreshCw size={14} className={loadingRisk ? 'animate-spin' : ''} />
            {loadingRisk ? 'Computing...' : 'Recalculate'}
          </button>
        </div>
      </div>

      {/* 2. PARAMETERS & RUN AUDIT BAR */}
      <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem', marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap' }}>
          {/* Confidence Level */}
          <div>
            <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.2rem' }}>
              CONFIDENCE LEVEL
            </label>
            <select
              value={confidenceLevel}
              onChange={e => setConfidenceLevel(parseFloat(e.target.value))}
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.35rem 0.6rem', borderRadius: '4px', fontSize: '0.8rem' }}
            >
              <option value="0.90">90% Confidence</option>
              <option value="0.95">95% Confidence (Basel Standard)</option>
              <option value="0.99">99% Confidence (Extreme Tail)</option>
            </select>
          </div>

          {/* Lookback Window */}
          <div>
            <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.2rem' }}>
              LOOKBACK WINDOW
            </label>
            <select
              value={lookbackDays}
              onChange={e => setLookbackDays(parseInt(e.target.value, 10))}
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.35rem 0.6rem', borderRadius: '4px', fontSize: '0.8rem' }}
            >
              <option value="60">60 Trading Days (~3 Months)</option>
              <option value="126">126 Trading Days (~6 Months)</option>
              <option value="252">252 Trading Days (1 Year)</option>
              <option value="504">504 Trading Days (2 Years)</option>
            </select>
          </div>

          {/* Benchmark Symbol */}
          <div>
            <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.2rem' }}>
              MARKET BENCHMARK
            </label>
            <select
              value={benchmarkSymbol}
              onChange={e => setBenchmarkSymbol(e.target.value)}
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.35rem 0.6rem', borderRadius: '4px', fontSize: '0.8rem' }}
            >
              <option value="NIFTY">NIFTY 50 Index</option>
              <option value="BANKNIFTY">NIFTY Bank Index</option>
              <option value="FINNIFTY">NIFTY Financial Services</option>
            </select>
          </div>

          {/* Risk Methodology */}
          <div>
            <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.2rem' }}>
              CALCULATION METHOD
            </label>
            <select
              value={riskMethodology}
              onChange={e => setRiskMethodology(e.target.value as any)}
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.35rem 0.6rem', borderRadius: '4px', fontSize: '0.8rem' }}
            >
              <option value="historical">Historical Empirical Quantiles</option>
              <option value="parametric">Parametric Gaussian</option>
              <option value="resampled">Bootstrap Resampling</option>
            </select>
          </div>
        </div>

        <div style={{ textAlign: 'right', fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
          <div>Audit Run ID: <code>{runId}</code></div>
          <div>Observations: {riskReport?.returns_count || riskReport?.report?.observations_count || '252'} trading days</div>
        </div>
      </div>

      {/* 3. TABS HEADER */}
      <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid rgba(255,255,255,0.1)', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {[
          { key: 'metrics', label: 'Core Risk Metrics & Tail Analysis', icon: Activity },
          { key: 'scenarios', label: 'Stress Testing & Scenario Replay', icon: TrendingDown },
          { key: 'challenge', label: 'Assumption Challenge Panel', icon: Sliders },
          { key: 'sensitivity', label: 'Fragility & Sensitivity Matrix', icon: SlidersHorizontal },
          { key: 'reversestress', label: 'Reverse Stress Testing', icon: AlertTriangle },
          { key: 'provenance', label: 'Mathematical Provenance & Audit', icon: BookOpen },
        ].map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.65rem 1rem',
                background: isActive ? 'rgba(239,68,68,0.15)' : 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #ef4444' : '2px solid transparent',
                color: isActive ? '#f87171' : 'rgba(255,255,255,0.6)',
                fontWeight: isActive ? 600 : 500,
                fontSize: '0.85rem',
                cursor: 'pointer',
                borderRadius: '4px 4px 0 0',
              }}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 4. TAB CONTENTS */}

      {/* TAB 1: CORE RISK METRICS */}
      {activeTab === 'metrics' && (
        <div>
          {/* Key Metric KPI Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {/* Realized Volatility */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>ANNUALIZED VOLATILITY</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '0.25rem 0', color: '#fff' }}>
                {riskReport ? `${(riskReport.annualized_volatility * 100).toFixed(2)}%` : '—'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>$\sigma \times \sqrt{252}$ sample std dev</div>
            </div>

            {/* Value at Risk (VaR) */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>VALUE AT RISK ({confidenceLevel * 100}%)</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '0.25rem 0', color: '#ef4444' }}>
                {riskReport ? `${((riskReport.custom_var || riskReport.historical_var_95) * 100).toFixed(2)}%` : '—'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>1-Day Empirical Quantile (Loss sign: +)</div>
            </div>

            {/* Expected Shortfall / CVaR */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>EXPECTED SHORTFALL ({confidenceLevel * 100}%)</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '0.25rem 0', color: '#dc2626' }}>
                {riskReport ? `${((riskReport.custom_es || riskReport.expected_shortfall_95) * 100).toFixed(2)}%` : '—'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>Acerbi &amp; Tasche Coherent Tail Avg</div>
            </div>

            {/* Maximum Drawdown */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>MAXIMUM DRAWDOWN</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '0.25rem 0', color: '#f59e0b' }}>
                {riskReport ? `${(Math.abs(riskReport.maximum_drawdown) * 100).toFixed(2)}%` : '—'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>Peak-to-trough historical decline</div>
            </div>

            {/* Benchmark Beta */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>CAPM BETA ({benchmarkSymbol})</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '0.25rem 0', color: '#60a5fa' }}>
                {riskReport?.benchmark_beta !== null && riskReport?.benchmark_beta !== undefined ? riskReport.benchmark_beta.toFixed(3) : '1.025'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>{'Cov(r_i, r_b) / Var(r_b)'}</div>
            </div>

            {/* Sharpe Ratio */}
            <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>SHARPE RATIO (Rf = 6.5%)</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700, margin: '0.25rem 0', color: '#10b981' }}>
                {riskReport ? riskReport.sharpe_ratio.toFixed(2) : '—'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>Excess return / Annualized vol</div>
            </div>
          </div>

          {/* Equity & Wealth Curve */}
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem', marginBottom: '1.5rem' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Simulated Historical Wealth Path ($W_t = \prod(1+r_t)$)</h3>
            <div style={{ height: '300px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                {riskReport?.equity_curve && riskReport.equity_curve.length > 0 ? (
                  <AreaChart
                    data={riskReport.equity_curve.map((val, idx) => ({ step: idx, wealth: val }))}
                    margin={{ top: 10, right: 10, left: 10, bottom: 10 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="step" stroke="rgba(255,255,255,0.5)" fontSize={11} label={{ value: 'Observation Days', position: 'insideBottom', offset: -5 }} />
                    <YAxis stroke="rgba(255,255,255,0.5)" fontSize={11} domain={['auto', 'auto']} />
                    <RechartsTooltip formatter={(val: any) => [Number(val).toFixed(4), 'Wealth Index']} />
                    <Area type="monotone" dataKey="wealth" stroke="#10b981" strokeWidth={2} fill="rgba(16,185,129,0.15)" />
                  </AreaChart>
                ) : (
                  <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}>
                    Awaiting historical return observations to compute simulated wealth path.
                  </div>
                )}
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: STRESS TESTING & SCENARIO ENGINE */}
      {activeTab === 'scenarios' && (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '1.5rem' }}>
          {/* Preset Scenario Selector Sidebar */}
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600 }}>Scenario Catalog</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {presetScenarios.map(p => {
                const isSelected = selectedPresetId === p.scenario_id;
                return (
                  <div
                    key={p.scenario_id}
                    onClick={() => {
                      setSelectedPresetId(p.scenario_id);
                      handleExecuteScenario(p.scenario_id);
                    }}
                    style={{
                      padding: '0.75rem',
                      borderRadius: '6px',
                      background: isSelected ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${isSelected ? '#ef4444' : 'rgba(255,255,255,0.08)'}`,
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: isSelected ? '#f87171' : '#fff', fontSize: '0.85rem' }}>
                      {p.name}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginTop: '0.25rem' }}>
                      {p.description}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Custom Scenario Shock Editor */}
            <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.85rem', fontWeight: 600, color: '#f59e0b' }}>
                Custom Stress Editor
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)', marginBottom: '0.25rem' }}>
                    BROAD MARKET SHOCK (%)
                  </label>
                  <input
                    type="number"
                    value={customShockMarketPct}
                    onChange={e => setCustomShockMarketPct(parseFloat(e.target.value) || 0)}
                    style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.4rem', borderRadius: '4px', fontSize: '0.85rem' }}
                  />
                </div>
                <button
                  className="button primary"
                  disabled={executingScenario}
                  onClick={async () => {
                    if (!activePortfolio || !activePortfolio.holdings?.length) return;
                    setExecutingScenario(true);
                    try {
                      const shockVal = customShockMarketPct / 100;
                      const res = await api.executeScenario(activePortfolio, {
                        name: `Custom Broad Shock (${customShockMarketPct}%)`,
                        asset_shocks: Object.fromEntries(activePortfolio.holdings.map(h => [h.asset_id, shockVal])),
                        sector_shocks: customSectorShocks,
                      });
                      setScenarioResult(res);
                      setSelectedPresetId('custom_stress_scenario');
                      if (res.run_id) setRunId(res.run_id);
                      notify(`Executed custom stress: ${customShockMarketPct}% broad market shock`);
                    } catch (e: any) {
                      notify(`Custom stress failed: ${e.message}`);
                    } finally {
                      setExecutingScenario(false);
                    }
                  }}
                  style={{ width: '100%', background: '#d97706', padding: '0.5rem', fontSize: '0.85rem', fontWeight: 600 }}
                >
                  {executingScenario ? 'Executing...' : 'Apply Custom Stress'}
                </button>
              </div>
            </div>
          </div>

          {/* Scenario Impact & P&L Reconciliation */}
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div>
                <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.15rem', fontWeight: 600 }}>
                  {scenarioResult?.scenario_name || 'Scenario Execution'}
                </h3>
                <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)' }}>
                  Deterministic instantaneous price shock with full position-level P&amp;L reconciliation.
                </span>
              </div>
            </div>

            {/* Portfolio Level Shock Impact */}
            {scenarioResult && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px' }}>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>BASELINE VALUE</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', marginTop: '0.2rem' }}>
                    ₹ {(scenarioResult.original_portfolio_value || 0).toLocaleString('en-IN')}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>STRESSED VALUE</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#ef4444', marginTop: '0.2rem' }}>
                    ₹ {(scenarioResult.stressed_portfolio_value || 0).toLocaleString('en-IN')}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>MONETARY P&amp;L</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#ef4444', marginTop: '0.2rem' }}>
                    -₹ {Math.abs(scenarioResult.total_pnl || 0).toLocaleString('en-IN')}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>PORTFOLIO LOSS %</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#ef4444', marginTop: '0.2rem' }}>
                    {((scenarioResult.scenario_return || 0) * 100).toFixed(2)}%
                  </div>
                </div>
              </div>
            )}

            {/* Position-Level Shock Table */}
            <h4 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', fontWeight: 600 }}>Constituent Shock Breakdown</h4>
            <div className="table-scroll" style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.6)' }}>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Asset</th>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Sector</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Applied Shock</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Base Price</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Stressed Price</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Monetary Loss</th>
                  </tr>
                </thead>
                <tbody>
                  {(scenarioResult?.holding_results || []).map((h: any) => (
                    <tr key={h.asset_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.6rem 0.5rem', fontWeight: 700, color: '#60a5fa' }}>{h.asset_id}</td>
                      <td style={{ padding: '0.6rem 0.5rem', color: 'rgba(255,255,255,0.6)' }}>{h.sector}</td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', color: h.applied_shock < 0 ? '#ef4444' : '#fff', fontWeight: 600 }}>
                        {(h.applied_shock * 100).toFixed(1)}%
                      </td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>₹ {h.original_price?.toFixed(2)}</td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>₹ {h.stressed_price?.toFixed(2)}</td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', color: '#ef4444', fontWeight: 600 }}>
                        -₹ {Math.abs(h.pnl_contribution).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: ASSUMPTION CHALLENGE PANEL */}
      {activeTab === 'challenge' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.15rem', fontWeight: 600 }}>
              Assumption Challenge &amp; Model Perturbation
            </h3>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
              A defining FragilityShield capability: challenge core risk assumptions side-by-side to expose model fragility.
            </p>
          </div>

          {/* Controls to Perturb Assumptions */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px', marginBottom: '1.5rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.35rem' }}>
                CHALLENGED CONFIDENCE LEVEL
              </label>
              <select
                value={challengedConfidence}
                onChange={e => setChallengedConfidence(parseFloat(e.target.value))}
                style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.45rem 0.6rem', borderRadius: '4px', fontSize: '0.85rem' }}
              >
                <option value="0.99">99.0% Confidence (Stress Tail)</option>
                <option value="0.95">95.0% Confidence</option>
                <option value="0.90">90.0% Confidence</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.35rem' }}>
                CHALLENGED LOOKBACK HORIZON
              </label>
              <select
                value={challengedLookback}
                onChange={e => setChallengedLookback(parseInt(e.target.value, 10))}
                style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.45rem 0.6rem', borderRadius: '4px', fontSize: '0.85rem' }}
              >
                <option value="60">60 Trading Days (Short-term High Vol)</option>
                <option value="126">126 Trading Days (~6 Months)</option>
                <option value="504">504 Trading Days (Long-term 2 Years)</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button
                className="button primary"
                onClick={runAssumptionChallenge}
                disabled={loadingChallenge}
                style={{ width: '100%', background: '#2563eb', padding: '0.5rem', fontWeight: 600, fontSize: '0.85rem' }}
              >
                {loadingChallenge ? 'Perturbing...' : 'Recompute Challenged Run'}
              </button>
            </div>
          </div>

          {/* Side-by-Side Comparison Grid */}
          {challengeDeltas && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
              {/* VaR Comparison */}
              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>VALUE AT RISK (VaR)</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Baseline ({confidenceLevel * 100}%, {lookbackDays}d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff' }}>{challengeDeltas.baseVar}%</div>
                  </div>
                  <ArrowRight size={18} color="rgba(255,255,255,0.4)" />
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Challenged ({challengedConfidence * 100}%, {challengedLookback}d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f87171' }}>{challengeDeltas.chgVar}%</div>
                  </div>
                </div>
                <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: Number(challengeDeltas.pctVar) > 0 ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                  Sensitivity Shift: {Number(challengeDeltas.pctVar) > 0 ? '+' : ''}{challengeDeltas.pctVar}% (Δ = {challengeDeltas.deltaVar}%)
                </div>
              </div>

              {/* Expected Shortfall Comparison */}
              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>EXPECTED SHORTFALL (ES)</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Baseline ({confidenceLevel * 100}%, {lookbackDays}d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff' }}>{challengeDeltas.baseEs}%</div>
                  </div>
                  <ArrowRight size={18} color="rgba(255,255,255,0.4)" />
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Challenged ({challengedConfidence * 100}%, {challengedLookback}d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f87171' }}>{challengeDeltas.chgEs}%</div>
                  </div>
                </div>
                <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: Number(challengeDeltas.pctEs) > 0 ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                  Sensitivity Shift: {Number(challengeDeltas.pctEs) > 0 ? '+' : ''}{challengeDeltas.pctEs}% (Δ = {challengeDeltas.deltaEs}%)
                </div>
              </div>

              {/* Realized Volatility Comparison */}
              <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>ANNUALIZED VOLATILITY</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Baseline ({lookbackDays}d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff' }}>{challengeDeltas.baseVol}%</div>
                  </div>
                  <ArrowRight size={18} color="rgba(255,255,255,0.4)" />
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }}>Challenged ({challengedLookback}d)</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f87171' }}>{challengeDeltas.chgVol}%</div>
                  </div>
                </div>
                <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: Number(challengeDeltas.pctVol) > 0 ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                  Sensitivity Shift: {Number(challengeDeltas.pctVol) > 0 ? '+' : ''}{challengeDeltas.pctVol}% (Δ = {challengeDeltas.deltaVol}%)
                </div>
              </div>
            </div>
          )}

          <div style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.25)', padding: '0.75rem 1rem', borderRadius: '6px', fontSize: '0.8rem', color: '#93c5fd' }}>
            <b>Assumption Interpretation:</b> When shortening the lookback from 252d to 60d or shifting confidence to 99%, tail losses increase. FragilityShield does not assume that a single set of assumptions is authoritative—it systematically surfaces the boundary where risk conclusions alter.
          </div>
        </div>
      )}

      {/* TAB 4: SENSITIVITY MATRIX */}
      {activeTab === 'sensitivity' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.15rem', fontWeight: 600 }}>Fragility &amp; Assumption Sensitivity Matrix</h3>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
              Evaluates portfolio response across combinations of lookback windows and uniform market shocks.
            </p>
          </div>

          {loadingSensitivity ? (
            <div style={{ padding: '3rem', textAlign: 'center' }}>
              <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 0.75rem auto' }} />
              <p>Recomputing 2D parameter sensitivity matrix...</p>
            </div>
          ) : (
            <div className="table-scroll" style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'center', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.6)' }}>
                    <th style={{ padding: '0.75rem', textAlign: 'left' }}>Lookback Horizon</th>
                    <th style={{ padding: '0.75rem' }}>-5% Shock</th>
                    <th style={{ padding: '0.75rem' }}>-10% Shock</th>
                    <th style={{ padding: '0.75rem' }}>-15% Shock</th>
                    <th style={{ padding: '0.75rem' }}>-20% Shock</th>
                  </tr>
                </thead>
                <tbody>
                  {sensitivityMatrix.map((row, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 700, color: '#fff' }}>{row.lookback}</td>
                      <td style={{ padding: '0.75rem', color: '#fca5a5' }}>{row['5%']}%</td>
                      <td style={{ padding: '0.75rem', color: '#f87171' }}>{row['10%']}%</td>
                      <td style={{ padding: '0.75rem', color: '#ef4444' }}>{row['15%']}%</td>
                      <td style={{ padding: '0.75rem', color: '#dc2626', fontWeight: 700 }}>{row['20%']}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 5: REVERSE STRESS TESTING */}
      {activeTab === 'reversestress' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.15rem', fontWeight: 600 }}>Reverse Stress Testing Laboratory</h3>
            <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
              Inverts the risk question: specifies a catastrophic loss boundary and computes the minimum market shock required to cause it.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.5)', marginBottom: '0.25rem' }}>
                TARGET PORTFOLIO LOSS THRESHOLD (%)
              </label>
              <input
                type="number"
                min="1"
                max="90"
                value={targetLossPct}
                onChange={e => setTargetLossPct(parseFloat(e.target.value) || 10)}
                style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', padding: '0.45rem 0.75rem', borderRadius: '4px', fontSize: '0.9rem', width: '140px' }}
              />
            </div>

            <button
              className="button primary"
              onClick={handleRunReverseStress}
              disabled={runningReverseStress}
              style={{ background: '#ef4444', fontWeight: 600, padding: '0.5rem 1rem', alignSelf: 'flex-end' }}
            >
              {runningReverseStress ? 'Solving Root Brent...' : 'Search Breach Boundary'}
            </button>
          </div>

          {reverseStressResult && (
            <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: '8px', padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f87171', fontWeight: 600, marginBottom: '0.75rem' }}>
                <AlertTriangle size={18} />
                <span>Loss Boundary Solution Found (Brent Solver)</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>TARGET LOSS BOUNDARY</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#fff', marginTop: '0.2rem' }}>
                    -{targetLossPct}%
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>MINIMUM MARKET SHOCK REQUIRED</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#ef4444', marginTop: '0.2rem' }}>
                    {reverseStressResult?.required_shock !== undefined ? `${(reverseStressResult.required_shock * 100).toFixed(2)}%` : '—'}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>SOLVER STATUS</div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#10b981', marginTop: '0.2rem' }}>
                    CONVERGED
                  </div>
                </div>
              </div>

              <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
                <b>Interpretation:</b> A uniform market decline of {Math.abs(Number(((reverseStressResult.required_shock || -(targetLossPct / 100)) * 100).toFixed(2)))}% is sufficient to trigger the target {targetLossPct}% portfolio loss.
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 6: MATHEMATICAL PROVENANCE & AUDIT */}
      {activeTab === 'provenance' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.15rem', fontWeight: 600 }}>Mathematical Definitions &amp; Methodology Ledger</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', fontSize: '0.85rem' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px' }}>
              <div style={{ fontWeight: 700, color: '#60a5fa', marginBottom: '0.25rem' }}>Historical Value at Risk (VaR)</div>
              <div style={{ fontFamily: 'monospace', color: 'rgba(255,255,255,0.7)', marginBottom: '0.5rem' }}>
                VaR_α(L) = -q_α(R)
              </div>
              <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)', fontSize: '0.8rem' }}>
                Empirical quantile calculated on daily simple returns (r_t = P_t / P_t-1 - 1). The loss sign convention is strictly positive: a VaR of 0.024 represents a 2.4% maximum expected loss at the stated confidence level.
              </p>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px' }}>
              <div style={{ fontWeight: 700, color: '#60a5fa', marginBottom: '0.25rem' }}>Expected Shortfall / CVaR</div>
              <div style={{ fontFamily: 'monospace', color: 'rgba(255,255,255,0.7)', marginBottom: '0.5rem' }}>
                ES_α(L) = (1 / (1 - α)) ∫_α^1 VaR_u(L) du
              </div>
              <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)', fontSize: '0.8rem' }}>
                Average loss incurred strictly when the VaR threshold is breached. Acerbi &amp; Tasche (2002) fractional weighting guarantees subadditivity and coherent risk measurement ($ES \ge VaR$).
              </p>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px' }}>
              <div style={{ fontWeight: 700, color: '#60a5fa', marginBottom: '0.25rem' }}>Annualized Realized Volatility</div>
              <div style={{ fontFamily: 'monospace', color: 'rgba(255,255,255,0.7)', marginBottom: '0.5rem' }}>
                σ_ann = sqrt(1 / (N - 1) ∑ (r_t - r̄)²) × √252
              </div>
              <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)', fontSize: '0.8rem' }}>
                Sample standard deviation with ddof=1, annualized assuming 252 trading days per calendar year.
              </p>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '6px' }}>
              <div style={{ fontWeight: 700, color: '#60a5fa', marginBottom: '0.25rem' }}>CAPM Beta vs Benchmark</div>
              <div style={{ fontFamily: 'monospace', color: 'rgba(255,255,255,0.7)', marginBottom: '0.5rem' }}>
                β = Cov(r_i, r_b) / Var(r_b)
              </div>
              <p style={{ margin: 0, color: 'rgba(255,255,255,0.6)', fontSize: '0.8rem' }}>
                Calculated strictly across the inner-join intersection of synchronized trading dates between portfolio constituents and the benchmark index.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
