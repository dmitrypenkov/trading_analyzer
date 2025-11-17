"""
Модуль анализа ATR (Average True Range) для поиска оптимальных временных окон
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time, date
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ATRAnalyzer:
    """Класс для анализа ATR и поиска оптимальных временных окон"""
    
    def __init__(self, data_processor):
        """
        Инициализация анализатора
        
        Args:
            data_processor: Экземпляр DataProcessor с загруженными данными
        """
        self.data_processor = data_processor
        self.cache = {}
        logger.info("ATRAnalyzer инициализирован")
    
    def calculate_atr(self, candles: pd.DataFrame, period: Optional[int] = 14) -> float:
        """
        Расчет классического ATR (Average True Range)
        
        Args:
            candles: DataFrame со свечами (требуются колонки: high, low, close)
            period: Период для расчета среднего. Если None, используются все данные
            
        Returns:
            Значение ATR или NaN если недостаточно данных
        """
        if len(candles) < 2:
            return np.nan
        
        # Расчет True Range для каждой свечи
        tr_values = []
        for i in range(1, len(candles)):
            high = candles.iloc[i]['high']
            low = candles.iloc[i]['low']
            prev_close = candles.iloc[i-1]['close']
            
            # True Range = max из трех значений
            tr = max(
                high - low,                    # Размер текущей свечи
                abs(high - prev_close),         # Гэп вверх
                abs(low - prev_close)          # Гэп вниз
            )
            tr_values.append(tr)
        
        if len(tr_values) == 0:
            return np.nan
        
        # Если period is None, берем среднее по всем значениям
        if period is None:
            return np.mean(tr_values)
        
        # Берем последние period значений и считаем среднее
        if len(tr_values) >= period:
            return np.mean(tr_values[-period:])
        else:
            # Если данных меньше периода, берем среднее по всем
            return np.mean(tr_values)
    
    def analyze_window(self, start_time: time, end_time: time,
                      start_date: date, end_date: date,
                      atr_period: int = 14) -> Dict:
        """
        Анализ ATR для временного окна за указанный период
        
        Args:
            start_time: Время начала окна
            end_time: Время конца окна
            start_date: Начальная дата анализа
            end_date: Конечная дата анализа
            atr_period: Период для расчета ATR
            
        Returns:
            Словарь со статистикой по окну
        """
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        atr_values = []
        
        for current_date in dates:
            # Получаем данные для окна в этот день
            window_data = self._get_window_data(current_date.date(), start_time, end_time)
            
            if len(window_data) > 0:
                atr = self.calculate_atr(window_data, atr_period)
                if not np.isnan(atr):
                    atr_values.append(atr)
        
        # Проверяем, достаточно ли данных
        if len(atr_values) < 10:  # Минимум 10 дней для статистики
            return {'valid': False}
        
        atr_array = np.array(atr_values)
        mean_atr = np.mean(atr_array)
        std_atr = np.std(atr_array)
        
        # Коэффициент вариации (CV) - мера относительной изменчивости
        cv = std_atr / mean_atr if mean_atr > 0 else 999
        
        return {
            'valid': True,
            'avg_atr': mean_atr,
            'std_atr': std_atr,
            'cv': cv,
            'stability': 1 - cv if cv < 1 else 0,  # Стабильность от 0 до 1
            'min_atr': np.min(atr_array),
            'max_atr': np.max(atr_array),
            'percentile_25': np.percentile(atr_array, 25),
            'percentile_75': np.percentile(atr_array, 75),
            'days_count': len(atr_values),
            'atr_values': atr_values  # Сохраняем для визуализации
        }
    
    def find_optimal_windows(self, min_atr: float, max_atr: float,
                           stability_threshold: float,
                           start_date: date, end_date: date,
                           window_size_candles: int = 12,
                           step_candles: int = 4,
                           atr_period: int = 14,
                           progress_callback=None) -> List[Dict]:
        """
        Поиск временных окон с ATR в заданных границах и высокой стабильностью
        
        Args:
            min_atr: Минимальный допустимый ATR
            max_atr: Максимальный допустимый ATR
            stability_threshold: Минимальная стабильность (1 - CV)
            start_date: Начальная дата анализа
            end_date: Конечная дата анализа
            window_size_candles: Размер окна в свечах (1 свеча = 15 минут)
            step_candles: Шаг смещения окна в свечах
            atr_period: Период для расчета ATR
            progress_callback: Функция для отображения прогресса
            
        Returns:
            Список окон, отсортированных по стабильности
        """
        results = []
        
        # Преобразуем размер окна в минуты
        window_minutes = window_size_candles * 15
        window_hours = window_minutes / 60
        
        # Количество позиций для проверки (24 часа / шаг)
        total_positions = (24 * 60) // (step_candles * 15)
        
        current_position = 0
        
        # Перебираем все возможные начальные позиции с заданным шагом
        for start_candle_offset in range(0, 96, step_candles):  # 96 = количество 15-минутных свечей в сутках
            current_position += 1
            
            # Конвертируем смещение в время
            start_minutes = start_candle_offset * 15
            start_time = time(start_minutes // 60, start_minutes % 60)
            
            # Вычисляем время окончания
            end_minutes = (start_minutes + window_minutes) % (24 * 60)
            end_time = time(end_minutes // 60, end_minutes % 60)
            
            # Обновляем прогресс
            if progress_callback:
                progress = current_position / total_positions
                progress_callback(progress, f"Анализ окна {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}")
            
            # Анализируем окно
            stats = self.analyze_window(start_time, end_time, start_date, end_date, atr_period)
            
            if not stats['valid']:
                continue
            
            # Проверяем критерии
            avg_atr = stats['avg_atr']
            stability = stats['stability']
            
            if (min_atr <= avg_atr <= max_atr and stability >= stability_threshold):
                results.append({
                    'start': start_time.strftime('%H:%M'),
                    'end': end_time.strftime('%H:%M'),
                    'window_candles': window_size_candles,
                    'duration_hours': window_hours,
                    'duration_str': self._format_duration(window_minutes),
                    'avg_atr': round(avg_atr, 2),
                    'stability': round(stability, 3),
                    'cv': round(stats['cv'], 3),
                    'min_atr': round(stats['min_atr'], 2),
                    'max_atr': round(stats['max_atr'], 2),
                    'range_25_75': f"{round(stats['percentile_25'], 1)}-{round(stats['percentile_75'], 1)}",
                    'days_analyzed': stats['days_count']
                })
        
        # Сортируем по стабильности (от лучшей к худшей)
        results.sort(key=lambda x: x['stability'], reverse=True)
        
        # Возвращаем топ-20 результатов
        return results[:20]
    
    def _get_window_data(self, current_date: date, start_time: time, end_time: time) -> pd.DataFrame:
        """
        Получение данных для временного окна в конкретный день
        
        Args:
            current_date: Дата
            start_time: Время начала окна
            end_time: Время конца окна
            
        Returns:
            DataFrame со свечами в указанном окне
        """
        start_dt = datetime.combine(current_date, start_time)
        end_dt = datetime.combine(current_date, end_time)
        
        # Обработка перехода через полночь
        if end_time <= start_time:
            end_dt += timedelta(days=1)
        
        # Фильтруем данные по времени
        mask = (
            (self.data_processor.price_data['timestamp'] >= start_dt) & 
            (self.data_processor.price_data['timestamp'] <= end_dt)
        )
        
        return self.data_processor.price_data[mask]
    
    def _format_duration(self, minutes: int) -> str:
        """
        Форматирование длительности в читаемый вид
        
        Args:
            minutes: Количество минут
            
        Returns:
            Строка вида "2ч 30м" или "45м"
        """
        hours = minutes // 60
        mins = minutes % 60
        
        if hours > 0:
            if mins > 0:
                return f"{hours}ч {mins}м"
            else:
                return f"{hours}ч"
        else:
            return f"{mins}м"
    
    def create_heatmap_data(self, start_date: date, end_date: date,
                           atr_period: int = 14) -> pd.DataFrame:
        """
        Создание данных для тепловой карты волатильности
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            atr_period: Период для расчета ATR
            
        Returns:
            DataFrame для построения heatmap
        """
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        hours = range(0, 24)
        
        heatmap_data = []
        
        for current_date in dates:
            for hour in hours:
                # Анализируем каждый час
                start_time = time(hour, 0)
                end_time = time((hour + 1) % 24, 0)
                
                window_data = self._get_window_data(current_date.date(), start_time, end_time)
                
                if len(window_data) > 1:
                    # Для часового окна используем все свечи (обычно 4 свечи по 15 мин)
                    atr = self.calculate_atr(window_data, period=None)
                    
                    if not np.isnan(atr):
                        heatmap_data.append({
                            'date': current_date.strftime('%Y-%m-%d'),
                            'hour': hour,
                            'hour_str': f"{hour:02d}:00",
                            'atr': round(atr, 2),
                            'weekday': current_date.strftime('%A')
                        })
        
        if heatmap_data:
            return pd.DataFrame(heatmap_data)
        else:
            return pd.DataFrame()
    
    def get_statistics_summary(self, start_date: date, end_date: date) -> Dict:
        """
        Получение общей статистики по данным
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            
        Returns:
            Словарь со статистикой
        """
        # Добавляем колонку date если её нет
        if 'date' not in self.data_processor.price_data.columns:
            self.data_processor.price_data['date'] = pd.to_datetime(
                self.data_processor.price_data['timestamp']
            ).dt.date
        
        # Фильтруем данные по датам
        mask = (
            (self.data_processor.price_data['date'] >= start_date) &
            (self.data_processor.price_data['date'] <= end_date)
        )
        filtered_data = self.data_processor.price_data[mask]
        
        if filtered_data.empty:
            return {}
        
        # Считаем общую статистику
        stats = {
            'total_candles': len(filtered_data),
            'date_range': f"{start_date} to {end_date}",
            'trading_days': filtered_data['date'].nunique(),
            'avg_daily_candles': len(filtered_data) / filtered_data['date'].nunique() if filtered_data['date'].nunique() > 0 else 0,
            'data_gaps': self._find_data_gaps(filtered_data)
        }
        
        return stats
    
    def _find_data_gaps(self, data: pd.DataFrame, threshold_hours: int = 2) -> List[str]:
        """
        Поиск пропусков в данных
        
        Args:
            data: DataFrame с данными
            threshold_hours: Минимальный размер пропуска в часах
            
        Returns:
            Список строк с описанием пропусков
        """
        gaps = []
        
        if len(data) < 2:
            return gaps
        
        # Сортируем по времени
        sorted_data = data.sort_values('timestamp')
        
        for i in range(1, len(sorted_data)):
            time_diff = sorted_data.iloc[i]['timestamp'] - sorted_data.iloc[i-1]['timestamp']
            
            if time_diff.total_seconds() > threshold_hours * 3600:
                gap_start = sorted_data.iloc[i-1]['timestamp']
                gap_end = sorted_data.iloc[i]['timestamp']
                gap_duration = time_diff.total_seconds() / 3600
                
                gaps.append(f"{gap_start:%Y-%m-%d %H:%M} - {gap_end:%H:%M} ({gap_duration:.1f}ч)")
        
        return gaps[:5]  # Возвращаем максимум 5 пропусков