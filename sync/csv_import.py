"""
Импорт CSV файлов со свечами и новостями в БД.
Поддерживает различные форматы колонок (time/timestamp, DateTime_UTC, Impact/impact).
"""

import pandas as pd
import re
import logging
from pathlib import Path
from typing import Optional, Union, IO
from dataclasses import dataclass

from db.repository import CandleRepository, NewsRepository, ImportLogRepository, InstrumentRepository

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    total: int
    inserted: int
    skipped: int
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    error: Optional[str] = None


class CsvImporter:
    """Импорт CSV файлов со свечами и новостями в SQLite."""

    def __init__(self):
        self.candle_repo = CandleRepository()
        self.news_repo = NewsRepository()
        self.import_log = ImportLogRepository()
        self.instrument_repo = InstrumentRepository()

    def import_price_csv(self, file_or_path: Union[str, Path, IO],
                         instrument_id: int,
                         timeframe: str = '15m',
                         filename: str = None) -> ImportResult:
        """
        Импорт CSV с ценовыми данными.
        Поддерживает колонки: time/timestamp, open, high, low, close.
        """
        try:
            df = pd.read_csv(file_or_path)

            if filename is None and isinstance(file_or_path, (str, Path)):
                filename = Path(file_or_path).name

            # Нормализация колонок (как в app.py:161-162)
            if 'time' in df.columns:
                df = df.rename(columns={'time': 'timestamp'})

            required = ['timestamp', 'open', 'high', 'low', 'close']
            missing = [c for c in required if c not in df.columns]
            if missing:
                return ImportResult(
                    total=len(df), inserted=0, skipped=0,
                    error=f"Отсутствуют колонки: {missing}"
                )

            # Оставляем только нужные колонки
            df = df[required].copy()

            # Парсинг timestamps и конвертация в naive UTC
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC').dt.tz_localize(None)

            df = df.sort_values('timestamp')
            df = df.dropna(subset=['open', 'high', 'low', 'close'])

            date_from = df['timestamp'].min().strftime('%Y-%m-%d %H:%M')
            date_to = df['timestamp'].max().strftime('%Y-%m-%d %H:%M')

            inserted, skipped = self.candle_repo.bulk_insert(
                instrument_id, df, timeframe, source='csv'
            )

            self.import_log.log_import(
                instrument_id=instrument_id, source='csv',
                filename=filename, rows_imported=inserted,
                rows_skipped=skipped, date_from=date_from, date_to=date_to
            )

            logger.info(
                f"Импорт свечей: {filename} -> instrument_id={instrument_id}, "
                f"вставлено={inserted}, пропущено={skipped}"
            )

            return ImportResult(
                total=len(df), inserted=inserted, skipped=skipped,
                date_from=date_from, date_to=date_to
            )

        except Exception as e:
            logger.error(f"Ошибка импорта CSV: {e}")
            return ImportResult(total=0, inserted=0, skipped=0, error=str(e))

    def import_news_csv(self, file_or_path: Union[str, Path, IO],
                        filename: str = None) -> ImportResult:
        """
        Импорт CSV с новостями.
        Поддерживает колонки: timestamp/DateTime_UTC, impact/Impact, event, currency/Currency.
        """
        try:
            df = pd.read_csv(file_or_path)

            if filename is None and isinstance(file_or_path, (str, Path)):
                filename = Path(file_or_path).name

            # Нормализация колонок (как в app.py:233-236)
            rename_map = {}
            if 'DateTime_UTC' in df.columns:
                rename_map['DateTime_UTC'] = 'timestamp'
            if 'Impact' in df.columns:
                rename_map['Impact'] = 'impact'
            if 'Currency' in df.columns:
                rename_map['Currency'] = 'currency'
            if 'Event' in df.columns:
                rename_map['Event'] = 'event'
            if rename_map:
                df = df.rename(columns=rename_map)

            required = ['timestamp', 'impact']
            missing = [c for c in required if c not in df.columns]
            if missing:
                return ImportResult(
                    total=len(df), inserted=0, skipped=0,
                    error=f"Отсутствуют колонки: {missing}"
                )

            # Парсинг timestamps и конвертация в naive UTC
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC').dt.tz_localize(None)

            df = df.sort_values('timestamp')

            date_from = df['timestamp'].min().strftime('%Y-%m-%d %H:%M')
            date_to = df['timestamp'].max().strftime('%Y-%m-%d %H:%M')

            inserted, skipped = self.news_repo.bulk_insert(df, source='csv')

            self.import_log.log_import(
                instrument_id=None, source='csv',
                filename=filename, rows_imported=inserted,
                rows_skipped=skipped, date_from=date_from, date_to=date_to
            )

            logger.info(
                f"Импорт новостей: {filename}, "
                f"вставлено={inserted}, пропущено={skipped}"
            )

            return ImportResult(
                total=len(df), inserted=inserted, skipped=skipped,
                date_from=date_from, date_to=date_to
            )

        except Exception as e:
            logger.error(f"Ошибка импорта новостей: {e}")
            return ImportResult(total=0, inserted=0, skipped=0, error=str(e))

    def auto_detect_instrument(self, filename: str) -> Optional[str]:
        """
        Определяет символ инструмента по имени файла.
        Например: 'EURUSD_2023-2025.csv' -> 'EURUSD'
        """
        name = Path(filename).stem.upper()

        # Получаем все известные символы
        instruments = self.instrument_repo.get_all()
        symbols = [i['symbol'] for i in instruments]

        # Проверяем, начинается ли имя файла с известного символа
        for symbol in sorted(symbols, key=len, reverse=True):
            if name.startswith(symbol):
                return symbol

        # Пробуем извлечь первую часть до подчёркивания
        match = re.match(r'^([A-Z0-9]+?)(?:_|\d{4})', name)
        if match:
            candidate = match.group(1)
            if candidate in symbols:
                return candidate

        return None
