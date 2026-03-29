#!/usr/bin/env python3
"""
Trading Analyzer v12 VPS — Headless optimization runner.

Запуск на VPS:
    nohup python3 run_optimization.py config.json > optimization.log 2>&1 &

Или через screen/tmux:
    screen -S trading
    python3 run_optimization.py config.json
    # Ctrl+A, D для отсоединения

Результаты появятся в папке results_YYYYMMDD_HHMMSS/
"""

import sys
import os
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy

import pandas as pd
import numpy as np

# Импорт модулей системы
from data_processor import DataProcessor
from analyzer import TradingAnalyzer
from r_calculator import RCalculator
from report_generator import ReportGenerator
from optimizer import TradingOptimizer

# ─────────────────────────────────────────────────
# Логирование
# ─────────────────────────────────────────────────

def setup_logging(output_dir: str):
    """Настройка логирования в файл и консоль."""
    log_file = os.path.join(output_dir, 'optimization.log')
    
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Файл
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(formatter)
    fh.setLevel(logging.INFO)
    
    # Консоль
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)
    
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)
    
    return logging.getLogger('vps_runner')


# ─────────────────────────────────────────────────
# Загрузка конфигурации
# ─────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Загружает и валидирует конфигурацию."""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Обязательные поля
    required = ['price_data_path', 'settings']
    for key in required:
        if key not in config:
            raise ValueError(f"Отсутствует обязательное поле: {key}")
    
    # Дефолты для оптимизации
    opt = config.setdefault('optimization', {})
    opt.setdefault('tp_range', [0.5, 3.0, 0.1])
    opt.setdefault('sl_range', [0.5, 2.0, 0.1])
    opt.setdefault('target', 'max_total_r')
    opt.setdefault('use_time_optimization', False)
    opt.setdefault('export_top_n_csv', 10)
    opt.setdefault('export_all_csv', False)
    
    # Дефолты для time optimization
    if opt['use_time_optimization']:
        opt.setdefault('block_start_fixed', '00:00')
        opt.setdefault('session_end_fixed', '20:00')
        opt.setdefault('split_hour_min', 3)
        opt.setdefault('split_hour_max', 18)
        opt.setdefault('split_hour_step', 1)
        opt.setdefault('from_previous_day', False)
    
    return config


def prepare_settings(raw_settings: dict) -> dict:
    """Конвертирует строковые значения настроек в нужные типы."""
    settings = raw_settings.copy()
    
    for tkey in ['block_start', 'block_end', 'session_start', 'session_end']:
        if isinstance(settings.get(tkey), str):
            settings[tkey] = datetime.strptime(settings[tkey], '%H:%M').time()
    
    for dkey in ['start_date', 'end_date']:
        if isinstance(settings.get(dkey), str):
            settings[dkey] = datetime.strptime(settings[dkey], '%Y-%m-%d').date()
    
    # Удаляем устаревшие
    settings.pop('target_r', None)
    
    return settings


# ─────────────────────────────────────────────────
# Экспорт CSV
# ─────────────────────────────────────────────────

def export_combination_csv(optimizer, report_gen, settings, tp, sl, output_dir, logger):
    """Экспортирует CSV для одной комбинации TP/SL."""
    cache_key = f"{tp}_{sl}"
    
    with optimizer._cache_lock:
        cached = optimizer._results_cache.get(cache_key)
    
    if not cached or 'analysis_results' not in cached:
        return None
    
    analysis_results = cached['analysis_results']
    
    daily_df = report_gen.prepare_daily_trades(
        analysis_results['results'],
        settings.get('tp_coefficient', 0.9),
        settings.get('sl_slippage_coefficient', 1.0),
        settings.get('commission_rate', 0.0)
    )
    
    tp_str = f"{tp:.2f}".replace('.', '_')
    sl_str = f"{sl:.2f}".replace('.', '_')
    filename = f"trades_TP{tp_str}_SL{sl_str}.csv"
    filepath = os.path.join(output_dir, filename)
    
    daily_df.to_csv(filepath, index=False, encoding='utf-8')
    return filepath


# ─────────────────────────────────────────────────
# HTML-отчёт
# ─────────────────────────────────────────────────

def generate_html_report(results, config, settings, output_dir, 
                         time_results=None, logger=None):
    """Генерирует HTML-отчёт с интерактивными Plotly-графиками."""
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    
    opt = config['optimization']
    target_names = {
        'max_total_r': 'Максимальный суммарный R',
        'max_r_dd_ratio': 'Баланс R / MaxDrawdown (Calmar)',
        'max_r_minus_dd': 'R − 2×MaxDrawdown (защитный)'
    }
    target_name = target_names.get(opt['target'], opt['target'])
    
    charts_html = []
    
    # ──────── Стандартная оптимизация TP/SL ────────
    if results and not time_results:
        best = results['best_params']
        grid = results['results_grid']
        results_df = results['results_df']
        
        # Тепловая карта
        fig_heatmap = go.Figure(data=go.Heatmap(
            z=grid.values,
            x=[f"{c:.1f}" for c in grid.columns],
            y=[f"{r:.1f}" for r in grid.index],
            colorscale='RdYlGn',
            text=[[f"{v:.2f}" if not pd.isna(v) else "" for v in row] for row in grid.values],
            texttemplate="%{text}",
            textfont={"size": 10},
            hoverongaps=False,
            colorbar=dict(title="Метрика")
        ))
        fig_heatmap.update_layout(
            title=f"Тепловая карта: {target_name}",
            xaxis_title="TP множитель",
            yaxis_title="SL множитель",
            template="plotly_dark",
            height=600
        )
        charts_html.append(fig_heatmap.to_html(full_html=False, include_plotlyjs=False))
        
        # Топ-10 таблица
        top_df = results_df.sort_values('metric_value', ascending=False).head(20)
        
        # Scatter: Total R vs Win Rate
        if 'total_r' in results_df.columns and 'win_rate' in results_df.columns:
            fig_scatter = go.Figure()
            fig_scatter.add_trace(go.Scatter(
                x=results_df['total_r'],
                y=results_df['win_rate'],
                mode='markers',
                marker=dict(
                    size=8,
                    color=results_df['metric_value'],
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title="Метрика")
                ),
                text=[f"TP={r['tp_multiplier']:.1f} SL={r['sl_multiplier']:.1f}" 
                      for _, r in results_df.iterrows()],
                hovertemplate="Total R: %{x:.2f}<br>Win Rate: %{y:.1f}%<br>%{text}<extra></extra>"
            ))
            fig_scatter.update_layout(
                title="Total R vs Win Rate",
                xaxis_title="Total R",
                yaxis_title="Win Rate %",
                template="plotly_dark",
                height=500
            )
            charts_html.append(fig_scatter.to_html(full_html=False, include_plotlyjs=False))
    
    # ──────── Оптимизация времени ────────
    if time_results:
        all_tr = time_results['all_time_results']
        best_overall = time_results['best_overall']
        
        # Bar chart метрики по часам
        fig_time = go.Figure()
        hours = [t['split_time'] for t in all_tr]
        metrics = [t.get('best_metric', 0) or 0 for t in all_tr]
        colors = ['gold' if h == best_overall['split_time'] else 'steelblue' for h in hours]
        
        fig_time.add_trace(go.Bar(x=hours, y=metrics, marker_color=colors))
        fig_time.update_layout(
            title="Лучшая метрика по времени разделения",
            xaxis_title="Час разделения (block_end = session_start)",
            yaxis_title=target_name,
            template="plotly_dark",
            height=500
        )
        charts_html.append(fig_time.to_html(full_html=False, include_plotlyjs=False))
        
        # Total R по часам
        total_rs = [t.get('best_total_r', 0) or 0 for t in all_tr]
        fig_r = go.Figure()
        fig_r.add_trace(go.Bar(
            x=hours, y=total_rs,
            marker_color=['gold' if h == best_overall['split_time'] else '#4CAF50' for h in hours]
        ))
        fig_r.update_layout(
            title="Total R по времени разделения",
            xaxis_title="Час разделения",
            yaxis_title="Total R",
            template="plotly_dark",
            height=400
        )
        charts_html.append(fig_r.to_html(full_html=False, include_plotlyjs=False))
        
        # Тепловая карта для лучшего временного окна
        # Ищем все результаты для лучшего часа
        best_hour_data = None
        for tr in all_tr:
            if tr['split_time'] == best_overall['split_time']:
                best_hour_data = tr
                break
        
        if best_hour_data and 'all_results' in best_hour_data:
            hour_df = pd.DataFrame(best_hour_data['all_results'])
            if len(hour_df) > 0:
                tp_vals = sorted(hour_df['tp_multiplier'].unique())
                sl_vals = sorted(hour_df['sl_multiplier'].unique())
                
                grid = pd.DataFrame(index=sl_vals, columns=tp_vals, dtype=float)
                for _, row in hour_df.iterrows():
                    grid.loc[row['sl_multiplier'], row['tp_multiplier']] = row['metric_value']
                grid = grid.sort_index(ascending=False)
                
                fig_best_heat = go.Figure(data=go.Heatmap(
                    z=grid.values,
                    x=[f"{c:.1f}" for c in grid.columns],
                    y=[f"{r:.1f}" for r in grid.index],
                    colorscale='RdYlGn',
                    text=[[f"{v:.2f}" if not pd.isna(v) else "" for v in row] for row in grid.values],
                    texttemplate="%{text}",
                    textfont={"size": 10},
                    colorbar=dict(title="Метрика")
                ))
                fig_best_heat.update_layout(
                    title=f"Тепловая карта TP/SL для лучшего окна ({best_overall['block']} → {best_overall['session']})",
                    xaxis_title="TP множитель",
                    yaxis_title="SL множитель",
                    template="plotly_dark",
                    height=600
                )
                charts_html.append(fig_best_heat.to_html(full_html=False, include_plotlyjs=False))
    
    # ──────── Собираем HTML ────────
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Сводка настроек
    settings_summary = f"""
    <table class="info-table">
        <tr><td>Блок</td><td>{settings.get('block_start', '?')} — {settings.get('block_end', '?')} UTC</td></tr>
        <tr><td>Сессия</td><td>{settings.get('session_start', '?')} — {settings.get('session_end', '?')} UTC</td></tr>
        <tr><td>Режим</td><td>{'Возвратный' if settings.get('use_return_mode') else 'По-тренду'}</td></tr>
        <tr><td>Лимитный вход</td><td>{'Да' if settings.get('limit_only_entry') else 'Нет'}</td></tr>
        <tr><td>С предыдущего дня</td><td>{'Да' if settings.get('from_previous_day') else 'Нет'}</td></tr>
        <tr><td>TP коэффициент</td><td>{settings.get('tp_coefficient', 0.9)}</td></tr>
        <tr><td>SL проскальзывание</td><td>{settings.get('sl_slippage_coefficient', 1.0)}</td></tr>
        <tr><td>Комиссия</td><td>{settings.get('commission_rate', 0) * 100:.2f}% за сторону</td></tr>
        <tr><td>Диапазон</td><td>{settings.get('min_range_size', 0)} — {settings.get('max_range_size', 99999)}</td></tr>
        <tr><td>Период</td><td>{settings.get('start_date', '?')} — {settings.get('end_date', '?')}</td></tr>
        <tr><td>Цель</td><td>{target_name}</td></tr>
    </table>
    """
    
    # Блок лучших результатов
    if time_results:
        bo = time_results['best_overall']
        details = time_results['optimization_details']
        best_html = f"""
        <div class="best-result">
            <h2>🏆 Лучший результат</h2>
            <div class="metrics-row">
                <div class="metric"><span class="metric-label">Блок</span><span class="metric-value">{bo['block']}</span></div>
                <div class="metric"><span class="metric-label">Сессия</span><span class="metric-value">{bo['session']}</span></div>
                <div class="metric"><span class="metric-label">TP</span><span class="metric-value">{bo.get('best_tp', '-')}</span></div>
                <div class="metric"><span class="metric-label">SL</span><span class="metric-value">{bo.get('best_sl', '-')}</span></div>
                <div class="metric"><span class="metric-label">Метрика</span><span class="metric-value">{bo.get('best_metric', 0):.2f}</span></div>
                <div class="metric"><span class="metric-label">Total R</span><span class="metric-value">{bo.get('best_total_r', '-')}</span></div>
                <div class="metric"><span class="metric-label">Win Rate</span><span class="metric-value">{bo.get('best_win_rate', '-')}%</span></div>
            </div>
            <p style="color:#888;">Прогонов: {details['total_steps']} | Время: {details['computation_time']:.0f} сек</p>
        </div>
        """
        
        # Таблица всех временных окон
        time_table_rows = ""
        for tr in time_results['all_time_results']:
            is_best = tr['split_time'] == bo['split_time']
            row_class = ' class="best-row"' if is_best else ''
            time_table_rows += f"""
            <tr{row_class}>
                <td>{tr['split_time']}</td>
                <td>{tr['block']}</td>
                <td>{tr['session']}</td>
                <td>{tr.get('best_metric', 0):.2f}</td>
                <td>{tr.get('best_tp', '-')}</td>
                <td>{tr.get('best_sl', '-')}</td>
                <td>{tr.get('best_total_r', '-')}</td>
                <td>{tr.get('best_trades', '-')}</td>
                <td>{tr.get('best_win_rate', '-')}%</td>
            </tr>"""
        
        time_table_html = f"""
        <h2>📊 Все временные окна</h2>
        <table class="data-table">
            <thead>
                <tr><th>Час</th><th>Блок</th><th>Сессия</th><th>Метрика</th><th>TP</th><th>SL</th><th>Total R</th><th>Сделок</th><th>Win%</th></tr>
            </thead>
            <tbody>{time_table_rows}</tbody>
        </table>
        """
    elif results:
        best = results['best_params']
        details = results['optimization_details']
        best_html = f"""
        <div class="best-result">
            <h2>🏆 Лучший результат</h2>
            <div class="metrics-row">
                <div class="metric"><span class="metric-label">TP</span><span class="metric-value">{best['tp_multiplier']}</span></div>
                <div class="metric"><span class="metric-label">SL</span><span class="metric-value">{best['sl_multiplier']}</span></div>
                <div class="metric"><span class="metric-label">Метрика</span><span class="metric-value">{results['best_metric']:.2f}</span></div>
            </div>
            <p style="color:#888;">Комбинаций: {details['total_combinations']} | Время: {details['computation_time']:.0f} сек</p>
        </div>
        """
        
        # Топ-20 таблица
        top = results['results_df'].sort_values('metric_value', ascending=False).head(20)
        top_rows = ""
        for i, (_, r) in enumerate(top.iterrows(), 1):
            top_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{r['tp_multiplier']:.1f}</td>
                <td>{r['sl_multiplier']:.1f}</td>
                <td>{r.get('metric_value', 0):.2f}</td>
                <td>{r.get('total_r', 0):.2f}</td>
                <td>{r.get('total_trades', 0)}</td>
                <td>{r.get('win_rate', 0):.1f}%</td>
            </tr>"""
        
        time_table_html = f"""
        <h2>📊 Топ-20 комбинаций</h2>
        <table class="data-table">
            <thead>
                <tr><th>#</th><th>TP</th><th>SL</th><th>Метрика</th><th>Total R</th><th>Сделок</th><th>Win%</th></tr>
            </thead>
            <tbody>{top_rows}</tbody>
        </table>
        """
    else:
        best_html = "<p>Нет результатов</p>"
        time_table_html = ""
    
    # Графики
    charts_section = "\n".join(f'<div class="chart-container">{ch}</div>' for ch in charts_html)
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Trading Analyzer v12 — Отчёт оптимизации</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #1a1a2e; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; }}
        h1 {{ color: #00d4ff; margin-bottom: 5px; }}
        h2 {{ color: #00d4ff; margin: 30px 0 15px; border-bottom: 1px solid #333; padding-bottom: 8px; }}
        .header {{ margin-bottom: 30px; }}
        .header .timestamp {{ color: #888; font-size: 14px; }}
        .best-result {{ background: #16213e; border: 1px solid #00d4ff; border-radius: 12px; padding: 20px; margin: 20px 0; }}
        .metrics-row {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 15px; }}
        .metric {{ background: #0f3460; border-radius: 8px; padding: 12px 20px; min-width: 120px; text-align: center; }}
        .metric-label {{ display: block; font-size: 12px; color: #888; text-transform: uppercase; }}
        .metric-value {{ display: block; font-size: 24px; font-weight: bold; color: #00d4ff; margin-top: 4px; }}
        .info-table {{ border-collapse: collapse; margin: 10px 0; }}
        .info-table td {{ padding: 6px 16px 6px 0; border-bottom: 1px solid #222; }}
        .info-table td:first-child {{ color: #888; }}
        .data-table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        .data-table th {{ background: #16213e; padding: 10px 12px; text-align: left; border-bottom: 2px solid #00d4ff; font-size: 13px; }}
        .data-table td {{ padding: 8px 12px; border-bottom: 1px solid #222; font-size: 13px; }}
        .data-table tr:hover {{ background: #16213e; }}
        .data-table .best-row {{ background: #1a3a2a; font-weight: bold; }}
        .chart-container {{ margin: 20px 0; }}
        .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }}
        @media (max-width: 800px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Trading Analyzer v12 VPS</h1>
        <p class="timestamp">Сгенерировано: {timestamp}</p>
    </div>
    
    <div class="two-col">
        <div>
            <h2>⚙️ Настройки</h2>
            {settings_summary}
        </div>
        <div>
            {best_html}
        </div>
    </div>
    
    {time_table_html}
    
    {charts_section}
    
    <p style="color:#555; margin-top:40px; text-align:center;">Trading Analyzer v12 VPS | {timestamp}</p>
</body>
</html>"""
    
    filepath = os.path.join(output_dir, 'report.html')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return filepath


# ─────────────────────────────────────────────────
# Основной процесс
# ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Trading Analyzer v12 VPS — Headless optimization')
    parser.add_argument('config', help='Путь к JSON-файлу конфигурации')
    parser.add_argument('--dry-run', action='store_true', help='Только проверить конфиг, не запускать')
    args = parser.parse_args()
    
    # Загрузка конфигурации
    config = load_config(args.config)
    opt = config['optimization']
    
    # Создание папки результатов
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = config.get('output_dir', f'results_{timestamp}')
    os.makedirs(output_dir, exist_ok=True)
    
    csv_dir = os.path.join(output_dir, 'csv')
    os.makedirs(csv_dir, exist_ok=True)
    
    # Логирование
    logger = setup_logging(output_dir)
    logger.info(f"═══ Trading Analyzer v12 VPS ═══")
    logger.info(f"Конфиг: {args.config}")
    logger.info(f"Результаты: {output_dir}")
    
    # Сохраняем копию конфига
    with open(os.path.join(output_dir, 'config_used.json'), 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False, default=str)
    
    # Загрузка данных
    if config.get('instrument'):
        # Загрузка из БД по имени инструмента
        try:
            from db.connection import init_db
            from db.repository import InstrumentRepository, CandleRepository, NewsRepository
            init_db()
            instr_repo = InstrumentRepository()
            candle_repo = CandleRepository()
            news_repo = NewsRepository()

            instr = instr_repo.get_by_symbol(config['instrument'])
            if not instr:
                logger.error(f"Инструмент '{config['instrument']}' не найден в БД")
                return

            logger.info(f"Загрузка из БД: {config['instrument']}")
            timeframe = config.get('timeframe', '15m')
            price_data = candle_repo.get_dataframe(instr['id'], timeframe)
            price_data['date'] = price_data['timestamp'].dt.date
            logger.info(f"  Загружено {len(price_data)} свечей, {price_data['date'].nunique()} дней")

            news_data = None
            news_df = news_repo.get_dataframe()
            if not news_df.empty:
                news_data = news_df
                logger.info(f"  Загружено {len(news_data)} новостей из БД")
        except ImportError:
            logger.error("Модули БД не найдены. Используйте price_data_path в конфиге.")
            return
    else:
        # Fallback: загрузка из CSV (обратная совместимость)
        logger.info(f"Загрузка ценовых данных: {config['price_data_path']}")
        price_data = pd.read_csv(config['price_data_path'])
        price_data['timestamp'] = pd.to_datetime(price_data['timestamp'])
        price_data['date'] = price_data['timestamp'].dt.date
        logger.info(f"  Загружено {len(price_data)} свечей, {price_data['date'].nunique()} дней")

        news_data = None
        if config.get('news_data_path'):
            logger.info(f"Загрузка новостей: {config['news_data_path']}")
            news_data = pd.read_csv(config['news_data_path'])
            news_data['timestamp'] = pd.to_datetime(news_data['timestamp'])
            logger.info(f"  Загружено {len(news_data)} новостей")
    
    # Подготовка настроек
    settings = prepare_settings(config['settings'])
    logger.info(f"Настройки подготовлены")
    logger.info(f"  Блок: {settings.get('block_start')} — {settings.get('block_end')}")
    logger.info(f"  Сессия: {settings.get('session_start')} — {settings.get('session_end')}")
    logger.info(f"  Режим: {'Возвратный' if settings.get('use_return_mode') else 'По-тренду'}")
    logger.info(f"  Лимитный вход: {settings.get('limit_only_entry', False)}")
    logger.info(f"  Период: {settings.get('start_date')} — {settings.get('end_date')}")
    logger.info(f"  Цель: {opt['target']}")
    
    if args.dry_run:
        logger.info("DRY RUN — выход без запуска")
        return
    
    # Инициализация
    data_processor = DataProcessor(price_data, news_data)
    analyzer = TradingAnalyzer(data_processor)
    r_calculator = RCalculator()
    report_gen = ReportGenerator(r_calculator)
    optimizer = TradingOptimizer(data_processor, analyzer, r_calculator)
    
    tp_range = tuple(opt['tp_range'])
    sl_range = tuple(opt['sl_range'])
    
    # Прогресс
    last_pct = [0]
    def progress_callback(pct):
        if pct >= last_pct[0] + 5:
            logger.info(f"  Прогресс: {pct}%")
            last_pct[0] = pct
    
    start_time = time.time()
    
    results = None
    time_results = None
    
    if opt['use_time_optimization']:
        logger.info(f"═══ Запуск оптимизации времени ═══")
        logger.info(f"  Разделение: {opt['split_hour_min']}:00 — {opt['split_hour_max']}:00")
        logger.info(f"  TP: {tp_range}, SL: {sl_range}")
        logger.info(f"  С предыдущего дня: {opt.get('from_previous_day', False)}")
        
        time_results = optimizer.optimize_time_and_params(
            settings=settings,
            block_start_fixed=opt['block_start_fixed'],
            session_end_fixed=opt['session_end_fixed'],
            split_hour_min=opt['split_hour_min'],
            split_hour_max=opt['split_hour_max'],
            split_hour_step=opt.get('split_hour_step', 1),
            tp_range=tp_range,
            sl_range=sl_range,
            optimization_target=opt['target'],
            from_previous_day=opt.get('from_previous_day', False),
            progress_callback=progress_callback
        )
        
        elapsed = time.time() - start_time
        logger.info(f"═══ Оптимизация завершена за {elapsed:.0f} сек ═══")
        
        bo = time_results['best_overall']
        logger.info(f"  Лучшее окно: {bo['block']} → {bo['session']}")
        logger.info(f"  TP={bo.get('best_tp')}, SL={bo.get('best_sl')}")
        logger.info(f"  Метрика={bo.get('best_metric', 0):.2f}, Total R={bo.get('best_total_r', '-')}")
        
        # Сводный CSV по временным окнам
        summary_rows = []
        for tr in time_results['all_time_results']:
            summary_rows.append({
                'split_hour': tr['split_time'],
                'block': tr['block'],
                'session': tr['session'],
                'best_metric': tr.get('best_metric', 0),
                'best_tp': tr.get('best_tp'),
                'best_sl': tr.get('best_sl'),
                'best_total_r': tr.get('best_total_r', 0),
                'best_trades': tr.get('best_trades', 0),
                'best_win_rate': tr.get('best_win_rate', 0)
            })
        
        summary_df = pd.DataFrame(summary_rows)
        summary_path = os.path.join(output_dir, 'time_optimization_summary.csv')
        summary_df.to_csv(summary_path, index=False, encoding='utf-8')
        logger.info(f"  Сводка: {summary_path}")
        
        # Экспорт CSV для лучшего часа (топ-N комбинаций)
        best_hour_data = None
        for tr in time_results['all_time_results']:
            if tr['split_time'] == bo['split_time']:
                best_hour_data = tr
                break
        
        if best_hour_data and 'all_results' in best_hour_data:
            hour_df = pd.DataFrame(best_hour_data['all_results'])
            hour_df_sorted = hour_df.sort_values('metric_value', ascending=False)
            
            all_combos_path = os.path.join(output_dir, f"all_combinations_{bo['split_time'].replace(':','')}.csv")
            hour_df_sorted.to_csv(all_combos_path, index=False, encoding='utf-8')
            logger.info(f"  Все комбинации лучшего часа: {all_combos_path}")
    
    else:
        logger.info(f"═══ Запуск стандартной оптимизации TP/SL ═══")
        logger.info(f"  TP: {tp_range}, SL: {sl_range}")
        
        results = optimizer.optimize_parameters(
            settings=settings,
            tp_range=tp_range,
            sl_range=sl_range,
            optimization_target=opt['target'],
            progress_callback=progress_callback,
            use_parallel=config.get('use_parallel', False)
        )
        
        elapsed = time.time() - start_time
        logger.info(f"═══ Оптимизация завершена за {elapsed:.0f} сек ═══")
        logger.info(f"  Лучший: TP={results['best_params']['tp_multiplier']}, SL={results['best_params']['sl_multiplier']}")
        logger.info(f"  Метрика: {results['best_metric']:.2f}")
        
        # Сводный CSV
        all_results_path = os.path.join(output_dir, 'all_combinations.csv')
        results['results_df'].sort_values('metric_value', ascending=False).to_csv(
            all_results_path, index=False, encoding='utf-8'
        )
        logger.info(f"  Все комбинации: {all_results_path}")
        
        # Экспорт CSV для топ-N
        export_n = opt.get('export_top_n_csv', 10)
        top_df = results['results_df'].sort_values('metric_value', ascending=False).head(export_n)
        
        logger.info(f"  Экспорт CSV для топ-{export_n} комбинаций...")
        exported = 0
        for _, row in top_df.iterrows():
            filepath = export_combination_csv(
                optimizer, report_gen, settings,
                row['tp_multiplier'], row['sl_multiplier'],
                csv_dir, logger
            )
            if filepath:
                exported += 1
        logger.info(f"  Экспортировано {exported} CSV файлов")
    
    # HTML-отчёт
    logger.info("Генерация HTML-отчёта...")
    report_path = generate_html_report(
        results, config, settings, output_dir,
        time_results=time_results, logger=logger
    )
    logger.info(f"  Отчёт: {report_path}")
    
    # Итог
    total_elapsed = time.time() - start_time
    logger.info(f"═══════════════════════════════════════")
    logger.info(f"  Общее время: {total_elapsed:.0f} сек ({total_elapsed/60:.1f} мин)")
    logger.info(f"  Результаты: {os.path.abspath(output_dir)}/")
    logger.info(f"  Отчёт: {os.path.abspath(report_path)}")
    logger.info(f"═══════════════════════════════════════")


if __name__ == '__main__':
    main()
