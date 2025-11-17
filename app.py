import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta, date
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, List, Optional, Tuple
import json
import io
import logging


# Импорт модулей системы
logger = logging.getLogger(__name__)
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator
from chart_visualizer import ChartVisualizer
from optimizer import TradingOptimizer  # НОВЫЙ ИМПОРТ


# Функции для работы с точностью отображения цен
def format_price(value, precision=None):
    """Форматирует цену с нужной точностью для отображения"""
    if value is None or pd.isna(value):
        return ""
    p = precision if precision is not None else st.session_state.get('price_precision', 2)
    return f"{value:.{p}f}"

def detect_precision(df):
    """Определяет количество знаков после запятой в ценовых данных"""
    sample = df[['open', 'high', 'low', 'close']].head(100).values.flatten()
    max_decimals = 0
    for price in sample:
        if pd.notna(price):
            str_price = str(float(price))
            if '.' in str_price:
                decimals = len(str_price.rstrip('0').split('.')[1])
                max_decimals = max(max_decimals, decimals)
    return min(max_decimals, 8)


# Настройка страницы
st.set_page_config(
    page_title="Trading Analyzer v10.0",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Инициализация session state
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'price_data' not in st.session_state:
    st.session_state.price_data = None
if 'news_data' not in st.session_state:
    st.session_state.news_data = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'daily_trades_df' not in st.session_state:
    st.session_state.daily_trades_df = None
if 'summary_report' not in st.session_state:
    st.session_state.summary_report = None

# Навигация для результатов
if 'view_level' not in st.session_state:
    st.session_state.view_level = 'overview'
if 'selected_year' not in st.session_state:
    st.session_state.selected_year = None
if 'selected_month' not in st.session_state:
    st.session_state.selected_month = None

# Сохранение состояния загруженных файлов
if 'price_file_info' not in st.session_state:
    st.session_state.price_file_info = None
if 'news_file_info' not in st.session_state:
    st.session_state.news_file_info = None

# НОВЫЕ session state для оптимизации
if 'optimization_results' not in st.session_state:
    st.session_state.optimization_results = None
if 'optimization_running' not in st.session_state:
    st.session_state.optimization_running = False
if 'price_precision' not in st.session_state:
    st.session_state.price_precision = 2  # По умолчанию 2 знака

# Заголовок приложения
st.title("📊 Trading Analyzer v10.0")
st.markdown("**R-ориентированная система анализа торговых стратегий**")

# Боковая панель для навигации
with st.sidebar:
    st.markdown("## 🧭 Навигация")
    section = st.radio(
        "Выберите раздел:",
        ["📁 Загрузка данных", "⚙️ Настройки", "📈 Результаты", "🔧 Оптимизация"],  # ДОБАВЛЕН НОВЫЙ РАЗДЕЛ
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.markdown("### 📋 Статус системы")
    if st.session_state.data_loaded:
        st.success("✅ Данные загружены")
        if st.session_state.price_file_info:
            st.caption(f"📊 Цены: {st.session_state.price_file_info['name']}")
            st.caption(f"└─ {st.session_state.price_file_info['rows']} свечей")
        if st.session_state.news_file_info:
            st.caption(f"📰 Новости: {st.session_state.news_file_info['name']}")
            st.caption(f"└─ {st.session_state.news_file_info['rows']} событий")
    else:
        st.warning("⏳ Данные не загружены")
    
    if st.session_state.summary_report:
        st.info("📊 Анализ выполнен")
    
    if st.session_state.optimization_results:
        st.success("🎯 Оптимизация выполнена")


# Раздел: Загрузка данных
if section == "📁 Загрузка данных":
    st.header("📁 Загрузка данных")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🕯️ Данные о ценах")
        
        # Показываем текущий статус
        if st.session_state.price_data is not None:
            st.success(f"✅ Загружено: {st.session_state.price_file_info['name']}")
            with st.expander("📊 Информация о данных"):
                st.info(f"""
                **Период данных:**
                - Начало: {st.session_state.price_file_info['start_date']}
                - Конец: {st.session_state.price_file_info['end_date']}
                - Всего дней: {st.session_state.price_file_info['total_days']}
                - Всего свечей: {st.session_state.price_file_info['rows']}
                """)
        
        price_file = st.file_uploader(
            "Загрузите CSV файл с ценовыми данными",
            type=['csv'],
            help="Файл должен содержать колонки: time (или timestamp), open, high, low, close",
            key="price_file_uploader"  # Добавлен явный ключ
        )
        
        # Временное хранилище для обработанных данных
        temp_price_data = None
        temp_price_info = None
        
        if price_file is not None:
            try:
                # Загрузка данных
                price_df = pd.read_csv(price_file)
                
                # Проверка и переименование колонок
                if 'time' in price_df.columns:
                    price_df = price_df.rename(columns={'time': 'timestamp'})
                
                # Проверка необходимых колонок
                required_columns = ['timestamp', 'open', 'high', 'low', 'close']
                if all(col in price_df.columns for col in required_columns):
                    # Преобразование timestamp
                    price_df['timestamp'] = pd.to_datetime(price_df['timestamp'])
                    price_df = price_df.sort_values('timestamp')
                    
                    # Подготавливаем информацию о файле
                    temp_price_info = {
                        'name': price_file.name,
                        'rows': len(price_df),
                        'start_date': price_df['timestamp'].min().strftime('%Y-%m-%d %H:%M'),
                        'end_date': price_df['timestamp'].max().strftime('%Y-%m-%d %H:%M'),
                        'total_days': (price_df['timestamp'].max() - price_df['timestamp'].min()).days
                    }
                    
                    temp_price_data = price_df
                    st.success(f"✅ Файл проверен: {len(price_df)} свечей")

                    # Определение и настройка точности
                    detected_precision = detect_precision(temp_price_data)
                    st.markdown("### ⚙️ Настройка точности отображения")
                    precision = st.number_input(
                        "Количество знаков после запятой",
                        min_value=0,
                        max_value=8,
                        value=detected_precision,
                        help=f"Автоматически определено: {detected_precision} знаков. Можно изменить вручную.",
                        key="temp_precision"
                    )
                    
                else:
                    st.error(f"❌ Отсутствуют необходимые колонки: {required_columns}")
                    
            except Exception as e:
                st.error(f"❌ Ошибка при загрузке файла: {str(e)}")
    
    with col2:
        st.subheader("📰 Данные о новостях (опционально)")
        
        # Показываем текущий статус
        if st.session_state.news_data is not None:
            st.success(f"✅ Загружено: {st.session_state.news_file_info['name']}")
            with st.expander("📰 Статистика новостей"):
                impact_counts = st.session_state.news_data['impact'].value_counts()
                st.info(f"""
                **Статистика новостей:**
                - High Impact: {impact_counts.get('high', 0)}
                - Medium Impact: {impact_counts.get('medium', 0)}
                - Low Impact: {impact_counts.get('low', 0)}
                - Всего событий: {st.session_state.news_file_info['rows']}
                """)
        
        news_file = st.file_uploader(
            "Загрузите CSV файл с новостными событиями",
            type=['csv'],
            help="Файл должен содержать колонки: DateTime_UTC (или timestamp), Impact (или impact), Event",
            key="news_file_uploader"  # Добавлен явный ключ
        )
        
        # Временное хранилище для обработанных данных
        temp_news_data = None
        temp_news_info = None
        
        if news_file is not None:
            try:
                news_df = pd.read_csv(news_file)
                
                # Проверка и переименование колонок
                if 'DateTime_UTC' in news_df.columns:
                    news_df = news_df.rename(columns={'DateTime_UTC': 'timestamp'})
                if 'Impact' in news_df.columns:
                    news_df = news_df.rename(columns={'Impact': 'impact'})
                
                # Проверка необходимых колонок
                required_columns = ['timestamp', 'impact']
                if all(col in news_df.columns for col in required_columns):
                    # Преобразование timestamp
                    news_df['timestamp'] = pd.to_datetime(news_df['timestamp'])
                    news_df = news_df.sort_values('timestamp')
                    
                    # Подготавливаем информацию о файле
                    temp_news_info = {
                        'name': news_file.name,
                        'rows': len(news_df)
                    }
                    
                    temp_news_data = news_df
                    st.success(f"✅ Файл проверен: {len(news_df)} новостных событий")
                    
                else:
                    st.error(f"❌ Отсутствуют необходимые колонки: {required_columns}")
                    
            except Exception as e:
                st.error(f"❌ Ошибка при загрузке файла: {str(e)}")
    
    # Кнопка для применения загруженных данных
    st.markdown("---")
    col1_btn, col2_btn = st.columns(2)
    
    with col1_btn:
        # Проверяем наличие новых данных для загрузки
        has_new_price = price_file is not None and 'temp_price_data' in locals() and temp_price_data is not None
        has_new_news = news_file is not None and 'temp_news_data' in locals() and temp_news_data is not None
        
        if has_new_price or has_new_news:
            if st.button("✅ Применить загруженные данные", type="primary", use_container_width=True):
                # Применяем данные о ценах
                if has_new_price:
                    st.session_state.price_data = temp_price_data
                    st.session_state.price_file_info = temp_price_info
                    st.session_state.data_loaded = True
                    # Применяем выбранную точность
                if 'temp_precision' in st.session_state:
                    st.session_state.price_precision = st.session_state.temp_precision
                
                # Применяем данные о новостях
                if has_new_news:
                    st.session_state.news_data = temp_news_data
                    st.session_state.news_file_info = temp_news_info
                
                st.success("✅ Данные успешно загружены!")
                st.balloons()
                st.rerun()
    
    with col2_btn:
        if st.session_state.data_loaded:
            if st.button("🗑️ Очистить все данные", use_container_width=True):
                st.session_state.price_data = None
                st.session_state.news_data = None
                st.session_state.price_file_info = None
                st.session_state.news_file_info = None
                st.session_state.data_loaded = False
                st.session_state.analysis_results = None
                st.session_state.daily_trades_df = None
                st.session_state.summary_report = None
                st.info("🗑️ Все данные очищены")
                st.rerun()


# Раздел: Настройки
elif section == "⚙️ Настройки":
    st.header("⚙️ Настройки стратегии")
    
    if not st.session_state.data_loaded:
        st.warning("⚠️ Сначала загрузите данные о ценах")
    else:
        # Создаем табы для разных групп настроек
        tab1, tab2, tab3, tab4 = st.tabs(["📊 Основные", "🎯 TP/SL", "📰 Новости", "💾 Сохранение"])
        
        with tab1:
            st.subheader("🕐 Временные настройки")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**📦 Настройки БЛОКА**")
                block_start = st.time_input(
                    "Начало БЛОКА (UTC)",
                    value=time(0, 0),
                    help="Время начала формирования ценового диапазона",
                    key="block_start"
                )
                
                block_end = st.time_input(
                    "Конец БЛОКА (UTC)",
                    value=time(13, 0),
                    help="Время окончания формирования ценового диапазона",
                    key="block_end"
                )
                
                # ========== НОВОЕ: Checkbox для БЛОКА с предыдущего дня ==========
                from_previous_day = st.checkbox(
                    "📅 Начать БЛОК с предыдущего дня",
                    value=False,
                    help="Если активно, БЛОК начинается с указанного времени предыдущего дня",
                    key="from_previous_day"
                )
                
                # Изменяем информацию если checkbox активен
                if from_previous_day:
                    st.info("⚠️ БЛОК начнется с предыдущего дня в указанное время")
                # ==================================================================
                
                st.markdown("**📏 Фильтры размера диапазона**")
                # Определяем точность и значения по умолчанию
                precision = st.session_state.get('price_precision', 2)
                if precision <= 2:
                    default_min_range = 100.0
                    default_max_range = 500.0
                else:
                    default_min_range = float(10**(-precision+2))
                    default_max_range = float(10**(-precision+3))
                
                min_range_size = st.number_input(
                    "Минимальный размер диапазона",
                    min_value=0.0,
                    value=default_min_range,
                    step=float(10**(-precision)),
                    format=f"%.{precision}f",
                    help="Минимальный размер диапазона БЛОКА в единицах цены",
                    key="min_range_size"
                )
                
                max_range_size = st.number_input(
                    "Максимальный размер диапазона",
                    min_value=0.0,
                    value=default_max_range,
                    step=float(10**(-precision)),
                    format=f"%.{precision}f",
                    help="Максимальный размер диапазона БЛОКА в единицах цены",
                    key="max_range_size"
                )
               
                
            with col2:
                st.markdown("**🎯 Настройки СЕССИИ**")
                session_start = st.time_input(
                    "Начало СЕССИИ (UTC)",
                    value=time(14, 0),
                    help="Время начала торговой сессии",
                    key="session_start"
                )
                
                session_end = st.time_input(
                    "Конец СЕССИИ (UTC)",
                    value=time(20, 0),
                    help="Время окончания торговой сессии",
                    key="session_end"
                )
                
                st.markdown("**🔄 Режим работы**")
                use_return_mode = st.selectbox(
                    "Выберите режим:",
                    options=[False, True],
                    format_func=lambda x: "🎯 По-тренду" if not x else "🔄 Возвратный",
                    help="По-тренду: торговля в направлении пробоя. Возвратный: торговля от границ внутрь.",
                    key="use_return_mode"
                )
                
                st.markdown("**📅 Торговые дни**")
                trading_days = st.multiselect(
                    "Выберите дни недели:",
                    options=[0, 1, 2, 3, 4, 5, 6],
                    default=[0, 1, 2, 3, 4],
                    format_func=lambda x: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][x],
                    help="Дни недели для анализа",
                    key="trading_days"
                )
        
        with tab2:
            st.subheader("🎯 Настройки Take Profit и Stop Loss")
            
            # Обычные настройки TP/SL
            col1, col2 = st.columns(2)
            
            with col1:
                tp_multiplier = st.slider(
                    "Take Profit множитель",
                    min_value=0.2,
                    max_value=3.0,
                    value=1.0,
                    step=0.1,
                    help="TP = entry_price ± (range_size × tp_multiplier)",
                    key="tp_multiplier"
                )
                
                sl_multiplier = st.slider(
                    "Stop Loss множитель",
                    min_value=0.2,
                    max_value=3.0,
                    value=1.0,
                    step=0.1,
                    help="SL = entry_price ± (range_size × sl_multiplier)",
                    key="sl_multiplier"
                )
                
            with col2:
                tp_coefficient = st.slider(
                    "🎯 Коэффициент R для TP",
                    min_value=0.5,
                    max_value=1.0,
                    value=0.9,
                    step=0.05,
                    help="Применяется только к прибыльным сделкам для учета комиссий",
                    key="tp_coefficient"
                )
                
                st.info("""
                💡 **Коэффициент R для TP**
                
                Используется для учета комиссий и спредов.
                - При коэффициенте 0.9: сделка с результатом 1.5R будет записана как 1.35R
                - Применяется только к прибыльным сделкам (TP)
                - SL и BE не изменяются
                """)
                
                target_r = st.number_input(
                    "Целевой R-результат",
                    min_value=1.0,
                    max_value=20.0,
                    value=5.0,
                    step=0.5,
                    help="Целевой R-результат для анализа скорости достижения",
                    key="target_r"
                )
            
            # НОВЫЙ РАЗДЕЛ: Фиксированные TP/SL
            st.markdown("---")
            st.markdown("### 🔧 Фиксированные TP/SL при выходе за пороги")
            
            use_fixed_tp_sl = st.checkbox(
                "Использовать фиксированные TP/SL при выходе диапазона за пороги",
                value=False,
                help="Если диапазон БЛОКА меньше минимального порога или больше максимального, использовать фиксированные значения вместо множителей",
                key="use_fixed_tp_sl"
            )
            
            if use_fixed_tp_sl:
                # Определяем точность для отображения на основе загруженных данных
                precision = st.session_state.get('price_precision', 2)
                
                st.info(f"""
                📏 **Настройка порогов и фиксированных значений**
                
                Точность отображения: {precision} знаков после запятой
                Примеры для разных инструментов:
                - XAUUSD: пороги 80.1 / 100.245, TP=3.5, SL=2.0
                - EURUSD: пороги 0.00200 / 0.00300, TP=0.00015, SL=0.00010
                """)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**📊 Пороговые значения диапазона**")
                    
                    # Автоматическая подстройка значений по умолчанию в зависимости от точности
                    if precision <= 2:
                        default_min = 80.0
                        default_max = 120.0
                        default_tp = 3.0
                        default_sl = 2.0
                    else:
                        default_min = float(10**(-precision+2))
                        default_max = float(10**(-precision+2) * 3)
                        default_tp = float(10**(-precision+1) * 5)
                        default_sl = float(10**(-precision+1) * 3)
                    
                    threshold_min = st.number_input(
                        "Минимальный порог диапазона",
                        min_value=0.0,
                        value=default_min,
                        step=float(10**(-precision)),
                        format=f"%.{precision}f",
                        help="Если размер диапазона меньше этого значения, используются фиксированные TP/SL",
                        key="threshold_min"
                    )
                    
                    threshold_max = st.number_input(
                        "Максимальный порог диапазона",
                        min_value=0.0,
                        value=default_max,
                        step=float(10**(-precision)),
                        format=f"%.{precision}f",
                        help="Если размер диапазона больше этого значения, используются фиксированные TP/SL",
                        key="threshold_max"
                    )
                
                with col2:
                    st.markdown("**🎯 Фиксированные значения TP/SL**")
                    
                    fixed_tp_distance = st.number_input(
                        "Фиксированное расстояние до TP",
                        min_value=0.0,
                        value=default_tp,
                        step=float(10**(-precision)),
                        format=f"%.{precision}f",
                        help="Фиксированное расстояние от цены входа до Take Profit в единицах цены",
                        key="fixed_tp_distance"
                    )
                    
                    fixed_sl_distance = st.number_input(
                        "Фиксированное расстояние до SL",
                        min_value=0.0,
                        value=default_sl,
                        step=float(10**(-precision)),
                        format=f"%.{precision}f",
                        help="Фиксированное расстояние от цены входа до Stop Loss в единицах цены",
                        key="fixed_sl_distance"
                    )
                
                # Пример расчета
                st.markdown("**📊 Пример применения:**")
                example_range = (threshold_min + threshold_max) / 2
                st.info(f"""
                При текущих настройках:
                - Диапазон < {format_price(threshold_min, precision)} → TP = вход ± {format_price(fixed_tp_distance, precision)}, SL = вход ± {format_price(fixed_sl_distance, precision)}
                - Диапазон {format_price(threshold_min, precision)} - {format_price(threshold_max, precision)} → обычный расчет через множители
                - Диапазон > {format_price(threshold_max, precision)} → TP = вход ± {format_price(fixed_tp_distance, precision)}, SL = вход ± {format_price(fixed_sl_distance, precision)}
                
                R-ratio при фиксированных: {(fixed_tp_distance / fixed_sl_distance if fixed_sl_distance > 0 else 0):.2f}
                """)
            else:
                # Показываем только стандартный пример
                st.markdown("**📊 Пример расчета:**")
                st.info(f"""
                При размере диапазона 100 пунктов:
                - TP расстояние: {100 * tp_multiplier:.0f} пунктов
                - SL расстояние: {100 * sl_multiplier:.0f} пунктов
                - R-ratio: {tp_multiplier / sl_multiplier:.2f}
                - Фактический R для TP: {(tp_multiplier / sl_multiplier) * tp_coefficient:.2f}
                """)
        
        with tab3:
            st.subheader("📰 Фильтрация новостей")
            
            use_news_filter = st.checkbox(
                "Использовать фильтр новостей",
                value=False,
                help="Блокировать входы перед важными новостями",
                key="use_news_filter"
            )
            
            if use_news_filter:
                col1, col2 = st.columns(2)
                
                with col1:
                    news_impact_filter = st.multiselect(
                        "Важность новостей для фильтрации",
                        options=['high', 'medium', 'low'],
                        default=['high'],
                        help="Какие новости учитывать при фильтрации",
                        key="news_impact_filter"
                    )
                    
                    news_currency_filter = st.multiselect(
                        "Валюты для фильтрации",
                        options=['EUR', 'USD', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD', 'CNY'],
                        default=['EUR', 'USD'],
                        help="Блокировать входы при новостях по выбранным валютам",
                        key="news_currency_filter"
                    )
                    
                with col2:
                    news_buffer_minutes = st.number_input(
                        "Буферное время (минуты)",
                        min_value=0,
                        max_value=120,
                        value=30,
                        step=5,
                        help="Время до/после новости для блокировки входов",
                        key="news_buffer_minutes"
                    )
                    
                    # ========== НОВОЕ: Checkbox для пропуска дней с красными новостями ==========
                    skip_red_news_days = st.checkbox(
                        "🚫 Пропускать дни с красными новостями",
                        value=False,
                        help="Полностью пропускать торговые дни с красными новостями по выбранным валютам",
                        key="skip_red_news_days"
                    )
                    
                    if skip_red_news_days:
                        st.warning("⚠️ Дни с красными новостями будут полностью исключены из анализа")
                    # ===========================================================================
        
        with tab4:
            st.subheader("💾 Сохранение настроек")
            
            # Загрузка настроек из JSON
            st.markdown("### 📥 Загрузка настроек")
            settings_file = st.file_uploader(
                "Загрузите JSON файл с настройками",
                type=['json'],
                help="Загрузите ранее сохраненные настройки"
            )
            
            if settings_file is not None:
                try:
                    loaded_settings = json.load(settings_file)
                    if st.button("📥 Применить загруженные настройки", type="primary"):
                        # Применяем настройки через session_state
                        for key, value in loaded_settings.items():
                            if key in ['block_start', 'block_end', 'session_start', 'session_end']:
                                # Преобразуем строки времени обратно в time объекты
                                st.session_state[key] = datetime.strptime(value, '%H:%M').time()
                            elif key in ['start_date', 'end_date']:
                                # Преобразуем строки дат
                                st.session_state[key] = datetime.strptime(value, '%Y-%m-%d').date()
                            else:
                                st.session_state[key] = value
                        
                        st.success(f"✅ Настройки загружены из {settings_file.name}")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Ошибка при загрузке настроек: {str(e)}")
            
            st.markdown("---")
            
            # Период анализа
            st.markdown("### 📅 Период анализа")
            col1, col2 = st.columns(2)
            with col1:
                # Изменено значение по умолчанию для более широкого периода
                start_date = st.date_input(
                    "Начальная дата анализа",
                    value=datetime.now().date() - timedelta(days=730),  # 2 года назад
                    help="Начало периода для анализа",
                    key="start_date"
                )
            with col2:
                end_date = st.date_input(
                    "Конечная дата анализа",
                    value=datetime.now().date(),
                    help="Конец периода для анализа",
                    key="end_date"
                )
            
            st.markdown("---")
            st.markdown("### 💾 Сохранение настроек")
            
            settings_name = st.text_input(
                "Название пресета",
                value=f"Settings_{datetime.now().strftime('%Y%m%d_%H%M')}",
                help="Введите название для сохранения текущих настроек"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("💾 Сохранить настройки", type="primary"):
                    settings = {
                        'block_start': block_start.strftime('%H:%M'),
                        'block_end': block_end.strftime('%H:%M'),
                        'session_start': session_start.strftime('%H:%M'),
                        'session_end': session_end.strftime('%H:%M'),
                        'use_return_mode': use_return_mode,
                        'trading_days': trading_days,
                        'tp_multiplier': tp_multiplier,
                        'sl_multiplier': sl_multiplier,
                        'tp_coefficient': tp_coefficient,
                        'target_r': target_r,
                        'min_range_size': min_range_size,
                        'max_range_size': max_range_size,
                        'use_news_filter': use_news_filter,
                        'news_impact_filter': news_impact_filter if use_news_filter else [],
                        'news_buffer_minutes': news_buffer_minutes if use_news_filter else 0,
                        'news_currency_filter': news_currency_filter if use_news_filter else [],
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d'),
                        # НОВЫЕ параметры для фиксированных TP/SL
                        'use_fixed_tp_sl': use_fixed_tp_sl,
                        'threshold_min': st.session_state.get('threshold_min', 0) if use_fixed_tp_sl else 0,
                        'threshold_max': st.session_state.get('threshold_max', float('inf')) if use_fixed_tp_sl else float('inf'),
                        'fixed_tp_distance': st.session_state.get('fixed_tp_distance', 0) if use_fixed_tp_sl else 0,
                        'fixed_sl_distance': st.session_state.get('fixed_sl_distance', 0) if use_fixed_tp_sl else 0,
                        # ========== НОВЫЕ параметры для новых функций ==========
                        'from_previous_day': from_previous_day,  # Добавляем флаг БЛОКА с предыдущего дня
                        'skip_red_news_days': skip_red_news_days if use_news_filter else False,  # Добавляем флаг пропуска дней
                        # ========================================================
                    }
                    
                    # Сохраняем в session state
                    if 'saved_settings' not in st.session_state:
                        st.session_state.saved_settings = {}
                    
                    st.session_state.saved_settings[settings_name] = settings
                    st.session_state.current_settings = settings
                    st.success(f"✅ Настройки '{settings_name}' сохранены")
            
            with col2:
                if st.button("📥 Скачать настройки как JSON"):
                    if 'current_settings' in st.session_state:
                        settings_json = json.dumps(st.session_state.current_settings, indent=2)
                        st.download_button(
                            label="📥 Скачать JSON",
                            data=settings_json,
                            file_name=f"{settings_name}.json",
                            mime="application/json"
                        )
# Раздел: Результаты
elif section == "📈 Результаты":
    st.header("📈 Результаты анализа")
    
    if not st.session_state.data_loaded:
        st.warning("⚠️ Сначала загрузите данные о ценах")
    else:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button("🚀 Запустить анализ", type="primary", use_container_width=True):
                if 'current_settings' not in st.session_state:
                    st.error("❌ Сначала сохраните настройки в разделе Настройки")
                else:
                    with st.spinner("🔄 Выполняется анализ..."):
                        try:
                            settings = st.session_state.current_settings
                            
                            # Создание экземпляров классов
                            data_processor = DataProcessor(
                                st.session_state.price_data,
                                st.session_state.news_data
                            )
                            analyzer = TradingAnalyzer(data_processor)
                            r_calculator = RCalculator()
                            optimizer = TradingOptimizer(data_processor, analyzer, r_calculator)
                            report_generator = ReportGenerator(r_calculator)
                            
                            # ВАЖНО: Сохраняем оптимизатор в session_state
                            st.session_state.optimizer = optimizer
                            
                            
                            # Преобразование строковых времен обратно в time объекты
                            settings_for_analysis = settings.copy()
                            settings_for_analysis['block_start'] = datetime.strptime(settings['block_start'], '%H:%M').time()
                            settings_for_analysis['block_end'] = datetime.strptime(settings['block_end'], '%H:%M').time()
                            settings_for_analysis['session_start'] = datetime.strptime(settings['session_start'], '%H:%M').time()
                            settings_for_analysis['session_end'] = datetime.strptime(settings['session_end'], '%H:%M').time()
                            settings_for_analysis['start_date'] = datetime.strptime(settings['start_date'], '%Y-%m-%d').date()
                            settings_for_analysis['end_date'] = datetime.strptime(settings['end_date'], '%Y-%m-%d').date()
                            
                            # Запуск анализа
                            analysis_results = analyzer.analyze_period(
                                settings_for_analysis['start_date'],
                                settings_for_analysis['end_date'],
                                settings_for_analysis
                            )
                            
                            # Генерация отчетов
                            daily_trades_df = report_generator.prepare_daily_trades(
                                analysis_results['results'], 
                                settings['tp_coefficient']
                            )
                            summary_report = report_generator.generate_summary_report(daily_trades_df)
                            
                            # Сохранение в session_state
                            st.session_state.analysis_results = analysis_results
                            st.session_state.daily_trades_df = daily_trades_df
                            st.session_state.summary_report = summary_report
                            st.session_state.view_level = 'overview'
                            
                            st.success("✅ Анализ выполнен успешно!")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ Ошибка при анализе: {str(e)}")
                            
        with col2:
            if st.button("🗑️ Очистить результаты", use_container_width=True):
                st.session_state.analysis_results = None
                st.session_state.daily_trades_df = None
                st.session_state.summary_report = None
                st.session_state.view_level = 'overview'
                st.session_state.selected_year = None
                st.session_state.selected_month = None
                st.rerun()
            
            # Временная кнопка для полной очистки (можно удалить после решения проблемы)
            if st.button("🔥 Полная очистка кеша", use_container_width=True, help="Используйте если обычная очистка не помогает"):
                for key in list(st.session_state.keys()):
                    if key not in ['data_loaded', 'price_data', 'news_data', 'price_file_info', 'news_file_info']:
                        del st.session_state[key]
                st.success("✅ Кеш полностью очищен")
                st.rerun()
        
        # Отображение результатов
        if st.session_state.summary_report is not None:
            # Навигационные хлебные крошки
            breadcrumb_cols = st.columns(4)
            with breadcrumb_cols[0]:
                if st.session_state.view_level != 'overview':
                    if st.button("📊 Обзор"):
                        st.session_state.view_level = 'overview'
                        st.session_state.selected_year = None
                        st.session_state.selected_month = None
                        st.rerun()
            
            with breadcrumb_cols[1]:
                if st.session_state.view_level in ['year', 'month'] and st.session_state.selected_year:
                    if st.button(f"📅 {st.session_state.selected_year}"):
                        st.session_state.view_level = 'year'
                        st.session_state.selected_month = None
                        st.rerun()
            
            with breadcrumb_cols[2]:
                if st.session_state.view_level == 'month' and st.session_state.selected_month:
                    st.button(f"📆 {st.session_state.selected_month}", disabled=True)
            
            st.markdown("---")
            
            # УРОВЕНЬ 1: Обзор и годовые отчеты
            if st.session_state.view_level == 'overview':
                st.subheader("📊 Общий обзор")
                
                # Основные метрики
                report = st.session_state.summary_report
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric(
                        "Всего R-результат",
                        f"{report['total_r']:.2f}R",
                        delta=f"{report['average_r_per_month']:.2f}R/мес"
                    )
                
                with col2:
                    st.metric(
                        "Исполнено сделок",
                        report['total_executed_trades'],
                        delta=f"{report['average_r_per_trade']:.2f}R/сделка"
                    )
                
                with col3:
                    win_rate = 0
                    if report['total_executed_trades'] > 0:
                        # Исправлен расчет win_rate - используем правильное поле
                        win_rate = (report['total_tp'] / report['total_executed_trades'] * 100)
                    st.metric(
                        "Win Rate",
                        f"{win_rate:.1f}%",
                        delta=None
                    )
                
                with col4:
                    # Отображаем более точное значение периода
                    years_str = f"{report['total_years']:.1f}" if report['total_years'] != int(report['total_years']) else str(int(report['total_years']))
                    st.metric(
                        "Период анализа",
                        f"{years_str} лет",
                        delta=f"{report['total_trading_days']} дней"
                    )
                
                # График накопительного R
                st.markdown("### 📈 Накопительный R-результат")
                if report['cumulative_r_series']:
                    # Используем ChartVisualizer для создания графика
                    chart_viz = ChartVisualizer()
                    fig = chart_viz.create_cumulative_r_chart(
                        dates=report['dates_series'],
                        r_values=report['cumulative_r_series']
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Нет данных для графика")
                
                # Кнопка экспорта всех данных
                st.markdown("### 📥 Экспорт данных")
                if st.button("📥 Экспорт всех данных в CSV", type="primary"):
                    if st.session_state.daily_trades_df is not None and not st.session_state.daily_trades_df.empty:
                        # Подготавливаем полные данные для экспорта
                        # Используем только существующие колонки
                        available_columns = st.session_state.daily_trades_df.columns.tolist()
                        
                        # Отладка: показываем доступные колонки
                        with st.expander("🔍 Отладка: доступные колонки"):
                            st.write("Колонки в DataFrame:", available_columns)
                            st.write("Первая строка данных:", st.session_state.daily_trades_df.iloc[0].to_dict() if not st.session_state.daily_trades_df.empty else "Нет данных")
                        
                        # Базовые колонки, которые должны быть всегда
                        base_columns = ['date', 'weekday', 'entry_type', 'direction', 
                                       'range_size', 'entry_time', 'entry_price', 
                                       'exit_time', 'exit_price', 'result', 
                                       'r_result', 'close_reason']
                        
                        # Дополнительные колонки, которые могут быть или не быть
                        optional_columns = ['tp_points', 'sl_points']
                        
                        # Формируем список колонок для экспорта
                        export_columns = []
                        for col in base_columns:
                            if col in available_columns:
                                export_columns.append(col)
                        
                        for col in optional_columns:
                            if col in available_columns:
                                export_columns.append(col)
                        
                        export_df = st.session_state.daily_trades_df[export_columns].copy()
                        
                        # Создаем CSV
                        csv = export_df.to_csv(index=False)
                        
                        # Предлагаем скачать
                        st.download_button(
                            label="💾 Скачать CSV файл",
                            data=csv,
                            file_name=f"trading_analyzer_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                        
                        # Информируем если не все данные доступны
                        missing_columns = [col for col in optional_columns if col not in available_columns]
                        if missing_columns:
                            st.info(f"ℹ️ Для полного экспорта перезапустите анализ. Отсутствуют поля: {', '.join(missing_columns)}")
                    else:
                        st.warning("Нет данных для экспорта")
                
                # Таблица годовых отчетов
                st.markdown("### 📅 Годовые отчеты")
                
                yearly_data = []
                for year_report in report['yearly_reports']:
                    yearly_data.append({
                        'Год': year_report['year'],
                        'Торговых дней': year_report['total_trading_days'],
                        'Сделок': year_report['executed_trades'],
                        'R-результат': f"{year_report['total_r']:.2f}",
                        'Средний R': f"{year_report['average_r_per_trade']:.2f}",
                        'Win Rate': f"{year_report['win_rate']:.1f}%",
                        'Лучший месяц': year_report['best_month']
                    })
                
                yearly_df = pd.DataFrame(yearly_data)
                
                # Интерактивная таблица
                selected_year = st.dataframe(
                    yearly_df,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row"
                )
                
                if selected_year and len(selected_year.selection.rows) > 0:
                    selected_idx = selected_year.selection.rows[0]
                    st.session_state.selected_year = yearly_df.iloc[selected_idx]['Год']
                    st.session_state.view_level = 'year'
                    st.rerun()
            
            # УРОВЕНЬ 2: Месячные отчеты выбранного года
            elif st.session_state.view_level == 'year' and st.session_state.selected_year:
                year = st.session_state.selected_year
                st.subheader(f"📅 Отчет за {year} год")
                
                # Найти годовой отчет
                year_report = None
                for yr in st.session_state.summary_report['yearly_reports']:
                    if yr['year'] == year:
                        year_report = yr
                        break
                
                if year_report:
                    # Метрики года
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric(
                            "R-результат года",
                            f"{year_report['total_r']:.2f}R",
                            delta=f"{year_report['average_r_per_month']:.2f}R/мес"
                        )
                    
                    with col2:
                        st.metric(
                            "Сделок за год",
                            year_report['executed_trades'],
                            delta=f"{year_report['average_r_per_trade']:.2f}R/сделка"
                        )
                    
                    with col3:
                        st.metric(
                            "Win Rate",
                            f"{year_report['win_rate']:.1f}%"
                        )
                    
                    with col4:
                        st.metric(
                            "Лучший месяц",
                            year_report['best_month'],
                            delta=f"{year_report['best_month_r']:.2f}R"
                        )
                    
                    # График накопительного R за год
                    st.markdown("### 📈 Накопительный R за год")
                    if year_report['cumulative_r_series']:
                        # Используем ChartVisualizer для создания графика
                        chart_viz = ChartVisualizer()
                        months = [f"{year}-{i:02d}" for i in range(1, 13)]
                        fig = chart_viz.create_yearly_cumulative_chart(
                            year=year,
                            months=months,
                            r_values=year_report['cumulative_r_series']
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    
                    # Таблица месячных отчетов
                    st.markdown("### 📆 Месячные отчеты")
                    
                    monthly_data = []
                    for month_report in year_report['months_data']:
                        monthly_data.append({
                            'Месяц': month_report['month'],
                            'Дней': month_report['trading_days'],
                            'Сделок': month_report['executed_trades'],
                            'R-результат': f"{month_report['total_r']:.2f}",
                            'Средний R': f"{month_report['average_r_per_trade']:.2f}",
                            'TP': month_report['tp_count'],
                            'SL': month_report['sl_count'],
                            'BE': month_report['be_count'],
                            'Win Rate': f"{month_report['win_rate']:.1f}%"
                        })
                    
                    monthly_df = pd.DataFrame(monthly_data)
                    
                    # Интерактивная таблица
                    selected_month = st.dataframe(
                        monthly_df,
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    if selected_month and len(selected_month.selection.rows) > 0:
                        selected_idx = selected_month.selection.rows[0]
                        st.session_state.selected_month = monthly_df.iloc[selected_idx]['Месяц']
                        st.session_state.view_level = 'month'
                        st.rerun()
            
            # УРОВЕНЬ 3: Дневные сделки выбранного месяца
            elif st.session_state.view_level == 'month' and st.session_state.selected_month:
                month = st.session_state.selected_month
                st.subheader(f"📆 Сделки за {month}")
                
                # Фильтры
                with st.expander("🔍 Фильтры", expanded=False):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        filter_results = st.multiselect(
                            "Результаты",
                            options=['TP', 'SL', 'BE', 'NO_TRADE'],
                            default=['TP', 'SL', 'BE']
                        )
                        
                        filter_entry_types = st.multiselect(
                            "Типы входов",
                            options=[
                                'ENTRY_LONG_TREND', 'ENTRY_SHORT_TREND',
                                'LIMIT_LONG_TREND', 'LIMIT_SHORT_TREND',
                                'ENTRY_LONG_REVERSE', 'ENTRY_SHORT_REVERSE',
                                'LIMIT_LONG_REVERSE', 'LIMIT_SHORT_REVERSE',
                                'INSIDE_BLOCK', 'OUTSIDE_BLOCK'
                            ]
                        )
                    
                    with col2:
                        r_min, r_max = st.slider(
                            "R-диапазон",
                            min_value=-3.0,
                            max_value=3.0,
                            value=(-3.0, 3.0),
                            step=0.1
                        )
                        
                        filter_weekdays = st.multiselect(
                            "Дни недели",
                            options=[0, 1, 2, 3, 4, 5, 6],
                            format_func=lambda x: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][x]
                        )
                    
                    with col3:
                        show_blocked = st.checkbox(
                            "Показать заблокированные новостями",
                            value=True
                        )
                
                # Применение фильтров
                filters = {
                    'results': filter_results if filter_results else None,
                    'entry_types': filter_entry_types if filter_entry_types else None,
                    'r_range': (r_min, r_max),
                    'weekdays': filter_weekdays if filter_weekdays else None,
                    'show_blocked': show_blocked
                }
                
                # Получение данных месяца
                month_df = st.session_state.daily_trades_df[
                    st.session_state.daily_trades_df['date'].str.startswith(month)
                ].copy()
                
                # Применение фильтров
                report_gen = ReportGenerator(RCalculator())
                filtered_df = report_gen.filter_trades(month_df, filters)
                
                # Отображение таблицы
                st.markdown(f"### 📊 Найдено сделок: {len(filtered_df)}")
                
                if not filtered_df.empty:
                    # Форматирование для отображения
                    # Проверяем какие колонки доступны
                    available_columns = filtered_df.columns.tolist()
                    
                    # Базовые колонки для отображения
                    display_columns = ['date', 'weekday', 'entry_type', 'direction', 
                                     'range_size', 'entry_time', 'entry_price', 
                                     'exit_time', 'exit_price', 'result', 'r_result', 
                                     'close_reason']
                    
                    # Добавляем новые колонки если они есть
                    if 'tp_points' in available_columns:
                        # Вставляем после exit_price
                        idx = display_columns.index('exit_price') + 1
                        display_columns.insert(idx, 'tp_points')
                        display_columns.insert(idx + 1, 'sl_points')
                    
                    # Фильтруем только существующие колонки
                    display_columns = [col for col in display_columns if col in available_columns]
                    
                    display_df = filtered_df[display_columns].copy()
                    
                    # Цветовое кодирование R-результатов
                    def color_r_result(val):
                        if pd.isna(val) or val == 0:
                            return ''
                        elif val > 0:
                            return 'color: green'
                        else:
                            return 'color: red'
                    
                    # Настройка форматирования с учетом точности
                    precision = st.session_state.get('price_precision', 2)
                    format_dict = {
                        'range_size': f'{{:.{precision}f}}',
                        'entry_price': f'{{:.{precision}f}}',
                        'exit_price': f'{{:.{precision}f}}',
                        'r_result': '{:.2f}'  # R всегда 2 знака
                    }
                    
                    # Добавляем форматирование для новых колонок если они есть
                    if 'tp_points' in display_df.columns:
                        format_dict['tp_points'] = f'{{:.{precision}f}}'
                        format_dict['sl_points'] = f'{{:.{precision}f}}'
                    
                    styled_df = display_df.style.applymap(
                        color_r_result, 
                        subset=['r_result']
                    ).format(format_dict, na_rep='')
                    
                    # Настройка отображения
                    column_config = {}
                    if 'tp_points' in display_df.columns:
                        column_config['tp_points'] = st.column_config.NumberColumn(
                            'TP (пункты)',
                            help='Размер Take Profit в пунктах'
                        )
                        column_config['sl_points'] = st.column_config.NumberColumn(
                            'SL (пункты)',
                            help='Размер Stop Loss в пунктах'
                        )
                    
                    st.dataframe(
                        styled_df,
                        use_container_width=True,
                        hide_index=True,
                        height=600,
                        column_config=column_config if column_config else None
                    )
                    
                    # Кнопка экспорта
                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Скачать CSV",
                        data=csv,
                        file_name=f"trades_{month}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Нет сделок, соответствующих выбранным фильтрам")
                
                # Статистика по отфильтрованным данным
                if not filtered_df.empty:
                    st.markdown("### 📊 Статистика отфильтрованных сделок")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    executed_df = filtered_df[filtered_df['result'].isin(['TP', 'SL', 'BE'])]
                    
                    with col1:
                        total_r = executed_df['r_result'].sum() if not executed_df.empty else 0
                        st.metric("Суммарный R", f"{total_r:.2f}")
                    
                    with col2:
                        avg_r = executed_df['r_result'].mean() if not executed_df.empty else 0
                        st.metric("Средний R", f"{avg_r:.2f}")
                    
                    with col3:
                        tp_count = len(filtered_df[filtered_df['result'] == 'TP'])
                        total_count = len(executed_df)
                        win_rate = (tp_count / total_count * 100) if total_count > 0 else 0
                        st.metric("Win Rate", f"{win_rate:.1f}%")
                    
                    with col4:
                        blocked_count = len(filtered_df[filtered_df['is_blocked'] == True])
                        st.metric("Заблокировано новостями", blocked_count)
                
                # Проверяем наличие новых полей
                if 'tp_points' not in filtered_df.columns:
                    st.info("ℹ️ Для отображения TP/SL в пунктах перезапустите анализ с обновленной версией")
        
        else:
            st.info("👆 Нажмите 'Запустить анализ' для начала")
            
            # Показываем статистику пропущенных дней если есть результаты анализа
            if st.session_state.analysis_results and 'skipped_days' in st.session_state.analysis_results:
                skipped = st.session_state.analysis_results['skipped_days']
                if skipped['total'] > 0:
                    st.markdown("### ⚠️ Пропущенные дни")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Всего пропущено", skipped['total'])
                    with col2:
                        st.metric("Нет данных", skipped['no_data'])
                    with col3:
                        st.metric("Малый диапазон", skipped['small_range'])
                    with col4:
                        st.metric("Большой диапазон", skipped['large_range'])
            
            # Диагностическая информация (можно удалить после отладки)
            if st.checkbox("🔍 Показать диагностическую информацию", value=False):
                if 'current_settings' in st.session_state:
                    st.json({
                        "Период анализа": {
                            "start_date": st.session_state.current_settings.get('start_date'),
                            "end_date": st.session_state.current_settings.get('end_date')
                        },
                        "Фильтры диапазона": {
                            "min_range_size": st.session_state.current_settings.get('min_range_size'),
                            "max_range_size": st.session_state.current_settings.get('max_range_size')
                        }
                    })
                
                if st.session_state.price_data is not None:
                    # Показываем доступные годы в загруженных данных
                    price_years = sorted(st.session_state.price_data['timestamp'].dt.year.unique())
                    st.info(f"📅 Годы в загруженных данных: {', '.join(map(str, price_years))}")

# НОВЫЙ РАЗДЕЛ: Оптимизация
elif section == "🔧 Оптимизация":
    st.header("🔧 Оптимизация параметров")
    
    # Проверка готовности системы
    if not st.session_state.data_loaded:
        st.warning("⚠️ Сначала загрузите данные о ценах")
    elif 'current_settings' not in st.session_state:
        st.warning("⚠️ Сначала сохраните настройки в разделе Настройки")
    else:
        # Основной интерфейс оптимизации
        st.markdown("### 🎯 Настройки оптимизации")
        
        col1, col2 = st.columns(2)
        
        with col1:
            optimization_target = st.selectbox(
                "Цель оптимизации",
                options=['max_total_r', 'max_days_above_threshold'],
                format_func=lambda x: {
                    'max_total_r': '📈 Максимальный суммарный R',
                    'max_days_above_threshold': '💰 Максимум дней с R > 0.35'
                }[x],
                help="Выберите метрику для оптимизации"
            )
        
        with col2:
            use_parallel = st.checkbox(
                "Использовать параллельную обработку",
                value=False,
                help="Ускоряет оптимизацию при большом количестве комбинаций (> 100)"
            )
        
        st.markdown("### 📊 Диапазоны параметров")
        
        # Настройка диапазона TP
        st.markdown("**Take Profit множитель**")
        tp_col1, tp_col2, tp_col3 = st.columns(3)
        with tp_col1:
            tp_min = st.number_input(
                "Минимум TP",
                min_value=0.1,
                max_value=10.0,
                value=0.5,
                step=0.1,
                key="opt_tp_min"
            )
        with tp_col2:
            tp_max = st.number_input(
                "Максимум TP",
                min_value=0.1,
                max_value=10.0,
                value=3.0,
                step=0.1,
                key="opt_tp_max"
            )
        with tp_col3:
            tp_step = st.number_input(
                "Шаг TP",
                min_value=0.05,
                max_value=1.0,
                value=0.1,
                step=0.05,
                key="opt_tp_step"
            )
        
        # Настройка диапазона SL
        st.markdown("**Stop Loss множитель**")
        sl_col1, sl_col2, sl_col3 = st.columns(3)
        with sl_col1:
            sl_min = st.number_input(
                "Минимум SL",
                min_value=0.1,
                max_value=10.0,
                value=0.5,
                step=0.1,
                key="opt_sl_min"
            )
        with sl_col2:
            sl_max = st.number_input(
                "Максимум SL",
                min_value=0.1,
                max_value=10.0,
                value=2.0,
                step=0.1,
                key="opt_sl_max"
            )
        with sl_col3:
            sl_step = st.number_input(
                "Шаг SL",
                min_value=0.05,
                max_value=1.0,
                value=0.1,
                step=0.05,
                key="opt_sl_step"
            )
        
        # Расчет количества комбинаций
        tp_count = int((tp_max - tp_min) / tp_step) + 1
        sl_count = int((sl_max - sl_min) / sl_step) + 1
        total_combinations = tp_count * sl_count
        
        # Информация о комбинациях
        st.info(f"""
        📊 **Параметры оптимизации:**
        - TP значений: {tp_count} (от {tp_min} до {tp_max} с шагом {tp_step})
        - SL значений: {sl_count} (от {sl_min} до {sl_max} с шагом {sl_step})
        - **Всего комбинаций: {total_combinations}**
        - Примерное время: {total_combinations * 0.5:.1f} - {total_combinations * 2:.1f} секунд
        """)
        
        # Кнопка запуска оптимизации
        if st.button("🚀 Запустить оптимизацию", type="primary", use_container_width=True):
            if total_combinations > 1000:
                st.warning("⚠️ Большое количество комбинаций может занять длительное время")
            
            st.session_state.optimization_running = True
            
            # Прогресс-бар
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(percent):
                progress_bar.progress(percent / 100)
                status_text.text(f"Обработано: {percent}%")
            
            try:
                # Создание экземпляров классов
                data_processor = DataProcessor(
                    st.session_state.price_data,
                    st.session_state.news_data
                )
                analyzer = TradingAnalyzer(data_processor)
                r_calculator = RCalculator()
                optimizer = TradingOptimizer(data_processor, analyzer, r_calculator)
                
                # Подготовка настроек
                settings = st.session_state.current_settings.copy()
                
                # Преобразование времен
                settings['block_start'] = datetime.strptime(settings['block_start'], '%H:%M').time()
                settings['block_end'] = datetime.strptime(settings['block_end'], '%H:%M').time()
                settings['session_start'] = datetime.strptime(settings['session_start'], '%H:%M').time()
                settings['session_end'] = datetime.strptime(settings['session_end'], '%H:%M').time()
                settings['start_date'] = datetime.strptime(settings['start_date'], '%Y-%m-%d').date()
                settings['end_date'] = datetime.strptime(settings['end_date'], '%Y-%m-%d').date()
                
                # Запуск оптимизации
                with st.spinner(f"🔄 Оптимизация {total_combinations} комбинаций..."):
                    optimization_results = optimizer.optimize_parameters(
                        settings=settings,
                        tp_range=(tp_min, tp_max, tp_step),
                        sl_range=(sl_min, sl_max, sl_step),
                        optimization_target=optimization_target,
                        progress_callback=update_progress,
                        use_parallel=use_parallel
                    )
                
                # Сохранение результатов
                st.session_state.optimization_results = optimization_results
                st.session_state.optimization_running = False
                # КРИТИЧЕСКИ ВАЖНО: Сохраняем кеш оптимизатора
                st.session_state.optimizer_cache = optimizer._results_cache.copy()
                st.session_state.optimizer_instance = optimizer
                
                progress_bar.progress(100)
                status_text.text("✅ Оптимизация завершена!")
                st.success(f"✅ Оптимизация завершена за {optimization_results['optimization_details']['computation_time']:.1f} сек")
                st.rerun()
                
            except Exception as e:
                st.session_state.optimization_running = False
                st.error(f"❌ Ошибка при оптимизации: {str(e)}")
        
        # Отображение результатов оптимизации
        if st.session_state.optimization_results is not None:
            st.markdown("---")
            st.markdown("## 📊 Результаты оптимизации")
            
            results = st.session_state.optimization_results
            
            # Лучшие параметры
            st.markdown("### 🏆 Лучшие параметры")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Лучший TP",
                    f"{results['best_params']['tp_multiplier']:.2f}"
                )
            
            with col2:
                st.metric(
                    "Лучший SL",
                    f"{results['best_params']['sl_multiplier']:.2f}"
                )
            
            with col3:
                st.metric(
                    "Значение метрики",
                    f"{results['best_metric']:.2f}"
                )
            
            with col4:
                r_ratio = results['best_params']['tp_multiplier'] / results['best_params']['sl_multiplier']
                st.metric(
                    "R-соотношение",
                    f"{r_ratio:.2f}"
                )
            
            # Кнопка применения лучших параметров
            if st.button("✅ Применить лучшие параметры к настройкам", type="primary"):
                st.session_state.tp_multiplier = results['best_params']['tp_multiplier']
                st.session_state.sl_multiplier = results['best_params']['sl_multiplier']
                
                # Обновляем current_settings
                if 'current_settings' in st.session_state:
                    st.session_state.current_settings['tp_multiplier'] = results['best_params']['tp_multiplier']
                    st.session_state.current_settings['sl_multiplier'] = results['best_params']['sl_multiplier']
                
                st.success("✅ Параметры применены! Перейдите в раздел Настройки для проверки")
            
            # Heatmap результатов
            st.markdown("### 🗺️ Тепловая карта результатов")
            
            # Создаем heatmap с plotly
            fig = go.Figure(data=go.Heatmap(
                z=results['results_grid'].values,
                x=results['results_grid'].columns,
                y=results['results_grid'].index,
                colorscale='RdYlGn',
                text=results['results_grid'].values.round(2),
                texttemplate='%{text}',
                textfont={"size": 10},
                colorbar=dict(title=dict(text="Метрика", side="right"))
            ))
            
            # Добавляем маркер для лучшей комбинации
            best_tp = results['best_params']['tp_multiplier']
            best_sl = results['best_params']['sl_multiplier']
            
            fig.add_trace(go.Scatter(
                x=[best_tp],
                y=[best_sl],
                mode='markers',
                marker=dict(
                    size=20,
                    color='red',
                    symbol='star',
                    line=dict(color='white', width=2)
                ),
                name='Лучший результат',
                showlegend=True
            ))
            
            fig.update_layout(
                title="Тепловая карта результатов оптимизации",
                xaxis_title="TP множитель",
                yaxis_title="SL множитель",
                height=600
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Таблица топ-10 комбинаций
            st.markdown("### 🏅 Топ-10 комбинаций")
            
            # Создаем экземпляр оптимизатора для использования метода get_top_combinations
            data_processor = DataProcessor(st.session_state.price_data, st.session_state.news_data)
            analyzer = TradingAnalyzer(data_processor)
            r_calculator = RCalculator()
            optimizer = TradingOptimizer(data_processor, analyzer, r_calculator)
            
            top_10 = optimizer.get_top_combinations(results['results_df'], 10)
            
            # Форматируем для отображения
            display_top_10 = top_10.copy()
            display_top_10 = display_top_10.round({
                'tp_multiplier': 2,
                'sl_multiplier': 2,
                'metric_value': 2,
                'total_r': 2,
                'win_rate': 1,
                'r_ratio': 2
            })
            
            st.dataframe(
                display_top_10,
                use_container_width=True,
                hide_index=True
            )
            
            # Экспорт результатов
            st.markdown("### 💾 Экспорт результатов")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Экспорт в CSV
                csv_data = results['results_df'].to_csv(index=False)
                st.download_button(
                    label="📥 Скачать все результаты (CSV)",
                    data=csv_data,
                    file_name=f"optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col2:
                # Экспорт сетки для анализа
                grid_csv = results['results_grid'].to_csv()
                st.download_button(
                    label="📥 Скачать сетку результатов (CSV)",
                    data=grid_csv,
                    file_name=f"optimization_grid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            # Детали оптимизации
            with st.expander("📋 Детали оптимизации"):
                st.json(results['optimization_details'])
            
            # Новый блок экспорта детальных результатов
            st.markdown("---")
            st.markdown("### 📁 Экспорт детальных результатов анализа")
            st.info("💡 Экспорт создает отдельный CSV файл для каждой комбинации TP/SL с полными данными по всем сделкам")
            
            # Проверяем что оптимизатор создан и есть данные в кеше
            if 'optimizer' not in st.session_state:
                # Создаем экземпляр оптимизатора если его нет
                data_processor = DataProcessor(st.session_state.price_data, st.session_state.news_data)
                analyzer = TradingAnalyzer(data_processor)
                r_calculator = RCalculator()
                st.session_state.optimizer = TradingOptimizer(data_processor, analyzer, r_calculator)
            
            optimizer = st.session_state.optimizer
            # Восстанавливаем кеш из session_state
            if 'optimizer_cache' in st.session_state:
                optimizer._results_cache = st.session_state.optimizer_cache
            
            # Проверяем количество комбинаций
            total_combinations = len(results['results_df'])
            
            col1, col2 = st.columns(2)
            
            with col1:
                export_mode = st.radio(
                    "Режим экспорта:",
                    ["top10", "all"],
                    format_func=lambda x: "📊 Топ-10 комбинаций" if x == "top10" else f"📈 Все комбинации ({total_combinations})",
                    help="Выберите какие комбинации экспортировать"
                )
                
                if export_mode == "all" and total_combinations > 100:
                    st.warning(f"⚠️ Будет создано {total_combinations} файлов. Это может занять время.")
            
            with col2:
                if st.button("🚀 Начать экспорт детальных результатов", type="primary"):
                    try:
                        # Создаем прогресс-бар
                        export_progress = st.progress(0)
                        export_status = st.empty()
                        
                        export_status.text("📂 Создание структуры папок...")
                        
                        # Получаем текущие настройки
                        settings = st.session_state.current_settings.copy()
                        
                        # Форматируем времена для папок
                        settings['block_start_time'] = settings.get('block_start', '00:00')
                        settings['block_end_time'] = settings.get('block_end', '23:59')
                        settings['session_start_time'] = settings.get('session_start', '00:00')
                        settings['session_end_time'] = settings.get('session_end', '23:59')
                        
                        # Функция обновления прогресса
                        def update_export_progress(percent):
                            export_progress.progress(percent)
                            export_status.text(f"📝 Экспорт файлов... {percent}%")
                        
                        # Запускаем экспорт
                        export_path = optimizer.export_detailed_results(
                            optimization_results=results,
                            settings=settings,
                            export_mode=export_mode,
                            progress_callback=update_export_progress
                        )
                        
                        export_progress.progress(100)
                        export_status.empty()
                        
                        # Показываем результат
                        st.success(f"✅ Экспорт завершен!")
                        st.info(f"📁 Файлы сохранены в папку:\n`{export_path}`")
                        
                        # Показываем информацию о структуре
                        with st.expander("📋 Структура экспортированных файлов"):
                            best_tp = str(results['best_params']['tp_multiplier']).replace('.', '_')
                            best_sl = str(results['best_params']['sl_multiplier']).replace('.', '_')
                            st.markdown(f"""
                            ```
                            {export_path}/
                            ├── export_info.txt  # Информация об экспорте
                            └── block_XXXX-XXXX_session_XXXX-XXXX/
                                ├── trading_analyzer_TP{best_tp}_SL{best_sl}.csv
                                └── ... другие комбинации
                            ```
                            
                            **Формат CSV файлов:**
                            - Такой же как в разделе "Результаты"
                            - Включает все колонки: дата, время, цены, результат, R-значение
                            - Готов для дальнейшего анализа в Excel или Python
                            """)
                        
                    except Exception as e:
                        st.error(f"❌ Ошибка при экспорте: {str(e)}")
                        logger.error(f"Ошибка экспорта детальных результатов: {str(e)}")
            
            # Информация о доступности данных
            if hasattr(optimizer, '_results_cache') and len(optimizer._results_cache) > 0:
                st.caption(f"✅ В кеше доступно {len(optimizer._results_cache)} комбинаций для экспорта")
            else:
                st.caption("⚠️ Перезапустите оптимизацию для обновления кеша данных")


# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Trading Analyzer v10.0 | R-ориентированная система анализа с оптимизацией
    </div>
    """,
    unsafe_allow_html=True
)