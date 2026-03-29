"""
Дефолтный реестр торговых инструментов с маппингом Yahoo Finance тикеров.
base_sl — базовый размер SL в единицах цены для режима "Base SL + RR".
news_currencies — валюты для фильтра новостей (JSON список).
"""

DEFAULT_INSTRUMENTS = [
    {"symbol": "EURUSD",  "yahoo_ticker": "EURUSD=X", "asset_class": "forex",     "precision": 5, "base_sl": 0.0010, "news_currencies": ["USD", "EUR"]},
    {"symbol": "USDJPY",  "yahoo_ticker": "USDJPY=X", "asset_class": "forex",     "precision": 3, "base_sl": 0.150,  "news_currencies": ["USD", "JPY"]},
    {"symbol": "USDCHF",  "yahoo_ticker": "USDCHF=X", "asset_class": "forex",     "precision": 5, "base_sl": 0.0010, "news_currencies": ["USD", "CHF"]},
    {"symbol": "XAUUSD",  "yahoo_ticker": "GC=F",     "asset_class": "commodity", "precision": 3, "base_sl": 20.0,   "news_currencies": ["USD"]},
    {"symbol": "XAGUSD",  "yahoo_ticker": "SI=F",     "asset_class": "commodity", "precision": 3, "base_sl": 0.300,  "news_currencies": ["USD"]},
    {"symbol": "SP500",   "yahoo_ticker": "^GSPC",    "asset_class": "index",     "precision": 2, "base_sl": 30.0,   "news_currencies": ["USD"]},
    {"symbol": "NAS100",  "yahoo_ticker": "^IXIC",    "asset_class": "index",     "precision": 2, "base_sl": 100.0,  "news_currencies": ["USD"]},
    {"symbol": "GER40",   "yahoo_ticker": "^GDAXI",   "asset_class": "index",     "precision": 2, "base_sl": 50.0,   "news_currencies": ["EUR"]},
    {"symbol": "JP225",   "yahoo_ticker": "^N225",    "asset_class": "index",     "precision": 2, "base_sl": 150.0,  "news_currencies": ["JPY"]},
    {"symbol": "ETHUSDT", "yahoo_ticker": "ETH-USD",  "asset_class": "crypto",    "precision": 2, "base_sl": 30.0,   "news_currencies": ["USD"]},
]
