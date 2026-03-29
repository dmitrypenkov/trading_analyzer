#!/usr/bin/env python3
"""
CLI для запуска бэктестов из Claude Code.

Использование:
    python scripts/run_backtest.py '{"instrument":"EURUSD","tp_multiplier":1.5}'
    python scripts/run_backtest.py --config backtest_config.json

Все параметры кроме instrument опциональны — подставляются разумные дефолты.
Результат выводится в JSON на stdout.
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, date
from pathlib import Path

# Добавляем корень проекта в sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Подавляем логи — на stdout только JSON
logging.disable(logging.CRITICAL)

import pandas as pd
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator


DEFAULTS = {
    "timeframe": "15m",
    "block_start": "20:00",
    "block_end": "02:00",
    "session_start": "03:00",
    "session_end": "20:00",
    "from_previous_day": True,
    "use_return_mode": False,
    "trading_days": [0, 1, 2, 3, 4],
    "limit_only_entry": False,
    "min_range_size": 0.0,
    "max_range_size": 999999.0,
    "tp_multiplier": 1.0,
    "sl_multiplier": 1.0,
    "tp_coefficient": 1.0,
    "sl_slippage_coefficient": 1.0,
    "commission_rate": 0.0,
    "use_fixed_tp_sl": False,
    "threshold_min": 0,
    "threshold_max": 999999,
    "fixed_tp_distance": 0,
    "fixed_sl_distance": 0,
    "use_base_sl_mode": False,
    "rr_ratio": 1.5,
    "use_news_filter": True,
    "news_impact_filter": ["high"],
    "news_buffer_minutes": 30,
    "news_currency_filter": [],
    "skip_red_news_days": False,
}


def error_result(message):
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def run_backtest(params: dict) -> dict:
    """Запускает бэктест и возвращает результат как dict."""

    # Валидация
    instrument_symbol = params.get("instrument")
    if not instrument_symbol:
        return {"status": "error", "message": "Параметр 'instrument' обязателен"}

    # Инициализация БД
    init_db()
    instr_repo = InstrumentRepository()
    candle_repo = CandleRepository()
    news_repo = NewsRepository()

    # Поиск инструмента
    instrument = instr_repo.get_by_symbol(instrument_symbol.upper())
    if not instrument:
        available = [i["symbol"] for i in instr_repo.get_all()]
        return {
            "status": "error",
            "message": f"Инструмент '{instrument_symbol}' не найден. Доступные: {', '.join(available)}"
        }

    # Собираем настройки с дефолтами
    settings = {}
    for key, default in DEFAULTS.items():
        settings[key] = params.get(key, default)

    timeframe = settings.pop("timeframe")

    # Определяем даты
    date_range = candle_repo.get_date_range(instrument["id"], timeframe)
    if not date_range:
        return {"status": "error", "message": f"Нет данных для {instrument_symbol} ({timeframe})"}

    if "start_date" in params:
        start_date = datetime.strptime(params["start_date"], "%Y-%m-%d").date()
    else:
        start_date = pd.to_datetime(date_range[0]).date()

    if "end_date" in params:
        end_date = datetime.strptime(params["end_date"], "%Y-%m-%d").date()
    else:
        end_date = pd.to_datetime(date_range[1]).date()

    settings["start_date"] = start_date.strftime("%Y-%m-%d")
    settings["end_date"] = end_date.strftime("%Y-%m-%d")

    # Подтянуть base_sl из инструмента если режим Base SL + RR
    if settings.get("use_base_sl_mode", False) and "base_sl" not in params:
        settings["base_sl"] = instrument.get("base_sl", 0)

    # Подтянуть news_currencies из инструмента если фильтр новостей включён
    if settings.get("use_news_filter", False) and "news_currency_filter" not in params:
        import json as _json
        nc_raw = instrument.get("news_currencies", "[]")
        try:
            settings["news_currency_filter"] = _json.loads(nc_raw) if isinstance(nc_raw, str) else nc_raw
        except (ValueError, TypeError):
            settings["news_currency_filter"] = []

    # Загрузка данных из БД
    price_df = candle_repo.get_dataframe(instrument["id"], timeframe, start_date, end_date)
    if price_df.empty:
        return {"status": "error", "message": f"Нет свечей за период {start_date} — {end_date}"}

    news_df = news_repo.get_dataframe(start_date, end_date)
    if news_df.empty:
        news_df = None

    # Инициализация pipeline (как app.py:1130-1133)
    data_processor = DataProcessor(price_df, news_df)
    analyzer = TradingAnalyzer(data_processor)
    r_calculator = RCalculator()
    report_generator = ReportGenerator(r_calculator)

    # Конвертация строковых параметров в объекты (как app.py:1140-1146)
    settings_for_analysis = settings.copy()
    settings_for_analysis["block_start"] = datetime.strptime(settings["block_start"], "%H:%M").time()
    settings_for_analysis["block_end"] = datetime.strptime(settings["block_end"], "%H:%M").time()
    settings_for_analysis["session_start"] = datetime.strptime(settings["session_start"], "%H:%M").time()
    settings_for_analysis["session_end"] = datetime.strptime(settings["session_end"], "%H:%M").time()
    settings_for_analysis["start_date"] = start_date
    settings_for_analysis["end_date"] = end_date

    # Запуск анализа (как app.py:1149-1153)
    analysis_results = analyzer.analyze_period(start_date, end_date, settings_for_analysis)

    # Генерация отчётов (как app.py:1156-1162)
    daily_trades_df = report_generator.prepare_daily_trades(
        analysis_results["results"],
        settings["tp_coefficient"],
        settings.get("sl_slippage_coefficient", 1.0),
        settings.get("commission_rate", 0.0),
    )
    summary = report_generator.generate_summary_report(daily_trades_df)

    # Формирование выходного JSON
    total_tp = summary.get("total_tp", 0)
    total_sl = summary.get("total_sl", 0)
    total_be = summary.get("total_be", 0)
    total_executed = summary.get("total_executed_trades", 0)
    total_r = summary.get("total_r", 0.0)
    max_dd = summary.get("max_drawdown", {}).get("max_drawdown", 0.0)

    # Win rate
    win_rate = round(total_tp / total_executed * 100, 2) if total_executed > 0 else 0.0

    # Profit factor
    trades_list = daily_trades_df.to_dict("records") if not daily_trades_df.empty else []
    gross_profit = sum(t["r_result"] for t in trades_list if t.get("r_result", 0) > 0)
    gross_loss = abs(sum(t["r_result"] for t in trades_list if t.get("r_result", 0) < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0

    # R/DD ratio
    r_dd_ratio = round(total_r / abs(max_dd), 2) if max_dd != 0 else 0.0

    # Yearly breakdown
    yearly = []
    for yr in summary.get("yearly_reports", []):
        yr_executed = yr.get("executed_trades", 0)
        yearly.append({
            "year": yr["year"],
            "total_r": yr.get("total_r", 0.0),
            "trades": yr_executed,
            "win_rate": yr.get("win_rate", 0.0),
        })

    # Entry type stats (win_rate уже в процентах из r_calculator)
    entry_stats = {}
    for etype, stats in summary.get("entry_type_statistics", {}).items():
        if stats.get("executed_count", 0) > 0:
            entry_stats[etype] = {
                "count": stats.get("executed_count", 0),
                "win_rate": stats.get("win_rate", 0.0),
                "avg_r": stats.get("average_r", 0.0),
                "total_r": stats.get("total_r", 0.0),
            }

    # settings_used — без объектов, только сериализуемое
    settings_used = {k: v for k, v in settings.items()}

    return {
        "status": "ok",
        "instrument": instrument_symbol.upper(),
        "period": f"{start_date} — {end_date}",
        "candles_loaded": len(price_df),
        "summary": {
            "total_r": total_r,
            "total_trades": total_executed,
            "total_tp": total_tp,
            "total_sl": total_sl,
            "total_be": total_be,
            "win_rate": win_rate,
            "average_r_per_trade": summary.get("average_r_per_trade", 0.0),
            "average_r_per_year": summary.get("average_r_per_year", 0.0),
            "average_r_per_month": summary.get("average_r_per_month", 0.0),
            "max_drawdown": round(max_dd, 2),
            "r_dd_ratio": r_dd_ratio,
            "profit_factor": profit_factor,
            "best_year": summary.get("best_year"),
            "best_year_r": summary.get("best_year_r", 0.0),
            "worst_year": summary.get("worst_year"),
            "worst_year_r": summary.get("worst_year_r", 0.0),
        },
        "entry_type_stats": entry_stats,
        "yearly": yearly,
        "settings_used": settings_used,
    }


def main():
    parser = argparse.ArgumentParser(description="Запуск бэктеста из CLI")
    parser.add_argument("params", nargs="?", help="JSON строка с параметрами")
    parser.add_argument("--config", "-c", help="Путь к JSON файлу с параметрами")
    args = parser.parse_args()

    # Загрузка параметров
    if args.config:
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                params = json.load(f)
        except Exception as e:
            print(error_result(f"Ошибка чтения конфига: {e}"))
            sys.exit(1)
    elif args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(error_result(f"Невалидный JSON: {e}"))
            sys.exit(1)
    elif not sys.stdin.isatty():
        try:
            params = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(error_result(f"Невалидный JSON из stdin: {e}"))
            sys.exit(1)
    else:
        print(error_result("Укажите параметры: JSON строка, --config файл, или stdin"))
        sys.exit(1)

    # Запуск
    try:
        result = run_backtest(params)
    except Exception as e:
        result = {"status": "error", "message": str(e)}

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
