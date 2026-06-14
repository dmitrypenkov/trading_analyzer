#!/usr/bin/env python3
"""
Анализ результатов loss_sweep: поиск постоянно проигрывающих стратегий.
"""

import json
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent

INSTRUMENTS = [
    "EURUSD", "USDJPY", "USDCHF", "XAUUSD", "XAGUSD",
    "SP500", "NAS100", "GER40", "JP225", "ETHUSDT"
]


def load_results(instrument: str) -> dict:
    """Загружает JSON с результатами для инструмента."""
    file = PROJECT_ROOT / f"{instrument.lower()}_loss_sweep_14-20.json"
    if not file.exists():
        return {}

    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_all():
    """Анализирует все результаты и находит проигрывающие стратегии."""

    # Загружаем все результаты
    all_results = {}
    for instr in INSTRUMENTS:
        data = load_results(instr)
        if data:
            all_results[instr] = data.get("results", {})

    if not all_results:
        print("❌ Нет данных для анализа")
        return

    # Агрегируем по стратегиям (combo_key)
    strategies = defaultdict(lambda: {
        "total_r_by_instr": {},
        "count_positive": 0,
        "count_negative": 0,
        "sum_r": 0.0,
        "instruments_list": [],
    })

    for instr, combos in all_results.items():
        for combo_key, metrics in combos.items():
            total_r = metrics.get("total_r", 0)
            strategies[combo_key]["total_r_by_instr"][instr] = total_r
            strategies[combo_key]["sum_r"] += total_r
            strategies[combo_key]["instruments_list"].append(instr)

            if total_r < 0:
                strategies[combo_key]["count_negative"] += 1
            else:
                strategies[combo_key]["count_positive"] += 1

    # Сортируем по:
    # 1. Количество инструментов с убытком (DESC)
    # 2. Сумма R (ASC — самые убыточные)
    sorted_strategies = sorted(
        strategies.items(),
        key=lambda x: (-x[1]["count_negative"], x[1]["sum_r"])
    )

    print("\n" + "="*80)
    print("ПОСТОЯННО ПРОИГРЫВАЮЩИЕ СТРАТЕГИИ")
    print("="*80)

    # Выводим топ 10 стратегий, которые проигрывают на 8+ инструментах
    print("\n📉 Стратегии, проигрывающие на 8+ инструментах:\n")

    shown = 0
    for combo_key, data in sorted_strategies:
        if data["count_negative"] < 8:
            break

        shown += 1
        if shown > 20:
            break

        block_start, mode, rr = combo_key.rsplit("_", 2)

        print(f"#{shown}. {block_start} | {mode:7s} | RR={rr}")
        print(f"   Убыток на инструментах: {data['count_negative']}/10")
        print(f"   Сумма R: {data['sum_r']:.1f} (avg: {data['sum_r']/10:.1f})")
        print(f"   По инструментам:")

        # Выводим по инструментам, отсортированные
        instr_results = sorted(
            data["total_r_by_instr"].items(),
            key=lambda x: x[1]
        )
        for instr, r in instr_results:
            symbol = "📉" if r < 0 else "📈"
            print(f"      {symbol} {instr:8s}: {r:7.1f}R")

        print()

    # Выводим стратегии, проигрывающие на ВСЕ 10 инструментах
    print("\n" + "="*80)
    print("СТРАТЕГИИ, ПРОИГРЫВАЮЩИЕ НА ВСЕХ 10 ИНСТРУМЕНТАХ:")
    print("="*80 + "\n")

    losing_all = [s for s in sorted_strategies if s[1]["count_negative"] == 10]

    if losing_all:
        for combo_key, data in losing_all[:15]:
            block_start, mode, rr = combo_key.rsplit("_", 2)
            print(f"✗ {block_start} | {mode:7s} | RR={rr} → Сумма R: {data['sum_r']:.1f}")
    else:
        print("(Нет стратегий, проигрывающих на всех инструментах)\n")

    # Анализ по режимам
    print("\n" + "="*80)
    print("АНАЛИЗ ПО РЕЖИМАМ")
    print("="*80 + "\n")

    by_mode = defaultdict(list)
    for combo_key, data in sorted_strategies:
        mode = combo_key.split("_")[-2]
        by_mode[mode].append((combo_key, data))

    for mode in ["TREND", "REVERSE"]:
        if mode not in by_mode:
            continue

        strategies_list = by_mode[mode]
        avg_negative = sum(1 for _, d in strategies_list if d["count_negative"] >= 5) / len(strategies_list) * 100

        total_sum_r = sum(d["sum_r"] for _, d in strategies_list)

        print(f"{mode:7s}:")
        print(f"  - Стратегий, проигрывающих на 5+ инструментах: {sum(1 for _, d in strategies_list if d['count_negative'] >= 5)}/{len(strategies_list)}")
        print(f"  - Средняя сумма R (все стратегии): {total_sum_r / len(strategies_list):.1f}")
        print(f"  - Всего R по режиму: {total_sum_r:.1f}\n")

    # Top 5 самых убыточных комбинаций
    print("\n" + "="*80)
    print("ТОП 5 САМЫХ УБЫТОЧНЫХ СТРАТЕГИЙ (по сумме R)")
    print("="*80 + "\n")

    for i, (combo_key, data) in enumerate(sorted_strategies[:5], 1):
        block_start, mode, rr = combo_key.rsplit("_", 2)
        print(f"{i}. {block_start} | {mode:7s} | RR={rr}")
        print(f"   Сумма R: {data['sum_r']:.1f} (убыток на {data['count_negative']}/10 инструментах)")
        print()


if __name__ == "__main__":
    analyze_all()
