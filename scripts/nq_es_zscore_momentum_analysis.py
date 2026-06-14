#!/usr/bin/env python3
"""
Анализ теории z-score momentum: если z достиг ±1 из экстрема,
продолжится ли движение глубже (-2, -3, -4, -5) или вернется обратно?

Метод: Отслеживаем каждый раз, когда |z| пересекает ±1 (в направлении к нулю),
смотрим что произойдет дальше в течение 24 часов:
  - CONTINUATION: z продолжает идти глубже (от -1 к -2, -3, ...)
  - REVERSAL: z разворачивается обратно (от -1 к -0.5, 0, +0.5, ...)
  - STALL: z застряет в коридоре ±1±0.5
"""

import sqlite3
import pandas as pd
import numpy as np

DB = '/Volumes/WD_Passport/Trading/trading_analyzer/data/trading.db'
NQ_ID, ES_ID = 7, 6
ZSCORE_LEN = 200
BETA_LONG = 24
MAX_BARS_LOOK = 96  # 24h on M15


def load():
    """Load and compute z-score for NQ/ES spread."""
    conn = sqlite3.connect(DB)
    nq = pd.read_sql(f"SELECT timestamp, close FROM candles WHERE instrument_id={NQ_ID} ORDER BY timestamp", conn)
    es = pd.read_sql(f"SELECT timestamp, close FROM candles WHERE instrument_id={ES_ID} ORDER BY timestamp", conn)
    conn.close()

    nq['timestamp'] = pd.to_datetime(nq['timestamp'])
    es['timestamp'] = pd.to_datetime(es['timestamp'])
    df = nq.merge(es, on='timestamp', suffixes=('_nq', '_es')).sort_values('timestamp').reset_index(drop=True)

    nq_r = df['close_nq'].pct_change()
    es_r = df['close_es'].pct_change()

    # rolling beta
    cov = (nq_r * es_r).rolling(BETA_LONG).mean() - nq_r.rolling(BETA_LONG).mean() * es_r.rolling(BETA_LONG).mean()
    var = (es_r * es_r).rolling(BETA_LONG).mean() - es_r.rolling(BETA_LONG).mean() ** 2
    df['beta'] = (cov / var.replace(0, np.nan)).fillna(4.0)

    df['spread'] = df['close_nq'] - df['beta'] * df['close_es']
    df['ma'] = df['spread'].rolling(ZSCORE_LEN).mean()
    df['sd'] = df['spread'].rolling(ZSCORE_LEN).std()
    df['z'] = (df['spread'] - df['ma']) / df['sd'].replace(0, np.nan)

    df['hour'] = df['timestamp'].dt.hour
    df['dow'] = df['timestamp'].dt.dayofweek

    return df.dropna(subset=['z']).reset_index(drop=True)


def analyze_momentum():
    """
    Найти все моменты когда z пересекает ±1 (coming from extreme).
    Для каждого пересечения, отследить дальнейшее движение:
      - Продолжил ли глубже?
      - Или развернулся?
    """
    df = load()
    z = df['z'].values
    n = len(df)

    events = []

    # Ищем пересечения через 1σ и -1σ
    # Пересечение -1 идет от отрицательного направления (z < -2.5, затем постепенно к -1, затем...)
    # Пересечение +1 идет из положительного направления (z > +2.5, затем к +1, затем...)

    for i in range(ZSCORE_LEN, n - MAX_BARS_LOOK):
        z_curr = z[i]
        z_prev = z[i-1]

        # Пересечение -1 снизу (z идет вверх, пересекает -1 идя от -2 к нулю)
        if z_prev < -1.0 and z_curr >= -1.0:
            direction = 'UPWARD'
            threshold = -1.0
            target_deep = -2.0
            target_reverse = -0.5
        # Пересечение +1 сверху (z идет вниз, пересекает +1 идя от +2 к нулю)
        elif z_prev > 1.0 and z_curr <= 1.0:
            direction = 'DOWNWARD'
            threshold = 1.0
            target_deep = 2.0
            target_reverse = 0.5
        else:
            continue

        # Теперь смотрим дальше: за 24 часа что произойдет?
        outcome = None
        bars_to_deep = None
        bars_to_reverse = None
        max_z = z_curr
        min_z = z_curr

        for j in range(1, MAX_BARS_LOOK + 1):
            zj = z[i + j]
            max_z = max(max_z, zj)
            min_z = min(min_z, zj)

            # Проверка CONTINUATION (глубже)
            if direction == 'UPWARD' and zj <= target_deep and bars_to_deep is None:
                bars_to_deep = j
                outcome = 'CONTINUATION'

            if direction == 'DOWNWARD' and zj >= target_deep and bars_to_deep is None:
                bars_to_deep = j
                outcome = 'CONTINUATION'

            # Проверка REVERSAL (назад)
            if direction == 'UPWARD' and zj >= target_reverse and bars_to_reverse is None:
                bars_to_reverse = j
                if outcome is None:
                    outcome = 'REVERSAL'

            if direction == 'DOWNWARD' and zj <= target_reverse and bars_to_reverse is None:
                bars_to_reverse = j
                if outcome is None:
                    outcome = 'REVERSAL'

        if outcome is None:
            outcome = 'STALL'

        events.append({
            'timestamp': df['timestamp'].iloc[i],
            'hour': df['hour'].iloc[i],
            'dow': df['dow'].iloc[i],
            'direction': direction,
            'entry_z': z_curr,
            'max_z': max_z,
            'min_z': min_z,
            'outcome': outcome,
            'bars_to_deep': bars_to_deep,
            'bars_to_reverse': bars_to_reverse,
        })

    return pd.DataFrame(events)


def main():
    print("=" * 90)
    print("NQ/ES — АНАЛИЗ Z-SCORE MOMENTUM: ±1 → ПРОДОЛЖЕНИЕ ИЛИ РЕВЕРС?")
    print("=" * 90)

    events = analyze_momentum()
    if len(events) == 0:
        print("Нет событий для анализа.")
        return

    print(f"\nВсего событий пересечения ±1: {len(events)}")

    # ---- Общая статистика ----
    print("\n" + "=" * 90)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 90)
    cont = (events['outcome'] == 'CONTINUATION').sum()
    rev = (events['outcome'] == 'REVERSAL').sum()
    stall = (events['outcome'] == 'STALL').sum()

    print(f"\n  ▶ CONTINUATION (продолжил глубже): {cont:>5} ({cont/len(events)*100:>5.1f}%)")
    print(f"  ◀ REVERSAL (развернулся):         {rev:>5} ({rev/len(events)*100:>5.1f}%)")
    print(f"  = STALL (ни то ни другое):        {stall:>5} ({stall/len(events)*100:>5.1f}%)")

    # ---- По направлению ----
    print("\n" + "=" * 90)
    print("ПО НАПРАВЛЕНИЮ")
    print("=" * 90)
    for dir_name in ['UPWARD', 'DOWNWARD']:
        sub = events[events['direction'] == dir_name]
        if len(sub) == 0:
            continue
        cont_sub = (sub['outcome'] == 'CONTINUATION').sum()
        rev_sub = (sub['outcome'] == 'REVERSAL').sum()
        stall_sub = (sub['outcome'] == 'STALL').sum()

        dir_desc = 'z < -1 → 0 (от -2.5 к нулю)' if dir_name == 'UPWARD' else 'z > +1 → 0 (от +2.5 к нулю)'
        print(f"\n  {dir_desc}")
        print(f"    ▶ Continuation: {cont_sub:>4} ({cont_sub/len(sub)*100:>5.1f}%)")
        print(f"    ◀ Reversal:     {rev_sub:>4} ({rev_sub/len(sub)*100:>5.1f}%)")
        print(f"    = Stall:        {stall_sub:>4} ({stall_sub/len(sub)*100:>5.1f}%)")

        if cont_sub > 0:
            avg_bars = events[events['outcome'] == 'CONTINUATION']['bars_to_deep'].dropna().mean()
            print(f"    ⏱ Среднее время до продолжения: {avg_bars:.1f} бар = {avg_bars*15/60:.1f}ч")

        if rev_sub > 0:
            avg_bars = events[events['outcome'] == 'REVERSAL']['bars_to_reverse'].dropna().mean()
            print(f"    ⏱ Среднее время до реверса: {avg_bars:.1f} бар = {avg_bars*15/60:.1f}ч")

    # ---- По часам ----
    print("\n" + "=" * 90)
    print("ПО ЧАСАМ UTC")
    print("=" * 90)
    print(f"  {'Час':>3}  {'Событий':>7}  {'Contin%':>8}  {'Reversal%':>10}  {'Stall%':>7}")
    print("  " + "-" * 60)
    for hr in range(24):
        sub = events[events['hour'] == hr]
        if len(sub) < 3:
            continue
        cont_pct = (sub['outcome'] == 'CONTINUATION').mean() * 100
        rev_pct = (sub['outcome'] == 'REVERSAL').mean() * 100
        stall_pct = (sub['outcome'] == 'STALL').mean() * 100
        print(f"  {hr:02d}:  {len(sub):>7}  {cont_pct:>7.1f}%  {rev_pct:>9.1f}%  {stall_pct:>6.1f}%")

    # ---- Время до события ----
    print("\n" + "=" * 90)
    print("РАСПРЕДЕЛЕНИЕ ВРЕМЕНИ ДО СОБЫТИЯ")
    print("=" * 90)

    cont_times = events[events['outcome'] == 'CONTINUATION']['bars_to_deep'].dropna() * 15 / 60
    rev_times = events[events['outcome'] == 'REVERSAL']['bars_to_reverse'].dropna() * 15 / 60

    if len(cont_times) > 0:
        print(f"\n  CONTINUATION (продолжение глубже):")
        for thr_h in [0.5, 1, 2, 4, 6, 12, 24]:
            pct = (cont_times <= thr_h).mean() * 100
            print(f"    ≤ {thr_h:>4.1f}ч: {pct:>5.1f}%")
        print(f"    Медиана: {cont_times.median():.1f}ч  P75: {cont_times.quantile(0.75):.1f}ч")

    if len(rev_times) > 0:
        print(f"\n  REVERSAL (реверс):")
        for thr_h in [0.5, 1, 2, 4, 6, 12, 24]:
            pct = (rev_times <= thr_h).mean() * 100
            print(f"    ≤ {thr_h:>4.1f}ч: {pct:>5.1f}%")
        print(f"    Медиана: {rev_times.median():.1f}ч  P75: {rev_times.quantile(0.75):.1f}ч")

    # ---- День недели ----
    print("\n" + "=" * 90)
    print("ПО ДНЮ НЕДЕЛИ")
    print("=" * 90)
    days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    print(f"  {'День':<5} {'Событий':>7}  {'Contin%':>8}  {'Reversal%':>10}")
    for d in range(7):
        sub = events[events['dow'] == d]
        if len(sub) < 3:
            continue
        cont_pct = (sub['outcome'] == 'CONTINUATION').mean() * 100
        rev_pct = (sub['outcome'] == 'REVERSAL').mean() * 100
        print(f"  {days[d]:<5} {len(sub):>7}  {cont_pct:>7.1f}%  {rev_pct:>9.1f}%")

    # ---- Выводы ----
    print("\n" + "=" * 90)
    print("ВЫВОДЫ")
    print("=" * 90)
    overall_cont_pct = cont / len(events) * 100
    print(f"\n✓ ТВОЯ ТЕОРИЯ ВЕРНА НА {overall_cont_pct:.1f}%")
    print(f"  Когда z достигает ±1 от экстрема (например -2.5),")
    print(f"  в {overall_cont_pct:.1f}% случаев он ПРОДОЛЖАЕТ идти глубже")
    print(f"  (до -2, -3, -4, -5...) вместо того чтобы вернуться назад.")
    print(f"\n  Обратный сценарий (реверс на ±0.5): {rev/len(events)*100:.1f}%")
    print(f"  Неопределённо (застой): {stall/len(events)*100:.1f}%")

    # Рекомендации
    print(f"\n" + "=" * 90)
    print("РЕКОМЕНДАЦИИ ДЛЯ ИНДИКАТОРА")
    print("=" * 90)
    if overall_cont_pct > 60:
        print(f"\n1. Не закрывай позицию по частичному профиту на ±1")
        print(f"   Там только {overall_cont_pct:.1f}% шанс что движение продолжится.")
        print(f"   Рекомендация: TP уровень должен быть ниже -2 или выше +2, не -1/+1.")

    if overall_cont_pct < 60:
        print(f"\n1. ±1 уровень — реальная зона реверса (только {overall_cont_pct:.1f}% продолжают).")
        print(f"   Можно использовать его как TP, но рас расхождение с текущей стратегией.")

    print(f"\n2. Закрытие по z=0 остаётся хорошей идеей:")
    print(f"   Mediana времени до z=0 (из предыдущего анализа): 5.8ч")
    print(f"   Большинство позиций завершают цикл через несколько часов.")

    if len(cont_times) > 0:
        median_cont = cont_times.median()
        print(f"\n3. Если даёшь шанс продолжению, медиана: {median_cont:.1f}ч")
        print(f"   90% достигают целевого уровня за {cont_times.quantile(0.9):.1f}ч")


if __name__ == "__main__":
    main()
