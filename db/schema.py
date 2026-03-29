"""
Схема базы данных для Trading Analyzer.
Определения таблиц и SQL для создания/миграции.
"""

SCHEMA_SQL = """
-- Реестр торговых инструментов
CREATE TABLE IF NOT EXISTS instruments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL UNIQUE,
    yahoo_ticker    TEXT,
    asset_class     TEXT,
    price_precision INTEGER DEFAULT 5,
    base_sl         REAL DEFAULT 0,
    is_active       BOOLEAN DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- OHLC свечи
CREATE TABLE IF NOT EXISTS candles (
    instrument_id   INTEGER NOT NULL,
    timestamp       TEXT NOT NULL,
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    timeframe       TEXT NOT NULL DEFAULT '15m',
    source          TEXT DEFAULT 'csv',
    PRIMARY KEY (instrument_id, timestamp, timeframe),
    FOREIGN KEY (instrument_id) REFERENCES instruments(id)
);

CREATE INDEX IF NOT EXISTS idx_candles_lookup
    ON candles(instrument_id, timeframe, timestamp);

-- Новости / экономический календарь
CREATE TABLE IF NOT EXISTS news_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    impact          TEXT NOT NULL,
    event           TEXT,
    currency        TEXT,
    source          TEXT DEFAULT 'csv',
    UNIQUE(timestamp, event, currency)
);

CREATE INDEX IF NOT EXISTS idx_news_lookup
    ON news_events(timestamp, impact);

-- Лог импортов
CREATE TABLE IF NOT EXISTS import_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id   INTEGER,
    source          TEXT NOT NULL,
    filename        TEXT,
    rows_imported   INTEGER,
    rows_skipped    INTEGER,
    date_from       TEXT,
    date_to         TEXT,
    imported_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
