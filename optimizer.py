"""
Модуль оптимизации параметров для Trading Analyzer v11.0
Выполняет перебор комбинаций TP/SL для поиска оптимальных параметров
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Callable, List, Any
from datetime import datetime, timedelta
import time
import logging
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import itertools
import os
from pathlib import Path

# Импорт модулей системы
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator
from data_processor import DataProcessor

# Настройка логирования
logger = logging.getLogger(__name__)


class TradingOptimizer:
    """
    Класс для оптимизации параметров торговой стратегии.
    Выполняет перебор комбинаций TP/SL множителей для достижения целевой метрики.
    """
    
    def __init__(self, data_processor: DataProcessor, 
                 analyzer: TradingAnalyzer, 
                 r_calculator: RCalculator):
        """
        Инициализация оптимизатора.
        
        Args:
            data_processor: Экземпляр DataProcessor с загруженными данными
            analyzer: Экземпляр TradingAnalyzer для анализа
            r_calculator: Экземпляр RCalculator для R-расчетов
        """
        self.data_processor = data_processor
        self.analyzer = analyzer
        self.r_calculator = r_calculator
        self.report_generator = ReportGenerator(r_calculator)
        
        # Кеш результатов для ускорения повторных вычислений
        self._results_cache = {}
        self._cache_lock = threading.Lock()
        
        logger.info("TradingOptimizer инициализирован")
    
    def optimize_parameters(self, 
                           settings: Dict,
                           tp_range: Tuple[float, float, float],
                           sl_range: Tuple[float, float, float],
                           optimization_target: str = 'max_total_r',
                           progress_callback: Optional[Callable] = None,
                           use_parallel: bool = False) -> Dict:
        """
        Оптимизирует параметры TP/SL методом перебора.
        
        Args:
            settings: Базовые настройки стратегии (без tp_multiplier и sl_multiplier)
            tp_range: (min, max, step) для TP множителя
            sl_range: (min, max, step) для SL множителя
            optimization_target: Цель оптимизации:
                - 'max_total_r': максимальный суммарный R-результат
                - 'max_days_above_threshold': максимум дней с R > 0.35
            progress_callback: Функция для обновления прогресса (принимает процент 0-100)
            use_parallel: Использовать параллельную обработку
        
        Returns:
            Словарь с результатами оптимизации:
            {
                'best_params': {'tp_multiplier': X, 'sl_multiplier': Y},
                'best_metric': значение целевой метрики,
                'results_grid': DataFrame со всеми протестированными комбинациями,
                'optimization_details': детали процесса оптимизации
            }
        """
        start_time = time.time()
        
        # Валидация входных параметров
        self._validate_ranges(tp_range, sl_range)
        
        # Генерация всех комбинаций
        tp_values = self._generate_range_values(*tp_range)
        sl_values = self._generate_range_values(*sl_range)
        
        all_combinations = list(itertools.product(tp_values, sl_values))
        total_combinations = len(all_combinations)
        
        logger.info(f"Начало оптимизации: {total_combinations} комбинаций, цель: {optimization_target}")
        
        # Результаты для каждой комбинации
        all_results = []
        best_metric = None
        best_params = None
        
        # Определяем функцию сравнения в зависимости от цели
        is_better = self._get_comparison_function(optimization_target)
        
        # Параллельная или последовательная обработка
        if use_parallel and total_combinations > 10:
            all_results = self._run_parallel_optimization(
                settings, all_combinations, optimization_target, progress_callback
            )
        else:
            # Последовательная обработка
            for idx, (tp_mult, sl_mult) in enumerate(all_combinations):
                # Обновляем прогресс
                if progress_callback:
                    progress = int((idx + 1) / total_combinations * 100)
                    progress_callback(progress)
                
                # Запускаем оптимизацию для одной комбинации
                result = self.run_single_optimization(
                    settings, tp_mult, sl_mult, optimization_target
                )
                
                all_results.append(result)
                
                # Проверяем, лучше ли текущий результат
                current_metric = result['metric_value']
                
                if best_metric is None or is_better(current_metric, best_metric):
                    best_metric = current_metric
                    best_params = {
                        'tp_multiplier': tp_mult,
                        'sl_multiplier': sl_mult
                    }
                    
                    logger.info(f"Новый лучший результат: TP={tp_mult}, SL={sl_mult}, метрика={best_metric:.2f}")
        
        # Создаем DataFrame с результатами
        results_df = pd.DataFrame(all_results)
        
        # Создаем сетку результатов для heatmap
        results_grid = self.create_results_grid(results_df, tp_values, sl_values)
        
        # Время выполнения
        computation_time = time.time() - start_time
        
        # Собираем финальный результат
        optimization_result = {
            'best_params': best_params,
            'best_metric': best_metric,
            'results_df': results_df,
            'results_grid': results_grid,
            'optimization_details': {
                'total_combinations': total_combinations,
                'computation_time': round(computation_time, 2),
                'target': optimization_target,
                'tp_range': tp_range,
                'sl_range': sl_range,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        logger.info(f"Оптимизация завершена за {computation_time:.1f} сек. Лучший результат: {best_metric:.2f}")
        
        return optimization_result
    
    def run_single_optimization(self, 
                               settings: Dict,
                               tp_multiplier: float,
                               sl_multiplier: float,
                               optimization_target: str = 'max_total_r') -> Dict:
        """
        Запускает анализ для одной комбинации TP/SL.
        
        Args:
            settings: Базовые настройки
            tp_multiplier: Множитель TP
            sl_multiplier: Множитель SL
            optimization_target: Цель оптимизации
        
        Returns:
            Словарь с результатами для одной комбинации
        """
        # Создаем копию настроек и добавляем TP/SL
        test_settings = deepcopy(settings)
        test_settings['tp_multiplier'] = tp_multiplier
        test_settings['sl_multiplier'] = sl_multiplier
        
        # Проверяем кеш
        cache_key = f"{tp_multiplier}_{sl_multiplier}"
        with self._cache_lock:
            if cache_key in self._results_cache:
                cached_result = self._results_cache[cache_key].copy()
                cached_result['metric_value'] = self.calculate_metric(
                    cached_result['analysis_results'], 
                    optimization_target,
                    test_settings
                )
                return cached_result
        
        try:
            # Запускаем анализ
            analysis_results = self.analyzer.analyze_period(
                test_settings['start_date'],
                test_settings['end_date'],
                test_settings
            )
            
            # Вычисляем метрику
            metric_value = self.calculate_metric(
                analysis_results, 
                optimization_target,
                test_settings
            )
            
            # Дополнительная статистика
            executed_trades = [
                r for r in analysis_results['results'] 
                if r.get('result') in ['TP', 'SL', 'BE']
            ]
            
            tp_count = sum(1 for r in executed_trades if r.get('result') == 'TP')
            sl_count = sum(1 for r in executed_trades if r.get('result') == 'SL')
            be_count = sum(1 for r in executed_trades if r.get('result') == 'BE')
            
            # Подсчет R-результата
            total_r = sum(
                self.r_calculator.calculate_r_result(r, test_settings.get('tp_coefficient', 0.9))
                for r in executed_trades
            )
            
            result = {
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'metric_value': metric_value,
                'total_r': round(total_r, 2),
                'total_trades': len(executed_trades),
                'tp_count': tp_count,
                'sl_count': sl_count,
                'be_count': be_count,
                'win_rate': round(tp_count / len(executed_trades) * 100, 1) if executed_trades else 0,
                'r_ratio': round(tp_multiplier / sl_multiplier, 2),
                'analysis_results': analysis_results  # Сохраняем для кеша
            }
            
            # Сохраняем в кеш
            with self._cache_lock:
                self._results_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при оптимизации TP={tp_multiplier}, SL={sl_multiplier}: {str(e)}")
            return {
                'tp_multiplier': tp_multiplier,
                'sl_multiplier': sl_multiplier,
                'metric_value': -999999,  # Штрафное значение
                'total_r': 0,
                'total_trades': 0,
                'tp_count': 0,
                'sl_count': 0,
                'be_count': 0,
                'win_rate': 0,
                'r_ratio': round(tp_multiplier / sl_multiplier, 2),
                'error': str(e)
            }
    
    def calculate_metric(self, 
                        analysis_results: Dict,
                        optimization_target: str,
                        settings: Dict = None) -> float:
        """
        Вычисляет целевую метрику для результатов анализа.
        
        Args:
            analysis_results: Результаты анализа из analyzer
            optimization_target: Цель оптимизации
            settings: Настройки стратегии (для tp_coefficient и др.)
        
        Returns:
            Значение метрики (float)
        """
        if not analysis_results or 'results' not in analysis_results:
            return -999999
        
        # Для обратной совместимости
        if settings is None:
            settings = {}
        tp_coefficient = settings.get('tp_coefficient', 0.9) if isinstance(settings, dict) else settings
        sl_slippage = settings.get('sl_slippage_coefficient', 1.0) if isinstance(settings, dict) else 1.0
        commission = settings.get('commission_rate', 0.0) if isinstance(settings, dict) else 0.0
        
        results = analysis_results['results']
        
        # Фильтруем исполненные сделки
        executed_trades = [
            r for r in results 
            if r.get('result') in ['TP', 'SL', 'BE']
        ]
        
        if not executed_trades:
            return -999999
        
        # Считаем R-результаты
        r_values = [
            self.r_calculator.calculate_r_result(r, tp_coefficient, sl_slippage, commission)
            for r in executed_trades
        ]
        total_r = sum(r_values)
        
        # Считаем Max Drawdown
        cumulative = []
        running = 0.0
        for rv in r_values:
            running += rv
            cumulative.append(round(running, 2))
        dd_info = self.r_calculator.calculate_max_drawdown(cumulative)
        max_dd_abs = dd_info.get('max_drawdown_abs', 0.0)
        
        if optimization_target == 'max_total_r':
            return total_r
        
        elif optimization_target == 'max_r_dd_ratio':
            # Calmar-like: Total R / |Max Drawdown|
            if max_dd_abs < 0.01:
                return total_r * 100 if total_r > 0 else 0
            return round(total_r / max_dd_abs, 4)
        
        elif optimization_target == 'max_r_minus_dd':
            # Weighted: Total R - 2 × |Max Drawdown|
            return round(total_r - 2.0 * max_dd_abs, 4)
        
        else:
            logger.warning(f"Неизвестная цель оптимизации: {optimization_target}")
            return 0
    
    def create_results_grid(self, 
                           results_df: pd.DataFrame,
                           tp_values: List[float],
                           sl_values: List[float]) -> pd.DataFrame:
        """
        Создает сетку результатов для heatmap.
        
        Args:
            results_df: DataFrame со всеми результатами
            tp_values: Список значений TP
            sl_values: Список значений SL
        
        Returns:
            DataFrame в формате сетки (SL по строкам, TP по колонкам)
        """
        # Создаем пустую сетку
        grid = pd.DataFrame(
            index=sl_values,
            columns=tp_values,
            dtype=float
        )
        
        # Заполняем сетку значениями метрики
        for _, row in results_df.iterrows():
            tp = row['tp_multiplier']
            sl = row['sl_multiplier']
            metric = row['metric_value']
            
            if sl in grid.index and tp in grid.columns:
                grid.loc[sl, tp] = metric
        
        # Сортируем индексы и колонки
        grid = grid.sort_index(ascending=False)
        grid = grid[sorted(grid.columns)]
        
        return grid
    
    def export_detailed_results(self, 
                               optimization_results: Dict,
                               settings: Dict,
                               export_mode: str = 'top10',
                               export_folder: str = None,
                               progress_callback: Optional[Callable] = None) -> str:
        """
        Экспортирует детальные результаты анализа для каждой комбинации TP/SL.
        
        Args:
            optimization_results: Результаты оптимизации из optimize_parameters
            settings: Настройки стратегии
            export_mode: 'top10' или 'all' - режим экспорта
            export_folder: Папка для экспорта (если None, создается автоматически)
            progress_callback: Функция для обновления прогресса
        
        Returns:
            Путь к папке с экспортированными файлами
        """
        try:
            # Определяем какие комбинации экспортировать
            if export_mode == 'top10':
                top_df = self.get_top_combinations(optimization_results['results_df'], 10)
                combinations_to_export = [(row['tp_multiplier'], row['sl_multiplier']) 
                                         for _, row in top_df.iterrows()]
                logger.info(f"Экспорт топ-10 комбинаций")
            else:
                combinations_to_export = [(row['tp_multiplier'], row['sl_multiplier']) 
                                         for _, row in optimization_results['results_df'].iterrows()]
                logger.info(f"Экспорт всех {len(combinations_to_export)} комбинаций")
            
            # Создаем структуру папок
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if export_folder is None:
                # Создаем папку exports если не существует
                base_export_dir = Path('exports')
                base_export_dir.mkdir(exist_ok=True)
                
                # Основная папка оптимизации
                optimization_dir = base_export_dir / f'optimization_{timestamp}'
            else:
                optimization_dir = Path(export_folder)
            
            optimization_dir.mkdir(parents=True, exist_ok=True)
            
            # Папка для конкретного временного периода
            block_start = settings.get('block_start_time', '00:00')
            block_end = settings.get('block_end_time', '23:59')
            session_start = settings.get('session_start_time', '00:00')
            session_end = settings.get('session_end_time', '23:59')
            
            # Форматируем время для имени папки (удаляем двоеточия)
            block_folder = f"block_{block_start.replace(':', '')}-{block_end.replace(':', '')}"
            session_folder = f"session_{session_start.replace(':', '')}-{session_end.replace(':', '')}"
            time_folder_name = f"{block_folder}_{session_folder}"
            
            time_dir = optimization_dir / time_folder_name
            time_dir.mkdir(exist_ok=True)
            
            # Экспортируем данные для каждой комбинации
            total_combinations = len(combinations_to_export)
            exported_count = 0
            
            for idx, (tp_mult, sl_mult) in enumerate(combinations_to_export):
                # Обновляем прогресс
                if progress_callback:
                    progress = int((idx + 1) / total_combinations * 100)
                    progress_callback(progress)
                
                # Получаем результаты из кеша
                cache_key = f"{tp_mult}_{sl_mult}"
                if cache_key not in self._results_cache:
                    # Если нет в кеше, пересчитываем
                    test_settings = deepcopy(settings)
                    test_settings['tp_multiplier'] = tp_mult
                    test_settings['sl_multiplier'] = sl_mult
                    
                    analysis_results = self.analyzer.analyze_period(
                        test_settings['start_date'],
                        test_settings['end_date'],
                        test_settings
                    )
                else:
                    analysis_results = self._results_cache[cache_key].get('analysis_results')
                
                if not analysis_results:
                    logger.warning(f"Пропуск комбинации TP={tp_mult}, SL={sl_mult} - нет результатов")
                    continue
                
                # Подготавливаем данные для экспорта
                daily_trades_df = self.report_generator.prepare_daily_trades(
                    analysis_results['results'], 
                    settings.get('tp_coefficient', 0.9)
                )
                
                # Формируем имя файла
                tp_str = str(tp_mult).replace('.', '_')
                sl_str = str(sl_mult).replace('.', '_')
                filename = f"trading_analyzer_TP{tp_str}_SL{sl_str}.csv"
                filepath = time_dir / filename
                
                # Сохраняем CSV
                daily_trades_df.to_csv(filepath, index=False)
                exported_count += 1
                
                logger.debug(f"Экспортирован файл: {filename}")
            
            # Создаем файл с информацией об экспорте
            info_file = optimization_dir / 'export_info.txt'
            with open(info_file, 'w', encoding='utf-8') as f:
                f.write(f"Trading Analyzer v11.0 - Детальный экспорт результатов оптимизации\n")
                f.write(f"{'='*60}\n")
                f.write(f"Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Режим экспорта: {export_mode}\n")
                f.write(f"Экспортировано комбинаций: {exported_count}\n")
                f.write(f"Папка с результатами: {time_folder_name}\n")
                f.write(f"\nПараметры оптимизации:\n")
                f.write(f"  Цель: {optimization_results['optimization_details']['target']}\n")
                f.write(f"  Диапазон TP: {optimization_results['optimization_details']['tp_range']}\n")
                f.write(f"  Диапазон SL: {optimization_results['optimization_details']['sl_range']}\n")
                f.write(f"  Всего комбинаций: {optimization_results['optimization_details']['total_combinations']}\n")
                f.write(f"\nЛучший результат:\n")
                f.write(f"  TP: {optimization_results['best_params']['tp_multiplier']}\n")
                f.write(f"  SL: {optimization_results['best_params']['sl_multiplier']}\n")
                f.write(f"  Метрика: {optimization_results['best_metric']:.2f}\n")
            
            logger.info(f"✅ Экспорт завершен. Экспортировано {exported_count} файлов в папку: {optimization_dir}")
            
            return str(optimization_dir)
            
        except Exception as e:
            logger.error(f"Ошибка при экспорте детальных результатов: {str(e)}")
            raise
    
    def get_top_combinations(self, results_df: pd.DataFrame, 
                           n: int = 10) -> pd.DataFrame:
        """
        Получает топ N комбинаций по метрике.
        
        Args:
            results_df: DataFrame с результатами
            n: Количество лучших комбинаций
        
        Returns:
            DataFrame с топ комбинациями
        """
        # Сортируем по метрике
        sorted_df = results_df.sort_values('metric_value', ascending=False)
        
        # Берем топ N
        top_df = sorted_df.head(n).copy()
        
        # Добавляем ранг
        top_df['rank'] = range(1, len(top_df) + 1)
        
        # Переупорядочиваем колонки
        columns_order = ['rank', 'tp_multiplier', 'sl_multiplier', 'metric_value', 
                        'total_r', 'total_trades', 'win_rate', 'tp_count', 
                        'sl_count', 'be_count', 'r_ratio']
        
        # Проверяем наличие колонок
        available_columns = [col for col in columns_order if col in top_df.columns]
        
        return top_df[available_columns]
    
    def export_optimization_results(self, optimization_result: Dict, 
                                   filename: str = None) -> str:
        """
        Экспортирует результаты оптимизации в Excel.
        
        Args:
            optimization_result: Результаты оптимизации
            filename: Имя файла (если None, генерируется автоматически)
        
        Returns:
            Путь к сохраненному файлу
        """
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"optimization_results_{timestamp}.xlsx"
        
        try:
            with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
                # Лист 1: Сводка
                summary_data = {
                    'Параметр': ['Цель оптимизации', 'Лучший TP', 'Лучший SL', 
                                'Лучшая метрика', 'Всего комбинаций', 
                                'Время выполнения (сек)'],
                    'Значение': [
                        optimization_result['optimization_details']['target'],
                        optimization_result['best_params']['tp_multiplier'],
                        optimization_result['best_params']['sl_multiplier'],
                        optimization_result['best_metric'],
                        optimization_result['optimization_details']['total_combinations'],
                        optimization_result['optimization_details']['computation_time']
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Сводка', index=False)
                
                # Лист 2: Топ-10 комбинаций
                top_10 = self.get_top_combinations(optimization_result['results_df'], 10)
                top_10.to_excel(writer, sheet_name='Топ-10', index=False)
                
                # Лист 3: Все результаты
                optimization_result['results_df'].to_excel(
                    writer, sheet_name='Все результаты', index=False
                )
                
                # Лист 4: Сетка для heatmap
                optimization_result['results_grid'].to_excel(
                    writer, sheet_name='Сетка результатов'
                )
            
            logger.info(f"Результаты оптимизации сохранены в {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Ошибка при экспорте результатов: {str(e)}")
            raise
    
    def optimize_time_and_params(self, 
                               settings: Dict,
                               block_start_fixed: str,
                               session_end_fixed: str,
                               split_hour_min: int,
                               split_hour_max: int,
                               split_hour_step: int,
                               tp_range: tuple,
                               sl_range: tuple,
                               optimization_target: str,
                               from_previous_day: bool = False,
                               progress_callback=None) -> Dict:
        """
        Двухфазная оптимизация: перебор времени разделения блок/сессия + TP/SL.
        
        block_start фиксирован, session_end фиксирован.
        block_end = session_start = split_hour (перебираемый параметр).
        
        Args:
            settings: Базовые настройки
            block_start_fixed: Фиксированное начало блока (напр. '00:00')
            session_end_fixed: Фиксированный конец сессии (напр. '20:00')
            split_hour_min: Минимальный час разделения (напр. 3)
            split_hour_max: Максимальный час разделения (напр. 18)
            split_hour_step: Шаг в часах (напр. 1)
            tp_range: (min, max, step) для TP
            sl_range: (min, max, step) для SL
            optimization_target: Цель оптимизации
            from_previous_day: Блок с предыдущего дня
            progress_callback: Функция прогресса
        
        Returns:
            Словарь с результатами оптимизации по всем временным окнам
        """
        from datetime import time as dt_time
        start_time = time.time()
        
        # Генерируем временные точки разделения
        split_hours = list(range(split_hour_min, split_hour_max + 1, split_hour_step))
        
        # Генерируем TP/SL комбинации
        tp_values = self._generate_range_values(*tp_range)
        sl_values = self._generate_range_values(*sl_range)
        tp_sl_combinations = list(itertools.product(tp_values, sl_values))
        
        total_steps = len(split_hours) * len(tp_sl_combinations)
        completed = 0
        
        all_time_results = []
        best_overall_metric = None
        best_overall_result = None
        
        is_better = self._get_comparison_function(optimization_target)
        
        for split_hour in split_hours:
            split_time_str = f"{split_hour:02d}:00"
            
            # Очищаем кеш для новых временных настроек
            self.clear_cache()
            
            # Настраиваем время
            time_settings = deepcopy(settings)
            time_settings['block_start'] = datetime.strptime(block_start_fixed, '%H:%M').time()
            time_settings['block_end'] = dt_time(split_hour, 0)
            time_settings['session_start'] = dt_time(split_hour, 0)
            time_settings['session_end'] = datetime.strptime(session_end_fixed, '%H:%M').time()
            time_settings['from_previous_day'] = from_previous_day
            
            # Лучший результат для текущего временного окна
            best_time_metric = None
            best_time_params = None
            time_results = []
            
            for tp_mult, sl_mult in tp_sl_combinations:
                result = self.run_single_optimization(
                    time_settings, tp_mult, sl_mult, optimization_target
                )
                result['split_hour'] = split_hour
                result['split_time'] = split_time_str
                time_results.append(result)
                
                current_metric = result['metric_value']
                if best_time_metric is None or is_better(current_metric, best_time_metric):
                    best_time_metric = current_metric
                    best_time_params = {
                        'tp_multiplier': tp_mult,
                        'sl_multiplier': sl_mult
                    }
                
                completed += 1
                if progress_callback:
                    progress_callback(int(completed / total_steps * 100))
            
            # Сохраняем лучший результат для этого времени
            time_summary = {
                'split_hour': split_hour,
                'split_time': split_time_str,
                'block': f"{block_start_fixed}-{split_time_str}",
                'session': f"{split_time_str}-{session_end_fixed}",
                'best_metric': best_time_metric,
                'best_tp': best_time_params['tp_multiplier'] if best_time_params else None,
                'best_sl': best_time_params['sl_multiplier'] if best_time_params else None,
                'all_results': time_results
            }
            
            # Считаем total_r и max_dd для лучшей комбинации
            if best_time_params:
                best_key = f"{best_time_params['tp_multiplier']}_{best_time_params['sl_multiplier']}"
                with self._cache_lock:
                    if best_key in self._results_cache:
                        cached = self._results_cache[best_key]
                        time_summary['best_total_r'] = cached.get('total_r', 0)
                        time_summary['best_trades'] = cached.get('total_trades', 0)
                        time_summary['best_win_rate'] = cached.get('win_rate', 0)
            
            all_time_results.append(time_summary)
            
            # Проверяем общий лучший
            if best_overall_metric is None or is_better(best_time_metric, best_overall_metric):
                best_overall_metric = best_time_metric
                best_overall_result = time_summary
            
            logger.info(f"Время {split_time_str}: лучшая метрика = {best_time_metric:.2f}, "
                       f"TP={best_time_params['tp_multiplier'] if best_time_params else '-'}, "
                       f"SL={best_time_params['sl_multiplier'] if best_time_params else '-'}")
        
        computation_time = time.time() - start_time
        
        return {
            'best_overall': best_overall_result,
            'all_time_results': all_time_results,
            'optimization_details': {
                'total_steps': total_steps,
                'time_points': len(split_hours),
                'tp_sl_combinations': len(tp_sl_combinations),
                'computation_time': round(computation_time, 2),
                'target': optimization_target,
                'block_start': block_start_fixed,
                'session_end': session_end_fixed,
                'from_previous_day': from_previous_day,
                'tp_range': tp_range,
                'sl_range': sl_range,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
    
    def clear_cache(self) -> None:
        """Очищает кеш результатов."""
        with self._cache_lock:
            self._results_cache.clear()
        logger.info("Кеш оптимизатора очищен")
    
    def _run_parallel_optimization(self,
                                  settings: Dict,
                                  combinations: List[Tuple[float, float]],
                                  optimization_target: str,
                                  progress_callback: Optional[Callable]) -> List[Dict]:
        """
        Запускает параллельную оптимизацию для ускорения.
        
        Args:
            settings: Настройки стратегии
            combinations: Список комбинаций (tp, sl)
            optimization_target: Цель оптимизации
            progress_callback: Функция обновления прогресса
        
        Returns:
            Список результатов для всех комбинаций
        """
        all_results = []
        completed = 0
        total = len(combinations)
        
        # Определяем количество потоков (не более 4 для стабильности)
        max_workers = min(4, total)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Создаем задачи
            future_to_params = {
                executor.submit(
                    self.run_single_optimization,
                    settings, tp, sl, optimization_target
                ): (tp, sl)
                for tp, sl in combinations
            }
            
            # Обрабатываем результаты по мере готовности
            for future in as_completed(future_to_params):
                tp, sl = future_to_params[future]
                try:
                    result = future.result(timeout=60)  # Таймаут 60 секунд
                    all_results.append(result)
                except Exception as e:
                    logger.error(f"Ошибка при параллельной оптимизации TP={tp}, SL={sl}: {str(e)}")
                    # Добавляем результат с ошибкой
                    all_results.append({
                        'tp_multiplier': tp,
                        'sl_multiplier': sl,
                        'metric_value': -999999,
                        'total_r': 0,
                        'total_trades': 0,
                        'error': str(e)
                    })
                
                # Обновляем прогресс
                completed += 1
                if progress_callback:
                    progress = int(completed / total * 100)
                    progress_callback(progress)
        
        return all_results
    
    def _validate_ranges(self, tp_range: Tuple[float, float, float], 
                        sl_range: Tuple[float, float, float]) -> None:
        """
        Валидирует диапазоны параметров.
        
        Args:
            tp_range: (min, max, step) для TP
            sl_range: (min, max, step) для SL
        
        Raises:
            ValueError: Если параметры некорректны
        """
        # Проверка TP диапазона
        if tp_range[0] <= 0 or tp_range[1] <= 0 or tp_range[2] <= 0:
            raise ValueError("Все значения TP должны быть положительными")
        
        if tp_range[0] > tp_range[1]:
            raise ValueError("Минимальное значение TP не может быть больше максимального")
        
        # Проверка SL диапазона
        if sl_range[0] <= 0 or sl_range[1] <= 0 or sl_range[2] <= 0:
            raise ValueError("Все значения SL должны быть положительными")
        
        if sl_range[0] > sl_range[1]:
            raise ValueError("Минимальное значение SL не может быть больше максимального")
        
        # Проверка шагов
        if tp_range[2] > (tp_range[1] - tp_range[0]):
            raise ValueError("Шаг TP слишком большой для заданного диапазона")
        
        if sl_range[2] > (sl_range[1] - sl_range[0]):
            raise ValueError("Шаг SL слишком большой для заданного диапазона")
    
    def _generate_range_values(self, min_val: float, max_val: float, 
                              step: float) -> List[float]:
        """
        Генерирует список значений для диапазона.
        
        Args:
            min_val: Минимальное значение
            max_val: Максимальное значение
            step: Шаг
        
        Returns:
            Список значений
        """
        values = []
        current = min_val
        
        while current <= max_val + 0.0001:  # Небольшая погрешность для float
            values.append(round(current, 4))
            current += step
        
        return values
    
    def _get_comparison_function(self, optimization_target: str) -> Callable:
        """
        Возвращает функцию сравнения для определения лучшего результата.
        
        Args:
            optimization_target: Цель оптимизации
        
        Returns:
            Функция сравнения (принимает new_value, best_value)
        """
        # Для обеих целей используем максимизацию
        return lambda new, best: new > best