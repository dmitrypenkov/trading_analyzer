"""
Дефолтный реестр торговых инструментов с маппингом Yahoo Finance тикеров.
"""

DEFAULT_INSTRUMENTS = [
    {"symbol": "EURUSD",  "yahoo_ticker": "EURUSD=X", "asset_class": "forex",     "precision": 5},
    {"symbol": "USDJPY",  "yahoo_ticker": "USDJPY=X", "asset_class": "forex",     "precision": 3},
    {"symbol": "USDCHF",  "yahoo_ticker": "USDCHF=X", "asset_class": "forex",     "precision": 5},
    {"symbol": "XAUUSD",  "yahoo_ticker": "GC=F",     "asset_class": "commodity", "precision": 3},
    {"symbol": "XAGUSD",  "yahoo_ticker": "SI=F",     "asset_class": "commodity", "precision": 3},
    {"symbol": "SP500",   "yahoo_ticker": "^GSPC",    "asset_class": "index",     "precision": 2},
    {"symbol": "NAS100",  "yahoo_ticker": "^IXIC",    "asset_class": "index",     "precision": 2},
    {"symbol": "GER40",   "yahoo_ticker": "^GDAXI",   "asset_class": "index",     "precision": 2},
    {"symbol": "JP225",   "yahoo_ticker": "^N225",    "asset_class": "index",     "precision": 2},
    {"symbol": "ETHUSDT", "yahoo_ticker": "ETH-USD",  "asset_class": "crypto",    "precision": 2},
]
