"""
Statistical Analyzer - Статистический анализ торговых данных
Главный файл Streamlit приложения
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import io

# Импорт модулей анализа
from rolling_window import analyze_rolling_windows
from series_analyzer import analyze_series, analyze_series_by_period
from temporal_analyzer import (
    analyze_by_hour, analyze_by_weekday, analyze_seasonality,
    calculate_holding_times, analyze_entry_types, analyze_directions
)

# Настройка страницы
st.set_page_config(
    page_title="Statistical Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Инициализация session state
if 'data' not in st.session_state:
    st.session_state.data = None
if 'filtered_data' not in st.session_state:
    st.session_state.filtered_data = None

# Заголовок
st.title("📊 Statistical Analyzer")
st.markdown("**Статистический анализ торговых данных с R-метриками**")

# Боковая панель с настройками
with st.sidebar:
    st.header("⚙️ Настройки анализа")
    
    # Основные параметры
    st.subheader("📈 Параметры R")
    target_r = st.number_input(
        "TARGET R (целевая прибыль)",
        min_value=1.0,
        max_value=50.0,
        value=5.0,
        step=0.5,
        help="Целевое значение прибыли в R-единицах"
    )
    
    drawdown_r = st.number_input(
        "DRAWDOWN R (критическая просадка)",
        min_value=-50.0,
        max_value=-1.0,
        value=-10.0,
        step=0.5,
        help="Критическое значение просадки в R-единицах"
    )
    
    st.subheader("📊 Rolling Window")
    rolling_window_days = st.slider(
        "Размер окна (торговые дни)",
        min_value=5,
        max_value=30,
        value=10,
        help="Размер скользящего окна в торговых днях"
    )
    
    st.subheader("🔄 Режим серий")
    ignore_be_no_trade = st.checkbox(
        "Игнорировать BE/NO_TRADE в сериях",
        value=False,
        help="Если включено, BE и NO_TRADE не прерывают серии TP/SL"
    )
    
    # Фильтры данных
    st.markdown("---")
    st.subheader("🔍 Фильтры данных")
    
    if st.session_state.data is not None:
        df = st.session_state.data
        
        # Фильтр по датам
        min_date = pd.to_datetime(df['date']).min()
        max_date = pd.to_datetime(df['date']).max()
        
        date_range = st.date_input(
            "Диапазон дат",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            help="Выберите период для анализа"
        )
        
        # Фильтр по типам входов
        all_entry_types = df['entry_type'].unique().tolist()
        selected_entry_types = st.multiselect(
            "Типы входов",
            options=all_entry_types,
            default=all_entry_types,
            help="Выберите типы входов для анализа"
        )
        
        # Фильтр по направлениям
        all_directions = df['direction'].unique().tolist()
        selected_directions = st.multiselect(
            "Направления",
            options=all_directions,
            default=all_directions,
            help="Выберите направления для анализа"
        )
        
        # Кнопка применения фильтров
        if st.button("🔄 Применить фильтры", type="primary"):
            # Применение фильтров
            filtered = df.copy()
            filtered['date_dt'] = pd.to_datetime(filtered['date'])
            
            # Фильтр по датам
            if len(date_range) == 2:
                start_date, end_date = date_range
                filtered = filtered[
                    (filtered['date_dt'] >= pd.to_datetime(start_date)) &
                    (filtered['date_dt'] <= pd.to_datetime(end_date))
                ]
            
            # Фильтр по типам входов
            filtered = filtered[filtered['entry_type'].isin(selected_entry_types)]
            
            # Фильтр по направлениям
            filtered = filtered[filtered['direction'].isin(selected_directions)]
            
            st.session_state.filtered_data = filtered
            st.success(f"✅ Фильтры применены: {len(filtered)} записей")

# Основная область
# Загрузка данных
st.header("📁 Загрузка данных")

uploaded_file = st.file_uploader(
    "Загрузите CSV файл с торговыми данными",
    type=['csv'],
    help="Файл должен содержать колонки: date, entry_type, direction, result, r_result и др."
)

if uploaded_file is not None:
    try:
        # Загрузка CSV
        df = pd.read_csv(uploaded_file)
        
        # Проверка необходимых колонок
        required_columns = ['date', 'entry_type', 'direction', 'result', 'r_result']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"❌ Отсутствуют необходимые колонки: {', '.join(missing_columns)}")
        else:
            st.session_state.data = df
            st.session_state.filtered_data = df.copy()
            
            # Информация о данных
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Всего записей", len(df))
            with col2:
                unique_dates = pd.to_datetime(df['date']).nunique()
                st.metric("Торговых дней", unique_dates)
            with col3:
                total_r = df['r_result'].sum()
                st.metric("Суммарный R", f"{total_r:.2f}")
            with col4:
                avg_r = df[df['result'] != 'NO_TRADE']['r_result'].mean()
                st.metric("Средний R", f"{avg_r:.2f}")
            
            st.success("✅ Данные успешно загружены!")
            
    except Exception as e:
        st.error(f"❌ Ошибка при загрузке файла: {str(e)}")

# Анализ данных
if st.session_state.filtered_data is not None:
    df = st.session_state.filtered_data
    
    st.markdown("---")
    st.header("📊 Результаты анализа")
    
    # Создаем вкладки для разных типов анализа
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📈 Серии сделок",
        "🎯 Rolling Window",
        "📊 Экстремальные R",
        "🎪 Типы входов",
        "🔄 Направления",
        "⏰ Временные паттерны"
    ])
    
    with tab1:
        st.subheader("📈 Анализ серий сделок")
        
        # Анализ серий
        series_results = analyze_series_by_period(df, ignore_be_no_trade)
        
        # Режим анализа
        mode_text = "Режим: BE/NO_TRADE игнорируются" if ignore_be_no_trade else "Режим: BE/NO_TRADE прерывают серию"
        st.info(mode_text)
        
        # Общая статистика
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Серии SL подряд (весь период)")
            total_sl = series_results['total']['sl_distribution_text']
            st.text(total_sl)
            st.metric("Максимум SL подряд", series_results['total']['sl_max_series'])
        
        with col2:
            st.markdown("### Серии TP подряд (весь период)")
            total_tp = series_results['total']['tp_distribution_text']
            st.text(total_tp)
            st.metric("Максимум TP подряд", series_results['total']['tp_max_series'])
        
        # По годам
        st.markdown("### Анализ по годам")
        years_data = []
        for year, data in series_results['by_year'].items():
            years_data.append({
                'Год': year,
                'Max TP подряд': data['tp_max_series'],
                'Max SL подряд': data['sl_max_series'],
                'Средняя серия TP': round(data['tp_avg_series'], 2),
                'Средняя серия SL': round(data['sl_avg_series'], 2)
            })
        if years_data:
            st.dataframe(pd.DataFrame(years_data), use_container_width=True)
    
    with tab2:
        st.subheader("🎯 Rolling Window анализ")
        
        # Анализ rolling window
        window_results = analyze_rolling_windows(df, rolling_window_days, target_r, drawdown_r)
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"📊 Размер окна: {rolling_window_days} дней")
            st.info(f"🎯 Target R: {target_r}")
            st.metric(
                "Достижение TARGET_R",
                f"{window_results['target_reached_count']} окон",
                f"{window_results['target_reached_pct']:.1f}%"
            )
        with col2:
            st.info(f"📉 Drawdown R: {drawdown_r}")
            st.info(f"📅 Всего окон: {window_results['total_windows']}")
            st.metric(
                "Достижение DRAWDOWN_R",
                f"{window_results['drawdown_reached_count']} окон",
                f"{window_results['drawdown_reached_pct']:.1f}%"
            )
        
        # Статистика
        st.markdown("### Статистика по окнам")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Средний R за окно", f"{window_results['avg_r_per_window']:.2f}")
        with col2:
            st.metric("Лучшее окно", f"{window_results['best_window_r']:.2f}R")
        with col3:
            st.metric("Худшее окно", f"{window_results['worst_window_r']:.2f}R")
        
        # Распределение
        st.markdown("### Распределение R по окнам")
        if 'distribution_visual' in window_results:
            st.text(window_results['distribution_visual'])
    
    with tab3:
        st.subheader("📊 Экстремальные значения R")
        
        # Подготовка данных для анализа экстремумов
        df['date_dt'] = pd.to_datetime(df['date'])
        df['year'] = df['date_dt'].dt.year
        df['month'] = df['date_dt'].dt.to_period('M')
        
        # Фильтруем только исполненные сделки
        executed = df[df['result'] != 'NO_TRADE']
        
        # Общие экстремумы
        extremes_data = []
        
        # Весь период
        if len(executed) > 0:
            extremes_data.append({
                'Период': 'Весь период',
                'Max R': f"{executed['r_result'].max():.2f}",
                'Min R': f"{executed['r_result'].min():.2f}",
                'Размах': f"{(executed['r_result'].max() - executed['r_result'].min()):.2f}"
            })
        
        # По годам
        for year in sorted(df['year'].unique()):
            year_data = executed[executed['year'] == year]
            if len(year_data) > 0:
                extremes_data.append({
                    'Период': f'{year} год',
                    'Max R': f"{year_data['r_result'].max():.2f}",
                    'Min R': f"{year_data['r_result'].min():.2f}",
                    'Размах': f"{(year_data['r_result'].max() - year_data['r_result'].min()):.2f}"
                })
        
        # По месяцам текущего года
        current_year = df['year'].max()
        for month in sorted(df[df['year'] == current_year]['month'].unique()):
            month_data = executed[executed['month'] == month]
            if len(month_data) > 0:
                extremes_data.append({
                    'Период': str(month),
                    'Max R': f"{month_data['r_result'].max():.2f}",
                    'Min R': f"{month_data['r_result'].min():.2f}",
                    'Размах': f"{(month_data['r_result'].max() - month_data['r_result'].min()):.2f}"
                })
        
        if extremes_data:
            st.table(pd.DataFrame(extremes_data))
    
    with tab4:
        st.subheader("🎪 Анализ типов входов")
        
        # Анализ типов входов
        entry_analysis = analyze_entry_types(df)
        
        # Таблица с результатами
        if entry_analysis['entry_stats']:
            entry_df = pd.DataFrame(entry_analysis['entry_stats'])
            
            # Форматируем для отображения
            display_columns = ['entry_type', 'total_signals', 'executed_trades', 
                             'tp_count', 'sl_count', 'be_count', 'no_trade_count',
                             'avg_r', 'total_r', 'win_rate']
            
            st.dataframe(
                entry_df[display_columns],
                use_container_width=True,
                hide_index=True
            )
            
            # Лучший и худший тип
            col1, col2 = st.columns(2)
            with col1:
                if entry_analysis['best_entry_type']:
                    st.success(f"✅ Лучший тип: {entry_analysis['best_entry_type']['entry_type']} "
                             f"(avg R: {entry_analysis['best_entry_type']['avg_r']})")
            with col2:
                if entry_analysis['worst_entry_type']:
                    st.error(f"❌ Худший тип: {entry_analysis['worst_entry_type']['entry_type']} "
                           f"(avg R: {entry_analysis['worst_entry_type']['avg_r']})")
    
    with tab5:
        st.subheader("🔄 Анализ направлений")
        
        # Анализ направлений
        direction_analysis = analyze_directions(df)
        
        # Таблица с результатами
        if direction_analysis['direction_stats']:
            direction_df = pd.DataFrame(direction_analysis['direction_stats'])
            
            st.dataframe(
                direction_df,
                use_container_width=True,
                hide_index=True
            )
            
            # Сравнение
            if direction_analysis['comparison']:
                comp = direction_analysis['comparison']
                st.info(f"📊 Лучшее направление: **{comp['better_direction']}** "
                       f"(разница avg R: {comp['avg_r_difference']}, "
                       f"разница win rate: {comp['win_rate_difference']}%)")
    
    with tab6:
        st.subheader("⏰ Временные паттерны")
        
        # Выбор типа анализа
        time_analysis = st.selectbox(
            "Выберите тип анализа",
            ["По часам", "По дням недели", "Сезонность", "Время удержания"]
        )
        
        if time_analysis == "По часам":
            hourly = analyze_by_hour(df)
            
            # Лучшие и худшие часы
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 🏆 Лучшие часы")
                for i, hour in enumerate(hourly['best_hours'], 1):
                    st.success(f"{i}. {hour['hour']} - avg R: {hour['avg_r']} ({hour['total_trades']} сделок)")
            
            with col2:
                st.markdown("### 📉 Худшие часы")
                for i, hour in enumerate(hourly['worst_hours'], 1):
                    st.error(f"{i}. {hour['hour']} - avg R: {hour['avg_r']} ({hour['total_trades']} сделок)")
            
            # Полная таблица
            if hourly['hourly_stats']:
                st.markdown("### Статистика по всем часам")
                hourly_df = pd.DataFrame(hourly['hourly_stats'])
                st.dataframe(hourly_df, use_container_width=True, hide_index=True)
        
        elif time_analysis == "По дням недели":
            weekday = analyze_by_weekday(df)
            
            # Таблица
            if weekday['weekday_stats']:
                weekday_df = pd.DataFrame(weekday['weekday_stats'])
                st.dataframe(weekday_df, use_container_width=True, hide_index=True)
            
            # Лучший и худший день
            col1, col2 = st.columns(2)
            with col1:
                if weekday['best_day']:
                    st.success(f"✅ Лучший день: {weekday['best_day']['weekday']} "
                             f"(avg R: {weekday['best_day']['avg_r']})")
            with col2:
                if weekday['worst_day']:
                    st.error(f"❌ Худший день: {weekday['worst_day']['weekday']} "
                           f"(avg R: {weekday['worst_day']['avg_r']})")
        
        elif time_analysis == "Сезонность":
            seasonality = analyze_seasonality(df)
            
            # Таблица по месяцам
            if seasonality['monthly_stats']:
                monthly_df = pd.DataFrame(seasonality['monthly_stats'])
                st.dataframe(monthly_df, use_container_width=True, hide_index=True)
            
            # Квартальная статистика
            st.markdown("### Квартальная статистика")
            if seasonality['quarterly_stats']:
                quarters_df = pd.DataFrame([seasonality['quarterly_stats']])
                st.dataframe(quarters_df, use_container_width=True, hide_index=True)
                
                if seasonality['best_quarter']:
                    st.success(f"✅ Лучший квартал: {seasonality['best_quarter']}")
                if seasonality['worst_quarter']:
                    st.error(f"❌ Худший квартал: {seasonality['worst_quarter']}")
        
        else:  # Время удержания
            holding = calculate_holding_times(df)
            
            # Статистика по типам
            for result_type in ['tp', 'sl', 'be']:
                key = f'{result_type}_holding'
                if key in holding:
                    data = holding[key]
                    st.markdown(f"### {result_type.upper()} сделки")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Среднее время", data['avg_formatted'])
                    with col2:
                        st.metric("Медиана", data['median_formatted'])
                    with col3:
                        st.metric("Количество", data['count'])
            
            # Сравнение скорости
            if 'speed_comparison' in holding:
                comp = holding['speed_comparison']
                st.info(f"⚡ Быстрее достигается: **{comp['faster_result']}** "
                       f"(разница: {comp['speed_difference_formatted']})")
    
    # Экспорт результатов
    st.markdown("---")
    st.header("💾 Экспорт результатов")
    
    if st.button("📥 Экспортировать полный отчет в CSV", type="primary"):
        # Подготовка данных для экспорта
        output = io.StringIO()
        
        # Записываем параметры анализа
        output.write("# ПАРАМЕТРЫ АНАЛИЗА\n")
        output.write(f"TARGET_R,{target_r}\n")
        output.write(f"DRAWDOWN_R,{drawdown_r}\n")
        output.write(f"ROLLING_WINDOW_DAYS,{rolling_window_days}\n")
        output.write(f"IGNORE_BE_NO_TRADE,{ignore_be_no_trade}\n")
        output.write(f"Дата анализа,{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Основные метрики
        output.write("\n# ОСНОВНЫЕ МЕТРИКИ\n")
        output.write(f"Всего записей,{len(df)}\n")
        output.write(f"Торговых дней,{pd.to_datetime(df['date']).nunique()}\n")
        output.write(f"Суммарный R,{df['r_result'].sum():.2f}\n")
        
        # Серии
        output.write("\n# АНАЛИЗ СЕРИЙ\n")
        output.write(f"Max TP подряд,{series_results['total']['tp_max_series']}\n")
        output.write(f"Max SL подряд,{series_results['total']['sl_max_series']}\n")
        
        # Rolling Window
        output.write("\n# ROLLING WINDOW\n")
        output.write(f"Всего окон,{window_results['total_windows']}\n")
        output.write(f"Target достигнут,{window_results['target_reached_count']} ({window_results['target_reached_pct']:.1f}%)\n")
        output.write(f"Drawdown достигнут,{window_results['drawdown_reached_count']} ({window_results['drawdown_reached_pct']:.1f}%)\n")
        
        # Исходные данные
        output.write("\n# ОТФИЛЬТРОВАННЫЕ ДАННЫЕ\n")
        df.to_csv(output, index=False)
        
        # Создаем кнопку скачивания
        st.download_button(
            label="💾 Скачать полный отчет CSV",
            data=output.getvalue(),
            file_name=f"statistical_analysis_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        st.success("✅ Отчет готов к скачиванию!")

else:
    st.info("👆 Загрузите CSV файл для начала анализа")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Statistical Analyzer v1.0 | R-ориентированный анализ торговых стратегий
    </div>
    """,
    unsafe_allow_html=True
)