import { useState } from 'react';
import {
  BookOpen, Search, Copy, CheckCircle2, ChevronRight, Terminal,
  ShieldCheck, ArrowUpRight, Gauge, Activity, ShieldAlert, Sparkles, Layers3
} from 'lucide-react';

interface DocSection {
  id: string;
  title: string;
  category: string;
  content: string;
  codeSnippet?: { language: string; code: string };
  relatedRoute?: string;
}

const DOCS: DocSection[] = [
  {
    id: 'getting-started',
    title: '1. Platform Architecture & Overview',
    category: 'Architecture',
    content: `FragilityShield is an open-source, plug-and-play quantitative finance research laboratory for portfolio risk analysis, financial stress testing, assumption auditing, and reproducible experiments.

The core architecture strictly separates concerns into five layers:
- Quantitative Engine (fragility_engine): Deterministic numerical routines in NumPy, SciPy, and Pandas.
- Tenancy & Security: Forced PostgreSQL Row-Level Security (RLS) across tenant boundaries.
- Asynchronous Workers: Background job processing with task leasing, heartbeat, and cancellation.
- Market Data Adapters: Direct Upstox Market Data V3 REST API integration.
- Quantitative Web Terminal: High-density React 19 interface with real-time analytics.`,
    codeSnippet: {
      language: 'bash',
      code: `# Start FragilityShield backend server locally
python -m backend.app

# Run complete test suite (701 unit and integration tests)
pytest backend/tests -q`,
    },
    relatedRoute: '/overview',
  },
  {
    id: 'risk-formulas',
    title: '2. Risk Metrics & Mathematical Foundations',
    category: 'Quantitative Methodology',
    content: `FragilityShield implements formal mathematical definitions for all risk metrics:

• Value at Risk (VaR):
  - Parametric Gaussian: VaR_α = -μ + σ · Φ⁻¹(α)
  - Historical Simulation: VaR_α = -Q_α(R), where Q_α is the empirical α-quantile.
• Expected Shortfall (CVaR):
  - ES_α = -E[ R | R ≤ -VaR_α ] (the conditional expectation of losses exceeding VaR).
• Annualized Volatility:
  - σ_ann = σ_daily · √(252)
• Sharpe Ratio:
  - SR = (R_p - R_f) / σ_ann, where R_f defaults to the RBI 91-day T-Bill rate (6.5%).
• Herfindahl-Hirschman Concentration Index (HHI):
  - HHI = Σ w_i², with Effective N = 1 / HHI.`,
    relatedRoute: '/labs/risk',
  },
  {
    id: 'upstox-integration',
    title: '3. Upstox V3 Market Data Setup',
    category: 'Market Data',
    content: `FragilityShield natively connects to Upstox Market Data V3 REST APIs:
- Quotes & LTP: Real-time snapshots via /v3/market-quote/ltp.
- Historical OHLCV Candles: Multi-year daily and intraday candles via /v3/historical-candle.
- Instrument Resolver: Fast in-memory resolution across NSE EQ, NSE FO, and BSE symbols.

Configuration:
Place your Upstox API credentials in the root .env file:
UPSTOX_ACCESS_TOKEN=your_upstox_jwt_token_here
UPSTOX_API_KEY=your_api_key
UPSTOX_API_SECRET=your_api_secret`,
    codeSnippet: {
      language: 'python',
      code: `from fragility_engine.upstox import UpstoxMarketDataAdapter

adapter = UpstoxMarketDataAdapter()
prices = adapter.get_historical_prices(symbol="RELIANCE")
print(f"Retrieved {len(prices)} closing observations for RELIANCE")`,
    },
    relatedRoute: '/data',
  },
  {
    id: 'assumption-fragility',
    title: '4. Assumption Fragility & Tornado Audits',
    category: 'Fragility & Stress',
    content: `A central question of FragilityShield is: "How much do the conclusions change when underlying assumptions are perturbed?"

The Fragility Lab executes systematic perturbation attacks across 5 dimensions:
1. Lookback Window Drift: Tests sensitivity to short vs long historical estimation windows (e.g. 20d vs 60d).
2. Volatility Estimator Shift: Compares sample standard deviation with RiskMetrics EWMA (decay λ = 0.94).
3. Transaction Friction Drag: Injects 10 bps to 50 bps execution costs into portfolio returns.
4. Confidence Level Jumps: Assesses delta when moving from 95% to 99% regulatory confidence.
5. Liquidation Shocks: Models market impact during fire-sale portfolio unwind.`,
    relatedRoute: '/labs/fragility',
  },
  {
    id: 'backtesting-validation',
    title: '5. Rolling Backtesting & Statistical Validation',
    category: 'Strategies',
    content: `FragilityShield avoids naive in-sample backtesting by implementing out-of-sample rolling walk-forward evaluation:
- Kupiec POF (Proportion of Failures) Test: Likelihood ratio test evaluating whether the observed VaR breach rate matches theoretical α.
- Christoffersen Independence Test: Evaluates whether VaR exceptions cluster over time (volatility clustering) vs occurring independently.
- Rejection Criteria: If p-value < 0.05, the risk model is flagged as miscalibrated or clustering-vulnerable.`,
    relatedRoute: '/labs/backtesting',
  },
  {
    id: 'sdk-reference',
    title: '6. FragilityShield Python SDK Reference',
    category: 'Developer Reference',
    content: `The fragility_engine Python package provides a clean, typed SDK for quantitative researchers and algorithmic engineers.`,
    codeSnippet: {
      language: 'python',
      code: `import numpy as np
from fragility_engine.risk import calculate_risk_report, Portfolio
from fragility_engine.fragility import run_fragility_audit

# 1. Load portfolio
port = Portfolio.from_dict({
    "portfolio_id": "nse_active",
    "name": "Active Fund",
    "currency": "INR",
    "holdings": [{"asset_id": "INFY", "quantity": 100, "current_price": 1850.0}]
})

# 2. Compute risk
report = calculate_risk_report(port, confidence_level=0.95, lookback_window=252)
print("95% Historical VaR:", report.var_95)
print("Annualized Volatility:", report.volatility_annualized)`,
    },
    relatedRoute: '/sdk',
  },
];

export function DocsCenter({
  navigate,
  notify,
}: {
  navigate: (path: string) => void;
  notify: (msg: string) => void;
}) {
  const [selectedDoc, setSelectedDoc] = useState<DocSection>(DOCS[0]);
  const [search, setSearch] = useState('');
  const [copiedCode, setCopiedCode] = useState(false);

  const filteredDocs = DOCS.filter(d =>
    d.title.toLowerCase().includes(search.toLowerCase()) ||
    d.content.toLowerCase().includes(search.toLowerCase()) ||
    d.category.toLowerCase().includes(search.toLowerCase())
  );

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
    notify('Code snippet copied to clipboard.');
  };

  return (
    <div className="stack-layout">
      {/* Hero Header */}
      <section className="panel generic-hero">
        <div className="generic-mark"><BookOpen size={22} /></div>
        <div>
          <span className="section-kicker">KNOWLEDGE BASE / PAGE 29</span>
          <h2>Documentation &amp; Quantitative Learning Center</h2>
          <p>
            Complete developer reference, mathematical formulations, market data configuration guides, and API integration examples.
          </p>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Sidebar Nav */}
        <section className="panel p-4 space-y-3 lg:col-span-1">
          <div className="flex items-center gap-2 bg-black/40 px-3 py-2 rounded border border-border/50">
            <Search size={14} className="text-muted" />
            <input
              type="text"
              placeholder="Search docs..."
              className="bg-transparent border-0 text-xs focus:outline-none w-full"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            {filteredDocs.map(doc => (
              <button
                key={doc.id}
                className={`w-full text-left p-2.5 rounded text-xs transition-colors flex items-center justify-between ${
                  selectedDoc.id === doc.id
                    ? 'bg-primary/15 text-primary font-semibold border-l-2 border-primary'
                    : 'text-muted hover:text-foreground hover:bg-white/[0.02]'
                }`}
                onClick={() => setSelectedDoc(doc)}
              >
                <span className="truncate">{doc.title}</span>
                <ChevronRight size={12} className="opacity-50" />
              </button>
            ))}
          </div>
        </section>

        {/* Content View */}
        <section className="panel p-6 space-y-5 lg:col-span-3">
          <div className="panel-head p-0 pb-4 border-b border-border flex justify-between items-center">
            <div>
              <span className="badge text-xs mb-1" style={{ background: 'rgba(37,125,112,0.15)', color: '#257d70' }}>
                {selectedDoc.category}
              </span>
              <h2 className="text-xl font-bold text-foreground">{selectedDoc.title}</h2>
            </div>
            {selectedDoc.relatedRoute && (
              <button
                className="button primary small inline-flex items-center gap-1"
                onClick={() => navigate(selectedDoc.relatedRoute!)}
              >
                Open Related Module <ArrowUpRight size={13} />
              </button>
            )}
          </div>

          <div className="prose prose-invert max-w-none text-sm text-foreground/90 whitespace-pre-wrap leading-relaxed">
            {selectedDoc.content}
          </div>

          {selectedDoc.codeSnippet && (
            <div className="space-y-2 pt-2">
              <div className="flex items-center justify-between text-xs text-muted">
                <span className="font-mono uppercase">{selectedDoc.codeSnippet.language} SNIPPET</span>
                <button
                  className="button secondary small inline-flex items-center gap-1 py-1"
                  onClick={() => copyCode(selectedDoc.codeSnippet!.code)}
                >
                  {copiedCode ? <CheckCircle2 size={12} className="text-emerald-400" /> : <Copy size={12} />}
                  {copiedCode ? 'Copied' : 'Copy'}
                </button>
              </div>
              <pre className="bg-black/60 p-4 rounded border border-border/50 font-mono text-xs overflow-x-auto text-emerald-400">
                {selectedDoc.codeSnippet.code}
              </pre>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
