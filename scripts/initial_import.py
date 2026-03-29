#!/usr/bin/env python3
"""
Скрипт начального импорта всех CSV из m15/ в SQLite БД.
Запуск: python scripts/initial_import.py [--csv-dir m15]
"""

import sys
import os
import argparse
from pathlib import Path

# Добавляем корень проекта в sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import init_db
from db.repository import InstrumentRepository
from sync.csv_import import CsvImporter


def main():
    parser = argparse.ArgumentParser(description="Импорт CSV в БД Trading Analyzer")
    parser.add_argument('--csv-dir', default='m15', help="Директория с CSV файлами (по умолчанию: m15)")
    parser.add_argument('--timeframe', default='15m', help="Таймфрейм данных (по умолчанию: 15m)")
    args = parser.parse_args()

    csv_dir = PROJECT_ROOT / args.csv_dir
    if not csv_dir.exists():
        print(f"Директория не найдена: {csv_dir}")
        sys.exit(1)

    print("=" * 60)
    print("Trading Analyzer — Начальный импорт CSV в БД")
    print("=" * 60)

    # 1. Инициализация БД
    print("\n[1/3] Инициализация базы данных...")
    init_db()
    print("  БД готова.")

    # 2. Импорт ценовых CSV
    print(f"\n[2/3] Импорт ценовых данных из {csv_dir}/...")
    importer = CsvImporter()
    instrument_repo = InstrumentRepository()

    csv_files = sorted(csv_dir.glob("*.csv"))
    news_files = []
    price_files = []

    for f in csv_files:
        if f.name.startswith('_') or f.name.lower().startswith('news'):
            news_files.append(f)
        elif f.name.endswith('.json'):
            continue
        else:
            price_files.append(f)

    total_inserted = 0
    total_skipped = 0

    for csv_path in price_files:
        symbol = importer.auto_detect_instrument(csv_path.name)
        if not symbol:
            print(f"  ПРОПУЩЕН: {csv_path.name} — не удалось определить инструмент")
            continue

        instrument = instrument_repo.get_by_symbol(symbol)
        if not instrument:
            print(f"  ПРОПУЩЕН: {csv_path.name} — инструмент '{symbol}' не найден в БД")
            continue

        result = importer.import_price_csv(
            str(csv_path), instrument['id'], args.timeframe, csv_path.name
        )

        if result.error:
            print(f"  ОШИБКА: {csv_path.name} — {result.error}")
        else:
            print(f"  {csv_path.name} -> {symbol}: "
                  f"вставлено {result.inserted:,}, пропущено {result.skipped:,} "
                  f"({result.date_from} — {result.date_to})")
            total_inserted += result.inserted
            total_skipped += result.skipped

    # 3. Импорт новостей
    print(f"\n[3/3] Импорт новостей...")
    for news_path in news_files:
        result = importer.import_news_csv(str(news_path), news_path.name)
        if result.error:
            print(f"  ОШИБКА: {news_path.name} — {result.error}")
        else:
            print(f"  {news_path.name}: "
                  f"вставлено {result.inserted:,}, пропущено {result.skipped:,} "
                  f"({result.date_from} — {result.date_to})")
            total_inserted += result.inserted
            total_skipped += result.skipped

    # Итоги
    print("\n" + "=" * 60)
    print(f"Готово! Всего вставлено: {total_inserted:,}, пропущено дубликатов: {total_skipped:,}")

    # Показать состояние БД
    print("\nСостояние базы данных:")
    from db.repository import CandleRepository, NewsRepository
    candle_repo = CandleRepository()
    news_repo = NewsRepository()

    for instr in instrument_repo.get_all():
        count = candle_repo.get_count(instr['id'], args.timeframe)
        if count > 0:
            date_range = candle_repo.get_date_range(instr['id'], args.timeframe)
            print(f"  {instr['symbol']:10s}: {count:>8,} свечей ({date_range[0][:10]} — {date_range[1][:10]})")

    news_count = news_repo.get_count()
    if news_count > 0:
        news_range = news_repo.get_date_range()
        print(f"  {'НОВОСТИ':10s}: {news_count:>8,} событий ({news_range[0][:10]} — {news_range[1][:10]})")

    print("=" * 60)


if __name__ == '__main__':
    main()
