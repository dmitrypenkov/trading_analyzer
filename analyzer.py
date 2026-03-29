"""
Модуль анализа торговых стратегий для Trading Analyzer v10.0
Реализует основную бизнес-логику определения типов входов и расчета сделок
"""

import pandas as pd
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple
from data_processor import DataProcessor
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


class TradingAnalyzer:
    """
    Класс для анализа торговых стратегий на основе БЛОКОВ и СЕССИЙ.
    Определяет типы входов и симулирует исполнение сделок.
    """
    
    def __init__(self, data_processor: DataProcessor):
        """
        Инициализация анализатора.
        
        Args:
            data_processor: Экземпляр DataProcessor с загруженными данными
        """
        self.data_processor = data_processor
        logger.info("TradingAnalyzer инициализирован")
    
    def analyze_day(self, date: datetime.date, settings: Dict) -> Optional[Dict]:
        """
        Анализирует один торговый день.
        
        Args:
            date: Дата для анализа
            settings: Словарь с настройками стратегии
                - block_start, block_end: время БЛОКА
                - session_start, session_end: время СЕССИИ
                - use_return_mode: режим работы (False=по-тренду, True=возвратный)
                - tp_multiplier, sl_multiplier: множители для TP/SL
                - min_range_size, max_range_size: фильтры размера диапазона
                - use_news_filter: использовать ли новостной фильтр
                - news_impact_filter: список важности новостей
                - news_buffer_minutes: буферное время для новостей
                - use_fixed_tp_sl: использовать ли фиксированные TP/SL
                - threshold_min, threshold_max: пороги для фиксированных TP/SL
                - fixed_tp_distance, fixed_sl_distance: фиксированные расстояния
                - from_previous_day: начать БЛОК с предыдущего дня
                - skip_red_news_days: пропускать дни с красными новостями
                - news_currency_filter: список валют для фильтра новостей
        
        Returns:
            Словарь с результатами анализа дня или None если день пропущен
        """
        try:
            # НОВОЕ: Проверка на красные новости в течение всего дня
            if settings.get('skip_red_news_days', False) and settings.get('use_news_filter', False):
                currency_filter = settings.get('news_currency_filter', [])
                if self.data_processor.has_high_impact_news_in_day(date, currency_filter):
                    logger.info(f"День {date} пропущен: есть красные новости")
                    return None
            
            # Получаем диапазон БЛОКА с учетом нового параметра from_previous_day
            block_range = self.data_processor.get_block_range(
                date,
                settings['block_start'],
                settings['block_end'],
                from_previous_day=settings.get('from_previous_day', False)  # НОВОЕ
            )
            
            if block_range is None:
                logger.info(f"День {date} пропущен: нет данных для БЛОКА")
                return None
            
            # Проверяем размер диапазона
            range_size = block_range['range_size']
            min_size = settings.get('min_range_size', 0)
            max_size = settings.get('max_range_size', float('inf'))
            
            if range_size < min_size:
                logger.info(f"День {date} пропущен: диапазон {range_size:.2f} < {min_size}")
                return None
            
            if range_size > max_size:
                logger.info(f"День {date} пропущен: диапазон {range_size:.2f} > {max_size}")
                return None
            
            # Получаем данные СЕССИИ
            session_candles = self.data_processor.get_session_data(
                date,
                settings['session_start'],
                settings['session_end']
            )
            
            if session_candles.empty:
                logger.info(f"День {date} пропущен: нет данных для СЕССИИ")
                return None
            
            # Определяем стартовую позицию
            session_start_time = datetime.combine(date, settings['session_start'])
            start_position = self.data_processor.get_start_position(
                session_start_time,
                block_range
            )
            
            # Определяем тип входа
            entry_info = self.determine_entry_type(
                session_candles,
                block_range,
                start_position,
                settings['use_return_mode'],
                limit_only_entry=settings.get('limit_only_entry', False)
            )
            
            # Базовый результат
            result = {
                'date': date,
                'range_high': block_range['range_high'],
                'range_low': block_range['range_low'],
                'range_size': block_range['range_size'],
                'start_position': start_position,
                'entry_type': entry_info['entry_type']
            }
            
            # Если нет торгового входа
            if entry_info['entry_type'] in ['INSIDE_BLOCK', 'OUTSIDE_BLOCK']:
                result.update({
                    'entry_price': None,
                    'entry_time': None,
                    'exit_price': None,
                    'exit_time': None,
                    'result': 'NO_TRADE',
                    'pnl': 0.0,
                    'close_reason': 'no_entry_signal'
                })
                return result
            
            # Проверяем новостной фильтр перед входом
            if settings.get('use_news_filter', False):
                has_news = self.data_processor.check_news_window(
                    entry_info['entry_time'],
                    settings['news_impact_filter'],
                    settings['news_buffer_minutes'],
                    settings.get('news_currency_filter', [])
                )
                
                if has_news:
                    logger.info(f"Вход заблокирован новостным фильтром: {entry_info['entry_time']}")
                    result.update({
                        'entry_price': None,
                        'entry_time': None,
                        'exit_price': None,
                        'exit_time': None,
                        'result': 'NO_TRADE',
                        'pnl': 0.0,
                        'close_reason': 'news_filter_blocked'
                    })
                    return result
            
            # Рассчитываем уровни TP/SL (с учетом фиксированных значений)
            trade_levels = self.calculate_trade_levels(
                entry_info['entry_price'],
                entry_info['entry_type'],
                block_range['range_size'],
                settings
            )
            
            # Подготавливаем настройки новостного фильтра для исполнения
            news_filter_settings = None
            if settings.get('use_news_filter', False):
                news_filter_settings = {
                    'impact_filter': settings['news_impact_filter'],
                    'buffer_minutes': settings['news_buffer_minutes'],
                    'currency_filter': settings.get('news_currency_filter', [])
                }
            
            # Симулируем исполнение сделки
            session_end_time = datetime.combine(date, settings['session_end'])
            if settings['session_end'] <= settings['session_start']:
                session_end_time += timedelta(days=1)
            
            trade_result = self.execute_trade(
                session_candles,
                entry_info['entry_candle_index'],
                trade_levels,
                session_end_time,
                news_filter_settings
            )
            
            # Обновляем результат
            result.update({
                'entry_price': entry_info['entry_price'],
                'entry_time': entry_info['entry_time'],
                'tp_price': trade_levels['tp_price'],
                'sl_price': trade_levels['sl_price'],
                'exit_price': trade_result['exit_price'],
                'exit_time': trade_result['exit_time'],
                'result': trade_result['result'],
                'pnl': trade_result['pnl'],
                'close_reason': trade_result['close_reason'],
                'tp_size': trade_levels['tp_size'],  
                'sl_size': trade_levels['sl_size']  
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при анализе дня {date}: {str(e)}")
            return None
    
    def determine_entry_type(self, session_candles: pd.DataFrame, block_range: Dict, 
                           start_position: str, use_return_mode: bool,
                           limit_only_entry: bool = False) -> Dict:
        """
        Определяет тип входа в позицию согласно бизнес-логике.
        
        Args:
            session_candles: DataFrame со свечами сессии
            block_range: Словарь с границами блока
            start_position: Позиция на старте ('INSIDE', 'ABOVE', 'BELOW')
            use_return_mode: Режим работы (False=по-тренду, True=возвратный)
            limit_only_entry: Если True, ENTRY-типы требуют пересечения границы + возврата
        
        Returns:
            Словарь с информацией о входе
        """
        range_high = block_range['range_high']
        range_low = block_range['range_low']
        
        # Флаги пересечения границ для limit_only_entry
        high_crossed = False
        low_crossed = False
        
        # Проходим по свечам сессии
        for idx, candle in session_candles.iterrows():
            candle_idx = session_candles.index.get_loc(idx)
            
            # Проверяем касания границ
            touches_high = self.check_boundary_touch(candle, range_high)
            touches_low = self.check_boundary_touch(candle, range_low)
            
            # Обновляем флаги пересечения для limit_only_entry
            if limit_only_entry and start_position == 'INSIDE':
                if candle['high'] > range_high:
                    high_crossed = True
                if candle['low'] < range_low:
                    low_crossed = True
            
            # РЕЖИМ ПО-ТРЕНДУ
            if not use_return_mode:
                if start_position == 'INSIDE':
                    if limit_only_entry:
                        # Лимитный вход: пересечение границы → возврат → вход
                        if high_crossed and touches_high and candle['low'] < range_high:
                            return {
                                'entry_type': 'ENTRY_LONG_TREND',
                                'entry_price': range_high,
                                'entry_time': candle['timestamp'],
                                'entry_candle_index': candle_idx
                            }
                        elif low_crossed and touches_low and candle['high'] > range_low:
                            return {
                                'entry_type': 'ENTRY_SHORT_TREND',
                                'entry_price': range_low,
                                'entry_time': candle['timestamp'],
                                'entry_candle_index': candle_idx
                            }
                    elif touches_high:
                        return {
                            'entry_type': 'ENTRY_LONG_TREND',
                            'entry_price': range_high,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
                    elif touches_low:
                        return {
                            'entry_type': 'ENTRY_SHORT_TREND',
                            'entry_price': range_low,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
                
                elif start_position == 'ABOVE':
                    if touches_low:
                        return {
                            'entry_type': 'LIMIT_SHORT_TREND',
                            'entry_price': range_low,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
                
                elif start_position == 'BELOW':
                    if touches_high:
                        return {
                            'entry_type': 'LIMIT_LONG_TREND',
                            'entry_price': range_high,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
            
            # ВОЗВРАТНЫЙ РЕЖИМ
            else:
                if start_position == 'INSIDE':
                    if limit_only_entry:
                        if high_crossed and touches_high and candle['low'] < range_high:
                            return {
                                'entry_type': 'ENTRY_SHORT_REVERSE',
                                'entry_price': range_high,
                                'entry_time': candle['timestamp'],
                                'entry_candle_index': candle_idx
                            }
                        elif low_crossed and touches_low and candle['high'] > range_low:
                            return {
                                'entry_type': 'ENTRY_LONG_REVERSE',
                                'entry_price': range_low,
                                'entry_time': candle['timestamp'],
                                'entry_candle_index': candle_idx
                            }
                    elif touches_high:
                        return {
                            'entry_type': 'ENTRY_SHORT_REVERSE',
                            'entry_price': range_high,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
                    elif touches_low:
                        return {
                            'entry_type': 'ENTRY_LONG_REVERSE',
                            'entry_price': range_low,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
                
                elif start_position == 'ABOVE':
                    if touches_high:
                        return {
                            'entry_type': 'LIMIT_SHORT_REVERSE',
                            'entry_price': range_high,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
                
                elif start_position == 'BELOW':
                    if touches_low:
                        return {
                            'entry_type': 'LIMIT_LONG_REVERSE',
                            'entry_price': range_low,
                            'entry_time': candle['timestamp'],
                            'entry_candle_index': candle_idx
                        }
        
        # Если не было касаний
        if start_position == 'INSIDE':
            return {
                'entry_type': 'INSIDE_BLOCK',
                'entry_price': None,
                'entry_time': None,
                'entry_candle_index': None
            }
        else:
            return {
                'entry_type': 'OUTSIDE_BLOCK',
                'entry_price': None,
                'entry_time': None,
                'entry_candle_index': None
            }
    
    def check_boundary_touch(self, candle: pd.Series, boundary: float) -> bool:
        """
        Проверяет касание свечой границы диапазона.
        
        Args:
            candle: Строка DataFrame со свечой (OHLC)
            boundary: Уровень границы
        
        Returns:
            True если свеча касается границы
        """
        # Свеча касается границы если уровень находится между low и high
        return candle['low'] <= boundary <= candle['high']
    
    def calculate_trade_levels(self, entry_price: float, entry_type: str,
                             range_size: float, settings: Dict) -> Dict:
        """
        Рассчитывает уровни Take Profit и Stop Loss.
        
        Args:
            entry_price: Цена входа
            entry_type: Тип входа
            range_size: Размер диапазона БЛОКА
            settings: Настройки стратегии
        
        Returns:
            Словарь с уровнями TP и SL
        """
        # Режим Base SL + RR
        if settings.get('use_base_sl_mode', False):
            base_sl = settings.get('base_sl', 0)
            sl_mult = settings.get('sl_multiplier', 0)
            rr_ratio = settings.get('rr_ratio', 1.0)

            sl_distance = base_sl + (range_size * sl_mult)
            tp_distance = sl_distance * rr_ratio

            is_long = 'LONG' in entry_type
            if is_long:
                tp_price = entry_price + tp_distance
                sl_price = entry_price - sl_distance
            else:
                tp_price = entry_price - tp_distance
                sl_price = entry_price + sl_distance

            return {
                'tp_price': tp_price,
                'sl_price': sl_price,
                'tp_size': tp_distance,
                'sl_size': sl_distance
            }

        # Проверка на фиксированные TP/SL
        use_fixed = settings.get('use_fixed_tp_sl', False)
        
        if use_fixed:
            threshold_min = settings.get('threshold_min', 0)
            threshold_max = settings.get('threshold_max', float('inf'))
            
            # Проверяем выход за пороги
            if range_size < threshold_min or range_size > threshold_max:
                # Используем фиксированные значения
                tp_distance = settings.get('fixed_tp_distance', 0)
                sl_distance = settings.get('fixed_sl_distance', 0)
                
                # Определяем направление в зависимости от типа входа
                is_long = 'LONG' in entry_type
                
                if is_long:
                    tp_price = entry_price + tp_distance
                    sl_price = entry_price - sl_distance
                else:
                    tp_price = entry_price - tp_distance
                    sl_price = entry_price + sl_distance
                
                return {
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'tp_size': tp_distance,
                    'sl_size': sl_distance
                }
        
        # Стандартный расчет через множители
        tp_multiplier = settings.get('tp_multiplier', 1.0)
        sl_multiplier = settings.get('sl_multiplier', 1.0)
        
        tp_distance = range_size * tp_multiplier
        sl_distance = range_size * sl_multiplier
        
        # Определяем направление в зависимости от типа входа
        is_long = 'LONG' in entry_type
        
        if is_long:
            tp_price = entry_price + tp_distance
            sl_price = entry_price - sl_distance
        else:
            tp_price = entry_price - tp_distance
            sl_price = entry_price + sl_distance
        
        return {
            'tp_price': tp_price,
            'sl_price': sl_price,
            'tp_size': tp_distance,
            'sl_size': sl_distance
        }
    
    def execute_trade(self, session_candles: pd.DataFrame, entry_candle_index: int,
                     trade_levels: Dict, session_end_time: datetime,
                     news_filter_settings: Optional[Dict] = None) -> Dict:
        """
        Симулирует исполнение сделки от точки входа.
        
        Args:
            session_candles: DataFrame со свечами сессии
            entry_candle_index: Индекс свечи входа
            trade_levels: Словарь с уровнями TP и SL
            session_end_time: Время окончания сессии
            news_filter_settings: Настройки новостного фильтра (опционально)
        
        Returns:
            Словарь с результатами исполнения сделки
        """
        tp_price = trade_levels['tp_price']
        sl_price = trade_levels['sl_price']
        
        # Проходим по свечам после входа
        for idx in range(entry_candle_index + 1, len(session_candles)):
            candle = session_candles.iloc[idx]
            
            # Проверка новостного фильтра
            if news_filter_settings:
                has_news = self.data_processor.check_news_window(
                    candle['timestamp'],
                    news_filter_settings['impact_filter'],
                    news_filter_settings['buffer_minutes'],
                    news_filter_settings.get('currency_filter', [])
                )
                
                if has_news:
                    # Закрываем по BE при новостях
                    entry_price = session_candles.iloc[entry_candle_index]['close']
                    return {
                        'exit_price': entry_price,
                        'exit_time': candle['timestamp'],
                        'result': 'BE',
                        'pnl': 0.0,
                        'close_reason': 'news_breakeven'
                    }
            
            # Проверка достижения TP
            if candle['high'] >= tp_price and candle['low'] <= tp_price:
                return {
                    'exit_price': tp_price,
                    'exit_time': candle['timestamp'],
                    'result': 'TP',
                    'pnl': abs(tp_price - session_candles.iloc[entry_candle_index]['close']),
                    'close_reason': 'take_profit'
                }
            
            # Проверка достижения SL
            if candle['high'] >= sl_price and candle['low'] <= sl_price:
                return {
                    'exit_price': sl_price,
                    'exit_time': candle['timestamp'],
                    'result': 'SL',
                    'pnl': -abs(sl_price - session_candles.iloc[entry_candle_index]['close']),
                    'close_reason': 'stop_loss'
                }
        
        # Если дошли до конца сессии - закрываем по времени
        last_candle = session_candles.iloc[-1]
        entry_price = session_candles.iloc[entry_candle_index]['close']
        exit_price = last_candle['close']
        pnl = exit_price - entry_price
        
        # Определяем результат по PnL
        if abs(pnl) < 0.0001:  # Практически BE
            result = 'BE'
        elif pnl > 0:
            result = 'TP'
        else:
            result = 'SL'
        
        return {
            'exit_price': exit_price,
            'exit_time': session_end_time,
            'result': result,
            'pnl': pnl,
            'close_reason': 'session_end'
        }
    
    def analyze_period(self, start_date: datetime.date, end_date: datetime.date,
                      settings: Dict) -> Dict:
        """
        Анализирует период из нескольких торговых дней.
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            settings: Настройки стратегии
        
        Returns:
            Словарь с результатами и статистикой
        """
        # Получаем список торговых дней
        trading_days = settings.get('trading_days', [0, 1, 2, 3, 4])
        dates_to_analyze = self.data_processor.filter_trading_days(
            start_date, end_date, trading_days
        )
        
        # Инициализация результатов
        results = []
        skipped_days = {
            'no_data': 0,
            'small_range': 0,
            'large_range': 0,
            'red_news': 0,  # НОВОЕ: счетчик дней с красными новостями
            'total': 0
        }
        
        # Анализируем каждый день
        for date in dates_to_analyze:
            # НОВОЕ: Проверка на красные новости
            if settings.get('skip_red_news_days', False) and settings.get('use_news_filter', False):
                currency_filter = settings.get('news_currency_filter', [])
                if self.data_processor.has_high_impact_news_in_day(date, currency_filter):
                    skipped_days['red_news'] += 1
                    skipped_days['total'] += 1
                    continue
            
            # Получаем диапазон для проверки (с учетом from_previous_day)
            block_range = self.data_processor.get_block_range(
                date,
                settings['block_start'],
                settings['block_end'],
                from_previous_day=settings.get('from_previous_day', False)  # НОВОЕ
            )
            
            if block_range is None:
                skipped_days['no_data'] += 1
                skipped_days['total'] += 1
                continue
            
            # Проверяем размер диапазона
            range_size = block_range['range_size']
            min_size = settings.get('min_range_size', 0)
            max_size = settings.get('max_range_size', float('inf'))
            
            if range_size < min_size:
                skipped_days['small_range'] += 1
                skipped_days['total'] += 1
                continue
            
            if range_size > max_size:
                skipped_days['large_range'] += 1
                skipped_days['total'] += 1
                continue
            
            # Анализируем день
            day_result = self.analyze_day(date, settings)
            if day_result:
                results.append(day_result)
        
        logger.info(f"Проанализировано {len(results)} дней, пропущено {skipped_days['total']}")
        if skipped_days['red_news'] > 0:
            logger.info(f"Пропущено из-за красных новостей: {skipped_days['red_news']} дней")
        
        return {
            'results': results,
            'skipped_days': skipped_days
        }