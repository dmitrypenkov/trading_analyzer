"""
Синхронизация данных с Yahoo Finance.
Подтягивает 15-минутные свечи за последние 60 дней.
"""

import pandas as pd
import time
import logging
from dataclasses import dataclass
from typing import Optional, List

from db.repository import CandleRepository, InstrumentRepository, ImportLogRepository

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    symbol: str
    yahoo_ticker: str
    fetched: int
    inserted: int
    skipped: int
    error: Optional[str] = None


class YahooFinanceSyncer:
    """Синхронизация OHLC данных с Yahoo Finance через yfinance."""

    def __init__(self):
        self.candle_repo = CandleRepository()
        self.instrument_repo = InstrumentRepository()
        self.import_log = ImportLogRepository()

    def sync_instrument(self, instrument_id: int,
                        timeframe: str = '15m') -> SyncResult:
        """
        Синхронизация одного инструмента.
        Загружает 15-мин данные за последние 60 дней из Yahoo Finance.
        """
        instrument = self.instrument_repo.get_by_id(instrument_id)
        if not instrument:
            return SyncResult("?", "?", 0, 0, 0, error="Инструмент не найден")

        symbol = instrument['symbol']
        yahoo_ticker = instrument.get('yahoo_ticker')

        if not yahoo_ticker:
            return SyncResult(symbol, "", 0, 0, 0,
                              error="Yahoo тикер не настроен")

        try:
            import yfinance as yf
        except ImportError:
            return SyncResult(symbol, yahoo_ticker, 0, 0, 0,
                              error="yfinance не установлен. pip install yfinance")

        try:
            logger.info(f"Синхронизация {symbol} ({yahoo_ticker})...")

            # Загрузка данных из Yahoo Finance
            # period='60d' — максимум для 15m интервала
            ticker = yf.Ticker(yahoo_ticker)
            yf_df = ticker.history(period='60d', interval=timeframe)

            if yf_df.empty:
                return SyncResult(symbol, yahoo_ticker, 0, 0, 0,
                                  error="Yahoo Finance вернул пустые данные")

            # Преобразование формата Yahoo Finance -> наш формат
            df = pd.DataFrame()
            df['timestamp'] = yf_df.index

            # Удаляем timezone info (конвертация в naive UTC)
            if df['timestamp'].dt.tz is not None:
                df['timestamp'] = df['timestamp'].dt.tz_localize(None)

            df['open'] = yf_df['Open'].values
            df['high'] = yf_df['High'].values
            df['low'] = yf_df['Low'].values
            df['close'] = yf_df['Close'].values

            # Убираем NaN строки
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            df = df.sort_values('timestamp').reset_index(drop=True)

            fetched = len(df)

            if fetched == 0:
                return SyncResult(symbol, yahoo_ticker, 0, 0, 0,
                                  error="Нет валидных данных после фильтрации")

            # Вставка в БД с дедупликацией
            inserted, skipped = self.candle_repo.bulk_insert(
                instrument_id, df, timeframe, source='yahoo'
            )

            # Лог импорта
            date_from = df['timestamp'].min().strftime('%Y-%m-%d %H:%M')
            date_to = df['timestamp'].max().strftime('%Y-%m-%d %H:%M')

            self.import_log.log_import(
                instrument_id=instrument_id, source='yahoo',
                filename=yahoo_ticker, rows_imported=inserted,
                rows_skipped=skipped, date_from=date_from, date_to=date_to
            )

            logger.info(
                f"Синхронизация {symbol}: загружено {fetched}, "
                f"вставлено {inserted}, пропущено {skipped}"
            )

            return SyncResult(symbol, yahoo_ticker, fetched, inserted, skipped)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка синхронизации {symbol}: {error_msg}")
            return SyncResult(symbol, yahoo_ticker, 0, 0, 0, error=error_msg)

    def sync_all_active(self, timeframe: str = '15m',
                        delay: float = 1.5) -> List[SyncResult]:
        """
        Синхронизация всех активных инструментов с Yahoo тикерами.
        delay — задержка между запросами для rate limiting.
        """
        instruments = self.instrument_repo.get_active()
        results = []

        for i, instr in enumerate(instruments):
            if not instr.get('yahoo_ticker'):
                continue

            result = self.sync_instrument(instr['id'], timeframe)
            results.append(result)

            # Rate limiting — пауза между запросами
            if i < len(instruments) - 1 and delay > 0:
                time.sleep(delay)

        return results
