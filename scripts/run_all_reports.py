#!/usr/bin/env python3
"""Полный отчёт по каждому инструменту: общее, помесячно, поквартально, полугодие, год."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging; logging.disable(logging.CRITICAL)
import pandas as pd
from datetime import datetime, date
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator
import json

init_db()
ir = InstrumentRepository()
cr = CandleRepository()
nr = NewsRepository()

CONFIGS = [
    {"symbol": "USDJPY",  "base_sl": 0.2,   "sl_mult": 0.10, "rr": 1.4},
    {"symbol": "XAUUSD",  "base_sl": 20,     "sl_mult": 0.30, "rr": 0.5},
    {"symbol": "GER40",   "base_sl": 80,     "sl_mult": 0.20, "rr": 1.5},
    {"symbol": "JP225",   "base_sl": 150,    "sl_mult": 0.10, "rr": 1.2},
    {"symbol": "USDCHF",  "base_sl": 0.002,  "sl_mult": 0.30, "rr": 1.1},
    {"symbol": "NAS100",  "base_sl": 100,    "sl_mult": 0.10, "rr": 1.3},
    {"symbol": "SP500",   "base_sl": 22,     "sl_mult": 0.10, "rr": 1.4},
    {"symbol": "EURUSD",  "base_sl": 0.002,  "sl_mult": 0.10, "rr": 1.4},
]

def run_report(cfg):
    symbol = cfg["symbol"]
    instr = ir.get_by_symbol(symbol)
    if not instr:
        return f"⚠️ {symbol} не найден"

    nc = json.loads(instr.get('news_currencies', '[]')) if isinstance(instr.get('news_currencies', ''), str) else []
    dr = cr.get_date_range(instr['id'])
    if not dr:
        return f"⚠️ {symbol} нет данных"

    start = pd.to_datetime(dr[0]).date()
    end = pd.to_datetime(dr[1]).date()

    price_df = cr.get_dataframe(instr['id'], '15m', start, end)
    news_df = nr.get_dataframe(start, end)

    dp = DataProcessor(price_df, news_df if not news_df.empty else None)
    analyzer = TradingAnalyzer(dp)
    rc = RCalculator()
    rg = ReportGenerator(rc)

    settings = {
        'block_start': datetime.strptime('20:00', '%H:%M').time(),
        'block_end': datetime.strptime('02:00', '%H:%M').time(),
        'session_start': datetime.strptime('03:00', '%H:%M').time(),
        'session_end': datetime.strptime('20:00', '%H:%M').time(),
        'from_previous_day': True,
        'use_return_mode': False,
        'trading_days': [0, 1, 2, 3, 4],
        'limit_only_entry': False,
        'min_range_size': 0.0, 'max_range_size': 999999.0,
        'use_base_sl_mode': True,
        'base_sl': cfg["base_sl"],
        'sl_multiplier': cfg["sl_mult"],
        'rr_ratio': cfg["rr"],
        'tp_coefficient': 1.0, 'sl_slippage_coefficient': 1.0, 'commission_rate': 0.0,
        'use_fixed_tp_sl': False,
        'use_news_filter': True,
        'news_impact_filter': ['high'], 'news_buffer_minutes': 30,
        'news_currency_filter': nc, 'skip_red_news_days': False,
        'start_date': start, 'end_date': end,
    }

    results = analyzer.analyze_period(start, end, settings)
    daily_df = rg.prepare_daily_trades(results['results'], 1.0, 1.0, 0.0)

    executed = daily_df[daily_df['result'].isin(['TP', 'SL', 'BE'])]
    if executed.empty:
        return f"⚠️ {symbol} нет сделок"

    total_r = executed['r_result'].sum()
    cum_r = executed['r_result'].cumsum()
    max_dd = (cum_r - cum_r.cummax()).min()
    tp_n = len(executed[executed['result'] == 'TP'])
    sl_n = len(executed[executed['result'] == 'SL'])
    be_n = len(executed[executed['result'] == 'BE'])
    wr = tp_n / len(executed) * 100

    cycles = rc.calculate_r_cycles(executed.to_dict('records'), 5.0)

    out = []
    out.append("=" * 85)
    out.append(f"{symbol} (base_sl={cfg['base_sl']}, SL mult={cfg['sl_mult']}, RR={cfg['rr']})")
    out.append(f"Период: {start} — {end} | Новости: {nc}")
    out.append("=" * 85)
    out.append(f"Сделок: {len(executed)} (TP={tp_n}, SL={sl_n}, BE={be_n}) | WR: {wr:.1f}%")
    out.append(f"Total R: {total_r:+.2f} | Max DD: {max_dd:.2f}R | R/DD: {total_r/abs(max_dd):.2f}" if max_dd != 0 else f"Total R: {total_r:+.2f}")
    out.append(f"R-циклы (±5R): {cycles['num_cycles']} ({cycles['win_cycles']}W/{cycles['loss_cycles']}L, {cycles['win_cycle_rate']}%)")
    out.append("")

    # Помесячно
    daily_df['date_parsed'] = pd.to_datetime(daily_df['date'])
    daily_df['month'] = daily_df['date_parsed'].dt.to_period('M')

    monthly = []
    run_r = 0; run_peak = 0

    out.append(f"{'Месяц':>10s} {'Сд':>4s} {'TP':>3s} {'SL':>3s} {'BE':>3s} {'WR%':>5s} {'R':>8s} {'CumR':>8s}")
    out.append("-" * 55)

    for m in sorted(daily_df['month'].unique()):
        mdf = daily_df[(daily_df['month'] == m) & daily_df['result'].isin(['TP', 'SL', 'BE'])]
        if mdf.empty:
            continue
        t = len(mdf); tp = len(mdf[mdf['result'] == 'TP']); sl = len(mdf[mdf['result'] == 'SL']); be = len(mdf[mdf['result'] == 'BE'])
        w = tp / t * 100; r = mdf['r_result'].sum(); run_r += r; run_peak = max(run_peak, run_r)
        monthly.append({'month': str(m), 'trades': t, 'tp': tp, 'sl': sl, 'be': be, 'wr': w, 'r': r})
        out.append(f"{str(m):>10s} {t:>4d} {tp:>3d} {sl:>3d} {be:>3d} {w:>5.1f} {r:>+8.2f} {run_r:>+8.2f}")

    mdf_all = pd.DataFrame(monthly)
    mdf_all['dt'] = pd.to_datetime(mdf_all['month'].str.replace('-', '') + '01', format='%Y%m%d')

    # Квартально
    mdf_all['Q'] = mdf_all['dt'].dt.to_period('Q')
    out.append("")
    out.append(f"{'Квартал':>10s} {'Сд':>4s} {'TP':>3s} {'SL':>3s} {'BE':>3s} {'WR%':>5s} {'R':>8s}")
    out.append("-" * 45)
    for q in sorted(mdf_all['Q'].unique()):
        qd = mdf_all[mdf_all['Q'] == q]; t = qd['trades'].sum(); tp = qd['tp'].sum(); sl = qd['sl'].sum(); be = qd['be'].sum()
        w = tp / t * 100 if t else 0; r = qd['r'].sum()
        out.append(f"{str(q):>10s} {t:>4d} {tp:>3d} {sl:>3d} {be:>3d} {w:>5.1f} {r:>+8.2f}")

    # Полугодие
    mdf_all['H'] = mdf_all['dt'].dt.year.astype(str) + '-H' + ((mdf_all['dt'].dt.month - 1) // 6 + 1).astype(str)
    out.append("")
    out.append(f"{'Полугод':>10s} {'Сд':>4s} {'TP':>3s} {'SL':>3s} {'BE':>3s} {'WR%':>5s} {'R':>8s}")
    out.append("-" * 45)
    for h in sorted(mdf_all['H'].unique()):
        hd = mdf_all[mdf_all['H'] == h]; t = hd['trades'].sum(); tp = hd['tp'].sum(); sl = hd['sl'].sum(); be = hd['be'].sum()
        w = tp / t * 100 if t else 0; r = hd['r'].sum()
        out.append(f"{h:>10s} {t:>4d} {tp:>3d} {sl:>3d} {be:>3d} {w:>5.1f} {r:>+8.2f}")

    # Год
    mdf_all['Y'] = mdf_all['dt'].dt.year
    out.append("")
    out.append(f"{'Год':>10s} {'Сд':>4s} {'TP':>3s} {'SL':>3s} {'BE':>3s} {'WR%':>5s} {'R':>8s}")
    out.append("-" * 45)
    for y in sorted(mdf_all['Y'].unique()):
        yd = mdf_all[mdf_all['Y'] == y]; t = yd['trades'].sum(); tp = yd['tp'].sum(); sl = yd['sl'].sum(); be = yd['be'].sum()
        w = tp / t * 100 if t else 0; r = yd['r'].sum()
        out.append(f"{y:>10d} {t:>4d} {tp:>3d} {sl:>3d} {be:>3d} {w:>5.1f} {r:>+8.2f}")

    out.append("")
    return "\n".join(out)


# ===== MAIN =====
import time
all_output = []
t_total = time.time()

for cfg in CONFIGS:
    print(f"Считаю {cfg['symbol']}...", flush=True)
    t0 = time.time()
    report = run_report(cfg)
    print(f"  {cfg['symbol']} готов за {time.time()-t0:.0f}s", flush=True)
    all_output.append(report)

total = time.time() - t_total
full_text = "\n\n".join(all_output)
print(full_text)

# Сохранить
outpath = Path(__file__).parent.parent / "exports" / "full_reports_all_instruments.txt"
outpath.parent.mkdir(exist_ok=True)
outpath.write_text(full_text)
print(f"\n\nСохранено: {outpath}")
print(f"Общее время: {total:.0f}s ({total/60:.1f} мин)")
