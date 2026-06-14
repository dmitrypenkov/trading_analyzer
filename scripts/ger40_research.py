"""
GER40 REVERSE — полное исследование с правильными временами
Блок: 20:00–07:00 (азиатская ночная консолидация)
Сессия: 07:00–20:00 (европейская + US)
"""
import sys, calendar as cal
sys.path.insert(0, '/Volumes/WD_Passport/Trading/trading_analyzer')
from scripts.run_backtest import run_backtest
from datetime import date

START = '2022-12-02'
END   = '2026-04-12'

common = dict(
    instrument='GER40',
    block_start='20:00', block_end='07:00',
    session_start='07:00', session_end='20:00',
    from_previous_day=True,
    use_base_sl_mode=True, base_sl=80.0,
    use_return_mode=True,
    use_news_filter=True,
    start_date=START, end_date=END,
)

# ── 1. GRID SWEEP ──────────────────────────────────────────────
sl_mults = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
rr_ratios = [1.0, 1.2, 1.5, 2.0, 3.0]

print('=== GRID SWEEP GER40 REVERSE (блок 20:00-07:00 / сессия 07:00-20:00) ===')
print(f"{'sl_mult':>8} | " + ' | '.join(f'RR={rr:<4}' for rr in rr_ratios))
print('-' * 65)

grid_results = []
for sl in sl_mults:
    row = [f'{sl:>8}']
    for rr in rr_ratios:
        v = run_backtest({**common, 'sl_multiplier': sl, 'rr_ratio': rr}).get('summary', {}).get('total_r', 0)
        grid_results.append((v, sl, rr))
        row.append(f'{v:>+7.1f}')
    print(' | '.join(row), flush=True)

print()
print('Топ-5 убыточных:')
for v, sl, rr in sorted(grid_results)[:5]:
    print(f'  sl={sl}, RR={rr} -> {v:+.1f}R')
print()

# ── 2. ВРЕМЕННЫЕ ОКНА × МЕСЯЦЫ для sl=0.1 (RR 1.5, 2.0, 3.0) ─
# Сдвигаем block_end/session_start от 07:00 до 12:00
windows = [
    ('07:00', '07:00'),
    ('08:00', '08:00'),
    ('09:00', '09:00'),
    ('10:00', '10:00'),
    ('11:00', '11:00'),
    ('12:00', '12:00'),
]

months = []
yr, mo = 2022, 12
e_date = date(2026, 4, 12)
while date(yr, mo, 1) <= e_date:
    last  = cal.monthrange(yr, mo)[1]
    end_d = 12 if (yr == 2026 and mo == 4) else last
    months.append((f'{yr}-{mo:02d}', f'{yr}-{mo:02d}-01', f'{yr}-{mo:02d}-{end_d:02d}'))
    mo += 1
    if mo > 12:
        mo = 1; yr += 1

w_labels = [f'bl/s{ss[:2]}' for _, ss in windows]
header = f"{'Month':>8} | " + ' | '.join(f'{l:>8}' for l in w_labels)
sep = '-' * len(header)

for rr in [1.5, 2.0, 3.0]:
    print(f'=== GER40 | sl=0.1 | RR={rr} | REVERSE — месяцы × окна ===')
    print(header); print(sep)
    all_r = {w: [] for w in windows}
    for label, start, end in months:
        row = [f'{label:>8}']
        for w in windows:
            v = run_backtest({
                **common,
                'sl_multiplier': 0.1, 'rr_ratio': rr,
                'block_end': w[0], 'session_start': w[1],
                'start_date': start, 'end_date': end,
            }).get('summary', {}).get('total_r', 0)
            all_r[w].append(v)
            row.append(f'{v:>+8.1f}')
        print(' | '.join(row), flush=True)
    print()
    print(f"{'ИТОГО':>8} | " + ' | '.join(f'{sum(all_r[w]):>+8.1f}' for w in windows))
    print(f"{'+ мес':>8} | " + ' | '.join(f'{sum(1 for v in all_r[w] if v > 0):>8}' for w in windows))
    print(f"{'- мес':>8} | " + ' | '.join(f'{sum(1 for v in all_r[w] if v <= 0):>8}' for w in windows))
    print(f"{'Худший':>8} | " + ' | '.join(f'{min(all_r[w]):>+8.1f}' for w in windows))
    print()

# ── 3. СРАВНЕНИЕ r% по месяцам (b20/s07 — стандарт) ──────────
print('=== СРАВНЕНИЕ: r=2% RR=1.5 vs r=1.5% RR=2.0 | GER40 REVERSE | b20/s07 ===')
configs_pct = [(1.5, 2.0, 'A r=2%  RR=1.5'), (2.0, 1.5, 'B r=1.5% RR=2.0')]

mo_data = {}
for rr, risk_pct, label in configs_pct:
    mo_r = {}
    for lbl, start, end in months:
        v = run_backtest({
            **common,
            'sl_multiplier': 0.1, 'rr_ratio': rr,
            'block_end': '07:00', 'session_start': '07:00',
            'start_date': start, 'end_date': end,
        }).get('summary', {}).get('total_r', 0)
        mo_r[lbl] = v * risk_pct
    mo_data[label] = mo_r

print(f"{'Месяц':>8} | {'A r=2% RR=1.5':>14} | {'B r=1.5% RR=2':>14} | {'Хуже':>5}")
print('-' * 50)
cum_a = cum_b = 0.0
for lbl, _, _ in months:
    a = mo_data['A r=2%  RR=1.5'].get(lbl, 0)
    b = mo_data['B r=1.5% RR=2.0'].get(lbl, 0)
    cum_a += a; cum_b += b
    worse = 'A' if a < b else ('B' if b < a else '=')
    print(f'{lbl:>8} | {a:>+13.1f}% | {b:>+13.1f}% | {worse:>5}')
print('-' * 50)
print(f"{'ИТОГО':>8} | {cum_a:>+13.1f}% | {cum_b:>+13.1f}% |")
print('\nDONE')
