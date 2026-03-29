"""
Модуль временного анализа
Анализ по часам, дням недели, месяцам и длительности позиций
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta


def analyze_by_hour(df: pd.DataFrame) -> Dict:
    """
    Анализирует эффективность по часам входа
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь с анализом по часам
    """
    df = df.copy()
    
    # Извлекаем час из времени входа
    df['entry_hour'] = pd.to_datetime(df['entry_time'], format='%H:%M', errors='coerce').dt.hour
    
    # Фильтруем только исполненные сделки
    executed = df[df['result'] != 'NO_TRADE'].copy()
    
    # Группируем по часам
    hourly_stats = []
    
    for hour in range(24):
        hour_data = executed[executed['entry_hour'] == hour]
        
        if len(hour_data) > 0:
            tp_count = len(hour_data[hour_data['result'] == 'TP'])
            sl_count = len(hour_data[hour_data['result'] == 'SL'])
            be_count = len(hour_data[hour_data['result'] == 'BE'])
            
            stats = {
                'hour': f"{hour:02d}:00",
                'total_trades': len(hour_data),
                'tp_count': tp_count,
                'sl_count': sl_count,
                'be_count': be_count,
                'avg_r': round(hour_data['r_result'].mean(), 3),
                'total_r': round(hour_data['r_result'].sum(), 2),
                'win_rate': round(tp_count / len(hour_data) * 100, 1) if len(hour_data) > 0 else 0
            }
        else:
            stats = {
                'hour': f"{hour:02d}:00",
                'total_trades': 0,
                'tp_count': 0,
                'sl_count': 0,
                'be_count': 0,
                'avg_r': 0,
                'total_r': 0,
                'win_rate': 0
            }
        
        hourly_stats.append(stats)
    
    # Создаем DataFrame для удобного анализа
    hourly_df = pd.DataFrame(hourly_stats)
    
    # Находим лучшие и худшие часы
    hourly_df_with_trades = hourly_df[hourly_df['total_trades'] > 0]
    
    if len(hourly_df_with_trades) > 0:
        best_hours = hourly_df_with_trades.nlargest(3, 'avg_r')[['hour', 'avg_r', 'total_trades']].to_dict('records')
        worst_hours = hourly_df_with_trades.nsmallest(3, 'avg_r')[['hour', 'avg_r', 'total_trades']].to_dict('records')
    else:
        best_hours = []
        worst_hours = []
    
    return {
        'hourly_stats': hourly_stats,
        'hourly_df': hourly_df,
        'best_hours': best_hours,
        'worst_hours': worst_hours,
        'most_active_hour': hourly_df.loc[hourly_df['total_trades'].idxmax()].to_dict() if len(hourly_df_with_trades) > 0 else None,
        'least_active_hour': hourly_df_with_trades.loc[hourly_df_with_trades['total_trades'].idxmin()].to_dict() if len(hourly_df_with_trades) > 0 else None
    }


def analyze_by_weekday(df: pd.DataFrame) -> Dict:
    """
    Анализирует эффективность по дням недели
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь с анализом по дням недели
    """
    df = df.copy()
    
    # Конвертируем дату и получаем день недели
    df['date_dt'] = pd.to_datetime(df['date'])
    df['weekday_num'] = df['date_dt'].dt.weekday
    
    # Названия дней недели
    weekday_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    
    # Фильтруем только исполненные сделки
    executed = df[df['result'] != 'NO_TRADE'].copy()
    
    # Группируем по дням недели
    weekday_stats = []
    
    for day_num in range(7):
        day_data = executed[executed['weekday_num'] == day_num]
        
        if len(day_data) > 0:
            tp_count = len(day_data[day_data['result'] == 'TP'])
            sl_count = len(day_data[day_data['result'] == 'SL'])
            be_count = len(day_data[day_data['result'] == 'BE'])
            
            stats = {
                'weekday': weekday_names[day_num],
                'weekday_num': day_num,
                'total_trades': len(day_data),
                'tp_count': tp_count,
                'sl_count': sl_count,
                'be_count': be_count,
                'avg_r': round(day_data['r_result'].mean(), 3),
                'total_r': round(day_data['r_result'].sum(), 2),
                'win_rate': round(tp_count / len(day_data) * 100, 1) if len(day_data) > 0 else 0
            }
        else:
            stats = {
                'weekday': weekday_names[day_num],
                'weekday_num': day_num,
                'total_trades': 0,
                'tp_count': 0,
                'sl_count': 0,
                'be_count': 0,
                'avg_r': 0,
                'total_r': 0,
                'win_rate': 0
            }
        
        weekday_stats.append(stats)
    
    # Создаем DataFrame
    weekday_df = pd.DataFrame(weekday_stats)
    
    # Находим лучший и худший день
    weekday_df_with_trades = weekday_df[weekday_df['total_trades'] > 0]
    
    if len(weekday_df_with_trades) > 0:
        best_day = weekday_df_with_trades.loc[weekday_df_with_trades['avg_r'].idxmax()].to_dict()
        worst_day = weekday_df_with_trades.loc[weekday_df_with_trades['avg_r'].idxmin()].to_dict()
    else:
        best_day = None
        worst_day = None
    
    return {
        'weekday_stats': weekday_stats,
        'weekday_df': weekday_df,
        'best_day': best_day,
        'worst_day': worst_day,
        'most_active_day': weekday_df.loc[weekday_df['total_trades'].idxmax()].to_dict() if len(weekday_df_with_trades) > 0 else None
    }


def analyze_seasonality(df: pd.DataFrame) -> Dict:
    """
    Анализирует сезонность по месяцам года
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь с анализом сезонности
    """
    df = df.copy()
    
    # Конвертируем дату и получаем месяц
    df['date_dt'] = pd.to_datetime(df['date'])
    df['month_num'] = df['date_dt'].dt.month
    df['year'] = df['date_dt'].dt.year
    
    # Названия месяцев
    month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    
    # Фильтруем только исполненные сделки
    executed = df[df['result'] != 'NO_TRADE'].copy()
    
    # Группируем по месяцам (усредняем по всем годам)
    monthly_stats = []
    
    for month_num in range(1, 13):
        month_data = executed[executed['month_num'] == month_num]
        
        if len(month_data) > 0:
            # Подсчитываем количество уникальных годов для этого месяца
            years_count = month_data['year'].nunique()
            
            tp_count = len(month_data[month_data['result'] == 'TP'])
            sl_count = len(month_data[month_data['result'] == 'SL'])
            be_count = len(month_data[month_data['result'] == 'BE'])
            
            stats = {
                'month': month_names[month_num - 1],
                'month_num': month_num,
                'total_trades': len(month_data),
                'avg_trades_per_year': round(len(month_data) / years_count, 1) if years_count > 0 else 0,
                'tp_count': tp_count,
                'sl_count': sl_count,
                'be_count': be_count,
                'avg_r': round(month_data['r_result'].mean(), 3),
                'total_r': round(month_data['r_result'].sum(), 2),
                'avg_r_per_year': round(month_data['r_result'].sum() / years_count, 2) if years_count > 0 else 0,
                'win_rate': round(tp_count / len(month_data) * 100, 1) if len(month_data) > 0 else 0,
                'years_present': years_count
            }
        else:
            stats = {
                'month': month_names[month_num - 1],
                'month_num': month_num,
                'total_trades': 0,
                'avg_trades_per_year': 0,
                'tp_count': 0,
                'sl_count': 0,
                'be_count': 0,
                'avg_r': 0,
                'total_r': 0,
                'avg_r_per_year': 0,
                'win_rate': 0,
                'years_present': 0
            }
        
        monthly_stats.append(stats)
    
    # Создаем DataFrame
    monthly_df = pd.DataFrame(monthly_stats)
    
    # Находим лучший и худший месяц
    monthly_df_with_trades = monthly_df[monthly_df['total_trades'] > 0]
    
    if len(monthly_df_with_trades) > 0:
        best_month = monthly_df_with_trades.loc[monthly_df_with_trades['avg_r'].idxmax()].to_dict()
        worst_month = monthly_df_with_trades.loc[monthly_df_with_trades['avg_r'].idxmin()].to_dict()
        
        # Определяем кварталы
        q1_r = monthly_df[monthly_df['month_num'].isin([1, 2, 3])]['total_r'].sum()
        q2_r = monthly_df[monthly_df['month_num'].isin([4, 5, 6])]['total_r'].sum()
        q3_r = monthly_df[monthly_df['month_num'].isin([7, 8, 9])]['total_r'].sum()
        q4_r = monthly_df[monthly_df['month_num'].isin([10, 11, 12])]['total_r'].sum()
        
        quarterly_stats = {
            'Q1': round(q1_r, 2),
            'Q2': round(q2_r, 2),
            'Q3': round(q3_r, 2),
            'Q4': round(q4_r, 2)
        }
        
        best_quarter = max(quarterly_stats, key=quarterly_stats.get)
        worst_quarter = min(quarterly_stats, key=quarterly_stats.get)
    else:
        best_month = None
        worst_month = None
        quarterly_stats = {'Q1': 0, 'Q2': 0, 'Q3': 0, 'Q4': 0}
        best_quarter = None
        worst_quarter = None
    
    return {
        'monthly_stats': monthly_stats,
        'monthly_df': monthly_df,
        'best_month': best_month,
        'worst_month': worst_month,
        'quarterly_stats': quarterly_stats,
        'best_quarter': best_quarter,
        'worst_quarter': worst_quarter
    }


def calculate_holding_times(df: pd.DataFrame) -> Dict:
    """
    Рассчитывает время удержания позиций
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь со статистикой времени удержания
    """
    df = df.copy()
    
    # Проверяем наличие необходимых колонок
    if 'entry_time' not in df.columns or 'exit_time' not in df.columns:
        return {
            'error': 'Отсутствуют колонки entry_time или exit_time',
            'tp_holding': {},
            'sl_holding': {},
            'be_holding': {}
        }
    
    # Конвертируем время в datetime для расчета разницы
    def calculate_duration(row):
        try:
            # Пробуем разные форматы времени
            if pd.isna(row['entry_time']) or pd.isna(row['exit_time']):
                return None
            
            # Создаем datetime объекты для расчета
            base_date = '2024-01-01'  # Используем фиктивную дату
            entry = pd.to_datetime(f"{base_date} {row['entry_time']}")
            exit = pd.to_datetime(f"{base_date} {row['exit_time']}")
            
            # Если выход раньше входа, предполагаем переход через полночь
            if exit < entry:
                exit += timedelta(days=1)
            
            duration = exit - entry
            return duration.total_seconds() / 60  # Возвращаем в минутах
        except:
            return None
    
    # Рассчитываем длительность для каждой сделки
    df['holding_minutes'] = df.apply(calculate_duration, axis=1)
    
    # Фильтруем только сделки с валидным временем
    valid_time = df[df['holding_minutes'].notna()].copy()
    
    # Группируем по результатам
    results = {}
    
    for result_type in ['TP', 'SL', 'BE']:
        type_data = valid_time[valid_time['result'] == result_type]['holding_minutes']
        
        if len(type_data) > 0:
            avg_minutes = type_data.mean()
            median_minutes = type_data.median()
            min_minutes = type_data.min()
            max_minutes = type_data.max()
            
            results[f'{result_type.lower()}_holding'] = {
                'count': len(type_data),
                'avg_minutes': round(avg_minutes, 1),
                'avg_formatted': format_duration(avg_minutes),
                'median_minutes': round(median_minutes, 1),
                'median_formatted': format_duration(median_minutes),
                'min_minutes': round(min_minutes, 1),
                'min_formatted': format_duration(min_minutes),
                'max_minutes': round(max_minutes, 1),
                'max_formatted': format_duration(max_minutes)
            }
        else:
            results[f'{result_type.lower()}_holding'] = {
                'count': 0,
                'avg_minutes': 0,
                'avg_formatted': '0ч 0мин',
                'median_minutes': 0,
                'median_formatted': '0ч 0мин',
                'min_minutes': 0,
                'min_formatted': '0ч 0мин',
                'max_minutes': 0,
                'max_formatted': '0ч 0мин'
            }
    
    # Сравнение скорости TP vs SL
    tp_median = results['tp_holding']['median_minutes']
    sl_median = results['sl_holding']['median_minutes']
    
    if tp_median > 0 and sl_median > 0:
        if tp_median < sl_median:
            faster_result = 'TP'
            speed_diff = sl_median - tp_median
        else:
            faster_result = 'SL'
            speed_diff = tp_median - sl_median
        
        results['speed_comparison'] = {
            'faster_result': faster_result,
            'speed_difference_minutes': round(speed_diff, 1),
            'speed_difference_formatted': format_duration(speed_diff),
            'tp_median': tp_median,
            'sl_median': sl_median
        }
    else:
        results['speed_comparison'] = {
            'faster_result': 'Недостаточно данных',
            'speed_difference_minutes': 0,
            'speed_difference_formatted': '0ч 0мин'
        }
    
    return results


def format_duration(minutes: float) -> str:
    """
    Форматирует длительность из минут в читаемый формат
    
    Args:
        minutes: количество минут
    
    Returns:
        Отформатированная строка (например, "2ч 15мин")
    """
    if pd.isna(minutes) or minutes < 0:
        return "0ч 0мин"
    
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    
    if hours > 0:
        return f"{hours}ч {mins}мин"
    else:
        return f"{mins}мин"


def analyze_entry_types(df: pd.DataFrame) -> Dict:
    """
    Анализирует эффективность по типам входов
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь с анализом по типам входов
    """
    entry_stats = []
    
    # Очищаем данные от NaN и приводим к строкам
    df_clean = df.copy()
    df_clean['entry_type'] = df_clean['entry_type'].fillna('Unknown').astype(str)
    
    # Получаем все уникальные типы входов
    entry_types = df_clean['entry_type'].unique()
    
    for entry_type in sorted(entry_types):
        type_data = df_clean[df_clean['entry_type'] == entry_type]
        
        # Подсчитываем результаты
        tp_count = len(type_data[type_data['result'] == 'TP'])
        sl_count = len(type_data[type_data['result'] == 'SL'])
        be_count = len(type_data[type_data['result'] == 'BE'])
        no_trade_count = len(type_data[type_data['result'] == 'NO_TRADE'])
        
        # Для расчета среднего R исключаем NO_TRADE
        executed = type_data[type_data['result'] != 'NO_TRADE']
        
        stats = {
            'entry_type': entry_type,
            'total_signals': len(type_data),
            'executed_trades': len(executed),
            'tp_count': tp_count,
            'sl_count': sl_count,
            'be_count': be_count,
            'no_trade_count': no_trade_count,
            'avg_r': round(executed['r_result'].mean(), 3) if len(executed) > 0 else 0,
            'total_r': round(executed['r_result'].sum(), 2) if len(executed) > 0 else 0,
            'win_rate': round(tp_count / len(executed) * 100, 1) if len(executed) > 0 else 0,
            'execution_rate': round(len(executed) / len(type_data) * 100, 1) if len(type_data) > 0 else 0
        }
        
        entry_stats.append(stats)
    
    # Создаем DataFrame
    entry_df = pd.DataFrame(entry_stats)
    
    # Находим лучший и худший тип входа по среднему R
    entry_df_executed = entry_df[entry_df['executed_trades'] > 0]
    
    if len(entry_df_executed) > 0:
        best_entry = entry_df_executed.loc[entry_df_executed['avg_r'].idxmax()].to_dict()
        worst_entry = entry_df_executed.loc[entry_df_executed['avg_r'].idxmin()].to_dict()
        most_profitable = entry_df_executed.loc[entry_df_executed['total_r'].idxmax()].to_dict()
    else:
        best_entry = None
        worst_entry = None
        most_profitable = None
    
    return {
        'entry_stats': entry_stats,
        'entry_df': entry_df,
        'best_entry_type': best_entry,
        'worst_entry_type': worst_entry,
        'most_profitable_type': most_profitable,
        'total_entry_types': len(entry_types)
    }


def analyze_directions(df: pd.DataFrame) -> Dict:
    """
    Анализирует эффективность по направлениям (Long/Short)
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь с анализом по направлениям
    """
    direction_stats = []
    
    # Очищаем данные от NaN и приводим к строкам
    df_clean = df.copy()
    df_clean['direction'] = df_clean['direction'].fillna('Unknown').astype(str)
    
    # Получаем уникальные направления
    directions = df_clean['direction'].unique()
    
    for direction in sorted(directions):
        dir_data = df_clean[df_clean['direction'] == direction]
        
        # Подсчитываем результаты
        tp_count = len(dir_data[dir_data['result'] == 'TP'])
        sl_count = len(dir_data[dir_data['result'] == 'SL'])
        be_count = len(dir_data[dir_data['result'] == 'BE'])
        no_trade_count = len(dir_data[dir_data['result'] == 'NO_TRADE'])
        
        # Для расчета среднего R исключаем NO_TRADE
        executed = dir_data[dir_data['result'] != 'NO_TRADE']
        
        stats = {
            'direction': direction,
            'total_signals': len(dir_data),
            'executed_trades': len(executed),
            'tp_count': tp_count,
            'sl_count': sl_count,
            'be_count': be_count,
            'no_trade_count': no_trade_count,
            'avg_r': round(executed['r_result'].mean(), 3) if len(executed) > 0 else 0,
            'total_r': round(executed['r_result'].sum(), 2) if len(executed) > 0 else 0,
            'win_rate': round(tp_count / len(executed) * 100, 1) if len(executed) > 0 else 0,
            'tp_percentage': round(tp_count / len(dir_data) * 100, 1) if len(dir_data) > 0 else 0,
            'sl_percentage': round(sl_count / len(dir_data) * 100, 1) if len(dir_data) > 0 else 0
        }
        
        direction_stats.append(stats)
    
    # Создаем DataFrame
    direction_df = pd.DataFrame(direction_stats)
    
    # Сравнение Long vs Short
    comparison = {}
    if 'Long' in directions and 'Short' in directions:
        long_stats = next((s for s in direction_stats if s['direction'] == 'Long'), None)
        short_stats = next((s for s in direction_stats if s['direction'] == 'Short'), None)
        
        if long_stats and short_stats:
            comparison = {
                'better_direction': 'Long' if long_stats['avg_r'] > short_stats['avg_r'] else 'Short',
                'avg_r_difference': round(abs(long_stats['avg_r'] - short_stats['avg_r']), 3),
                'win_rate_difference': round(abs(long_stats['win_rate'] - short_stats['win_rate']), 1),
                'total_r_difference': round(abs(long_stats['total_r'] - short_stats['total_r']), 2)
            }
    
    return {
        'direction_stats': direction_stats,
        'direction_df': direction_df,
        'comparison': comparison
    }


def analyze_temporal_patterns(df: pd.DataFrame) -> Dict:
    """
    Выполняет полный временной анализ
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь со всеми временными паттернами
    """
    results = {
        'hourly': analyze_by_hour(df),
        'weekday': analyze_by_weekday(df),
        'seasonality': analyze_seasonality(df),
        'holding_times': calculate_holding_times(df),
        'entry_types': analyze_entry_types(df),
        'directions': analyze_directions(df)
    }
    
    return results