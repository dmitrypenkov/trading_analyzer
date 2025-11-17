"""
Модуль визуализации графиков для Trading Analyzer v10
Отвечает за создание всех графиков в системе
"""

import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict, Optional
import pandas as pd


class ChartVisualizer:
    """Класс для создания графиков системы."""
    
    @staticmethod
    def create_cumulative_r_chart(dates: List[str], r_values: List[float], 
                                  title: str = "Накопительный R-результат") -> go.Figure:
        """
        Создает график накопительного R-результата.
        
        Args:
            dates: Список дат
            r_values: Список накопительных R-значений
            title: Заголовок графика
            
        Returns:
            Plotly Figure объект
        """
        fig = go.Figure()
        
        # Основная линия
        fig.add_trace(go.Scatter(
            x=dates,
            y=r_values,
            mode='lines',
            name='Накопительный R',
            line=dict(color='green', width=2)
        ))
        
        # Добавляем нулевую линию
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # Настройка layout
        fig.update_layout(
            title=title,
            xaxis_title='Дата',
            yaxis_title='R-результат',
            height=400,
            hovermode='x unified',
            showlegend=True
        )
        
        return fig
    
    @staticmethod
    def create_yearly_cumulative_chart(year: int, months: List[str], 
                                      r_values: List[float]) -> go.Figure:
        """
        Создает график накопительного R для конкретного года.
        
        Args:
            year: Год
            months: Список месяцев
            r_values: Список накопительных R-значений
            
        Returns:
            Plotly Figure объект
        """
        fig = go.Figure()
        
        # Основная линия с маркерами
        fig.add_trace(go.Scatter(
            x=months[:len(r_values)],
            y=r_values,
            mode='lines+markers',
            name='Накопительный R',
            line=dict(color='blue', width=2),
            marker=dict(size=8)
        ))
        
        # Добавляем нулевую линию
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        
        # Настройка layout
        fig.update_layout(
            title=f'Накопительный R за {year} год',
            xaxis_title='Месяц',
            yaxis_title='R-результат',
            height=400,
            hovermode='x unified'
        )
        
        return fig
    
    @staticmethod
    def create_monthly_r_distribution(monthly_data: pd.DataFrame) -> go.Figure:
        """
        Создает гистограмму распределения R по месяцам.
        
        Args:
            monthly_data: DataFrame с месячными данными
            
        Returns:
            Plotly Figure объект
        """
        fig = go.Figure()
        
        # Цвета для положительных и отрицательных значений
        colors = ['green' if x > 0 else 'red' for x in monthly_data['total_r']]
        
        fig.add_trace(go.Bar(
            x=monthly_data['month'],
            y=monthly_data['total_r'],
            marker_color=colors,
            name='R-результат'
        ))
        
        # Настройка layout
        fig.update_layout(
            title='Распределение R-результатов по месяцам',
            xaxis_title='Месяц',
            yaxis_title='R-результат',
            height=400,
            showlegend=False
        )
        
        return fig
    
    @staticmethod
    def create_entry_type_pie_chart(entry_stats: Dict) -> go.Figure:
        """
        Создает круговую диаграмму по типам входов.
        
        Args:
            entry_stats: Статистика по типам входов
            
        Returns:
            Plotly Figure объект
        """
        # Подготавливаем данные
        labels = []
        values = []
        
        for entry_type, stats in entry_stats.items():
            if stats['executed_count'] > 0:
                labels.append(entry_type)
                values.append(stats['executed_count'])
        
        # Создаем диаграмму
        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.3
        )])
        
        fig.update_layout(
            title='Распределение сделок по типам входов',
            height=400
        )
        
        return fig