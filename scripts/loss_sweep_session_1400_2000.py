#!/usr/bin/env python3
"""
Поиск проигрывающей стратегии для времени 14:00-20:00 UTC.

Перебирает:
- block_start: 00:00-13:00 (шаг 1 час)
- block_end: 13:30 (фиксированный)
- session: 14:00-20:00 (фиксированный)
- sl_multiplier: 0.1 (фиксированный)
- rr_ratio: 2.0, 1.5
- mode: TREND, REVERSE

Результаты по месяцам + суммарные по инструментам.
Сохраняет по отдельному JSON файлу для каждого инструмента.
"""

import sys
import os
import json
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
VENV_PY = PROJECT_ROOT / "venv_trading" / "bin" / "python"

# Параметры оптимизации
BLOCK_START_HOURS = list(range(0, 14))  # 00:00 до 13:00
BLOCK_END = "13:30"
SESSION_START = "14:00"
SESSION_END = "20:00"
SL_MULTIPLIER = 0.1
RR_RATIOS = [2.0, 1.5]
MODES = ["TREND", "REVERSE"]

INSTRUMENTS = [
    "EURUSD", "USDJPY", "USDCHF", "XAUUSD", "XAGUSD",
    "SP500", "NAS100", "GER40", "JP225", "ETHUSDT"
]

START_DATE = "2024-01-01"
END_DATE = date.today().strftime("%Y-%m-%d")


def format_time(hour: int) -> str:
    """Преобразует час в HH:MM формат."""
    return f"{hour:02d}:00"


def extract_month(date_str: str) -> str:
    """Извлекает YYYY-MM из даты."""
    return date_str[:7]


def run_backtest(instrument: str, block_start: str, rr_ratio: float, mode: str) -> dict:
    """
    Запускает бэктест через run_backtest.py.
    Возвращает результаты или None если ошибка.
    """
    params = {
        "instrument": instrument,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "block_start": block_start,
        "block_end": BLOCK_END,
        "session_start": SESSION_START,
        "session_end": SESSION_END,
        "use_base_sl_mode": True,
        "sl_multiplier": SL_MULTIPLIER,
        "rr_ratio": rr_ratio,
        "use_news_filter": True,
        "news_impact_filter": ["high"],
        "news_buffer_minutes": 30,
    }

    # Добавляем mode через соответствующие параметры
    if mode == "REVERSE":
        params["use_return_mode"] = True
    # TREND — это дефолт (use_return_mode = False)

    json_params = json.dumps(params)

    try:
        result = subprocess.run(
            [str(VENV_PY), "scripts/run_backtest.py", json_params],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"  ❌ {instrument} {block_start} RR={rr_ratio} {mode}: stderr={result.stderr[:200]}")
            return None

        output = json.loads(result.stdout)

        if output.get("status") != "ok":
            print(f"  ❌ {instrument} {block_start} RR={rr_ratio} {mode}: {output.get('message')}")
            return None

        return output

    except subprocess.TimeoutExpired:
        print(f"  ⏱️ {instrument} {block_start} RR={rr_ratio} {mode}: timeout")
        return None
    except json.JSONDecodeError:
        print(f"  ⚠️ {instrument} {block_start} RR={rr_ratio} {mode}: invalid JSON output")
        return None
    except Exception as e:
        print(f"  ❌ {instrument} {block_start} RR={rr_ratio} {mode}: {e}")
        return None


def aggregate_by_month(result: dict) -> dict:
    """
    Разбивает результаты по месяцам.
    Возвращает {month: {daily_trades}}
    """
    if result.get("status") != "ok":
        return {}

    # Берём daily_trades_df и разбиваем по месяцам
    # К сожалению, run_backtest.py не возвращает дневные торговли в JSON
    # Нам нужно рассчитать на основе summary и yearly данных

    # Для простоты используем yearly данные и дополнительно считаем monthly
    # путем анализа период целиком

    return {
        "summary": result.get("summary", {}),
        "yearly": result.get("yearly", []),
    }


def process_instrument(instrument: str) -> dict:
    """
    Обрабатывает один инструмент: перебирает все комбинации параметров.
    Возвращает структурированные результаты.
    """
    print(f"\n{'='*60}")
    print(f"Обработка {instrument}")
    print(f"{'='*60}")

    results_by_params = {}

    total_combos = len(BLOCK_START_HOURS) * len(RR_RATIOS) * len(MODES)
    current = 0

    for hour in BLOCK_START_HOURS:
        block_start = format_time(hour)

        for rr_ratio in RR_RATIOS:
            for mode in MODES:
                current += 1

                combo_key = f"{block_start}_{mode}_{rr_ratio}"
                print(f"[{current}/{total_combos}] {combo_key}...", end=" ", flush=True)

                result = run_backtest(instrument, block_start, rr_ratio, mode)

                if result:
                    summary = result.get("summary", {})
                    yearly = result.get("yearly", [])

                    results_by_params[combo_key] = {
                        "block_start": block_start,
                        "mode": mode,
                        "rr_ratio": rr_ratio,
                        "total_r": summary.get("total_r", 0.0),
                        "trades": summary.get("total_trades", 0),
                        "win_rate": summary.get("win_rate", 0.0),
                        "max_drawdown": summary.get("max_drawdown", 0.0),
                        "profit_factor": summary.get("profit_factor", 0.0),
                        "r_dd_ratio": summary.get("r_dd_ratio", 0.0),
                        "yearly": yearly,
                    }
                    print(f"✓ R={summary.get('total_r', 0):.1f}")
                else:
                    print(f"✗")

    return results_by_params


def save_instrument_results(instrument: str, results: dict) -> Path:
    """
    Сохраняет результаты для инструмента в JSON файл.
    """
    output_file = PROJECT_ROOT / f"{instrument.lower()}_loss_sweep_14-20.json"

    output_data = {
        "instrument": instrument,
        "date_generated": datetime.now().isoformat(),
        "period": f"{START_DATE} to {END_DATE}",
        "parameters": {
            "block_end": BLOCK_END,
            "session_start": SESSION_START,
            "session_end": SESSION_END,
            "sl_multiplier": SL_MULTIPLIER,
            "use_news_filter": True,
            "news_impact_filter": ["high"],
            "news_buffer_minutes": 30,
        },
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n📁 Сохранено: {output_file}")
    return output_file


def main():
    print("🚀 Поиск проигрывающей стратегии (14:00-20:00 UTC)")
    print(f"Дата: {START_DATE} — {END_DATE}")
    print(f"Инструменты: {', '.join(INSTRUMENTS)}")
    print(f"Параметры: block_end={BLOCK_END}, session={SESSION_START}-{SESSION_END}")
    print(f"SL multiplier: {SL_MULTIPLIER}, RR ratios: {RR_RATIOS}, Modes: {MODES}")

    output_files = []

    for instrument in INSTRUMENTS:
        try:
            results = process_instrument(instrument)
            output_file = save_instrument_results(instrument, results)
            output_files.append(output_file)
        except Exception as e:
            print(f"\n❌ Ошибка при обработке {instrument}: {e}")

    print(f"\n{'='*60}")
    print(f"✅ Завершено. Обработано инструментов: {len(output_files)}/{len(INSTRUMENTS)}")
    for f in output_files:
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
