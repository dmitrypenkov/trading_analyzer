#!/usr/bin/env python3
"""
CLI для запуска оптимизации R-циклов из Claude Code.

Использование:
    python scripts/run_optimization.py '{"instrument":"NAS100","target_r":5}'
    python scripts/run_optimization.py --config opt_config.json

Параметры:
    instrument      — обязательный, символ инструмента
    target_r        — порог R-цикла (default: 5.0)
    sl_mult_min/max/step — диапазон SL множителя (default: 0.0/0.5/0.05)
    rr_min/max/step — диапазон RR (default: 0.5/5.0/0.5)
    top_n           — сколько лучших показать (default: 10)
    + все параметры стратегии из run_backtest.py

Результат: JSON на stdout.
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from copy import deepcopy

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.disable(logging.CRITICAL)

import pandas as pd
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from optimizer import TradingOptimizer


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
    "sl_multiplier": 0.1,
    "tp_coefficient": 1.0,
    "sl_slippage_coefficient": 1.0,
    "commission_rate": 0.0,
    "use_fixed_tp_sl": False,
    "use_base_sl_mode": True,
    "rr_ratio": 1.5,
    "use_news_filter": False,
    "news_impact_filter": ["high"],
    "news_buffer_minutes": 30,
    "news_currency_filter": [],
    "skip_red_news_days": False,
}

OPT_DEFAULTS = {
    "target_r": 5.0,
    "sl_mult_min": 0.0,
    "sl_mult_max": 0.5,
    "sl_mult_step": 0.05,
    "rr_min": 0.5,
    "rr_max": 5.0,
    "rr_step": 0.5,
    "top_n": 10,
}


def error_result(message):
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def run_optimization(params: dict) -> dict:
    instrument_symbol = params.get("instrument")
    if not instrument_symbol:
        return {"status": "error", "message": "Параметр 'instrument' обязателен"}

    init_db()
    instr_repo = InstrumentRepository()
    candle_repo = CandleRepository()
    news_repo = NewsRepository()

    instrument = instr_repo.get_by_symbol(instrument_symbol.upper())
    if not instrument:
        available = [i["symbol"] for i in instr_repo.get_all()]
        return {"status": "error", "message": f"Инструмент '{instrument_symbol}' не найден. Доступные: {', '.join(available)}"}

    # Настройки стратегии
    settings = {}
    for key, default in DEFAULTS.items():
        settings[key] = params.get(key, default)

    timeframe = settings.pop("timeframe")

    # Даты
    date_range = candle_repo.get_date_range(instrument["id"], timeframe)
    if not date_range:
        return {"status": "error", "message": f"Нет данных для {instrument_symbol}"}

    start_date = datetime.strptime(params["start_date"], "%Y-%m-%d").date() if "start_date" in params else pd.to_datetime(date_range[0]).date()
    end_date = datetime.strptime(params["end_date"], "%Y-%m-%d").date() if "end_date" in params else pd.to_datetime(date_range[1]).date()

    settings["start_date"] = start_date
    settings["end_date"] = end_date

    # Base SL из инструмента
    if settings.get("use_base_sl_mode", True) and "base_sl" not in params:
        settings["base_sl"] = instrument.get("base_sl", 0)

    # News currencies из инструмента
    if settings.get("use_news_filter", False) and "news_currency_filter" not in params:
        import json as _json
        nc_raw = instrument.get("news_currencies", "[]")
        try:
            settings["news_currency_filter"] = _json.loads(nc_raw) if isinstance(nc_raw, str) else nc_raw
        except (ValueError, TypeError):
            settings["news_currency_filter"] = []

    # Конвертация времён
    for tkey in ["block_start", "block_end", "session_start", "session_end"]:
        if isinstance(settings.get(tkey), str):
            settings[tkey] = datetime.strptime(settings[tkey], "%H:%M").time()

    # Загрузка данных
    price_df = candle_repo.get_dataframe(instrument["id"], timeframe, start_date, end_date)
    if price_df.empty:
        return {"status": "error", "message": f"Нет свечей за {start_date} — {end_date}"}

    news_df = news_repo.get_dataframe(start_date, end_date)

    # Pipeline
    data_processor = DataProcessor(price_df, news_df if not news_df.empty else None)
    analyzer = TradingAnalyzer(data_processor)
    r_calculator = RCalculator()
    optimizer = TradingOptimizer(data_processor, analyzer, r_calculator)

    # Параметры оптимизации
    target_r = params.get("target_r", OPT_DEFAULTS["target_r"])
    sl_mult_range = (
        params.get("sl_mult_min", OPT_DEFAULTS["sl_mult_min"]),
        params.get("sl_mult_max", OPT_DEFAULTS["sl_mult_max"]),
        params.get("sl_mult_step", OPT_DEFAULTS["sl_mult_step"]),
    )
    rr_range = (
        params.get("rr_min", OPT_DEFAULTS["rr_min"]),
        params.get("rr_max", OPT_DEFAULTS["rr_max"]),
        params.get("rr_step", OPT_DEFAULTS["rr_step"]),
    )
    top_n = params.get("top_n", OPT_DEFAULTS["top_n"])

    # Запуск
    result = optimizer.optimize_base_sl_rr(
        settings=settings,
        sl_mult_range=sl_mult_range,
        rr_range=rr_range,
        target_r=target_r,
    )

    # Формирование ответа
    top_results = result["all_results"][:top_n]

    return {
        "status": "ok",
        "instrument": instrument_symbol.upper(),
        "period": f"{start_date} — {end_date}",
        "base_sl": settings.get("base_sl", 0),
        "target_r": target_r,
        "total_combinations": result["total_combinations"],
        "computation_time": result["computation_time"],
        "best": result["best"],
        "top": top_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Оптимизация R-циклов (Base SL + RR)")
    parser.add_argument("params", nargs="?", help="JSON строка с параметрами")
    parser.add_argument("--config", "-c", help="Путь к JSON файлу")
    args = parser.parse_args()

    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            params = json.load(f)
    elif args.params:
        params = json.loads(args.params)
    elif not sys.stdin.isatty():
        params = json.load(sys.stdin)
    else:
        print(error_result("Укажите параметры"))
        sys.exit(1)

    try:
        result = run_optimization(params)
    except Exception as e:
        result = {"status": "error", "message": str(e)}

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
