# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A backtesting system for range breakout/reversion trading strategies. Written in Python + Streamlit. Analyzes historical OHLC data, identifies entries from range boundaries, simulates trade execution, and measures results in R-units (1R = stop-loss size). Documentation and UI are in Russian.

## Running

```bash
# Activate venv and run main Streamlit app
source venv_trading/bin/activate
streamlit run app.py

# ATR explorer (separate Streamlit app)
streamlit run atr_explorer.py

# Statistical analyzer (separate Streamlit app)
cd statistical_analyzer && streamlit run app.py

# Headless optimization on VPS
python3 VPS/run_optimization.py config.json
python3 VPS/run_optimization.py config.json --dry-run  # verify config without running
```

## Dependencies

```bash
pip install -r requirements.txt
# Core: streamlit, pandas, numpy, plotly, xlsxwriter
```

Python 3.11 (venv at `venv_trading/`). No test suite or linter configured.

## Architecture

### Data Flow

```
CSV (prices) -> DataProcessor -> TradingAnalyzer -> RCalculator -> ReportGenerator -> UI (app.py)
CSV (news)   ->                                                     ^
                                                         TradingOptimizer (parameter sweep)
```

### Core Modules (root directory)

- **app.py** (~2600 lines) — Streamlit UI, all widgets, display logic, settings save/load via JSON. Uses `st.session_state` extensively; settings loaded via `_pending_settings` buffer to work around Streamlit's widget-state timing.
- **data_processor.py** — Loads CSV, computes block ranges (range_high/low/size), returns session candles, determines start position (INSIDE/ABOVE/BELOW), news window checks.
- **analyzer.py** — Core business logic: `TradingAnalyzer` class. `analyze_day()` processes one day through block->entry->trade. `analyze_period()` runs across date ranges. Determines entry types (ENTRY/LIMIT × LONG/SHORT × TREND/REVERSE) and simulates candle-by-candle execution to TP/SL/BE/SESSION_CLOSE.
- **r_calculator.py** — R-metric calculations: R per trade (with tp_coefficient, sl_slippage_coefficient, commission_rate), cumulative R curves, max drawdown, entry type statistics, win rate, profit factor.
- **report_generator.py** — Generates summary/monthly/yearly reports and daily trade DataFrames.
- **optimizer.py** — `TradingOptimizer`: brute-force sweep of tp_multiplier × sl_multiplier combinations. Supports time optimization (sweeping block_end/session_start split hour). Optional parallel execution via ThreadPoolExecutor (up to 4 threads, thread-safe cache with Lock). Three optimization targets: max_total_r, max_r_dd_ratio (Calmar-like), max_r_minus_dd.
- **chart_visualizer.py** — Static Plotly chart builder (cumulative R chart with green/red fill).
- **atr_analyzer.py** / **atr_explorer.py** — Standalone ATR volatility analysis tool (separate Streamlit app), not connected to main strategy.

### Sub-projects

- **statistical_analyzer/** — Separate Streamlit app for post-hoc statistical analysis of exported trade CSVs. Modules: `series_analyzer.py` (consecutive TP/SL streaks), `rolling_window.py` (rolling R windows with target/drawdown checks), `temporal_analyzer.py` (hourly/daily/seasonal patterns). Input: CSV with columns `date, weekday, entry_type, direction, entry_time, exit_time, result, r_result`.
- **VPS/** — Headless optimization runner (`run_optimization.py`) for remote servers. Reads `config.json`, runs full parameter sweep without Streamlit, outputs results to timestamped directory with HTML report, CSVs, and log. See `VPS/VPS_DEPLOY.md` for deployment instructions and `VPS/config_example.json` for config format.

### Key Domain Concepts

- **Block**: Time window where price range is established (range_high, range_low, range_size).
- **Session**: Trading window after block where one trade is sought and executed.
- **Entry types**: Determined by start position (INSIDE/ABOVE/BELOW) and which boundary is touched first. Two modes: Trend (trade in breakout direction) and Reverse (trade in reversion direction). ENTRY types = price starts inside range; LIMIT types = price starts outside range.
- **R-unit**: All results normalized to stop-loss size. R = (exit - entry) / sl_distance.
- **Settings dict**: Passed throughout the pipeline; contains all strategy parameters (block/session times, multipliers, coefficients, filters). See `DOCUMENTATION.md` for the full parameter table.

## Key Patterns

- All modules communicate via plain dicts (settings dict, trade result dicts). No ORM, no database.
- `TradingAnalyzer` takes a `DataProcessor` instance; `TradingOptimizer` instantiates its own analyzer internally.
- The optimizer's result cache is a dict protected by `threading.Lock`.
- Streamlit state management uses a `_pending_settings` pattern to apply loaded JSON settings before widgets render.
- `exports/` directory is used for CSV/Excel exports from the UI.
