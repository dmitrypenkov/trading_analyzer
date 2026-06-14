"""
backtest.py — market-neutral парный бэктест по OOS-предсказаниям.

Вход на открытии сессии (02:00), направление = прогноз модели:
  pred_up=1 → LONG спред (long NAS / short β·SP), профит при росте спреда
  pred_up=0 → SHORT спред
Размер риска: 1R = m_sl·σ_entry (дистанция SL в пунктах спреда), TP = RR·1R.
Путь спреда — по close 15m баров сессии (intrabar экстремумы спреда недоступны →
проверка на закрытии бара, слегка консервативно). Если ни SL, ни TP к 20:00 — закрытие
по последнему бару: R = знак·Δspread / 1R. Хедж beta-neutral → нетто-экспозиция ≈ 0.
"""

import numpy as np
import pandas as pd


def simulate_day(path: np.ndarray, entry: float, sigma: float, pred_up: int,
                 m_sl: float, rr: float, cost_R: float = 0.0) -> float:
    """R одной парной сделки за день."""
    r_unit = m_sl * sigma
    long = pred_up == 1
    if long:
        tp_lvl, sl_lvl = entry + rr * r_unit, entry - r_unit
    else:
        tp_lvl, sl_lvl = entry - rr * r_unit, entry + r_unit

    for s in path[1:]:
        if long:
            if s <= sl_lvl:
                return -1.0 - cost_R
            if s >= tp_lvl:
                return rr - cost_R
        else:
            if s >= sl_lvl:
                return -1.0 - cost_R
            if s <= tp_lvl:
                return rr - cost_R

    # закрытие по концу сессии
    move = (path[-1] - entry) if long else (entry - path[-1])
    return move / r_unit - cost_R


def _metrics(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {"total_r": 0, "trades": 0, "win_rate": 0, "pf": 0, "sharpe": 0, "max_dd": 0}
    gp = r[r > 0].sum()
    gl = -r[r < 0].sum()
    cum = np.cumsum(r)
    dd = float((cum - np.maximum.accumulate(cum)).min())
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0
    return {
        "total_r": round(float(r.sum()), 2),
        "trades": int(len(r)),
        "win_rate": round(float((r > 0).mean()) * 100, 1),
        "pf": round(float(gp / gl), 2) if gl > 0 else float("inf"),
        "sharpe": round(sharpe, 2),
        "max_dd": round(dd, 2),
    }


def run_backtest(oos: pd.DataFrame, feat_df: pd.DataFrame, paths: dict,
                 model: str, m_sl: float, rr: float, cost_R: float = 0.0):
    """Возвращает (metrics dict, r_series DataFrame[date, R])."""
    meta = feat_df.set_index("date")[["entry_spread", "sigma_entry"]]
    pred_col = f"{model}_pred"

    dates, rs = [], []
    for _, row in oos.iterrows():
        d = row["date"]
        if d not in paths or d not in meta.index:
            continue
        r = simulate_day(paths[d], meta.at[d, "entry_spread"], meta.at[d, "sigma_entry"],
                         int(row[pred_col]), m_sl, rr, cost_R)
        dates.append(d)
        rs.append(r)

    r_arr = np.array(rs)
    m = _metrics(r_arr)
    m["model"] = model
    m["m_sl"] = m_sl
    m["rr"] = rr
    return m, pd.DataFrame({"date": dates, "R": rs})


def sweep(oos, feat_df, paths, models, m_sls=(1.0, 1.5, 2.0), rrs=(1.0, 1.5, 2.0), cost_R=0.0):
    """Свип model × m_sl × rr. Возвращает DataFrame метрик."""
    out = []
    for model in models:
        for m_sl in m_sls:
            for rr in rrs:
                met, _ = run_backtest(oos, feat_df, paths, model, m_sl, rr, cost_R)
                out.append(met)
    cols = ["model", "m_sl", "rr", "total_r", "trades", "win_rate", "pf", "sharpe", "max_dd"]
    return pd.DataFrame(out)[cols]
