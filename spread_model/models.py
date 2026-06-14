"""
models.py — baselines + ML с walk-forward (expanding window) OOS.

Модели:
  majority  — всегда мажоритарный класс train (нижняя планка)
  z_rule    — reversion-правило: спред вырастет, если z_entry < 0
  logistic  — LogisticRegression (StandardScaler) на фичах блока
  gbm       — GradientBoostingClassifier

Walk-forward: train на всех днях строго раньше тестового месяца, предсказываем месяц,
ретрейн каждый месяц. OOS-предсказания всех моделей выровнены по одним и тем же дням.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

from spread_model.dataset import FEATURE_COLS

TRAIN_END = "2024-01-01"   # 2023 целиком — стартовый train


def _make_models():
    return {
        "logistic": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, C=0.5, class_weight="balanced"),
        ),
        "gbm": GradientBoostingClassifier(
            n_estimators=120, max_depth=3, learning_rate=0.05,
            subsample=0.8, random_state=42,
        ),
    }


def walk_forward(feat_df: pd.DataFrame, train_end: str = TRAIN_END) -> pd.DataFrame:
    """Возвращает OOS-таблицу: date, label, sess_ret_R, <model>_pred, <model>_proba."""
    feat_df = feat_df.sort_values("date").reset_index(drop=True)
    X_all = feat_df[FEATURE_COLS].to_numpy()
    y_all = feat_df["label"].to_numpy()

    test_mask = feat_df["date"] >= pd.Timestamp(train_end)
    months = sorted(feat_df.loc[test_mask, "date"].dt.to_period("M").unique())

    rows = []
    for m in months:
        m_start = m.start_time
        m_end = (m + 1).start_time
        tr = feat_df["date"] < m_start
        te = (feat_df["date"] >= m_start) & (feat_df["date"] < m_end)
        if te.sum() == 0 or tr.sum() < 30:
            continue

        Xtr, ytr = X_all[tr.to_numpy()], y_all[tr.to_numpy()]
        Xte = X_all[te.to_numpy()]
        sub = feat_df.loc[te, ["date", "label", "sess_ret_R", "z_entry"]].copy()

        # baselines
        maj = int(round(ytr.mean()))
        sub["majority_pred"] = maj
        sub["majority_proba"] = ytr.mean()
        sub["z_rule_pred"] = (sub["z_entry"] < 0).astype(int)
        sub["z_rule_proba"] = (sub["z_entry"] < 0).astype(float)

        # ML (если в train оба класса)
        if len(np.unique(ytr)) == 2:
            for name, mdl in _make_models().items():
                mdl.fit(Xtr, ytr)
                proba = mdl.predict_proba(Xte)[:, 1]
                sub[f"{name}_proba"] = proba
                sub[f"{name}_pred"] = (proba >= 0.5).astype(int)
        else:
            for name in _make_models():
                sub[f"{name}_proba"] = float(maj)
                sub[f"{name}_pred"] = maj

        rows.append(sub.drop(columns=["z_entry"]))

    oos = pd.concat(rows, ignore_index=True).sort_values("date").reset_index(drop=True)
    return oos


def classification_report(oos: pd.DataFrame, models=("majority", "z_rule", "logistic", "gbm")) -> pd.DataFrame:
    """Accuracy / AUC по OOS для каждой модели."""
    from sklearn.metrics import roc_auc_score
    y = oos["label"].to_numpy()
    out = []
    for name in models:
        pred = oos[f"{name}_pred"].to_numpy()
        acc = (pred == y).mean()
        try:
            auc = roc_auc_score(y, oos[f"{name}_proba"].to_numpy())
        except ValueError:
            auc = float("nan")
        out.append({"model": name, "accuracy": round(acc, 4), "auc": round(auc, 4),
                    "n": len(y), "pred_up_rate": round(pred.mean(), 3)})
    return pd.DataFrame(out)


if __name__ == "__main__":
    from spread_model.dataset import build_dataset
    feat, _ = build_dataset()
    oos = walk_forward(feat)
    print(f"OOS наблюдений: {len(oos)} ({oos['date'].min().date()} … {oos['date'].max().date()})")
    print(f"Базовая доля label=1 в OOS: {oos['label'].mean():.3f}\n")
    print(classification_report(oos).to_string(index=False))
