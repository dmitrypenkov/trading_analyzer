#!/usr/bin/env python3
"""
Анализ проигрывающих стратегий по месяцам для каждого инструмента.
Берет лучшую проигрывающую стратегию каждого инструмента и показывает результаты по месяцам.
"""

import json
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path
from dateutil.relativedelta import relativedelta
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
VENV_PY = PROJECT_ROOT / "venv_trading" / "bin" / "python"

# Определяем лучшие проигрывающие стратегии для каждого инструмента
LOSING_STRATEGIES = {
    "EURUSD": {"block_start": "13:00", "mode": "TREND", "rr_ratio": 2.0},
    "USDJPY": {"block_start": "09:00", "mode": "REVERSE", "rr_ratio": 2.0},
    "USDCHF": {"block_start": "13:00", "mode": "REVERSE", "rr_ratio": 1.5},
    "XAUUSD": {"block_start": "13:00", "mode": "REVERSE", "rr_ratio": 1.5},
    "XAGUSD": {"block_start": "03:00", "mode": "REVERSE", "rr_ratio": 1.5},
    "SP500": {"block_start": "04:00", "mode": "REVERSE", "rr_ratio": 2.0},
    "NAS100": {"block_start": "12:00", "mode": "REVERSE", "rr_ratio": 1.5},
    "GER40": {"block_start": "12:00", "mode": "REVERSE", "rr_ratio": 1.5},
    "JP225": {"block_start": "00:00", "mode": "TREND", "rr_ratio": 1.5},
    "ETHUSDT": {"block_start": "13:00", "mode": "REVERSE", "rr_ratio": 1.5},
}


def run_backtest_month(instrument: str, strategy: dict, start_date: str, end_date: str) -> dict:
    """Запускает бэктест для месяца."""
    params = {
        "instrument": instrument,
        "start_date": start_date,
        "end_date": end_date,
        "block_start": strategy["block_start"],
        "block_end": "13:30",
        "session_start": "14:00",
        "session_end": "20:00",
        "use_base_sl_mode": True,
        "sl_multiplier": 0.1,
        "rr_ratio": strategy["rr_ratio"],
        "use_news_filter": True,
        "news_impact_filter": ["high"],
        "news_buffer_minutes": 30,
    }

    if strategy["mode"] == "REVERSE":
        params["use_return_mode"] = True

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
            return None

        output = json.loads(result.stdout)
        if output.get("status") != "ok":
            return None

        return output

    except Exception as e:
        print(f"    ❌ Ошибка: {e}")
        return None


def generate_monthly_report(instrument: str, strategy: dict) -> str:
    """Генерирует отчет по месяцам для инструмента."""
    lines = []

    # Заголовок
    lines.append(f"\n{'='*90}")
    lines.append(f"{instrument.upper()}")
    lines.append(f"{'='*90}")
    lines.append(f"Стратегия: {strategy['block_start']} блок, {strategy['mode']}, RR={strategy['rr_ratio']}")
    lines.append(f"{'='*90}\n")

    # Таблица с месячными результатами
    lines.append(f"{'Месяц':<12} {'Сделок':<10} {'R':<10} {'Win%':<10} {'DD':<10} {'PF':<8}")
    lines.append("-" * 90)

    # Генерируем месячные отчеты
    start = datetime(2024, 1, 1)
    end_date = date.today()

    monthly_results = []
    total_r = 0
    total_trades = 0

    current = start
    while current.date() <= end_date:
        month_start = current.strftime("%Y-%m-%d")
        month_end = (current + relativedelta(months=1) - timedelta(days=1)).strftime("%Y-%m-%d")

        # Ограничиваем по сегодняшней дате
        if datetime.strptime(month_end, "%Y-%m-%d").date() > end_date:
            month_end = end_date.strftime("%Y-%m-%d")

        month_key = current.strftime("%Y-%m")

        print(f"  {instrument} {month_key}...", end=" ", flush=True)

        result = run_backtest_month(instrument, strategy, month_start, month_end)

        if result:
            summary = result.get("summary", {})
            r = summary.get("total_r", 0)
            trades = summary.get("total_trades", 0)
            win_rate = summary.get("win_rate", 0)
            dd = summary.get("max_drawdown", 0)
            pf = summary.get("profit_factor", 0)

            monthly_results.append((month_key, trades, r, win_rate, dd, pf))
            total_r += r
            total_trades += trades

            # Форматируем строку
            r_str = f"{r:+.1f}R" if r != 0 else "0.0R"
            dd_str = f"{dd:.1f}R"
            pf_str = f"{pf:.2f}"

            lines.append(f"{month_key:<12} {trades:<10} {r_str:<10} {win_rate:>8.1f}% {dd_str:<10} {pf_str:<8}")
            print("✓")
        else:
            print("✗")

        current += relativedelta(months=1)

    # Итоговая строка
    lines.append("-" * 90)
    avg_r_per_month = total_r / len(monthly_results) if monthly_results else 0
    lines.append(f"{'ИТОГО':<12} {total_trades:<10} {total_r:+.1f}R")
    lines.append(f"{'Среднее/мес':<12} {total_trades/len(monthly_results):>8.0f} {avg_r_per_month:+.1f}R")

    return "\n".join(lines)


def main():
    print("\n🔍 Анализ проигрывающих стратегий по месяцам\n")

    all_reports = []

    for instrument in sorted(LOSING_STRATEGIES.keys()):
        strategy = LOSING_STRATEGIES[instrument]
        print(f"\n{instrument}:")

        report = generate_monthly_report(instrument, strategy)
        all_reports.append(report)

    # Сохраняем в файл
    output_file = PROJECT_ROOT / "exports" / "losing_strategies_monthly.txt"

    full_report = "\n".join(all_reports)
    full_report = "=" * 90 + "\n" + \
                  "ПРОИГРЫВАЮЩИЕ СТРАТЕГИИ ПО МЕСЯЦАМ\n" + \
                  "Период: 2024-01-01 — 2026-04-14 (сегодня)\n" + \
                  "=" * 90 + \
                  full_report

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(full_report)

    print(f"\n✅ Сохранено: {output_file}")


if __name__ == "__main__":
    main()
