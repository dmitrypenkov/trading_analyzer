"""
Overnight grid sweep: EURUSD, USDJPY, USDCHF, NAS100
TREND + REVERSE × sl_mults × RR/risk × base_sl factors × time windows

Запуск:
    source venv_trading/bin/activate
    nohup python scripts/overnight_grid.py > /tmp/overnight_grid.log 2>&1 &

Результат: exports/overnight_grid_results.csv + /tmp/overnight_grid.log
"""
import sys, csv, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.run_backtest import run_backtest

OUTPUT_CSV = '/Volumes/WD_Passport/Trading/trading_analyzer/exports/overnight_grid_results.csv'

# ── Параметры сетки ────────────────────────────────────────────
INSTRUMENTS = [
    # (symbol, base_sl, news_currencies)
    ('EURUSD', 0.002,  ['USD', 'EUR']),
    ('USDJPY', 0.15,   ['USD', 'JPY']),
    ('USDCHF', 0.002,  ['USD', 'CHF']),
    ('NAS100', 100.0,  ['USD']),
]

SL_MULTS       = [0.1, 0.3, 0.5]
RR_RISK        = [(2.0, 1.5), (1.5, 2.0)]   # (rr_ratio, risk_pct)
MODES          = [('REVERSE', True), ('TREND', False)]
BASE_SL_FACTORS = [1.0, 1.1, 1.2, 1.3]

# block_start, block_end, session_start, session_end
TIME_WINDOWS = [
    ('20:00', '01:00', '02:00', '20:00'),  # -1h от стандарта
    ('20:00', '02:00', '03:00', '20:00'),  # стандарт
    ('20:00', '03:00', '04:00', '20:00'),  # +1h
    ('20:00', '04:00', '05:00', '20:00'),  # +2h
]

# Период — фиксируем одинаковый для всех инструментов
# (иначе EURUSD без ограничения грузит данные с 2017 = 2 мин/прогон)
START_DATE = '2022-12-01'
END_DATE   = '2026-04-12'

# ── Подсчёт итоговых комбинаций ────────────────────────────────
total = (len(INSTRUMENTS) * len(SL_MULTS) * len(RR_RISK) *
         len(MODES) * len(BASE_SL_FACTORS) * len(TIME_WINDOWS))

CSV_FIELDS = [
    'instrument', 'mode', 'sl_mult', 'rr', 'risk_pct',
    'base_sl', 'base_sl_factor',
    'block_end', 'session_start',
    'total_r', 'total_pct',
    'trades', 'win_rate', 'max_dd', 'profit_factor',
    'period', 'error',
]

# ── Запуск ─────────────────────────────────────────────────────
t_start = time.time()
done = 0

print(f'=== OVERNIGHT GRID SWEEP ===')
print(f'Комбинаций: {total}')
print(f'Вывод: {OUTPUT_CSV}')
print(f'Старт: {time.strftime("%Y-%m-%d %H:%M:%S")}')
print('=' * 40, flush=True)

with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as fout:
    writer = csv.DictWriter(fout, fieldnames=CSV_FIELDS)
    writer.writeheader()
    fout.flush()

    for symbol, base_sl_orig, nc in INSTRUMENTS:
        for mode_name, use_return in MODES:
            for sl_mult in SL_MULTS:
                for rr, risk_pct in RR_RISK:
                    for bsl_factor in BASE_SL_FACTORS:
                        for bs, be, ss, se in TIME_WINDOWS:
                            done += 1
                            base_sl = round(base_sl_orig * bsl_factor, 6)

                            row = {
                                'instrument':    symbol,
                                'mode':          mode_name,
                                'sl_mult':       sl_mult,
                                'rr':            rr,
                                'risk_pct':      risk_pct,
                                'base_sl':       base_sl,
                                'base_sl_factor': bsl_factor,
                                'block_end':     be,
                                'session_start': ss,
                                'total_r':       '',
                                'total_pct':     '',
                                'trades':        '',
                                'win_rate':      '',
                                'max_dd':        '',
                                'profit_factor': '',
                                'period':        '',
                                'error':         '',
                            }

                            try:
                                result = run_backtest({
                                    'instrument':          symbol,
                                    'block_start':         bs,
                                    'block_end':           be,
                                    'session_start':       ss,
                                    'session_end':         se,
                                    'from_previous_day':   True,
                                    'use_base_sl_mode':    True,
                                    'base_sl':             base_sl,
                                    'sl_multiplier':       sl_mult,
                                    'rr_ratio':            rr,
                                    'use_return_mode':     use_return,
                                    'use_news_filter':     True,
                                    'news_currency_filter': nc,
                                    'start_date':          START_DATE,
                                    'end_date':            END_DATE,
                                })

                                if result.get('status') == 'ok':
                                    s = result['summary']
                                    total_r   = round(s.get('total_r', 0), 2)
                                    total_pct = round(total_r * risk_pct, 2)
                                    row.update({
                                        'total_r':       total_r,
                                        'total_pct':     total_pct,
                                        'trades':        s.get('total_trades', 0),
                                        'win_rate':      round(s.get('win_rate', 0), 1),
                                        'max_dd':        round(s.get('max_drawdown', 0), 2),
                                        'profit_factor': s.get('profit_factor', 0),
                                        'period':        result.get('period', ''),
                                    })
                                else:
                                    row['error'] = result.get('message', 'unknown error')

                            except Exception as e:
                                row['error'] = str(e)[:200]
                                print(f'  ERROR {symbol} {mode_name} sl={sl_mult} rr={rr}: {e}', flush=True)

                            writer.writerow(row)
                            fout.flush()

                            # Прогресс каждые 50 прогонов
                            if done % 50 == 0:
                                elapsed = time.time() - t_start
                                eta = elapsed / done * (total - done)
                                print(
                                    f'[{done}/{total}] {elapsed/60:.1f} мин прошло, '
                                    f'~{eta/60:.0f} мин осталось | '
                                    f'последний: {symbol} {mode_name} sl={sl_mult} rr={rr} '
                                    f'bsl×{bsl_factor} w={be}/{ss} → {row.get("total_pct","?")}%',
                                    flush=True
                                )

elapsed_total = time.time() - t_start
print(f'\n=== ГОТОВО ===')
print(f'Всего прогонов: {done}')
print(f'Время: {elapsed_total/60:.1f} мин')
print(f'Результаты: {OUTPUT_CSV}')
print(f'Финиш: {time.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
