# spread_model — прогноз направления спреда NAS100/SP500

Предсказание знака движения спреда **NAS100/SP500** в сессии **02:00–20:00 UTC** по фичам
из блока **22:00–02:00**, с торговлей market-neutral пары (beta-хедж, нетто-экспозиция ≈ 0)
и выходом по SL/TP в R. Baseline + ML, оценка строго out-of-sample (walk-forward).

## Запуск

```bash
VENV_PY=/Volumes/WD_Passport/Trading/trading_analyzer/venv_trading/bin/python
$VENV_PY -m spread_model.run        # полный пайплайн + отчёт + results.json
$VENV_PY -m spread_model.data       # проверка спред-фрейма
$VENV_PY -m spread_model.dataset    # проверка датасета (834 наблюдения)
$VENV_PY -m spread_model.models     # walk-forward классификация
```

Зависимость: `scikit-learn` (в requirements.txt).

## Как устроено

- **data.py** — грузит NAS100(id 7)+SP500(id 6) 15m из `data/trading.db`, строит
  `spread = close_NAS − β·close_SP`, β = 24-бар rolling-регрессия доходностей,
  `z = (spread−MA50)/STD50` (формулы из `scripts/nq_es_analytics.py`).
- **dataset.py** — 1 наблюдение/день: фичи из блока (≤02:00, без lookahead), `β_entry`
  фиксируется на входе, путь спреда сессии для бэктеста, `label = sign(Δspread за сессию)`.
- **models.py** — baselines (majority, z-rule, logistic) + GradientBoosting; expanding-window
  walk-forward (train строго раньше тестового месяца).
- **backtest.py** — парный бэктест: вход 02:00, `1R = m_sl·σ_спреда`, TP = RR·1R, beta-neutral.
- **run.py** — оркестратор + честный вердикт; сохраняет `results.json`, `equity_best.csv`.

## Результат (OOS 2024-01…2026-03, 577 дней)

- Классификация: logistic **acc 0.555**, AUC 0.55 — слегка выше majority (0.532) и random (0.50).
  GBM переобучается (хуже majority). Слабый, но устойчивый край.
- Бэктест: спред **дрейфил вверх** (NAS обгонял SP), поэтому даже naive «always long spread»
  даёт +12.6R. **Чистый вклад модели** над дрейфом — всего **+2.5R** (Sharpe 1.23→1.45 при 1.5/1.5).
- **Вывод:** направление спреда на горизонте сессии предсказуемо лишь слабо; сырой +R в основном
  от дрейфа, а не от тайминга. Малая выборка, риск подгонки SL/TP.

## ⚠️ Данные

Блок 22:00–02:00 требует ночных данных индексов → доступно только **2023-01…2026-03**
(после индексы Yahoo = cash-only, ночь оборвалась). Для live-торговли нужен фьючерсный
фид (NQ/ES), а не Yahoo cash-индекс. См. память `data_coverage_indices`.
