#!/usr/bin/env python3
"""
Свип убыточных стратегий: все инструменты × TREND/REVERSE × 2 окна × 2 RR/risk × 3 sl_mult
Период: 2024-01-01 — 2026-04-13
Выход: exports/losing_sweep_2024_report.txt
"""
import sys, time, logging
from pathlib import Path
from datetime import datetime, date

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
logging.disable(logging.CRITICAL)

from db.connection import init_db
from db.repository import InstrumentRepository, CandleRepository, NewsRepository
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator

# ── Параметры ──────────────────────────────────────────────────────────────────
START_DATE  = date(2024, 1, 1)
END_DATE    = date(2026, 4, 13)
OUTPUT_FILE = PROJECT_ROOT / 'exports' / 'losing_sweep_2024_report.txt'

INSTRUMENTS = [
    ('EURUSD', ['USD', 'EUR']),
    ('USDJPY', ['USD', 'JPY']),
    ('USDCHF', ['USD', 'CHF']),
    ('NAS100', ['USD']),
    ('XAUUSD', ['USD']),
    ('GER40',  ['EUR']),
]

SL_MULTS = [0.1, 0.3, 0.5]

RR_CONFIGS = [
    (2.0, 1.5, 'RR=2.0 | risk=1.5%'),
    (1.5, 2.0, 'RR=1.5 | risk=2.0%'),
]

MODES = [
    ('REVERSE', True),
    ('TREND',   False),
]

WINDOWS = [
    ('W1', '20:00', '02:00', '03:00', '20:00', 'Block 20:00–02:00 / Session 03:00–20:00'),
    ('W2', '16:00', '00:15', '00:30', '20:00', 'Block 16:00–00:15 / Session 00:30–20:00'),
]

BASE_SETTINGS = {
    'from_previous_day':      True,
    'use_base_sl_mode':       True,
    'tp_multiplier':          1.0,
    'tp_coefficient':         1.0,
    'sl_slippage_coefficient': 1.0,
    'commission_rate':        0.0,
    'trading_days':           [0, 1, 2, 3, 4],
    'limit_only_entry':       False,
    'min_range_size':         0.0,
    'max_range_size':         999999.0,
    'use_fixed_tp_sl':        False,
    'threshold_min':          0,
    'threshold_max':          999999,
    'fixed_tp_distance':      0,
    'fixed_sl_distance':      0,
    'skip_red_news_days':     False,
    'use_news_filter':        True,
    'news_impact_filter':     ['high'],
    'news_buffer_minutes':    30,
}


# ── Один прогон ────────────────────────────────────────────────────────────────
def run_one(price_df, news_df, settings_dict):
    dp  = DataProcessor(price_df, news_df)
    ana = TradingAnalyzer(dp)
    rc  = RCalculator()
    rg  = ReportGenerator(rc)

    sa = settings_dict.copy()
    for key in ('block_start', 'block_end', 'session_start', 'session_end'):
        sa[key] = datetime.strptime(settings_dict[key], "%H:%M").time()
    sa['start_date'] = START_DATE
    sa['end_date']   = END_DATE

    res        = ana.analyze_period(START_DATE, END_DATE, sa)
    daily_df   = rg.prepare_daily_trades(
        res['results'],
        settings_dict.get('tp_coefficient', 1.0),
        settings_dict.get('sl_slippage_coefficient', 1.0),
        settings_dict.get('commission_rate', 0.0),
    )
    summary = rg.generate_summary_report(daily_df)

    # ── собираем месячные данные ────────────────────────────────────────────
    monthly = []
    for yr in summary.get('yearly_reports', []):
        for m in yr.get('months_data', []):
            if m.get('executed_trades', 0) == 0:
                continue
            monthly.append({
                'month':   m['month'],
                'trades':  m['executed_trades'],
                'total_r': round(m.get('total_r', 0.0), 2),
                'win_rate': round(m.get('win_rate', 0.0), 1),
                'tp': m.get('tp_count', 0),
                'sl': m.get('sl_count', 0),
                'be': m.get('be_count', 0),
            })

    total_tp  = summary.get('total_tp', 0)
    total_sl  = summary.get('total_sl', 0)
    total_be  = summary.get('total_be', 0)
    executed  = total_tp + total_sl + total_be
    total_r   = round(summary.get('total_r', 0.0), 2)
    win_rate  = round(total_tp / executed * 100, 1) if executed > 0 else 0.0
    max_dd    = round(summary.get('max_drawdown', {}).get('max_drawdown', 0.0), 2)

    return {
        'total_r':   total_r,
        'executed':  executed,
        'win_rate':  win_rate,
        'max_dd':    max_dd,
        'monthly':   monthly,
    }


# ── Генерация текстового отчёта ────────────────────────────────────────────────
def generate_report(results, elapsed_min):
    W = 96
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []

    def hdr(text, char='='):
        lines.append(char * W)
        lines.append(f'  {text}')
        lines.append(char * W)

    def row_fmt(sym, mode, sl, total_pct, total_r, trades, wr, max_dd):
        sign_pct = '+' if total_pct >= 0 else ''
        sign_r   = '+' if total_r   >= 0 else ''
        return (
            f"  {sym:<9} {mode:<8} {sl:<5}  "
            f"{sign_pct}{total_pct:>8.1f}%  "
            f"{sign_r}{total_r:>8.2f}R  "
            f"{trades:>6}  {wr:>5.1f}%  {max_dd:>+8.2f}R"
        )

    col_header = (
        f"  {'Инстр.':<9} {'Режим':<8} {'SL':<5}  "
        f"{'Total%':>9}  {'TotalR':>9}  {'Trades':>6}  {'WR%':>6}  {'MaxDD':>9}"
    )
    col_sep = "  " + "-" * 9 + " " + "-" * 8 + " " + "-" * 5 + "  " + "-" * 9 + "  " + "-" * 9 + "  " + "-" * 6 + "  " + "-" * 6 + "  " + "-" * 9

    hdr(f'СВИП УБЫТОЧНЫХ СТРАТЕГИЙ | Период: {START_DATE} — {END_DATE} | {ts}')
    lines.append(f'  Прогонов: {len(results)} | Время: {elapsed_min:.1f} мин')
    lines.append('')

    # ── Глобальная сводка (top-30 худших) ─────────────────────────────────
    hdr('ТОП-30 ХУДШИХ КОМБИНАЦИЙ (по убыванию убытков)', '-')
    lines.append(col_header)
    lines.append(col_sep)
    top30 = sorted(results, key=lambda x: x['total_pct'])[:30]
    for r in top30:
        lines.append(row_fmt(
            r['symbol'], r['mode'], r['sl_mult'],
            r['total_pct'], r['total_r'], r['executed'],
            r['win_rate'], r['max_dd']
        ) + f"  | {r['rr_label']} | {r['window']}")
    lines.append('')

    # ── Секции по RR config → Window ──────────────────────────────────────
    for rr, risk_pct, rr_label in RR_CONFIGS:
        hdr(rr_label.upper())
        lines.append('')

        for wname, bs, be, ss, se, wlabel in WINDOWS:
            lines.append(f'  [{wname}]  {wlabel}')
            lines.append(col_header)
            lines.append(col_sep)

            subset = [r for r in results
                      if r['rr'] == rr and r['risk_pct'] == risk_pct and r['window'] == wname]
            subset_sorted = sorted(subset, key=lambda x: x['total_pct'])  # worst first

            for r in subset_sorted:
                lines.append(row_fmt(
                    r['symbol'], r['mode'], r['sl_mult'],
                    r['total_pct'], r['total_r'], r['executed'],
                    r['win_rate'], r['max_dd']
                ))
            lines.append('')

    # ── Помесячная разбивка ────────────────────────────────────────────────
    hdr('ПОМЕСЯЧНАЯ РАЗБИВКА — ХУДШИЙ КОНФИГ НА ИНСТРУМЕНТ')
    lines.append('')

    for symbol, _ in INSTRUMENTS:
        sym_res = [r for r in results if r['symbol'] == symbol]
        if not sym_res:
            continue

        # Сортируем по худшим: выбираем абсолютно худший (минимальный total_pct)
        worst = min(sym_res, key=lambda x: x['total_pct'])

        hdr(
            f'{symbol} | Худший: {worst["mode"]} sl={worst["sl_mult"]} '
            f'{worst["rr_label"]} {worst["window"]}',
            '-'
        )
        sign = '+' if worst['total_pct'] >= 0 else ''
        lines.append(
            f'  Total: {sign}{worst["total_pct"]:.1f}% ({worst["total_r"]:+.2f}R) | '
            f'WR={worst["win_rate"]:.1f}% | MaxDD={worst["max_dd"]:+.2f}R | '
            f'Trades={worst["executed"]}'
        )
        lines.append('')

        if worst['monthly']:
            lines.append(
                f'  {"Месяц":<9}  {"TP":>4}  {"SL":>4}  {"BE":>4}  '
                f'{"WR%":>6}  {"МесR":>8}  {"CumR":>9}'
            )
            lines.append(
                f'  {"-"*9}  {"-"*4}  {"-"*4}  {"-"*4}  '
                f'{"-"*6}  {"-"*8}  {"-"*9}'
            )
            cum_r = 0.0
            for m in worst['monthly']:
                cum_r += m['total_r']
                lines.append(
                    f'  {m["month"]:<9}  {m["tp"]:>4}  {m["sl"]:>4}  {m["be"]:>4}  '
                    f'{m["win_rate"]:>5.1f}%  {m["total_r"]:>+8.2f}  {cum_r:>+9.2f}'
                )
        else:
            lines.append('  (нет исполненных сделок)')
        lines.append('')

        # Дополнительно — ТОП-3 худших по каждому окну для этого инструмента
        lines.append(f'  Все результаты {symbol} (сортировка: от худшего):')
        lines.append(col_header)
        lines.append(col_sep)
        sym_sorted = sorted(sym_res, key=lambda x: x['total_pct'])
        for r in sym_sorted:
            lines.append(row_fmt(
                r['symbol'], r['mode'], r['sl_mult'],
                r['total_pct'], r['total_r'], r['executed'],
                r['win_rate'], r['max_dd']
            ) + f"  | {r['rr_label']} | {r['window']}")
        lines.append('')

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    init_db()
    instr_repo  = InstrumentRepository()
    candle_repo = CandleRepository()
    news_repo   = NewsRepository()

    print('Загружаю новости...')
    news_df_raw = news_repo.get_dataframe(START_DATE, END_DATE)
    news_df     = news_df_raw if not news_df_raw.empty else None
    print(f'  Новостей: {len(news_df_raw) if news_df is not None else 0}')

    # ── Кешируем цены по инструментам ─────────────────────────────────────
    instr_data = {}
    price_dfs  = {}
    for symbol, nc in INSTRUMENTS:
        instr = instr_repo.get_by_symbol(symbol)
        if not instr:
            print(f'  WARN: {symbol} не найден в БД')
            continue
        price_df = candle_repo.get_dataframe(instr['id'], '15m', START_DATE, END_DATE)
        if price_df.empty:
            print(f'  WARN: {symbol} — нет свечей')
            continue
        instr_data[symbol] = instr
        price_dfs[symbol]  = price_df
        print(f'  {symbol}: {len(price_df)} свечей, base_sl={instr["base_sl"]}')

    total = len(INSTRUMENTS) * len(MODES) * len(RR_CONFIGS) * len(WINDOWS) * len(SL_MULTS)
    print(f'\nКомбинаций: {total}')
    print('=' * 60)

    all_results = []
    done = 0
    t0   = time.time()

    for symbol, nc in INSTRUMENTS:
        if symbol not in price_dfs:
            continue
        price_df = price_dfs[symbol]
        base_sl  = instr_data[symbol].get('base_sl', 0)

        for mode_name, use_return_mode in MODES:
            for rr, risk_pct, rr_label in RR_CONFIGS:
                for wname, bs, be, ss, se, wlabel in WINDOWS:
                    for sl_mult in SL_MULTS:
                        done += 1
                        t1 = time.time()

                        settings = {
                            **BASE_SETTINGS,
                            'block_start':         bs,
                            'block_end':           be,
                            'session_start':        ss,
                            'session_end':          se,
                            'base_sl':             base_sl,
                            'sl_multiplier':       sl_mult,
                            'rr_ratio':            rr,
                            'use_return_mode':     use_return_mode,
                            'news_currency_filter': nc,
                        }

                        try:
                            out = run_one(price_df, news_df, settings)
                            total_pct = round(out['total_r'] * risk_pct, 2)

                            all_results.append({
                                'symbol':    symbol,
                                'mode':      mode_name,
                                'rr':        rr,
                                'risk_pct':  risk_pct,
                                'rr_label':  rr_label,
                                'window':    wname,
                                'wlabel':    wlabel,
                                'sl_mult':   sl_mult,
                                'total_r':   out['total_r'],
                                'total_pct': total_pct,
                                'executed':  out['executed'],
                                'win_rate':  out['win_rate'],
                                'max_dd':    out['max_dd'],
                                'monthly':   out['monthly'],
                            })

                            elapsed = time.time() - t1
                            eta = (time.time() - t0) / done * (total - done) / 60
                            print(
                                f'[{done:>3}/{total}] {symbol:<7} {mode_name:<8} '
                                f'sl={sl_mult} rr={rr} risk={risk_pct}% {wname}  '
                                f'{total_pct:>+8.1f}%  ({elapsed:.1f}s)  ETA~{eta:.0f}мин'
                            )

                        except Exception as e:
                            print(f'[{done:>3}/{total}] ERROR {symbol} {mode_name} sl={sl_mult}: {e}')

    elapsed_total = (time.time() - t0) / 60
    print(f'\nГотово: {len(all_results)} прогонов за {elapsed_total:.1f} мин')
    print('Генерирую отчёт...')
    generate_report(all_results, elapsed_total)
    print(f'Отчёт сохранён: {OUTPUT_FILE}')


if __name__ == '__main__':
    main()
