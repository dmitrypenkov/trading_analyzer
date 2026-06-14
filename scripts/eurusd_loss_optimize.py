#!/usr/bin/env python3
"""EURUSD — оптимизация на максимум loss циклов (-5R)."""
import sys; sys.path.insert(0, '/Volumes/WD_Passport/Trading/trading_analyzer')
sys.stdout.reconfigure(line_buffering=True)  # Без буферизации!

import logging; logging.disable(logging.CRITICAL)
import json, itertools, time
import pandas as pd
from datetime import datetime, date
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator

init_db()
ir = InstrumentRepository()
cr = CandleRepository()
nr = NewsRepository()

instr = ir.get_by_symbol('EURUSD')
nc = json.loads(instr.get('news_currencies', '[]'))
dr = cr.get_date_range(instr['id'])
start = date(2024, 1, 1)
end = pd.to_datetime(dr[1]).date()

print(f"EURUSD: {start} — {end}", flush=True)

price_df = cr.get_dataframe(instr['id'], '15m', start, end)
news_df = nr.get_dataframe(start, end)
print(f"Свечей: {len(price_df)}, Новостей: {len(news_df)}", flush=True)

dp = DataProcessor(price_df, news_df)
az = TradingAnalyzer(dp)
rc = RCalculator()
rg = ReportGenerator(rc)

base = {
    'block_start': datetime.strptime('20:00','%H:%M').time(),
    'block_end': datetime.strptime('02:00','%H:%M').time(),
    'session_start': datetime.strptime('03:00','%H:%M').time(),
    'session_end': datetime.strptime('20:00','%H:%M').time(),
    'from_previous_day': True, 'use_return_mode': False,
    'trading_days': [0,1,2,3,4], 'limit_only_entry': False,
    'min_range_size': 0.0, 'max_range_size': 999999.0,
    'use_base_sl_mode': True, 'base_sl': 0.002,
    'tp_coefficient': 1.0, 'sl_slippage_coefficient': 1.0, 'commission_rate': 0.0,
    'use_fixed_tp_sl': False,
    'use_news_filter': True, 'news_impact_filter': ['high'],
    'news_buffer_minutes': 30, 'news_currency_filter': nc,
    'skip_red_news_days': False, 'start_date': start, 'end_date': end,
}

sl_values = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
rr_values = [round(x*0.1, 1) for x in range(5, 16)]
combos = list(itertools.product(sl_values, rr_values))
print(f"Комбинаций: {len(combos)}", flush=True)

results = []
t0 = time.time()

for idx, (sl_m, rr) in enumerate(combos):
    s = base.copy()
    s['sl_multiplier'] = sl_m
    s['rr_ratio'] = rr

    res = az.analyze_period(start, end, s)
    daily_df = rg.prepare_daily_trades(res['results'], 1.0, 1.0, 0.0)
    executed = daily_df[daily_df['result'].isin(['TP','SL','BE'])]

    if executed.empty:
        continue

    cum_r = 0.0; cs = 0; loss_c = []; win_c = []
    for i, t in enumerate(executed.to_dict('records')):
        cum_r += t['r_result']
        if cum_r >= 5.0:
            win_c.append(i - cs + 1); cum_r = 0.0; cs = i + 1
        elif cum_r <= -5.0:
            loss_c.append(i - cs + 1); cum_r = 0.0; cs = i + 1

    total = len(win_c) + len(loss_c)
    results.append({
        'sl': sl_m, 'rr': rr,
        'loss': len(loss_c), 'win': len(win_c), 'tot': total,
        'loss_pct': len(loss_c)/total*100 if total else 0,
        'avg_loss': sum(loss_c)/len(loss_c) if loss_c else 999,
        'fast': min(loss_c) if loss_c else 999,
        'total_r': round(executed['r_result'].sum(), 2),
        'trades': len(executed),
    })
    print(f"  [{idx+1}/{len(combos)}] SL={sl_m} RR={rr} loss={len(loss_c)} win={len(win_c)} {time.time()-t0:.0f}s", flush=True)

results.sort(key=lambda x: (-x['loss_pct'], x['avg_loss']))

print(f"\n{'='*70}")
print(f"EURUSD — Оптимизация на максимум LOSS (-5R)")
print(f"Период: {start} — {end} | {len(combos)} комбинаций за {time.time()-t0:.0f}s")
print(f"\n{'SL':>5s} {'RR':>5s} {'Loss':>5s} {'Win':>4s} {'Tot':>4s} {'Loss%':>6s} {'AvgСд':>6s} {'Fast':>5s} {'TotR':>8s}")
print('-' * 55)
for r in results[:20]:
    print(f"{r['sl']:>5.2f} {r['rr']:>5.1f} {r['loss']:>5d} {r['win']:>4d} {r['tot']:>4d} {r['loss_pct']:>6.1f} {r['avg_loss']:>6.1f} {r['fast']:>5d} {r['total_r']:>+8.2f}")
print("\nDONE", flush=True)
