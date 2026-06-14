"""
dataset.py — формирует по одному наблюдению на день из block(22:00-02:00)→session(02:00-20:00).

Без lookahead: ВСЕ фичи считаются по барам ≤ 02:00 (entry). Label — знак движения спреда
за сессию (будущее относительно entry, что и предсказываем).

Хедж фиксируется на entry: beta_entry = beta_l на первом баре сессии; для трейда строим
spread_fixed_t = close_nas_t − beta_entry·close_sp_t (постоянные пропорции весь день).
"""

import numpy as np
import pandas as pd

from spread_model.data import load_spread_frame

# окна (UTC, часы)
BLOCK_START_H = 22   # предыдущий день
BLOCK_END_H = 2      # = session start
SESSION_END_H = 20

MIN_BLOCK_BARS = 4
MIN_SESSION_BARS = 12

# Колонки-фичи (всё известно на entry 02:00)
FEATURE_COLS = [
    "z_entry", "abs_z", "dz_block",
    "block_spread_range", "block_spread_ret", "block_spread_pos",
    "beta_l", "beta_s", "beta_drift", "corr",
    "nas_ret_block", "sp_ret_block", "ret_diff_block",
    "nas_vol_block", "sp_vol_block",
    "dow", "month",
]


def build_dataset(frame: pd.DataFrame | None = None):
    """
    Возвращает (feat_df, paths):
      feat_df  — DataFrame, строка/день: date, FEATURE_COLS..., label(0/1),
                 entry_spread, sigma_entry, sess_end_spread, sess_ret_R
      paths    — dict[date(pd.Timestamp) -> np.ndarray] путь spread_fixed по сессии (для бэктеста)
    """
    df = frame if frame is not None else load_spread_frame()
    df = df.set_index("timestamp").sort_index()

    # дни, где есть бары сессии
    sess_all = df[(df.index.hour >= BLOCK_END_H) & (df.index.hour < SESSION_END_H)]
    session_dates = pd.Index(sorted(set(sess_all.index.normalize())))

    records = []
    paths = {}

    for d in session_dates:
        b_start = d - pd.Timedelta(days=1) + pd.Timedelta(hours=BLOCK_START_H)
        b_end = d + pd.Timedelta(hours=BLOCK_END_H)          # = entry boundary 02:00
        s_end = d + pd.Timedelta(hours=SESSION_END_H)        # 20:00

        block = df.loc[(df.index >= b_start) & (df.index < b_end)]
        session = df.loc[(df.index >= b_end) & (df.index < s_end)]

        if len(block) < MIN_BLOCK_BARS or len(session) < MIN_SESSION_BARS:
            continue

        entry = session.iloc[0]
        beta_entry = entry["beta_l"]
        sigma_entry = entry["spread_sd"]
        if not np.isfinite(beta_entry) or not np.isfinite(sigma_entry) or sigma_entry <= 0:
            continue

        # spread с фиксированным на entry хеджем — для блока, сессии и label
        block_sf = block["close_nas"] - beta_entry * block["close_sp"]
        sess_sf = (session["close_nas"] - beta_entry * session["close_sp"]).to_numpy()
        entry_spread = sess_sf[0]
        sess_end_spread = sess_sf[-1]

        # --- фичи (только block / entry, ≤ 02:00) ---
        b_lo, b_hi = block_sf.min(), block_sf.max()
        b_rng = b_hi - b_lo
        nas_ret_block = block["close_nas"].iloc[-1] / block["close_nas"].iloc[0] - 1
        sp_ret_block = block["close_sp"].iloc[-1] / block["close_sp"].iloc[0] - 1

        rec = {
            "date": d,
            "z_entry": entry["z"],
            "abs_z": abs(entry["z"]),
            "dz_block": entry["z"] - block["z"].iloc[0],
            "block_spread_range": b_rng / sigma_entry,
            "block_spread_ret": (entry_spread - block_sf.iloc[0]) / sigma_entry,
            "block_spread_pos": (entry_spread - b_lo) / b_rng if b_rng > 0 else 0.5,
            "beta_l": beta_entry,
            "beta_s": entry["beta_s"],
            "beta_drift": entry["beta_drift"],
            "corr": entry["corr"],
            "nas_ret_block": nas_ret_block,
            "sp_ret_block": sp_ret_block,
            "ret_diff_block": nas_ret_block - sp_ret_block,
            "nas_vol_block": block["nas_r"].std(),
            "sp_vol_block": block["es_r"].std(),
            "dow": int(d.dayofweek),
            "month": int(d.month),
            # цель + служебное для бэктеста
            "label": int(sess_end_spread > entry_spread),
            "entry_spread": entry_spread,
            "sigma_entry": sigma_entry,
            "sess_end_spread": sess_end_spread,
            "sess_ret_R": (sess_end_spread - entry_spread) / sigma_entry,
        }
        records.append(rec)
        paths[d] = sess_sf

    feat_df = pd.DataFrame(records).dropna(subset=FEATURE_COLS).reset_index(drop=True)
    return feat_df, paths


if __name__ == "__main__":
    feat, paths = build_dataset()
    print(f"Наблюдений (дней): {len(feat)}")
    print(f"Диапазон: {feat['date'].min().date()} … {feat['date'].max().date()}")
    print(f"Доля label=1 (спред вырос): {feat['label'].mean():.3f}")
    print(f"Среднее |движение спреда| в σ: {feat['sess_ret_R'].abs().mean():.2f}")
    print("\nПримеры фич:")
    print(feat[["date", "z_entry", "block_spread_ret", "ret_diff_block", "label", "sess_ret_R"]].head().to_string())
