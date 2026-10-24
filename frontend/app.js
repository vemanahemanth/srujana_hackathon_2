/**
 * FragilityShield — Frontend Application Engine (Phase 9)
 *
 * Implements client-side state management, tab routing, SVG chart rendering,
 * and direct REST API orchestration with the backend quantitative engine.
 */

class FragilityShieldApp {
  constructor() {
    this.state = {
      activeTab: 'overview',
      portfolio: null,
      concentration: null,
      riskReport: null,
      scenarioResult: null,
      fragilityResult: null,
      benchmarkReport: null,
      backtestReport: null,
      studioReport: null,
      registeredModels: [],
    };

    this.init();
  }

  async init() {
    this.bindEvents();
    await this.fetchEngineHealth();
    await this.loadSamplePortfolio('nse_10l.json');
  }

  bindEvents() {
    // Navigation Tabs
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        if (tab) this.switchTab(tab);
      });
    });

    // Top Bar Quick Actions
    const btnSwitch = document.getElementById('btnSwitchPortfolio');
    if (btnSwitch) {
      btnSwitch.addEventListener('click', () => this.openUploadModal());
    }

    const btnQuickAudit = document.getElementById('btnQuickAudit');
    if (btnQuickAudit) {
      btnQuickAudit.addEventListener('click', () => {
        this.switchTab('fragility');
        this.runFragilityAudit();
      });
    }

    // Portfolio Lab Controls
    const btnLoadSample = document.getElementById('btnLoadSamplePortfolio');
    if (btnLoadSample) {
      btnLoadSample.addEventListener('click', () => this.loadSamplePortfolio('nse_10l.json'));
    }

    const btnOpenUpload = document.getElementById('btnOpenUploadModal');
    if (btnOpenUpload) {
      btnOpenUpload.addEventListener('click', () => this.openUploadModal());
    }

    // Modal controls
    const modalClose = document.getElementById('btnCloseUploadModal');
    const modalCancel = document.getElementById('btnCancelUpload');
    if (modalClose) modalClose.addEventListener('click', () => this.closeUploadModal());
    if (modalCancel) modalCancel.addEventListener('click', () => this.closeUploadModal());

    const btnSubmitUpload = document.getElementById('btnSubmitUpload');
    if (btnSubmitUpload) {
      btnSubmitUpload.addEventListener('click', () => this.handlePortfolioUpload());
    }

    // Risk Controls
    const btnRecalcRisk = document.getElementById('btnRecalculateRisk');
    if (btnRecalcRisk) {
      btnRecalcRisk.addEventListener('click', () => this.calculateRisk());
    }

    // Scenario Controls
    const btnExecScenario = document.getElementById('btnExecuteScenario');
    if (btnExecScenario) {
      btnExecScenario.addEventListener('click', () => this.executeScenario());
    }

    // Fragility Controls
    const btnFragility = document.getElementById('btnRunFragilityAudit');
    if (btnFragility) {
      btnFragility.addEventListener('click', () => this.runFragilityAudit());
    }

    // Benchmark Controls
    const btnBenchmark = document.getElementById('btnExecuteBenchmark');
    if (btnBenchmark) {
      btnBenchmark.addEventListener('click', () => this.executeBenchmark());
    }

    // Backtest Controls
    const btnBacktest = document.getElementById('btnRunBacktest');
    if (btnBacktest) {
      btnBacktest.addEventListener('click', () => this.runBacktest());
    }

    // Studio & Export Controls
    const btnRunStudio = document.getElementById('btnRunStudioExp');
    if (btnRunStudio) {
      btnRunStudio.addEventListener('click', () => this.runStudioExperiment());
    }

    const btnExportMd = document.getElementById('btnExportMarkdown');
    if (btnExportMd) {
      btnExportMd.addEventListener('click', () => this.exportCurrentReport('markdown'));
    }

    const btnExportJson = document.getElementById('btnExportJson');
    if (btnExportJson) {
      btnExportJson.addEventListener('click', () => this.exportCurrentReport('json'));
    }
  }

  switchTab(tabId) {
    this.state.activeTab = tabId;

    // Update sidebar navigation active classes
    document.querySelectorAll('.nav-item').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });

    // Update tab panes
    document.querySelectorAll('.tab-pane').forEach(pane => {
      pane.classList.remove('active');
    });

    const targetPane = document.getElementById(`pane-${tabId}`);
    if (targetPane) {
      targetPane.classList.add('active');
    }
  }

  // ============================================================================
  // API Calls & Data Loaders
  // ============================================================================

  async fetchEngineHealth() {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      if (data.success) {
        this.state.registeredModels = data.registered_models || [];
        this.renderRegisteredModels();
      }
    } catch (err) {
      console.warn('Engine health fetch error:', err);
    }
  }

  async loadSamplePortfolio(sampleId = 'nse_10l.json') {
    try {
      const res = await fetch(`/api/portfolios/sample?id=${encodeURIComponent(sampleId)}`);
      const data = await res.json();
      if (data.success) {
        this.state.portfolio = data.portfolio;
        this.state.concentration = data.concentration;
        this.updateTopContextBar();
        this.renderPortfolioLab();
        this.renderOverview();
        
        // Auto-run baseline risk, scenario, and fragility audit
        await this.calculateRisk();
        await this.executeScenario();
        await this.runFragilityAudit();
        await this.executeBenchmark();
      } else {
        alert(`Failed to load sample portfolio: ${data.error}`);
      }
    } catch (err) {
      console.error('Sample portfolio load error:', err);
    }
  }

  async handlePortfolioUpload() {
    const format = document.getElementById('uploadFormat').value;
    const content = document.getElementById('uploadContent').value.trim();
    const errorEl = document.getElementById('uploadError');
    errorEl.style.display = 'none';

    if (!content) {
      errorEl.textContent = 'Please paste valid JSON or CSV content.';
      errorEl.style.display = 'block';
      return;
    }

    try {
      const res = await fetch('/api/portfolios/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format, content }),
      });
      const data = await res.json();

      if (data.success) {
        this.state.portfolio = data.portfolio;
        this.state.concentration = data.concentration;
        this.closeUploadModal();
        this.updateTopContextBar();
        this.renderPortfolioLab();
        this.renderOverview();
        await this.calculateRisk();
        await this.executeScenario();
        await this.runFragilityAudit();
      } else {
        errorEl.textContent = data.error || 'Portfolio validation failed.';
        errorEl.style.display = 'block';
      }
    } catch (err) {
      errorEl.textContent = `Upload error: ${err.message}`;
      errorEl.style.display = 'block';
    }
  }

  async calculateRisk() {
    try {
      const conf = parseFloat(document.getElementById('riskConfidence')?.value || 0.95);
      const res = await fetch('/api/risk/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confidence_level: conf }),
      });
      const data = await res.json();
      if (data.success) {
        this.state.riskReport = data;
        this.renderRiskLab();
        this.renderOverview();
      }
    } catch (err) {
      console.error('Risk calculation error:', err);
    }
  }

  async executeScenario() {
    if (!this.state.portfolio) return;
    try {
      const presetId = document.getElementById('scenarioPreset')?.value || 'banking_minus_20_it_minus_10';
      const res = await fetch('/api/scenarios/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          portfolio: this.state.portfolio,
          preset_id: presetId === 'custom' ? 'banking_minus_20_it_minus_10' : presetId,
        }),
      });
      const data = await res.json();
      if (data.success) {
        this.state.scenarioResult = data.scenario_result;
        this.renderScenarioLab();
        this.renderOverview();
      }
    } catch (err) {
      console.error('Scenario execution error:', err);
    }
  }

  async runFragilityAudit() {
    try {
      const res = await fetch('/api/fragility/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          portfolio: this.state.portfolio,
          friction_bps: 10.0,
          decay_factor: 0.94,
        }),
      });
      const data = await res.json();
      if (data.success) {
        this.state.fragilityResult = data;
        this.renderFragilityLab();
        this.renderOverview();
      }
    } catch (err) {
      console.error('Fragility audit error:', err);
    }
  }

  async executeBenchmark() {
    try {
      const res = await fetch('/api/benchmarks/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plugin_ids: ['builtin.parametric_gaussian', 'builtin.historical_simulation', 'builtin.ewma'],
          metrics_to_compare: ['var_95', 'volatility_annualized'],
          target_ranking_metric: 'var_95',
          ranking_direction: 'lower_is_better',
          evaluation_mode: 'in_sample_descriptive',
        }),
      });
      const data = await res.json();
      if (data.success) {
        this.state.benchmarkReport = data.report;
        this.renderBenchmarkLab();
        this.renderOverview();
      }
    } catch (err) {
      console.error('Benchmark execution error:', err);
    }
  }

  async runBacktest() {
    try {
      const modelId = document.getElementById('btModelSelect')?.value || 'builtin.parametric_gaussian';
      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_id: modelId,
          estimation_window: 40,
          confidence_level: 0.95,
        }),
      });
      const data = await res.json();
      if (data.success) {
        this.state.backtestReport = data.report;
        this.renderBacktestLab();
        this.renderOverview();
      } else {
        alert(`Backtest error: ${data.error}`);
      }
    } catch (err) {
      console.error('Backtest error:', err);
    }
  }

  async runStudioExperiment() {
    try {
      const res = await fetch('/api/studio/experiment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          experiment_id: `studio_run_${Date.now()}`,
          name: 'Interactive Studio Audit Run',
        }),
      });
      const data = await res.json();
      if (data.success) {
        this.state.studioReport = data.report;
        const previewEl = document.getElementById('stReportPreview');
        if (previewEl) {
          previewEl.textContent = data.markdown_preview || JSON.stringify(data.report, null, 2);
        }
        const badgeEl = document.getElementById('stStatusBadge');
        if (badgeEl) {
          badgeEl.textContent = data.report.status?.toUpperCase() || 'COMPLETED';
          badgeEl.className = 'card-badge badge-success';
        }
      }
    } catch (err) {
      console.error('Studio experiment error:', err);
    }
  }

  async exportCurrentReport(format = 'markdown') {
    const reportData = this.state.benchmarkReport || this.state.backtestReport;
    const reportType = this.state.backtestReport && this.state.activeTab === 'backtest' ? 'backtest' : 'benchmark';

    if (!reportData) {
      alert('Please run a benchmark or backtest first before exporting.');
      return;
    }

    try {
      const res = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: reportType,
          format: format,
          report_data: reportData,
        }),
      });

      const text = await res.text();
      const blob = new Blob([text], { type: format === 'json' ? 'application/json' : 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fragilityshield_${reportType}_report.${format === 'json' ? 'json' : 'md'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
    }
  }

  // ============================================================================
  // DOM Renderers
  // ============================================================================

  updateTopContextBar() {
    const p = this.state.portfolio;
    const c = this.state.concentration;
    if (!p) return;

    document.getElementById('topPortfolioName').textContent = p.name || p.portfolio_id;
    document.getElementById('topPortfolioValuation').textContent = this.formatCurrency(p.total_value, p.currency);
    document.getElementById('topHoldingsCount').textContent = `${p.holdings.length} assets`;

    const hhiPts = c?.hhi_asset_points ?? 0;
    const badge = document.getElementById('topHhiBadge');
    badge.textContent = `${hhiPts} pts (${hhiPts < 1500 ? 'Diverse' : hhiPts <= 2500 ? 'Moderate' : 'Concentrated'})`;
  }

  renderOverview() {
    const p = this.state.portfolio;
    const c = this.state.concentration;
    const r = this.state.riskReport?.report;
    const s = this.state.scenarioResult;
    const f = this.state.fragilityResult;

    if (p) {
      document.getElementById('ovPortfolioValue').textContent = this.formatCurrency(p.total_value, p.currency);
      document.getElementById('ovPortfolioCurrency').textContent = `${p.currency} • ${p.holdings.length} Positions`;
    }

    if (c) {
      const assetPts = c.asset_hhi_points ?? c.hhi_asset_points ?? 0;
      const sectorPts = c.sector_hhi_points ?? c.hhi_sector_points ?? 0;
      const secWeights = c.sector_weights ?? c.sector_proportions ?? {};
      const secVals = c.sector_market_values ?? c.sector_allocations ?? {};

      document.getElementById('ovHhiPoints').textContent = `${Math.round(assetPts)} pts`;
      document.getElementById('ovHhiInterpretation').textContent = `Sector HHI: ${Math.round(sectorPts)} pts`;
      this.renderSectorDonutChart('ovSectorChart', 'ovSectorLegend', secWeights);
      document.getElementById('ovSectorCount').textContent = `${Object.keys(secVals).length} Sectors`;
    }

    if (r) {
      const vol = r.volatility_annualized ?? r.annualized_volatility ?? 0;
      const v95 = r.var_95 ?? r.historical_var_95 ?? 0;
      const es95 = r.expected_shortfall_95 ?? 0;

      document.getElementById('ovAnnualVol').textContent = `${(vol * 100).toFixed(2)}%`;
      document.getElementById('ovVar95').textContent = `${(v95 * 100).toFixed(2)}%`;
      document.getElementById('ovEs95').textContent = `${(es95 * 100).toFixed(2)}%`;
    }

    if (s) {
      const pnlLoss = s.total_pnl_impact ?? s.loss_magnitude ?? 0;
      const ret = s.percentage_pnl ?? s.scenario_return ?? 0;
      document.getElementById('ovScenarioPnl').textContent = `P&L: -${this.formatCurrency(Math.abs(pnlLoss))} (${(ret * 100).toFixed(2)}%)`;
    }

    if (f) {
      const volExp = f.experiments?.find(e => e.perturbation_id === 'volatility_estimator');
      if (volExp) {
        const delta = volExp.absolute_changes?.volatility_annualized ?? 0;
        document.getElementById('ovVolGap').textContent = `Δ: ${(delta * 100 >= 0 ? '+' : '')}${(delta * 100).toFixed(2)}%`;
      }
      const confExp = f.experiments?.find(e => e.perturbation_id === 'confidence_level_shift');
      if (confExp) {
        const deltaVar = confExp.absolute_changes?.var ?? confExp.absolute_changes?.var_95 ?? 0;
        document.getElementById('ovTailGap').textContent = `Δ: +${(deltaVar * 100).toFixed(2)}%`;
      }
      if (f.liquidation_shock) {
        document.getElementById('ovLiquidationCost').textContent = `-₹${f.liquidation_shock.liquidation_cost?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
      }
    }

    // Benchmark Rankings mini list
    const bm = this.state.benchmarkReport;
    const bmRankingsEl = document.getElementById('ovBenchmarkRankings');
    if (bm && bm.rankings && bmRankingsEl) {
      bmRankingsEl.innerHTML = bm.rankings.map(rnk => `
        <div class="highlight-item">
          <span><strong>Rank ${rnk.rank}:</strong> ${rnk.model_name}</span>
          <span class="mono">${(rnk.metric_value * 100).toFixed(2)}% (${rnk.interpretation})</span>
        </div>
      `).join('');
    }

    // Backtest mini stats
    const bt = this.state.backtestReport;
    if (bt) {
      document.getElementById('ovKupiecStatus').textContent = bt.kupiec_test?.decision === 'ACCEPT_NULL' ? 'CALIBRATED' : 'REJECTED';
      document.getElementById('ovKupiecStatus').className = bt.kupiec_test?.decision === 'ACCEPT_NULL' ? 'kpi-mini-value text-emerald' : 'kpi-mini-value text-rose';
      document.getElementById('ovBreachRate').textContent = `${(bt.observed_breach_rate * 100).toFixed(2)}%`;
      document.getElementById('ovChrisStatus').textContent = bt.christoffersen_test?.decision_independence === 'ACCEPT_NULL' ? 'INDEPENDENT' : 'CLUSTERED';
    }
  }

  renderPortfolioLab() {
    const p = this.state.portfolio;
    const c = this.state.concentration;
    if (!p) return;

    document.getElementById('plTotalValuation').textContent = this.formatCurrency(p.total_value, p.currency);
    document.getElementById('plHoldingsBadge').textContent = `${p.holdings.length} Positions`;

    if (c) {
      const assetDec = c.asset_hhi_decimal ?? c.hhi_asset_decimal ?? 0;
      const assetPts = c.asset_hhi_points ?? c.hhi_asset_points ?? 0;
      const secDec = c.sector_hhi_decimal ?? c.hhi_sector_decimal ?? 0;
      const secPts = c.sector_hhi_points ?? c.hhi_sector_points ?? 0;

      document.getElementById('plAssetHhi').textContent = Number(assetDec).toFixed(4);
      document.getElementById('plAssetHhiMeta').textContent = `HHI: ${Math.round(assetPts)} points • ${assetPts < 1500 ? 'Low Concentration' : 'Moderate Concentration'}`;
      document.getElementById('plSectorHhi').textContent = Number(secDec).toFixed(4);
      document.getElementById('plSectorHhiMeta').textContent = `HHI: ${Math.round(secPts)} points • Sector Level`;

      const secWeights = c.sector_weights ?? c.sector_proportions ?? {};
      this.renderSectorDonutChart('plSectorChart', 'plSectorLegend', secWeights);
    }

    const tbody = document.getElementById('plHoldingsTbody');
    tbody.innerHTML = p.holdings.map(h => {
      const weight = p.total_value > 0 ? (h.market_value / p.total_value) * 100 : 0;
      return `
        <tr>
          <td><strong>${h.asset_id}</strong></td>
          <td><span class="legend-chip">${h.sector || 'Unclassified'}</span></td>
          <td class="text-right mono">${h.quantity.toLocaleString()}</td>
          <td class="text-right mono">₹${Number(h.price).toFixed(2)}</td>
          <td class="text-right mono font-semibold">₹${Number(h.market_value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
          <td class="text-right mono text-cyan">${weight.toFixed(2)}%</td>
        </tr>
      `;
    }).join('');
  }

  renderRiskLab() {
    const r = this.state.riskReport?.report;
    if (!r) return;

    const vol = r.volatility_annualized ?? r.annualized_volatility ?? 0;
    const dailyVol = r.volatility_daily ?? r.daily_volatility ?? 0;
    const v95 = r.var_95 ?? r.historical_var_95 ?? 0;
    const es95 = r.expected_shortfall_95 ?? 0;
    const dd = r.drawdown ?? r.max_drawdown ?? {};
    const mdd = dd.max_drawdown ?? dd.maximum_drawdown ?? 0;

    document.getElementById('rkAnnualVol').textContent = `${(vol * 100).toFixed(2)}%`;
    document.getElementById('rkDailyVol').textContent = `Daily StdDev: ${(dailyVol * 100).toFixed(3)}%`;
    document.getElementById('rkVarVal').textContent = `${(v95 * 100).toFixed(2)}%`;
    document.getElementById('rkEsVal').textContent = `${(es95 * 100).toFixed(2)}%`;
    document.getElementById('rkMddVal').textContent = `${(mdd * 100).toFixed(2)}%`;
    document.getElementById('rkMddDur').textContent = `Peak-to-Trough: ${dd.peak_to_trough_duration ?? 0}d • Recovery: ${dd.recovery_duration ?? 'Unrecovered'}d`;

    // Render Equity & Drawdown SVG chart
    const curve = this.state.riskReport?.equity_curve || [];
    this.renderEquityChart('rkEquityChart', curve);
  }

  renderScenarioLab() {
    const s = this.state.scenarioResult;
    if (!s) return;

    document.getElementById('scOriginalValue').textContent = `₹${s.original_portfolio_value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    document.getElementById('scStressedValue').textContent = `₹${s.stressed_portfolio_value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    document.getElementById('scTotalPnl').textContent = `-₹${s.loss_magnitude.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    document.getElementById('scReturnMeta').textContent = `Scenario Return: ${(s.scenario_return * 100).toFixed(2)}%`;

    const tbody = document.getElementById('scSectorTbody');
    if (s.sector_results && tbody) {
      tbody.innerHTML = s.sector_results.map(sec => {
        const pctLoss = s.loss_magnitude > 0 ? (Math.max(0, -sec.pnl_contribution) / s.loss_magnitude) * 100 : 0;
        return `
          <tr>
            <td><strong>${sec.sector}</strong></td>
            <td class="text-right mono">₹${sec.original_market_value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
            <td class="text-right mono text-rose">${(sec.average_applied_shock * 100).toFixed(1)}%</td>
            <td class="text-right mono">₹${sec.stressed_market_value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
            <td class="text-right mono text-rose">-₹${Math.abs(sec.pnl_contribution).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
            <td class="text-right mono">${pctLoss.toFixed(1)}%</td>
          </tr>
        `;
      }).join('');
    }
  }

  renderFragilityLab() {
    const f = this.state.fragilityResult;
    if (!f) return;

    // Render Tornado Sensitivity Chart
    const ranking = f.sensitivity_rankings?.volatility_annualized;
    if (ranking && ranking.ranked_impacts) {
      this.renderTornadoChart('fragilityTornadoChart', ranking.ranked_impacts);
    }

    // Populate experiments table
    const tbody = document.getElementById('fragilityExpTbody');
    if (f.experiments && tbody) {
      document.getElementById('fragilityExpCount').textContent = `${f.experiments.length} Experiments`;
      tbody.innerHTML = f.experiments.map(exp => {
        const metricKey = Object.keys(exp.baseline_metrics)[0];
        const m0 = exp.baseline_metrics[metricKey];
        const m1 = exp.perturbed_metrics[metricKey];
        const absChg = exp.absolute_changes[metricKey] ?? (m1 - m0);
        const relChg = exp.relative_changes[metricKey];

        return `
          <tr>
            <td><strong>${exp.perturbation_name}</strong></td>
            <td class="text-sm text-muted">${exp.description}</td>
            <td class="text-right mono">${(m0 * 100).toFixed(2)}%</td>
            <td class="text-right mono">${(m1 * 100).toFixed(2)}%</td>
            <td class="text-right mono font-semibold ${absChg >= 0 ? 'text-amber' : 'text-cyan'}">${(absChg * 100 >= 0 ? '+' : '')}${(absChg * 100).toFixed(2)}%</td>
            <td class="text-right mono">${relChg !== null ? `${(relChg * 100 >= 0 ? '+' : '')}${(relChg * 100).toFixed(1)}%` : 'N/A'}</td>
            <td><span class="badge-success">COMPLETED</span></td>
          </tr>
        `;
      }).join('');
    }
  }

  renderBenchmarkLab() {
    const bm = this.state.benchmarkReport;
    if (!bm) return;

    document.getElementById('bmInputFp').textContent = bm.input_fingerprint ? bm.input_fingerprint.substring(0, 16) + '...' : 'None';
    document.getElementById('bmConfigFp').textContent = bm.configuration_fingerprint ? bm.configuration_fingerprint.substring(0, 16) + '...' : 'None';
    document.getElementById('bmOutputFp').textContent = bm.output_fingerprint ? bm.output_fingerprint.substring(0, 16) + '...' : 'None';

    const tbody = document.getElementById('bmRankingsTbody');
    if (bm.rankings && tbody) {
      tbody.innerHTML = bm.rankings.map(r => `
        <tr>
          <td class="text-center font-bold">${r.rank}</td>
          <td><span class="mono">${r.plugin_id}</span></td>
          <td><strong>${r.model_name}</strong></td>
          <td class="text-right mono font-semibold text-cyan">${(r.metric_value * 100).toFixed(2)}%</td>
          <td>${r.unit}</td>
          <td><span class="legend-chip">${r.interpretation}</span></td>
          <td class="text-center">${r.tied ? 'Yes' : 'No'}</td>
        </tr>
      `).join('');
    }
  }

  renderBacktestLab() {
    const bt = this.state.backtestReport;
    if (!bt) return;

    const kup = bt.kupiec_test;
    const chris = bt.christoffersen_test;

    document.getElementById('btKupiecDecision').textContent = kup?.decision === 'ACCEPT_NULL' ? 'CALIBRATED (ACCEPT H0)' : 'REJECTED';
    document.getElementById('btKupiecDecision').className = kup?.decision === 'ACCEPT_NULL' ? 'kpi-value text-emerald' : 'kpi-value text-rose';
    document.getElementById('btKupiecPval').textContent = `P-Value: ${kup?.p_value.toFixed(6)} (LR=${kup?.likelihood_ratio.toFixed(3)})`;

    document.getElementById('btObservedRate').textContent = `${(bt.observed_breach_rate * 100).toFixed(2)}%`;
    document.getElementById('btBreachCount').textContent = `${bt.breach_count} breaches / ${bt.evaluation_sample_size} periods`;

    document.getElementById('btChrisDecision').textContent = chris?.decision_independence === 'ACCEPT_NULL' ? 'INDEPENDENT (ACCEPT H0)' : 'CLUSTERED';
    document.getElementById('btChrisDecision').className = chris?.decision_independence === 'ACCEPT_NULL' ? 'kpi-value text-emerald' : 'kpi-value text-rose';
    document.getElementById('btChrisPval').textContent = `P-Value: ${chris?.p_value_independence.toFixed(6)} (LR=${chris?.lr_independence.toFixed(3)})`;

    // Contingency matrix
    const ctg = chris?.contingency_matrix || {};
    document.getElementById('btN00').textContent = ctg.n00 ?? 0;
    document.getElementById('btN01').textContent = ctg.n01 ?? 0;
    document.getElementById('btN10').textContent = ctg.n10 ?? 0;
    document.getElementById('btN11').textContent = ctg.n11 ?? 0;

    // Breach timeline visualizer
    this.renderBreachTimeline('btBreachTimeline', bt.breach_evaluations || []);
  }

  renderRegisteredModels() {
    const el = document.getElementById('bmRegisteredModelsList');
    if (!el || !this.state.registeredModels) return;

    el.innerHTML = this.state.registeredModels.map(m => `
      <div class="highlight-item">
        <div>
          <strong>${m.name}</strong> <span class="mono text-muted text-xs">(${m.plugin_id})</span>
          <p class="text-muted text-xs">${m.description}</p>
        </div>
        <span class="badge-accent">v${m.version}</span>
      </div>
    `).join('');
  }

  // ============================================================================
  // Lightweight SVG Visualizations
  // ============================================================================

  renderSectorDonutChart(containerId, legendId, sectorProportions = {}) {
    const container = document.getElementById(containerId);
    const legend = document.getElementById(legendId);
    if (!container || !sectorProportions) return;

    const entries = Object.entries(sectorProportions);
    if (entries.length === 0) {
      container.innerHTML = '<span class="text-muted text-sm">No sector data</span>';
      return;
    }

    const colors = ['#6366f1', '#06b6d4', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#3b82f6'];
    let accumulatedAngle = 0;
    const slices = [];

    entries.forEach(([sector, pct], idx) => {
      const angle = pct * 360;
      const color = colors[idx % colors.length];
      slices.push({ sector, pct, color, startAngle: accumulatedAngle, endAngle: accumulatedAngle + angle });
      accumulatedAngle += angle;
    });

    // Generate SVG Donut
    const size = 180;
    const center = size / 2;
    const radius = 70;
    const innerRadius = 45;

    let paths = '';
    slices.forEach(s => {
      const p = this.describeDonutSlice(center, center, radius, innerRadius, s.startAngle, s.endAngle);
      paths += `<path d="${p}" fill="${s.color}" opacity="0.9"><title>${s.sector}: ${(s.pct * 100).toFixed(1)}%</title></path>`;
    });

    container.innerHTML = `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        ${paths}
        <circle cx="${center}" cy="${center}" r="${innerRadius}" fill="var(--bg-card)"></circle>
        <text x="${center}" y="${center + 4}" text-anchor="middle" fill="#fff" font-size="12" font-weight="700">${entries.length} Sectors</text>
      </svg>
    `;

    if (legend) {
      legend.innerHTML = slices.map(s => `
        <span class="legend-chip">
          <span class="legend-color" style="background-color: ${s.color};"></span>
          ${s.sector}: ${(s.pct * 100).toFixed(1)}%
        </span>
      `).join('');
    }
  }

  describeDonutSlice(cx, cy, r, ir, startAngle, endAngle) {
    const toRad = a => (a - 90) * Math.PI / 180.0;
    const x1 = cx + r * Math.cos(toRad(startAngle));
    const y1 = cy + r * Math.sin(toRad(startAngle));
    const x2 = cx + r * Math.cos(toRad(endAngle - 0.01));
    const y2 = cy + r * Math.sin(toRad(endAngle - 0.01));

    const ix1 = cx + ir * Math.cos(toRad(endAngle - 0.01));
    const iy1 = cy + ir * Math.sin(toRad(endAngle - 0.01));
    const ix2 = cx + ir * Math.cos(toRad(startAngle));
    const iy2 = cy + ir * Math.sin(toRad(startAngle));

    const largeArc = (endAngle - startAngle) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} L ${ix1} ${iy1} A ${ir} ${ir} 0 ${largeArc} 0 ${ix2} ${iy2} Z`;
  }

  renderEquityChart(containerId, curve = []) {
    const el = document.getElementById(containerId);
    if (!el || curve.length === 0) return;

    const w = 700;
    const h = 240;
    const pad = 35;

    const minVal = Math.min(...curve) * 0.98;
    const maxVal = Math.max(...curve) * 1.02;

    const points = curve.map((val, idx) => {
      const x = pad + (idx / (curve.length - 1)) * (w - 2 * pad);
      const y = h - pad - ((val - minVal) / (maxVal - minVal)) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const fillPoints = `${pad},${h - pad} ${points} ${w - pad},${h - pad}`;

    el.innerHTML = `
      <svg width="100%" height="100%" viewBox="0 0 ${w} ${h}">
        <defs>
          <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.3"/>
            <stop offset="100%" stop-color="#06b6d4" stop-opacity="0.0"/>
          </linearGradient>
        </defs>
        <!-- Axes -->
        <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="var(--border-subtle)" stroke-width="1"/>
        <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="var(--border-subtle)" stroke-width="1"/>
        <!-- Area & Line -->
        <polygon points="${fillPoints}" fill="url(#eqGrad)"/>
        <polyline points="${points}" fill="none" stroke="#06b6d4" stroke-width="2" stroke-linejoin="round"/>
        <!-- Labels -->
        <text x="${pad}" y="${pad - 10}" fill="var(--text-dim)" font-size="10">${maxVal.toFixed(2)}x</text>
        <text x="${pad}" y="${h - pad + 15}" fill="var(--text-dim)" font-size="10">Day 1</text>
        <text x="${w - pad - 20}" y="${h - pad + 15}" fill="var(--text-dim)" font-size="10">Day ${curve.length}</text>
      </svg>
    `;
  }

  renderTornadoChart(containerId, impacts = []) {
    const el = document.getElementById(containerId);
    if (!el || impacts.length === 0) return;

    const maxAbs = Math.max(...impacts.map(i => Math.abs(i.absolute_change)), 0.001);

    el.innerHTML = `
      <div style="width: 100%; display: flex; flex-direction: column; gap: 0.65rem;">
        ${impacts.map(imp => {
          const pctWidth = (Math.abs(imp.absolute_change) / maxAbs) * 100;
          const isUp = imp.absolute_change >= 0;
          return `
            <div style="display: flex; align-items: center; gap: 1rem; font-size: 0.8rem;">
              <span style="width: 180px; font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                ${imp.perturbation_name}
              </span>
              <div style="flex: 1; height: 16px; background: var(--bg-surface-subtle); border-radius: var(--radius-sm); position: relative; overflow: hidden;">
                <div style="width: ${pctWidth}%; height: 100%; background: ${isUp ? 'var(--accent-amber)' : 'var(--accent-cyan)'}; border-radius: var(--radius-sm); transition: width 0.3s ease;"></div>
              </div>
              <span class="mono" style="width: 70px; text-align: right; color: ${isUp ? 'var(--accent-amber)' : 'var(--accent-cyan)'}; font-weight: 600;">
                ${isUp ? '+' : ''}${(imp.absolute_change * 100).toFixed(2)}%
              </span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  renderBreachTimeline(containerId, breachEvals = []) {
    const el = document.getElementById(containerId);
    if (!el || breachEvals.length === 0) {
      el.innerHTML = '<span class="text-muted text-sm">Execute backtest to view timeline.</span>';
      return;
    }

    el.innerHTML = `
      <div style="display: flex; gap: 4px; align-items: flex-end; height: 90px; padding-top: 10px; overflow-x: auto;">
        ${breachEvals.map((b, idx) => {
          const isB = b.is_breach;
          const height = isB ? 65 : 22;
          const color = isB ? 'var(--accent-rose)' : 'var(--border-subtle)';
          return `
            <div style="flex: 1; min-width: 8px; height: ${height}px; background-color: ${color}; border-radius: 2px;"
                 title="Period ${b.forecast?.target_index ?? idx}: Return=${(b.realized_return * 100).toFixed(2)}%, Loss=${(b.realized_loss * 100).toFixed(2)}%, VaR=${(b.forecast?.var_estimate * 100).toFixed(2)}% ${isB ? '-> BREACH!' : ''}">
            </div>
          `;
        }).join('')}
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-dim); margin-top: 0.5rem;">
        <span>Out-of-sample start</span>
        <span style="color: var(--accent-rose); font-weight: 600;">Red bars denote strict loss breaches (L &gt; VaR)</span>
        <span>Out-of-sample end (${breachEvals.length} periods)</span>
      </div>
    `;
  }

  // ============================================================================
  // Modal Helpers
  // ============================================================================

  openUploadModal() {
    const modal = document.getElementById('uploadModal');
    if (modal) modal.classList.add('active');
  }

  closeUploadModal() {
    const modal = document.getElementById('uploadModal');
    if (modal) modal.classList.remove('active');
  }

  formatCurrency(val, currency = 'INR') {
    const symbol = currency === 'INR' ? '₹' : '$';
    const num = typeof val === 'number' && !isNaN(val) ? val : 0;
    return `${symbol}${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
}

// Global bootstrap
document.addEventListener('DOMContentLoaded', () => {
  window.app = new FragilityShieldApp();
});
