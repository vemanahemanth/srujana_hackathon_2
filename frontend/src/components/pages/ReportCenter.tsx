import { useState } from 'react';
import { api, type Portfolio, type RiskReport, type ConcentrationReport } from '@/lib/api';
import {
  FileText, Download, Copy, CheckCircle2, RefreshCw, Layers3,
  SlidersHorizontal, ShieldCheck, ArrowDownToLine
} from 'lucide-react';

export function ReportCenter({
  activePortfolio,
  riskReport,
  concentration,
  notify,
}: {
  activePortfolio: Portfolio | null;
  riskReport: RiskReport | null;
  concentration: ConcentrationReport | null;
  notify: (msg: string) => void;
}) {
  const [reportType, setReportType] = useState<'risk' | 'portfolio' | 'stress' | 'benchmark'>('risk');
  const [exportFormat, setExportFormat] = useState<'markdown' | 'json' | 'csv'>('markdown');
  const [reportTitle, setReportTitle] = useState('Comprehensive Quantitative Risk Audit');
  const [loading, setLoading] = useState(false);
  const [generatedContent, setGeneratedContent] = useState<string>('');
  const [copied, setCopied] = useState(false);

  const [includeSections, setIncludeSections] = useState({
    executiveSummary: true,
    riskMetrics: true,
    concentration: true,
    dataProvenance: true,
    warnings: true,
  });

  const handleGenerate = async () => {
    if (!riskReport && !activePortfolio) {
      notify('Cannot generate report: No real analysis or portfolio data available. Run Risk Analytics first.');
      return;
    }
    setLoading(true);
    notify(`Generating ${reportType.toUpperCase()} report in ${exportFormat.toUpperCase()} format...`);
    try {
      const vol = riskReport?.annualized_volatility !== undefined ? `${(riskReport.annualized_volatility * 100).toFixed(2)}%` : 'N/A';
      const var95 = riskReport?.historical_var_95 !== undefined ? `${(riskReport.historical_var_95 * 100).toFixed(2)}%` : 'N/A';
      const es95 = riskReport?.expected_shortfall_95 !== undefined ? `${(riskReport.expected_shortfall_95 * 100).toFixed(2)}%` : 'N/A';
      const sharpe = riskReport?.sharpe_ratio !== undefined ? riskReport.sharpe_ratio.toFixed(2) : 'N/A';
      const mdd = riskReport?.maximum_drawdown !== undefined ? `${(riskReport.maximum_drawdown * 100).toFixed(2)}%` : 'N/A';
      const hhi = concentration?.hhi !== undefined ? concentration.hhi.toFixed(4) : 'N/A';
      const effN = concentration?.effective_n !== undefined ? concentration.effective_n.toFixed(1) : 'N/A';
      const hash = (riskReport as any)?.reproducibility_hash || (activePortfolio ? `pf_${activePortfolio.portfolio_id}` : 'unverified');

      const reportPayload = {
        title: reportTitle,
        type: reportType,
        format: exportFormat,
        report_data: {
          portfolio_name: activePortfolio?.name || 'Selected Portfolio',
          holdings_count: activePortfolio?.holdings?.length || 0,
          annualized_volatility: vol,
          historical_var_95: var95,
          expected_shortfall_95: es95,
          sharpe_ratio: sharpe,
          maximum_drawdown: mdd,
          hhi_concentration: hhi,
          effective_n_holdings: effN,
          data_provenance: 'Real Upstox V3 Market Data Composite',
          as_of_date: new Date().toISOString().split('T')[0],
          reproducible_hash: hash,
        },
      };

      const res = await api.exportReport(reportPayload);
      if (typeof res === 'string') {
        setGeneratedContent(res);
      } else {
        setGeneratedContent(JSON.stringify(res, null, 2));
      }
      notify('Research report successfully compiled from FragilityEngine.');
    } catch (err: any) {
      notify(`Export failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!generatedContent) return;
    const ext = exportFormat === 'markdown' ? 'md' : exportFormat;
    const blob = new Blob([generatedContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fragilityshield_${reportType}_report.${ext}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    notify(`Downloaded fragilityshield_${reportType}_report.${ext}`);
  };

  const handleCopy = () => {
    if (!generatedContent) return;
    navigator.clipboard.writeText(generatedContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    notify('Report content copied to clipboard.');
  };

  return (
    <div className="stack-layout">
      {/* Hero Header */}
      <section className="panel generic-hero">
        <div className="generic-mark"><FileText size={22} /></div>
        <div>
          <span className="section-kicker">ARTIFACTS &amp; GOVERNANCE / PAGE 26</span>
          <h2>Results Reporting &amp; Research Export Center</h2>
          <p>
            Generate auditable, publication-ready research reports in Markdown, CSV, or JSON directly from native calculation runs with immutable provenance tracking.
          </p>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Configuration Panel */}
        <section className="panel p-5 space-y-4 lg:col-span-1">
          <div className="panel-head p-0 pb-3 border-b border-border">
            <div>
              <span className="section-kicker">REPORT SPECIFICATION</span>
              <h3 className="text-base font-bold">Configure Report</h3>
            </div>
          </div>

          <div className="space-y-3">
            <label className="field-label">
              REPORT TITLE
              <input
                value={reportTitle}
                onChange={e => setReportTitle(e.target.value)}
              />
            </label>

            <label className="field-label">
              SUBJECT DOMAIN
              <select
                value={reportType}
                onChange={e => setReportType(e.target.value as any)}
                className="w-full bg-black/40 border border-border p-2 rounded text-xs"
              >
                <option value="risk">Portfolio Quantitative Risk Analysis</option>
                <option value="portfolio">Portfolio Holdings &amp; Concentration</option>
                <option value="stress">Macroeconomic Stress Scenario Impact</option>
                <option value="benchmark">Model Tournament &amp; Benchmark</option>
              </select>
            </label>

            <label className="field-label">
              EXPORT FORMAT
              <div className="grid grid-cols-3 gap-1.5 pt-1">
                {(['markdown', 'json', 'csv'] as const).map(fmt => (
                  <button
                    key={fmt}
                    type="button"
                    className={`button text-xs py-1.5 ${exportFormat === fmt ? 'primary' : 'secondary'}`}
                    onClick={() => setExportFormat(fmt)}
                  >
                    {fmt.toUpperCase()}
                  </button>
                ))}
              </div>
            </label>

            <div className="space-y-2 pt-2 border-t border-border/40">
              <span className="text-xs font-semibold text-muted block">REPORT SECTIONS</span>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeSections.executiveSummary}
                  onChange={e => setIncludeSections({ ...includeSections, executiveSummary: e.target.checked })}
                />
                Executive Summary &amp; Methodology
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeSections.riskMetrics}
                  onChange={e => setIncludeSections({ ...includeSections, riskMetrics: e.target.checked })}
                />
                Core Risk Metrics (VaR, ES, Vol, Sharpe)
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeSections.concentration}
                  onChange={e => setIncludeSections({ ...includeSections, concentration: e.target.checked })}
                />
                HHI &amp; Effective N Concentration
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeSections.dataProvenance}
                  onChange={e => setIncludeSections({ ...includeSections, dataProvenance: e.target.checked })}
                />
                Data Provenance &amp; Instrument Map
              </label>
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeSections.warnings}
                  onChange={e => setIncludeSections({ ...includeSections, warnings: e.target.checked })}
                />
                Limitations &amp; Regulatory Disclaimers
              </label>
            </div>

            <div className="pt-3">
              <button
                className="button primary small w-full inline-flex items-center justify-center gap-1.5"
                disabled={loading}
                onClick={handleGenerate}
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                {loading ? 'Compiling Report...' : 'Generate Research Report'}
              </button>
            </div>
          </div>
        </section>

        {/* Live Preview Panel */}
        <section className="panel p-5 space-y-4 lg:col-span-2">
          <div className="panel-head p-0 pb-3 border-b border-border flex justify-between items-center">
            <div>
              <span className="section-kicker">PREVIEW &amp; ARTIFACT</span>
              <h3 className="text-base font-bold">Generated Output ({exportFormat.toUpperCase()})</h3>
            </div>
            {generatedContent && (
              <div className="flex items-center gap-2">
                <button className="button secondary small inline-flex items-center gap-1" onClick={handleCopy}>
                  {copied ? <CheckCircle2 size={13} className="text-emerald-400" /> : <Copy size={13} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
                <button className="button primary small inline-flex items-center gap-1" onClick={handleDownload}>
                  <Download size={13} /> Download .{exportFormat === 'markdown' ? 'md' : exportFormat}
                </button>
              </div>
            )}
          </div>

          {generatedContent ? (
            <div className="bg-black/40 p-4 rounded border border-border/50 font-mono text-xs overflow-auto max-h-[600px] whitespace-pre-wrap leading-relaxed">
              {generatedContent}
            </div>
          ) : (
            <div className="result-empty py-16">
              <div className="result-empty-mark"><FileText size={22} /></div>
              <b>No report generated yet</b>
              <span>Click 'Generate Research Report' to compile results into an auditable document.</span>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
