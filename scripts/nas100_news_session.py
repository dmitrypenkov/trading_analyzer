#!/usr/bin/env python3
"""
NAS100 «после новостей»: сессия стартует 14:30 UTC (= 17:30 UTC+3), до 20:00 UTC.
Блок = диапазон ДО 14:30 (вокруг/до новостей), сделка — на выходе после.

Данные NAS100 после ~2026-03 только cash (см. memory data_coverage_indices),
поэтому основной ранкинг считаем на чистом периоде 2024-01…2026-03.
Блок 13:30-14:30 укладывается в cash-сессию => такой конфиг считается и на свежих данных
(для него отдельно показываем полный период).

Сетка: block_start × RR{0.8,1,1.5,2} × sl_mult{0.1,0.2,0.3,0.5,0.7,1} × {TREND,REVERSE}.
"""

import json
from pathlib import Path

from _xauusd_common import XauPipeline, metrics_from_df

PROJECT_ROOT = Path(__file__).parent.parent

SESSION_START = "14:30"   # 17:30 UTC+3
SESSION_END = "20:00"
BLOCK_END = "14:30"       # сессия сразу за блоком
BLOCK_STARTS = ["13:30", "12:30", "11:00", "08:00", "00:00", "20:00"]  # 13:30 = cash-robust
RR_RATIOS = [0.8, 1.0, 1.5, 2.0]
SL_MULTS = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
MODES = ["TREND", "REVERSE"]

CLEAN_START = "2024-01-01"
CLEAN_END = "2026-03-31"   # дальше у NAS100 только cash-данные
MIN_TRADES = 30


def run_grid(pipe, start, end):
    rows = []
    for bs in BLOCK_STARTS:
        for rr in RR_RATIOS:
            for sl in SL_MULTS:
                for mode in MODES:
                    st = pipe.build_settings(
                        block_start=bs, block_end=BLOCK_END,
                        session_start=SESSION_START, session_end=SESSION_END,
                        mode=mode, sl_multiplier=sl, rr_ratio=rr,
                    )
                    df = pipe.run(st, start, end)
                    m = metrics_from_df(df)
                    rows.append({
                        "key": f"block {bs}-{BLOCK_END}|sess {SESSION_START}-{SESSION_END}|RR{rr}|sl{sl}|{mode}",
                        "block_start": bs, "rr": rr, "sl": sl, "mode": mode, "m": m,
                    })
    return rows


def show(title, rows, n=10):
    print(title)
    print(f"{'#':>2}  {'конфиг':<56} {'R':>8} {'тр':>4} {'WR%':>6} {'DD':>8} {'PF':>5}")
    print("-" * 96)
    for i, r in enumerate(rows[:n], 1):
        m = r["m"]
        print(f"{i:>2}  {r['key']:<56} {m['total_r']:>8.2f} {m['trades']:>4} "
              f"{m['win_rate']:>6.1f} {m['max_drawdown']:>8.2f} {m['profit_factor']:>5.2f}")
    print()


def main():
    print("=" * 96)
    print("NAS100 ПОСЛЕ НОВОСТЕЙ — сессия 14:30-20:00 UTC (17:30-23:00 UTC+3)")
    print(f"Чистый период: {CLEAN_START} … {CLEAN_END} (далее только cash-данные)")
    print("=" * 96 + "\n")

    pipe = XauPipeline(symbol="NAS100", load_from="2023-12-01")
    end_full = str(pipe.data_last)

    rows = run_grid(pipe, CLEAN_START, CLEAN_END)
    eligible = [r for r in rows if r["m"]["trades"] >= MIN_TRADES]

    worst = sorted(eligible, key=lambda r: r["m"]["total_r"])
    best = sorted(eligible, key=lambda r: -r["m"]["total_r"])

    show("ТОП-10 ПРИБЫЛЬНЫХ (после новостей):", best, 10)
    show("ТОП-10 УБЫТОЧНЫХ (после новостей):", worst, 10)

    # Инверсия лучшего убыточного: помогает ли переворот в ЭТОМ окне?
    w = worst[0]
    inv_mode = "TREND" if w["mode"] == "REVERSE" else "REVERSE"
    st_inv = pipe.build_settings(block_start=w["block_start"], block_end=BLOCK_END,
                                 session_start=SESSION_START, session_end=SESSION_END,
                                 mode=inv_mode, sl_multiplier=w["sl"], rr_ratio=w["rr"])
    m_inv = metrics_from_df(pipe.run(st_inv, CLEAN_START, CLEAN_END))
    print("-" * 96)
    print("ИНВЕРСИЯ ХУДШЕГО (работает ли переворот в after-news окне?)")
    print(f"  BASE   {w['key']}")
    print(f"         R={w['m']['total_r']:.2f}  WR={w['m']['win_rate']:.1f}%  PF={w['m']['profit_factor']:.2f}")
    print(f"  INV -> {inv_mode}: R={m_inv['total_r']:.2f}  WR={m_inv['win_rate']:.1f}%  PF={m_inv['profit_factor']:.2f}")
    print()

    # Cash-robust конфиги (block 13:30) на ПОЛНОМ периоде, включая свежие cash-данные
    print("-" * 96)
    print(f"CASH-ROBUST (block 13:30-14:30) на ПОЛНОМ периоде {CLEAN_START} … {end_full}")
    print("(этот блок целиком в cash-сессии => считается и на свежих данных после 03.2026)")
    print(f"{'конфиг':<56} {'R_чист':>8} {'R_полн':>8} {'тр_полн':>8}")
    cash_rows = [r for r in best if r["block_start"] == "13:30"][:6]
    for r in cash_rows:
        st = pipe.build_settings(block_start="13:30", block_end=BLOCK_END,
                                 session_start=SESSION_START, session_end=SESSION_END,
                                 mode=r["mode"], sl_multiplier=r["sl"], rr_ratio=r["rr"])
        m_full = metrics_from_df(pipe.run(st, CLEAN_START, end_full))
        print(f"{r['key']:<56} {r['m']['total_r']:>8.2f} {m_full['total_r']:>8.2f} {m_full['trades']:>8}")

    # Сохранение
    out = {
        "instrument": "NAS100",
        "session": f"{SESSION_START}-{SESSION_END} UTC (после новостей, 17:30 UTC+3)",
        "clean_period": f"{CLEAN_START} … {CLEAN_END}",
        "best": best[:15], "worst": worst[:15],
        "inversion_of_worst": {"inv_mode": inv_mode, "metrics": m_inv},
    }
    (PROJECT_ROOT / "nas100_news_session.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📁 nas100_news_session.json")


if __name__ == "__main__":
    main()
