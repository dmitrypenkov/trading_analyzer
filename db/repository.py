"""
Репозитории для доступа к данным в SQLite.
Возвращают pandas DataFrame в формате, совместимом с DataProcessor.
"""

import pandas as pd
import logging
from datetime import date, datetime
from typing import Optional, List, Tuple

from db.connection import get_connection

logger = logging.getLogger(__name__)


class InstrumentRepository:
    """Управление реестром торговых инструментов."""

    def get_all(self) -> List[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM instruments ORDER BY symbol"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_active(self) -> List[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM instruments WHERE is_active = 1 ORDER BY symbol"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_by_symbol(self, symbol: str) -> Optional[dict]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM instruments WHERE symbol = ?", (symbol,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_by_id(self, instrument_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM instruments WHERE id = ?", (instrument_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create(self, symbol: str, yahoo_ticker: str = None,
               asset_class: str = None, precision: int = 5) -> int:
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO instruments (symbol, yahoo_ticker, asset_class, price_precision)
                   VALUES (?, ?, ?, ?)""",
                (symbol, yahoo_ticker, asset_class, precision)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update(self, instrument_id: int, **kwargs):
        allowed = {"symbol", "yahoo_ticker", "asset_class", "price_precision", "is_active"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [instrument_id]
        conn = get_connection()
        try:
            conn.execute(f"UPDATE instruments SET {set_clause} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def delete(self, instrument_id: int):
        conn = get_connection()
        try:
            conn.execute("DELETE FROM candles WHERE instrument_id = ?", (instrument_id,))
            conn.execute("DELETE FROM instruments WHERE id = ?", (instrument_id,))
            conn.commit()
        finally:
            conn.close()


class CandleRepository:
    """
    Доступ к OHLC свечам.
    get_dataframe() возвращает DataFrame совместимый с DataProcessor.__init__:
    колонки [timestamp, open, high, low, close].
    """

    def get_dataframe(self, instrument_id: int, timeframe: str = '15m',
                      start_date: Optional[date] = None,
                      end_date: Optional[date] = None) -> pd.DataFrame:
        """
        Загружает свечи из БД и возвращает DataFrame.
        Формат полностью совместим с тем, что DataProcessor ожидает.
        """
        query = """
            SELECT timestamp, open, high, low, close
            FROM candles
            WHERE instrument_id = ? AND timeframe = ?
        """
        params: list = [instrument_id, timeframe]

        if start_date:
            query += " AND timestamp >= ?"
            params.append(str(start_date))
        if end_date:
            # end_date включительно — берём до конца дня
            query += " AND timestamp < ?"
            end_dt = datetime.combine(end_date, datetime.max.time())
            params.append(end_dt.strftime('%Y-%m-%d %H:%M:%S'))

        query += " ORDER BY timestamp"

        conn = get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()

        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df

    def get_date_range(self, instrument_id: int,
                       timeframe: str = '15m') -> Optional[Tuple[str, str]]:
        conn = get_connection()
        try:
            row = conn.execute(
                """SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts
                   FROM candles WHERE instrument_id = ? AND timeframe = ?""",
                (instrument_id, timeframe)
            ).fetchone()
            if row and row['min_ts']:
                return (row['min_ts'], row['max_ts'])
            return None
        finally:
            conn.close()

    def get_count(self, instrument_id: int, timeframe: str = '15m') -> int:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM candles WHERE instrument_id = ? AND timeframe = ?",
                (instrument_id, timeframe)
            ).fetchone()
            return row['cnt']
        finally:
            conn.close()

    def bulk_insert(self, instrument_id: int, df: pd.DataFrame,
                    timeframe: str = '15m', source: str = 'csv') -> Tuple[int, int]:
        """
        Вставляет свечи из DataFrame в БД.
        Использует INSERT OR IGNORE для дедупликации по (instrument_id, timestamp, timeframe).
        Возвращает (inserted, skipped).
        """
        if df.empty:
            return (0, 0)

        conn = get_connection()
        try:
            total = len(df)
            count_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM candles WHERE instrument_id = ? AND timeframe = ?",
                (instrument_id, timeframe)
            ).fetchone()['cnt']

            # Подготовка данных для batch insert
            records = []
            for _, row in df.iterrows():
                ts = row['timestamp']
                if isinstance(ts, pd.Timestamp):
                    ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    ts_str = str(ts)
                records.append((
                    instrument_id, ts_str,
                    float(row['open']), float(row['high']),
                    float(row['low']), float(row['close']),
                    timeframe, source
                ))

            conn.executemany(
                """INSERT OR IGNORE INTO candles
                   (instrument_id, timestamp, open, high, low, close, timeframe, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                records
            )
            conn.commit()

            count_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM candles WHERE instrument_id = ? AND timeframe = ?",
                (instrument_id, timeframe)
            ).fetchone()['cnt']

            inserted = count_after - count_before
            skipped = total - inserted
            return (inserted, skipped)
        finally:
            conn.close()


class NewsRepository:
    """
    Доступ к новостному календарю.
    get_dataframe() возвращает DataFrame совместимый с DataProcessor:
    колонки [timestamp, impact, event, currency].
    """

    def get_dataframe(self, start_date: Optional[date] = None,
                      end_date: Optional[date] = None) -> pd.DataFrame:
        query = "SELECT timestamp, impact, event, currency FROM news_events WHERE 1=1"
        params: list = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(str(start_date))
        if end_date:
            end_dt = datetime.combine(end_date, datetime.max.time())
            query += " AND timestamp < ?"
            params.append(end_dt.strftime('%Y-%m-%d %H:%M:%S'))

        query += " ORDER BY timestamp"

        conn = get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()

        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df

    def get_date_range(self) -> Optional[Tuple[str, str]]:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM news_events"
            ).fetchone()
            if row and row['min_ts']:
                return (row['min_ts'], row['max_ts'])
            return None
        finally:
            conn.close()

    def get_count(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM news_events").fetchone()
            return row['cnt']
        finally:
            conn.close()

    def bulk_insert(self, df: pd.DataFrame, source: str = 'csv') -> Tuple[int, int]:
        """
        Вставляет новости из DataFrame в БД.
        Дедупликация по UNIQUE(timestamp, event, currency).
        Возвращает (inserted, skipped).
        """
        if df.empty:
            return (0, 0)

        conn = get_connection()
        try:
            total = len(df)
            count_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM news_events"
            ).fetchone()['cnt']

            records = []
            for _, row in df.iterrows():
                ts = row['timestamp']
                if isinstance(ts, pd.Timestamp):
                    ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    ts_str = str(ts)
                records.append((
                    ts_str,
                    str(row.get('impact', '')),
                    str(row.get('event', '')) if pd.notna(row.get('event')) else None,
                    str(row.get('currency', '')) if pd.notna(row.get('currency')) else None,
                    source
                ))

            conn.executemany(
                """INSERT OR IGNORE INTO news_events
                   (timestamp, impact, event, currency, source)
                   VALUES (?, ?, ?, ?, ?)""",
                records
            )
            conn.commit()

            count_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM news_events"
            ).fetchone()['cnt']

            inserted = count_after - count_before
            skipped = total - inserted
            return (inserted, skipped)
        finally:
            conn.close()


class ImportLogRepository:
    """Лог импортов для отслеживания истории."""

    def log_import(self, instrument_id: Optional[int], source: str,
                   filename: Optional[str], rows_imported: int,
                   rows_skipped: int, date_from: str = None,
                   date_to: str = None):
        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO import_log
                   (instrument_id, source, filename, rows_imported, rows_skipped, date_from, date_to)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (instrument_id, source, filename, rows_imported, rows_skipped, date_from, date_to)
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent(self, limit: int = 20) -> List[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT il.*, i.symbol
                   FROM import_log il
                   LEFT JOIN instruments i ON il.instrument_id = i.id
                   ORDER BY il.imported_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
