"""
Дефолтный реестр торговых инструментов с маппингом Yahoo Finance тикеров.
base_sl — базовый размер SL в единицах цены для режима "Base SL + RR".
"""

DEFAULT_INSTRUMENTS = [
    {"symbol": "EURUSD",  "yahoo_ticker": "EURUSD=X", "asset_class": "forex",     "precision": 5, "base_sl": 0.0010},
    {"symbol": "USDJPY",  "yahoo_ticker": "USDJPY=X", "asset_class": "forex",     "precision": 3, "base_sl": 0.150},
    {"symbol": "USDCHF",  "yahoo_ticker": "USDCHF=X", "asset_class": "forex",     "precision": 5, "base_sl": 0.0010},
    {"symbol": "XAUUSD",  "yahoo_ticker": "GC=F",     "asset_class": "commodity", "precision": 3, "base_sl": 20.0},
    {"symbol": "XAGUSD",  "yahoo_ticker": "SI=F",     "asset_class": "commodity", "precision": 3, "base_sl": 0.300},
    {"symbol": "SP500",   "yahoo_ticker": "^GSPC",    "asset_class": "index",     "precision": 2, "base_sl": 30.0},
    {"symbol": "NAS100",  "yahoo_ticker": "^IXIC",    "asset_class": "index",     "precision": 2, "base_sl": 100.0},
    {"symbol": "GER40",   "yahoo_ticker": "^GDAXI",   "asset_class": "index",     "precision": 2, "base_sl": 50.0},
    {"symbol": "JP225",   "yahoo_ticker": "^N225",    "asset_class": "index",     "precision": 2, "base_sl": 150.0},
    {"symbol": "ETHUSDT", "yahoo_ticker": "ETH-USD",  "asset_class": "crypto",    "precision": 2, "base_sl": 30.0},
]
