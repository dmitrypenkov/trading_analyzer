#!/usr/bin/env python3
"""
Широкий перебор внутридневных конфигов XAUUSD для поиска САМОЙ УБЫТОЧНОЙ стратегии.

Грузит данные один раз, гоняет конфиги напрямую через пайплайн (без subprocess).
Окно поиска — последние 12 мес; отдельно считается срез последних 30 дней (вырезается
из того же per-trade DataFrame, без повторного прогона).

Сетка (UTC), use_base_sl_mode=True (base_sl XAUUSD=20), news-фильтр включён:
  session-окна × block_start × rr_ratio{1.5,2.0,3.0} × sl_mult{0.1,0.3} × mode{TREND,REVERSE}

Ранжирование по total_r за 12 мес ПО ВОЗРАСТАНИЮ (худшее сверху), фильтр trades >= MIN_TRADES.
Результат: топ-15 худших в stdout + полный JSON в xauusd_loss_finder.json.
"""

import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from _xauusd_common import XauPipeline, metrics_from_df, window_dates

PROJECT_ROOT = Path(__file__).parent.parent

# Блок заканчивается до 04:00; сессия = от конца блока до 20:00 (внутри дня).
# base_sl=20 (фикс, из инструмента), sl_multiplier ПЕРЕБИРАЕМ.
# session-окна: (label, session_start, session_end, block_end, [block_start...])
BLOCK_ENDS = ["02:00", "03:00", "04:00"]
BLOCK_STARTS = ["20:00", "22:00", "00:00"]   # 20/22 = блок предыдущего дня (overnight)
SESSION_END = "20:00"
WINDOWS = [
    (f"BE{be}", be, SESSION_END, be, BLOCK_STARTS)   # session_start == block_end
    for be in BLOCK_ENDS
]

RR_RATIOS = [0.8, 1.0, 1.5, 2.0]
SL_MULTS = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
MODES = ["TREND", "REVERSE"]

MIN_TRADES = 40          # минимум сделок за 12 мес, иначе конфиг отбрасывается
SLICE_DAYS = 30          # размер недавнего среза
TOP_N = 20


def main(symbol="XAUUSD"):
    print(f"🔍 {symbol} loss-finder: загрузка данных...", flush=True)
    pipe = XauPipeline(symbol=symbol, load_from="2023-12-01")
    print(f"   свечей загружено: {pipe.candles_loaded:,}; данные по {pipe.data_last}; base_sl={pipe.base_sl}", flush=True)

    start_12m, end_12m = window_dates(pipe, months=12)
    cutoff_30d = (datetime.strptime(end_12m, "%Y-%m-%d").date() - timedelta(days=SLICE_DAYS)).strftime("%Y-%m-%d")
    print(f"   окно поиска: {start_12m} … {end_12m} | срез 30д: {cutoff_30d} … {end_12m}\n", flush=True)

    # Собираем все комбинации
    combos = []
    for label, ss, se, be, block_starts in WINDOWS:
        for bs in block_starts:
            for rr in RR_RATIOS:
                for sl in SL_MULTS:
                    for mode in MODES:
                        combos.append((label, ss, se, be, bs, rr, sl, mode))

    total = len(combos)
    print(f"Всего комбинаций: {total}\n", flush=True)

    results = []
    for i, (label, ss, se, be, bs, rr, sl, mode) in enumerate(combos, 1):
        settings = pipe.build_settings(
            block_start=bs, block_end=be, session_start=ss, session_end=se,
            mode=mode, sl_multiplier=sl, rr_ratio=rr,
        )
        df = pipe.run(settings, start_12m, end_12m)
        m12 = metrics_from_df(df)
        m30 = metrics_from_df(df, date_from=cutoff_30d)

        key = f"{label}|block {bs}-{be}|sess {ss}-{se}|RR{rr}|sl{sl}|{mode}"
        results.append({
            "key": key,
            "window": label,
            "block_start": bs, "block_end": be,
            "session_start": ss, "session_end": se,
            "rr_ratio": rr, "sl_multiplier": sl, "mode": mode,
            "m12": m12, "m30": m30,
        })
        if i % 25 == 0 or i == total:
            print(f"  [{i}/{total}] последний: {key} -> R12={m12['total_r']}", flush=True)

    # Ранжирование: худшее по total_r за 12 мес, с фильтром по числу сделок
    eligible = [r for r in results if r["m12"]["trades"] >= MIN_TRADES]
    eligible.sort(key=lambda r: r["m12"]["total_r"])

    print(f"\n{'='*100}")
    print(f"ТОП-{TOP_N} САМЫХ УБЫТОЧНЫХ КОНФИГОВ (12 мес, trades>={MIN_TRADES})")
    print(f"{'='*100}")
    print(f"{'#':>2}  {'конфиг':<58} {'R12':>8} {'тр':>4} {'WR%':>6} {'DD':>8} {'PF':>5} {'R30д':>7}")
    print("-" * 100)
    for idx, r in enumerate(eligible[:TOP_N], 1):
        m, m30 = r["m12"], r["m30"]
        print(f"{idx:>2}  {r['key']:<58} {m['total_r']:>8.2f} {m['trades']:>4} "
              f"{m['win_rate']:>6.1f} {m['max_drawdown']:>8.2f} {m['profit_factor']:>5.2f} "
              f"{m30['total_r']:>7.2f}")

    # Для контекста: лучшие (чтобы видеть симметрию)
    print(f"\nТОП-5 ЛУЧШИХ (для контекста):")
    for idx, r in enumerate(sorted(eligible, key=lambda r: -r["m12"]["total_r"])[:5], 1):
        m = r["m12"]
        print(f"{idx:>2}  {r['key']:<58} {m['total_r']:>8.2f} тр={m['trades']} WR={m['win_rate']:.1f}%")

    # Сохранение
    out = {
        "instrument": symbol,
        "generated": datetime.now().isoformat(),
        "search_window": f"{start_12m} … {end_12m}",
        "slice_30d": f"{cutoff_30d} … {end_12m}",
        "min_trades": MIN_TRADES,
        "grid": {
            "windows": [[w[0], w[1], w[2], w[3], w[4]] for w in WINDOWS],
            "rr_ratios": RR_RATIOS, "sl_mults": SL_MULTS, "modes": MODES,
        },
        "ranked_worst": eligible,
        "all_results": results,
    }
    out_file = PROJECT_ROOT / f"{symbol.lower()}_loss_finder.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n📁 Сохранено: {out_file}")

    if eligible:
        w = eligible[0]
        print(f"\n🎯 WORST = {w['key']}  (R12={w['m12']['total_r']}, R30={w['m30']['total_r']})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="XAUUSD", help="Тикер инструмента (по умолчанию XAUUSD)")
    main(ap.parse_args().symbol.upper())
