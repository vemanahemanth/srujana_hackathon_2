# Page 02: Market Terminal — Inspection, Correction, and Verification Report

**Component Route:** `/market` (also supporting deep links `/market/instrument/:instrumentId`)  
**Page Title:** Market Terminal: All Supported Market Instruments  
**Audit & Implementation Date:** 2026-10-25  
**Engine:** FragilityShield Quantitative Risk Engine (FastAPI + Upstox Market Data V3 + Native Math Kernels)  
**Status:** **PASS** (All 8 Core Functional Tabs and Workspace Sections Verified End-to-End)

---

## 1. Existing Functionality Discovered During Inspection

Before correction, the original `/market` route contained several partial components and substantial data policy violations:

1. **Synthetic / Mock Data Violations:**
   - The original `MarketTerminal.tsx` contained `generateSyntheticCandles` which fabricated random daily closing prices using Brownian drift and randomized shocks (`Math.random() - 0.48`).
   - Contained `generateIntradaySimulation` which generated sinusoidal intraday price ticks using `Math.sin()` and `Math.cos()` with random noise.
   - `INITIAL_NIFTY_UNIVERSE` contained hardcoded static prices, volumes, and percentage changes for 50 instruments.
   - When Upstox candle retrieval was uncalibrated or failed, it silently fell back to `generateSyntheticCandles` and claimed: `"Synthesized Research Simulation (Calibrated to NSE Historical Distributions)"`.

2. **Missing Workspace Sections & Tabs:**
   - There was no structured tab navigation for the 8 core functional areas required by the Page 02 specification.
   - The Indices Explorer and Equities Explorer were merged into an incomplete table.
   - Watchlist management was non-existent (users could not create, rename, or delete watchlists, nor persist them to the backend).
   - Category and Sector performance was absent (no sector aggregations, constituent counts, or return heatmaps).
   - Historical Market Data was not accessible as an inspection table, and CSV export of actual retrieved observations was missing.
   - Multi-instrument comparison (normalized performance curve, comparative risk/return summary, Pearson correlation matrix) was completely missing.

3. **Backend & Resolver Gaps:**
   - `UpstoxInstrument` lacked sector metadata (`sector: str`).
   - `UpstoxInstrumentResolver.CURATED_INSTRUMENTS` was limited to ~20 instruments, missing over half of the NIFTY 50 universe.
   - No dedicated endpoint existed to return all resolvable market instruments with authoritative ISIN keys, sectors, and exchange metadata (`/api/market/instruments`).
   - No backend persistence layer existed for watchlists (`/api/market/watchlists`).

---

## 2. Problems Identified and Corrections Implemented

| Area | Discovered Problem | Correction Implemented | File(s) Changed |
| :--- | :--- | :--- | :--- |
| **Real-Data Policy** | Synthetic candle generators (`generateSyntheticCandles`, `generateIntradaySimulation`) manufactured random prices. | Completely removed all synthetic generators. Now fetches genuine historical candles via `/api/upstox/candles` or displays an honest uncalibrated state. | [`MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx) |
| **Hardcoded Prices** | Static numbers hardcoded in `INITIAL_NIFTY_UNIVERSE`. | Replaced with dynamic quote resolution from Upstox V3 Market Data via `/api/upstox/quote`. Fallback values display honest uncalibrated `— —`. | [`MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx) |
| **Instrument Resolution** | Resolver only had ~20 symbols; lacked sectors. | Added `sector: str = "General"` to `UpstoxInstrument` and expanded `CURATED_INSTRUMENTS` to include all NIFTY 50 stocks with verified ISINs and sector tags. | [`backend/fragility_engine/upstox.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/upstox.py) |
| **Catalog API** | No endpoint to list all supported instruments. | Implemented `GET /api/market/instruments` returning all 57 canonical instruments sorted by index then equity symbol. | [`backend/app.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py) |
| **Watchlist Persistence** | No watchlist creation, deletion, or storage. | Built `GET`, `POST`, and `DELETE` endpoints for `/api/market/watchlists` backed by `data/watchlists.json` with client-side fallback. | [`backend/app.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py) |
| **Workspace Navigation** | Fragmented layout missing required sections. | Implemented an 8-tab professional research terminal: Overview, Indices, Equities, Watchlists, Sectors, Details, Historical, Compare. | [`MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx) |
| **Technical Indicators** | Hardcoded or mock indicator parameters. | Implemented real quantitative calculations: SMA 20/50, EMA 9/21, Bollinger Bands (20, 2σ), RSI 14 (Wilder), MACD (12, 26, 9), ATR 14, Rolling Volatility 20d, Momentum 10d. | [`MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx) |
| **Multi-Instrument Compare**| No comparison workspace. | Implemented normalized price curve ($P_t / P_0 \times 100$), comparative total returns, annualized volatility, max drawdown, and Pearson daily return correlation matrix. | [`MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx) |
| **Data Export** | No CSV download for historical records or catalog. | Implemented genuine RFC 4180 CSV export for both the full instruments catalog and historical OHLCV observations. | [`MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx) |

---

## 3. Files Changed and Traceability

1. **[`backend/fragility_engine/upstox.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/upstox.py)**
   - Added `sector: str = "General"` to `UpstoxInstrument` dataclass and its `to_dict()` serialization.
   - Expanded authoritative `CURATED_INSTRUMENTS` to include 57 canonical Indian market instruments:
     - **Indices:** Nifty 50, Nifty Bank, Nifty Financial Services, Nifty Midcap Select, Nifty 100, Nifty 500, Nifty IT.
     - **Equities (Nifty 50):** Reliance, TCS, HDFC Bank, Infosys, ICICI Bank, Bharti Airtel, SBI, ITC, HUL, L&T, Bajaj Finance, Maruti Suzuki, Sun Pharma, Axis Bank, Titan, Kotak Bank, Tata Motors, NTPC, ONGC, Power Grid, Tata Steel, JSW Steel, Adani Enterprises, Adani Ports, Coal India, M&M, Bajaj Finserv, Asian Paints, UltraTech Cement, Wipro, HCL Tech, Dr. Reddy's, Cipla, Trent, BEL, Tech Mahindra, Grasim, Nestle India, Apollo Hospitals, Eicher Motors, Divi's Labs, BPCL, Shree Cement, Hero MotoCorp, Britannia, IndusInd Bank, Tata Consumer, SBI Life, HDFC Life, Bajaj Auto.

2. **[`backend/app.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py)**
   - Registered endpoints:
     - `GET /api/market/instruments`: Returns all resolvable instruments with their ISINs, sectors, exchange, and types.
     - `GET /api/market/watchlists`: Retrieves saved watchlists from `data/watchlists.json`.
     - `POST /api/market/watchlists`: Creates or updates watchlists (add/remove symbols, rename, edit description).
     - `DELETE /api/market/watchlists/{id}`: Deletes watchlists with confirmation.

3. **[`frontend/src/lib/api.ts`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/lib/api.ts)**
   - Added client methods: `listMarketInstruments()`, `listWatchlists()`, `saveWatchlist()`, and `deleteWatchlist()`.

4. **[`frontend/src/components/pages/MarketTerminal.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MarketTerminal.tsx)**
   - Complete architectural implementation of Page 02 Market Terminal across 8 tabs:
     1. `overview`: Live benchmark indices ribbon, Market Breadth (Advances/Declines bar), Top Gainers & Losers, and Equal-Weighted Sector Heatmap.
     2. `indices`: Benchmark & Sectoral indices table with Day High/Low, LTP, % change, and provider instrument key.
     3. `equities`: Searchable, filterable equities table with LTP, change, open, high, low, volume, sector tags, and sorting controls.
     4. `watchlists`: Watchlist workspace supporting multi-watchlist switching, creation modal, delete confirmation, and real-time quotes.
     5. `sectors`: Sector classification cards showing constituent counts, aggregate volume, average return, and constituent tags.
     6. `details`: Deep-dive into selected instrument with live quote snapshot, timeframe buttons (`1W`, `1M`, `3M`, `6M`, `1Y`, `ALL`), chart modes (Area, Line, Candlestick), technical overlays (SMA 20/50, EMA 9/21, Bollinger Bands), and subcharts (Volume, RSI 14, MACD, ATR 14, Rolling Volatility 20d, Momentum 10d).
     7. `historical`: Authenticated OHLCV table in Asia/Kolkata (+05:30) timezone with pagination and RFC 4180 CSV export.
     8. `compare`: Multi-instrument comparison workspace (2 to 4 instruments) with normalized cumulative performance ($P_t / P_0 \times 100$), comparative risk/return summary, and daily return Pearson correlation matrix.

5. **[`backend/tests/test_page_02_market_terminal.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_page_02_market_terminal.py)**
   - Automated test suite verifying instrument listing, watchlist CRUD lifecycle, candle formats, and quote formats.

---

## 4. Real Data Sources & Provider Verification

| Data Field / Section | Real Source | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Provider Connection** | Upstox Market Data V3 (`/v3/market-quote/ltp`) | `/api/upstox/status` connectivity check | **PASS** (Live & Authenticated) |
| **Curated Catalog** | Authoritative Upstox Instrument Resolver | `GET /api/market/instruments` (57 instruments) | **PASS** |
| **Live Quotes** | Upstox Market Data V3 Quote Endpoint | `/api/upstox/quote?symbols=...` | **PASS** (Real LTP, OHL, Close, Volume) |
| **Historical OHLCV** | Upstox V3 `/v3/historical-candle` | `/api/upstox/candles?symbol=...` | **PASS** (Normalized IST ISO timestamps) |
| **Local Catalog Datasets** | `data/catalog/ds_upstox_reliance_2c1be717.csv` | Validated via `validate_financial_ohlcv` | **PASS** (22 authenticated daily candles) |
| **Watchlists** | Server Persistence `data/watchlists.json` | `GET/POST/DELETE /api/market/watchlists` | **PASS** (Thread-safe JSON store) |
| **Downstream Labs** | Risk Attribution, Stress Testing, Backtesting | Deep link routing (`/risk-models`, `/stress-testing`, `/backtest`) | **PASS** |

---

## 5. Quantitative Technical Indicator Definitions & Math

All indicators in the terminal are derived strictly from genuine historical observations:

1. **Simple Moving Average (SMA $N$):**
   $$\text{SMA}_t(N) = \frac{1}{N} \sum_{i=0}^{N-1} C_{t-i}$$
   Implemented for $N = 20$ and $N = 50$. Requires at least $N$ observations; returns `undefined` otherwise.

2. **Exponential Moving Average (EMA $N$):**
   $$\text{EMA}_t(N) = C_t \times k + \text{EMA}_{t-1} \times (1 - k), \quad k = \frac{2}{N + 1}$$
   Implemented for $N = 9$ and $N = 21$.

3. **Bollinger Bands ($N=20, k=2$):**
   $$\text{Upper} = \text{SMA}_{20} + 2 \times \sigma_{20}, \quad \text{Lower} = \text{SMA}_{20} - 2 \times \sigma_{20}$$

4. **Relative Strength Index (RSI 14, Wilder's Smoothing):**
   $$\text{RSI} = 100 - \frac{100}{1 + \text{RS}}, \quad \text{RS} = \frac{\text{Average Gain}_{14}}{\text{Average Loss}_{14}}$$
   Overbought threshold line rendered at 70, oversold threshold line at 30.

5. **Moving Average Convergence Divergence (MACD 12, 26, 9):**
   $$\text{MACD Line} = \text{EMA}_{12}(C) - \text{EMA}_{26}(C)$$
   $$\text{Signal Line} = \text{EMA}_9(\text{MACD}), \quad \text{Histogram} = \text{MACD} - \text{Signal}$$

6. **Average True Range (ATR 14):**
   $$\text{TR}_t = \max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|), \quad \text{ATR}_{14} = \frac{1}{14} \sum_{i=0}^{13} \text{TR}_{t-i}$$

7. **Rolling Volatility (20-day Annualized %):**
   $$\sigma_{\text{ann}} = \sqrt{\frac{1}{19} \sum_{i=0}^{19} (R_{t-i} - \bar{R})^2} \times \sqrt{252} \times 100\%$$

8. **Momentum (10-day):**
   $$\text{MOM}_t = C_t - C_{t-10}$$

9. **Normalized Comparison Performance:**
   $$P_{\text{norm}, t} = 100 \times \frac{P_t}{P_0}$$

10. **Pearson Daily Return Correlation:**
    $$r_{X, Y} = \frac{\sum (R_{X, t} - \bar{R}_X)(R_{Y, t} - \bar{R}_Y)}{\sqrt{\sum (R_{X, t} - \bar{R}_X)^2 \sum (R_{Y, t} - \bar{R}_Y)^2}}$$

---

## 6. Verification Results

| Verification Item | Command / Test | Result | Notes |
| :--- | :--- | :--- | :--- |
| **Backend Market Tests** | `pytest backend/tests/test_page_02_market_terminal.py` | **PASS** | 4 passed in 0.91s |
| **Upstox Adapter Tests** | `pytest backend/tests/test_upstox_adapter.py` | **PASS** | 26 passed in 1.25s |
| **Total Backend Test Suite**| `pytest backend/tests -q` | **PASS** | 705 passed in 6.99s |
| **TypeScript Type Check** | `tsc --noEmit --project frontend/tsconfig.json` | **PASS** | 0 errors |
| **Production Build** | `npm run build --prefix frontend` | **PASS** | Built in 2.19s (`dist/assets/index-Cbq00pMc.js`) |
| **Browser E2E Subagent** | Automated subagent browser interaction | **PASS** | Video: `market_terminal_verify_1792924285245.webp` |

---

## 7. Known Limitations and Configuration Notes

1. **Upstox Token Expiration:**
   Upstox access tokens expire daily at 03:30 AM IST per Upstox OAuth policy. When the token expires, the terminal honestly transitions to `"Unauthenticated / Token Expired"` and displays clear instructions to update `UPSTOX_ACCESS_TOKEN` in the environment rather than silently injecting fake quotes.

2. **BSE Exchange Coverage:**
   The primary configured exchange is the National Stock Exchange of India (`NSE`). BSE instruments can be resolved through direct instrument keys (e.g. `BSE_EQ|500325`), but are flagged as secondary coverage.

3. **Rate Limits:**
   Historical candle requests are automatically partitioned into 365-day batches (for daily interval) or 30-day batches (for minute interval) to respect Upstox upstream rate limits.

---

## 8. Summary Status

**Page 02 — Market Terminal is VERIFIED and in a PASS state.** All 8 workspace sections operate strictly on real market data and verifiable quantitative mathematical kernels, with zero mock fallbacks.
