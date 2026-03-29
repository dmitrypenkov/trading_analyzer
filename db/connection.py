"""
Управление соединением с SQLite базой данных.
"""

import sqlite3
import os
import logging
from pathlib import Path

from db.schema import SCHEMA_SQL
from config.instruments import DEFAULT_INSTRUMENTS

logger = logging.getLogger(__name__)

# Путь к БД: data/trading.db рядом с корнем проекта
_PROJECT_ROOT = Path(__file__).parent.parent
_DB_DIR = _PROJECT_ROOT / "data"
_DB_PATH = _DB_DIR / "trading.db"


def get_db_path() -> Path:
    """Возвращает путь к файлу БД."""
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    """
    Создаёт и возвращает соединение с SQLite.
    Включает WAL mode для concurrent reads.
    """
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Инициализирует БД: создаёт таблицы и сидирует дефолтные инструменты.
    Безопасно вызывать повторно (CREATE IF NOT EXISTS + INSERT OR IGNORE).
    """
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)

        # Миграции
        columns = [row['name'] for row in conn.execute("PRAGMA table_info(instruments)").fetchall()]
        if 'base_sl' not in columns:
            conn.execute("ALTER TABLE instruments ADD COLUMN base_sl REAL DEFAULT 0")
            logger.info("Миграция: добавлена колонка base_sl")
        if 'news_currencies' not in columns:
            conn.execute("ALTER TABLE instruments ADD COLUMN news_currencies TEXT DEFAULT ''")
            logger.info("Миграция: добавлена колонка news_currencies")

        # Сидирование дефолтных инструментов
        import json as _json
        for instr in DEFAULT_INSTRUMENTS:
            nc = _json.dumps(instr.get("news_currencies", []))
            conn.execute(
                """INSERT OR IGNORE INTO instruments (symbol, yahoo_ticker, asset_class, price_precision, base_sl, news_currencies)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (instr["symbol"], instr["yahoo_ticker"], instr["asset_class"], instr["precision"], instr.get("base_sl", 0), nc)
            )

        # Обновить поля для существующих инструментов если пустые
        for instr in DEFAULT_INSTRUMENTS:
            nc = _json.dumps(instr.get("news_currencies", []))
            if instr.get("base_sl", 0) > 0:
                conn.execute(
                    "UPDATE instruments SET base_sl = ? WHERE symbol = ? AND base_sl = 0",
                    (instr["base_sl"], instr["symbol"])
                )
            if instr.get("news_currencies"):
                conn.execute(
                    "UPDATE instruments SET news_currencies = ? WHERE symbol = ? AND (news_currencies IS NULL OR news_currencies = '' OR news_currencies = '[]')",
                    (nc, instr["symbol"])
                )

        conn.commit()
        logger.info(f"БД инициализирована: {_DB_PATH}")
    finally:
        conn.close()
