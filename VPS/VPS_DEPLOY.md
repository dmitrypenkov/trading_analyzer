# Развёртывание Trading Analyzer на VPS

## Быстрый старт

### 1. Подготовка сервера (Vultr Ubuntu 22/24)

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Python
sudo apt install python3 python3-pip screen -y

# Создать рабочую папку
mkdir ~/trading && cd ~/trading
```

### 2. Загрузить файлы

```bash
# Через scp с ноутбука:
scp app.py analyzer.py data_processor.py r_calculator.py \
    report_generator.py optimizer.py chart_visualizer.py \
    run_optimization.py config.json requirements.txt \
    root@YOUR_VPS_IP:~/trading/

# Загрузить данные
scp data/ETHUSDT_1m.csv root@YOUR_VPS_IP:~/trading/data/
```

### 3. Установить зависимости

```bash
cd ~/trading
pip3 install pandas numpy plotly --break-system-packages
```

Streamlit не нужен для headless-режима. Plotly нужен только для генерации HTML-отчёта.

### 4. Настроить конфиг

```bash
# Скопировать пример и отредактировать
cp config_example.json config.json
nano config.json
```

Обязательно проверить:
- `price_data_path` — путь к CSV с ценами
- `settings.start_date` / `end_date` — период
- `optimization.target` — цель оптимизации
- `optimization.tp_range` / `sl_range` — диапазоны перебора

### 5. Проверить (dry-run)

```bash
python3 run_optimization.py config.json --dry-run
```

Покажет загруженные настройки без запуска вычислений.

### 6. Запустить в фоне

**Вариант A — screen (рекомендуется):**
```bash
screen -S trading
python3 run_optimization.py config.json
# Ctrl+A, D — отсоединиться
# screen -r trading — вернуться
```

**Вариант B — nohup:**
```bash
nohup python3 run_optimization.py config.json > /dev/null 2>&1 &
# Логи в results_XXXXXX/optimization.log
```

**Вариант C — tmux:**
```bash
tmux new -s trading
python3 run_optimization.py config.json
# Ctrl+B, D — отсоединиться
# tmux attach -t trading — вернуться
```

### 7. Забрать результаты

```bash
# С ноутбука:
scp -r root@YOUR_VPS_IP:~/trading/results_*/ ./results/

# Или архивом:
ssh root@YOUR_VPS_IP "cd ~/trading && tar czf results.tar.gz results_*/"
scp root@YOUR_VPS_IP:~/trading/results.tar.gz .
```

---

## Структура результатов

```
results_20260301_143022/
├── config_used.json              # Копия конфига (для воспроизводимости)
├── optimization.log              # Полный лог с прогрессом
├── report.html                   # HTML-отчёт с графиками (открыть в браузере)
├── time_optimization_summary.csv # Сводка по временным окнам
├── all_combinations_1300.csv     # Все TP/SL для лучшего часа
└── csv/
    ├── trades_TP1_50_SL0_80.csv  # Сделки для комбинации TP=1.5 SL=0.8
    ├── trades_TP1_20_SL0_70.csv
    └── ...                       # Топ-N комбинаций
```

### report.html

Самодостаточный HTML-файл с:
- Тепловой картой TP/SL
- Bar chart метрики по временным окнам
- Scatter plot Total R vs Win Rate
- Таблицей всех результатов
- Настройками и лучшим результатом

Открывается в любом браузере, даже без интернета (Plotly.js подгружается с CDN при первом открытии).

---

## Примеры конфигов

### Быстрый тест (5 мин)

```json
{
    "price_data_path": "data/ETHUSDT_5m.csv",
    "settings": {
        "block_start": "00:00",
        "block_end": "13:00",
        "session_start": "13:00",
        "session_end": "20:00",
        "use_return_mode": false,
        "start_date": "2025-01-01",
        "end_date": "2025-03-01",
        "trading_days": [0,1,2,3,4],
        "tp_coefficient": 0.9,
        "sl_slippage_coefficient": 1.0,
        "commission_rate": 0.0005,
        "min_range_size": 10,
        "max_range_size": 200
    },
    "optimization": {
        "tp_range": [0.5, 2.0, 0.5],
        "sl_range": [0.5, 2.0, 0.5],
        "target": "max_total_r"
    }
}
```

### Полная оптимизация с временем (~1–3 часа)

```json
{
    "price_data_path": "data/ETHUSDT_1m.csv",
    "settings": {
        "block_start": "00:00",
        "block_end": "10:00",
        "session_start": "10:00",
        "session_end": "20:00",
        "use_return_mode": false,
        "limit_only_entry": true,
        "start_date": "2024-01-01",
        "end_date": "2025-12-31",
        "trading_days": [0,1,2,3,4],
        "tp_coefficient": 0.9,
        "sl_slippage_coefficient": 1.02,
        "commission_rate": 0.0005,
        "min_range_size": 15,
        "max_range_size": 150
    },
    "optimization": {
        "tp_range": [0.3, 3.0, 0.1],
        "sl_range": [0.3, 2.0, 0.1],
        "target": "max_r_dd_ratio",
        "use_time_optimization": true,
        "block_start_fixed": "00:00",
        "session_end_fixed": "20:00",
        "split_hour_min": 3,
        "split_hour_max": 18,
        "from_previous_day": false,
        "export_top_n_csv": 20
    }
}
```

---

## Мониторинг

```bash
# Смотреть лог в реальном времени
tail -f ~/trading/results_*/optimization.log

# Проверить, работает ли процесс
ps aux | grep run_optimization

# Использование ресурсов
htop
```

---

## Оценка времени

| Данные   | TP/SL комбинаций | Временных точек | Примерное время |
|----------|-------------------|-----------------|-----------------|
| 5m, 1 год | 100              | —               | ~1–3 мин        |
| 5m, 2 года | 500             | —               | ~15–30 мин      |
| 1m, 2 года | 500             | —               | ~1–2 часа       |
| 5m, 2 года | 500             | 16              | ~4–8 часов      |
| 1m, 2 года | 500             | 16              | ~16–30 часов    |

Рекомендация: для первых тестов использовать 5m-данные и грубый шаг (0.5). Когда найдены перспективные зоны — сузить диапазон и уменьшить шаг.
