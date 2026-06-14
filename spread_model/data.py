"""
data.py — загрузка NAS100/SP500 и построение непрерывного фрейма спреда.

Спред и z-score переносим из scripts/nq_es_analytics.py:load_and_compute
(beta = 24-бар rolling-регрессия доходностей, z = (spread-MA50)/STD50).
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.repository import CandleRepository  # noqa: E402

# id инструментов в БД
NAS_ID, SP_ID = 7, 6
# параметры как в nq_es_analytics.py
BETA_SHORT, BETA_LONG, ZSCORE_LEN, CORR_LEN = 3, 24, 50, 12
# рабочий диапазон (далее индексы Yahoo = cash-only, ночного блока нет)
DEFAULT_START = date(2023, 1, 1)
DEFAULT_END = date(2026, 3, 31)


def _rolling_beta(nq_r: pd.Series, es_r: pd.Series, w: int) -> pd.Series:
    """Rolling-beta доходностей NAS на SP (как в nq_es_analytics)."""
    cov = (nq_r * es_r).rolling(w).mean() - nq_r.rolling(w).mean() * es_r.rolling(w).mean()
    var = (es_r * es_r).rolling(w).mean() - es_r.rolling(w).mean() ** 2
    return cov / var.replace(0, np.nan)


def load_spread_frame(start: date = DEFAULT_START, end: date = DEFAULT_END) -> pd.DataFrame:
    """
    Возвращает непрерывный 15m-фрейм с колонками:
      timestamp, close_nas, close_sp, nas_r, es_r,
      beta_l, beta_s, beta_drift, corr, spread, spread_ma, spread_sd, z, dz
    spread = close_nas - beta_l*close_sp (beta_l.fillna(4.0) как в оригинале).
    """
    repo = CandleRepository()
    nas = repo.get_dataframe(NAS_ID, '15m', start, end)[['timestamp', 'close']]
    sp = repo.get_dataframe(SP_ID, '15m', start, end)[['timestamp', 'close']]

    df = nas.merge(sp, on='timestamp', suffixes=('_nas', '_sp'))
    df = df.sort_values('timestamp').reset_index(drop=True)

    df['nas_r'] = df['close_nas'].pct_change()
    df['es_r'] = df['close_sp'].pct_change()

    df['beta_l'] = _rolling_beta(df['nas_r'], df['es_r'], BETA_LONG)
    df['beta_s'] = _rolling_beta(df['nas_r'], df['es_r'], BETA_SHORT)
    df['beta_drift'] = (df['beta_s'] - df['beta_l']).abs() / df['beta_l'].abs().replace(0, np.nan) * 100
    df['corr'] = df['nas_r'].rolling(CORR_LEN).corr(df['es_r'])

    beta_use = df['beta_l'].fillna(4.0)
    df['spread'] = df['close_nas'] - beta_use * df['close_sp']
    df['spread_ma'] = df['spread'].rolling(ZSCORE_LEN).mean()
    df['spread_sd'] = df['spread'].rolling(ZSCORE_LEN).std()
    df['z'] = (df['spread'] - df['spread_ma']) / df['spread_sd'].replace(0, np.nan)
    df['dz'] = df['z'].diff()

    df['hour'] = df['timestamp'].dt.hour
    df['date'] = df['timestamp'].dt.normalize()
    return df


if __name__ == "__main__":
    f = load_spread_frame()
    print(f"Спред-фрейм: {len(f):,} баров, {f['timestamp'].min()} … {f['timestamp'].max()}")
    print(f"NaN в z: {f['z'].isna().sum()}; beta_l median: {f['beta_l'].median():.2f}")
    print(f.tail(3)[['timestamp', 'close_nas', 'close_sp', 'beta_l', 'spread', 'z']].to_string())
