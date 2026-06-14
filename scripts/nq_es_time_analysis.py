#!/usr/bin/env python3
"""
NQ/ES — анализ оптимального времени входа/выхода для парного трейдинга.

Метод: симуляция входа при |z|>2.5 (как в v8 индикаторе),
       замер времени до возврата к z=0, +1, -1 (TP/StopOut),
       группировка по часу UTC и дню недели.
"""

import sqlite3
import pandas as pd
import numpy as np

DB = '/Volumes/WD_Passport/Trading/trading_analyzer/data/trading.db'
NQ_ID, ES_ID = 7, 6
ZSCORE_LEN = 200
BETA_LONG = 24

# Пороги сигналов из v8 индикатора
Z_ENTRY_STRONG = 2.5
Z_ENTRY = 2.0
Z_TP = 1.0      # цель: возврат к +1σ
Z_BE = 0.0      # break-even: возврат к среднему
Z_STOP = 3.5    # дальнейшее расширение на 1σ — сигнал "что-то идёт не так"

MAX_BARS_HOLD = 96  # 24ч на M15


def load():
    conn = sqlite3.connect(DB)
    nq = pd.read_sql(f"SELECT timestamp, close FROM candles WHERE instrument_id={NQ_ID} ORDER BY timestamp", conn)
    es = pd.read_sql(f"SELECT timestamp, close FROM candles WHERE instrument_id={ES_ID} ORDER BY timestamp", conn)
    conn.close()

    nq['timestamp'] = pd.to_datetime(nq['timestamp'])
    es['timestamp'] = pd.to_datetime(es['timestamp'])
    df = nq.merge(es, on='timestamp', suffixes=('_nq', '_es')).sort_values('timestamp').reset_index(drop=True)

    nq_r = df['close_nq'].pct_change()
    es_r = df['close_es'].pct_change()

    # rolling beta (long window)
    cov = (nq_r * es_r).rolling(BETA_LONG).mean() - nq_r.rolling(BETA_LONG).mean() * es_r.rolling(BETA_LONG).mean()
    var = (es_r * es_r).rolling(BETA_LONG).mean() - es_r.rolling(BETA_LONG).mean() ** 2
    df['beta'] = (cov / var.replace(0, np.nan)).fillna(4.0)

    df['spread'] = df['close_nq'] - df['beta'] * df['close_es']
    df['ma'] = df['spread'].rolling(ZSCORE_LEN).mean()
    df['sd'] = df['spread'].rolling(ZSCORE_LEN).std()
    df['z'] = (df['spread'] - df['ma']) / df['sd'].replace(0, np.nan)

    df['hour'] = df['timestamp'].dt.hour
    df['dow'] = df['timestamp'].dt.dayofweek
    df['date'] = df['timestamp'].dt.date

    return df.dropna(subset=['z']).reset_index(drop=True)


def simulate_entries(df, z_threshold=Z_ENTRY_STRONG):
    """
    Симулирует вход при |z|>threshold (cross extreme), замеряет:
      - время до z=0 (BE), z=±1 (TP), z=±3.5 (STOP)
      - часовую/дневную статистику
    """
    z = df['z'].values
    h = df['hour'].values
    dow = df['dow'].values
    n = len(df)

    trades = []

    # Direction: enter LONG-spread (long NQ short ES) when z < -threshold
    #            enter SHORT-spread (short NQ long ES) when z > +threshold
    i = ZSCORE_LEN  # warm up
    while i < n - 1:
        if z[i] < -z_threshold and z[i-1] >= -z_threshold:
            direction = 'LONG_SPREAD'
            target = Z_TP   # exit when z reaches -Z_TP from below (i.e. -1 from -2.5)
            be     = Z_BE
            stop   = -Z_STOP
        elif z[i] > z_threshold and z[i-1] <= z_threshold:
            direction = 'SHORT_SPREAD'
            target = -Z_TP
            be     = Z_BE
            stop   = Z_STOP
        else:
            i += 1
            continue

        entry_z = z[i]
        entry_h = h[i]
        entry_dow = dow[i]
        entry_ts = df['timestamp'].iloc[i]

        # Walk forward
        bars_to_be = None
        bars_to_tp = None
        outcome = 'TIMEOUT'
        exit_j = MAX_BARS_HOLD  # default = end of holding window

        for j in range(1, MAX_BARS_HOLD + 1):
            if i + j >= n:
                outcome = 'EOD'
                exit_j = j
                break
            zj = z[i + j]

            if direction == 'LONG_SPREAD':
                if bars_to_be is None and zj >= be:
                    bars_to_be = j
                    outcome = 'BE_REACHED'
                    exit_j = j
                    break
                if zj <= stop:
                    outcome = 'STOP_OUT'
                    exit_j = j
                    break
            else:
                if bars_to_be is None and zj <= be:
                    bars_to_be = j
                    outcome = 'BE_REACHED'
                    exit_j = j
                    break
                if zj >= stop:
                    outcome = 'STOP_OUT'
                    exit_j = j
                    break

        # Final z at exit moment (correct for all outcomes)
        exit_idx = min(i + exit_j, n - 1)
        exit_z = z[exit_idx]
        exit_h = h[exit_idx]

        # R = movement in z-space, signed by direction
        if direction == 'LONG_SPREAD':
            r_units = exit_z - entry_z  # positive = profit
        else:
            r_units = entry_z - exit_z

        trades.append({
            'entry_ts': entry_ts,
            'entry_h': entry_h,
            'entry_dow': entry_dow,
            'entry_z': entry_z,
            'direction': direction,
            'bars_to_be': bars_to_be,
            'bars_to_tp': bars_to_tp,
            'exit_h': exit_h,
            'exit_z': exit_z,
            'r_units': r_units,
            'outcome': outcome,
        })

        # Skip ahead so we don't double-count overlapping entries
        i += max(bars_to_be if bars_to_be else 4, 4)

    return pd.DataFrame(trades)


def main():
    print("=" * 78)
    print("NQ/ES — АНАЛИЗ ОПТИМАЛЬНОГО ВРЕМЕНИ ВХОДА/ВЫХОДА (M15, 2022-2026)")
    print("=" * 78)

    df = load()
    print(f"\nДанные: {len(df):,} баров, {df['timestamp'].min()} → {df['timestamp'].max()}")
    print(f"z-score: lookback={ZSCORE_LEN} баров (50ч), beta_long={BETA_LONG} баров")

    # ---- Симуляция ----
    print(f"\n--- Симуляция входов при |z|>{Z_ENTRY_STRONG} ---")
    trades = simulate_entries(df, Z_ENTRY_STRONG)
    if len(trades) == 0:
        print("Нет сделок при таком пороге.")
        return

    n = len(trades)
    won = (trades['outcome'] == 'BE_REACHED').sum()
    stopped = (trades['outcome'] == 'STOP_OUT').sum()
    timed = (trades['outcome'].isin(['TIMEOUT','EOD'])).sum()

    print(f"  Всего сделок:     {n}")
    print(f"  ✓ BE достигнут:   {won}  ({won/n*100:.1f}%)")
    print(f"  ✗ Stop-out (>3.5σ): {stopped}  ({stopped/n*100:.1f}%)")
    print(f"  ⏱ Timeout (24ч):  {timed}  ({timed/n*100:.1f}%)")
    avg_be = trades['bars_to_be'].dropna().mean()
    med_be = trades['bars_to_be'].dropna().median()
    print(f"  Среднее время до BE: {avg_be:.1f} бар = {avg_be*15/60:.1f}ч  (медиана {med_be:.0f} бар = {med_be*15/60:.1f}ч)")

    # ---- По часам входа ----
    print("\n" + "=" * 78)
    print("ВХОД ПО ЧАСУ UTC")
    print("=" * 78)
    print(f"\n  {'Час':>3}  {'Сделок':>7}  {'BE%':>6}  {'Stop%':>6}  {'Время до BE (ч)':>17}  {'Avg R':>7}")
    print("  " + "-" * 70)
    by_h = []
    for hr in range(24):
        sub = trades[trades['entry_h'] == hr]
        if len(sub) < 5:
            continue
        be_pct = (sub['outcome'] == 'BE_REACHED').mean() * 100
        st_pct = (sub['outcome'] == 'STOP_OUT').mean() * 100
        be_t = sub['bars_to_be'].dropna().mean() * 15 / 60
        avg_r = sub['r_units'].mean()
        by_h.append((hr, len(sub), be_pct, st_pct, be_t, avg_r))
        marker = ''
        if be_pct >= 90 and len(sub) >= 10:
            marker = '  ★ хороший вход'
        elif be_pct < 75:
            marker = '  ⚠ слабый'
        print(f"  {hr:02d}:  {len(sub):>7}  {be_pct:>5.1f}%  {st_pct:>5.1f}%  {be_t:>14.1f}ч  {avg_r:>+6.2f}{marker}")

    # ---- Экстремальный вход (>2.5) только в overlap ----
    print("\n--- Сравнение часовых зон (агрегаты) ---")
    zones = {
        'Asian (00-06 UTC)': trades[trades['entry_h'].between(0, 5)],
        'EU pre (06-12 UTC)': trades[trades['entry_h'].between(6, 11)],
        'EU+US overlap (12-16 UTC)': trades[trades['entry_h'].between(12, 15)],
        'US main (16-20 UTC)': trades[trades['entry_h'].between(16, 19)],
        'US after (20-23 UTC)': trades[trades['entry_h'].between(20, 23)],
    }
    print(f"  {'Зона':<28} {'N':>5} {'BE%':>6} {'Stop%':>6} {'Avg R':>7} {'Время BE':>10}")
    for name, sub in zones.items():
        if len(sub) == 0:
            continue
        be_pct = (sub['outcome'] == 'BE_REACHED').mean() * 100
        st_pct = (sub['outcome'] == 'STOP_OUT').mean() * 100
        avg_r = sub['r_units'].mean()
        be_t = sub['bars_to_be'].dropna().mean() * 15 / 60
        print(f"  {name:<28} {len(sub):>5} {be_pct:>5.1f}% {st_pct:>5.1f}% {avg_r:>+6.2f} {be_t:>8.1f}ч")

    # ---- По дню недели ----
    print("\n" + "=" * 78)
    print("ВХОД ПО ДНЮ НЕДЕЛИ")
    print("=" * 78)
    days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    print(f"\n  {'День':<5} {'Сделок':>7} {'BE%':>6} {'Stop%':>6} {'Avg R':>7} {'Время BE':>10}")
    for d in range(7):
        sub = trades[trades['entry_dow'] == d]
        if len(sub) < 5:
            continue
        be_pct = (sub['outcome'] == 'BE_REACHED').mean() * 100
        st_pct = (sub['outcome'] == 'STOP_OUT').mean() * 100
        avg_r = sub['r_units'].mean()
        be_t = sub['bars_to_be'].dropna().mean() * 15 / 60
        print(f"  {days[d]:<5} {len(sub):>7} {be_pct:>5.1f}% {st_pct:>5.1f}% {avg_r:>+6.2f} {be_t:>8.1f}ч")

    # ---- Распределение часов выхода ----
    print("\n" + "=" * 78)
    print("ВЫХОД (BE) ПО ЧАСУ UTC — когда сделки закрываются")
    print("=" * 78)
    closed = trades[trades['outcome'] == 'BE_REACHED']
    print(f"\n  {'Час':>3}  {'Закрытий':>9}  {'%':>5}")
    for hr in range(24):
        cnt = (closed['exit_h'] == hr).sum()
        pct = cnt / len(closed) * 100 if len(closed) else 0
        bar = '█' * int(pct / 2)
        print(f"  {hr:02d}:  {cnt:>9}  {pct:>4.1f}%  {bar}")

    # ---- Распределение времени удержания ----
    print("\n" + "=" * 78)
    print("РАСПРЕДЕЛЕНИЕ ВРЕМЕНИ УДЕРЖАНИЯ (до возврата к среднему)")
    print("=" * 78)
    times = closed['bars_to_be'].dropna() * 15 / 60  # in hours
    if len(times) > 0:
        for thr_h in [1, 2, 4, 6, 12, 24]:
            pct = (times <= thr_h).mean() * 100
            print(f"  ≤ {thr_h:>2}ч:  {pct:>5.1f}% сделок")
        print(f"\n  P25={times.quantile(0.25):.1f}ч  P50={times.median():.1f}ч  P75={times.quantile(0.75):.1f}ч  P90={times.quantile(0.9):.1f}ч")

    # ---- Сравнение порогов ----
    print("\n" + "=" * 78)
    print("СРАВНЕНИЕ ПОРОГОВ ВХОДА")
    print("=" * 78)
    for thr in [1.5, 2.0, 2.5, 3.0]:
        t = simulate_entries(df, thr)
        if len(t) == 0:
            continue
        be_pct = (t['outcome'] == 'BE_REACHED').mean() * 100
        st_pct = (t['outcome'] == 'STOP_OUT').mean() * 100
        avg_r = t['r_units'].mean()
        avg_t = t['bars_to_be'].dropna().mean() * 15 / 60
        print(f"  |z| > {thr}:  N={len(t):>4}  BE={be_pct:>5.1f}%  Stop={st_pct:>4.1f}%  Avg R={avg_r:>+5.2f}σ  Время BE={avg_t:.1f}ч")


if __name__ == "__main__":
    main()
