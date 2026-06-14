"""
run.py — полный пайплайн: данные → датасет → walk-forward → бэктест → отчёт.

Запуск:  venv_trading/bin/python -m spread_model.run
Сохраняет spread_model/results.json и spread_model/equity_best.csv
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from spread_model.data import load_spread_frame
from spread_model.dataset import build_dataset, FEATURE_COLS
from spread_model.models import walk_forward, classification_report
from spread_model.backtest import sweep, run_backtest

MODELS = ["majority", "z_rule", "logistic", "gbm"]
OUT_DIR = Path(__file__).parent


def main():
    print("=" * 78)
    print("SPREAD MODEL — NAS100/SP500: прогноз направления спреда block 22:00-02:00")
    print("=" * 78)

    frame = load_spread_frame()
    feat, paths = build_dataset(frame)
    print(f"\nДанные: {feat['date'].min().date()} … {feat['date'].max().date()} | "
          f"наблюдений: {len(feat)} | доля label=1: {feat['label'].mean():.3f}")
    print(f"Среднее |движение спреда| за сессию: {feat['sess_ret_R'].abs().mean():.2f} σ")

    # --- Walk-forward классификация ---
    oos = walk_forward(feat)
    rep = classification_report(oos, MODELS)
    print(f"\n--- КЛАССИФИКАЦИЯ (OOS {oos['date'].min().date()} … {oos['date'].max().date()}, "
          f"n={len(oos)}) ---")
    print("Ориентиры: random=0.500, majority=%.3f\n" % oos["label"].mean())
    print(rep.to_string(index=False))

    # --- Бэктест (свип SL/TP) ---
    sw = sweep(oos, feat, paths, MODELS)
    print("\n--- БЭКТЕСТ market-neutral пары (OOS, R) — свип m_sl × RR ---")
    print(sw.to_string(index=False))

    # Лучшая ML-конфигурация (logistic/gbm) по total_r
    ml = sw[sw["model"].isin(["logistic", "gbm"])].sort_values("total_r", ascending=False)
    best = ml.iloc[0]
    best_met, best_eq = run_backtest(oos, feat, paths, best["model"], best["m_sl"], best["rr"])
    best_eq["cumR"] = best_eq["R"].cumsum().round(3)
    best_eq.to_csv(OUT_DIR / "equity_best.csv", index=False)

    # Сравнение моделей при фиксированных m_sl=1.5, RR=1.5 (нейтральный сетап)
    fixed = sw[(sw["m_sl"] == 1.5) & (sw["rr"] == 1.5)].sort_values("total_r", ascending=False)

    # --- Вердикт (честно: отделяем дрейф спреда от реального скилла модели) ---
    log_acc = float(rep.loc[rep["model"] == "logistic", "accuracy"].iloc[0])
    maj_acc = max(float(oos["label"].mean()), 1 - float(oos["label"].mean()))
    # сравнение при ОДИНАКОВОЙ нейтральной размерности 1.5/1.5
    fr = fixed.set_index("model")
    log_r = float(fr.at["logistic", "total_r"]); log_sh = float(fr.at["logistic", "sharpe"])
    maj_r = float(fr.at["majority", "total_r"]); maj_sh = float(fr.at["majority", "sharpe"])
    incr = log_r - maj_r

    print("\n" + "=" * 78)
    print("ВЕРДИКТ")
    print("=" * 78)
    edge_cls = log_acc > maj_acc + 0.01
    print(f"• Классификация (OOS): logistic acc={log_acc:.3f} vs majority={maj_acc:.3f} vs random=0.500, "
          f"AUC={float(rep.loc[rep.model=='logistic','auc'].iloc[0]):.3f}")
    print(f"  → {'слабый, но устойчивый край есть' if edge_cls else 'на уровне случайности'}")
    print(f"• ВАЖНО: спред дрейфил вверх (NAS обгонял SP) → даже naive «always long spread» (majority)")
    print(f"  даёт +{maj_r:.1f}R при 1.5/1.5. Бóльшая часть R — это ДРЕЙФ, а не предсказание.")
    print(f"• Чистый вклад модели (logistic − majority при 1.5/1.5): {incr:+.1f}R, "
          f"Sharpe {maj_sh:.2f}→{log_sh:.2f}")
    print(f"• Лучшая ML по R (подобрано на OOS, риск переподгонки): {best['model']} "
          f"m_sl={best['m_sl']} RR={best['rr']} → {float(best['total_r']):+.1f}R, sharpe={best_met['sharpe']}")
    verdict = (
        f"Слабый край ЕСТЬ (acc {log_acc:.3f}>majority {maj_acc:.3f}, Sharpe {maj_sh:.2f}→{log_sh:.2f}), "
        f"но он МАЛ: чистый вклад модели над «always long spread» всего {incr:+.1f}R за {len(oos)} дней. "
        f"Сырой +R в основном от дрейфа спреда (NAS>SP), а не от тайминга."
        if (edge_cls and incr > 0) else
        "Направление спреда на горизонте сессии практически НЕ предсказуемо: модель не бьёт дрейф/majority."
    )
    print(f"• ИТОГ: {verdict}")
    print("⚠ Данные только 2023…2026-03 (ночной блок индексов оборвался); для live нужен NQ/ES-фьючерс.")

    # --- Сохранение ---
    results = {
        "period": f"{feat['date'].min().date()} … {feat['date'].max().date()}",
        "n_obs": int(len(feat)),
        "n_oos": int(len(oos)),
        "label_up_rate": round(float(feat["label"].mean()), 4),
        "classification": rep.to_dict("records"),
        "backtest_sweep": sw.to_dict("records"),
        "fixed_1.5_1.5": fixed.to_dict("records"),
        "best_ml": {**{k: (float(v) if isinstance(v, (np.floating, float)) else v)
                       for k, v in best_met.items()}},
        "verdict": verdict,
        "feature_cols": FEATURE_COLS,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                                          encoding="utf-8")
    print(f"\n📁 spread_model/results.json + spread_model/equity_best.csv")


if __name__ == "__main__":
    main()
