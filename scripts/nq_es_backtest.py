#!/usr/bin/env python3
"""
NQ/ES Transfer Monitor — Backtest & Threshold Validation
Analyzes historical NQ/ES 15m data to validate indicator thresholds
and test z-score mean reversion.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

DB_PATH = '/Volumes/WD_Passport/Trading/trading_analyzer/data/trading.db'
NQ_ID = 7   # NAS100
ES_ID = 6   # SP500

# Pine Script defaults (bars on 15m chart)
BETA_SHORT_BARS = 3    # math.round(15 / 5) = 3
BETA_LONG_BARS = 24    # math.round(120 / 5) = 24
CORR_LEN = 12
ZSCORE_LEN = 50

# Current thresholds from indicator
BETA_WARN = 8.0
BETA_ALERT = 12.0
CORR_WARN = 0.95
CORR_ALERT = 0.90

HORIZONS = [4, 8, 16, 24, 48, 96]  # bars forward (1h, 2h, 4h, 6h, 12h, 24h)
HORIZON_LABELS = ['1ч', '2ч', '4ч', '6ч', '12ч', '24ч']


def load_data():
    """Load NQ and ES 15m candles, merge on timestamp."""
    conn = sqlite3.connect(DB_PATH)
    nq = pd.read_sql(
        f"SELECT timestamp, close FROM candles WHERE instrument_id={NQ_ID} ORDER BY timestamp",
        conn
    )
    es = pd.read_sql(
        f"SELECT timestamp, close FROM candles WHERE instrument_id={ES_ID} ORDER BY timestamp",
        conn
    )
    conn.close()

    nq['timestamp'] = pd.to_datetime(nq['timestamp'])
    es['timestamp'] = pd.to_datetime(es['timestamp'])

    df = nq.merge(es, on='timestamp', suffixes=('_nq', '_es'))
    df = df.sort_values('timestamp').reset_index(drop=True)
    print(f"Загружено {len(df)} совпадающих баров")
    print(f"Период: {df['timestamp'].iloc[0]} — {df['timestamp'].iloc[-1]}")
    return df


def compute_metrics(df):
    """Compute all indicator metrics matching Pine Script logic."""
    # Returns
    df['nq_r'] = df['close_nq'].pct_change()
    df['es_r'] = df['close_es'].pct_change()

    # Rolling beta
    def rolling_beta(nq_r, es_r, window):
        cov = (nq_r * es_r).rolling(window).mean() - nq_r.rolling(window).mean() * es_r.rolling(window).mean()
        var = (es_r * es_r).rolling(window).mean() - es_r.rolling(window).mean() ** 2
        return cov / var.replace(0, np.nan)

    df['beta_s'] = rolling_beta(df['nq_r'], df['es_r'], BETA_SHORT_BARS)
    df['beta_l'] = rolling_beta(df['nq_r'], df['es_r'], BETA_LONG_BARS)
    df['beta_drift'] = (df['beta_s'] - df['beta_l']).abs() / df['beta_l'].abs().replace(0, np.nan) * 100

    # Correlation
    df['corr'] = df['nq_r'].rolling(CORR_LEN).corr(df['es_r'])

    # Z-score of spread
    beta_use = df['beta_l'].fillna(4.0)
    df['spread'] = df['close_nq'] - beta_use * df['close_es']
    df['spread_ma'] = df['spread'].rolling(ZSCORE_LEN).mean()
    df['spread_sd'] = df['spread'].rolling(ZSCORE_LEN).std()
    df['zscore'] = (df['spread'] - df['spread_ma']) / df['spread_sd'].replace(0, np.nan)

    # Time
    df['hour_utc'] = df['timestamp'].dt.hour

    # Forward PnL for Long NQ / Short ES (in basis points)
    for i, h in enumerate(HORIZONS):
        nq_fwd = df['close_nq'].shift(-h) / df['close_nq'] - 1
        es_fwd = df['close_es'].shift(-h) / df['close_es'] - 1
        df[f'pnl_{h}'] = (nq_fwd - es_fwd) * 10000  # bps

    # Forward spread change (for z-score reversion test)
    for h in HORIZONS:
        df[f'z_fwd_{h}'] = df['zscore'].shift(-h)

    return df.dropna(subset=['beta_drift', 'corr', 'zscore']).copy()


def analyze_beta_drift(df):
    """Analyze PnL conditional on beta drift level."""
    print("\n" + "=" * 70)
    print("1. BETA DRIFT — при каком уровне хедж реально ломается?")
    print("=" * 70)

    buckets = [0, 5, 8, 12, 20, 50, 100, 500, np.inf]
    labels = ['0-5%', '5-8%', '8-12%', '12-20%', '20-50%', '50-100%', '100-500%', '500%+']
    df['bd_bucket'] = pd.cut(df['beta_drift'], bins=buckets, labels=labels, right=False)

    print(f"\n{'Bucket':<12} {'Count':>8} {'% bars':>8}", end='')
    for lbl in HORIZON_LABELS:
        print(f" {'PnL '+lbl+' (bps)':>15}", end='')
    print(f" {'StdDev 6ч':>12}")

    total = len(df)
    for label in labels:
        subset = df[df['bd_bucket'] == label]
        if len(subset) < 10:
            continue
        pct = len(subset) / total * 100
        print(f"{label:<12} {len(subset):>8} {pct:>7.1f}%", end='')
        for h in HORIZONS:
            col = f'pnl_{h}'
            if col in subset.columns:
                print(f" {subset[col].mean():>15.2f}", end='')
            else:
                print(f" {'n/a':>15}", end='')
        print(f" {subset['pnl_24'].std():>12.2f}" if 'pnl_24' in subset.columns else "")

    # Optimal threshold
    print("\n--- Оптимальный порог ---")
    thresholds = [5, 8, 10, 12, 15, 20, 30, 50, 100]
    print(f"{'Порог':<10} {'% RED':>8} {'PnL GO (6ч)':>14} {'PnL NO (6ч)':>14} {'Разница':>10} {'GO std':>10} {'NO std':>10}")
    for th in thresholds:
        go = df[df['beta_drift'] < th]
        no = df[df['beta_drift'] >= th]
        if len(go) < 10 or len(no) < 10:
            continue
        pct_red = len(no) / total * 100
        go_pnl = go['pnl_24'].mean()
        no_pnl = no['pnl_24'].mean()
        print(f"{th:>5}%     {pct_red:>7.1f}% {go_pnl:>14.2f} {no_pnl:>14.2f} {go_pnl - no_pnl:>10.2f} {go['pnl_24'].std():>10.2f} {no['pnl_24'].std():>10.2f}")


def analyze_correlation(df):
    """Analyze PnL conditional on correlation level."""
    print("\n" + "=" * 70)
    print("2. CORRELATION — при какой корреляции хедж работает?")
    print("=" * 70)

    buckets = [-1, 0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.01]
    labels = ['<0', '0-0.5', '0.5-0.7', '0.7-0.8', '0.8-0.9', '0.9-0.95', '0.95+']
    df['corr_bucket'] = pd.cut(df['corr'], bins=buckets, labels=labels, right=False)

    print(f"\n{'Bucket':<12} {'Count':>8} {'% bars':>8}", end='')
    for lbl in HORIZON_LABELS:
        print(f" {'PnL '+lbl+' (bps)':>15}", end='')
    print(f" {'StdDev 6ч':>12}")

    total = len(df)
    for label in labels:
        subset = df[df['corr_bucket'] == label]
        if len(subset) < 10:
            continue
        pct = len(subset) / total * 100
        print(f"{label:<12} {len(subset):>8} {pct:>7.1f}%", end='')
        for h in HORIZONS:
            col = f'pnl_{h}'
            print(f" {subset[col].mean():>15.2f}", end='')
        print(f" {subset['pnl_24'].std():>12.2f}")

    # Optimal threshold
    print("\n--- Оптимальный порог ---")
    thresholds = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
    print(f"{'Порог':<10} {'% RED':>8} {'PnL GO (6ч)':>14} {'PnL NO (6ч)':>14} {'Разница':>10} {'|PnL| NO':>10}")
    for th in thresholds:
        go = df[df['corr'] >= th]
        no = df[df['corr'] < th]
        if len(go) < 10 or len(no) < 10:
            continue
        pct_red = len(no) / total * 100
        go_pnl = go['pnl_24'].mean()
        no_pnl = no['pnl_24'].mean()
        abs_no = no['pnl_24'].abs().mean()
        print(f"  {th:<8} {pct_red:>7.1f}% {go_pnl:>14.2f} {no_pnl:>14.2f} {go_pnl - no_pnl:>10.2f} {abs_no:>10.2f}")


def analyze_zscore_reversion(df):
    """Test whether z-score mean-reverts at various thresholds."""
    print("\n" + "=" * 70)
    print("3. Z-SCORE MEAN REVERSION — работает ли возврат к среднему?")
    print("=" * 70)

    print("\n--- Когда z-score > порог, как часто возвращается ближе к 0? ---")
    thresholds = [1.0, 1.5, 2.0, 2.5, 3.0]

    for th in thresholds:
        above = df[df['zscore'] > th].copy()
        below = df[df['zscore'] < -th].copy()

        if len(above) < 10 and len(below) < 10:
            continue

        print(f"\n  Z > +{th} ({len(above)} баров):")
        if len(above) >= 10:
            for i, h in enumerate(HORIZONS):
                col = f'z_fwd_{h}'
                if col not in above.columns:
                    continue
                valid = above[col].dropna()
                reverted = (valid < above.loc[valid.index, 'zscore']).sum()
                crossed_zero = (valid < 0).sum()
                rate = reverted / len(valid) * 100 if len(valid) > 0 else 0
                zero_rate = crossed_zero / len(valid) * 100 if len(valid) > 0 else 0
                avg_z_after = valid.mean()
                print(f"    {HORIZON_LABELS[i]:>4}: стал ближе к 0 в {rate:.1f}% | пересёк 0 в {zero_rate:.1f}% | avg z после: {avg_z_after:.2f}")

        print(f"  Z < -{th} ({len(below)} баров):")
        if len(below) >= 10:
            for i, h in enumerate(HORIZONS):
                col = f'z_fwd_{h}'
                if col not in below.columns:
                    continue
                valid = below[col].dropna()
                reverted = (valid > below.loc[valid.index, 'zscore']).sum()
                crossed_zero = (valid > 0).sum()
                rate = reverted / len(valid) * 100 if len(valid) > 0 else 0
                zero_rate = crossed_zero / len(valid) * 100 if len(valid) > 0 else 0
                avg_z_after = valid.mean()
                print(f"    {HORIZON_LABELS[i]:>4}: стал ближе к 0 в {rate:.1f}% | пересёк 0 в {zero_rate:.1f}% | avg z после: {avg_z_after:.2f}")

    # PnL conditional on z-score (for Long NQ / Short ES)
    print("\n--- PnL парной позиции (L NQ / S ES) при разных z-score ---")
    z_buckets = [(-np.inf, -3), (-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 3), (3, np.inf)]
    z_labels = ['<-3', '-3..-2', '-2..-1', '-1..0', '0..+1', '+1..+2', '+2..+3', '>+3']

    print(f"{'Z-score':<10} {'Count':>8}", end='')
    for lbl in HORIZON_LABELS:
        print(f" {'PnL '+lbl:>12}", end='')
    print()

    for (lo, hi), label in zip(z_buckets, z_labels):
        subset = df[(df['zscore'] >= lo) & (df['zscore'] < hi)]
        if len(subset) < 10:
            continue
        print(f"{label:<10} {len(subset):>8}", end='')
        for h in HORIZONS:
            print(f" {subset[f'pnl_{h}'].mean():>12.2f}", end='')
        print()


def analyze_stationarity(df):
    """Test spread stationarity with ADF test."""
    print("\n" + "=" * 70)
    print("4. СТАЦИОНАРНОСТЬ СПРЕДА — можно ли вообще доверять z-score?")
    print("=" * 70)

    try:
        from statsmodels.tsa.stattools import adfuller
        spread = df['spread'].dropna()

        # Full period
        result = adfuller(spread, maxlag=50, autolag='AIC')
        print(f"\nADF тест (весь период, {len(spread)} баров):")
        print(f"  Статистика: {result[0]:.4f}")
        print(f"  p-value:    {result[1]:.6f}")
        print(f"  Критические: 1%={result[4]['1%']:.4f}  5%={result[4]['5%']:.4f}  10%={result[4]['10%']:.4f}")
        if result[1] < 0.01:
            print(f"  ✓ Спред СТАЦИОНАРЕН (p={result[1]:.6f} < 0.01) — z-score имеет смысл")
        elif result[1] < 0.05:
            print(f"  ~ Спред СЛАБО стационарен (p={result[1]:.6f}) — z-score с осторожностью")
        else:
            print(f"  ✗ Спред НЕ стационарен (p={result[1]:.6f}) — z-score НЕНАДЁЖЕН")

        # Rolling ADF (yearly windows)
        print("\n  Стационарность по годам:")
        for year in sorted(df['timestamp'].dt.year.unique()):
            yearly = df[df['timestamp'].dt.year == year]['spread'].dropna()
            if len(yearly) < 200:
                continue
            r = adfuller(yearly, maxlag=30, autolag='AIC')
            status = "✓ стац." if r[1] < 0.05 else "✗ НЕ стац."
            print(f"    {year}: p={r[1]:.4f} {status} ({len(yearly)} баров)")

    except ImportError:
        print("\n  statsmodels не установлен — пропускаю ADF тест")
        print("  Альтернативный тест: автокорреляция z-score")

        # Simple mean reversion test: autocorrelation of z-score changes
        dz = df['zscore'].diff().dropna()
        for lag in [1, 4, 8, 16]:
            ac = dz.autocorr(lag=lag)
            print(f"  Autocorr dZ (lag={lag}): {ac:.4f}", "← отрицательная = mean reversion" if ac < 0 else "← положительная = тренд")


def analyze_time_of_day(df):
    """Analyze which hours are best/worst for the pair."""
    print("\n" + "=" * 70)
    print("5. ВРЕМЯ ДНЯ — какие часы реально опасны/безопасны?")
    print("=" * 70)

    # Current time windows
    def time_status(h):
        if (3 <= h < 7) or (14 <= h < 19):
            return 'GREEN'
        elif 7 <= h < 12:
            return 'YELLOW'
        else:
            return 'RED'

    print(f"\n{'Час UTC':<10} {'Статус':<8} {'Count':>8} {'PnL 1ч':>10} {'PnL 4ч':>10} {'PnL 6ч':>10} {'Волат 6ч':>10} {'|PnL| 6ч':>10}")

    for h in range(24):
        subset = df[df['hour_utc'] == h]
        if len(subset) < 10:
            continue
        status = time_status(h)
        pnl_1 = subset['pnl_4'].mean()
        pnl_4 = subset['pnl_16'].mean()
        pnl_6 = subset['pnl_24'].mean()
        vol = subset['pnl_24'].std()
        abs_pnl = subset['pnl_24'].abs().mean()
        print(f"  {h:02d}:00    {status:<8} {len(subset):>8} {pnl_1:>10.2f} {pnl_4:>10.2f} {pnl_6:>10.2f} {vol:>10.2f} {abs_pnl:>10.2f}")

    # Aggregate by status
    print("\n--- Агрегат по статусу ---")
    print(f"{'Статус':<10} {'Count':>8} {'Avg PnL 6ч':>14} {'StdDev':>10} {'Sharpe':>10}")
    for status in ['GREEN', 'YELLOW', 'RED']:
        hours = [h for h in range(24) if time_status(h) == status]
        subset = df[df['hour_utc'].isin(hours)]
        if len(subset) < 10:
            continue
        avg = subset['pnl_24'].mean()
        std = subset['pnl_24'].std()
        sharpe = avg / std if std > 0 else 0
        print(f"  {status:<8} {len(subset):>8} {avg:>14.2f} {std:>10.2f} {sharpe:>10.4f}")


def analyze_signal_quality(df):
    """Test combined signal quality with current thresholds."""
    print("\n" + "=" * 70)
    print("6. КАЧЕСТВО СИГНАЛА — false positive / false negative")
    print("=" * 70)

    def time_status_num(h):
        if (3 <= h < 7) or (14 <= h < 19):
            return 0
        elif 7 <= h < 12:
            return 1
        else:
            return 2

    df['beta_st'] = df['beta_drift'].apply(lambda x: 2 if x >= BETA_ALERT else (1 if x >= BETA_WARN else 0))
    df['corr_st'] = df['corr'].apply(lambda x: 2 if x < CORR_ALERT else (1 if x < CORR_WARN else 0))
    df['time_st'] = df['hour_utc'].apply(time_status_num)

    df['market_risk'] = df[['beta_st', 'corr_st']].max(axis=1)
    df['overall'] = df[['market_risk', 'time_st']].max(axis=1)

    status_map = {0: 'GO', 1: 'WAIT', 2: 'NO'}

    print(f"\n{'Статус':<8} {'Count':>8} {'% bars':>8} {'Avg PnL 6ч':>14} {'Avg PnL 24ч':>15} {'% PnL>0 (6ч)':>14} {'StdDev 6ч':>12}")
    total = len(df)

    for s in [0, 1, 2]:
        subset = df[df['overall'] == s]
        if len(subset) < 10:
            continue
        pct = len(subset) / total * 100
        avg6 = subset['pnl_24'].mean()
        avg24 = subset['pnl_96'].mean()
        pos_rate = (subset['pnl_24'] > 0).sum() / len(subset) * 100
        std6 = subset['pnl_24'].std()
        print(f"  {status_map[s]:<6} {len(subset):>8} {pct:>7.1f}% {avg6:>14.2f} {avg24:>15.2f} {pos_rate:>13.1f}% {std6:>12.2f}")

    # Market risk only (without time)
    print(f"\n--- Только рыночный риск (без Time) ---")
    print(f"{'Статус':<10} {'Count':>8} {'% bars':>8} {'Avg PnL 6ч':>14} {'% PnL>0':>10} {'StdDev':>10}")
    mkt_map = {0: 'MKT OK', 1: 'MKT RISK', 2: 'MKT DANGER'}
    for s in [0, 1, 2]:
        subset = df[df['market_risk'] == s]
        if len(subset) < 10:
            continue
        pct = len(subset) / total * 100
        avg = subset['pnl_24'].mean()
        pos = (subset['pnl_24'] > 0).sum() / len(subset) * 100
        std = subset['pnl_24'].std()
        print(f"  {mkt_map[s]:<10} {len(subset):>8} {pct:>7.1f}% {avg:>14.2f} {pos:>9.1f}% {std:>10.2f}")

    # Individual metric contribution
    print(f"\n--- Вклад каждой метрики ---")
    for name, col in [('β-drift RED', 'beta_st'), ('Corr RED', 'corr_st')]:
        red = df[df[col] == 2]
        ok = df[df[col] == 0]
        if len(red) < 10 or len(ok) < 10:
            continue
        print(f"  {name}: RED PnL={red['pnl_24'].mean():+.2f} bps ({len(red)} бар) | OK PnL={ok['pnl_24'].mean():+.2f} bps ({len(ok)} бар) | Δ={ok['pnl_24'].mean() - red['pnl_24'].mean():.2f} bps")


def analyze_zscore_as_exit(df):
    """Test z-score as exit signal: enter at any time, exit when z crosses threshold."""
    print("\n" + "=" * 70)
    print("7. Z-SCORE КАК СИГНАЛ ВЫХОДА — практический тест")
    print("=" * 70)

    # Simulate: if you're Long NQ / Short ES and z-score hits +2, close.
    # Compare PnL of closing at z=+2 vs holding.
    z_exits = [1.0, 1.5, 2.0, 2.5]

    print(f"\n--- Если закрыть когда z-score пересекает порог вверх ---")
    print(f"{'Порог':<8} {'Пересечений':>12} {'Avg PnL после (6ч)':>20} {'Avg PnL после (24ч)':>22}")
    print("  (PnL после = сколько вы ТЕРЯЕТЕ если НЕ закрыли)")

    for z_exit in z_exits:
        cross_up = df[(df['zscore'] >= z_exit) & (df['zscore'].shift(1) < z_exit)]
        if len(cross_up) < 5:
            continue
        # PnL AFTER the crossing (what you miss/avoid by closing)
        pnl_after_6h = cross_up['pnl_24'].mean()
        pnl_after_24h = cross_up['pnl_96'].mean()
        print(f"  z>{z_exit:<5} {len(cross_up):>12} {pnl_after_6h:>20.2f} {pnl_after_24h:>22.2f}")

    print(f"\n--- Если закрыть когда z-score пересекает порог вниз (стоп-лосс) ---")
    print(f"{'Порог':<8} {'Пересечений':>12} {'Avg PnL после (6ч)':>20} {'Avg PnL после (24ч)':>22}")
    print("  (PnL после = сколько вы ПОЛУЧИТЕ если НЕ закрыли и подождали)")

    for z_exit in z_exits:
        cross_dn = df[(df['zscore'] <= -z_exit) & (df['zscore'].shift(1) > -z_exit)]
        if len(cross_dn) < 5:
            continue
        pnl_after_6h = cross_dn['pnl_24'].mean()
        pnl_after_24h = cross_dn['pnl_96'].mean()
        print(f"  z<-{z_exit:<4} {len(cross_dn):>12} {pnl_after_6h:>20.2f} {pnl_after_24h:>22.2f}")


def summary_recommendations(df):
    """Print final recommendations."""
    print("\n" + "=" * 70)
    print("ИТОГИ И РЕКОМЕНДАЦИИ")
    print("=" * 70)

    # Find best thresholds
    best_beta = None
    best_beta_diff = 0
    for th in range(5, 101, 5):
        go = df[df['beta_drift'] < th]['pnl_24']
        no = df[df['beta_drift'] >= th]['pnl_24']
        if len(go) < 100 or len(no) < 100:
            continue
        diff = go.mean() - no.mean()
        if diff > best_beta_diff:
            best_beta_diff = diff
            best_beta = th

    best_corr = None
    best_corr_diff = 0
    for th_x10 in range(50, 100, 5):
        th = th_x10 / 100
        go = df[df['corr'] >= th]['pnl_24']
        no = df[df['corr'] < th]['pnl_24']
        if len(go) < 100 or len(no) < 100:
            continue
        diff = go.mean() - no.mean()
        if diff > best_corr_diff:
            best_corr_diff = diff
            best_corr = th

    print(f"""
  Текущие пороги → Рекомендация:

  β-drift:     {BETA_ALERT}% → {best_beta}%  (разница PnL: {best_beta_diff:.2f} bps)
  Correlation:  {CORR_ALERT} → {best_corr}   (разница PnL: {best_corr_diff:.2f} bps)

  Z-score mean reversion: см. таблицу выше.
  Если z < -2 возвращается к 0 в >60% случаев за 6ч — имеет смысл ДЕРЖАТЬ.
  Если z > +2 откатывается в >60% — имеет смысл ЗАКРЫВАТЬ.
  """)


def main():
    print("=" * 70)
    print("NQ/ES TRANSFER MONITOR — BACKTEST & VALIDATION")
    print("=" * 70)

    df = load_data()
    print("Вычисляю метрики...")
    df = compute_metrics(df)
    print(f"Данных после вычисления метрик: {len(df)} баров\n")

    analyze_beta_drift(df)
    analyze_correlation(df)
    analyze_zscore_reversion(df)
    analyze_stationarity(df)
    analyze_time_of_day(df)
    analyze_signal_quality(df)
    analyze_zscore_as_exit(df)
    summary_recommendations(df)


if __name__ == '__main__':
    main()
