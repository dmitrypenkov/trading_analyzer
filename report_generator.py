"""
Модуль генерации отчетов для Trading Analyzer v10.0
Создает годовые, месячные и дневные отчеты на основе результатов анализа
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple
from r_calculator import RCalculator
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Класс для генерации отчетов торговой системы.
    Подготавливает данные для отображения в Streamlit.
    """
    
    # Названия дней недели на русском
    WEEKDAYS_RU = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    
    def __init__(self, r_calculator: RCalculator):
        """
        Инициализация генератора отчетов.
        
        Args:
            r_calculator: Экземпляр RCalculator для R-расчетов
        """
        self.r_calculator = r_calculator
        logger.info("ReportGenerator инициализирован")
    
    def prepare_daily_trades(self, analysis_results: List[Dict], 
                           tp_coefficient: float = 0.9,
                           sl_slippage_coefficient: float = 1.0,
                           commission_rate: float = 0.0) -> pd.DataFrame:
        """
        Преобразует результаты анализа в DataFrame для отображения.
        
        Args:
            analysis_results: Список результатов анализа из analyzer
            tp_coefficient: Коэффициент для TP сделок
            sl_slippage_coefficient: Коэффициент проскальзывания для SL
            commission_rate: Ставка комиссии за сторону
        
        Returns:
            DataFrame с подготовленными данными для отображения
        """
        # Добавляем R-результаты
        trades_with_r = self.r_calculator.add_r_to_trades(
            analysis_results, tp_coefficient,
            sl_slippage_coefficient, commission_rate
        )
        
        # Создаем список строк для DataFrame
        rows = []
        for trade in trades_with_r:
            # Проверяем наличие даты
            if 'date' not in trade:
                continue
            
            # Преобразуем дату в объект datetime для работы
            trade_date = pd.to_datetime(trade['date'])
            
            row = {
                'date': trade_date.strftime('%Y-%m-%d'),
                'weekday': self._format_weekday(trade_date),
                'entry_type': trade.get('entry_type', ''),
                'range_size': trade.get('range_size', 0),
                'direction': self._extract_direction(trade.get('entry_type', '')),
                'entry_time': self._format_time(trade.get('entry_time')),
                'entry_price': trade.get('entry_price'),
                'exit_time': self._format_time(trade.get('exit_time')),
                'exit_price': trade.get('exit_price'),
                'result': trade.get('result', ''),
                'r_result': trade.get('r_result', 0.0),
                'close_reason': trade.get('close_reason', ''),
                'is_blocked': trade.get('close_reason') == 'news_filter_blocked',
                'tp_points': trade.get('tp_size', 0),
                'sl_points': trade.get('sl_size', 0)
            }
            
            rows.append(row)
        
        # Создаем DataFrame
        df = pd.DataFrame(rows)
        
        # Сортируем по дате
        if not df.empty:
            df['date_sort'] = pd.to_datetime(df['date'])
            df = df.sort_values('date_sort').drop('date_sort', axis=1)
        
        return df
    
    def generate_monthly_report(self, year: int, month: int, 
                              daily_trades_df: pd.DataFrame) -> Dict:
        """
        Генерирует отчет за конкретный месяц.
        
        Args:
            year: Год
            month: Месяц (1-12)
            daily_trades_df: DataFrame с дневными сделками
        
        Returns:
            Словарь с месячным отчетом
        """
        # Фильтруем данные по году и месяцу
        month_str = f"{year:04d}-{month:02d}"
        month_df = daily_trades_df[daily_trades_df['date'].str.startswith(month_str)].copy()
        
        # Базовая структура отчета
        report = {
            'month': month_str,
            'trading_days': len(month_df),
            'total_signals': len(month_df),
            'executed_trades': 0,
            'blocked_by_news': 0,
            'no_signals': 0,
            'total_r': 0.0,
            'average_r_per_day': 0.0,
            'average_r_per_trade': 0.0,
            'tp_count': 0,
            'sl_count': 0,
            'be_count': 0,
            'win_rate': 0.0,
            'best_day_r': 0.0,
            'worst_day_r': 0.0,
            'daily_trades': month_df
        }
        
        if month_df.empty:
            return report
        
        # Считаем статистику
        report['blocked_by_news'] = len(month_df[month_df['is_blocked'] == True])
        report['no_signals'] = len(month_df[month_df['entry_type'].isin(['INSIDE_BLOCK', 'OUTSIDE_BLOCK'])])
        
        # Фильтруем исполненные сделки
        executed_df = month_df[month_df['result'].isin(['TP', 'SL', 'BE'])]
        report['executed_trades'] = len(executed_df)
        
        if not executed_df.empty:
            # Считаем результаты
            report['tp_count'] = len(executed_df[executed_df['result'] == 'TP'])
            report['sl_count'] = len(executed_df[executed_df['result'] == 'SL'])
            report['be_count'] = len(executed_df[executed_df['result'] == 'BE'])
            
            # R-статистика
            report['total_r'] = round(executed_df['r_result'].sum(), 2)
            report['average_r_per_trade'] = round(report['total_r'] / report['executed_trades'], 2)
            report['best_day_r'] = round(executed_df['r_result'].max(), 2)
            report['worst_day_r'] = round(executed_df['r_result'].min(), 2)
            
            # Win rate
            report['win_rate'] = round(report['tp_count'] / report['executed_trades'] * 100, 1)
        
        # Средний R на день
        if report['trading_days'] > 0:
            report['average_r_per_day'] = round(report['total_r'] / report['trading_days'], 2)
        
        return report
    
    def generate_yearly_report(self, year: int, daily_trades_df: pd.DataFrame) -> Dict:
        """
        Генерирует годовой отчет.
        
        Args:
            year: Год
            daily_trades_df: DataFrame с дневными сделками
        
        Returns:
            Словарь с годовым отчетом
        """
        # Генерируем отчеты для всех 12 месяцев
        months_data = []
        for month in range(1, 13):
            month_report = self.generate_monthly_report(year, month, daily_trades_df)
            # Удаляем DataFrame из месячного отчета для годового
            month_summary = month_report.copy()
            month_summary.pop('daily_trades', None)
            months_data.append(month_summary)
        
        # Фильтруем данные за год
        year_str = f"{year:04d}"
        year_df = daily_trades_df[daily_trades_df['date'].str.startswith(year_str)]
        
        # Базовая структура отчета
        report = {
            'year': year,
            'months_data': months_data,
            'total_trading_days': len(year_df),
            'total_signals': len(year_df),
            'executed_trades': 0,
            'blocked_by_news': 0,
            'total_r': 0.0,
            'average_r_per_month': 0.0,
            'average_r_per_trade': 0.0,
            'tp_count': 0,
            'sl_count': 0,
            'be_count': 0,
            'win_rate': 0.0,
            'best_month': '',
            'best_month_r': -999.0,
            'worst_month': '',
            'worst_month_r': 999.0,
            'cumulative_r_series': []
        }
        
        if year_df.empty:
            return report
        
        # Считаем годовую статистику
        report['blocked_by_news'] = len(year_df[year_df['is_blocked'] == True])
        
        # Исполненные сделки
        executed_df = year_df[year_df['result'].isin(['TP', 'SL', 'BE'])]
        report['executed_trades'] = len(executed_df)
        
        if not executed_df.empty:
            report['tp_count'] = len(executed_df[executed_df['result'] == 'TP'])
            report['sl_count'] = len(executed_df[executed_df['result'] == 'SL'])
            report['be_count'] = len(executed_df[executed_df['result'] == 'BE'])
            report['total_r'] = round(executed_df['r_result'].sum(), 2)
            report['average_r_per_trade'] = round(report['total_r'] / report['executed_trades'], 2)
            report['win_rate'] = round(report['tp_count'] / report['executed_trades'] * 100, 1)
        
        # Находим лучший и худший месяц
        for month_data in months_data:
            if month_data['trading_days'] > 0:
                if month_data['total_r'] > report['best_month_r']:
                    report['best_month'] = month_data['month']
                    report['best_month_r'] = month_data['total_r']
                if month_data['total_r'] < report['worst_month_r']:
                    report['worst_month'] = month_data['month']
                    report['worst_month_r'] = month_data['total_r']
        
        # Средний R на месяц
        months_with_trades = sum(1 for m in months_data if m['trading_days'] > 0)
        if months_with_trades > 0:
            report['average_r_per_month'] = round(report['total_r'] / months_with_trades, 2)
        
        # Накопительный R по месяцам
        report['cumulative_r_series'] = self._calculate_monthly_cumulative_r(months_data)
        
        return report
    def generate_summary_report(self, daily_trades_df: pd.DataFrame) -> Dict:
        """
        Генерирует общий отчет за весь период.
        
        Args:
            daily_trades_df: DataFrame с дневными сделками
        
        Returns:
            Словарь с общим отчетом
        """
        if daily_trades_df.empty:
            return {
                'period_start': '',
                'period_end': '',
                'total_years': 0,
                'yearly_reports': [],
                'total_trading_days': 0,
                'total_executed_trades': 0,
                'total_r': 0.0,
                'average_r_per_year': 0.0,
                'average_r_per_month': 0.0,
                'average_r_per_trade': 0.0,
                'best_year': None,
                'best_year_r': 0.0,
                'worst_year': None,
                'worst_year_r': 0.0,
                'entry_type_statistics': {},
                'cumulative_r_series': [],
                'dates_series': [],
                'total_tp': 0,  # Добавлено для правильного подсчета win_rate
                'total_sl': 0,
                'total_be': 0,
                'max_drawdown': {
                    'max_drawdown': 0.0, 'max_drawdown_abs': 0.0,
                    'peak_index': 0, 'trough_index': 0,
                    'peak_value': 0.0, 'trough_value': 0.0,
                    'recovery_index': None
                }
            }
        
        # Определяем период
        daily_trades_df['date_obj'] = pd.to_datetime(daily_trades_df['date'])
        period_start = daily_trades_df['date_obj'].min()
        period_end = daily_trades_df['date_obj'].max()
        
        # Генерируем годовые отчеты
        years = sorted(daily_trades_df['date_obj'].dt.year.unique())
        yearly_reports = []
        for year in years:
            yearly_reports.append(self.generate_yearly_report(year, daily_trades_df))
        
        # Общая статистика
        executed_df = daily_trades_df[daily_trades_df['result'].isin(['TP', 'SL', 'BE'])]
        total_executed = len(executed_df)
        total_r = executed_df['r_result'].sum() if not executed_df.empty else 0.0
        
        # Подсчет TP, SL, BE для правильного win_rate
        total_tp = len(executed_df[executed_df['result'] == 'TP'])
        total_sl = len(executed_df[executed_df['result'] == 'SL'])
        total_be = len(executed_df[executed_df['result'] == 'BE'])
        
        # Находим лучший и худший год
        best_year = None
        best_year_r = -999.0
        worst_year = None
        worst_year_r = 999.0
        
        for year_report in yearly_reports:
            if year_report['total_trading_days'] > 0:
                if year_report['total_r'] > best_year_r:
                    best_year = year_report['year']
                    best_year_r = year_report['total_r']
                if year_report['total_r'] < worst_year_r:
                    worst_year = year_report['year']
                    worst_year_r = year_report['total_r']
        
        # Подготавливаем данные для r_calculator
        trades_list = daily_trades_df.to_dict('records')
        
        # Статистика по типам входов
        entry_type_statistics = self.r_calculator.calculate_entry_type_statistics(trades_list)
        
        # Накопительный R и даты для графика
        if not executed_df.empty:
            executed_trades_sorted = executed_df.sort_values('date_obj')
            cumulative_r_series = executed_trades_sorted['r_result'].cumsum().round(2).tolist()
            dates_series = executed_trades_sorted['date'].tolist()
        else:
            cumulative_r_series = []
            dates_series = []
        
        # Расчет Max Drawdown
        drawdown_info = self.r_calculator.calculate_max_drawdown(cumulative_r_series)
        
        # Расчет правильного количества лет в периоде
        years_diff = (period_end - period_start).days / 365.25
        
        report = {
            'period_start': period_start.strftime('%Y-%m-%d'),
            'period_end': period_end.strftime('%Y-%m-%d'),
            'total_years': round(years_diff, 1),  # Более точный расчет периода
            'yearly_reports': yearly_reports,
            'total_trading_days': len(daily_trades_df),
            'total_executed_trades': total_executed,
            'total_r': round(total_r, 2),
            'average_r_per_year': round(total_r / len(years), 2) if years else 0.0,
            'average_r_per_month': round(total_r / ((period_end - period_start).days / 30), 2),
            'average_r_per_trade': round(total_r / total_executed, 2) if total_executed > 0 else 0.0,
            'best_year': best_year,
            'best_year_r': round(best_year_r, 2) if best_year else 0.0,
            'worst_year': worst_year,
            'worst_year_r': round(worst_year_r, 2) if worst_year else 0.0,
            'entry_type_statistics': entry_type_statistics,
            'cumulative_r_series': cumulative_r_series,
            'dates_series': dates_series,
            'total_tp': total_tp,  # Добавлено для использования в app.py
            'total_sl': total_sl,
            'total_be': total_be,
            'max_drawdown': drawdown_info  # Max Drawdown информация
        }
        
        return report
    
    
    def filter_trades(self, daily_trades_df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
        """
        Универсальный метод фильтрации сделок.
        
        Args:
            daily_trades_df: DataFrame с дневными сделками
            filters: Словарь с параметрами фильтрации
        
        Returns:
            Отфильтрованный DataFrame
        """
        filtered_df = daily_trades_df.copy()
        
        # Фильтр по результатам
        if 'results' in filters and filters['results']:
            filtered_df = filtered_df[filtered_df['result'].isin(filters['results'])]
        
        # Фильтр по типам входов
        if 'entry_types' in filters and filters['entry_types']:
            filtered_df = filtered_df[filtered_df['entry_type'].isin(filters['entry_types'])]
        
        # Фильтр по R-диапазону
        if 'r_range' in filters and filters['r_range']:
            min_r, max_r = filters['r_range']
            filtered_df = filtered_df[
                (filtered_df['r_result'] >= min_r) & 
                (filtered_df['r_result'] <= max_r)
            ]
        
        # Фильтр по дням недели
        if 'weekdays' in filters and filters['weekdays']:
            weekday_names = [self.WEEKDAYS_RU[i] for i in filters['weekdays']]
            filtered_df = filtered_df[filtered_df['weekday'].isin(weekday_names)]
        
        # Фильтр по диапазону дат
        if 'date_range' in filters and filters['date_range']:
            start_date, end_date = filters['date_range']
            filtered_df = filtered_df[
                (filtered_df['date'] >= start_date) & 
                (filtered_df['date'] <= end_date)
            ]
        
        # Фильтр блокированных новостями
        if 'show_blocked' in filters and not filters['show_blocked']:
            filtered_df = filtered_df[filtered_df['is_blocked'] == False]
        
        return filtered_df
    
    def export_to_dict(self, report: Dict, format: str = 'full') -> Dict:
        """
        Подготавливает отчет для экспорта.
        
        Args:
            report: Отчет для экспорта
            format: 'full' или 'summary'
        
        Returns:
            Словарь, готовый для JSON-сериализации
        """
        export_dict = report.copy()
        
        # Удаляем DataFrame объекты
        if 'daily_trades' in export_dict:
            if isinstance(export_dict['daily_trades'], pd.DataFrame):
                export_dict['daily_trades'] = export_dict['daily_trades'].to_dict('records')
        
        # Рекурсивно обрабатываем вложенные отчеты
        if 'yearly_reports' in export_dict:
            for i, year_report in enumerate(export_dict['yearly_reports']):
                export_dict['yearly_reports'][i] = self.export_to_dict(year_report, format)
        
        if 'months_data' in export_dict:
            for i, month_data in enumerate(export_dict['months_data']):
                if isinstance(month_data, dict):
                    export_dict['months_data'][i] = self.export_to_dict(month_data, format)
        
        # Для summary формата удаляем детальные данные
        if format == 'summary':
            keys_to_remove = ['daily_trades', 'cumulative_r_series', 'dates_series']
            for key in keys_to_remove:
                export_dict.pop(key, None)
        
        return export_dict
    
    def _extract_direction(self, entry_type: str) -> str:
        """
        Извлекает направление из типа входа.
        
        Args:
            entry_type: Тип входа
        
        Returns:
            'Long', 'Short' или 'N/A'
        """
        if 'LONG' in entry_type:
            return 'Long'
        elif 'SHORT' in entry_type:
            return 'Short'
        else:
            return 'N/A'
    
    def _format_weekday(self, date: pd.Timestamp) -> str:
        """
        Форматирует день недели на русском.
        
        Args:
            date: Дата
        
        Returns:
            День недели на русском
        """
        return self.WEEKDAYS_RU[date.weekday()]
    
    def _format_time(self, time_obj: Optional[datetime]) -> str:
        """
        Форматирует время для отображения.
        
        Args:
            time_obj: Объект datetime или None
        
        Returns:
            Отформатированное время или пустая строка
        """
        if time_obj is None:
            return ''
        
        if isinstance(time_obj, str):
            try:
                time_obj = pd.to_datetime(time_obj)
            except:
                return ''
        
        if hasattr(time_obj, 'strftime'):
            return time_obj.strftime('%H:%M')
        
        return ''
    
    def _calculate_monthly_cumulative_r(self, monthly_data: List[Dict]) -> List[float]:
        """
        Рассчитывает накопительный R по месяцам.
        
        Args:
            monthly_data: Список месячных отчетов
        
        Returns:
            Список накопительных значений R
        """
        cumulative_r = []
        current_sum = 0.0
        
        for month in monthly_data:
            current_sum += month.get('total_r', 0.0)
            cumulative_r.append(round(current_sum, 2))
        
        return cumulative_r