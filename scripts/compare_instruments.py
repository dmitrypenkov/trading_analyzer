"""
Сравнение двух конфигураций риска/RR для нескольких инструментов
A: r=2%,   RR=1.5, sl=0.1, REVERSE
B: r=1.5%, RR=2.0, sl=0.1, REVERSE
"""
import sys, json
from datetime import datetime, date
import pandas as pd

sys.path.insert(0, '/Volumes/WD_Passport/Trading/trading_analyzer')
from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator

init_db()
instr_repo  = InstrumentRepository()
candle_repo = CandleRepository()
news_repo   = NewsRepository()

INSTRUMENTS = [
    ('NAS100', 100.0, ['USD']),
    ('XAUUSD',  20.0, ['USD']),
    ('GER40',   80.0, ['EUR']),
]
CONFIGS = [
    (1.5, 2.0, 'A: r=2%  RR=1.5'),
    (2.0, 1.5, 'B: r=1.5% RR=2.0'),
]

def get_trades(price_df, news_df, rr, base_sl, nc, start_date, end_date):
    s = {
        'block_start':   datetime.strptime('20:00', '%H:%M').time(),
        'block_end':     datetime.strptime('02:00', '%H:%M').time(),
        'session_start': datetime.strptime('03:00', '%H:%M').time(),
        'session_end':   datetime.strptime('20:00', '%H:%M').time(),
        'from_previous_day': True,
        'use_base_sl_mode': True,
        'base_sl': base_sl, 'sl_multiplier': 0.1, 'rr_ratio': rr,
        'use_return_mode': True,
        'use_news_filter': True,
        'news_impact_filter': ['high'],
        'news_buffer_minutes': 30,
        'news_currency_filter': nc,
        'skip_red_news_days': False,
        'trading_days': [0, 1, 2, 3, 4],
        'limit_only_entry': False,
        'min_range_size': 0.0, 'max_range_size': 999999.0,
        'tp_coefficient': 1.0, 'sl_slippage_coefficient': 1.0,
        'commission_rate': 0.0, 'use_fixed_tp_sl': False,
        'threshold_min': 0, 'threshold_max': 999999,
        'fixed_tp_distance': 0, 'fixed_sl_distance': 0,
        'start_date': start_date, 'end_date': end_date,
    }
    dp  = DataProcessor(price_df, news_df)
    res = TradingAnalyzer(dp).analyze_period(start_date, end_date, s)
    df  = ReportGenerator(RCalculator()).prepare_daily_trades(res['results'], 1.0, 1.0, 0.0)
    df  = df[df['result'].isin(['TP', 'SL', 'BE'])].copy()
    df['date']  = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M')
    df['year']  = df['date'].dt.year
    return df

for symbol, base_sl, nc in INSTRUMENTS:
    instr      = instr_repo.get_by_symbol(symbol)
    dr         = candle_repo.get_date_range(instr['id'], '15m')
    start_date = pd.to_datetime(dr[0]).date()
    end_date   = date(2026, 4, 12)
    n_months   = round((end_date - start_date).days / 30.5, 1)

    print(f'\n{"="*70}')
    print(f'=== {symbol} | sl=0.1 | REVERSE | {start_date} — {end_date} ({n_months:.0f} мес) ===')
    print(f'{"="*70}')

    price_df = candle_repo.get_dataframe(instr['id'], '15m', start_date, end_date)
    news_df  = news_repo.get_dataframe(start_date, end_date)

    dfs = {}
    for rr, risk_pct, label in CONFIGS:
        df = get_trades(price_df, news_df, rr, base_sl, nc, start_date, end_date)
        df['pct'] = df['r_result'] * risk_pct
        dfs[label] = df
        sys.stdout.flush()

    # --- Итоги ---
    for label, df in dfs.items():
        n   = len(df)
        tp  = (df['result'] == 'TP').sum()
        sl  = (df['result'] == 'SL').sum()
        be  = (df['result'] == 'BE').sum()
        tot = df['pct'].sum()
        wr  = tp / n * 100 if n else 0
        mo  = df.groupby('month')['pct'].sum()
        neg = (mo < 0).sum()
        worst = mo.min()
        best  = mo.max()
        cum   = df.sort_values('date')['pct'].cumsum()
        maxdd = (cum - cum.cummax()).min()
        print(f'  {label}')
        print(f'    Сделок: {n} (TP={tp} SL={sl} BE={be})  WR={wr:.1f}%')
        print(f'    Total: {tot:+.1f}%  /год: {tot/(n_months/12):+.1f}%  /мес: {tot/len(mo):+.2f}%')
        print(f'    Худший мес: {worst:+.1f}%  Лучший: {best:+.1f}%  Минусовых: {neg}/{len(mo)}')
        print(f'    Макс просадка: {maxdd:+.1f}%')

    # --- По годам ---
    df_a = dfs['A: r=2%  RR=1.5']
    df_b = dfs['B: r=1.5% RR=2.0']
    print()
    print(f"  {'Год':>5} | {'A r=2% RR=1.5':>14} | {'B r=1.5% RR=2':>14} | {'Хуже':>5}")
    print('  ' + '-'*45)
    for yr in sorted(set(df_a['year']) | set(df_b['year'])):
        a = df_a[df_a['year'] == yr]['pct'].sum()
        b = df_b[df_b['year'] == yr]['pct'].sum()
        worse = 'A' if a < b else ('B' if b < a else '=')
        print(f'  {yr:>5} | {a:>+13.1f}% | {b:>+13.1f}% | {worse:>5}')

    # --- Помесячно ---
    mo_a = df_a.groupby('month')['pct'].sum()
    mo_b = df_b.groupby('month')['pct'].sum()
    all_months = sorted(set(mo_a.index) | set(mo_b.index))
    print()
    print(f"  {'Месяц':>8} | {'A r=2% RR=1.5':>14} | {'B r=1.5% RR=2':>14} | {'Хуже':>5}")
    print('  ' + '-'*50)
    cum_a = cum_b = 0.0
    for mo in all_months:
        a = mo_a.get(mo, 0.0)
        b = mo_b.get(mo, 0.0)
        cum_a += a; cum_b += b
        worse = 'A' if a < b else ('B' if b < a else '=')
        print(f'  {str(mo):>8} | {a:>+13.1f}% | {b:>+13.1f}% | {worse:>5}')
    print('  ' + '-'*50)
    print(f"  {'ИТОГО':>8} | {cum_a:>+13.1f}% | {cum_b:>+13.1f}% |")

print('\nДONE')
