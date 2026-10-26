import { api } from '@/lib/api';
import { useState, useEffect } from 'react';
import {
  BriefcaseBusiness, Play, Plus, Search, Filter, SlidersHorizontal,
  ArrowUpRight, CheckCircle2, ChevronRight, X, TrendingUp, ShieldAlert,
  ArrowDownToLine, Zap
} from 'lucide-react';

export interface StrategyTemplate {
  id: string;
  name: string;
  family: string;
  description: string;
  entryRule: string;
  exitRule: string;
  defaultParams: {
    fastPeriod?: number;
    slowPeriod?: number;
    targetVol?: number;
    stopLossPct?: number;
    transactionCostBps: number;
    slippageBps: number;
    positionSizePct: number;
  };
}

const TEMPLATES: StrategyTemplate[] = [
  {
    id: 'strat_ma_cross',
    name: 'Moving Average Crossover (20 / 50)',
    family: 'Trend Following',
    description: 'Enters long when the fast 20-day simple moving average crosses above the slow 50-day SMA; exits on downward cross.',
    entryRule: 'SMA(20) > SMA(50) and Lag(SMA(20)) <= Lag(SMA(50))',
    exitRule: 'SMA(20) < SMA(50)',
    defaultParams: {
      fastPeriod: 20,
      slowPeriod: 50,
      stopLossPct: 3.5,
      transactionCostBps: 10,
      slippageBps: 5,
      positionSizePct: 100,
    },
  },
  {
    id: 'strat_momentum_rsi',
    name: 'Relative Strength Momentum (RSI 14)',
    family: 'Momentum',
    description: 'Enters when 14-day RSI accelerates out of oversold territory (> 35); exits when RSI crosses overbought threshold (> 70).',
    entryRule: 'RSI(14) > 35 and Lag(RSI(14)) <= 35',
    exitRule: 'RSI(14) >= 70 or StopLoss hit',
    defaultParams: {
      fastPeriod: 14,
      stopLossPct: 4.0,
      transactionCostBps: 10,
      slippageBps: 5,
      positionSizePct: 80,
    },
  },
  {
    id: 'strat_vol_target',
    name: 'Risk-Budgeted Volatility Targeting (15% Vol)',
    family: 'Risk Parity / Volatility',
    description: 'Scales portfolio exposure inversely to realized 20-day annualized volatility to maintain a strict 15% risk ceiling.',
    entryRule: 'Target_Weight = Min(1.0, 0.15 / Realized_Vol_20d)',
    exitRule: 'Daily rebalancing when realized volatility shifts by > 200 bps',
    defaultParams: {
      targetVol: 15.0,
      fastPeriod: 20,
      transactionCostBps: 8,
      slippageBps: 4,
      positionSizePct: 100,
    },
  },
  {
    id: 'strat_mean_reversion',
    name: 'Statistical Mean Reversion (Bollinger 2σ)',
    family: 'Mean Reversion',
    description: 'Trades statistical reversion to the 20-day mean when prices breach lower 2-standard-deviation Bollinger envelope.',
    entryRule: 'Close < (SMA(20) - 2 * StDev(20))',
    exitRule: 'Close >= SMA(20)',
    defaultParams: {
      fastPeriod: 20,
      stopLossPct: 2.5,
      transactionCostBps: 12,
      slippageBps: 6,
      positionSizePct: 50,
    },
  },
  {
    id: 'strat_buy_and_hold',
    name: 'Passive Buy & Hold Benchmark',
    family: 'Benchmark Baseline',
    description: 'Fully invested baseline without rebalancing friction or signal delay; canonical benchmark for alpha calculation.',
    entryRule: 'Day 1 Allocation = 100%',
    exitRule: 'Terminal Horizon Valuation',
    defaultParams: {
      transactionCostBps: 5,
      slippageBps: 2,
      positionSizePct: 100,
    },
  },
];

export function StrategyLibrary({
  navigate,
  notify,
}: {
  navigate: (path: string) => void;
  notify: (msg: string) => void;
}) {
  const [strategies, setStrategies] = useState<StrategyTemplate[]>(TEMPLATES);
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'catalog' | 'builder'>('catalog');
  const [selectedStrat, setSelectedStrat] = useState<StrategyTemplate>(TEMPLATES[0]);

  useEffect(() => {
    async function loadCustom() {
      try {
        const res = await api.listCustomStrategies();
        const custom = Array.isArray(res) ? res : (res?.strategies || []);
        if (custom.length > 0) {
          const mapped: StrategyTemplate[] = custom.map((c: any) => ({
            id: c.id || c.strategy_id || `strat_user_${Date.now()}`,
            name: c.name || 'Custom Quantitative Strategy',
            family: c.family || 'Custom',
            description: c.description || 'User-defined registered strategy',
            entryRule: c.entryRule || c.entry_rule || 'Custom Entry Rule',
            exitRule: c.exitRule || c.exit_rule || 'Custom Exit Rule',
            defaultParams: c.defaultParams || c.default_params || {
              transactionCostBps: 10,
              slippageBps: 5,
              positionSizePct: 100,
            },
          }));
          const seen = new Set(TEMPLATES.map((t) => t.id));
          const merged = [...TEMPLATES];
          for (const m of mapped) {
            if (!seen.has(m.id)) {
              seen.add(m.id);
              merged.push(m);
            }
          }
          setStrategies(merged);
        }
      } catch (err) {
        // Fallback to built-in templates
      }
    }
    loadCustom();
  }, []);

  // Strategy Builder State
  const [builderParams, setBuilderParams] = useState({
    name: 'Custom Moving Average Strategy',
    family: 'Trend Following',
    fastPeriod: 20,
    slowPeriod: 50,
    stopLossPct: 3.5,
    transactionCostBps: 10,
    slippageBps: 5,
    positionSizePct: 100,
  });

  const [previewSignals, setPreviewSignals] = useState<{ date: string; price: number; signal: 'BUY' | 'SELL' | 'HOLD'; equity: number }[]>([]);

  const handlePreview = () => {
    // Generate deterministic trade signal demonstration
    const rows = [];
    let p = 1000;
    let eq = 1000000;
    let inPos = false;
    for (let i = 1; i <= 30; i++) {
      const ret = (Math.sin(i * 0.4) * 0.015) + (Math.cos(i * 0.2) * 0.008);
      p = Number((p * (1 + ret)).toFixed(2));
      let sig: 'BUY' | 'SELL' | 'HOLD' = 'HOLD';
      if (i === 5 || i === 18) {
        sig = 'BUY';
        inPos = true;
      } else if (i === 12 || i === 26) {
        sig = 'SELL';
        inPos = false;
      }
      if (inPos) {
        eq = Number((eq * (1 + ret - (builderParams.transactionCostBps / 10000))).toFixed(0));
      }
      rows.push({
        date: `2026-09-${String(i).padStart(2, '0')}`,
        price: p,
        signal: sig,
        equity: eq,
      });
    }
    setPreviewSignals(rows);
    notify('Generated preview signals and simulated position path.');
  };

  const handleLaunchBacktest = (strat: StrategyTemplate) => {
    notify(`Transferring strategy "${strat.name}" to Backtesting Lab...`);
    navigate('/labs/backtesting');
  };

  const handleSaveCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    const newStrat: StrategyTemplate = {
      id: `strat_user_${Date.now()}`,
      name: builderParams.name,
      family: builderParams.family,
      description: `User-defined ${builderParams.family} model with fast=${builderParams.fastPeriod}, slow=${builderParams.slowPeriod}.`,
      entryRule: `Fast(${builderParams.fastPeriod}) > Slow(${builderParams.slowPeriod})`,
      exitRule: `Fast(${builderParams.fastPeriod}) < Slow(${builderParams.slowPeriod}) or StopLoss(${builderParams.stopLossPct}%)`,
      defaultParams: {
        fastPeriod: builderParams.fastPeriod,
        slowPeriod: builderParams.slowPeriod,
        stopLossPct: builderParams.stopLossPct,
        transactionCostBps: builderParams.transactionCostBps,
        slippageBps: builderParams.slippageBps,
        positionSizePct: builderParams.positionSizePct,
      },
    };
    try {
      await api.saveCustomStrategy(newStrat);
      notify(`Custom strategy "${builderParams.name}" saved to strategy registry.`);
    } catch (err: any) {
      notify(`Saved locally: ${err?.message || 'Offline mode'}`);
    }
    setStrategies((prev) => [newStrat, ...prev]);
    setSelectedStrat(newStrat);
    setActiveTab('catalog');
    notify(`Saved custom strategy "${newStrat.name}" to Library.`);
  };

  return (
    <div className="stack-layout">
      {/* Hero Header */}
      <section className="panel generic-hero">
        <div className="generic-mark"><BriefcaseBusiness size={22} /></div>
        <div>
          <span className="section-kicker">STRATEGY OPERATIONS / PAGE 15</span>
          <h2>Strategy Library &amp; Quantitative Builder</h2>
          <p>
            Inspect reusable trading strategies, configure signal generation rules, model realistic transaction frictions, and transfer directly to the Backtesting Lab.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className={`button small ${activeTab === 'catalog' ? 'primary' : 'secondary'}`}
            onClick={() => setActiveTab('catalog')}
          >
            Strategy Catalog ({strategies.length})
          </button>
          <button
            className={`button small ${activeTab === 'builder' ? 'primary' : 'secondary'}`}
            onClick={() => {
              setActiveTab('builder');
              if (!previewSignals.length) handlePreview();
            }}
          >
            <SlidersHorizontal size={14} className="mr-1" /> Strategy Builder
          </button>
        </div>
      </section>

      {activeTab === 'catalog' ? (
        <>
          {/* Strategy Search */}
          <section className="panel">
            <div className="flex items-center justify-between gap-3 p-4">
              <div className="flex items-center gap-2 flex-1">
                <Search size={16} className="text-muted" />
                <input
                  type="text"
                  placeholder="Search quantitative strategies by name or rule..."
                  className="bg-transparent border-0 text-sm focus:outline-none w-full"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
                {search && <button onClick={() => setSearch('')} className="text-muted"><X size={14} /></button>}
              </div>
            </div>
          </section>

          {/* Strategy Catalog Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {strategies
              .filter(s => s.name.toLowerCase().includes(search.toLowerCase()) || s.family.toLowerCase().includes(search.toLowerCase()))
              .map(strat => (
                <div key={strat.id} className="panel p-5 space-y-4 hover:border-primary/50 transition-colors">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="badge text-xs mb-1.5" style={{ background: 'rgba(37,125,112,0.15)', color: '#257d70' }}>
                        {strat.family}
                      </span>
                      <h3 className="text-base font-bold text-foreground">{strat.name}</h3>
                    </div>
                  </div>

                  <p className="text-xs text-muted line-clamp-2">{strat.description}</p>

                  <div className="space-y-1.5 bg-white/[0.02] p-3 rounded border border-border/40 font-mono text-xs">
                    <div className="truncate"><span className="text-primary font-bold">ENTRY:</span> {strat.entryRule}</div>
                    <div className="truncate"><span className="text-destructive font-bold">EXIT:</span> {strat.exitRule}</div>
                    <div className="text-muted text-[11px] pt-1 border-t border-border/30 flex justify-between">
                      <span>Friction: {strat.defaultParams.transactionCostBps} bps</span>
                      <span>Slippage: {strat.defaultParams.slippageBps} bps</span>
                      <span>Stop: {strat.defaultParams.stopLossPct ?? 'None'}%</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <button
                      className="button secondary small inline-flex items-center gap-1"
                      onClick={() => {
                        setBuilderParams({
                          name: `${strat.name} (Custom)`,
                          family: strat.family,
                          fastPeriod: strat.defaultParams.fastPeriod ?? 20,
                          slowPeriod: strat.defaultParams.slowPeriod ?? 50,
                          stopLossPct: strat.defaultParams.stopLossPct ?? 3.5,
                          transactionCostBps: strat.defaultParams.transactionCostBps,
                          slippageBps: strat.defaultParams.slippageBps,
                          positionSizePct: strat.defaultParams.positionSizePct,
                        });
                        setActiveTab('builder');
                        handlePreview();
                      }}
                    >
                      <SlidersHorizontal size={13} /> Customize
                    </button>
                    <button
                      className="button primary small inline-flex items-center gap-1"
                      onClick={() => handleLaunchBacktest(strat)}
                    >
                      <Play size={13} /> Run Backtest <ArrowUpRight size={13} />
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </>
      ) : (
        /* Strategy Builder Workspace */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <section className="panel p-5 space-y-4 lg:col-span-1">
            <div className="panel-head p-0 pb-3 border-b border-border">
              <div>
                <span className="section-kicker">PARAMETER TUNING</span>
                <h3 className="text-base font-bold">Configure Rules</h3>
              </div>
            </div>

            <form onSubmit={handleSaveCustom} className="space-y-3">
              <label className="field-label">
                STRATEGY NAME
                <input
                  value={builderParams.name}
                  onChange={e => setBuilderParams({ ...builderParams, name: e.target.value })}
                  required
                />
              </label>

              <label className="field-label">
                FAST LOOKBACK (PERIODS)
                <input
                  type="number"
                  min="2"
                  max="200"
                  value={builderParams.fastPeriod}
                  onChange={e => setBuilderParams({ ...builderParams, fastPeriod: Number(e.target.value) })}
                />
              </label>

              <label className="field-label">
                SLOW LOOKBACK (PERIODS)
                <input
                  type="number"
                  min="5"
                  max="300"
                  value={builderParams.slowPeriod}
                  onChange={e => setBuilderParams({ ...builderParams, slowPeriod: Number(e.target.value) })}
                />
              </label>

              <label className="field-label">
                STOP-LOSS THRESHOLD (%)
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  max="20"
                  value={builderParams.stopLossPct}
                  onChange={e => setBuilderParams({ ...builderParams, stopLossPct: Number(e.target.value) })}
                />
              </label>

              <div className="grid grid-cols-2 gap-2">
                <label className="field-label">
                  FEES (BPS)
                  <input
                    type="number"
                    value={builderParams.transactionCostBps}
                    onChange={e => setBuilderParams({ ...builderParams, transactionCostBps: Number(e.target.value) })}
                  />
                </label>
                <label className="field-label">
                  SLIPPAGE (BPS)
                  <input
                    type="number"
                    value={builderParams.slippageBps}
                    onChange={e => setBuilderParams({ ...builderParams, slippageBps: Number(e.target.value) })}
                  />
                </label>
              </div>

              <div className="pt-2 flex flex-col gap-2">
                <button type="button" className="button secondary small w-full inline-flex items-center justify-center gap-1" onClick={handlePreview}>
                  <Zap size={14} /> Refresh Signal Preview
                </button>
                <button type="submit" className="button primary small w-full inline-flex items-center justify-center gap-1">
                  Save to Library
                </button>
              </div>
            </form>
          </section>

          <section className="panel p-5 space-y-4 lg:col-span-2">
            <div className="panel-head p-0 pb-3 border-b border-border flex justify-between items-center">
              <div>
                <span className="section-kicker">SIMULATED EXECUTION PREVIEW</span>
                <h3 className="text-base font-bold">Signal Log &amp; Simulated Equity</h3>
              </div>
              <button
                className="button primary small inline-flex items-center gap-1"
                onClick={() => handleLaunchBacktest({
                  id: 'custom_builder',
                  name: builderParams.name,
                  family: builderParams.family,
                  description: 'Configured in Strategy Builder',
                  entryRule: `Fast(${builderParams.fastPeriod}) > Slow(${builderParams.slowPeriod})`,
                  exitRule: `Fast(${builderParams.fastPeriod}) < Slow(${builderParams.slowPeriod})`,
                  defaultParams: builderParams,
                })}
              >
                <Play size={13} /> Launch Full Backtest <ArrowUpRight size={13} />
              </button>
            </div>

            <div className="table-scroll max-h-96">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Simulated Price</th>
                    <th>Signal</th>
                    <th>Simulated Equity</th>
                  </tr>
                </thead>
                <tbody>
                  {previewSignals.map(row => (
                    <tr key={row.date}>
                      <td className="font-mono text-xs">{row.date}</td>
                      <td className="font-mono text-xs">₹ {row.price.toFixed(2)}</td>
                      <td>
                        <span className={`badge text-xs ${
                          row.signal === 'BUY'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : row.signal === 'SELL'
                            ? 'bg-rose-500/20 text-rose-400'
                            : 'bg-white/10 text-muted'
                        }`}>
                          {row.signal}
                        </span>
                      </td>
                      <td className="font-mono text-xs font-semibold">₹ {row.equity.toLocaleString('en-IN')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
