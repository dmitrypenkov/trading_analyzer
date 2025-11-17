"""
ATR Explorer - Простой и понятный анализатор волатильности
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import plotly.graph_objects as go
import json
import logging

# Импорт модулей
from atr_analyzer import ATRAnalyzer
from data_processor import DataProcessor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка страницы
st.set_page_config(
    page_title="ATR Explorer",
    page_icon="📈",
    layout="wide"
)

st.title("📈 ATR Explorer")
st.markdown("**Анализатор волатильности для поиска оптимальных временных окон**")

# Инициализация session state только для данных
if 'price_data' not in st.session_state:
    st.session_state.price_data = None
if 'atr_results' not in st.session_state:
    st.session_state.atr_results = None

# ========== БОКОВАЯ ПАНЕЛЬ ==========
with st.sidebar:
    st.header("⚙️ Настройки")
    
    # --- Загрузка данных ---
    st.subheader("📂 Загрузка данных")
    uploaded_file = st.file_uploader(
        "Выберите CSV файл",
        type=['csv'],
        help="Файл должен содержать колонки: time (или timestamp), open, high, low, close"
    )
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            
            # Проверка и переименование колонки времени
            if 'time' in df.columns:
                df = df.rename(columns={'time': 'timestamp'})
            elif 'timestamp' not in df.columns:
                st.error("❌ Не найдена колонка time или timestamp")
                st.stop()
            
            # Проверка остальных колонок
            required_cols = ['open', 'high', 'low', 'close']
            if not all(col in df.columns for col in required_cols):
                st.error(f"❌ Отсутствуют колонки: {[col for col in required_cols if col not in df.columns]}")
                st.stop()
            
            st.session_state.price_data = df
            st.success(f"✅ Загружено {len(df)} свечей")
            
        except Exception as e:
            st.error(f"❌ Ошибка при загрузке файла: {e}")
            st.stop()
    
    # Если данные не загружены, останавливаем выполнение
    if st.session_state.price_data is None:
        st.warning("⏸️ Загрузите данные для начала работы")
        st.stop()
    
    # Работаем с загруженными данными
    df = st.session_state.price_data
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Добавляем колонку date если её нет
    if 'date' not in df.columns:
        df['date'] = df['timestamp'].dt.date
    
    data_min_date = df['timestamp'].min().date()
    data_max_date = df['timestamp'].max().date()
    
    st.divider()
    
    # --- Настройки ATR ---
    st.subheader("📊 Параметры ATR")
    
    min_atr = st.number_input(
        "Минимальный ATR",
        min_value=1.0,
        value=20.0,
        step=1.0
    )
    
    max_atr = st.number_input(
        "Максимальный ATR",
        min_value=1.0,
        value=50.0,
        step=1.0
    )
    
    stability_threshold = st.slider(
        "Минимальная стабильность",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.05,
        help="1 - коэффициент вариации. Чем выше, тем стабильнее"
    )
    
    st.divider()
    
    # --- Настройки окна ---
    st.subheader("⏱️ Размер окна")
    
    window_size_candles = st.slider(
        "Размер окна (свечей)",
        min_value=1,
        max_value=48,
        value=12,
        help="1 свеча = 15 минут"
    )
    
    window_hours = window_size_candles * 0.25
    if window_hours >= 1:
        st.caption(f"📏 Это {window_hours:.1f} часов")
    else:
        st.caption(f"📏 Это {window_size_candles * 15} минут")
    
    st.divider()
    
    # --- Шаг поиска ---
    st.subheader("🔄 Шаг поиска")
    
    step_options = {
        "15 минут": 1,
        "30 минут": 2,
        "1 час": 4,
        "2 часа": 8,
        "4 часа": 16
    }
    
    selected_step = st.selectbox(
        "Шаг смещения окна",
        options=list(step_options.keys()),
        index=2  # По умолчанию 1 час
    )
    step_candles = step_options[selected_step]
    
    total_positions = 96 // step_candles
    st.caption(f"🎯 Будет проверено {total_positions} позиций")
    
    st.divider()
    
    # --- Период анализа ---
    st.subheader("📅 Период анализа")
    
    # По умолчанию последние 30 дней
    default_start = max(data_min_date, data_max_date - timedelta(days=30))
    
    # Используем отдельные виджеты для начальной и конечной даты
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Начало периода",
            value=default_start,
            min_value=data_min_date,
            max_value=data_max_date,
            key="start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "Конец периода",
            value=data_max_date,
            min_value=data_min_date,
            max_value=data_max_date,
            key="end_date"
        )
    
    # Проверка корректности дат
    if start_date > end_date:
        st.error("❌ Начальная дата не может быть позже конечной")
        st.stop()
    
    period_days = (end_date - start_date).days + 1
    st.caption(f"📅 Период анализа: {period_days} дней")

# ========== ОСНОВНАЯ ОБЛАСТЬ ==========

# Создаем процессор данных и анализатор
try:
    data_processor = DataProcessor(st.session_state.price_data, None)
    atr_analyzer = ATRAnalyzer(data_processor)
except Exception as e:
    st.error(f"❌ Ошибка инициализации: {e}")
    st.stop()

# Создаем вкладки
tab1, tab2, tab3 = st.tabs(["📊 Анализ", "🎯 Поиск окон", "📈 Результаты"])

# ========== ВКЛАДКА 1: АНАЛИЗ ==========
with tab1:
    st.header("📊 Анализ волатильности")
    
    if st.button("🔥 Построить тепловую карту", type="primary"):
        with st.spinner("Построение тепловой карты..."):
            try:
                heatmap_data = atr_analyzer.create_heatmap_data(start_date, end_date)
                
                if not heatmap_data.empty:
                    # Создаем pivot таблицу
                    pivot = heatmap_data.pivot_table(
                        values='atr',
                        index='hour',
                        columns='date',
                        aggfunc='mean'
                    )
                    
                    # График тепловой карты
                    fig = go.Figure(data=go.Heatmap(
                        z=pivot.values,
                        x=pivot.columns,
                        y=[f"{h:02d}:00" for h in pivot.index],
                        colorscale='RdYlGn_r',
                        colorbar=dict(title="ATR"),
                        hoverongaps=False
                    ))
                    
                    fig.update_layout(
                        title="Волатильность по часам",
                        xaxis_title="Дата",
                        yaxis_title="Час (UTC)",
                        height=600
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # График среднего ATR по часам
                    hourly_avg = heatmap_data.groupby('hour')['atr'].mean()
                    
                    fig2 = go.Figure()
                    fig2.add_trace(go.Bar(
                        x=[f"{h:02d}:00" for h in hourly_avg.index],
                        y=hourly_avg.values,
                        marker_color='lightblue'
                    ))
                    
                    fig2.add_hline(y=min_atr, line_dash="dash", line_color="green", 
                                  annotation_text=f"Min: {min_atr}")
                    fig2.add_hline(y=max_atr, line_dash="dash", line_color="red",
                                  annotation_text=f"Max: {max_atr}")
                    
                    fig2.update_layout(
                        title="Средний ATR по часам дня",
                        xaxis_title="Час",
                        yaxis_title="ATR",
                        height=400
                    )
                    
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.warning("⚠️ Недостаточно данных для построения карты")
            except Exception as e:
                st.error(f"❌ Ошибка при построении карты: {e}")
                logger.exception("Ошибка при построении тепловой карты")

# ========== ВКЛАДКА 2: ПОИСК ОКОН ==========
with tab2:
    st.header("🎯 Поиск оптимальных окон")
    
    # Информация о параметрах поиска
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("ATR диапазон", f"{min_atr:.0f} - {max_atr:.0f}")
    with col2:
        st.metric("Размер окна", f"{window_size_candles} свечей")
    with col3:
        st.metric("Мин. стабильность", f"{stability_threshold:.0%}")
    
    st.info(f"""
    **План поиска:**
    - Окно из {window_size_candles} свечей будет смещаться на {step_candles} {'свечу' if step_candles == 1 else f'свечи ({step_candles*15} мин)'} 
    - Всего {total_positions} позиций для проверки
    - Период: {period_days} дней данных
    """)
    
    if st.button("🚀 ЗАПУСТИТЬ ПОИСК", type="primary", use_container_width=True):
        progress = st.progress(0)
        status = st.empty()
        
        def update_progress(value, message):
            progress.progress(value)
            status.text(message)
        
        with st.spinner("Поиск оптимальных окон..."):
            try:
                results = atr_analyzer.find_optimal_windows(
                    min_atr=min_atr,
                    max_atr=max_atr,
                    stability_threshold=stability_threshold,
                    start_date=start_date,
                    end_date=end_date,
                    window_size_candles=window_size_candles,
                    step_candles=step_candles,
                    progress_callback=update_progress
                )
                
                st.session_state.atr_results = results
                
                if results:
                    st.success(f"✅ Найдено {len(results)} подходящих окон!")
                    st.balloons()
                else:
                    st.warning("⚠️ Не найдено окон с заданными параметрами")
                    
            except Exception as e:
                st.error(f"❌ Ошибка при поиске: {e}")
                logger.exception("Ошибка при поиске окон")

# ========== ВКЛАДКА 3: РЕЗУЛЬТАТЫ ==========
with tab3:
    st.header("📈 Результаты поиска")
    
    if st.session_state.atr_results:
        results_df = pd.DataFrame(st.session_state.atr_results)
        
        # Топ-5 результатов
        st.subheader("🏆 Топ-5 лучших окон")
        
        top5 = results_df.head(5)[['start', 'end', 'window_candles', 'avg_atr', 'stability', 'days_analyzed']]
        
        # Форматирование для отображения
        top5 = top5.copy()
        top5['stability'] = top5['stability'].apply(lambda x: f"{x:.1%}")
        top5.columns = ['Начало', 'Конец', 'Свечей', 'Средний ATR', 'Стабильность', 'Дней']
        
        st.dataframe(top5, use_container_width=True, hide_index=True)
        
        # График сравнения
        if len(results_df) > 1:
            st.subheader("📊 Сравнение найденных окон")
            
            fig = go.Figure()
            
            # Создаем метки для окон
            results_df['label'] = results_df.apply(
                lambda x: f"{x['start']}-{x['end']}", axis=1
            )
            
            # Scatter plot
            fig.add_trace(go.Scatter(
                x=results_df['avg_atr'][:10],
                y=results_df['stability'][:10],
                mode='markers+text',
                text=results_df['label'][:10],
                textposition="top center",
                marker=dict(
                    size=results_df['days_analyzed'][:10],
                    color=results_df['stability'][:10],
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title="Стабильность"),
                    sizemode='diameter',
                    sizeref=2
                )
            ))
            
            # Добавляем целевую зону
            fig.add_vrect(x0=min_atr, x1=max_atr, 
                         fillcolor="green", opacity=0.1,
                         annotation_text="Целевой ATR")
            
            fig.update_layout(
                title="ATR vs Стабильность (топ-10)",
                xaxis_title="Средний ATR",
                yaxis_title="Стабильность",
                height=500,
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Экспорт
        st.subheader("💾 Экспорт результатов")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Экспорт лучшего окна
            best = results_df.iloc[0]
            export_json = {
                "session_start": best['start'],
                "session_end": best['end'],
                "window_candles": int(best['window_candles']),
                "avg_atr": float(best['avg_atr']),
                "stability": float(best['stability'])
            }
            
            st.download_button(
                "📥 Скачать лучшее окно (JSON)",
                data=json.dumps(export_json, indent=2),
                file_name=f"best_window_{best['start'].replace(':', '')}_{best['end'].replace(':', '')}.json",
                mime="application/json"
            )
        
        with col2:
            # Экспорт всех результатов
            csv = results_df.to_csv(index=False)
            st.download_button(
                "📊 Скачать все результаты (CSV)",
                data=csv,
                file_name=f"atr_analysis_{datetime.now():%Y%m%d_%H%M%S}.csv",
                mime="text/csv"
            )
    else:
        st.info("👆 Сначала запустите поиск во вкладке 'Поиск окон'")
        
        st.markdown("""
        ### 📝 Как использовать:
        
        1. **Загрузите данные** в боковой панели
        2. **Настройте параметры** ATR и размер окна
        3. **Запустите поиск** во вкладке "Поиск окон"
        4. **Изучите результаты** здесь
        
        ### 💡 Подсказка:
        Начните с широких границ ATR и низкой стабильности, 
        затем сужайте параметры для более точных результатов.
        """)