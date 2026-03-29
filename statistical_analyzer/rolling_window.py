"""
Модуль анализа скользящего окна (Rolling Window)
Расчет метрик для фиксированных периодов
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


def create_rolling_windows(df: pd.DataFrame, window_days: int) -> List[pd.DataFrame]:
    """
    Создает список скользящих окон из данных
    
    Args:
        df: DataFrame с торговыми данными
        window_days: размер окна в торговых днях
    
    Returns:
        Список DataFrame для каждого окна
    """
    # Получаем уникальные торговые дни
    df['date_dt'] = pd.to_datetime(df['date'])
    unique_dates = sorted(df['date_dt'].unique())
    
    windows = []
    
    # Создаем окна, сдвигаясь на один день
    for i in range(len(unique_dates) - window_days + 1):
        window_dates = unique_dates[i:i + window_days]
        window_df = df[df['date_dt'].isin(window_dates)].copy()
        
        if len(window_df) > 0:
            window_df['window_start'] = window_dates[0]
            window_df['window_end'] = window_dates[-1]
            windows.append(window_df)
    
    return windows


def analyze_window_metrics(window_df: pd.DataFrame) -> Dict:
    """
    Рассчитывает метрики для одного окна
    
    Args:
        window_df: DataFrame одного окна
    
    Returns:
        Словарь с метриками окна
    """
    # Фильтруем только исполненные сделки (не NO_TRADE)
    executed = window_df[window_df['result'] != 'NO_TRADE'].copy()
    
    metrics = {
        'window_start': window_df['window_start'].iloc[0] if 'window_start' in window_df.columns else None,
        'window_end': window_df['window_end'].iloc[0] if 'window_end' in window_df.columns else None,
        'total_trades': len(window_df),
        'executed_trades': len(executed),
        'total_r': executed['r_result'].sum() if len(executed) > 0 else 0,
        'avg_r': executed['r_result'].mean() if len(executed) > 0 else 0,
        'max_r': executed['r_result'].max() if len(executed) > 0 else 0,
        'min_r': executed['r_result'].min() if len(executed) > 0 else 0,
        'tp_count': len(executed[executed['result'] == 'TP']),
        'sl_count': len(executed[executed['result'] == 'SL']),
        'be_count': len(executed[executed['result'] == 'BE']),
        'no_trade_count': len(window_df[window_df['result'] == 'NO_TRADE'])
    }
    
    return metrics


def analyze_rolling_windows(df: pd.DataFrame, window_days: int, 
                           target_r: float, drawdown_r: float) -> Dict:
    """
    Выполняет полный анализ скользящих окон
    
    Args:
        df: DataFrame с торговыми данными
        window_days: размер окна в днях
        target_r: целевая прибыль в R
        drawdown_r: критическая просадка в R
    
    Returns:
        Словарь с результатами анализа
    """
    # Создаем окна
    windows = create_rolling_windows(df, window_days)
    
    if not windows:
        return {
            'total_windows': 0,
            'window_metrics': [],
            'distribution': {},
            'target_achievement': 0,
            'drawdown_achievement': 0
        }
    
    # Анализируем каждое окно
    window_metrics = []
    for window in windows:
        metrics = analyze_window_metrics(window)
        
        # Проверяем достижение целей
        metrics['target_reached'] = metrics['total_r'] >= target_r
        metrics['drawdown_reached'] = metrics['total_r'] <= drawdown_r
        
        window_metrics.append(metrics)
    
    # Создаем DataFrame для удобного анализа
    metrics_df = pd.DataFrame(window_metrics)
    
    # Рассчитываем статистику
    results = {
        'total_windows': len(windows),
        'window_metrics': window_metrics,
        'metrics_df': metrics_df,
        
        # Достижение целей
        'target_reached_count': metrics_df['target_reached'].sum(),
        'target_reached_pct': (metrics_df['target_reached'].sum() / len(metrics_df) * 100) if len(metrics_df) > 0 else 0,
        'drawdown_reached_count': metrics_df['drawdown_reached'].sum(),
        'drawdown_reached_pct': (metrics_df['drawdown_reached'].sum() / len(metrics_df) * 100) if len(metrics_df) > 0 else 0,
        
        # Общая статистика
        'avg_r_per_window': metrics_df['total_r'].mean(),
        'median_r_per_window': metrics_df['total_r'].median(),
        'std_r_per_window': metrics_df['total_r'].std(),
        'best_window_r': metrics_df['total_r'].max(),
        'worst_window_r': metrics_df['total_r'].min(),
        
        # Экстремальные окна
        'best_window': metrics_df.loc[metrics_df['total_r'].idxmax()].to_dict() if len(metrics_df) > 0 else None,
        'worst_window': metrics_df.loc[metrics_df['total_r'].idxmin()].to_dict() if len(metrics_df) > 0 else None
    }
    
    # Создаем распределение
    results['distribution'] = create_r_distribution(metrics_df)
    results['distribution_visual'] = create_distribution_visual(metrics_df)
    
    return results


def create_r_distribution(metrics_df: pd.DataFrame) -> Dict:
    """
    Создает распределение R-результатов по окнам
    
    Args:
        metrics_df: DataFrame с метриками окон
    
    Returns:
        Словарь с распределением
    """
    if len(metrics_df) == 0:
        return {}
    
    # Определяем границы интервалов
    bins = [-float('inf'), -10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10, float('inf')]
    labels = [
        '< -10R',
        '-10R до -8R',
        '-8R до -6R',
        '-6R до -4R',
        '-4R до -2R',
        '-2R до 0R',
        '0R до +2R',
        '+2R до +4R',
        '+4R до +6R',
        '+6R до +8R',
        '+8R до +10R',
        '+10R+'
    ]
    
    # Создаем категории
    metrics_df['r_category'] = pd.cut(metrics_df['total_r'], bins=bins, labels=labels)
    
    # Подсчитываем распределение
    distribution = metrics_df['r_category'].value_counts().sort_index()
    
    # Конвертируем в словарь
    dist_dict = {}
    for label in labels:
        dist_dict[label] = {
            'count': int(distribution.get(label, 0)),
            'percentage': float(distribution.get(label, 0) / len(metrics_df) * 100)
        }
    
    return dist_dict


def create_distribution_visual(metrics_df: pd.DataFrame) -> str:
    """
    Создает визуальное представление распределения R
    
    Args:
        metrics_df: DataFrame с метриками окон
    
    Returns:
        Строка с визуализацией распределения
    """
    if len(metrics_df) == 0:
        return "Нет данных для визуализации"
    
    distribution = create_r_distribution(metrics_df)
    
    # Максимальное количество для масштабирования
    max_count = max(d['count'] for d in distribution.values())
    max_bar_length = 30  # Максимальная длина полосы
    
    visual = []
    
    # Пропускаем категории с нулевыми значениями в начале и конце
    categories_to_show = []
    for label, data in distribution.items():
        if data['count'] > 0:
            categories_to_show.append((label, data))
    
    for label, data in categories_to_show:
        count = data['count']
        
        # Рассчитываем длину полосы
        if max_count > 0:
            bar_length = int((count / max_count) * max_bar_length)
        else:
            bar_length = 0
        
        # Создаем полосу
        bar = '▓' * bar_length if bar_length > 0 else ''
        
        # Форматируем строку
        line = f"{label:15} {bar:30} ({count} окон, {data['percentage']:.1f}%)"
        visual.append(line)
    
    return '\n'.join(visual)


def get_extreme_windows(metrics_df: pd.DataFrame, n: int = 10) -> Dict:
    """
    Получает топ лучших и худших окон
    
    Args:
        metrics_df: DataFrame с метриками окон
        n: количество окон для выборки
    
    Returns:
        Словарь с лучшими и худшими окнами
    """
    if len(metrics_df) == 0:
        return {'best_windows': [], 'worst_windows': []}
    
    # Сортируем по total_r
    sorted_df = metrics_df.sort_values('total_r', ascending=False)
    
    # Лучшие окна
    best_windows = sorted_df.head(n).to_dict('records')
    
    # Худшие окна
    worst_windows = sorted_df.tail(n).to_dict('records')
    
    return {
        'best_windows': best_windows,
        'worst_windows': worst_windows
    }


def analyze_series_in_windows(windows: List[pd.DataFrame], ignore_be_no_trade: bool = False) -> Dict:
    """
    Анализирует максимальные серии TP/SL в окнах
    
    Args:
        windows: список DataFrame окон
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE в сериях
    
    Returns:
        Словарь со статистикой серий в окнах
    """
    max_tp_series = []
    max_sl_series = []
    windows_without_sl = 0
    windows_without_tp = 0
    
    for window in windows:
        # Подсчет максимальной серии TP
        tp_series = count_consecutive_in_window(window, 'TP', ignore_be_no_trade)
        max_tp_series.append(tp_series)
        
        # Подсчет максимальной серии SL
        sl_series = count_consecutive_in_window(window, 'SL', ignore_be_no_trade)
        max_sl_series.append(sl_series)
        
        # Проверка окон без SL или TP
        executed = window[window['result'] != 'NO_TRADE']
        if len(executed[executed['result'] == 'SL']) == 0:
            windows_without_sl += 1
        if len(executed[executed['result'] == 'TP']) == 0:
            windows_without_tp += 1
    
    return {
        'max_tp_in_window': max(max_tp_series) if max_tp_series else 0,
        'max_sl_in_window': max(max_sl_series) if max_sl_series else 0,
        'avg_tp_series': np.mean(max_tp_series) if max_tp_series else 0,
        'avg_sl_series': np.mean(max_sl_series) if max_sl_series else 0,
        'windows_without_sl': windows_without_sl,
        'windows_without_tp': windows_without_tp,
        'windows_without_sl_pct': (windows_without_sl / len(windows) * 100) if windows else 0,
        'windows_without_tp_pct': (windows_without_tp / len(windows) * 100) if windows else 0
    }


def count_consecutive_in_window(window_df: pd.DataFrame, result_type: str, 
                                ignore_be_no_trade: bool = False) -> int:
    """
    Подсчитывает максимальную серию определенного результата в окне
    
    Args:
        window_df: DataFrame окна
        result_type: тип результата ('TP' или 'SL')
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE
    
    Returns:
        Максимальная длина серии
    """
    if len(window_df) == 0:
        return 0
    
    results = window_df['result'].tolist()
    
    if ignore_be_no_trade:
        # Фильтруем BE и NO_TRADE, оставляя только TP и SL
        filtered_results = [r for r in results if r in ['TP', 'SL']]
        results = filtered_results
    
    if not results:
        return 0
    
    # Подсчет максимальной серии
    max_series = 0
    current_series = 0
    
    for result in results:
        if result == result_type:
            current_series += 1
            max_series = max(max_series, current_series)
        elif not ignore_be_no_trade or result in ['TP', 'SL']:
            # Сбрасываем счетчик только если это другой значимый результат
            current_series = 0
    
    return max_series