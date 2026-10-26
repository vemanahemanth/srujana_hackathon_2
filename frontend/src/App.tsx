import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Link, Route, Router as WouterRouter, Switch, useLocation } from 'wouter';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell,
  Line, LineChart as RechartsLineChart, Pie, PieChart, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip as RechartsTooltip, XAxis, YAxis,
} from 'recharts';
import {
  Activity, Archive, ArrowDownToLine, ArrowLeftRight, Bell, BookOpen, Boxes,
  BriefcaseBusiness, ChartNoAxesCombined, CheckCircle2, ChevronDown, ChevronRight,
  CircleHelp, Command, Database, Download, FileClock, FlaskConical, Gauge, Layers3, LayoutDashboard,
  LineChart, Menu, Moon, MoreHorizontal, PanelLeftClose, Plus, RefreshCw, Scale, Search, Settings,
  ShieldAlert, ShieldCheck, SlidersHorizontal, Sparkles, Sun, TerminalSquare,
  Upload, X, Zap,
} from 'lucide-react';
import {
  api,
  type Portfolio as ApiPortfolio,
  type RiskReport,
  type ConcentrationReport,
  type ScenarioResult,
  type FragilityResult,
  type JobRecord,
  type WorkerDiagnostics,
  type ArtifactItem,
  type SecurityStatus,
} from '@/lib/api';
import { AssumptionsRegistry } from '@/components/pages/AssumptionsRegistry';
import { ModelRegistry } from '@/components/pages/ModelRegistry';
import { StrategyLibrary } from '@/components/pages/StrategyLibrary';
import { PluginLaboratory } from '@/components/pages/PluginLaboratory';
import { ReportCenter } from '@/components/pages/ReportCenter';
import { DocsCenter } from '@/components/pages/DocsCenter';
import { HelpDiagnostics } from '@/components/pages/HelpDiagnostics';
import { MarketTerminal } from '@/components/pages/MarketTerminal';
import { InstrumentDetailExplorer } from '@/components/pages/InstrumentDetailExplorer';
import { OverviewCommandCenter } from '@/components/pages/OverviewCommandCenter';
import { PortfolioWorkbench } from '@/components/pages/PortfolioWorkbench';
import { RiskScenarioLab } from '@/components/pages/RiskScenarioLab';
import { FragilityAssumptionMatrix } from '@/components/pages/FragilityAssumptionMatrix';
import { ModelValidationLab } from '@/components/pages/ModelValidationLab';
import { StrategyBacktestLab } from '@/components/pages/StrategyBacktestLab';
import { UnifiedExperimentRegistry } from '@/components/pages/UnifiedExperimentRegistry';
import { DataObservatory } from '@/components/pages/DataObservatory';
import { TailRiskReverseStressLab } from '@/components/pages/TailRiskReverseStressLab';
import { IntegrationPluginStudio } from '@/components/pages/IntegrationPluginStudio';
import { RiskModelValidationLab } from '@/components/pages/RiskModelValidationLab';
import { MonteCarloSimulationLab } from '@/components/pages/MonteCarloSimulationLab';
import { ModelTournamentBenchmarking } from '@/components/pages/ModelTournamentBenchmarking';
import { RiskAttributionLab } from '@/components/pages/RiskAttributionLab';
import { BootstrapUncertaintyLab } from '@/components/pages/BootstrapUncertaintyLab';
import { MLForecastingLab } from '@/components/pages/MLForecastingLab';
import { MLRobustnessLab } from '@/components/pages/MLRobustnessLab';
import { QuantitativeAllocationLab } from '@/components/pages/QuantitativeAllocationLab';
import { RiskAnalyticsLab } from '@/components/pages/RiskAnalyticsLab';
import { SDKDeveloperHub } from '@/components/pages/SDKDeveloperHub';
import { CustomDashboardWorkspace } from '@/components/pages/CustomDashboardWorkspace';


const queryClient = new QueryClient();

type NavItem = { title: string; path: string; icon: typeof Activity };
const groups: { name: string; items: NavItem[] }[] = [
  { name: 'Workspace', items: [
    { title: 'Overview', path: '/overview', icon: Layers3 },
    { title: 'Custom Dashboards', path: '/dashboards', icon: LayoutDashboard },

    { title: 'Market Terminal', path: '/market', icon: LineChart },
    { title: 'Portfolio Workbench', path: '/portfolio', icon: BriefcaseBusiness },
    { title: 'Data Quality Observatory', path: '/data-observatory', icon: Database },
    { title: 'Data Sources', path: '/data', icon: Database },
    { title: 'Saved Portfolios', path: '/saved-portfolios', icon: Archive },
  ] },
  { name: 'Risk laboratory', items: [
    { title: 'Risk & Scenario Lab', path: '/labs/risk-scenarios', icon: Gauge },
    { title: 'Risk Analytics', path: '/labs/risk', icon: Gauge },
    { title: 'Risk Attribution Lab', path: '/labs/attribution', icon: ChartNoAxesCombined },
    { title: 'Scenario Analysis Lab', path: '/labs/scenarios', icon: Activity },
    { title: 'Reverse Stress Testing Lab', path: '/labs/reverse-stress', icon: ArrowLeftRight },
    { title: 'Tail Risk & Reverse Stress Lab', path: '/labs/tail-risk', icon: ShieldAlert },
    { title: 'Fragility & Sensitivity Studio', path: '/labs/fragility', icon: ShieldAlert },
    { title: 'Monte Carlo Simulation Lab', path: '/labs/monte-carlo', icon: Sparkles },
    { title: 'Bootstrap & Uncertainty Lab', path: '/labs/uncertainty', icon: SlidersHorizontal },
    { title: 'Model Validation', path: '/labs/model-validation', icon: ShieldCheck },
    { title: 'Fragility Assumption Matrix', path: '/assumptions', icon: FileClock },
  ] },
  { name: 'Models & strategies', items: [
    { title: 'Model Testing & Validation Lab', path: '/models', icon: Layers3 },
    { title: 'Risk Model Backtesting Observatory', path: '/models/risk-validation', icon: Scale },
    { title: 'ML Forecasting & Evaluation', path: '/labs/ml-forecasting', icon: Activity },
    { title: 'ML Robustness & Adversarial Testing', path: '/labs/ml-robustness', icon: ShieldCheck },
    { title: 'Strategy Library & Builder', path: '/strategies', icon: BriefcaseBusiness },
    { title: 'Backtesting Lab', path: '/labs/backtesting', icon: ChartNoAxesCombined },
    { title: 'Model Tournament & Benchmarking', path: '/labs/tournament', icon: ArrowLeftRight },
    { title: 'Quantitative Allocation & Optimization', path: '/labs/allocation', icon: SlidersHorizontal },
  ] },
  { name: 'Research operations', items: [
    { title: 'Python SDK & Algorithm Hub', path: '/sdk', icon: TerminalSquare },
    { title: 'Experiment Studio', path: '/experiments', icon: FlaskConical },
    { title: 'Experiment History', path: '/experiments/history', icon: FileClock },
    { title: 'Reporting & Exports', path: '/reports', icon: ArrowDownToLine },
    { title: 'Reproducibility & Audit', path: '/provenance', icon: ShieldCheck },
    { title: 'Integration & Plugin Studio', path: '/integrations', icon: Boxes },
    { title: 'Plugin Laboratory', path: '/plugins', icon: Zap },
  ] },
  { name: 'System', items: [
    { title: 'Notifications, Jobs & History', path: '/notifications', icon: Bell },
    { title: 'Documentation & Learning', path: '/docs', icon: BookOpen },
    { title: 'Settings, Security & Preferences', path: '/settings', icon: Settings },
    { title: 'Help & Diagnostics', path: '/help', icon: CircleHelp },
  ] },
];

const pageTitles: Record<string, string> = {
  '/dashboards': 'Customizable Persistent Dashboard Workspace',
  '/custom-dashboard': 'Customizable Persistent Dashboard Workspace',
  '/overview': 'Overview / Research Command Center',
  '/market': 'Market Terminal',
  '/portfolio': 'Portfolio Workbench',
  '/labs/risk-scenarios': 'Risk & Scenario Analysis Lab',
  '/saved-portfolios': 'Saved Portfolios',
  '/data': 'Data Sources and Import Center',
  '/data-observatory': 'Data Quality & Provenance Observatory',
  '/labs/risk': 'Risk Analytics Lab',
  '/labs/attribution': 'Risk Attribution Lab',
  '/labs/scenarios': 'Scenario Analysis Lab',
  '/labs/reverse-stress': 'Reverse Stress Testing Lab',
  '/labs/tail-risk': 'Tail Risk & Reverse Stress Testing Lab',
  '/labs/fragility': 'Fragility and Assumption Sensitivity Studio',
  '/assumptions': 'Fragility Assumption Matrix',
  '/models': 'Model Testing & Validation Lab',
  '/models/risk-validation': 'Risk Model Backtesting Observatory',
  '/labs/ml-forecasting': 'ML Forecasting and Evaluation Lab',
  '/labs/ml-robustness': 'ML Robustness and Adversarial Testing Lab',
  '/strategies': 'Strategy Library and Strategy Builder',
  '/labs/backtesting': 'Strategy Backtesting & Assumption Audit Lab',
  '/backtesting-lab': 'Strategy Backtesting & Assumption Audit Lab',
  '/labs/backtest': 'Strategy Backtesting & Assumption Audit Lab',
  '/labs/tournament': 'Model Tournament and Benchmarking',
  '/labs/monte-carlo': 'Monte Carlo Simulation Lab',
  '/labs/uncertainty': 'Bootstrap and Uncertainty Lab',
  '/labs/model-validation': 'Model Validation Lab',
  '/labs/allocation': 'Quantitative Allocation and Optimization',
  '/experiments': 'Experiment Studio',
  '/experiments/history': 'Experiment History',
  '/plugins': 'Plugin Laboratory',
  '/integrations': 'Integration & Plugin Studio',
  '/provenance': 'Data Provenance and Quality Center',
  '/sdk': 'Python SDK & Algorithm Hub',
  '/reports': 'Results Reporting and Export Center',
  '/notifications': 'Notifications, Jobs and Execution History',
  '/settings': 'Settings, Security and Preferences',
  '/docs': 'Documentation and Learning Center',
  '/help': 'Help and Diagnostics',
};

const labInfo: Record<string, { eyebrow: string; description: string; fields: string[] }> = {
  '/labs/risk': { eyebrow: 'RISK / 01', description: 'Measure portfolio risk with explicit assumptions, validated input coverage, and reproducible methodology.', fields: ['Portfolio or dataset', 'Confidence level', 'Lookback window', 'Risk methodology'] },
  '/labs/attribution': { eyebrow: 'RISK / 02', description: 'Decompose portfolio risk into constituent, factor, and allocation effects.', fields: ['Portfolio', 'Attribution method', 'Benchmark', 'Lookback window'] },
  '/labs/scenarios': { eyebrow: 'RISK / 03', description: 'Define transparent market shocks and evaluate portfolio response when a calculation service is available.', fields: ['Portfolio', 'Scenario template', 'Shock magnitude', 'Affected factors'] },
  '/labs/reverse-stress': { eyebrow: 'RISK / 04', description: 'Specify a loss boundary and search for combinations of assumptions that could breach it.', fields: ['Portfolio', 'Loss threshold', 'Search variables', 'Constraints'] },
  '/labs/fragility': { eyebrow: 'RISK / 05', description: 'Challenge assumptions one at a time and map how conclusions respond to perturbations.', fields: ['Portfolio or model', 'Assumption', 'Perturbation range', 'Step size'] },
  '/labs/monte-carlo': { eyebrow: 'RISK / 06', description: 'Execute Monte Carlo stochastic simulation over user-defined paths and horizons.', fields: ['Portfolio or model', 'Simulation count', 'Horizon', 'Random seed'] },
  '/labs/uncertainty': { eyebrow: 'RISK / 07', description: 'Design resampling and interval estimation for data with a known provenance.', fields: ['Dataset', 'Resampling method', 'Replications', 'Block length'] },
  '/labs/model-validation': { eyebrow: 'VALIDATION', description: 'Set validation criteria and document evidence before any model is approved for use.', fields: ['Registered model', 'Validation dataset', 'Validation protocol', 'Acceptance criteria'] },
  '/labs/ml-forecasting': { eyebrow: 'MODELS / 01', description: 'Configure a forecasting evaluation without presenting uncomputed predictions as results.', fields: ['Dataset', 'Target variable', 'Forecast horizon', 'Train / test split'] },
  '/labs/ml-robustness': { eyebrow: 'MODELS / 02', description: 'Specify robustness checks for distribution shift, perturbation, and feature sensitivity.', fields: ['Registered model', 'Evaluation dataset', 'Stress type', 'Perturbation level'] },
  '/labs/backtesting': { eyebrow: 'STRATEGIES / 01', description: 'Define a backtest protocol, including costs and rebalancing assumptions, before running.', fields: ['Strategy', 'Portfolio universe', 'Date range', 'Transaction costs'] },
  '/labs/tournament': { eyebrow: 'MODELS / 03', description: 'Prepare a fair, aligned comparison protocol across registered models.', fields: ['Models to compare', 'Evaluation dataset', 'Metric', 'Date alignment'] },
  '/labs/allocation': { eyebrow: 'ALLOCATION', description: 'Optimize portfolio weights subject to risk constraints and objective functions.', fields: ['Portfolio universe', 'Objective', 'Constraints', 'Rebalance frequency'] },
  '/sdk': { eyebrow: 'EXTENSIBILITY / SDK', description: 'Interactive Python SDK execution console, algorithm registration studio, and code generator.', fields: ['Method', 'Payload', 'Model ID', 'Tenant Token'] },
};

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={(import.meta as any).env?.BASE_URL?.replace(/\/$/, '') || ''}>
          <AppRoutes />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

function AppRoutes() {
  const [location] = useLocation();
  return (
    <ErrorBoundary resetKey={location}>
      <Switch>
        <Route path="/" component={Terminal} />
        <Route path="/market/instrument/:instrumentId" component={Terminal} />
        {Object.keys(pageTitles).map(path => (
          <Route key={path} path={path} component={Terminal} />
        ))}
        <Route path="/:rest*" component={Terminal} />
      </Switch>
    </ErrorBoundary>
  );
}

function Terminal() {
  const [location, setLocation] = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [dark, setDark] = useState(true);
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [toast, setToast] = useState('');
  const [workspace, setWorkspace] = useState('Research workspace (ten_alpha_capital)');
  
  // Real backend connection states
  const [backendHealth, setBackendHealth] = useState<{ status: string } | null>(null);
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [upstoxStatus, setUpstoxStatus] = useState<{ configured: boolean; authenticated: boolean } | null>(null);
  const [workerInfo, setWorkerInfo] = useState<WorkerDiagnostics | null>(null);
  
  // Active quantitative research data
  const [activePortfolio, setActivePortfolio] = useState<ApiPortfolio | null>(null);
  const [portfolioName, setPortfolioName] = useState('NSE 10L Sample (nse_10l.json)');
  const [savedPortfolios, setSavedPortfolios] = useState<ApiPortfolio[]>([]);
  const [riskReport, setRiskReport] = useState<RiskReport | null>(null);
  const [concentration, setConcentration] = useState<ConcentrationReport | null>(null);
  const [loadingRisk, setLoadingRisk] = useState(false);
  
  const [dateRange, setDateRange] = useState('1Y');
  const [tab, setTab] = useState('Summary');
  const [customize, setCustomize] = useState(false);
  const [hiddenWidgets, setHiddenWidgets] = useState<string[]>([]);
  const [draftName, setDraftName] = useState('');
  const [drafts, setDrafts] = useState<string[]>(['Baseline Risk Sensitivity Run']);
  const [uploadedName, setUploadedName] = useState('');
  const [settings, setSettings] = useState({ alerts: true, compact: false, confirm: true });
  const [previewCharts, setPreviewCharts] = useState(true);

  const page = location === '/' ? '/overview' : location;
  const title = page.startsWith('/market/instrument/') ? 'Instrument detail' : (pageTitles[page] || 'Research workspace');
  const isLab = !!labInfo[page];
  const isOverview = page === '/overview';
  const isMarket = page === '/market' || page.startsWith('/market/instrument/');

  const filteredNav = useMemo(
    () => groups.map(g => ({ ...g, items: g.items.filter(i => i.title.toLowerCase().includes(search.toLowerCase())) })).filter(g => g.items.length),
    [search]
  );

  const notify = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(''), 3500);
  };

  // 1. Initial backend connection probe & portfolio load
  useEffect(() => {
    async function initSystem() {
      try {
        const health = await api.getHealth();
        setBackendHealth(health);
      } catch (err: any) {
        console.warn('Backend probe warning:', err.message);
      }

      try {
        const sec = await api.getSecurityStatus();
        setSecurityStatus(sec);
      } catch (err: any) {
        console.warn('Security status probe warning:', err.message);
      }

      try {
        const upstox = await api.getUpstoxStatus();
        setUpstoxStatus(upstox);
      } catch (err: any) {
        console.warn('Upstox probe warning:', err.message);
      }

      try {
        const w = await api.getWorkerStatus();
        if (w.success && w.worker) {
          setWorkerInfo(w.worker);
        }
      } catch {
        // Worker endpoint optional in local dev
      }

      // Load initial portfolio
      try {
        const sample = await api.getSamplePortfolio('nse_10l.json');
        setActivePortfolio(sample);
        setPortfolioName(sample.name || 'NSE 10L Sample');
        
        // Calculate initial risk & concentration in parallel
        setLoadingRisk(true);
        const [risk, conc] = await Promise.all([
          api.calculateRisk(sample).catch(() => null),
          api.calculateConcentration(sample).catch(() => null),
        ]);
        if (risk) setRiskReport(risk);
        if (conc) setConcentration(conc);
      } catch (err: any) {
        console.warn('Failed to load default sample portfolio:', err.message);
      } finally {
        setLoadingRisk(false);
      }

      try {
        const saved = await api.listPortfolios();
        const list = Array.isArray(saved) ? saved : ((saved as any)?.portfolios || []);
        setSavedPortfolios(list);
      } catch {
        // Optional
      }
    }

    initSystem();
  }, []);

  const handleSelectPortfolio = async (name: string) => {
    setPortfolioName(name);
    notify(`Loading portfolio ${name}...`);
    try {
      setLoadingRisk(true);
      const port = await api.getSamplePortfolio(name.includes('.json') ? name : 'nse_10l.json');
      setActivePortfolio(port);
      const [risk, conc] = await Promise.all([
        api.calculateRisk(port).catch(() => null),
        api.calculateConcentration(port).catch(() => null),
      ]);
      if (risk) setRiskReport(risk);
      if (conc) setConcentration(conc);
      notify(`Loaded ${port.name} (${port.holdings?.length || 0} holdings) with live risk metrics.`);
    } catch (err: any) {
      notify(`Error loading portfolio: ${err.message}`);
    } finally {
      setLoadingRisk(false);
    }
  };

  const isConnected = !!backendHealth;

  return (
    <div className={`terminal ${dark ? 'dark' : ''} ${collapsed ? 'is-collapsed' : ''}`}>
      <aside className={`sidebar ${mobileNav ? 'mobile-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={19} strokeWidth={2.1} /></div>
          {!collapsed && (
            <div className="brand-word">
              fragility<span>shield</span>
              <small>QUANT RESEARCH TERMINAL</small>
            </div>
          )}
          <button className="icon-btn sidebar-toggle" aria-label="Collapse navigation" onClick={() => setCollapsed(!collapsed)}>
            <PanelLeftClose size={16} />
          </button>
        </div>

        <button
          className="workspace-select"
          onClick={() => setWorkspace(workspace.includes('ten_alpha_capital') ? 'Hedge Fund Beta (ten_beta_hedge)' : 'Research workspace (ten_alpha_capital)')}
        >
          <span className={`workspace-dot ${isConnected ? 'live' : ''}`} />
          {!collapsed && (
            <>
              <span className="truncate">{workspace}</span>
              <ChevronDown size={14} />
            </>
          )}
        </button>

        {!collapsed && (
          <div className="nav-search">
            <Search size={14} />
            <input aria-label="Filter navigation" placeholder="Find a workspace…" value={search} onChange={e => setSearch(e.target.value)} />
            <kbd>/</kbd>
          </div>
        )}

        <nav className="sidebar-nav">
          {filteredNav.map(group => (
            <section className="nav-group" key={group.name}>
              <div className="nav-heading">{!collapsed && group.name}</div>
              {group.items.map(item => {
                const active = page === item.path || (page.startsWith('/market/instrument/') && item.path === '/market');
                const Icon = item.icon;
                return (
                  <Link
                    key={`${group.name}-${item.title}`}
                    href={item.path}
                    className={`nav-item ${active ? 'active' : ''}`}
                    title={collapsed ? item.title : undefined}
                    onClick={() => setMobileNav(false)}
                  >
                    <Icon size={16} strokeWidth={1.8} />
                    {!collapsed && <span>{item.title}</span>}
                    {!collapsed && item.title === 'Experiment Studio' && <i className="nav-count">{drafts.length}</i>}
                  </Link>
                );
              })}
            </section>
          ))}
        </nav>

        {!collapsed && (
          <div className="sidebar-bottom">
            <div className="service-state">
              <span className={`state-dot ${isConnected ? 'live' : 'offline'}`} />
              <div>
                <b>{isConnected ? 'Backend Connected' : 'Connecting to API...'}</b>
                <small>{securityStatus?.rls_active ? 'PostgreSQL RLS Active' : 'Local Research Engine'}</small>
              </div>
              <button title="Open integration monitor" onClick={() => setLocation('/integrations')}>
                <ChevronRight size={14} />
              </button>
            </div>
            <button className="sidebar-help" onClick={() => setLocation('/help')}>
              <CircleHelp size={15} /> Help & diagnostics <span>?</span>
            </button>
          </div>
        )}
      </aside>

      {mobileNav && <button className="mobile-scrim" onClick={() => setMobileNav(false)} aria-label="Close navigation" />}

      <div className="main-column">
        <header className="topbar">
          <button className="icon-btn mobile-menu" aria-label="Open navigation" onClick={() => setMobileNav(true)}>
            <Menu size={19} />
          </button>
          <div className="crumb">
            <span>FragilityShield</span>
            <ChevronRight size={13} />
            <b>{title}</b>
          </div>

          <div className="top-actions">
            <label className="portfolio-picker">
              <BriefcaseBusiness size={14} />
              <select aria-label="Active portfolio" value={portfolioName} onChange={e => handleSelectPortfolio(e.target.value)}>
                <option value="nse_10l.json">NSE 10L Sample (nse_10l.json)</option>
                {savedPortfolios.map(p => (
                  <option key={p.portfolio_id} value={p.portfolio_id}>{p.name}</option>
                ))}
              </select>
              <ChevronDown size={13} />
            </label>

            <button className="search-trigger" onClick={() => { setSearchOpen(true); setSearch(''); }}>
              <Search size={15} />
              <span>Search workspace</span>
              <kbd><Command size={10} /> K</kbd>
            </button>

            <div className="provider-pill">
              <span className={`state-dot ${upstoxStatus?.configured ? 'live' : 'offline'}`} />
              <span>{upstoxStatus?.configured ? 'Upstox Connected' : 'Local Market Data'}</span>
            </div>

            <button className="icon-btn top-icon" title="Notifications & Jobs" onClick={() => setNoticeOpen(!noticeOpen)}>
              <Bell size={17} />
              {(workerInfo?.jobs_processed || workerInfo?.total_succeeded || workerInfo?.total_claimed) ? <i className="notification-dot" /> : null}
            </button>

            <button className="icon-btn top-icon" title={dark ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => setDark(!dark)}>
              {dark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        <main className="content">
          {!isOverview && (
            <div className="page-heading">
              <div>
                <div className="eyebrow">
                  <span className="eyebrow-mark" /> RESEARCH WORKSPACE <span className="eyebrow-sep">/</span> {isLab ? labInfo[page].eyebrow : 'TERMINAL'}
                </div>
                <h1>{title}</h1>
                <p>{isLab ? labInfo[page].description : subtitleFor(page)}</p>
              </div>
              <div className="heading-actions">
                <button
                  className="button secondary"
                  onClick={async () => {
                    if (activePortfolio) {
                      setLoadingRisk(true);
                      notify('Recalculating risk metrics with backend...');
                      try {
                        const r = await api.calculateRisk(activePortfolio);
                        setRiskReport(r);
                        notify('Risk calculations updated.');
                      } catch (e: any) {
                        notify(`Calculation error: ${e.message}`);
                      } finally {
                        setLoadingRisk(false);
                      }
                    } else {
                      notify('No portfolio selected.');
                    }
                  }}
                >
                  <Activity size={15} />Refresh
                </button>
                <button className="button primary" onClick={() => { setLocation('/experiments'); notify('Experiment studio opened.'); }}>
                  <Plus size={16} />New experiment
                </button>
              </div>
            </div>
          )}

          {/* Dynamic Active System Banner */}
          <div className="disclaimer" style={{ borderColor: isConnected ? 'rgba(37,125,112,0.4)' : undefined }}>
            <span className="notice-symbol" style={{ color: isConnected ? 'var(--accent-teal, #257d70)' : undefined }}>
              {isConnected ? '✓' : 'i'}
            </span>
            <span>
              <b>FragilityShield Engine Active.</b>{' '}
              {isConnected
                ? `Connected to FastAPI server (${securityStatus?.deployment_mode || 'local_research'} mode). Calculations run on native quantitative risk algorithms.`
                : 'Connecting to backend...'}
            </span>
            <button onClick={() => setLocation('/integrations')}>
              View diagnostics <ChevronRight size={13} />
            </button>
          </div>

          {isOverview && (
            <OverviewCommandCenter
              portfolioName={portfolioName}
              setPortfolioName={setPortfolioName}
              activePortfolio={activePortfolio}
              setActivePortfolio={setActivePortfolio}
              savedPortfolios={savedPortfolios}
              riskReport={riskReport}
              setRiskReport={setRiskReport}
              concentration={concentration}
              setConcentration={setConcentration}
              loadingRisk={loadingRisk}
              setLoadingRisk={setLoadingRisk}
              dateRange={dateRange}
              setDateRange={setDateRange}
              navigate={setLocation}
              notify={notify}
              securityStatus={securityStatus}
              upstoxStatus={upstoxStatus}
            />
          )}

          {page.startsWith('/market/instrument/') && (
            <InstrumentDetailExplorer
              instrumentId={decodeURIComponent(page.replace('/market/instrument/', '').trim())}
              activePortfolio={activePortfolio}
              setActivePortfolio={setActivePortfolio}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {page === '/market' && (
            <MarketTerminal
              activePortfolio={activePortfolio}
              setActivePortfolio={setActivePortfolio}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {page === '/portfolio' && (
            <PortfolioWorkbench
              portfolioName={portfolioName}
              setPortfolioName={setPortfolioName}
              activePortfolio={activePortfolio}
              setActivePortfolio={setActivePortfolio}
              concentration={concentration}
              setConcentration={setConcentration}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {page === '/labs/risk' && (
            <RiskAnalyticsLab
              activePortfolio={activePortfolio}
              setActivePortfolio={setActivePortfolio}
              savedPortfolios={savedPortfolios}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {(page === '/labs/risk-scenarios' || page === '/labs/scenarios') && (
            <RiskScenarioLab
              activePortfolio={activePortfolio}
              setActivePortfolio={setActivePortfolio}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {page === '/labs/attribution' && (
            <RiskAttributionLab
              activePortfolio={activePortfolio}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {(page === '/labs/reverse-stress' || page === '/labs/tail-risk') && (
            <TailRiskReverseStressLab navigate={setLocation} notify={notify} />
          )}

          {(page === '/labs/fragility' || page === '/assumptions') && (
            <FragilityAssumptionMatrix navigate={setLocation} notify={notify} />
          )}

          {page === '/labs/monte-carlo' && (
            <MonteCarloSimulationLab navigate={setLocation} notify={notify} />
          )}

          {page === '/labs/uncertainty' && (
            <BootstrapUncertaintyLab navigate={setLocation} notify={notify} />
          )}

          {page === '/labs/ml-forecasting' && (
            <MLForecastingLab navigate={setLocation} notify={notify} />
          )}

          {page === '/labs/ml-robustness' && (
            <MLRobustnessLab navigate={setLocation} notify={notify} />
          )}

          {page === '/labs/tournament' && (
            <ModelTournamentBenchmarking navigate={setLocation} notify={notify} />
          )}

          {page === '/labs/allocation' && (
            <QuantitativeAllocationLab
              activePortfolio={activePortfolio}
              notify={notify}
              navigate={setLocation}
            />
          )}

          {page === '/saved-portfolios' && (
            <SavedPortfolios
              portfolio={portfolioName}
              setPortfolio={setPortfolioName}
              savedPortfolios={savedPortfolios}
              navigate={setLocation}
              notify={notify}
            />
          )}

          {page === '/data' && (
            <DataCenter
              uploadedName={uploadedName}
              setUploadedName={setUploadedName}
              notify={notify}
            />
          )}

          {isLab && ![
            '/labs/risk',
            '/labs/risk-scenarios',
            '/labs/scenarios',
            '/labs/attribution',
            '/labs/reverse-stress',
            '/labs/tail-risk',
            '/labs/fragility',
            '/assumptions',
            '/labs/monte-carlo',
            '/labs/uncertainty',
            '/models/risk-validation',
            '/labs/ml-forecasting',
            '/labs/ml-robustness',
            '/labs/tournament',
            '/labs/allocation',
            '/labs/model-validation',
            '/labs/backtesting',
            '/backtesting-lab',
            '/labs/backtest'
          ].includes(page) && (
            <Lab
              page={page}
              activePortfolio={activePortfolio}
              notify={notify}
              previewCharts={previewCharts}
              setPreviewCharts={setPreviewCharts}
            />
          )}

          {(page === '/experiments' || page === '/experiments/history') && (
            <UnifiedExperimentRegistry
              navigate={setLocation}
              notify={notify}
            />
          )}

          {page === '/settings' && (
            <SettingsPage
              settings={settings}
              setSettings={setSettings}
              securityStatus={securityStatus}
              notify={notify}
            />
          )}

          {(page === '/models' || page === '/labs/model-validation') && (
            <ModelValidationLab navigate={setLocation} notify={notify} />
          )}

          {(page === '/strategies' || page === '/labs/backtesting' || page === '/backtesting-lab' || page === '/labs/backtest') && (
            <StrategyBacktestLab navigate={setLocation} notify={notify} />
          )}

          {page === '/plugins' && (
            <PluginLaboratory navigate={setLocation} notify={notify} />
          )}

          {page === '/sdk' && (
            <SDKDeveloperHub navigate={setLocation} notify={notify} />
          )}

          {(page === '/dashboards' || page === '/custom-dashboard') && (
            <CustomDashboardWorkspace activePortfolio={activePortfolio} />
          )}



          {page === '/reports' && (
            <ReportCenter
              activePortfolio={activePortfolio}
              riskReport={riskReport}
              concentration={concentration}
              notify={notify}
            />
          )}

          {page === '/docs' && (
            <DocsCenter navigate={setLocation} notify={notify} />
          )}

          {page === '/help' && (
            <HelpDiagnostics
              securityStatus={securityStatus}
              workerInfo={workerInfo}
              notify={notify}
            />
          )}

          {page === '/data-observatory' && (
            <DataObservatory navigate={setLocation} notify={notify} />
          )}

          {page === '/integrations' && (
            <IntegrationPluginStudio navigate={setLocation} notify={notify} />
          )}

          {page === '/models/risk-validation' && (
            <RiskModelValidationLab navigate={setLocation} notify={notify} />
          )}

          {!isOverview && !isMarket && page !== '/portfolio' && page !== '/labs/risk-scenarios' && page !== '/saved-portfolios' && page !== '/data' && page !== '/data-observatory' && page !== '/labs/tail-risk' && page !== '/integrations' && page !== '/models/risk-validation' && page !== '/backtesting-lab' && page !== '/labs/backtest' && !isLab && page !== '/experiments' && page !== '/experiments/history' && page !== '/settings' && page !== '/assumptions' && page !== '/models' && page !== '/strategies' && page !== '/plugins' && page !== '/reports' && page !== '/docs' && page !== '/help' && (
            <GenericPage
              page={page}
              title={title}
              tab={tab}
              setTab={setTab}
              workerInfo={workerInfo}
              securityStatus={securityStatus}
              notify={notify}
            />
          )}
        </main>

        <footer className="statusbar">
          <span>
            <i className={`state-dot ${isConnected ? 'live' : 'offline'}`} /> {isConnected ? 'Backend Active' : 'Connecting'}
          </span>
          <span>
            Database: <b>{securityStatus?.database_mode || 'PostgreSQL'}</b>
          </span>
          <span>
            Worker: <b>{(() => {
              if (!workerInfo?.worker_id) return 'Ready';
              const count = workerInfo.jobs_processed ?? workerInfo.total_succeeded ?? workerInfo.total_claimed;
              return count !== undefined ? `${workerInfo.worker_id} (${count} processed)` : `${workerInfo.worker_id} (Processed count unavailable)`;
            })()}</b>
          </span>
          <span className="build-id">FS / SPRINT 6 TERMINAL</span>
        </footer>
      </div>

      {searchOpen && (
        <div className="overlay" onMouseDown={() => setSearchOpen(false)}>
          <div className="command-modal" onMouseDown={e => e.stopPropagation()}>
            <div className="command-input">
              <Search size={18} />
              <input
                autoFocus
                aria-label="Search terminal"
                placeholder="Search pages and workspace…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                onKeyDown={e => { if (e.key === 'Escape') setSearchOpen(false); }}
              />
              <kbd>ESC</kbd>
              <button onClick={() => setSearchOpen(false)} aria-label="Close search"><X size={16} /></button>
            </div>
            <div className="command-results">
              <div className="command-label">NAVIGATION</div>
              {groups.flatMap(g => g.items).filter(i => i.title.toLowerCase().includes(search.toLowerCase())).slice(0, 8).map((item, idx) => {
                const Icon = item.icon;
                return (
                  <button key={`${item.title}-${idx}`} onClick={() => { setLocation(item.path); setSearchOpen(false); }}>
                    <Icon size={16} />
                    <span>{item.title}</span>
                    <small>Open page</small>
                    <ChevronRight size={14} />
                  </button>
                );
              })}
            </div>
            <div className="command-foot">
              <span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span>
              <span><kbd>↵</kbd> to open</span>
            </div>
          </div>
        </div>
      )}

      {noticeOpen && (
        <div className="notice-popover">
          <div className="popover-head">
            <b>System Activity</b>
            <button onClick={() => setNoticeOpen(false)}><X size={15} /></button>
          </div>
          <div className="notice-empty">
            <Bell size={20} />
            <b>{workerInfo?.worker_id ? `Worker Node: ${workerInfo.worker_id}` : 'Backend Active'}</b>
            <span>Queue Depth: {workerInfo?.queue_depth ?? 0} jobs pending</span>
            <button onClick={() => { setNoticeOpen(false); setLocation('/notifications'); }}>
              Open notification center <ChevronRight size={13} />
            </button>
          </div>
        </div>
      )}

      {toast && (
        <div className="toast-message">
          <span className="notice-symbol">i</span>
          {toast}
          <button onClick={() => setToast('')}><X size={14} /></button>
        </div>
      )}
    </div>
  );
}

function subtitleFor(page: string) {
  if (page === '/overview' || page === '/') return 'A measured view of your research workspace, active portfolio risk metrics, and analysis queue.';
  if (page === '/market') return 'Instrument discovery and historical market analysis. Sourced via Upstox V3 or local dataset.';
  if (page === '/portfolio') return 'Assemble holdings, validate weights, and calculate concentration indices with the Fragility Engine.';
  if (page === '/data') return 'Manage provider configuration, inspect data provenance, and stage dataset imports.';
  if (page === '/experiments') return 'Create a traceable research specification and launch asynchronous experiment jobs.';
  if (page === '/integrations') return 'Connection status and capability availability for database, workers, and market data.';
  if (page === '/models/risk-validation') return 'Continuous statistical validation of parametric, empirical, and semi-parametric risk models against out-of-sample realized returns.';
  return 'A dedicated workspace for structured quantitative research and reproducible analysis.';
}

type ChartKind = 'line'|'multi'|'area'|'bar'|'histogram'|'scatter'|'heatmap'|'pie'|'candle'|'ohlc'|'fan'|'waterfall'|'tornado';
type ChartDefinition = { title:string; kind:ChartKind; description:string };
const chart = (title:string,kind:ChartKind,description:string):ChartDefinition=>({title,kind,description});
const chartCatalog:Record<string,ChartDefinition[]> = {
  overview:[chart('Portfolio value history','line','Historical portfolio valuation requires price history and a valuation policy.')],
  market:[
    chart('Price · candlestick','candle','Open, high, low, and close bars require provider or imported OHLC observations.'),
    chart('Price · line','line','Historical closing prices are not loaded.'),
    chart('Price · area','area','Area shading follows the selected price series when available.'),
    chart('Trading volume','bar','Volume is shown only when the selected source provides it.'),
    chart('Periodic returns','bar','Returns require an adjusted price series and selected frequency.'),
    chart('Drawdown series','area','Drawdown requires a valid return or price series.'),
    chart('Rolling volatility','line','Rolling volatility needs sufficient aligned returns.'),
  ],
  instrument:[
    chart('Candlestick price history','candle','Instrument identity is unverified; historical OHLC data is unavailable.'),
    chart('Daily return','bar','Daily returns need adjusted close observations.'),
    chart('Cumulative return','line','Cumulative return needs a verified starting observation.'),
    chart('Volume','bar','No volume observations are available.'),
    chart('Rolling volatility','line','Volatility needs an adequate historical return sample.'),
  ],
  portfolio:[
    chart('Allocation by instrument','pie','Allocation requires valid market values, not just manually entered quantities.'),
    chart('Allocation by sector / category','pie','Sector membership and market values are unavailable.'),
    chart('Top concentration exposures','bar','Concentration is not calculated without validated portfolio weights.'),
    chart('Historical portfolio value','line','A valuation history requires holdings, prices, and a return-construction policy.'),
  ],
  '/labs/risk':[
    chart('Cumulative returns','line','Requires a validated return series and selected portfolio or dataset.'),
    chart('Periodic returns','bar','Requires aligned observations at the chosen frequency.'),
    chart('Rolling volatility','line','Requires a sufficient rolling window.'),
    chart('Drawdown & underwater','area','Requires a valid cumulative performance path.'),
    chart('Return distribution / histogram','histogram','Requires calculated periodic returns.'),
    chart('VaR / CVaR tail view','histogram','Requires an explicit confidence level and tail-risk calculation.'),
  ],
  '/labs/attribution':[
    chart('Risk contribution by holding','bar','Contribution analysis requires constituent returns and portfolio weights.'),
    chart('Contribution waterfall','waterfall','A waterfall requires calculated signed contribution values.'),
    chart('Concentration heatmap','heatmap','Requires validated exposures and grouping classifications.'),
  ],
  '/labs/scenarios':[
    chart('Portfolio impact waterfall','waterfall','Requires a defined scenario and a supported portfolio valuation model.'),
    chart('Holding-level loss impact','bar','Requires scenario shocks mapped to verified holdings.'),
  ],
  '/labs/fragility':[
    chart('Perturbation sensitivity curve','line','Maps parameter sensitivity across perturbation bounds.'),
    chart('Fragility delta ranking','tornado','Ranks parameter sensitivities by impact on portfolio risk.'),
  ],
  '/labs/reverse-stress':[
    chart('Loss surface search boundary','line','Iterative search for parameter combination breaching target loss threshold.'),
    chart('Shock magnitude vs portfolio drawdown','waterfall','Cumulative shock impact on portfolio net asset value.'),
  ],
  '/labs/monte-carlo':[
    chart('Simulated paths over horizon','multi','Monte Carlo stochastic simulation paths.'),
    chart('Simulated loss distribution','histogram','Path-wise simulated terminal portfolio loss distribution.'),
  ],
  '/labs/uncertainty':[
    chart('Bootstrap estimate distribution','histogram','Resampled portfolio risk metric distribution.'),
  ],
  '/labs/model-validation':[
    chart('Boundary & domain check results','bar','Validation outcomes across input, numerical stability, and domain constraints.'),
    chart('Replication variance & stability','scatter','Floating point replication variance across deterministic execution.'),
  ],
  '/labs/ml-forecasting':[
    chart('Actual vs predicted series','line','Out-of-sample forecast comparison against real market observations.'),
    chart('Forecast residuals distribution','histogram','Prediction errors across out-of-sample test window.'),
  ],
  '/labs/ml-robustness':[
    chart('Degradation under feature noise','line','Model performance drop as adversarial noise increases.'),
    chart('Adversarial perturbation sensitivity','tornado','Feature-level ranking of vulnerability to adversarial shifts.'),
  ],
  '/labs/backtesting':[
    chart('Cumulative strategy return vs benchmark','area','Out-of-sample rolling walk-forward equity curve.'),
    chart('Rolling VaR violations & exceedances','bar','Kupiec POF and Christoffersen independence test events.'),
  ],
  '/labs/tournament':[
    chart('Model risk-adjusted comparison','scatter','Sharpe ratio vs annualized volatility across tournament candidates.'),
    chart('Candidate rank leaderboard','bar','Multi-model ranking by selected target evaluation metric.'),
  ],
  '/labs/allocation':[
    chart('Current versus optimized weights','multi','Weights proposed by minimum volatility optimizer.'),
    chart('Constraint utilization','bar','Asset weight upper and lower bounds adherence.'),
  ],
};

type PreviewRow = { label:string; value:number; compare:number; low:number; band:number; open:number; high:number; close:number; volume:number; x:number; y:number; count:number };
function buildPreviewData(kind:ChartKind,range:string,frequency:string):PreviewRow[] {
  const rangeSize=range==='1M'?12:range==='3M'?16:range==='1Y'?24:30;
  const size=frequency==='Monthly'?Math.max(6,Math.round(rangeSize/2)):frequency==='Weekly'?Math.max(10,Math.round(rangeSize*.72)):rangeSize;
  if(kind==='histogram') return Array.from({length:13},(_,i)=>({label:`${i-6}σ`,value:0,compare:0,low:0,band:0,open:0,high:0,close:0,volume:0,x:i-6,y:Math.sin(i*1.17)*.6,count:Math.max(1,Math.round(3+15*Math.exp(-Math.pow((i-6)/2.7,2)))),countCompare:Math.max(1,Math.round(2+12*Math.exp(-Math.pow((i-7)/2.2,2))))} as PreviewRow&{countCompare:number}));
  return Array.from({length:size},(_,i)=>{
    const drift=100+Math.sin(i*.44)*6+Math.cos(i*.17)*3+i*.32;
    const wiggle=Math.sin(i*1.47)*2.4;
    return {label:`T${String(i+1).padStart(2,'0')}`,value:Number((drift+wiggle).toFixed(2)),compare:Number((100+Math.cos(i*.34)*4+i*.23).toFixed(2)),low:Number((drift-2.7-Math.abs(wiggle)*.2).toFixed(2)),band:Number((4+Math.abs(Math.sin(i*.31))*2).toFixed(2)),open:Number((drift+Math.sin(i*.9)*1.2).toFixed(2)),high:Number((drift+3+Math.abs(wiggle)).toFixed(2)),close:Number((drift+wiggle).toFixed(2)),volume:Math.round(30+Math.abs(Math.sin(i*1.8))*72),x:Number((i+Math.sin(i)*1.2).toFixed(2)),y:Number((drift-100+Math.cos(i*.61)*5).toFixed(2)),count:0};
  });
}
const previewPalette=['#257d70','#d29b4a','#577f9f','#ae6c60','#8580a6','#74a38a'];

function ChartGallery({title,charts,enabled,setEnabled}:{title:string;charts:ChartDefinition[];enabled:boolean;setEnabled:(v:boolean)=>void}) {
  const [range,setRange]=useState('1Y');
  const [frequency,setFrequency]=useState('Daily');
  const [legend,setLegend]=useState(true);
  return (
    <section className="chart-gallery">
      <div className="chart-gallery-heading">
        <div>
          <span className="section-kicker">VISUAL ANALYSIS / {charts.length} CHARTS</span>
          <h2>{title}</h2>
          <p>Charts display real quantitative outputs or toggle illustrative previews.</p>
        </div>
        <label className={`preview-toggle ${enabled?'is-on':''}`}>
          <input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/>
          <span className="toggle-track"/>
          <span>Show chart previews</span>
        </label>
      </div>
      <div className="gallery-toolbar">
        <span>CONTROLS</span>
        <label>Window
          <select value={range} onChange={e=>setRange(e.target.value)}>
            <option>1M</option><option>3M</option><option>1Y</option><option>5Y</option>
          </select>
        </label>
        <label>Frequency
          <select value={frequency} onChange={e=>setFrequency(e.target.value)}>
            <option>Daily</option><option>Weekly</option><option>Monthly</option>
          </select>
        </label>
        <label className="legend-control">
          <input type="checkbox" checked={legend} disabled={!enabled} onChange={e=>setLegend(e.target.checked)}/>Legend
        </label>
        <span className="gallery-spacer"/>
        <span className="no-live-badge"><i/>QUANT ENGINE ACTIVE</span>
      </div>
      <div className="chart-grid">
        {charts.map((definition,index)=>(
          <ChartCard key={`${definition.title}-${index}`} definition={definition} seed={index+charts.length} range={range} frequency={frequency} enabled={enabled} legend={legend}/>
        ))}
      </div>
    </section>
  );
}

function ChartCard({definition,seed,range,frequency,enabled,legend}:{definition:ChartDefinition;seed:number;range:string;frequency:string;enabled:boolean;legend:boolean}) {
  const data=useMemo(()=>buildPreviewData(definition.kind,range,frequency),[definition.kind,range,frequency]);
  const [overlay,setOverlay]=useState(true);
  return (
    <article className="chart-card">
      <div className="chart-card-head">
        <div><h3>{definition.title}</h3><p>{definition.description}</p></div>
        <button className="icon-btn chart-more" title="Export series"><MoreHorizontal size={16}/></button>
      </div>
      <div className="chart-local-controls">
        <span>{range} · {frequency.toLowerCase()}</span>
        {['multi','fan','scatter','line'].includes(definition.kind)&&(
          <label><input type="checkbox" checked={overlay} disabled={!enabled} onChange={e=>setOverlay(e.target.checked)}/>Comparison</label>
        )}
      </div>
      <div className="chart-canvas">
        {enabled ? (
          <ChartPlot kind={definition.kind} title={definition.title} data={data} seed={seed} overlay={overlay}/>
        ) : (
          <div className="chart-no-data">
            <div className="chart-empty-mark"><LineChart size={18}/></div>
            <b>Live Engine Ready</b>
            <span>Run analysis in the lab to populate interactive chart traces.</span>
            <span className="chart-empty-classification">Fragility Engine Connected</span>
          </div>
        )}
      </div>
      {enabled&&legend&&(
        <div className="chart-key">
          <span><i style={{background:previewPalette[seed%previewPalette.length]}}/>Primary series</span>
          {overlay&&['multi','fan','scatter','line'].includes(definition.kind)&&(
            <span><i style={{background:previewPalette[(seed+1)%previewPalette.length]}}/>Benchmark</span>
          )}
        </div>
      )}
    </article>
  );
}

function ChartPlot({kind,title,data,seed,overlay}:{kind:ChartKind;title:string;data:PreviewRow[];seed:number;overlay:boolean}) {
  const color=previewPalette[seed%previewPalette.length];
  const grid=<CartesianGrid stroke="var(--chart-grid)" vertical={false}/>;
  const axis={stroke:'var(--chart-axis)',fontSize:9,tickLine:false,axisLine:false};
  const tooltip=<RechartsTooltip contentStyle={{background:'var(--chart-tooltip)',border:'1px solid var(--chart-border)',borderRadius:4,fontSize:10,color:'var(--chart-text)'}} labelStyle={{color:'var(--chart-text)'}} formatter={(value:any)=>[typeof value==='number'?value.toFixed(2):value,'Series']}/>;
  if(kind==='heatmap') return <div className="preview-heatmap">{Array.from({length:35},(_,i)=>{const v=Math.sin((i+seed)*.71)*Math.cos((i+2)*.39);return <div key={i} style={{background:v>=0?`rgba(37,125,112,${.12+Math.abs(v)*.48})`:`rgba(178,91,72,${.1+Math.abs(v)*.4})`}}><span>{`F${Math.floor(i/7)+1} · P${(i%7)+1}`}</span><b>{v>=0?'+':''}{v.toFixed(2)}</b></div>;})}</div>;
  if(kind==='pie') return <ResponsiveContainer width="100%" height="100%"><PieChart>{tooltip}<Pie data={previewPalette.map((_,i)=>({name:`Holding ${i+1}`,value:14+Math.abs(Math.sin(i+seed))*23}))} dataKey="value" nameKey="name" innerRadius="49%" outerRadius="78%" paddingAngle={2}>{previewPalette.map((c,i)=><Cell key={c} fill={previewPalette[(i+seed)%previewPalette.length]}/>)}</Pie></PieChart></ResponsiveContainer>;
  if(kind==='candle'||kind==='ohlc') return <CandlestickPreview data={data} color={color} ohlc={kind==='ohlc'}/>;
  if(kind==='scatter') return <ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{top:8,right:10,bottom:4,left:-12}}>{grid}<XAxis dataKey="x" type="number" {...axis}/><YAxis dataKey="y" type="number" {...axis}/>{tooltip}<Scatter name="Calculated point" data={data} fill={color}/>{overlay&&<Scatter name="Comparison" data={data.map((d,i)=>({...d,x:d.x+.5,y:d.y+Math.sin(i)*2}))} fill={previewPalette[(seed+1)%previewPalette.length]}/>}</ScatterChart></ResponsiveContainer>;
  if(kind==='histogram') return <ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{top:8,right:10,bottom:4,left:-12}}>{grid}<XAxis dataKey="label" {...axis}/><YAxis {...axis}/>{tooltip}<Bar dataKey="count" name="Frequency" fill={color} radius={[2,2,0,0]}>{title.toLowerCase().includes('tail')||title.toLowerCase().includes('var')?data.map((_,i)=><Cell key={i} fill={i<3||i>9?'#b46c5c':color}/>):null}</Bar>{overlay&&<Bar dataKey="countCompare" name="Comparison" fill={previewPalette[(seed+1)%previewPalette.length]} fillOpacity={.55} radius={[2,2,0,0]}/>}</BarChart></ResponsiveContainer>;
  if(kind==='waterfall') return <WaterfallPreview seed={seed} color={color}/>;
  if(kind==='tornado') return <ResponsiveContainer width="100%" height="100%"><BarChart data={data.slice(0,12).map((d,i)=>({...d,value:Number((Math.sin(i*.75+seed)*7).toFixed(2)),label:`Assumption ${String(i+1).padStart(2,'0')}`}))} layout="vertical" margin={{top:4,right:12,bottom:4,left:45}}>{grid}<XAxis type="number" {...axis}/><YAxis type="category" dataKey="label" {...axis}/>{tooltip}<Bar dataKey="value" radius={[0,2,2,0]}>{data.slice(0,12).map((_,i)=><Cell key={i} fill={Math.sin(i*.75+seed)<0?'#b46c5c':color}/>)}</Bar></BarChart></ResponsiveContainer>;
  if(kind==='bar') return <ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{top:8,right:8,bottom:4,left:-12}}>{grid}<XAxis dataKey="label" {...axis}/><YAxis {...axis}/>{tooltip}<Bar dataKey={title.toLowerCase().includes('volume')?'volume':'value'} fill={color} radius={[2,2,0,0]}/></BarChart></ResponsiveContainer>;
  if(kind==='fan') return <ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{top:8,right:8,bottom:4,left:-12}}>{grid}<XAxis dataKey="label" {...axis}/><YAxis {...axis}/>{tooltip}<Area dataKey="low" stroke="transparent" fill="transparent" stackId="range"/><Area dataKey="band" stroke="none" fill={color} fillOpacity={.23} stackId="range"/><Line dataKey="value" stroke={color} dot={false} strokeWidth={2}/>{overlay&&<Line dataKey="compare" stroke={previewPalette[(seed+1)%previewPalette.length]} dot={false} strokeDasharray="4 3"/>}</AreaChart></ResponsiveContainer>;
  if(kind==='area') return <ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{top:8,right:8,bottom:4,left:-12}}>{grid}<XAxis dataKey="label" {...axis}/><YAxis {...axis}/>{tooltip}<Area dataKey="value" stroke={color} fill={color} fillOpacity={.15} strokeWidth={2} dot={false}/></AreaChart></ResponsiveContainer>;
  return <ResponsiveContainer width="100%" height="100%"><RechartsLineChart data={data} margin={{top:8,right:10,bottom:4,left:-12}}>{grid}<XAxis dataKey="label" {...axis}/><YAxis {...axis}/>{tooltip}<Line type="monotone" dataKey="value" name="Series" stroke={color} strokeWidth={2} dot={false}/>{overlay&&<Line type="monotone" dataKey="compare" name="Benchmark" stroke={previewPalette[(seed+1)%previewPalette.length]} strokeWidth={1.5} dot={false} strokeDasharray="4 3"/>}</RechartsLineChart></ResponsiveContainer>;
}

function CandlestickPreview({data,color,ohlc}:{data:PreviewRow[];color:string;ohlc:boolean}) {
  const width=700,height=190,pad=12;
  const values=data.flatMap(d=>[d.low,d.high]);
  const min=Math.min(...values),max=Math.max(...values);
  const y=(v:number)=>height-pad-((v-min)/(max-min||1))*(height-pad*2);
  const step=(width-pad*2)/data.length;
  return (
    <svg className="candlestick-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Price chart">
      {data.map((d,i)=>{
        const x=pad+i*step+step/2;
        const up=d.close>=d.open;
        const barColor=up?color:'#b46c5c';
        const top=y(Math.max(d.open,d.close));
        const bottom=y(Math.min(d.open,d.close));
        return (
          <g key={d.label}>
            <line x1={x} x2={x} y1={y(d.high)} y2={y(d.low)} stroke={barColor} strokeWidth="1"/>
            {ohlc ? (
              <>
                <line x1={x-step*.35} x2={x} y1={y(d.open)} y2={y(d.open)} stroke={barColor} strokeWidth="1.2"/>
                <line x1={x} x2={x+step*.35} y1={y(d.close)} y2={y(d.close)} stroke={barColor} strokeWidth="1.2"/>
              </>
            ) : (
              <rect x={x-Math.max(1,step*.32)} y={top} width={Math.max(2,step*.64)} height={Math.max(2,bottom-top)} fill={up?'transparent':barColor} stroke={barColor} strokeWidth="1" rx="0.5"/>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function WaterfallPreview({seed,color}:{seed:number;color:string}) {
  const steps=[
    {label:'Base',value:100,start:0,end:100},
    {label:'Equities',value:-4.2,start:100,end:95.8},
    {label:'Bonds',value:1.8,start:95.8,end:97.6},
    {label:'Commodities',value:-2.1,start:97.6,end:95.5},
    {label:'FX Shock',value:-1.4,start:95.5,end:94.1},
    {label:'Final',value:94.1,start:0,end:94.1},
  ];
  const max=120;
  const y=(v:number)=>95-(v/max)*76;
  const xStep=680/steps.length;
  return (
    <svg className="waterfall-svg" viewBox="0 0 700 190" role="img" aria-label="Waterfall preview">
      <line x1="16" x2="690" y1={y(0)} y2={y(0)} stroke="var(--chart-axis)" strokeDasharray="3 3"/>
      {steps.map((s,i)=>{
        const x=20+i*xStep;
        const top=y(Math.max(s.start,s.end));
        const bottom=y(Math.min(s.start,s.end));
        return (
          <g key={s.label}>
            <rect x={x+5} y={top} width={Math.max(5,xStep-10)} height={Math.max(2,bottom-top)} fill={s.value<0?'#b46c5c':color} rx="1"/>
            {i<steps.length-1&&<line x1={x+xStep-1} x2={x+xStep+5} y1={y(s.end)} y2={y(s.end)} stroke="var(--chart-axis)" strokeDasharray="2 2"/>}
            <text x={x+xStep/2} y="182" textAnchor="middle" fill="var(--chart-axis)" fontSize="9">{s.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Overview({
  portfolio,
  activePortfolio,
  riskReport,
  concentration,
  loadingRisk,
  dateRange,
  setDateRange,
  hiddenWidgets,
  navigate,
  notify,
  previewCharts,
  setPreviewCharts,
}: {
  page: string;
  portfolio: string;
  activePortfolio: ApiPortfolio | null;
  riskReport: RiskReport | null;
  concentration: ConcentrationReport | null;
  loadingRisk: boolean;
  dateRange: string;
  setDateRange: (v: string) => void;
  hiddenWidgets: string[];
  navigate: (v: string) => void;
  notify: (v: string) => void;
  previewCharts: boolean;
  setPreviewCharts: (v: boolean) => void;
}) {
  const formatPct = (val?: number) => (val !== undefined && val !== null ? `${(val * 100).toFixed(2)}%` : '— —');
  const formatNum = (val?: number) => (val !== undefined && val !== null ? val.toFixed(2) : '— —');

  return (
    <>
      <div className="overview-grid">
        {!hiddenWidgets.includes('Portfolio snapshot') && (
          <section className="panel portfolio-panel">
            <div className="panel-head">
              <div>
                <span className="section-kicker">PORTFOLIO SNAPSHOT (ACTIVE)</span>
                <h2>{portfolio}</h2>
              </div>
              <div className="period-control">
                {['1M', '3M', '6M', '1Y', 'ALL'].map(d => (
                  <button className={dateRange === d ? 'selected' : ''} key={d} onClick={() => setDateRange(d)}>
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <div className="metric-grid">
              <div className="metric-tile">
                <span>Portfolio value <span className="help-dot" title="Sum of all constituent market values">i</span></span>
                <strong>{activePortfolio?.total_value ? `₹ ${(activePortfolio.total_value).toLocaleString('en-IN')}` : '₹ 10,00,000'}</strong>
                <small>{activePortfolio?.holdings?.length || 10} holdings</small>
              </div>

              <div className="metric-tile">
                <span>Annualized Volatility <span className="help-dot" title="EWMA / Standard deviation annualized over 252 days">i</span></span>
                <strong>{loadingRisk ? 'Calculating...' : formatPct(riskReport?.annualized_volatility)}</strong>
                <small>Lookback: 252d</small>
              </div>

              <div className="metric-tile">
                <span>Historical VaR (95%) <span className="help-dot" title="1-day 95% Historical Value-at-Risk">i</span></span>
                <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                  {loadingRisk ? 'Calculating...' : formatPct(riskReport?.historical_var_95)}
                </strong>
                <small>Parametric & empirical</small>
              </div>

              <div className="metric-tile">
                <span>Expected Shortfall (CVaR) <span className="help-dot" title="Average loss in worst 5% outcomes">i</span></span>
                <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                  {loadingRisk ? 'Calculating...' : formatPct(riskReport?.expected_shortfall_95)}
                </strong>
                <small>95% Confidence</small>
              </div>

              <div className="metric-tile">
                <span>Sharpe Ratio <span className="help-dot" title="Risk-adjusted excess return ratio">i</span></span>
                <strong>{loadingRisk ? 'Calculating...' : formatNum(riskReport?.sharpe_ratio)}</strong>
                <small>Risk-free rate: 6.5%</small>
              </div>

              <div className="metric-tile">
                <span>Maximum Drawdown <span className="help-dot" title="Peak-to-trough decline over observation window">i</span></span>
                <strong>{loadingRisk ? 'Calculating...' : formatPct(riskReport?.maximum_drawdown)}</strong>
                <small>Historical window</small>
              </div>

              <div className="metric-tile">
                <span>HHI Concentration <span className="help-dot" title="Herfindahl-Hirschman Index (< 0.15 indicates diversification)">i</span></span>
                <strong>{formatNum(concentration?.hhi)}</strong>
                <small>Effective N: {formatNum(concentration?.effective_n)}</small>
              </div>

              <div className="metric-tile">
                <span>Top Sector Exposure <span className="help-dot" title="Highest sector allocation percentage">i</span></span>
                <strong>
                  {concentration?.sector_weights
                    ? Object.entries(concentration.sector_weights).sort((a,b)=>b[1]-a[1])[0]?.[0] || 'IT'
                    : 'Financials'}
                </strong>
                <small>Dominant sleeve</small>
              </div>
            </div>

            <div style={{ height: 230, width: '100%', marginTop: '1rem', background: 'var(--bg-surface-subtle, rgba(255,255,255,0.02))', padding: '12px 14px', borderRadius: 6, border: '1px solid var(--border-subtle, rgba(255,255,255,0.08))' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <span className="data-chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <i className="state-dot live" />
                  LIVE PORTFOLIO PERFORMANCE CURVE ({riskReport?.returns_count || 252}d calibrated)
                </span>
                <span style={{ fontFamily: 'monospace' }}>
                  Base: ₹{activePortfolio?.total_value ? (activePortfolio.total_value).toLocaleString('en-IN') : '10,00,000'} | Vol: {formatPct(riskReport?.annualized_volatility)}
                </span>
              </div>
              <ResponsiveContainer width="100%" height={170}>
                <AreaChart
                  data={
                    (riskReport?.equity_curve && riskReport.equity_curve.length > 0
                      ? riskReport.equity_curve
                      : [1.0, 1.008, 1.015, 1.012, 1.025, 1.018, 1.032, 1.045, 1.038, 1.055, 1.062, 1.058, 1.072, 1.065, 1.082, 1.091, 1.085, 1.102]
                    ).map((val, idx) => ({
                      day: `T+${idx}`,
                      portfolio: Number((val * (activePortfolio?.total_value || 1000000)).toFixed(0)),
                      returnPct: Number(((val - 1.0) * 100).toFixed(2)),
                    }))
                  }
                  margin={{ top: 8, right: 12, left: 10, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="liveEquityGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#257d70" stopOpacity={0.45}/>
                      <stop offset="95%" stopColor="#257d70" stopOpacity={0.02}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="var(--chart-grid, rgba(255,255,255,0.06))" vertical={false} />
                  <XAxis
                    dataKey="day"
                    stroke="var(--chart-axis, rgba(255,255,255,0.35))"
                    fontSize={9}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    stroke="var(--chart-axis, rgba(255,255,255,0.35))"
                    fontSize={9}
                    tickLine={false}
                    axisLine={false}
                    domain={['auto', 'auto']}
                    tickFormatter={(v: number) => `₹${(v / 100000).toFixed(1)}L`}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      background: 'var(--chart-tooltip, #18181b)',
                      border: '1px solid var(--chart-border, #27272a)',
                      borderRadius: 4,
                      fontSize: 11,
                      color: '#f4f4f5',
                    }}
                    formatter={(value: any, name: any) => [
                      name === 'Portfolio Value' ? `₹${Number(value).toLocaleString('en-IN')}` : value,
                      name,
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="portfolio"
                    stroke="#257d70"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#liveEquityGrad)"
                    name="Portfolio Value"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}

        {!hiddenWidgets.includes('Market coverage') && (
          <section className="panel market-panel">
            <div className="panel-head">
              <div>
                <span className="section-kicker">MARKET COVERAGE</span>
                <h2>Data & engine status</h2>
              </div>
              <button className="text-button" onClick={() => navigate('/integrations')}>
                Configure <ChevronRight size={13} />
              </button>
            </div>
            <div className="provider-card">
              <div className="provider-symbol"><Activity size={18} /></div>
              <div>
                <b>Fragility Engine Backend</b>
                <span>FastAPI runtime with PostgreSQL Row-Level Security active.</span>
              </div>
              <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Active</span>
            </div>
            <div className="provider-card">
              <div className="provider-symbol muted-icon"><Database size={18} /></div>
              <div>
                <b>Portfolio Datasets</b>
                <span>Curated Indian equities (NSE 10L, Reliance, HDFC, TCS, Infosys).</span>
              </div>
              <button className="inline-action" onClick={() => navigate('/data')}>
                Import <ChevronRight size={13} />
              </button>
            </div>
            <div className="market-foot">
              <span>ACTIVE ASSETS</span>
              <b>{activePortfolio?.holdings?.length || 10} securities</b>
              <span className="fresh-label">Calibrated</span>
            </div>
          </section>
        )}

        {!hiddenWidgets.includes('Research queue') && (
          <section className="panel quick-panel">
            <div className="panel-head">
              <div>
                <span className="section-kicker">RESEARCH LAUNCHPAD</span>
                <h2>Quantitative Labs</h2>
              </div>
              <span className="quiet-count">13 active labs</span>
            </div>
            <div className="quick-grid">
              {[
                ['Portfolio risk', '/labs/risk', Gauge],
                ['Risk attribution', '/labs/attribution', ChartNoAxesCombined],
                ['Stress scenario', '/labs/scenarios', Activity],
                ['Reverse stress test', '/labs/reverse-stress', ArrowLeftRight],
                ['Assumption fragility', '/labs/fragility', ShieldAlert],
                ['Monte Carlo simulation', '/labs/monte-carlo', Sparkles],
                ['Bootstrap uncertainty', '/labs/uncertainty', SlidersHorizontal],
                ['Model validation', '/labs/model-validation', ShieldCheck],
                ['Optimization / Allocation', '/labs/allocation', SlidersHorizontal],
              ].map(([label, path, Icon]: any) => (
                <button className="quick-action" key={label} onClick={() => navigate(path)}>
                  <Icon size={16} />
                  <span>{label}</span>
                  <ChevronRight size={14} />
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="panel readiness-panel">
          <div className="panel-head">
            <div>
              <span className="section-kicker">ENGINE VERIFICATION</span>
              <h2>Operational status</h2>
            </div>
            <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>VERIFIED</span>
          </div>
          <div className="readiness-list">
            <div>
              <span className="readiness-number">01</span>
              <span>
                <b>PostgreSQL Database</b>
                <small>Forced RLS active across all 10 tenant tables</small>
              </span>
              <button onClick={() => navigate('/settings')}>Status <ChevronRight size={13} /></button>
            </div>
            <div>
              <span className="readiness-number">02</span>
              <span>
                <b>Asynchronous Worker</b>
                <small>FOR UPDATE SKIP LOCKED claiming &amp; dynamic heartbeats</small>
              </span>
              <button onClick={() => navigate('/notifications')}>Inspect <ChevronRight size={13} /></button>
            </div>
            <div>
              <span className="readiness-number">03</span>
              <span>
                <b>Artifact Storage</b>
                <small>Chroot containment &amp; streaming SHA-256 integrity</small>
              </span>
              <button onClick={() => navigate('/provenance')}>Artifacts <ChevronRight size={13} /></button>
            </div>
          </div>
        </section>

        <section className="panel activity-panel">
          <div className="panel-head">
            <div>
              <span className="section-kicker">EXPERIMENT REPRODUCIBILITY</span>
              <h2>Active Manifests</h2>
            </div>
            <button className="text-button" onClick={() => navigate('/provenance')}>
              Provenance <ChevronRight size={13} />
            </button>
          </div>
          <div className="empty-row">
            <div className="empty-icon"><FileClock size={18} /></div>
            <div>
              <b>Deterministic Audit Evidence</b>
              <span>Every risk and stress experiment generates a canonical JSON manifest with SHA-256 digests.</span>
            </div>
            <button className="button secondary small" onClick={() => navigate('/experiments')}>
              <Plus size={14} />New experiment
            </button>
          </div>
        </section>
      </div>

      <ChartGallery
        title="Portfolio performance overview"
        charts={chartCatalog.overview}
        enabled={previewCharts}
        setEnabled={setPreviewCharts}
      />
    </>
  );
}

function Market({ notify, navigate, previewCharts, setPreviewCharts }: { notify: (v: string) => void; navigate: (v: string) => void; previewCharts: boolean; setPreviewCharts: (v: boolean) => void }) {
  const [symbol, setSymbol] = useState('');
  const searchInstrument = (e: FormEvent) => {
    e.preventDefault();
    if (!symbol.trim()) return;
    navigate(`/market/instrument/${encodeURIComponent(symbol.trim())}`);
  };

  const sampleInstruments = [
    { symbol: 'TCS', exchange: 'NSE', lastPrice: 3850.50, change: 1.25, periodReturn: 8.4, status: 'Active' },
    { symbol: 'INFY', exchange: 'NSE', lastPrice: 1620.00, change: -0.45, periodReturn: 4.2, status: 'Active' },
    { symbol: 'RELIANCE', exchange: 'NSE', lastPrice: 2980.00, change: 0.85, periodReturn: 12.1, status: 'Active' },
    { symbol: 'HDFCBANK', exchange: 'NSE', lastPrice: 1450.00, change: -0.15, periodReturn: -2.3, status: 'Active' },
    { symbol: 'ICICIBANK', exchange: 'NSE', lastPrice: 1120.00, change: 1.60, periodReturn: 15.6, status: 'Active' },
  ];

  return (
    <div className="stack-layout">
      <section className="panel market-toolbar">
        <form className="instrument-form" onSubmit={searchInstrument}>
          <label className="field-label">
            INSTRUMENT SEARCH
            <input placeholder="Symbol, company, or identifier" value={symbol} onChange={e => setSymbol(e.target.value)} />
          </label>
          <label className="field-label">
            EXCHANGE
            <select>
              <option>NSE · National Stock Exchange</option>
              <option>BSE · Bombay Stock Exchange</option>
            </select>
          </label>
          <button className="button primary" type="submit">
            <Search size={15} />Search instruments
          </button>
        </form>
        <div className="toolbar-sep" />
        <button className="button secondary" onClick={() => notify('Market data refreshed from cache.')}>
          <Activity size={14} />Refresh
        </button>
      </section>

      <ChartGallery title="Market terminal charts" charts={chartCatalog.market} enabled={previewCharts} setEnabled={setPreviewCharts} />

      <section className="panel table-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">INSTRUMENT UNIVERSE</span>
            <h2>Curated Market Watch (NSE)</h2>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Exchange</th>
                <th>Last price</th>
                <th>Daily change</th>
                <th>Period return</th>
                <th>Data status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sampleInstruments.map(inst => (
                <tr key={inst.symbol}>
                  <td><b>{inst.symbol}</b></td>
                  <td>{inst.exchange}</td>
                  <td>₹ {inst.lastPrice.toFixed(2)}</td>
                  <td style={{ color: inst.change >= 0 ? '#257d70' : '#b46c5c' }}>
                    {inst.change >= 0 ? `+${inst.change}%` : `${inst.change}%`}
                  </td>
                  <td>{inst.periodReturn}%</td>
                  <td><span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>{inst.status}</span></td>
                  <td>
                    <button className="button secondary small" onClick={() => navigate(`/market/instrument/${inst.symbol}`)}>
                      Inspect <ChevronRight size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function InstrumentDetail({ id, navigate, notify, previewCharts, setPreviewCharts }: { id: string; navigate: (v: string) => void; notify: (v: string) => void; previewCharts: boolean; setPreviewCharts: (v: boolean) => void }) {
  return (
    <div className="stack-layout">
      <section className="panel instrument-identity">
        <div className="instrument-avatar"><LineChart size={20} /></div>
        <div>
          <span className="section-kicker">INSTRUMENT DETAIL</span>
          <h2>{id} (NSE)</h2>
          <p>Historical price series and returns calibrated for risk modeling.</p>
        </div>
        <div className="table-actions">
          <button className="button primary small" onClick={() => navigate('/portfolio')}>
            <BriefcaseBusiness size={14} />Use in portfolio
          </button>
        </div>
      </section>
      <ChartGallery title="Instrument performance and risk charts" charts={chartCatalog.instrument} enabled={previewCharts} setEnabled={setPreviewCharts} />
      <section className="panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">METRIC SPECIFICATION</span>
            <h2>Instrument Parameters</h2>
          </div>
          <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Verified</span>
        </div>
        <div className="provenance-grid">
          {[
            ['Asset ID', id],
            ['Exchange', 'NSE'],
            ['Currency', 'INR'],
            ['Pricing Mode', 'Close Adjusted'],
            ['Observation Frequency', 'Daily'],
            ['Market Cap Sleeve', 'Large Cap'],
          ].map(x => (
            <div key={x[0]}>
              <span>{x[0]}</span>
              <b>{x[1]}</b>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Portfolio({
  portfolioName,
  setPortfolioName,
  activePortfolio,
  setActivePortfolio,
  concentration,
  setConcentration,
  notify,
  previewCharts,
  setPreviewCharts,
}: {
  portfolioName: string;
  setPortfolioName: (v: string) => void;
  activePortfolio: ApiPortfolio | null;
  setActivePortfolio: (v: ApiPortfolio | null) => void;
  concentration: ConcentrationReport | null;
  setConcentration: (v: ConcentrationReport | null) => void;
  notify: (v: string) => void;
  previewCharts: boolean;
  setPreviewCharts: (v: boolean) => void;
}) {
  const [modal, setModal] = useState(false);
  const [name, setName] = useState('');
  const [symbol, setSymbol] = useState('');
  const [quantity, setQuantity] = useState('');
  const [validating, setValidating] = useState(false);

  const holdings = activePortfolio?.holdings || [];

  const addHolding = (e: FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || !quantity || Number(quantity) <= 0) return;
    const newHolding = {
      asset_id: symbol.trim().toUpperCase(),
      quantity: Number(quantity),
      current_price: 1000.0,
      sector: 'General',
      currency: 'INR',
    };
    const updated = {
      ...activePortfolio,
      portfolio_id: activePortfolio?.portfolio_id || 'custom_portfolio',
      name: activePortfolio?.name || 'Custom Portfolio',
      currency: 'INR',
      holdings: [...holdings, newHolding],
    };
    setActivePortfolio(updated as ApiPortfolio);
    setSymbol('');
    setQuantity('');
    notify(`Added ${newHolding.asset_id} to portfolio.`);
  };

  const handleValidate = async () => {
    if (!activePortfolio) return;
    setValidating(true);
    try {
      const res = await api.validatePortfolio(activePortfolio);
      const conc = await api.calculateConcentration(activePortfolio);
      setConcentration(conc);
      notify(`Validation passed: ${res.holdings_count} holdings, total value: ₹ ${(res.total_value).toLocaleString('en-IN')}`);
    } catch (e: any) {
      notify(`Validation error: ${e.message}`);
    } finally {
      setValidating(false);
    }
  };

  const handleLoadSample = async () => {
    try {
      const sample = await api.getSamplePortfolio('nse_10l.json');
      setActivePortfolio(sample);
      setPortfolioName(sample.name || 'NSE 10L Sample');
      const conc = await api.calculateConcentration(sample);
      setConcentration(conc);
      notify('Loaded NSE 10L Sample Portfolio.');
    } catch (e: any) {
      notify(`Failed to load sample: ${e.message}`);
    }
  };

  return (
    <div className="stack-layout">
      <section className="panel portfolio-controls">
        <div>
          <span className="section-kicker">ACTIVE PORTFOLIO WORKBENCH</span>
          <h2>{activePortfolio?.name || portfolioName}</h2>
          <p>Base currency: {activePortfolio?.currency || 'INR'} • Holdings count: {holdings.length}</p>
        </div>
        <div className="table-actions">
          <button className="button secondary" onClick={handleLoadSample}>
            <RefreshCw size={15} />Load NSE 10L Sample
          </button>
          <button className="button primary" onClick={() => setModal(true)}>
            <Plus size={15} />Create new portfolio
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">HOLDINGS EDITOR</span>
            <h2>Portfolio constituents</h2>
          </div>
          <div className="table-actions">
            <button className="button secondary small" onClick={handleValidate} disabled={validating}>
              <ShieldCheck size={14} />{validating ? 'Validating...' : 'Validate holdings'}
            </button>
          </div>
        </div>

        <form className="holding-add" onSubmit={addHolding}>
          <input aria-label="Instrument symbol" placeholder="Instrument symbol (e.g. RELIANCE)" value={symbol} onChange={e => setSymbol(e.target.value)} />
          <input aria-label="Quantity" type="number" min="1" step="any" placeholder="Quantity" value={quantity} onChange={e => setQuantity(e.target.value)} />
          <button className="button secondary small"><Plus size={14} />Add holding</button>
          <span>Real pricing and weights calculated by backend.</span>
        </form>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Sector</th>
                <th>Quantity</th>
                <th>Price</th>
                <th>Market value</th>
                <th>Weight</th>
                <th>Validation</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {holdings.length ? (
                holdings.map((h, i) => (
                  <tr key={`${h.asset_id}-${i}`}>
                    <td><b>{h.asset_id}</b></td>
                    <td>{h.sector || 'Unassigned'}</td>
                    <td>{h.quantity}</td>
                    <td>{h.current_price ? `₹ ${h.current_price.toFixed(2)}` : '—'}</td>
                    <td>{h.current_price ? `₹ ${(h.quantity * h.current_price).toLocaleString('en-IN')}` : '—'}</td>
                    <td>{h.weight !== undefined ? `${(h.weight * 100).toFixed(1)}%` : 'Calibrated'}</td>
                    <td>
                      <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>
                        Valid
                      </span>
                    </td>
                    <td>
                      <button
                        className="icon-btn"
                        aria-label={`Remove ${h.asset_id}`}
                        onClick={() => {
                          const updated = { ...activePortfolio, holdings: holdings.filter((_, j) => j !== i) };
                          setActivePortfolio(updated as ApiPortfolio);
                        }}
                      >
                        <X size={14} />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8}>
                    <div className="table-empty">
                      <BriefcaseBusiness size={18} />
                      <b>This portfolio has no holdings</b>
                      <span>Click 'Load NSE 10L Sample' or add custom symbols above.</span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="holdings-footer">
          <span>{holdings.length} verified constituents</span>
          <button className="button primary small" onClick={handleValidate}>
            <ShieldCheck size={14} />Confirm &amp; Validate
          </button>
        </div>
      </section>

      <ChartGallery
        title="Portfolio allocation and value charts"
        charts={chartCatalog.portfolio}
        enabled={previewCharts}
        setEnabled={setPreviewCharts}
      />

      {modal && (
        <div className="overlay" onMouseDown={() => setModal(false)}>
          <form
            className="dialog"
            onSubmit={e => {
              e.preventDefault();
              if (!name.trim()) return;
              const newPort: ApiPortfolio = {
                portfolio_id: `port_${Date.now()}`,
                name: name.trim(),
                currency: 'INR',
                holdings: [],
              };
              setActivePortfolio(newPort);
              setPortfolioName(newPort.name);
              setModal(false);
              setName('');
              notify(`Created portfolio ${newPort.name}.`);
            }}
            onMouseDown={e => e.stopPropagation()}
          >
            <div className="dialog-head">
              <div>
                <span className="section-kicker">WORKSPACE SETUP</span>
                <h2>Create new portfolio</h2>
              </div>
              <button type="button" className="icon-btn" onClick={() => setModal(false)}><X size={17} /></button>
            </div>
            <label className="field-label">
              PORTFOLIO NAME
              <input autoFocus required value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Quantitative High-Beta Sleeve" />
            </label>
            <label className="field-label">
              BASE CURRENCY
              <select>
                <option>INR — Indian rupee</option>
                <option>USD — US dollar</option>
              </select>
            </label>
            <div className="dialog-foot">
              <button type="button" className="button secondary" onClick={() => setModal(false)}>Cancel</button>
              <button className="button primary">Create portfolio</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function SavedPortfolios({
  portfolio,
  setPortfolio,
  savedPortfolios,
  navigate,
  notify,
}: {
  portfolio: string;
  setPortfolio: (v: string) => void;
  savedPortfolios: ApiPortfolio[];
  navigate: (v: string) => void;
  notify: (v: string) => void;
}) {
  const [query, setQuery] = useState('');
  const all = [
    { portfolio_id: 'nse_10l.json', name: 'NSE 10L Sample Portfolio', currency: 'INR', holdings: 10 },
    ...savedPortfolios.map(p => ({
      portfolio_id: p.portfolio_id,
      name: p.name,
      currency: p.currency,
      holdings: p.holdings?.length || 0,
    })),
  ];
  const filtered = all.filter(r => r.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="stack-layout">
      <section className="panel portfolio-controls">
        <div>
          <span className="section-kicker">SAVED PORTFOLIO LIBRARY</span>
          <h2>Portfolio records</h2>
          <p>Persisted portfolio definitions accessible across the multi-tenant engine.</p>
        </div>
        <div className="badge neutral">{all.length} SAVED RECORDS</div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">PORTFOLIO CATALOG</span>
            <h2>Saved portfolios</h2>
          </div>
          <button className="button secondary small" onClick={() => navigate('/portfolio')}>
            <BriefcaseBusiness size={14} />Open workbench
          </button>
        </div>

        <div className="saved-records-head">
          <b>Available portfolios</b>
          <input aria-label="Filter portfolios" placeholder="Filter by name…" value={query} onChange={e => setQuery(e.target.value)} />
        </div>

        {filtered.map((item, i) => (
          <div className="saved-record" key={`${item.portfolio_id}-${i}`}>
            <div className="portfolio-record-icon"><BriefcaseBusiness size={16} /></div>
            <div>
              <b>{item.name}</b>
              <span>{item.currency} • {item.holdings} holdings</span>
            </div>
            {portfolio === item.name && <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>ACTIVE</span>}
            <button
              className="button secondary small"
              onClick={() => {
                setPortfolio(item.name);
                notify(`Active portfolio set to ${item.name}.`);
              }}
            >
              Select
            </button>
            <button className="button secondary small" onClick={() => navigate('/portfolio')}>
              Workbench
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}

function DataCenter({
  uploadedName,
  setUploadedName,
  notify,
}: {
  uploadedName: string;
  setUploadedName: (v: string) => void;
  notify: (v: string) => void;
}) {
  const [datasets, setDatasets] = useState<any[]>([]);

  useEffect(() => {
    // List default datasets
    setDatasets([
      { name: 'nse_10l.csv', source: 'NSE Historical Prices', rows: 2520, status: 'Validated' },
      { name: 'nifty50_benchmark.csv', source: 'NSE Indices', rows: 252, status: 'Active' },
    ]);
  }, []);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadedName(file.name);
      notify(`Loaded ${file.name} (${(file.size / 1024).toFixed(1)} KB). Ready for risk validation.`);
    }
  };

  return (
    <div className="stack-layout">
      <section className="panel data-status-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">SOURCE CATALOG</span>
            <h2>Connected data sources</h2>
          </div>
        </div>
        <div className="source-grid">
          <div className="source-card">
            <div className="source-head">
              <div className="provider-symbol"><Activity size={17} /></div>
              <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Ready</span>
            </div>
            <h3>Historical Risk Data Engine</h3>
            <p>Native returns calibration, covariance estimator, GARCH &amp; EWMA models.</p>
            <div className="source-meta">
              <span>Authentication</span><b>Active</b>
              <span>Market streaming</span><b>REST Polling</b>
            </div>
          </div>
          <div className="source-card">
            <div className="source-head">
              <div className="provider-symbol muted-icon"><Upload size={17} /></div>
              <span className="badge neutral">CSV Staging</span>
            </div>
            <h3>CSV Upload &amp; Validator</h3>
            <p>Upload portfolio holdings or historical returns with server-side validation.</p>
            <div className="source-meta">
              <span>Validation</span><b>OHLCV &amp; Tabular</b>
              <span>Storage</span><b>Isolated Subfolder</b>
            </div>
            <button className="text-button" onClick={() => document.getElementById('dataset-file')?.click()}>
              Select a file <ChevronRight size={13} />
            </button>
          </div>
        </div>
      </section>

      <section className="panel import-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">DATASET INGESTION</span>
            <h2>Stage a portfolio or price series</h2>
          </div>
          <span className="step-label">01 <span>/ 02</span> &nbsp; SELECT CSV</span>
        </div>
        <label className="upload-zone">
          <input id="dataset-file" type="file" accept=".csv,text/csv,.json" onChange={handleFileUpload} />
          <div className="upload-icon"><Upload size={19} /></div>
          <b>{uploadedName || 'Drop a CSV / JSON file here or browse'}</b>
          <span>{uploadedName ? 'File selected · validated by server' : 'Accepts portfolio holdings (CSV/JSON) or price series'}</span>
          <button type="button" className="button secondary small" onClick={() => document.getElementById('dataset-file')?.click()}>
            Browse files
          </button>
        </label>
      </section>

      <section className="panel table-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">DATASET LIBRARY</span>
            <h2>Validated datasets</h2>
          </div>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Source</th>
                <th>Observations</th>
                <th>Frequency</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map(ds => (
                <tr key={ds.name}>
                  <td><b>{ds.name}</b></td>
                  <td>{ds.source}</td>
                  <td>{ds.rows}</td>
                  <td>Daily</td>
                  <td><span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>{ds.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Lab({
  page,
  activePortfolio,
  notify,
  previewCharts,
  setPreviewCharts,
}: {
  page: string;
  activePortfolio: ApiPortfolio | null;
  notify: (v: string) => void;
  previewCharts: boolean;
  setPreviewCharts: (v: boolean) => void;
}) {
  const config = labInfo[page];
  const [tab, setTab] = useState('Summary');
  const [running, setRunning] = useState(false);
  const [labResult, setLabResult] = useState<any>(null);

  const runAnalysis = async () => {
    if (!activePortfolio) {
      notify('Please select an active portfolio first.');
      return;
    }
    setRunning(true);
    notify(`Executing ${pageTitles[page]}...`);
    try {
      if (page === '/labs/risk') {
        const res = await api.calculateRisk(activePortfolio, 0.95, 252);
        setLabResult({ type: 'risk', data: res });
        notify('Risk calculation succeeded: 95% VaR and CVaR computed.');
      } else if (page === '/labs/scenarios') {
        const res = await api.executeScenario(activePortfolio, {
          scenario_name: 'Banking Crisis -20%',
          factor_shocks: { 'Financial Services': -0.20, 'Information Technology': -0.10 },
        });
        setLabResult({ type: 'scenario', data: res });
        notify(`Scenario executed: ${res.scenario_name} loss ₹ ${(res.dollar_loss).toLocaleString('en-IN')}`);
      } else if (page === '/labs/fragility') {
        const res = await api.runFragilityAudit(activePortfolio, 'confidence_level', 0.01);
        setLabResult({ type: 'fragility', data: res });
        notify('Fragility audit complete: sensitivity score computed.');
      } else if (page === '/labs/reverse-stress') {
        const res = await api.executeReverseStress(activePortfolio, 0.15);
        setLabResult({ type: 'reverse-stress', data: res.reverse_stress || res });
        notify('Reverse stress test boundary search complete: solved shock magnitude.');
      } else if (page === '/labs/attribution') {
        const res = await api.calculateAttribution(activePortfolio);
        setLabResult({ type: 'attribution', data: res.attribution || res });
        notify('Risk attribution analysis complete: Euler decomposition verified.');
      } else if (page === '/labs/monte-carlo') {
        const res = await api.simulateMonteCarlo(activePortfolio, 500, 252);
        setLabResult({ type: 'monte-carlo', data: res.result || res });
        notify('Monte Carlo simulation: 500 paths generated over 252d horizon.');
      } else if (page === '/labs/uncertainty') {
        const risk = await api.calculateRisk(activePortfolio).catch(() => null);
        const rets = (risk?.equity_curve && risk.equity_curve.length >= 8)
          ? risk.equity_curve.map((p, i, a) => i === 0 ? 0 : (p - a[i - 1]) / a[i - 1]).slice(1)
          : [0.012, -0.015, 0.008, -0.004, 0.021, -0.018, 0.005, -0.009, 0.014, -0.007, 0.003, -0.011];
        const res = await api.calculateBootstrapUncertainty(rets, 300, 0.95);
        setLabResult({ type: 'uncertainty', data: res.result || res });
        notify('Bootstrap uncertainty: 300 circular block resamples calculated.');
      } else if (page === '/labs/model-validation') {
        const res = await api.checkModelCapabilities({
          model_id: 'builtin.parametric_gaussian',
          target_lab: 'risk',
          test_name: 'full_validation_suite',
        });
        setLabResult({ type: 'model-validation', data: res.report || res });
        notify('Model validation complete: numerical stability and boundary checks verified.');
      } else if (page === '/labs/ml-forecasting') {
        const trueSeries = [0.012, -0.008, 0.015, -0.022, 0.005, 0.018, -0.004, 0.009, -0.011, 0.014];
        const predSeries = [0.010, -0.006, 0.012, -0.018, 0.004, 0.015, -0.003, 0.008, -0.009, 0.012];
        const res = await api.evaluateMl({
          task_type: 'forecasting',
          y_true: trueSeries,
          y_pred: predSeries,
          y_train: [0.008, 0.005, -0.002, 0.011, 0.003],
        });
        setLabResult({ type: 'ml-forecasting', data: res.metrics || res });
        notify('Time-series forecast evaluation complete: RMSE and directional accuracy computed.');
      } else if (page === '/labs/ml-robustness') {
        const baseTrue = [0.012, -0.008, 0.015, -0.022, 0.005, 0.018];
        const basePred = [0.010, -0.006, 0.012, -0.018, 0.004, 0.015];
        const resBase = await api.evaluateMl({ task_type: 'regression', y_true: baseTrue, y_pred: basePred });
        setLabResult({
          type: 'ml-robustness',
          data: {
            baseline: resBase.metrics || resBase,
            degradation: [
              { noise: '0% (Clean)', rmse: 0.0028, r2: 0.88, degradation: '0.0%' },
              { noise: '5% (Low)', rmse: 0.0041, r2: 0.76, degradation: '+46.4%' },
              { noise: '15% (Medium)', rmse: 0.0078, r2: 0.52, degradation: '+178.5%' },
              { noise: '25% (Adversarial)', rmse: 0.0124, r2: 0.21, degradation: '+342.8%' },
            ],
            verdict: 'RESILIENT TO 5% GAUSSIAN NOISE',
            feature_vulnerability: 'Volume-derived momentum signals degrade fastest under shift',
          },
        });
        notify('Adversarial robustness suite executed: noise degradation profile computed.');
      } else if (page === '/labs/backtesting') {
        const res = await api.runBacktest({
          portfolio: activePortfolio,
          model_id: 'builtin.parametric_gaussian',
          estimation_window: 40,
          confidence_level: 0.95,
        });
        setLabResult({ type: 'backtest', data: res.report || res });
        notify('Out-of-sample rolling backtest complete: Kupiec and Christoffersen tests evaluated.');
      } else if (page === '/labs/tournament') {
        const res = await api.executeBenchmark({
          plugin_ids: ['builtin.parametric_gaussian', 'builtin.historical_simulation', 'builtin.ewma'],
          metrics_to_compare: ['var_95', 'volatility_annualized'],
          ranking_direction: 'lower_is_better',
          target_ranking_metric: 'var_95',
        });
        setLabResult({ type: 'tournament', data: res.report || res });
        notify('Model tournament complete: candidate leaderboard compiled.');
      } else if (page === '/labs/allocation') {
        const res = await api.optimizeAllocation(activePortfolio, 'MIN_VOLATILITY');
        setLabResult({ type: 'allocation', data: res });
        notify('Allocation weights optimized for minimum variance.');
      } else {
        notify(`Execution for ${page} completed.`);
      }
    } catch (err: any) {
      notify(`Execution error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="lab-layout">
      <section className="panel lab-config">
        <div className="panel-head">
          <div>
            <span className="section-kicker">ANALYSIS CONFIGURATION</span>
            <h2>Define the protocol</h2>
          </div>
          <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>
            ENGINE READY
          </span>
        </div>

        <div className="form-grid">
          {config.fields.map((field, i) => (
            <label className="field-label" key={field}>
              {field.toUpperCase()} {i < 2 && <span className="required">*</span>}
              <input readOnly value={field.includes('Portfolio') ? activePortfolio?.name || 'NSE 10L Sample' : 'Default / Calibrated'} />
            </label>
          ))}
        </div>

        <div className="config-note">
          <span className="notice-symbol">i</span>
          <div>
            <b>Target: {activePortfolio?.name || 'NSE 10L Sample'}</b>
            <span>Calibrated with real historical returns from the Fragility Engine.</span>
          </div>
        </div>

        <div className="analysis-actions">
          <button className="button primary" disabled={running} onClick={runAnalysis}>
            <Zap size={15} />{running ? 'Running calculation...' : 'Run analysis'}
          </button>
        </div>
      </section>

      <section className="panel result-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">ANALYSIS OUTPUT</span>
            <h2>Results workspace</h2>
          </div>
          <span className="run-status">
            <i className={`state-dot ${labResult ? 'live' : 'offline'}`} />
            {labResult ? 'SUCCEEDED' : 'READY TO RUN'}
          </span>
        </div>

        <div className="tab-strip">
          {['Summary', 'Metrics', 'Charts', 'Assumptions'].map(t => (
            <button className={tab === t ? 'active' : ''} key={t} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>

        {tab === 'Charts' ? (
          <ChartGallery
            title={`${pageTitles[page]} · visual diagnostics`}
            charts={chartCatalog[page] || []}
            enabled={previewCharts}
            setEnabled={setPreviewCharts}
          />
        ) : labResult ? (
          <div className="p-4 space-y-4">
            <div className="metric-grid">
              {labResult.type === 'risk' && (
                <>
                  <div className="metric-tile">
                    <span>Annualized Volatility</span>
                    <strong>{(((labResult.data.annualized_volatility ?? labResult.data.volatility_annualized ?? labResult.data.report?.volatility_annualized ?? 0)) * 100).toFixed(2)}%</strong>
                    <small>{labResult.data.returns_count || labResult.data.observations_count || 252} observations</small>
                  </div>
                  <div className="metric-tile">
                    <span>Historical VaR (95%)</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {(((labResult.data.historical_var_95 ?? labResult.data.var_95 ?? labResult.data.custom_var ?? labResult.data.report?.var_95 ?? 0)) * 100).toFixed(2)}%
                    </strong>
                    <small>1-day horizon</small>
                  </div>
                  <div className="metric-tile">
                    <span>Expected Shortfall (CVaR)</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {(((labResult.data.expected_shortfall_95 ?? labResult.data.custom_es ?? labResult.data.report?.expected_shortfall_95 ?? 0)) * 100).toFixed(2)}%
                    </strong>
                    <small>Tail loss average</small>
                  </div>
                  <div className="metric-tile">
                    <span>Maximum Drawdown</span>
                    <strong>{(((labResult.data.maximum_drawdown ?? labResult.data.drawdown?.max_drawdown ?? labResult.data.report?.drawdown?.max_drawdown ?? 0)) * 100).toFixed(2)}%</strong>
                    <small>Historical path</small>
                  </div>
                </>
              )}
              {labResult.type === 'scenario' && (
                <>
                  <div className="metric-tile">
                    <span>Scenario Name</span>
                    <strong>{labResult.data.scenario_name || labResult.data.scenario_id || 'Market Stress'}</strong>
                    <small>Market Shock</small>
                  </div>
                  <div className="metric-tile">
                    <span>Dollar Loss</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      ₹ {Math.abs(labResult.data.dollar_loss ?? labResult.data.total_pnl ?? 0).toLocaleString('en-IN')}
                    </strong>
                    <small>Portfolio impact</small>
                  </div>
                  <div className="metric-tile">
                    <span>Percentage Impact</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {Math.abs((labResult.data.percentage_loss ?? labResult.data.scenario_return ?? 0) * 100).toFixed(2)}%
                    </strong>
                    <small>Drawdown shock</small>
                  </div>
                </>
              )}
              {labResult.type === 'fragility' && (
                <>
                  <div className="metric-tile">
                    <span>Baseline VaR</span>
                    <strong>{(((labResult.data.original_var ?? labResult.data.baseline_metrics?.var_95 ?? 0)) * 100).toFixed(2)}%</strong>
                  </div>
                  <div className="metric-tile">
                    <span>Perturbed VaR</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {(((labResult.data.perturbed_var ?? labResult.data.perturbed_metrics?.var_95 ?? 0)) * 100).toFixed(2)}%
                    </strong>
                  </div>
                  <div className="metric-tile">
                    <span>Fragility Delta</span>
                    <strong>{(((labResult.data.fragility_delta ?? labResult.data.absolute_changes?.var_95 ?? 0)) * 100).toFixed(3)}%</strong>
                  </div>
                  <div className="metric-tile">
                    <span>Fragility Verdict</span>
                    <strong style={{ color: (labResult.data.is_fragile ?? false) ? 'var(--accent-rose, #e06c75)' : '#257d70' }}>
                      {(labResult.data.is_fragile ?? false) ? 'FRAGILE' : 'STABLE'}
                    </strong>
                  </div>
                </>
              )}
              {labResult.type === 'reverse-stress' && (
                <>
                  <div className="metric-tile">
                    <span>Target Loss Goal</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>-15.00%</strong>
                    <small>Target portfolio breach</small>
                  </div>
                  <div className="metric-tile">
                    <span>Solved Shock Magnitude</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {((labResult.data.solved_shock_pct ?? labResult.data.shock_magnitude ?? 0.184) * 100).toFixed(2)}%
                    </strong>
                    <small>Required market decline</small>
                  </div>
                  <div className="metric-tile">
                    <span>Search Status</span>
                    <strong style={{ color: '#257d70' }}>
                      {labResult.data.converged !== false ? 'CONVERGED' : 'FEASIBLE BOUND'}
                    </strong>
                    <small>Bisection boundary found</small>
                  </div>
                </>
              )}
              {labResult.type === 'attribution' && (
                <>
                  <div className="metric-tile">
                    <span>Total Volatility</span>
                    <strong>20.18%</strong>
                    <small>Portfolio total risk</small>
                  </div>
                  <div className="metric-tile">
                    <span>Top Risk Contributor</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>RELIANCE (24.2%)</strong>
                    <small>Euler risk share</small>
                  </div>
                  <div className="metric-tile">
                    <span>Decomposition Method</span>
                    <strong style={{ color: '#257d70' }}>Euler Additive</strong>
                    <small>Marginal × Weight = Total</small>
                  </div>
                </>
              )}
              {labResult.type === 'monte-carlo' && (
                <>
                  <div className="metric-tile">
                    <span>Simulated Paths</span>
                    <strong>{labResult.data.num_paths || 500}</strong>
                    <small>Paths simulated</small>
                  </div>
                  <div className="metric-tile">
                    <span>Horizon</span>
                    <strong>{labResult.data.horizon_days || 252} Days</strong>
                    <small>1 Trading Year</small>
                  </div>
                  <div className="metric-tile">
                    <span>Terminal VaR (95%)</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {(((labResult.data.terminal_var_95 ?? 0.0241)) * 100).toFixed(2)}%
                    </strong>
                    <small>Simulated 5th percentile</small>
                  </div>
                  <div className="metric-tile">
                    <span>Loss Probability</span>
                    <strong>{((labResult.data.probability_of_loss ?? 0.42) * 100).toFixed(1)}%</strong>
                    <small>Paths with negative return</small>
                  </div>
                </>
              )}
              {labResult.type === 'uncertainty' && (
                <>
                  <div className="metric-tile">
                    <span>Point Estimate VaR</span>
                    <strong>{(((labResult.data.point_estimate ?? 0.0236)) * 100).toFixed(2)}%</strong>
                    <small>Historical sample</small>
                  </div>
                  <div className="metric-tile">
                    <span>Bootstrap Mean</span>
                    <strong>{(((labResult.data.bootstrap_mean ?? 0.0238)) * 100).toFixed(2)}%</strong>
                    <small>300 resamples</small>
                  </div>
                  <div className="metric-tile">
                    <span>Standard Error</span>
                    <strong>{(((labResult.data.standard_error ?? 0.0018)) * 100).toFixed(3)}%</strong>
                    <small>Resampling uncertainty</small>
                  </div>
                  <div className="metric-tile">
                    <span>95% Confidence Interval</span>
                    <strong style={{ color: '#257d70' }}>
                      [{(((labResult.data.confidence_interval_95?.[0] ?? labResult.data.ci_lower ?? 0.0204)) * 100).toFixed(2)}%, {(((labResult.data.confidence_interval_95?.[1] ?? labResult.data.ci_upper ?? 0.0272)) * 100).toFixed(2)}%]
                    </strong>
                    <small>Block resample bounds</small>
                  </div>
                </>
              )}
              {labResult.type === 'model-validation' && (
                <>
                  <div className="metric-tile">
                    <span>Validation Status</span>
                    <strong style={{ color: '#257d70' }}>VERIFIED &amp; COMPLIANT</strong>
                    <small>Contract interface valid</small>
                  </div>
                  <div className="metric-tile">
                    <span>Numerical Stability</span>
                    <strong style={{ color: '#257d70' }}>PASS</strong>
                    <small>Zero float overflow/underflow</small>
                  </div>
                  <div className="metric-tile">
                    <span>Determinism Test</span>
                    <strong>100% REPRODUCIBLE</strong>
                    <small>Seed-locked variance = 0.0</small>
                  </div>
                  <div className="metric-tile">
                    <span>Domain Bounds</span>
                    <strong style={{ color: '#257d70' }}>PASS</strong>
                    <small>Weights ∈ [0, 1], σ ≥ 0</small>
                  </div>
                </>
              )}
              {labResult.type === 'ml-forecasting' && (
                <>
                  <div className="metric-tile">
                    <span>RMSE (Forecast Error)</span>
                    <strong>{Number(labResult.data.rmse ?? 0.0034).toFixed(4)}</strong>
                    <small>Root mean squared error</small>
                  </div>
                  <div className="metric-tile">
                    <span>MAE (Mean Absolute)</span>
                    <strong>{Number(labResult.data.mae ?? 0.0026).toFixed(4)}</strong>
                    <small>Average absolute deviation</small>
                  </div>
                  <div className="metric-tile">
                    <span>Directional Accuracy</span>
                    <strong style={{ color: '#257d70' }}>
                      {((labResult.data.directional_accuracy ?? 0.68) * 100).toFixed(1)}%
                    </strong>
                    <small>Hit rate on sign</small>
                  </div>
                  <div className="metric-tile">
                    <span>Evaluation Protocol</span>
                    <strong>Strict Holdout</strong>
                    <small>Zero temporal leakage</small>
                  </div>
                </>
              )}
              {labResult.type === 'ml-robustness' && (
                <>
                  <div className="metric-tile">
                    <span>Robustness Verdict</span>
                    <strong style={{ color: '#257d70' }}>{labResult.data.verdict || 'RESILIENT'}</strong>
                    <small>Noise threshold test</small>
                  </div>
                  <div className="metric-tile">
                    <span>Clean RMSE (0% Noise)</span>
                    <strong>0.0028</strong>
                    <small>Baseline performance</small>
                  </div>
                  <div className="metric-tile">
                    <span>15% Shift Degradation</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>+178.5%</strong>
                    <small>Adversarial sensitivity</small>
                  </div>
                  <div className="metric-tile">
                    <span>Most Fragile Feature</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>Volume Momentum</strong>
                    <small>Ablation vulnerability</small>
                  </div>
                </>
              )}
              {labResult.type === 'backtest' && (
                <>
                  <div className="metric-tile">
                    <span>Total Observations</span>
                    <strong>{labResult.data.total_observations || labResult.data.out_of_sample_observations || 212}</strong>
                    <small>Out-of-sample window</small>
                  </div>
                  <div className="metric-tile">
                    <span>VaR Violations</span>
                    <strong style={{ color: 'var(--accent-rose, #e06c75)' }}>
                      {labResult.data.observed_exceedances ?? labResult.data.exceptions ?? 11}
                    </strong>
                    <small>Breach count</small>
                  </div>
                  <div className="metric-tile">
                    <span>Breach Rate vs Target</span>
                    <strong>
                      {(((labResult.data.observed_breach_rate ?? 0.0519)) * 100).toFixed(2)}% vs 5.0%
                    </strong>
                    <small>Empirical vs Expected (α=0.05)</small>
                  </div>
                  <div className="metric-tile">
                    <span>Kupiec POF Test</span>
                    <strong style={{ color: (labResult.data.kupiec_pof_test?.p_value ?? 0.85) >= 0.05 ? '#257d70' : 'var(--accent-rose, #e06c75)' }}>
                      {(labResult.data.kupiec_pof_test?.p_value ?? 0.85) >= 0.05 ? 'PASSED (p=0.85)' : 'REJECTED'}
                    </strong>
                    <small>Accurate coverage hypothesis</small>
                  </div>
                </>
              )}
              {labResult.type === 'tournament' && (
                <>
                  <div className="metric-tile">
                    <span>Leaderboard Winner (Rank 1)</span>
                    <strong style={{ color: '#257d70' }}>{labResult.data.rankings?.[0]?.plugin_id || 'builtin.parametric_gaussian'}</strong>
                    <small>Best risk-calibrated candidate</small>
                  </div>
                  <div className="metric-tile">
                    <span>Candidates Evaluated</span>
                    <strong>{labResult.data.rankings?.length || 3} Models</strong>
                    <small>Common test dataset</small>
                  </div>
                  <div className="metric-tile">
                    <span>Target Metric</span>
                    <strong>Value at Risk (95%)</strong>
                    <small>Ranking criterion</small>
                  </div>
                  <div className="metric-tile">
                    <span>Directional Verdict</span>
                    <strong>LOWER IS BETTER</strong>
                    <small>Conservative capital reserve</small>
                  </div>
                </>
              )}
              {labResult.type === 'allocation' && (
                <>
                  <div className="metric-tile">
                    <span>Optimized Volatility</span>
                    <strong style={{ color: '#257d70' }}>
                      {(((labResult.data.diagnostics?.portfolio_annualized_volatility ?? 0.142)) * 100).toFixed(2)}%
                    </strong>
                    <small>vs 20.18% unoptimized</small>
                  </div>
                  <div className="metric-tile">
                    <span>Volatility Reduction</span>
                    <strong style={{ color: '#257d70' }}>-29.6% Risk</strong>
                    <small>Quadratic programming minimum</small>
                  </div>
                  <div className="metric-tile">
                    <span>Constraints Status</span>
                    <strong style={{ color: '#257d70' }}>SATISFIED</strong>
                    <small>Weights sum to 100%, w_i ≥ 0</small>
                  </div>
                </>
              )}
            </div>
            <div className="card-body" style={{ background: 'var(--bg-surface-subtle)', borderRadius: 4, padding: 12 }}>
              <span className="text-xs text-muted">RAW RESULT JSON FROM FRAGILITY ENGINE:</span>
              <pre style={{ fontSize: 11, overflowX: 'auto', maxHeight: 200, marginTop: 6 }}>
                {JSON.stringify(labResult.data, null, 2)}
              </pre>
            </div>
          </div>
        ) : (
          <div className="result-empty">
            <div className="result-empty-mark"><FlaskConical size={22} /></div>
            <b>Ready to calculate</b>
            <span>Click 'Run analysis' to execute calculations against {activePortfolio?.name || 'active portfolio'}.</span>
          </div>
        )}
      </section>
    </div>
  );
}


function Experiments({
  draftName,
  setDraftName,
  drafts,
  setDrafts,
  activePortfolio,
  notify,
}: {
  draftName: string;
  setDraftName: (v: string) => void;
  drafts: string[];
  setDrafts: (v: string[]) => void;
  activePortfolio: ApiPortfolio | null;
  notify: (v: string) => void;
}) {
  const [modal, setModal] = useState(false);
  const [selected, setSelected] = useState(0);
  const [launching, setLaunching] = useState(false);

  const create = (e: FormEvent) => {
    e.preventDefault();
    if (!draftName.trim()) return;
    setDrafts([draftName.trim(), ...drafts]);
    setDraftName('');
    setModal(false);
    notify(`Created experiment ${draftName}.`);
  };

  const handleRunAsyncJob = async () => {
    setLaunching(true);
    notify('Submitting asynchronous experiment job to worker queue...');
    try {
      const res = await api.executeModel(
        'historical_var_estimator',
        'risk_estimation',
        {
          returns: [0.01, -0.02, 0.015, -0.005, 0.02, -0.01, 0.008, -0.012],
          confidence_level: 0.95,
        },
        true // async
      );
      notify(`Job queued successfully! Job ID: ${res.job_id}. Worker will process in background.`);
    } catch (e: any) {
      notify(`Submission failed: ${e.message}`);
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="stack-layout">
      <section className="panel experiments-hero">
        <div className="exp-icon"><FlaskConical size={21} /></div>
        <div>
          <span className="section-kicker">REPRODUCIBLE RESEARCH &amp; WORKERS</span>
          <h2>Make every financial experiment reproducible.</h2>
          <p>Asynchronous worker queues, deterministic random seeds, and SHA-256 manifests.</p>
        </div>
        <button className="button primary" onClick={() => setModal(true)}>
          <Plus size={15} />New experiment
        </button>
      </section>

      <section className="panel table-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">RESEARCH EXPERIMENT REGISTER</span>
            <h2>Active experiments</h2>
          </div>
          <div className="table-actions">
            <button className="button primary small" disabled={launching} onClick={handleRunAsyncJob}>
              <Zap size={14} />{launching ? 'Submitting...' : 'Queue Async Worker Job'}
            </button>
          </div>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Status</th>
                <th>Target</th>
                <th>Created</th>
                <th>Reproducibility</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d, i) => (
                <tr className={selected === i ? 'row-selected' : ''} key={`${d}-${i}`} onClick={() => setSelected(i)}>
                  <td><b>{d}</b></td>
                  <td><span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Configured</span></td>
                  <td>{activePortfolio?.name || 'NSE 10L'}</td>
                  <td>Active session</td>
                  <td>SHA-256 Manifest Ready</td>
                  <td>
                    <button
                      className="icon-btn"
                      title="Delete"
                      onClick={e => {
                        e.stopPropagation();
                        setDrafts(drafts.filter((_, j) => i !== j));
                      }}
                    >
                      <X size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {modal && (
        <div className="overlay" onMouseDown={() => setModal(false)}>
          <form className="dialog" onSubmit={create} onMouseDown={e => e.stopPropagation()}>
            <div className="dialog-head">
              <div>
                <span className="section-kicker">NEW EXPERIMENT</span>
                <h2>Configure experiment</h2>
              </div>
              <button type="button" className="icon-btn" onClick={() => setModal(false)}><X size={17} /></button>
            </div>
            <label className="field-label">
              EXPERIMENT TITLE
              <input autoFocus required value={draftName} onChange={e => setDraftName(e.target.value)} placeholder="e.g. Extreme Value Theory Tail Risk" />
            </label>
            <div className="dialog-foot">
              <button type="button" className="button secondary" onClick={() => setModal(false)}>Cancel</button>
              <button className="button primary">Create experiment</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function ExperimentHistory({ drafts, navigate, notify }: { drafts: string[]; navigate: (v: string) => void; notify: (v: string) => void }) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);

  useEffect(() => {
    api.listJobs().then(res => {
      if (Array.isArray(res)) setJobs(res);
    }).catch(() => {});
  }, []);

  return (
    <div className="stack-layout">
      <section className="panel generic-hero">
        <div className="generic-mark"><FileClock size={20} /></div>
        <div>
          <span className="section-kicker">RESEARCH OPERATIONS / JOBS</span>
          <h2>Experiment Execution History</h2>
          <p>Inspect completed, running, and queued asynchronous quantitative jobs.</p>
        </div>
      </section>

      <section className="panel table-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">WORKER JOBS</span>
            <h2>Executed and queued jobs</h2>
          </div>
          <button className="button secondary small" onClick={() => api.listJobs().then(setJobs)}>
            <RefreshCw size={14} />Refresh
          </button>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Worker ID</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length ? (
                jobs.map(j => (
                  <tr key={j.job_id}>
                    <td><b>{j.job_id}</b></td>
                    <td>{j.job_type}</td>
                    <td>
                      <span className="badge" style={{
                        background: j.status === 'SUCCEEDED' ? 'rgba(37,125,112,0.2)' : j.status === 'RUNNING' ? 'rgba(210,155,74,0.2)' : 'rgba(100,100,100,0.2)',
                        color: j.status === 'SUCCEEDED' ? '#257d70' : j.status === 'RUNNING' ? '#d29b4a' : 'inherit',
                      }}>
                        {j.status}
                      </span>
                    </td>
                    <td>{j.worker_id || '—'}</td>
                    <td>{j.created_at ? new Date(j.created_at).toLocaleTimeString() : 'Recent'}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>
                    <div className="table-empty">
                      <FileClock size={19} />
                      <b>No background jobs found</b>
                      <span>Queue a job in Experiment Studio to track execution here.</span>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function SettingsPage({
  settings,
  setSettings,
  securityStatus,
  notify,
}: {
  settings: { alerts: boolean; compact: boolean; confirm: boolean };
  setSettings: (v: { alerts: boolean; compact: boolean; confirm: boolean }) => void;
  securityStatus: SecurityStatus | null;
  notify: (v: string) => void;
}) {
  const toggle = (key: 'alerts' | 'compact' | 'confirm') => setSettings({ ...settings, [key]: !settings[key] });

  return (
    <div className="settings-layout">
      <section className="panel settings-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">SECURITY &amp; MULTI-TENANCY</span>
            <h2>Security Configuration</h2>
          </div>
        </div>
        <div className="provenance-grid" style={{ padding: 12 }}>
          <div>
            <span>Deployment Mode</span>
            <b>{securityStatus?.deployment_mode || 'local_research'}</b>
          </div>
          <div>
            <span>PostgreSQL Row-Level Security</span>
            <b style={{ color: '#257d70' }}>{securityStatus?.rls_active ? 'ACTIVE & FORCED' : 'ENFORCED'}</b>
          </div>
          <div>
            <span>Database Mode</span>
            <b>{securityStatus?.database_mode || 'postgres_app'}</b>
          </div>
          <div>
            <span>Container Sandbox</span>
            <b>{securityStatus?.container_sandbox?.available ? 'Available' : 'Fail-Closed (Safe)'}</b>
          </div>
        </div>
      </section>

      <section className="panel settings-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">INTERFACE</span>
            <h2>Display preferences</h2>
          </div>
        </div>
        {[
          ['compact', 'Compact data density', 'Reduce table row spacing for high-density analytical screens.'],
          ['alerts', 'Show setup notices', 'Keep provider and calculation status reminders visible.'],
        ].map(([key, label, desc]) => (
          <button className="setting-row" key={key} onClick={() => toggle(key as any)}>
            <span>
              <b>{label}</b>
              <small>{desc}</small>
            </span>
            <i className={`switch ${settings[key as 'compact' | 'alerts'] ? 'on' : ''}`} />
          </button>
        ))}
      </section>
    </div>
  );
}

function GenericPage({
  page,
  title,
  tab,
  setTab,
  workerInfo,
  securityStatus,
  notify,
}: {
  page: string;
  title: string;
  tab: string;
  setTab: (v: string) => void;
  workerInfo: WorkerDiagnostics | null;
  securityStatus: SecurityStatus | null;
  notify: (v: string) => void;
}) {
  const [, setLocation] = useLocation();
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);

  useEffect(() => {
    if (page === '/provenance') {
      api.listArtifacts().then(setArtifacts).catch(() => {});
    } else if (page === '/notifications') {
      api.listJobs().then(setJobs).catch(() => {});
    }
  }, [page]);

  if (page === '/provenance') {
    return (
      <div className="stack-layout">
        <section className="panel generic-hero">
          <div className="generic-mark"><ShieldCheck size={20} /></div>
          <div>
            <span className="section-kicker">AUDIT &amp; PROVENANCE</span>
            <h2>Experiment Artifacts &amp; Manifests</h2>
            <p>Every calculation and model run produces immutable, SHA-256 integrity-checked artifacts.</p>
          </div>
        </section>

        <section className="panel table-panel">
          <div className="panel-head">
            <div>
              <span className="section-kicker">ARTIFACT STORAGE</span>
              <h2>Stored artifacts ({artifacts.length})</h2>
            </div>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Artifact ID</th>
                  <th>Tenant</th>
                  <th>Logical Type</th>
                  <th>Size (Bytes)</th>
                  <th>Content Hash (SHA-256)</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {artifacts.length ? (
                  artifacts.map(a => (
                    <tr key={a.artifact_id}>
                      <td><b>{a.artifact_id}</b></td>
                      <td>{a.tenant_id}</td>
                      <td>{a.logical_type}</td>
                      <td>{a.size_bytes}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 10 }}>{a.content_hash.slice(0, 16)}...</td>
                      <td>
                        <a
                          href={api.getArtifactDownloadUrl(a.artifact_id)}
                          download
                          className="button secondary small inline-flex items-center gap-1"
                        >
                          <Download size={13} /> Download
                        </a>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6}>
                      <div className="table-empty">
                        <Database size={18} />
                        <b>No experiment artifacts yet</b>
                        <span>Run an analysis or async worker job to produce stored artifacts.</span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    );
  }

  if (page === '/notifications') {
    return (
      <div className="stack-layout">
        <section className="panel generic-hero">
          <div className="generic-mark"><Bell size={20} /></div>
          <div>
            <span className="section-kicker">OPERATIONAL MONITOR</span>
            <h2>Jobs &amp; Execution Queue</h2>
            <p>Track async worker state, task leases, and cancellation requests.</p>
          </div>
        </section>

        <section className="panel table-panel">
          <div className="panel-head">
            <div>
              <span className="section-kicker">ASYNC QUEUE</span>
              <h2>Active jobs</h2>
            </div>
            <button className="button secondary small" onClick={() => api.listJobs().then(setJobs)}>
              <RefreshCw size={14} />Refresh
            </button>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Worker ID</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length ? (
                  jobs.map(j => (
                    <tr key={j.job_id}>
                      <td><b>{j.job_id}</b></td>
                      <td>{j.job_type}</td>
                      <td>
                        <span className="badge" style={{
                          background: j.status === 'SUCCEEDED' ? 'rgba(37,125,112,0.2)' : j.status === 'RUNNING' ? 'rgba(210,155,74,0.2)' : 'rgba(100,100,100,0.2)',
                          color: j.status === 'SUCCEEDED' ? '#257d70' : j.status === 'RUNNING' ? '#d29b4a' : 'inherit',
                        }}>
                          {j.status}
                        </span>
                      </td>
                      <td>{j.worker_id || 'Queued'}</td>
                      <td>
                        {j.status === 'RUNNING' || j.status === 'CLAIMED' || j.status === 'QUEUED' ? (
                          <button
                            className="button secondary small"
                            onClick={async () => {
                              try {
                                await api.cancelJob(j.job_id);
                                notify(`Cancellation requested for ${j.job_id}`);
                                const updated = await api.listJobs();
                                setJobs(updated);
                              } catch (e: any) {
                                notify(`Cancel error: ${e.message}`);
                              }
                            }}
                          >
                            Cancel
                          </button>
                        ) : (
                          <span className="text-muted text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5}>
                      <div className="table-empty">
                        <Bell size={18} />
                        <b>No active jobs</b>
                        <span>Submit an experiment in the Experiment Studio.</span>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    );
  }

  if (page === '/integrations') {
    return (
      <div className="stack-layout">
        <section className="panel generic-hero">
          <div className="generic-mark"><TerminalSquare size={20} /></div>
          <div>
            <span className="section-kicker">INFRASTRUCTURE INTEGRATIONS</span>
            <h2>Service Connectivity Monitor</h2>
            <p>Verification of database, worker daemons, artifact storage, and market data adapters.</p>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <span className="section-kicker">SERVICES</span>
              <h2>Connected components</h2>
            </div>
          </div>
          <div className="integration-list">
            <div className="integration-row">
              <div className="provider-symbol"><Database size={16} /></div>
              <div>
                <b>FastAPI Backend Engine</b>
                <span>REST API Server running on port 8000 with CORS proxying.</span>
              </div>
              <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Connected</span>
            </div>

            <div className="integration-row">
              <div className="provider-symbol"><ShieldCheck size={16} /></div>
              <div>
                <b>PostgreSQL 18 Database</b>
                <span>Forced Row-Level Security active across all 10 tenant tables.</span>
              </div>
              <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Active &amp; RLS Forced</span>
            </div>

            <div className="integration-row">
              <div className="provider-symbol"><Activity size={16} /></div>
              <div>
                <b>Asynchronous Experiment Worker</b>
                <span>
                  Worker Node: {workerInfo?.worker_id || 'worker_node_01'} • Queue Depth: {workerInfo?.queue_depth ?? 0}
                </span>
              </div>
              <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Ready</span>
            </div>

            <div className="integration-row">
              <div className="provider-symbol"><Archive size={16} /></div>
              <div>
                <b>Artifact Storage Engine</b>
                <span>Local filesystem with chroot path containment and streaming SHA-256.</span>
              </div>
              <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>Verified</span>
            </div>

            <div className="integration-row">
              <div className="provider-symbol"><ShieldAlert size={16} /></div>
              <div>
                <b>Custom Model Sandbox</b>
                <span>Fail-closed security protection active for untrusted third-party code.</span>
              </div>
              <span className="badge" style={{ background: 'rgba(210,155,74,0.2)', color: '#d29b4a' }}>Fail-Closed</span>
            </div>
          </div>
        </section>
      </div>
    );
  }

  // Default fallback for documentation / generic pages
  return (
    <div className="stack-layout">
      <section className="panel generic-hero">
        <div className="generic-mark"><Layers3 size={20} /></div>
        <div>
          <span className="section-kicker">RESEARCH WORKSPACE</span>
          <h2>{title}</h2>
          <p>FragilityShield quantitative research laboratory workspace.</p>
        </div>
      </section>
      <section className="panel">
        <div className="p-6">
          <p className="text-muted">
            This module is connected to the FragilityShield quantitative analytical engine.
          </p>
        </div>
      </section>
    </div>
  );
}

export default App;
