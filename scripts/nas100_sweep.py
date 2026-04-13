#!/usr/bin/env python3
"""NAS100 sweep — данные загружаются один раз, все комбо in-memory."""
import sys, logging, time
logging.disable(logging.CRITICAL)
sys.path.insert(0, '/Volumes/WD_Passport/Trading/trading_analyzer')

from datetime import datetime, date
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator

START = date(2022, 12, 1)
END   = date(2026, 4, 12)

WINDOWS = [
    ('18:00', '01:00', '02:00'),
    ('18:00', '02:00', '03:00'),
    ('18:00', '03:00', '04:00'),
    ('18:00', '04:00', '05:00'),
    ('19:00', '01:00', '02:00'),
    ('19:00', '02:00', '03:00'),
    ('19:00', '03:00', '04:00'),
    ('19:00', '04:00', '05:00'),
    ('20:00', '01:00', '02:00'),
    ('20:00', '02:00', '03:00'),
    ('20:00', '03:00', '04:00'),
    ('20:00', '04:00', '05:00'),
]

t0 = time.time()
print("Загружаем данные...", flush=True)
init_db()
ir = InstrumentRepository()
cr = CandleRepository()
nr = NewsRepository()

instr = ir.get_by_symbol('NAS100')
price_df = cr.get_dataframe(instr['id'], '15m', START, END)
news_df  = nr.get_dataframe(START, END)
print(f"Свечей: {len(price_df)}, Новостей: {len(news_df)}, загрузка: {time.time()-t0:.1f}s", flush=True)

dp  = DataProcessor(price_df, news_df)
az  = TradingAnalyzer(dp)
rc  = RCalculator()
rg  = ReportGenerator(rc)

rows = []
n = 0
total = 2 * 2 * 2 * len(WINDOWS)

for mode, use_return in [('REVERSE', True), ('TREND', False)]:
    for sl in [0.1, 0.3]:
        for rr, risk in [(2.0, 1.5), (1.5, 2.0)]:
            for bs, be, ss in WINDOWS:
                settings = {
                    'block_start':  datetime.strptime(bs, '%H:%M').time(),
                    'block_end':    datetime.strptime(be, '%H:%M').time(),
                    'session_start':datetime.strptime(ss, '%H:%M').time(),
                    'session_end':  datetime.strptime('20:00', '%H:%M').time(),
                    'from_previous_day': True,
                    'use_return_mode': use_return,
                    'use_base_sl_mode': True, 'base_sl': 100.0,
                    'sl_multiplier': sl, 'rr_ratio': rr,
                    'tp_multiplier': 1.0, 'tp_coefficient': 1.0,
                    'sl_slippage_coefficient': 1.0, 'commission_rate': 0.0,
                    'trading_days': [0,1,2,3,4], 'limit_only_entry': False,
                    'min_range_size': 0.0, 'max_range_size': 999999.0,
                    'use_fixed_tp_sl': False, 'threshold_min': 0, 'threshold_max': 999999,
                    'use_news_filter': True, 'news_impact_filter': ['high'],
                    'news_buffer_minutes': 30, 'news_currency_filter': ['USD'],
                    'skip_red_news_days': False,
                    'start_date': START, 'end_date': END,
                }
                res = az.analyze_period(START, END, settings)
                df  = rg.prepare_daily_trades(res['results'], 1.0, 1.0, 0.0)
                ex  = df[df['result'].isin(['TP','SL','BE'])]
                total_r   = round(ex['r_result'].sum(), 1) if not ex.empty else 0.0
                total_pct = round(total_r * risk, 1)
                wr = round(len(ex[ex['result']=='TP']) / len(ex) * 100, 1) if len(ex) > 0 else 0.0
                rows.append((total_pct, total_r, mode, sl, rr, risk, bs, be, ss, wr, len(ex)))
                n += 1
                if n % 12 == 0:
                    print(f"  [{n}/{total}] {time.time()-t0:.0f}s", flush=True)

rows.sort()
print(f"\nГотово за {time.time()-t0:.1f}s")
print(f"\n{'Mode':7s} {'sl':4s} {'RR':4s} {'r%':4s} {'bs':6s} {'be':6s} {'ss':6s}  {'Total%':>8s}  {'TotalR':>7s}  {'WR%':>5s}  {'Tr':>4s}")
print('-'*78)
print("=== ТОП УБЫТОЧНЫХ ===")
for total_pct, total_r, mode, sl, rr, risk, bs, be, ss, wr, tr in rows[:15]:
    print(f"{mode:7s} {sl:4.1f} {rr:4.1f} {risk:4.1f} {bs:6s} {be:6s} {ss:6s}  {total_pct:>8.1f}%  {total_r:>+7.1f}R  {wr:>5.1f}%  {tr:>4d}")
print("\n=== ТОП ПРИБЫЛЬНЫХ ===")
for total_pct, total_r, mode, sl, rr, risk, bs, be, ss, wr, tr in rows[-5:]:
    print(f"{mode:7s} {sl:4.1f} {rr:4.1f} {risk:4.1f} {bs:6s} {be:6s} {ss:6s}  {total_pct:>8.1f}%  {total_r:>+7.1f}R  {wr:>5.1f}%  {tr:>4d}")
