#!/usr/bin/env python3
"""
Общие хелперы для XAUUSD loss-finder / inversion / cycle анализа.

Грузит данные XAUUSD ОДИН раз, строит пайплайн один раз и гоняет конфиги напрямую
через analyzer.analyze_period (без subprocess). Метрики считаются из per-trade
daily_trades_df, что позволяет вырезать произвольные под-периоды (напр. последние 30
дней) без повторного прогона.
"""

import sys
import json
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.disable(logging.CRITICAL)

import pandas as pd
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator

TIMEFRAME = "15m"


def _to_time(hhmm: str):
    return datetime.strptime(hhmm, "%H:%M").time()


class XauPipeline:
    """Загружает XAUUSD один раз и прогоняет произвольные конфиги."""

    def __init__(self, symbol="XAUUSD", load_from="2023-12-01"):
        init_db()
        instr_repo = InstrumentRepository()
        candle_repo = CandleRepository()
        news_repo = NewsRepository()

        self.instrument = instr_repo.get_by_symbol(symbol)
        if not self.instrument:
            raise RuntimeError(f"Инструмент {symbol} не найден")

        self.symbol = symbol
        self.base_sl = self.instrument.get("base_sl", 0) or 0

        # news_currencies инструмента (как в run_backtest.py)
        nc_raw = self.instrument.get("news_currencies", "[]")
        try:
            self.news_currencies = json.loads(nc_raw) if isinstance(nc_raw, str) else (nc_raw or [])
        except (ValueError, TypeError):
            self.news_currencies = []

        # Диапазон данных
        dr = candle_repo.get_date_range(self.instrument["id"], TIMEFRAME)
        self.data_first = pd.to_datetime(dr[0]).date()
        self.data_last = pd.to_datetime(dr[1]).date()

        load_start = datetime.strptime(load_from, "%Y-%m-%d").date()

        price_df = candle_repo.get_dataframe(
            self.instrument["id"], TIMEFRAME, load_start, self.data_last
        )
        news_df = news_repo.get_dataframe(load_start, self.data_last)
        if news_df.empty:
            news_df = None

        self.data_processor = DataProcessor(price_df, news_df)
        self.analyzer = TradingAnalyzer(self.data_processor)
        self.r_calc = RCalculator()
        self.report_gen = ReportGenerator(self.r_calc)
        self.candles_loaded = len(price_df)

    def build_settings(self, *, block_start, block_end, session_start, session_end,
                       mode="TREND", invert_signals=False,
                       sl_multiplier=0.1, rr_ratio=2.0,
                       use_news_filter=True, news_buffer_minutes=30,
                       news_exit_mode="be",
                       from_previous_day=False):
        """Собирает settings dict с time-объектами, base_sl режим + news."""
        return {
            "block_start": _to_time(block_start),
            "block_end": _to_time(block_end),
            "session_start": _to_time(session_start),
            "session_end": _to_time(session_end),
            "from_previous_day": from_previous_day,
            "use_return_mode": (mode == "REVERSE"),
            "invert_signals": invert_signals,
            "trading_days": [0, 1, 2, 3, 4],
            "limit_only_entry": False,
            "min_range_size": 0.0,
            "max_range_size": 999999.0,
            "tp_multiplier": 1.0,
            "sl_multiplier": sl_multiplier,
            "tp_coefficient": 1.0,
            "sl_slippage_coefficient": 1.0,
            "commission_rate": 0.0,
            "use_fixed_tp_sl": False,
            "threshold_min": 0,
            "threshold_max": 999999,
            "fixed_tp_distance": 0,
            "fixed_sl_distance": 0,
            "use_base_sl_mode": True,
            "base_sl": self.base_sl,
            "rr_ratio": rr_ratio,
            "use_news_filter": use_news_filter,
            "news_exit_mode": news_exit_mode,
            "news_impact_filter": ["high"],
            "news_buffer_minutes": news_buffer_minutes,
            "news_currency_filter": self.news_currencies,
            "skip_red_news_days": False,
        }

    def run(self, settings, start_date, end_date):
        """Прогоняет конфиг, возвращает daily_trades_df (per-trade)."""
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        s = dict(settings)
        s["start_date"] = start_date
        s["end_date"] = end_date

        analysis = self.analyzer.analyze_period(start_date, end_date, s)
        df = self.report_gen.prepare_daily_trades(
            analysis["results"],
            s.get("tp_coefficient", 1.0),
            s.get("sl_slippage_coefficient", 1.0),
            s.get("commission_rate", 0.0),
        )
        return df


def metrics_from_df(df, date_from=None, date_to=None, direction=None):
    """
    Считает метрики из daily_trades_df (только executed TP/SL/BE).
    date_from/date_to — строки 'YYYY-MM-DD' для вырезания под-периода.
    direction — 'LONG' или 'SHORT' для фильтра только по одной стороне (по entry_type).
    """
    empty = {"total_r": 0.0, "trades": 0, "win_rate": 0.0,
             "max_drawdown": 0.0, "profit_factor": 0.0, "tp": 0, "sl": 0, "be": 0}
    if df is None or df.empty:
        return empty

    ex = df[df["result"].isin(["TP", "SL", "BE"])].copy()
    if ex.empty:
        return empty
    if date_from is not None:
        ex = ex[ex["date"] >= date_from]
    if date_to is not None:
        ex = ex[ex["date"] <= date_to]
    if direction is not None:
        ex = ex[ex["entry_type"].str.contains(direction, na=False)]
    if ex.empty:
        return empty

    ex = ex.sort_values("date")
    r = ex["r_result"]
    total_r = float(r.sum())
    trades = int(len(ex))
    tp = int((ex["result"] == "TP").sum())
    sl = int((ex["result"] == "SL").sum())
    be = int((ex["result"] == "BE").sum())
    win_rate = round(tp / trades * 100, 2) if trades else 0.0

    cum = r.cumsum()
    running_max = cum.cummax()
    max_dd = float((cum - running_max).min())

    gross_profit = float(r[r > 0].sum())
    gross_loss = float(-r[r < 0].sum())
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0

    return {
        "total_r": round(total_r, 2),
        "trades": trades,
        "win_rate": win_rate,
        "max_drawdown": round(max_dd, 2),
        "profit_factor": pf,
        "tp": tp, "sl": sl, "be": be,
    }


def window_dates(pipeline, months=12):
    """Возвращает (start, end) для последних N месяцев по данным."""
    end = pipeline.data_last
    start = end - timedelta(days=int(months * 30.44))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
