"""
Модуль анализа серий сделок
Подсчет последовательных TP/SL с учетом режима игнорирования BE/NO_TRADE
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from collections import Counter


def find_consecutive_series(df: pd.DataFrame, result_type: str, 
                           ignore_be_no_trade: bool = False) -> List[int]:
    """
    Находит все серии подряд идущих результатов определенного типа
    
    Args:
        df: DataFrame с торговыми данными
        result_type: тип результата ('TP' или 'SL')
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE в сериях
    
    Returns:
        Список длин всех найденных серий
    """
    if len(df) == 0:
        return []
    
    # Сортируем по дате и времени
    df_sorted = df.sort_values(['date', 'entry_time'])
    results = df_sorted['result'].tolist()
    
    if ignore_be_no_trade:
        # Фильтруем, оставляя только TP и SL
        filtered_results = []
        for r in results:
            if r in ['TP', 'SL']:
                filtered_results.append(r)
        results = filtered_results
    
    if not results:
        return []
    
    # Подсчет серий
    series_lengths = []
    current_series = 0
    
    for result in results:
        if result == result_type:
            current_series += 1
        else:
            if ignore_be_no_trade and result not in ['TP', 'SL']:
                # BE или NO_TRADE - не прерываем серию
                continue
            else:
                # Другой значимый результат - сохраняем серию и сбрасываем
                if current_series > 0:
                    series_lengths.append(current_series)
                    current_series = 0
    
    # Добавляем последнюю серию
    if current_series > 0:
        series_lengths.append(current_series)
    
    return series_lengths


def count_series_distribution(series_lengths: List[int], max_length: int = 10) -> Dict[int, int]:
    """
    Создает распределение серий по их длинам
    
    Args:
        series_lengths: список длин серий
        max_length: максимальная длина для отображения
    
    Returns:
        Словарь {длина_серии: количество_раз}
    """
    # Инициализируем счетчики для всех длин
    distribution = {i: 0 for i in range(1, max_length + 1)}
    
    # Подсчитываем серии
    series_counter = Counter(series_lengths)
    
    for length, count in series_counter.items():
        if length <= max_length:
            distribution[length] = count
        else:
            # Серии длиннее max_length группируем
            if max_length + 1 not in distribution:
                distribution[max_length + 1] = 0
            distribution[max_length + 1] += count
    
    return distribution


def format_series_distribution(distribution: Dict[int, int], result_type: str, 
                              max_display: int = 10) -> str:
    """
    Форматирует распределение серий для отображения
    
    Args:
        distribution: словарь с распределением
        result_type: тип результата ('TP' или 'SL')
        max_display: максимальная длина для отображения
    
    Returns:
        Отформатированная строка
    """
    lines = []
    
    # Отображаем от максимальной длины к минимальной
    for length in range(max_display, 0, -1):
        count = distribution.get(length, 0)
        
        # Формируем строку с правильным склонением
        if count == 0:
            count_str = "0 раз"
        elif count == 1:
            count_str = "1 раз"
        elif 2 <= count <= 4:
            count_str = f"{count} раза"
        else:
            count_str = f"{count} раз"
        
        # Добавляем визуальную индикацию для ненулевых значений
        if count > 0:
            bar = '█' * min(count, 20)  # Ограничиваем длину бара
            line = f"{length:2d} {result_type} подряд: {count_str:10s} {bar}"
        else:
            line = f"{length:2d} {result_type} подряд: {count_str:10s}"
        
        lines.append(line)
    
    # Проверяем серии длиннее max_display
    if max_display + 1 in distribution and distribution[max_display + 1] > 0:
        count = distribution[max_display + 1]
        count_str = f"{count} раз" if count != 1 else "1 раз"
        lines.insert(0, f">{max_display} {result_type} подряд: {count_str}")
    
    return '\n'.join(lines)


def analyze_series(df: pd.DataFrame, ignore_be_no_trade: bool = False) -> Dict:
    """
    Выполняет полный анализ серий TP/SL
    
    Args:
        df: DataFrame с торговыми данными
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE
    
    Returns:
        Словарь с результатами анализа серий
    """
    # Находим все серии TP и SL
    tp_series = find_consecutive_series(df, 'TP', ignore_be_no_trade)
    sl_series = find_consecutive_series(df, 'SL', ignore_be_no_trade)
    
    # Создаем распределения
    tp_distribution = count_series_distribution(tp_series)
    sl_distribution = count_series_distribution(sl_series)
    
    results = {
        # Серии TP
        'tp_series_found': len(tp_series),
        'tp_max_series': max(tp_series) if tp_series else 0,
        'tp_avg_series': np.mean(tp_series) if tp_series else 0,
        'tp_distribution': tp_distribution,
        'tp_distribution_text': format_series_distribution(tp_distribution, 'TP'),
        
        # Серии SL
        'sl_series_found': len(sl_series),
        'sl_max_series': max(sl_series) if sl_series else 0,
        'sl_avg_series': np.mean(sl_series) if sl_series else 0,
        'sl_distribution': sl_distribution,
        'sl_distribution_text': format_series_distribution(sl_distribution, 'SL'),
        
        # Общая информация
        'mode': 'ignore_be_no_trade' if ignore_be_no_trade else 'count_all',
        'total_records': len(df)
    }
    
    return results


def analyze_series_by_period(df: pd.DataFrame, ignore_be_no_trade: bool = False) -> Dict:
    """
    Анализирует серии по различным периодам (год, месяц)
    
    Args:
        df: DataFrame с торговыми данными
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE
    
    Returns:
        Словарь с анализом по периодам
    """
    df = df.copy()
    df['date_dt'] = pd.to_datetime(df['date'])
    df['year'] = df['date_dt'].dt.year
    df['month'] = df['date_dt'].dt.to_period('M')
    
    results = {
        'total': analyze_series(df, ignore_be_no_trade),
        'by_year': {},
        'by_month': {}
    }
    
    # Анализ по годам
    for year in sorted(df['year'].unique()):
        year_df = df[df['year'] == year]
        results['by_year'][year] = analyze_series(year_df, ignore_be_no_trade)
    
    # Анализ по месяцам
    for month in sorted(df['month'].unique()):
        month_df = df[df['month'] == month]
        month_str = str(month)
        results['by_month'][month_str] = analyze_series(month_df, ignore_be_no_trade)
    
    return results


def get_series_extremes(df: pd.DataFrame, ignore_be_no_trade: bool = False) -> Dict:
    """
    Находит экстремальные серии и их даты
    
    Args:
        df: DataFrame с торговыми данными
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE
    
    Returns:
        Словарь с информацией об экстремальных сериях
    """
    df_sorted = df.sort_values(['date', 'entry_time']).copy()
    
    # Находим позиции максимальных серий
    tp_series_info = find_series_with_positions(df_sorted, 'TP', ignore_be_no_trade)
    sl_series_info = find_series_with_positions(df_sorted, 'SL', ignore_be_no_trade)
    
    # Находим максимальные серии
    max_tp = max(tp_series_info, key=lambda x: x['length']) if tp_series_info else None
    max_sl = max(sl_series_info, key=lambda x: x['length']) if sl_series_info else None
    
    results = {
        'max_tp_series': {
            'length': max_tp['length'] if max_tp else 0,
            'start_date': max_tp['start_date'] if max_tp else None,
            'end_date': max_tp['end_date'] if max_tp else None,
            'trades': max_tp['trades'] if max_tp else []
        },
        'max_sl_series': {
            'length': max_sl['length'] if max_sl else 0,
            'start_date': max_sl['start_date'] if max_sl else None,
            'end_date': max_sl['end_date'] if max_sl else None,
            'trades': max_sl['trades'] if max_sl else []
        },
        'all_tp_series': tp_series_info,
        'all_sl_series': sl_series_info
    }
    
    return results


def find_series_with_positions(df: pd.DataFrame, result_type: str, 
                              ignore_be_no_trade: bool = False) -> List[Dict]:
    """
    Находит серии с информацией о позициях в данных
    
    Args:
        df: DataFrame с торговыми данными
        result_type: тип результата ('TP' или 'SL')
        ignore_be_no_trade: игнорировать ли BE/NO_TRADE
    
    Returns:
        Список словарей с информацией о сериях
    """
    series_info = []
    current_series = []
    
    for idx, row in df.iterrows():
        result = row['result']
        
        if result == result_type:
            current_series.append({
                'date': row['date'],
                'entry_time': row.get('entry_time', ''),
                'r_result': row.get('r_result', 0)
            })
        else:
            if ignore_be_no_trade and result not in ['TP', 'SL']:
                # BE или NO_TRADE - не прерываем серию
                continue
            else:
                # Сохраняем серию если она есть
                if current_series:
                    series_info.append({
                        'length': len(current_series),
                        'start_date': current_series[0]['date'],
                        'end_date': current_series[-1]['date'],
                        'total_r': sum(t['r_result'] for t in current_series),
                        'trades': current_series
                    })
                    current_series = []
    
    # Добавляем последнюю серию
    if current_series:
        series_info.append({
            'length': len(current_series),
            'start_date': current_series[0]['date'],
            'end_date': current_series[-1]['date'],
            'total_r': sum(t['r_result'] for t in current_series),
            'trades': current_series
        })
    
    return series_info


def compare_series_modes(df: pd.DataFrame) -> Dict:
    """
    Сравнивает результаты анализа серий в разных режимах
    
    Args:
        df: DataFrame с торговыми данными
    
    Returns:
        Словарь со сравнением режимов
    """
    # Анализ с учетом BE/NO_TRADE
    with_be = analyze_series(df, ignore_be_no_trade=False)
    
    # Анализ без учета BE/NO_TRADE
    without_be = analyze_series(df, ignore_be_no_trade=True)
    
    comparison = {
        'with_be_no_trade': {
            'max_tp': with_be['tp_max_series'],
            'max_sl': with_be['sl_max_series'],
            'avg_tp': round(with_be['tp_avg_series'], 2),
            'avg_sl': round(with_be['sl_avg_series'], 2)
        },
        'ignore_be_no_trade': {
            'max_tp': without_be['tp_max_series'],
            'max_sl': without_be['sl_max_series'],
            'avg_tp': round(without_be['tp_avg_series'], 2),
            'avg_sl': round(without_be['sl_avg_series'], 2)
        },
        'difference': {
            'max_tp_diff': without_be['tp_max_series'] - with_be['tp_max_series'],
            'max_sl_diff': without_be['sl_max_series'] - with_be['sl_max_series'],
            'avg_tp_diff': round(without_be['tp_avg_series'] - with_be['tp_avg_series'], 2),
            'avg_sl_diff': round(without_be['sl_avg_series'] - with_be['sl_avg_series'], 2)
        }
    }
    
    return comparison


def create_series_summary_table(analysis_results: Dict) -> pd.DataFrame:
    """
    Создает сводную таблицу по сериям для экспорта
    
    Args:
        analysis_results: результаты анализа серий
    
    Returns:
        DataFrame со сводной таблицей
    """
    summary_data = []
    
    # Общие данные
    total = analysis_results.get('total', {})
    summary_data.append({
        'Период': 'Весь период',
        'Max TP подряд': total.get('tp_max_series', 0),
        'Max SL подряд': total.get('sl_max_series', 0),
        'Средняя серия TP': round(total.get('tp_avg_series', 0), 2),
        'Средняя серия SL': round(total.get('sl_avg_series', 0), 2),
        'Всего серий TP': total.get('tp_series_found', 0),
        'Всего серий SL': total.get('sl_series_found', 0)
    })
    
    # Данные по годам
    for year, data in analysis_results.get('by_year', {}).items():
        summary_data.append({
            'Период': f'{year} год',
            'Max TP подряд': data.get('tp_max_series', 0),
            'Max SL подряд': data.get('sl_max_series', 0),
            'Средняя серия TP': round(data.get('tp_avg_series', 0), 2),
            'Средняя серия SL': round(data.get('sl_avg_series', 0), 2),
            'Всего серий TP': data.get('tp_series_found', 0),
            'Всего серий SL': data.get('sl_series_found', 0)
        })
    
    return pd.DataFrame(summary_data)