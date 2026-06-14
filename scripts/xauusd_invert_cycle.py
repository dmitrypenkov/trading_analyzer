#!/usr/bin/env python3
"""
Инверсия самой убыточной XAUUSD-стратегии + анализ циклов (когда она перестаёт работать).

Берёт WORST-конфиг из xauusd_loss_finder.json (ranked_worst[0]) и прогоняет:
  BASE   — исходный убыточный конфиг как есть
  INV-A  — use_return_mode переключён (TREND<->REVERSE)
  INV-B  — invert_signals=True (истинное зеркало: разворот направления каждой сделки)

Затем по BASE строит циклы за 2024-01-01..present:
  - по дню недели
  - по календарному месяцу (сезонность)
  - таймлайн по YYYY-MM (когда теряет / зарабатывает) + сравнение с INV-B
  - срез последних 30 дней

Отчёт: stdout + exports/xauusd_invert_cycle_report.txt + xauusd_invert_cycle.json
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from _xauusd_common import XauPipeline, metrics_from_df

PROJECT_ROOT = Path(__file__).parent.parent
WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
RU_MONTH = ["", "янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек"]


def load_worst(symbol):
    loss_json = PROJECT_ROOT / f"{symbol.lower()}_loss_finder.json"
    if not loss_json.exists():
        raise RuntimeError(f"Нет {loss_json} — сначала запусти xauusd_loss_finder.py {symbol}")
    data = json.loads(loss_json.read_text(encoding="utf-8"))
    return data["ranked_worst"][0], data


def fmt_metrics(tag, m):
    return (f"{tag:<8} R={m['total_r']:>8.2f}  тр={m['trades']:>3}  "
            f"WR={m['win_rate']:>5.1f}%  DD={m['max_drawdown']:>7.2f}  PF={m['profit_factor']:>4.2f}  "
            f"(TP={m['tp']} SL={m['sl']} BE={m['be']})")


def monthly_table(df, label):
    """Возвращает DataFrame по YYYY-MM с R и числом сделок (executed)."""
    ex = df[df["result"].isin(["TP", "SL", "BE"])].copy()
    if ex.empty:
        return pd.DataFrame(columns=["month", f"R_{label}", f"n_{label}"])
    ex["month"] = ex["date"].str[:7]
    g = ex.groupby("month").agg(R=("r_result", "sum"), n=("r_result", "size")).reset_index()
    g["R"] = g["R"].round(2)
    return g.rename(columns={"R": f"R_{label}", "n": f"n_{label}"})


def main(symbol="XAUUSD"):
    worst, meta = load_worst(symbol)
    lines = []

    def out(s=""):
        print(s)
        lines.append(s)

    out("=" * 90)
    out("XAUUSD — ИНВЕРСИЯ САМОЙ УБЫТОЧНОЙ СТРАТЕГИИ + АНАЛИЗ ЦИКЛОВ")
    out("=" * 90)
    out(f"WORST-конфиг (из loss-finder, окно {meta['search_window']}):")
    out(f"  {worst['key']}")
    out(f"  block {worst['block_start']}-{worst['block_end']} | "
        f"session {worst['session_start']}-{worst['session_end']} | "
        f"RR={worst['rr_ratio']} | sl_mult={worst['sl_multiplier']} | mode={worst['mode']}")
    out("")

    pipe = XauPipeline(symbol=symbol, load_from="2023-12-01")
    end = str(pipe.data_last)
    win_start = meta["search_window"].split(" … ")[0]
    cycle_start = "2024-01-01"
    cutoff_30d = (pipe.data_last - timedelta(days=30)).strftime("%Y-%m-%d")

    base_kwargs = dict(
        block_start=worst["block_start"], block_end=worst["block_end"],
        session_start=worst["session_start"], session_end=worst["session_end"],
        mode=worst["mode"], sl_multiplier=worst["sl_multiplier"], rr_ratio=worst["rr_ratio"],
    )
    inv_mode = "TREND" if worst["mode"] == "REVERSE" else "REVERSE"

    # ---- Прогон трёх вариантов на 12-мес окне и на 2024+ ----
    out("-" * 90)
    out(f"СРАВНЕНИЕ ИНВЕРСИЙ  (окно поиска {win_start} … {end})")
    out("-" * 90)
    base_12 = pipe.run(pipe.build_settings(**base_kwargs), win_start, end)
    inva_12 = pipe.run(pipe.build_settings(**{**base_kwargs, "mode": inv_mode}), win_start, end)
    invb_12 = pipe.run(pipe.build_settings(**base_kwargs, invert_signals=True), win_start, end)
    out(fmt_metrics("BASE", metrics_from_df(base_12)))
    out(fmt_metrics(f"INV-A", metrics_from_df(inva_12)) + f"   [use_return_mode -> {inv_mode}]")
    out(fmt_metrics("INV-B", metrics_from_df(invb_12)) + "   [истинное зеркало]")
    out("")

    out("-" * 90)
    out(f"СРАВНЕНИЕ ИНВЕРСИЙ  (длинная история {cycle_start} … {end})")
    out("-" * 90)
    base_df = pipe.run(pipe.build_settings(**base_kwargs), cycle_start, end)
    inva_df = pipe.run(pipe.build_settings(**{**base_kwargs, "mode": inv_mode}), cycle_start, end)
    invb_df = pipe.run(pipe.build_settings(**base_kwargs, invert_signals=True), cycle_start, end)
    m_base, m_inva, m_invb = metrics_from_df(base_df), metrics_from_df(inva_df), metrics_from_df(invb_df)
    out(fmt_metrics("BASE", m_base))
    out(fmt_metrics("INV-A", m_inva) + f"   [use_return_mode -> {inv_mode}]")
    out(fmt_metrics("INV-B", m_invb) + "   [истинное зеркало]")
    # Расхождение INV-A vs INV-B
    diff = round(m_inva["total_r"] - m_invb["total_r"], 2)
    out(f"\nРасхождение INV-A vs INV-B: {diff:+.2f} R "
        f"(>0 => use_return_mode лучше зеркала; причина — дни со стартом ABOVE/BELOW)")
    out("")

    # ---- Циклы по BASE (длинная история) ----
    ex = base_df[base_df["result"].isin(["TP", "SL", "BE"])].copy()
    ex["d"] = pd.to_datetime(ex["date"])
    ex["dow"] = ex["d"].dt.dayofweek
    ex["mon"] = ex["d"].dt.month
    ex["ym"] = ex["date"].str[:7]

    out("-" * 90)
    out("ЦИКЛ 1 — ПО ДНЮ НЕДЕЛИ (BASE, убыточная стратегия)")
    out("-" * 90)
    out(f"{'день':<5} {'сделок':>7} {'R':>9} {'R/сделку':>10} {'WR%':>7}")
    for dow in range(5):
        sub = ex[ex["dow"] == dow]
        if len(sub) == 0:
            continue
        r = sub["r_result"].sum()
        wr = (sub["result"] == "TP").mean() * 100
        out(f"{WD[dow]:<5} {len(sub):>7} {r:>9.2f} {r/len(sub):>10.3f} {wr:>7.1f}")
    out("")

    out("-" * 90)
    out("ЦИКЛ 2 — СЕЗОННОСТЬ ПО КАЛЕНДАРНОМУ МЕСЯЦУ (BASE)")
    out("-" * 90)
    out(f"{'мес':<5} {'сделок':>7} {'R':>9} {'R/сделку':>10} {'WR%':>7}")
    for mon in range(1, 13):
        sub = ex[ex["mon"] == mon]
        if len(sub) == 0:
            continue
        r = sub["r_result"].sum()
        wr = (sub["result"] == "TP").mean() * 100
        out(f"{RU_MONTH[mon]:<5} {len(sub):>7} {r:>9.2f} {r/len(sub):>10.3f} {wr:>7.1f}")
    out("")

    out("-" * 90)
    out("ЦИКЛ 3 — ТАЙМЛАЙН ПО МЕСЯЦАМ: BASE vs INV-B (зеркало)  [когда стратегия теряет/зарабатывает]")
    out("-" * 90)
    mb = monthly_table(base_df, "base")
    mi = monthly_table(invb_df, "inv")
    merged = mb.merge(mi, on="month", how="outer").fillna(0).sort_values("month")
    cum_b = cum_i = 0.0
    out(f"{'месяц':<8} {'R_base':>8} {'R_зеркало':>10} {'cum_base':>9} {'cum_зерк':>9}  знак")
    for _, row in merged.iterrows():
        rb, ri = row.get("R_base", 0.0), row.get("R_inv", 0.0)
        cum_b += rb
        cum_i += ri
        mark = "BASE+" if rb > 0 else ""   # месяцы где убыточная стратегия В ПЛЮСЕ => инверсия теряет
        out(f"{row['month']:<8} {rb:>8.2f} {ri:>10.2f} {cum_b:>9.2f} {cum_i:>9.2f}  {mark}")
    months_base_pos = int((merged.get("R_base", pd.Series(dtype=float)) > 0).sum())
    out(f"\nМесяцев где BASE в плюсе (инверсия там проигрывает): {months_base_pos} из {len(merged)}")
    out("")

    # ---- Последние 30 дней ----
    out("-" * 90)
    out(f"СРЕЗ ПОСЛЕДНИХ 30 ДНЕЙ  ({cutoff_30d} … {end})")
    out("-" * 90)
    out(fmt_metrics("BASE", metrics_from_df(base_df, date_from=cutoff_30d)))
    out(fmt_metrics("INV-A", metrics_from_df(inva_df, date_from=cutoff_30d)))
    out(fmt_metrics("INV-B", metrics_from_df(invb_df, date_from=cutoff_30d)))
    recent = ex[ex["date"] >= cutoff_30d].sort_values("date")
    out(f"\nСделки за 30 дней ({len(recent)} шт):")
    out(f"{'дата':<12} {'день':<4} {'тип входа':<22} {'рез':<4} {'R':>7}")
    for _, r in recent.iterrows():
        out(f"{r['date']:<12} {WD[int(r['dow'])]:<4} {r['entry_type']:<22} {r['result']:<4} {r['r_result']:>7.2f}")
    out("")

    # ---- Вывод ----
    out("=" * 90)
    out("ИТОГ")
    out("=" * 90)
    inv_best = "INV-A" if m_inva["total_r"] >= m_invb["total_r"] else "INV-B"
    inv_best_r = max(m_inva["total_r"], m_invb["total_r"])
    out(f"BASE (убыточная): {m_base['total_r']:+.2f} R за {cycle_start}..{end}")
    out(f"Лучшая инверсия {inv_best}: {inv_best_r:+.2f} R")
    out(f"Стабильность убытка: BASE в плюсе только {months_base_pos}/{len(merged)} месяцев "
        f"=> {'инверсия надёжна' if months_base_pos <= len(merged)*0.35 else 'инверсия УСЛОВНА (есть периоды где BASE сам в плюсе)'}")
    out("ВНИМАНИЕ: конфиг частично подобран под историю; нужна форвард-проверка.")

    # Сохранение
    exports = PROJECT_ROOT / "exports"
    exports.mkdir(exist_ok=True)
    sl = symbol.lower()
    (exports / f"{sl}_invert_cycle_report.txt").write_text("\n".join(lines), encoding="utf-8")
    result = {
        "worst": worst,
        "cycle_period": f"{cycle_start} … {end}",
        "inversion_12m": {
            "BASE": metrics_from_df(base_12),
            "INV_A": metrics_from_df(inva_12),
            "INV_B": metrics_from_df(invb_12),
        },
        "inversion_full": {"BASE": m_base, "INV_A": m_inva, "INV_B": m_invb},
        "inv_a_vs_b_diff": diff,
        "months_base_positive": months_base_pos,
        "months_total": int(len(merged)),
        "timeline": merged.to_dict("records"),
    }
    (PROJECT_ROOT / f"{sl}_invert_cycle.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    out(f"\n📁 exports/{sl}_invert_cycle_report.txt + {sl}_invert_cycle.json")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="XAUUSD", help="Тикер (по умолчанию XAUUSD)")
    main(ap.parse_args().symbol.upper())
