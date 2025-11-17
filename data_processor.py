"""
Модуль обработки данных для Trading Analyzer v10.0
Отвечает за подготовку и фильтрацию данных для анализа
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Union
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataProcessor:
    """
    Класс для обработки ценовых данных и новостей.
    Подготавливает данные для последующего анализа торговых стратегий.
    """
    
    def __init__(self, price_data: pd.DataFrame, news_data: Optional[pd.DataFrame] = None):
        """
        Инициализация процессора данных.
        
        Args:
            price_data: DataFrame с OHLC данными (колонки: timestamp, open, high, low, close)
            news_data: Опциональный DataFrame с новостями (колонки: timestamp, impact, event)
        
        Raises:
            ValueError: Если отсутствуют необходимые колонки или данные некорректны
        """
        # Валидация ценовых данных
        required_price_columns = ['timestamp', 'open', 'high', 'low', 'close']
        if not all(col in price_data.columns for col in required_price_columns):
            raise ValueError(f"Ценовые данные должны содержать колонки: {required_price_columns}")
        
        # Копируем данные чтобы не изменять оригинал
        self.price_data = price_data.copy()
        
        # Убеждаемся что timestamp это datetime
        if not pd.api.types.is_datetime64_any_dtype(self.price_data['timestamp']):
            self.price_data['timestamp'] = pd.to_datetime(self.price_data['timestamp'])
        
        # ИСПРАВЛЕНИЕ: Конвертируем timezone-aware datetime в timezone-naive
        # Это решает проблему сравнения с обычными datetime объектами
        if self.price_data['timestamp'].dt.tz is not None:
            logger.info(f"Конвертация timezone-aware datetime в timezone-naive")
            self.price_data['timestamp'] = self.price_data['timestamp'].dt.tz_localize(None)
        
        # Сортируем по времени
        self.price_data = self.price_data.sort_values('timestamp').reset_index(drop=True)
        
        # Добавляем вспомогательные колонки
        self.price_data['date'] = self.price_data['timestamp'].dt.date
        self.price_data['time'] = self.price_data['timestamp'].dt.time
        
        # Обработка новостных данных
        self.news_data = None
        if news_data is not None:
            required_news_columns = ['timestamp', 'impact']
            if all(col in news_data.columns for col in required_news_columns):
                self.news_data = news_data.copy()
                
                # Убеждаемся что timestamp это datetime
                if not pd.api.types.is_datetime64_any_dtype(self.news_data['timestamp']):
                    self.news_data['timestamp'] = pd.to_datetime(self.news_data['timestamp'])
                
                # ИСПРАВЛЕНИЕ: Конвертируем timezone-aware datetime в timezone-naive
                if self.news_data['timestamp'].dt.tz is not None:
                    logger.info(f"Конвертация timezone-aware datetime в timezone-naive для новостей")
                    self.news_data['timestamp'] = self.news_data['timestamp'].dt.tz_localize(None)
                
                # Добавляем дату для удобства
                self.news_data['date'] = self.news_data['timestamp'].dt.date
                
                logger.info(f"Загружено {len(self.news_data)} новостей")
            else:
                logger.warning(f"Новостные данные не содержат необходимых колонок: {required_news_columns}")
        
        logger.info(f"DataProcessor инициализирован с {len(self.price_data)} свечами")
    
    def get_block_range(self, date: datetime.date, block_start: time, 
                       block_end: time, from_previous_day: bool = False) -> Optional[Dict]:
        """
        Рассчитывает границы ценового диапазона БЛОКА.
        
        Args:
            date: Дата для анализа
            block_start: Время начала БЛОКА (UTC)
            block_end: Время окончания БЛОКА (UTC)
            from_previous_day: Если True, БЛОК начинается с предыдущего дня
        
        Returns:
            Словарь с границами диапазона или None если данных недостаточно:
            {
                'range_high': float,
                'range_low': float,
                'range_size': float,
                'candle_count': int
            }
        """
        try:
            # Определяем дату начала БЛОКА
            if from_previous_day:
                # БЛОК начинается с предыдущего дня
                block_start_date = date - timedelta(days=1)
                logger.debug(f"БЛОК начинается с предыдущего дня: {block_start_date}")
            else:
                block_start_date = date
            
            # Создаем datetime для начала и конца блока
            block_start_dt = datetime.combine(block_start_date, block_start)
            block_end_dt = datetime.combine(date, block_end)
            
            # Обработка случая когда блок переходит через полночь (без учета from_previous_day)
            if not from_previous_day and block_end <= block_start:
                block_end_dt += timedelta(days=1)
            
            # Фильтруем свечи в диапазоне блока
            mask = (
                (self.price_data['timestamp'] >= block_start_dt) & 
                (self.price_data['timestamp'] < block_end_dt)
            )
            
            block_candles = self.price_data[mask]
            
            # Если недостаточно данных
            if len(block_candles) == 0:
                logger.warning(f"Нет данных для БЛОКА {date} {block_start}-{block_end} (from_previous_day={from_previous_day})")
                return None
            
            # Рассчитываем границы
            range_high = block_candles['high'].max()
            range_low = block_candles['low'].min()
            range_size = range_high - range_low
            
            result = {
                'range_high': float(range_high),
                'range_low': float(range_low),
                'range_size': float(range_size),
                'candle_count': len(block_candles),
                'block_start': block_start_dt,
                'block_end': block_end_dt
            }
            
            logger.debug(f"БЛОК {date}: High={range_high:.2f}, Low={range_low:.2f}, Size={range_size:.2f}, Свечей={len(block_candles)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при расчете БЛОКА для {date}: {str(e)}")
            return None
    
    def get_session_data(self, date: datetime.date, session_start: time, session_end: time) -> pd.DataFrame:
        """
        Возвращает DataFrame со свечами для указанной СЕССИИ.
        
        Args:
            date: Дата для анализа
            session_start: Время начала СЕССИИ (UTC)
            session_end: Время окончания СЕССИИ (UTC)
        
        Returns:
            DataFrame со свечами сессии или пустой DataFrame
        """
        try:
            # Создаем datetime для начала и конца сессии
            session_start_dt = datetime.combine(date, session_start)
            session_end_dt = datetime.combine(date, session_end)
            
            # Обработка случая когда сессия переходит через полночь
            if session_end <= session_start:
                session_end_dt += timedelta(days=1)
            
            # Фильтруем свечи в диапазоне сессии
            mask = (
                (self.price_data['timestamp'] >= session_start_dt) & 
                (self.price_data['timestamp'] <= session_end_dt)
            )
            
            session_candles = self.price_data[mask].copy()
            
            if len(session_candles) == 0:
                logger.warning(f"Нет данных для СЕССИИ {date} {session_start}-{session_end}")
                return pd.DataFrame()
            
            logger.debug(f"СЕССИЯ {date}: найдено {len(session_candles)} свечей")
            
            return session_candles
            
        except Exception as e:
            logger.error(f"Ошибка при получении данных СЕССИИ для {date}: {str(e)}")
            return pd.DataFrame()
    
    def filter_trading_days(self, start_date: datetime.date, end_date: datetime.date, 
                          trading_days: List[int]) -> List[datetime.date]:
        """
        Возвращает список дат для анализа с учетом торговых дней недели.
        
        Args:
            start_date: Начальная дата периода
            end_date: Конечная дата периода
            trading_days: Список дней недели для торговли (0=понедельник, 6=воскресенье)
        
        Returns:
            Список дат для анализа
        """
        try:
            # Генерируем все даты в диапазоне
            date_range = pd.date_range(start=start_date, end=end_date, freq='D')
            
            # Фильтруем по дням недели
            trading_dates = [
                d.date() for d in date_range 
                if d.weekday() in trading_days
            ]
            
            # Дополнительно фильтруем по наличию данных
            available_dates = self.price_data['date'].unique()
            
            filtered_dates = [
                d for d in trading_dates 
                if d in available_dates
            ]
            
            logger.info(f"Отфильтровано {len(filtered_dates)} торговых дней из {len(trading_dates)}")
            
            return filtered_dates
            
        except Exception as e:
            logger.error(f"Ошибка при фильтрации торговых дней: {str(e)}")
            return []
    
    def has_high_impact_news_in_day(self, check_date: datetime.date, 
                                    currency_filter: List[str] = None) -> bool:
        """
        Проверяет наличие красных (high impact) новостей в течение всего дня.
        
        Args:
            check_date: Дата для проверки
            currency_filter: Список валют для фильтрации (если None, проверяются все валюты)
        
        Returns:
            True если есть красные новости в этот день, False если нет
        """
        # Если новости не загружены, не блокируем
        if self.news_data is None or len(self.news_data) == 0:
            return False
        
        try:
            # Фильтруем новости по дате
            day_news = self.news_data[self.news_data['date'] == check_date]
            
            if len(day_news) == 0:
                return False
            
            # Фильтруем только красные новости
            high_impact_news = day_news[day_news['impact'] == 'high']
            
            if len(high_impact_news) == 0:
                return False
            
            # Если указаны валюты для фильтрации
            if currency_filter and len(currency_filter) > 0:
                # Проверяем наличие колонки Currency или currency
                if 'Currency' in high_impact_news.columns:
                    high_impact_news = high_impact_news[high_impact_news['Currency'].isin(currency_filter)]
                elif 'currency' in high_impact_news.columns:
                    high_impact_news = high_impact_news[high_impact_news['currency'].isin(currency_filter)]
            
            # Если после фильтрации остались новости - день блокируется
            if len(high_impact_news) > 0:
                logger.info(f"День {check_date} имеет {len(high_impact_news)} красных новостей")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке красных новостей для {check_date}: {str(e)}")
            return False
    
    def check_news_window(self, timestamp: datetime, impact_filter: List[str], 
                         buffer_minutes: int, currency_filter: List[str] = None) -> bool:
        """
        Проверяет наличие блокирующих новостей в окне ±buffer_minutes от timestamp.
        
        Args:
            timestamp: Время для проверки
            impact_filter: Список уровней важности новостей для фильтрации (например: ['high', 'medium'])
            buffer_minutes: Размер окна в минутах до и после новости
            currency_filter: Список валют для фильтрации
        
        Returns:
            True если есть блокирующие новости, False если нет или новости не загружены
        """
        # Если новости не загружены, не блокируем
        if self.news_data is None or len(self.news_data) == 0:
            return False
        
        try:
            # Создаем временное окно
            window_start = timestamp - timedelta(minutes=buffer_minutes)
            window_end = timestamp + timedelta(minutes=buffer_minutes)
            
            # Фильтруем новости по важности
            filtered_news = self.news_data[
                self.news_data['impact'].isin(impact_filter)
            ]
            
            # Добавляем фильтрацию по валютам
            if currency_filter and len(currency_filter) > 0:
                # Проверяем наличие колонки Currency
                if 'Currency' in filtered_news.columns:
                    filtered_news = filtered_news[filtered_news['Currency'].isin(currency_filter)]
                elif 'currency' in filtered_news.columns:
                    filtered_news = filtered_news[filtered_news['currency'].isin(currency_filter)]
            
            # Проверяем попадание в окно
            news_in_window = filtered_news[
                (filtered_news['timestamp'] >= window_start) & 
                (filtered_news['timestamp'] <= window_end)
            ]
            
            if len(news_in_window) > 0:
                logger.debug(f"Найдено {len(news_in_window)} блокирующих новостей около {timestamp}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при проверке новостного окна: {str(e)}")
            return False
    
    def get_start_position(self, session_start_time: datetime, block_range: Dict) -> str:
        """
        Определяет позицию цены относительно диапазона БЛОКА на старте СЕССИИ.
        
        Args:
            session_start_time: Время начала сессии
            block_range: Словарь с границами блока (range_high, range_low)
        
        Returns:
            'INSIDE' - цена внутри диапазона
            'ABOVE' - цена выше диапазона
            'BELOW' - цена ниже диапазона
        """
        try:
            # Находим свечу перед началом сессии
            candles_before = self.price_data[
                self.price_data['timestamp'] < session_start_time
            ]
            
            if len(candles_before) == 0:
                logger.warning(f"Нет данных перед началом сессии {session_start_time}")
                return 'INSIDE'  # По умолчанию
            
            # Берем последнюю свечу перед сессией
            last_candle = candles_before.iloc[-1]
            start_price = last_candle['close']
            
            # Определяем позицию
            if start_price > block_range['range_high']:
                position = 'ABOVE'
            elif start_price < block_range['range_low']:
                position = 'BELOW'
            else:
                position = 'INSIDE'
            
            logger.debug(f"Позиция на старте сессии: {position} (цена={start_price:.2f})")
            
            return position
            
        except Exception as e:
            logger.error(f"Ошибка при определении стартовой позиции: {str(e)}")
            return 'INSIDE'  # По умолчанию
    
    def get_price_at_time(self, target_time: datetime) -> Optional[float]:
        """
        Вспомогательный метод для получения цены на конкретное время.
        
        Args:
            target_time: Время для которого нужна цена
        
        Returns:
            Цена close ближайшей свечи или None
        """
        try:
            # Находим ближайшую свечу
            time_diff = abs(self.price_data['timestamp'] - target_time)
            closest_idx = time_diff.idxmin()
            
            # Проверяем что разница не слишком большая (макс 15 минут)
            if time_diff[closest_idx] > timedelta(minutes=15):
                return None
            
            return float(self.price_data.loc[closest_idx, 'close'])
            
        except Exception as e:
            logger.error(f"Ошибка при получении цены для {target_time}: {str(e)}")
            return None
    
    def validate_data_quality(self) -> Dict[str, Union[bool, str, int]]:
        """
        Проверяет качество загруженных данных.
        
        Returns:
            Словарь с результатами проверки
        """
        validation_results = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'candle_count': len(self.price_data),
            'date_range': None,
            'missing_data': False
        }
        
        try:
            # Проверка минимального количества данных
            if len(self.price_data) < 100:
                validation_results['warnings'].append(f"Мало данных: только {len(self.price_data)} свечей")
            
            # Проверка диапазона дат
            min_date = self.price_data['timestamp'].min()
            max_date = self.price_data['timestamp'].max()
            validation_results['date_range'] = f"{min_date.date()} - {max_date.date()}"
            
            # Проверка на пропуски в данных (большие временные разрывы)
            time_diffs = self.price_data['timestamp'].diff()
            max_gap = time_diffs.max()
            
            if max_gap > timedelta(hours=24):
                validation_results['warnings'].append(f"Найдены пропуски в данных: макс разрыв {max_gap}")
                validation_results['missing_data'] = True
            
            # Проверка корректности цен
            price_columns = ['open', 'high', 'low', 'close']
            for col in price_columns:
                if self.price_data[col].isna().any():
                    validation_results['errors'].append(f"Найдены NaN значения в колонке {col}")
                    validation_results['is_valid'] = False
                
                if (self.price_data[col] <= 0).any():
                    validation_results['errors'].append(f"Найдены некорректные цены <= 0 в колонке {col}")
                    validation_results['is_valid'] = False
            
            # Проверка логики OHLC
            invalid_candles = self.price_data[
                (self.price_data['high'] < self.price_data['low']) |
                (self.price_data['high'] < self.price_data['open']) |
                (self.price_data['high'] < self.price_data['close']) |
                (self.price_data['low'] > self.price_data['open']) |
                (self.price_data['low'] > self.price_data['close'])
            ]
            
            if len(invalid_candles) > 0:
                validation_results['errors'].append(f"Найдено {len(invalid_candles)} свечей с некорректными OHLC")
                validation_results['is_valid'] = False
            
            # Информация о новостях
            if self.news_data is not None:
                validation_results['news_count'] = len(self.news_data)
                validation_results['news_date_range'] = f"{self.news_data['timestamp'].min().date()} - {self.news_data['timestamp'].max().date()}"
            else:
                validation_results['news_count'] = 0
                validation_results['warnings'].append("Новостные данные не загружены")
            
        except Exception as e:
            validation_results['errors'].append(f"Ошибка при валидации: {str(e)}")
            validation_results['is_valid'] = False
        
        return validation_results