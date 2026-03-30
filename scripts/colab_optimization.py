"""
Google Colab скрипт для массовой оптимизации R-циклов по всем инструментам.

Инструкция:
1. Загрузите trading.db на Google Drive
2. Откройте Google Colab
3. Вставьте этот код в ячейки
4. Измените GDRIVE_DB_PATH если нужно
"""

# ============================================================
# ЯЧЕЙКА 1: Установка и подключение Google Drive
# ============================================================
CELL_1 = """
# Подключаем Google Drive
from google.colab import drive
drive.mount('/content/drive')

# Путь к БД на Google Drive (ИЗМЕНИТЕ если нужно)
GDRIVE_DB_PATH = "/content/drive/MyDrive/trading.db"

import shutil
shutil.copy(GDRIVE_DB_PATH, "/content/trading.db")
print(f"БД скопирована: {GDRIVE_DB_PATH} -> /content/trading.db")

import os
print(f"Размер: {os.path.getsize('/content/trading.db') / 1024 / 1024:.1f} MB")
"""

# ============================================================
# ЯЧЕЙКА 2: Весь код оптимизации (самодостаточный, без зависимостей от проекта)
# ============================================================
CELL_2 = '''
import sqlite3
import pandas as pd
import numpy as np
import json
import time
import itertools
from datetime import datetime, date, timedelta
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

DB_PATH = "/content/trading.db"

# ===== Параметры оптимизации =====
INSTRUMENTS = ["EURUSD", "USDJPY", "USDCHF", "XAUUSD", "SP500", "NAS100", "GER40", "JP225"]
START_DATE = date(2024, 1, 1)
END_DATE = date(2026, 3, 26)
TARGET_R = 5.0

SL_MULT_RANGE = (0.1, 0.5, 0.1)   # min, max, step
RR_RANGE = (0.5, 1.5, 0.1)         # min, max, step

# Стратегия
STRATEGY = {
    "block_start": datetime.strptime("20:00", "%H:%M").time(),
    "block_end": datetime.strptime("02:00", "%H:%M").time(),
    "session_start": datetime.strptime("03:00", "%H:%M").time(),
    "session_end": datetime.strptime("20:00", "%H:%M").time(),
    "from_previous_day": True,
    "use_return_mode": False,
    "trading_days": [0, 1, 2, 3, 4],
    "limit_only_entry": False,
    "min_range_size": 0.0,
    "max_range_size": 999999.0,
    "use_base_sl_mode": True,
    "tp_coefficient": 1.0,
    "sl_slippage_coefficient": 1.0,
    "commission_rate": 0.0,
    "use_fixed_tp_sl": False,
    "use_news_filter": True,
    "news_impact_filter": ["high"],
    "news_buffer_minutes": 30,
    "skip_red_news_days": False,
}

# ===== DB helpers =====
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_instrument(symbol):
    conn = get_connection()
    row = conn.execute("SELECT * FROM instruments WHERE symbol = ?", (symbol,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_candles(instrument_id, start_date, end_date):
    conn = get_connection()
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    df = pd.read_sql_query(
        "SELECT timestamp, open, high, low, close FROM candles WHERE instrument_id = ? AND timeframe = '15m' AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
        conn, params=[instrument_id, str(start_date), end_dt.strftime('%Y-%m-%d %H:%M:%S')]
    )
    conn.close()
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def get_news(start_date, end_date):
    conn = get_connection()
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    df = pd.read_sql_query(
        "SELECT timestamp, impact, event, currency FROM news_events WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp",
        conn, params=[str(start_date), end_dt.strftime('%Y-%m-%d %H:%M:%S')]
    )
    conn.close()
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

# ===== Минимальный DataProcessor =====
class DataProcessor:
    def __init__(self, price_data, news_data=None):
        self.price_data = price_data.copy()
        if self.price_data['timestamp'].dt.tz is not None:
            self.price_data['timestamp'] = self.price_data['timestamp'].dt.tz_localize(None)
        self.price_data = self.price_data.sort_values('timestamp').reset_index(drop=True)
        self.price_data['date'] = self.price_data['timestamp'].dt.date
        self.price_data['time'] = self.price_data['timestamp'].dt.time

        self.news_data = None
        if news_data is not None and not news_data.empty:
            self.news_data = news_data.copy()
            if self.news_data['timestamp'].dt.tz is not None:
                self.news_data['timestamp'] = self.news_data['timestamp'].dt.tz_localize(None)
            self.news_data['date'] = self.news_data['timestamp'].dt.date

    def get_block_range(self, target_date, block_start, block_end, from_previous_day=False):
        if from_previous_day:
            block_start_date = target_date - timedelta(days=1)
        else:
            block_start_date = target_date

        block_start_dt = datetime.combine(block_start_date, block_start)
        block_end_dt = datetime.combine(target_date, block_end)

        if not from_previous_day and block_end <= block_start:
            block_end_dt += timedelta(days=1)

        mask = (self.price_data['timestamp'] >= block_start_dt) & (self.price_data['timestamp'] <= block_end_dt)
        block_data = self.price_data[mask]

        if block_data.empty:
            return None

        range_high = block_data['high'].max()
        range_low = block_data['low'].min()
        return {
            'range_high': range_high,
            'range_low': range_low,
            'range_size': range_high - range_low,
            'candle_count': len(block_data)
        }

    def get_session_data(self, target_date, session_start, session_end):
        session_start_dt = datetime.combine(target_date, session_start)
        session_end_dt = datetime.combine(target_date, session_end)
        if session_end <= session_start:
            session_end_dt += timedelta(days=1)

        mask = (self.price_data['timestamp'] >= session_start_dt) & (self.price_data['timestamp'] <= session_end_dt)
        return self.price_data[mask].reset_index(drop=True)

    def get_start_position(self, first_candle, block_range):
        price = first_candle['open']
        if price > block_range['range_high']:
            return 'ABOVE'
        elif price < block_range['range_low']:
            return 'BELOW'
        return 'INSIDE'

    def filter_trading_days(self, start_date, end_date, trading_days):
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        available_dates = set(self.price_data['date'].unique())
        return [d.date() for d in dates if d.weekday() in trading_days and d.date() in available_dates]

    def check_news_window(self, timestamp, impact_filter, buffer_minutes, currency_filter=None):
        if self.news_data is None:
            return False
        window_start = timestamp - timedelta(minutes=buffer_minutes)
        window_end = timestamp + timedelta(minutes=buffer_minutes)
        filtered = self.news_data[self.news_data['impact'].isin(impact_filter)]
        if currency_filter:
            filter_upper = [c.upper() for c in currency_filter]
            if 'currency' in filtered.columns:
                filtered = filtered[filtered['currency'].str.upper().isin(filter_upper)]
            elif 'Currency' in filtered.columns:
                filtered = filtered[filtered['Currency'].str.upper().isin(filter_upper)]
        news_in_window = filtered[(filtered['timestamp'] >= window_start) & (filtered['timestamp'] <= window_end)]
        return len(news_in_window) > 0

    def has_high_impact_news_in_day(self, check_date, currency_filter=None):
        if self.news_data is None:
            return False
        day_news = self.news_data[self.news_data['date'] == check_date]
        high_news = day_news[day_news['impact'] == 'high']
        if currency_filter:
            filter_upper = [c.upper() for c in currency_filter]
            if 'currency' in high_news.columns:
                high_news = high_news[high_news['currency'].str.upper().isin(filter_upper)]
            elif 'Currency' in high_news.columns:
                high_news = high_news[high_news['Currency'].str.upper().isin(filter_upper)]
        return len(high_news) > 0

# ===== Минимальный Analyzer =====
class Analyzer:
    def __init__(self, dp):
        self.dp = dp

    def analyze_period(self, start_date, end_date, settings):
        trading_days = self.dp.filter_trading_days(start_date, end_date, settings['trading_days'])
        results = []
        for day in trading_days:
            r = self.analyze_day(day, settings)
            if r:
                results.append(r)
        return results

    def analyze_day(self, target_date, settings):
        block = self.dp.get_block_range(target_date, settings['block_start'], settings['block_end'], settings.get('from_previous_day', False))
        if not block or block['range_size'] <= 0:
            return None

        range_size = block['range_size']
        if range_size < settings.get('min_range_size', 0) or range_size > settings.get('max_range_size', 999999):
            return None

        # Skip red news days
        if settings.get('skip_red_news_days') and settings.get('use_news_filter'):
            if self.dp.has_high_impact_news_in_day(target_date, settings.get('news_currency_filter')):
                return None

        session = self.dp.get_session_data(target_date, settings['session_start'], settings['session_end'])
        if session.empty or len(session) < 2:
            return None

        start_pos = self.dp.get_start_position(session.iloc[0], block)

        # Determine entry
        entry = self._find_entry(session, block, start_pos, settings.get('use_return_mode', False))
        if not entry:
            return {'date': target_date, 'result': 'NO_TRADE', 'entry_type': start_pos + '_BLOCK', 'r_result': 0}

        # Calculate TP/SL
        base_sl = settings.get('base_sl', 0)
        sl_mult = settings.get('sl_multiplier', 0.1)
        rr = settings.get('rr_ratio', 1.5)

        sl_distance = base_sl + (range_size * sl_mult)
        tp_distance = sl_distance * rr

        is_long = 'LONG' in entry['type']
        entry_price = entry['price']

        if is_long:
            tp_price = entry_price + tp_distance
            sl_price = entry_price - sl_distance
        else:
            tp_price = entry_price - tp_distance
            sl_price = entry_price + sl_distance

        # Execute trade
        result = self._execute(session, entry['idx'], tp_price, sl_price, entry_price, is_long, settings)
        result['entry_type'] = entry['type']
        result['date'] = target_date
        result['sl_size'] = sl_distance
        return result

    def _find_entry(self, session, block, start_pos, use_return_mode):
        rh = block['range_high']
        rl = block['range_low']

        for i in range(len(session)):
            c = session.iloc[i]
            touches_high = c['high'] >= rh
            touches_low = c['low'] <= rl

            if start_pos == 'INSIDE':
                if touches_high and touches_low:
                    continue
                if touches_high:
                    etype = 'ENTRY_SHORT_TREND' if use_return_mode else 'ENTRY_LONG_TREND'
                    return {'type': etype, 'price': rh, 'idx': i}
                if touches_low:
                    etype = 'ENTRY_LONG_TREND' if use_return_mode else 'ENTRY_SHORT_TREND'
                    return {'type': etype, 'price': rl, 'idx': i}
            elif start_pos == 'ABOVE':
                if touches_low:
                    etype = 'LIMIT_LONG_TREND' if use_return_mode else 'LIMIT_SHORT_TREND'
                    return {'type': etype, 'price': rl, 'idx': i}
                if touches_high:
                    etype = 'LIMIT_SHORT_TREND' if use_return_mode else 'LIMIT_LONG_TREND'
                    return {'type': etype, 'price': rh, 'idx': i}
            elif start_pos == 'BELOW':
                if touches_high:
                    etype = 'LIMIT_SHORT_TREND' if use_return_mode else 'LIMIT_LONG_TREND'
                    return {'type': etype, 'price': rh, 'idx': i}
                if touches_low:
                    etype = 'LIMIT_LONG_TREND' if use_return_mode else 'LIMIT_SHORT_TREND'
                    return {'type': etype, 'price': rl, 'idx': i}
        return None

    def _execute(self, session, entry_idx, tp_price, sl_price, entry_price, is_long, settings):
        news_filter = settings.get('use_news_filter', False)

        for i in range(entry_idx + 1, len(session)):
            c = session.iloc[i]

            # News breakeven
            if news_filter:
                if self.dp.check_news_window(
                    c['timestamp'],
                    settings.get('news_impact_filter', ['high']),
                    settings.get('news_buffer_minutes', 30),
                    settings.get('news_currency_filter', [])
                ):
                    pnl = c['open'] - entry_price if is_long else entry_price - c['open']
                    sl_size = abs(entry_price - sl_price)
                    r_val = pnl / sl_size if sl_size > 0 else 0
                    return {'result': 'BE', 'r_result': round(r_val, 2), 'exit_price': c['open']}

            # TP check
            if is_long:
                if c['high'] >= tp_price:
                    sl_size = abs(entry_price - sl_price)
                    r_val = (tp_price - entry_price) / sl_size if sl_size > 0 else 0
                    return {'result': 'TP', 'r_result': round(r_val * settings.get('tp_coefficient', 1.0), 2), 'exit_price': tp_price}
                if c['low'] <= sl_price:
                    r_val = -1.0 * settings.get('sl_slippage_coefficient', 1.0)
                    return {'result': 'SL', 'r_result': round(r_val, 2), 'exit_price': sl_price}
            else:
                if c['low'] <= tp_price:
                    sl_size = abs(sl_price - entry_price)
                    r_val = (entry_price - tp_price) / sl_size if sl_size > 0 else 0
                    return {'result': 'TP', 'r_result': round(r_val * settings.get('tp_coefficient', 1.0), 2), 'exit_price': tp_price}
                if c['high'] >= sl_price:
                    r_val = -1.0 * settings.get('sl_slippage_coefficient', 1.0)
                    return {'result': 'SL', 'r_result': round(r_val, 2), 'exit_price': sl_price}

        # Session end
        last = session.iloc[-1]
        pnl = last['close'] - entry_price if is_long else entry_price - last['close']
        sl_size = abs(entry_price - sl_price)
        r_val = pnl / sl_size if sl_size > 0 else 0
        result_type = 'BE' if abs(r_val) < 0.01 else ('TP' if r_val > 0 else 'SL')
        return {'result': result_type, 'r_result': round(r_val, 2), 'exit_price': last['close']}

# ===== R-циклы =====
def calculate_r_cycles(trades, target_r):
    executed = [t for t in trades if t.get('result') in ('TP', 'SL', 'BE')]
    if not executed:
        return {'num_cycles': 0, 'win_cycles': 0, 'loss_cycles': 0, 'avg_trades_per_cycle': 0, 'win_cycle_rate': 0, 'total_trades': 0}

    cum_r = 0.0
    cycle_start = 0
    cycles = []
    for i, t in enumerate(executed):
        cum_r += t['r_result']
        if cum_r >= target_r or cum_r <= -target_r:
            cycles.append({'trades': i - cycle_start + 1, 'result': 'win' if cum_r >= target_r else 'loss'})
            cum_r = 0.0
            cycle_start = i + 1

    n = len(cycles)
    w = sum(1 for c in cycles if c['result'] == 'win')
    total_r = sum(t['r_result'] for t in executed)
    tp_count = sum(1 for t in executed if t['result'] == 'TP')

    return {
        'num_cycles': n,
        'win_cycles': w,
        'loss_cycles': n - w,
        'avg_trades_per_cycle': round(sum(c['trades'] for c in cycles) / n, 1) if n > 0 else 0,
        'win_cycle_rate': round(w / n * 100, 1) if n > 0 else 0,
        'total_trades': len(executed),
        'total_r': round(total_r, 2),
        'win_rate': round(tp_count / len(executed) * 100, 1) if executed else 0,
    }

# ===== ГЛАВНЫЙ ЗАПУСК =====
print("=" * 70)
print("Trading Analyzer — Оптимизация R-циклов (Google Colab)")
print("=" * 70)

# Генерация комбинаций
sl_values = []
v = SL_MULT_RANGE[0]
while v <= SL_MULT_RANGE[1] + 1e-9:
    sl_values.append(round(v, 4))
    v += SL_MULT_RANGE[2]

rr_values = []
v = RR_RANGE[0]
while v <= RR_RANGE[1] + 1e-9:
    rr_values.append(round(v, 4))
    v += RR_RANGE[2]

combos = list(itertools.product(sl_values, rr_values))
print(f"SL mult: {sl_values}")
print(f"RR: {rr_values}")
print(f"Комбинаций на инструмент: {len(combos)}")
print(f"Инструменты: {INSTRUMENTS}")
print(f"Период: {START_DATE} — {END_DATE}")
print(f"Target R: ±{TARGET_R}")
print(f"Всего прогонов: {len(combos) * len(INSTRUMENTS)}")
print()

# Загрузка новостей (один раз)
news_df = get_news(START_DATE, END_DATE)
print(f"Новостей загружено: {len(news_df)}")

all_results = {}
total_start = time.time()

for symbol in INSTRUMENTS:
    instr = get_instrument(symbol)
    if not instr:
        print(f"⚠️ {symbol} не найден в БД, пропускаю")
        continue

    nc_raw = instr.get('news_currencies', '[]')
    news_currencies = json.loads(nc_raw) if isinstance(nc_raw, str) and nc_raw else []
    base_sl = instr.get('base_sl', 0)

    print(f"\n{'='*50}")
    print(f"📊 {symbol} (base_sl={base_sl}, news={news_currencies})")
    print(f"{'='*50}")

    # Загрузка свечей
    price_df = get_candles(instr['id'], START_DATE, END_DATE)
    if price_df.empty:
        print(f"  Нет данных, пропускаю")
        continue
    print(f"  Свечей: {len(price_df):,}")

    dp = DataProcessor(price_df, news_df)
    analyzer = Analyzer(dp)

    results = []
    t0 = time.time()

    for idx, (sl_mult, rr) in enumerate(combos):
        s = deepcopy(STRATEGY)
        s['start_date'] = START_DATE
        s['end_date'] = END_DATE
        s['use_base_sl_mode'] = True
        s['base_sl'] = base_sl
        s['sl_multiplier'] = sl_mult
        s['rr_ratio'] = rr
        s['news_currency_filter'] = news_currencies

        trades = analyzer.analyze_period(START_DATE, END_DATE, s)
        cycles = calculate_r_cycles(trades, TARGET_R)

        results.append({
            'sl_multiplier': sl_mult,
            'rr_ratio': rr,
            **cycles
        })

        if (idx + 1) % 10 == 0:
            print(f"  [{idx+1}/{len(combos)}] {time.time()-t0:.0f}s", end="\\r")

    elapsed = time.time() - t0
    results.sort(key=lambda x: (x['num_cycles'], x['win_cycle_rate']), reverse=True)
    all_results[symbol] = results

    # Показать топ-5
    print(f"  Готово за {elapsed:.0f}s")
    print(f"  {'SL mult':>8s} {'RR':>5s} {'Cycles':>7s} {'Win':>4s} {'Loss':>5s} {'WinR%':>6s} {'Trd/cyc':>8s} {'TotalR':>7s} {'WR%':>5s}")
    for r in results[:5]:
        print(f"  {r['sl_multiplier']:>8.2f} {r['rr_ratio']:>5.1f} {r['num_cycles']:>7d} {r['win_cycles']:>4d} {r['loss_cycles']:>5d} {r['win_cycle_rate']:>6.1f} {r['avg_trades_per_cycle']:>8.1f} {r['total_r']:>7.2f} {r['win_rate']:>5.1f}")

total_elapsed = time.time() - total_start
print(f"\\n{'='*70}")
print(f"Общее время: {total_elapsed:.0f}s ({total_elapsed/60:.1f} мин)")
print(f"{'='*70}")

# Сводная таблица лучших по каждому инструменту
print(f"\\n🏆 ЛУЧШИЕ ПАРАМЕТРЫ ПО КАЖДОМУ ИНСТРУМЕНТУ:")
print(f"{'Инструмент':>12s} {'SL mult':>8s} {'RR':>5s} {'Cycles':>7s} {'Win':>4s} {'Loss':>5s} {'WinR%':>6s} {'TotalR':>7s}")
for symbol in INSTRUMENTS:
    if symbol in all_results and all_results[symbol]:
        b = all_results[symbol][0]
        print(f"{symbol:>12s} {b['sl_multiplier']:>8.2f} {b['rr_ratio']:>5.1f} {b['num_cycles']:>7d} {b['win_cycles']:>4d} {b['loss_cycles']:>5d} {b['win_cycle_rate']:>6.1f} {b['total_r']:>7.2f}")
'''

# ============================================================
# ЯЧЕЙКА 3: Экспорт результатов в CSV
# ============================================================
CELL_3 = '''
# Экспорт всех результатов в CSV
import pandas as pd

all_rows = []
for symbol, results in all_results.items():
    for r in results:
        row = {'instrument': symbol, **r}
        all_rows.append(row)

export_df = pd.DataFrame(all_rows)
export_path = "/content/drive/MyDrive/optimization_results.csv"
export_df.to_csv(export_path, index=False)
print(f"Результаты сохранены: {export_path}")
print(f"Строк: {len(export_df)}")
export_df.head(20)
'''

if __name__ == "__main__":
    print("=" * 60)
    print("Скопируйте содержимое каждой ячейки в Google Colab:")
    print("=" * 60)
    print("\n--- ЯЧЕЙКА 1: Подключение Google Drive ---")
    print(CELL_1)
    print("\n--- ЯЧЕЙКА 2: Оптимизация (основной код) ---")
    print(CELL_2)
    print("\n--- ЯЧЕЙКА 3: Экспорт в CSV ---")
    print(CELL_3)
