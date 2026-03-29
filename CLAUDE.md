# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A backtesting system for range breakout/reversion trading strategies. Written in Python + Streamlit. Analyzes historical OHLC data, identifies entries from range boundaries, simulates trade execution, and measures results in R-units (1R = stop-loss size). Documentation and UI are in Russian.

## Running

```bash
# Activate venv and run main Streamlit app
source venv_trading/bin/activate
streamlit run app.py

# Or use the .app launcher (macOS)
# /Volumes/WD_Passport/Trading/Trading Analyzer.app

# ATR explorer (separate Streamlit app)
streamlit run atr_explorer.py

# Statistical analyzer (separate Streamlit app)
cd statistical_analyzer && streamlit run app.py

# CLI backtest (for Claude Code automation)
python scripts/run_backtest.py '{"instrument":"EURUSD","tp_multiplier":1.5,"sl_multiplier":0.3}'
python scripts/run_backtest.py --config backtest_config.json

# Initial CSV import into SQLite
python scripts/initial_import.py [--csv-dir m15]

# Headless optimization on VPS
python3 VPS/run_optimization.py config.json
python3 VPS/run_optimization.py config.json --dry-run  # verify config without running
```

## Dependencies

```bash
pip install -r requirements.txt
# Core: streamlit, pandas, plotly, xlsxwriter, yfinance, beautifulsoup4
```

Python 3.11 (venv at `venv_trading/`). No test suite or linter configured.

## Architecture

### Data Flow

```
SQLite DB (data/trading.db)
  ├── candles table ──→ CandleRepository.get_dataframe() ──→ DataProcessor ──→ TradingAnalyzer ──→ RCalculator ──→ ReportGenerator ──→ UI (app.py)
  └── news_events table ──→ NewsRepository.get_dataframe() ──→ DataProcessor ──↗        ↑
                                                                          TradingOptimizer (parameter sweep)

Data import:
  CSV files ──→ sync/csv_import.py ──→ SQLite
  Yahoo Finance ──→ sync/yahoo_finance.py ──→ SQLite (last 60 days, 15m candles)
  ForexFactory HTML ──→ sync/forexfactory_parser.py ──→ SQLite (news events)
```

### Database Layer (`db/`)

- **db/schema.py** — SQLite table definitions: `instruments`, `candles`, `news_events`, `import_log`.
- **db/connection.py** — `get_connection()` (WAL mode), `init_db()` (creates tables + seeds default instruments).
- **db/repository.py** — `InstrumentRepository`, `CandleRepository`, `NewsRepository`, `ImportLogRepository`. All `get_dataframe()` methods return DataFrames compatible with `DataProcessor.__init__()`.

### Data Sync (`sync/`)

- **sync/csv_import.py** — `CsvImporter`: imports price CSV and news CSV into DB. Auto-detects instrument from filename. Deduplication via `INSERT OR IGNORE`.
- **sync/yahoo_finance.py** — `YahooFinanceSyncer`: downloads 15m candles from yfinance (last 60 days). Converts timezone to UTC before storing.
- **sync/forexfactory_parser.py** — Parses saved HTML pages from forexfactory.com/calendar. Handles AM/PM time format. Outputs DataFrame for `NewsRepository.bulk_insert()`.

### Config (`config/`)

- **config/instruments.py** — `DEFAULT_INSTRUMENTS` list with 10 instruments and Yahoo Finance ticker mapping.

### Core Modules (root directory)

- **app.py** (~2800 lines) — Streamlit UI with 4 sections: Данные (DB load/import/Yahoo/instruments), Настройки, Результаты, Оптимизация. Uses `st.session_state` extensively; settings loaded via `_pending_settings` buffer.
- **data_processor.py** — Receives DataFrames (from DB or CSV), computes block ranges, returns session candles, determines start position (INSIDE/ABOVE/BELOW), news window checks.
- **analyzer.py** — Core business logic: `TradingAnalyzer` class. `analyze_day()` processes one day through block→entry→trade. `analyze_period()` runs across date ranges. Determines entry types (ENTRY/LIMIT × LONG/SHORT × TREND/REVERSE) and simulates candle-by-candle execution to TP/SL/BE/SESSION_CLOSE.
- **r_calculator.py** — R-metric calculations: R per trade (with tp_coefficient, sl_slippage_coefficient, commission_rate), cumulative R curves, max drawdown, entry type statistics, win rate, profit factor.
- **report_generator.py** — Generates summary/monthly/yearly reports and daily trade DataFrames.
- **optimizer.py** — `TradingOptimizer`: brute-force sweep of tp_multiplier × sl_multiplier combinations. Supports time optimization (sweeping block_end/session_start split hour). Optional parallel execution via ThreadPoolExecutor (up to 4 threads, thread-safe cache with deepcopy + Lock). Three optimization targets: max_total_r, max_r_dd_ratio (Calmar-like), max_r_minus_dd.
- **chart_visualizer.py** — Static Plotly chart builder (cumulative R chart with green/red fill).
- **atr_analyzer.py** / **atr_explorer.py** — Standalone ATR volatility analysis tool (separate Streamlit app), not connected to main strategy.

### Scripts (`scripts/`)

- **scripts/run_backtest.py** — CLI for running backtests from Claude Code. Accepts JSON params (instrument + strategy settings), loads from SQLite, outputs results as JSON to stdout. All params except `instrument` have sensible defaults.
- **scripts/initial_import.py** — Bulk imports all CSV files from `m15/` directory into SQLite DB.

### Sub-projects

- **statistical_analyzer/** — Separate Streamlit app for post-hoc statistical analysis of exported trade CSVs. Independent from main DB.
- **VPS/** — Headless optimization runner. Supports both `instrument` (DB) and `price_data_path` (CSV) in config.

### Key Domain Concepts

- **Block**: Time window where price range is established (range_high, range_low, range_size).
- **Session**: Trading window after block where one trade is sought and executed.
- **Entry types**: Determined by start position (INSIDE/ABOVE/BELOW) and which boundary is touched first. Two modes: Trend (trade in breakout direction) and Reverse (trade in reversion direction). ENTRY types = price starts inside range; LIMIT types = price starts outside range.
- **R-unit**: All results normalized to stop-loss size. R = (exit - entry) / sl_distance.
- **Settings dict**: Passed throughout the pipeline; contains all strategy parameters (block/session times, multipliers, coefficients, filters). See `DOCUMENTATION.md` for the full parameter table.

## Key Patterns

- All modules communicate via plain dicts (settings dict, trade result dicts). No ORM.
- SQLite with WAL mode. Data accessed via repository classes that return pandas DataFrames.
- Deduplication: `INSERT OR IGNORE` on composite primary keys (candles) and unique constraints (news).
- `DataProcessor` takes DataFrames — agnostic to data source (DB, CSV, Yahoo).
- `TradingAnalyzer` takes a `DataProcessor` instance; `TradingOptimizer` instantiates its own analyzer internally.
- The optimizer's result cache is a dict protected by `threading.Lock` with `deepcopy` on retrieval.
- Streamlit state management uses a `_pending_settings` pattern to apply loaded JSON settings before widgets render.
- `exports/` directory is used for CSV/Excel exports from the UI.

## CLI Backtest API

```bash
# Minimal — all defaults
python scripts/run_backtest.py '{"instrument":"EURUSD"}'

# With params
python scripts/run_backtest.py '{"instrument":"XAUUSD","tp_multiplier":1.5,"sl_multiplier":0.5,"start_date":"2024-01-01","end_date":"2025-06-30"}'

# Output: JSON with summary (total_r, win_rate, max_drawdown, profit_factor), yearly breakdown, entry_type_stats
```
