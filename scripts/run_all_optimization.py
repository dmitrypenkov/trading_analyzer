#!/usr/bin/env python3
"""
Массовая оптимизация R-циклов по всем инструментам.
Запуск: nohup python scripts/run_all_optimization.py > optimization_log.txt 2>&1 &
Результат: exports/optimization_results_all.csv
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, date
from copy import deepcopy

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import logging
logging.disable(logging.CRITICAL)

from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator
from optimizer import TradingOptimizer

# ===== ПАРАМЕТРЫ =====
INSTRUMENTS = ["EURUSD", "USDJPY", "USDCHF", "XAUUSD", "SP500", "NAS100", "GER40", "JP225"]
START_DATE = date(2024, 1, 1)
END_DATE = date(2026, 3, 26)
TARGET_R = 5.0

SL_MULT_RANGE = (0.1, 0.5, 0.1)
RR_RANGE = (0.5, 1.5, 0.1)

init_db()
ir = InstrumentRepository()
cr = CandleRepository()
nr = NewsRepository()

print("=" * 70)
print("Trading Analyzer — Массовая оптимизация R-циклов")
print(f"Период: {START_DATE} — {END_DATE}, Target: ±{TARGET_R}R")
print("=" * 70)
print(flush=True)

news_df = nr.get_dataframe(START_DATE, END_DATE)
print(f"Новостей загружено: {len(news_df)}")

all_rows = []
total_start = time.time()

for symbol in INSTRUMENTS:
    instr = ir.get_by_symbol(symbol)
    if not instr:
        print(f"⚠️ {symbol} не найден")
        continue

    nc_raw = instr.get('news_currencies', '[]')
    news_currencies = json.loads(nc_raw) if isinstance(nc_raw, str) and nc_raw else []
    base_sl = instr.get('base_sl', 0)

    print(f"\n{'='*50}")
    print(f"📊 {symbol} (base_sl={base_sl}, news={news_currencies})")
    print(flush=True)

    price_df = cr.get_dataframe(instr['id'], '15m', START_DATE, END_DATE)
    if price_df.empty:
        print(f"  Нет данных, пропускаю")
        continue
    print(f"  Свечей: {len(price_df):,}")

    dp = DataProcessor(price_df, news_df if not news_df.empty else None)
    analyzer = TradingAnalyzer(dp)
    r_calc = RCalculator()
    optimizer = TradingOptimizer(dp, analyzer, r_calc)

    settings = {
        'block_start': datetime.strptime("20:00", "%H:%M").time(),
        'block_end': datetime.strptime("02:00", "%H:%M").time(),
        'session_start': datetime.strptime("03:00", "%H:%M").time(),
        'session_end': datetime.strptime("20:00", "%H:%M").time(),
        'from_previous_day': True,
        'use_return_mode': False,
        'trading_days': [0, 1, 2, 3, 4],
        'limit_only_entry': False,
        'min_range_size': 0.0,
        'max_range_size': 999999.0,
        'use_base_sl_mode': True,
        'base_sl': base_sl,
        'tp_coefficient': 1.0,
        'sl_slippage_coefficient': 1.0,
        'commission_rate': 0.0,
        'use_fixed_tp_sl': False,
        'use_news_filter': True,
        'news_impact_filter': ['high'],
        'news_buffer_minutes': 30,
        'news_currency_filter': news_currencies,
        'skip_red_news_days': False,
        'start_date': START_DATE,
        'end_date': END_DATE,
    }

    t0 = time.time()
    result = optimizer.optimize_base_sl_rr(
        settings=settings,
        sl_mult_range=SL_MULT_RANGE,
        rr_range=RR_RANGE,
        target_r=TARGET_R,
    )
    elapsed = time.time() - t0

    # Сохранить результаты
    for r in result['all_results']:
        all_rows.append({'instrument': symbol, 'base_sl': base_sl, **r})

    # Показать топ-5
    print(f"  Готово за {elapsed:.0f}s")
    print(f"  {'SL':>6s} {'RR':>5s} {'Cyc':>4s} {'W':>3s} {'L':>3s} {'WR%':>5s} {'T/c':>5s} {'TotR':>7s} {'WR%':>5s}")
    for r in result['all_results'][:5]:
        print(f"  {r['sl_multiplier']:>6.2f} {r['rr_ratio']:>5.1f} {r['num_cycles']:>4d} {r['win_cycles']:>3d} {r['loss_cycles']:>3d} {r['win_cycle_rate']:>5.1f} {r['avg_trades_per_cycle']:>5.1f} {r['total_r']:>7.2f} {r['win_rate']:>5.1f}")
    print(flush=True)

# Экспорт
total_elapsed = time.time() - total_start
export_df = pd.DataFrame(all_rows)
export_path = PROJECT_ROOT / "exports" / "optimization_results_all.csv"
export_path.parent.mkdir(exist_ok=True)
export_df.to_csv(export_path, index=False)

print(f"\n{'='*70}")
print(f"Общее время: {total_elapsed:.0f}s ({total_elapsed/60:.1f} мин)")
print(f"Результаты: {export_path}")
print(f"Строк: {len(export_df)}")

# Сводка
print(f"\n🏆 ЛУЧШИЕ:")
print(f"{'Инструмент':>12s} {'BSL':>6s} {'SL':>5s} {'RR':>5s} {'Cyc':>4s} {'W':>3s} {'L':>3s} {'WR%':>5s} {'TotR':>7s}")
for sym in INSTRUMENTS:
    sdf = export_df[export_df['instrument'] == sym].sort_values(['num_cycles', 'win_cycle_rate'], ascending=False)
    if not sdf.empty:
        b = sdf.iloc[0]
        print(f"{sym:>12s} {b['base_sl']:>6g} {b['sl_multiplier']:>5.2f} {b['rr_ratio']:>5.1f} {b['num_cycles']:>4.0f} {b['win_cycles']:>3.0f} {b['loss_cycles']:>3.0f} {b['win_cycle_rate']:>5.1f} {b['total_r']:>7.2f}")

print(f"\n✅ DONE", flush=True)
