#!/usr/bin/env python3
"""
Поиск самой убыточной стратегии: блок до 03:00, сессия с 03:00 до 20:00, RR=1.
Реальный выход перед новостями (news_exit_mode=market). Инструменты: XAUUSD, USDJPY.

Перебор: block_start × sl_multiplier × mode (RR фиксирован = 1.0).
Сохраняет block03_rr1_market.json. Запуск: venv_trading/bin/python -m scripts.block03_rr1_sweep
(или из папки scripts: python block03_rr1_sweep.py)
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _xauusd_common import XauPipeline, metrics_from_df, window_dates

PROJECT_ROOT = Path(__file__).parent.parent

BLOCK_END = "03:00"
SESSION_START = "03:00"
SESSION_END = "20:00"
RR = 1.0
BLOCK_STARTS = ["20:00", "22:00", "23:00", "00:00", "01:00", "02:00"]
SL_MULTS = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
MODES = ["TREND", "REVERSE"]
INSTRUMENTS = ["XAUUSD", "USDJPY"]
MIN_TRADES = 40


def sweep_symbol(sym: str) -> dict:
    pipe = XauPipeline(symbol=sym, load_from="2023-06-01")
    end = str(pipe.data_last)
    s12, e12 = window_dates(pipe, 12)
    rows = []
    for bs in BLOCK_STARTS:
        for sl in SL_MULTS:
            for mode in MODES:
                st = pipe.build_settings(
                    block_start=bs, block_end=BLOCK_END,
                    session_start=SESSION_START, session_end=SESSION_END,
                    mode=mode, sl_multiplier=sl, rr_ratio=RR,
                    use_news_filter=True, news_exit_mode="market",
                )
                m12 = metrics_from_df(pipe.run(st, s12, end))
                m24 = metrics_from_df(pipe.run(st, "2024-01-01", end))
                rows.append({"block_start": bs, "sl_multiplier": sl, "mode": mode,
                             "m12": m12, "m24plus": m24})
    elig = [r for r in rows if r["m12"]["trades"] >= MIN_TRADES]
    elig.sort(key=lambda r: r["m12"]["total_r"])
    return {"symbol": sym, "window_12m": f"{s12} … {e12}", "data_last": end,
            "ranked_worst": elig, "all_results": rows}


def main():
    out = {
        "params": {"block_end": BLOCK_END, "session": f"{SESSION_START}-{SESSION_END}",
                   "rr_ratio": RR, "news_exit_mode": "market",
                   "block_starts": BLOCK_STARTS, "sl_mults": SL_MULTS, "modes": MODES},
        "instruments": {},
    }
    for sym in INSTRUMENTS:
        print(f"--- {sym} ---", flush=True)
        res = sweep_symbol(sym)
        out["instruments"][sym] = res
        w = res["ranked_worst"][0]
        print(f"🎯 WORST {sym}: block {w['block_start']}-{BLOCK_END} / sess {SESSION_START}-{SESSION_END} "
              f"/ RR1 / sl{w['sl_multiplier']} / {w['mode']} = "
              f"{w['m12']['total_r']:.1f}R/12м, {w['m24plus']['total_r']:.1f}R/2024+", flush=True)

    out_file = PROJECT_ROOT / "block03_rr1_market.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📁 {out_file}")


if __name__ == "__main__":
    main()
