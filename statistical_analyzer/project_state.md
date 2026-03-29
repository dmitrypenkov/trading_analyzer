# PROJECT STATE - Statistical Analyzer

## ✅ ЗАВЕРШЕНО
- [x] **README.md** - документация проекта
  - Описание функционала
  - Инструкции по установке
  - Формат данных
  - Примеры использования

- [x] **app.py** (главный файл, 393 строки)
  - Импорты и настройка страницы
  - Загрузка CSV данных с валидацией
  - UI для настройки параметров:
    - TARGET_R (number_input)
    - DRAWDOWN_R (number_input)  
    - ROLLING_WINDOW_DAYS (slider)
    - IGNORE_BE_NO_TRADE (checkbox)
  - Фильтры данных:
    - Диапазон дат
    - Entry types (multiselect)
    - Directions (multiselect)
  - 6 вкладок для результатов
  - Базовый экспорт в CSV
  - Заглушки для вызова функций из модулей

## 🔄 В ПРОЦЕССЕ
Нет активных задач

## 📋 ОСТАЛОСЬ СДЕЛАТЬ

### 2. **rolling_window.py**
- [ ] `calculate_rolling_windows()` - создание окон
- [ ] `analyze_window_metrics()` - метрики для каждого окна
- [ ] `calculate_target_achievement()` - достижение TARGET_R
- [ ] `calculate_drawdown_achievement()` - достижение DRAWDOWN_R
- [ ] `create_distribution_table()` - таблица распределения
- [ ] `get_extreme_windows()` - лучшие/худшие окна

### 3. **series_analyzer.py**
- [ ] `find_consecutive_series()` - поиск серий TP/SL
- [ ] `count_series_distribution()` - распределение длин серий
- [ ] `analyze_series_by_period()` - серии по годам/месяцам
- [ ] `handle_be_no_trade_mode()` - обработка режима игнорирования
- [ ] `get_max_series_stats()` - статистика максимальных серий

### 4. **temporal_analyzer.py**
- [ ] `analyze_by_hour()` - анализ по часам входа
- [ ] `analyze_by_weekday()` - анализ по дням недели
- [ ] `analyze_seasonality()` - анализ по месяцам года
- [ ] `calculate_holding_times()` - время удержания позиций
- [ ] `compare_tp_sl_speed()` - скорость достижения TP vs SL

## 📊 ТЕХНИЧЕСКИЕ ДЕТАЛИ

### Входные данные
- CSV с колонками: date, weekday, entry_type, direction, entry_time, exit_time, result, r_result
- ~151 строка данных из приложенного файла

### Ключевые параметры
```python
DEFAULT_TARGET_R = 5.0
DEFAULT_DRAWDOWN_R = -10.0
DEFAULT_WINDOW_DAYS = 10
DEFAULT_IGNORE_BE_NO_TRADE = False
```

### Структура вывода
1. **Серии**: таблицы распределения количества TP/SL подряд
2. **Rolling Window**: распределение R с визуализацией ▓▓▓
3. **Экстремумы**: min/max R по периодам
4. **Entry/Direction**: связь с результатами
5. **Временные паттерны**: часы, дни, месяцы

## 🎯 СЛЕДУЮЩИЙ ШАГ
Создание **app.py** - главного файла приложения с UI и координацией всех модулей