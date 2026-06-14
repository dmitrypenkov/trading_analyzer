#!/usr/bin/env python3
"""
Разбивка WORST-конфига XAUUSD по стороне: ALL / только LONG / только SHORT.
Для BASE (убыточная REVERSE) и для инверсии (TREND).

В session/block-системе максимум одна сделка в день, сделки независимы =>
фильтр по направлению эквивалентен "торговать только long" / "только short".
"""

import json
from pathlib import Path

from _xauusd_common import XauPipeline, metrics_from_df

PROJECT_ROOT = Path(__file__).parent.parent


def row(tag, m):
    return (f"  {tag:<14} R={m['total_r']:>8.2f}  тр={m['trades']:>3}  "
            f"WR={m['win_rate']:>5.1f}%  DD={m['max_drawdown']:>7.2f}  PF={m['profit_factor']:>4.2f}  "
            f"(TP={m['tp']} SL={m['sl']} BE={m['be']})")


def block(title, df, date_from=None):
    print(title)
    print(row("ALL",   metrics_from_df(df, date_from=date_from)))
    print(row("LONG-only",  metrics_from_df(df, date_from=date_from, direction="LONG")))
    print(row("SHORT-only", metrics_from_df(df, date_from=date_from, direction="SHORT")))
    print()


def main(symbol="XAUUSD"):
    loss_json = PROJECT_ROOT / f"{symbol.lower()}_loss_finder.json"
    data = json.loads(loss_json.read_text(encoding="utf-8"))
    worst = data["ranked_worst"][0]
    print("=" * 78)
    print("XAUUSD — РАЗБИВКА ПО СТОРОНЕ (only LONG / only SHORT)")
    print("=" * 78)
    print(f"WORST: {worst['key']}")
    print(f"  block {worst['block_start']}-{worst['block_end']} | session {worst['session_start']}-{worst['session_end']}"
          f" | RR={worst['rr_ratio']} | sl={worst['sl_multiplier']} | mode={worst['mode']}\n")

    pipe = XauPipeline(symbol=symbol, load_from="2023-12-01")
    end = str(pipe.data_last)
    win_start = data["search_window"].split(" … ")[0]
    cycle_start = "2024-01-01"
    cutoff_30d = (pipe.data_last - __import__("datetime").timedelta(days=30)).strftime("%Y-%m-%d")

    base_kwargs = dict(
        block_start=worst["block_start"], block_end=worst["block_end"],
        session_start=worst["session_start"], session_end=worst["session_end"],
        mode=worst["mode"], sl_multiplier=worst["sl_multiplier"], rr_ratio=worst["rr_ratio"],
    )
    inv_mode = "TREND" if worst["mode"] == "REVERSE" else "REVERSE"

    base_df = pipe.run(pipe.build_settings(**base_kwargs), cycle_start, end)
    inv_df = pipe.run(pipe.build_settings(**{**base_kwargs, "mode": inv_mode}), cycle_start, end)

    print("-" * 78)
    print(f"BASE = {worst['mode']} (убыточная)")
    print("-" * 78)
    block(f"[2024+]  {cycle_start} … {end}", base_df)
    block(f"[12 мес] {win_start} … {end}", base_df, date_from=win_start)
    block(f"[30 дней] {cutoff_30d} … {end}", base_df, date_from=cutoff_30d)

    print("-" * 78)
    print(f"ИНВЕРСИЯ = {inv_mode}")
    print("-" * 78)
    block(f"[2024+]  {cycle_start} … {end}", inv_df)
    block(f"[12 мес] {win_start} … {end}", inv_df, date_from=win_start)
    block(f"[30 дней] {cutoff_30d} … {end}", inv_df, date_from=cutoff_30d)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="XAUUSD", help="Тикер (по умолчанию XAUUSD)")
    main(ap.parse_args().symbol.upper())
