"""
Модуль для R-расчетов в Trading Analyzer v11.0
Рассчитывает R-результаты с учетом коэффициента для TP,
коэффициента проскальзывания для SL, комиссий и Max Drawdown
"""

from typing import Dict, List, Optional, Tuple
import logging

# Настройка логирования
logger = logging.getLogger(__name__)


class RCalculator:
    """
    Класс для расчета R-метрик торговой системы.
    R-единица = размер одного Stop Loss.
    """
    
    def __init__(self):
        """Простая инициализация без параметров."""
        logger.info("RCalculator инициализирован")
    
    def calculate_r_result(self, trade: Dict, tp_coefficient: float = 0.9,
                           sl_slippage_coefficient: float = 1.0,
                           commission_rate: float = 0.0) -> float:
        """
        Рассчитывает R-результат одной сделки с учетом коэффициентов и комиссий.
        
        Args:
            trade: Словарь с данными сделки
            tp_coefficient: коэффициент для TP сделок (0.5-1.0), уменьшает прибыль
            sl_slippage_coefficient: коэффициент проскальзывания для SL (1.0+), увеличивает убыток
            commission_rate: ставка комиссии за сторону (например 0.001 = 0.1%)
        
        Returns:
            R-результат, округленный до 2 знаков
        """
        try:
            # Проверка на NO_TRADE или блокировку новостями
            if trade.get('result') == 'NO_TRADE':
                return 0.0
            
            if trade.get('close_reason') == 'news_filter_blocked':
                return 0.0
            
            # Проверка наличия необходимых полей
            required_fields = ['entry_price', 'exit_price', 'sl_price', 'entry_type']
            if not all(field in trade and trade[field] is not None for field in required_fields):
                logger.warning(f"Отсутствуют необходимые поля в сделке: {trade}")
                return 0.0
            
            # Извлекаем данные
            entry_price = float(trade['entry_price'])
            exit_price = float(trade['exit_price'])
            sl_price = float(trade['sl_price'])
            entry_type = trade['entry_type']
            result = trade.get('result', '')
            
            # Определяем направление сделки
            is_long = 'LONG' in entry_type
            
            # Расчет размера стоп-лосса
            sl_size = abs(entry_price - sl_price)
            
            # Защита от деления на ноль
            if sl_size == 0:
                logger.warning(f"Размер SL равен нулю для сделки {trade}")
                return 0.0
            
            # Расчет фактической прибыли/убытка
            if is_long:
                actual_pnl = exit_price - entry_price
            else:
                actual_pnl = entry_price - exit_price
            
            # Базовый R-результат
            base_r = actual_pnl / sl_size
            
            # Применяем коэффициенты в зависимости от результата
            if result == 'TP':
                final_r = base_r * tp_coefficient
            elif result == 'SL':
                # SL slippage увеличивает убыток: -1.0R * 1.05 = -1.05R
                final_r = base_r * sl_slippage_coefficient
            else:
                final_r = base_r
            
            # Вычитаем комиссию в R-единицах (round-trip: вход + выход)
            if commission_rate > 0 and sl_size > 0:
                # Commission_in_R = (entry_price * commission_rate * 2) / sl_size
                commission_in_r = (entry_price * commission_rate * 2) / sl_size
                final_r -= commission_in_r
            
            # Округляем до 2 знаков
            return round(final_r, 2)
            
        except Exception as e:
            logger.error(f"Ошибка при расчете R-результата: {str(e)}")
            return 0.0
    
    def add_r_to_trades(self, trades: List[Dict], tp_coefficient: float = 0.9,
                        sl_slippage_coefficient: float = 1.0,
                        commission_rate: float = 0.0) -> List[Dict]:
        """
        Добавляет поле 'r_result' к каждой сделке в списке.
        
        Args:
            trades: Список сделок
            tp_coefficient: Коэффициент для TP сделок
            sl_slippage_coefficient: Коэффициент проскальзывания для SL
            commission_rate: Ставка комиссии за сторону
        
        Returns:
            Новый список с добавленными R-результатами
        """
        trades_with_r = []
        
        for trade in trades:
            # Создаем копию сделки
            trade_copy = trade.copy()
            
            # Рассчитываем и добавляем R-результат
            trade_copy['r_result'] = self.calculate_r_result(
                trade, tp_coefficient, sl_slippage_coefficient, commission_rate
            )
            
            trades_with_r.append(trade_copy)
        
        return trades_with_r
    
    def calculate_cumulative_r(self, trades: List[Dict]) -> List[float]:
        """
        Рассчитывает накопительную кривую R-результатов.
        
        Args:
            trades: Список сделок с рассчитанными r_result
        
        Returns:
            Список накопительных значений R
        """
        cumulative_r = []
        current_sum = 0.0
        
        for trade in trades:
            r_result = trade.get('r_result', 0.0)
            
            # Пропускаем сделки с нулевым R (NO_TRADE, заблокированные)
            if r_result != 0:
                current_sum += r_result
            
            cumulative_r.append(round(current_sum, 2))
        
        return cumulative_r
    
    def calculate_max_drawdown(self, cumulative_r_series: List[float]) -> Dict:
        """
        Рассчитывает максимальный drawdown по кривой кумулятивного R.
        
        Алгоритм: идём по массиву, отслеживаем текущий пик (максимум),
        на каждом шаге считаем просадку = текущее значение - пик.
        Максимальный drawdown = минимальная просадка (наибольшее падение).
        
        Args:
            cumulative_r_series: Список кумулятивных R значений
        
        Returns:
            Словарь с информацией о drawdown:
                - max_drawdown: максимальная просадка (отрицательное число или 0)
                - max_drawdown_abs: абсолютное значение просадки
                - peak_index: индекс пика перед просадкой
                - trough_index: индекс дна просадки
                - peak_value: значение R на пике
                - trough_value: значение R на дне
                - recovery_index: индекс восстановления (None если не восстановился)
        """
        if not cumulative_r_series or len(cumulative_r_series) < 2:
            return {
                'max_drawdown': 0.0,
                'max_drawdown_abs': 0.0,
                'peak_index': 0,
                'trough_index': 0,
                'peak_value': 0.0,
                'trough_value': 0.0,
                'recovery_index': None
            }
        
        peak = cumulative_r_series[0]
        peak_index = 0
        max_drawdown = 0.0
        max_dd_peak_index = 0
        max_dd_trough_index = 0
        max_dd_peak_value = 0.0
        max_dd_trough_value = 0.0
        
        for i, value in enumerate(cumulative_r_series):
            # Обновляем пик
            if value > peak:
                peak = value
                peak_index = i
            
            # Рассчитываем текущую просадку
            drawdown = value - peak
            
            # Обновляем максимальную просадку
            if drawdown < max_drawdown:
                max_drawdown = drawdown
                max_dd_peak_index = peak_index
                max_dd_trough_index = i
                max_dd_peak_value = peak
                max_dd_trough_value = value
        
        # Ищем индекс восстановления после максимальной просадки
        recovery_index = None
        if max_dd_trough_index < len(cumulative_r_series) - 1:
            for i in range(max_dd_trough_index + 1, len(cumulative_r_series)):
                if cumulative_r_series[i] >= max_dd_peak_value:
                    recovery_index = i
                    break
        
        return {
            'max_drawdown': round(max_drawdown, 2),
            'max_drawdown_abs': round(abs(max_drawdown), 2),
            'peak_index': max_dd_peak_index,
            'trough_index': max_dd_trough_index,
            'peak_value': round(max_dd_peak_value, 2),
            'trough_value': round(max_dd_trough_value, 2),
            'recovery_index': recovery_index
        }
    
    def calculate_entry_type_statistics(self, trades: List[Dict]) -> Dict:
        """
        Рассчитывает статистику по типам входов.
        
        Args:
            trades: Список сделок с r_result
        
        Returns:
            Словарь со статистикой по каждому типу входа
        """
        # Все возможные типы входов
        all_entry_types = [
            'ENTRY_LONG_TREND', 'ENTRY_SHORT_TREND',
            'LIMIT_LONG_TREND', 'LIMIT_SHORT_TREND',
            'ENTRY_LONG_REVERSE', 'ENTRY_SHORT_REVERSE',
            'LIMIT_LONG_REVERSE', 'LIMIT_SHORT_REVERSE',
            'INSIDE_BLOCK', 'OUTSIDE_BLOCK'
        ]
        
        # Инициализация статистики
        stats = {}
        for entry_type in all_entry_types:
            stats[entry_type] = {
                'count': 0,
                'executed_count': 0,
                'blocked_by_news': 0,
                'total_r': 0.0,
                'average_r': 0.0,
                'win_rate': 0.0,
                'tp_count': 0,
                'sl_count': 0,
                'be_count': 0,
                'tp_rate': 0.0,
                'sl_rate': 0.0,
                'be_rate': 0.0
            }
        
        # Обработка каждой сделки
        for trade in trades:
            entry_type = trade.get('entry_type', '')
            if entry_type not in stats:
                continue
            
            stats[entry_type]['count'] += 1
            
            # Проверка блокировки новостями
            if trade.get('close_reason') == 'news_filter_blocked':
                stats[entry_type]['blocked_by_news'] += 1
                continue
            
            # Для INSIDE_BLOCK и OUTSIDE_BLOCK не может быть исполненных сделок
            if entry_type in ['INSIDE_BLOCK', 'OUTSIDE_BLOCK']:
                continue
            
            # Считаем исполненные сделки
            result = trade.get('result', '')
            if result in ['TP', 'SL', 'BE']:
                stats[entry_type]['executed_count'] += 1
                
                # Суммируем R-результат
                r_result = trade.get('r_result', 0.0)
                stats[entry_type]['total_r'] += r_result
                
                # Считаем по типам результатов
                if result == 'TP':
                    stats[entry_type]['tp_count'] += 1
                elif result == 'SL':
                    stats[entry_type]['sl_count'] += 1
                elif result == 'BE':
                    stats[entry_type]['be_count'] += 1
        
        # Расчет производных метрик
        for entry_type, data in stats.items():
            if data['executed_count'] > 0:
                # Средний R
                data['average_r'] = round(data['total_r'] / data['executed_count'], 2)
                
                # Win rate (TP считаем выигрышем)
                data['win_rate'] = round(data['tp_count'] / data['executed_count'] * 100, 1)
                
                # Процентные соотношения
                data['tp_rate'] = round(data['tp_count'] / data['executed_count'] * 100, 1)
                data['sl_rate'] = round(data['sl_count'] / data['executed_count'] * 100, 1)
                data['be_rate'] = round(data['be_count'] / data['executed_count'] * 100, 1)
            
            # Округляем total_r
            data['total_r'] = round(data['total_r'], 2)
        
        return stats
    
    def calculate_basic_statistics(self, trades: List[Dict]) -> Dict:
        """
        Рассчитывает базовую статистику по всем сделкам.
        
        Args:
            trades: Список сделок с r_result
        
        Returns:
            Словарь с базовой статистикой
        """
        stats = {
            'total_signals': len(trades),
            'executed_trades': 0,
            'blocked_by_news': 0,
            'no_entry_signals': 0,
            'total_r': 0.0,
            'average_r_per_trade': 0.0,
            'average_r_per_day': 0.0,
            'tp_total': 0,
            'sl_total': 0,
            'be_total': 0,
            'best_trade_r': 0.0,
            'worst_trade_r': 0.0,
            'win_rate': 0.0,
            'profit_factor': None
        }
        
        executed_r_values = []
        positive_r = 0.0
        negative_r = 0.0
        
        for trade in trades:
            # Считаем блокированные новостями
            if trade.get('close_reason') == 'news_filter_blocked':
                stats['blocked_by_news'] += 1
                continue
            
            # Считаем дни без сигналов
            entry_type = trade.get('entry_type', '')
            if entry_type in ['INSIDE_BLOCK', 'OUTSIDE_BLOCK']:
                stats['no_entry_signals'] += 1
                continue
            
            # Обрабатываем исполненные сделки
            result = trade.get('result', '')
            if result in ['TP', 'SL', 'BE']:
                stats['executed_trades'] += 1
                
                r_result = trade.get('r_result', 0.0)
                executed_r_values.append(r_result)
                stats['total_r'] += r_result
                
                # Суммируем для profit factor
                if r_result > 0:
                    positive_r += r_result
                else:
                    negative_r += abs(r_result)
                
                # Считаем по типам
                if result == 'TP':
                    stats['tp_total'] += 1
                elif result == 'SL':
                    stats['sl_total'] += 1
                elif result == 'BE':
                    stats['be_total'] += 1
        
        # Расчет производных метрик
        if stats['executed_trades'] > 0:
            stats['average_r_per_trade'] = round(stats['total_r'] / stats['executed_trades'], 2)
            stats['win_rate'] = round(stats['tp_total'] / stats['executed_trades'] * 100, 1)
            
            if executed_r_values:
                stats['best_trade_r'] = round(max(executed_r_values), 2)
                stats['worst_trade_r'] = round(min(executed_r_values), 2)
        
        if stats['total_signals'] > 0:
            stats['average_r_per_day'] = round(stats['total_r'] / stats['total_signals'], 2)
        
        # Profit Factor
        if negative_r > 0:
            stats['profit_factor'] = round(positive_r / negative_r, 2)
        elif positive_r > 0:
            stats['profit_factor'] = None  # Бесконечность, когда нет убытков
        
        # Округляем total_r
        stats['total_r'] = round(stats['total_r'], 2)

        return stats

    def calculate_r_cycles(self, trades: List[Dict], target_r: float = 5.0) -> Dict:
        """
        Считает R-циклы: отрезки торговли от сброса до достижения +target_r или -target_r.

        Args:
            trades: Список сделок с r_result
            target_r: Порог R для завершения цикла (по модулю)

        Returns:
            Словарь с метриками циклов
        """
        executed = [t for t in trades if t.get('result') in ('TP', 'SL', 'BE') and 'r_result' in t]

        if not executed:
            return {
                'num_cycles': 0, 'avg_trades_per_cycle': 0,
                'win_cycles': 0, 'loss_cycles': 0,
                'win_cycle_rate': 0.0, 'total_trades': 0,
                'incomplete_r': 0.0, 'cycles': []
            }

        cum_r = 0.0
        cycle_start_idx = 0
        cycles = []

        for i, trade in enumerate(executed):
            cum_r += trade['r_result']

            if cum_r >= target_r or cum_r <= -target_r:
                cycles.append({
                    'trades': i - cycle_start_idx + 1,
                    'result': 'win' if cum_r >= target_r else 'loss',
                    'r_reached': round(cum_r, 2)
                })
                cum_r = 0.0
                cycle_start_idx = i + 1

        num_cycles = len(cycles)
        win_cycles = sum(1 for c in cycles if c['result'] == 'win')
        loss_cycles = num_cycles - win_cycles

        return {
            'num_cycles': num_cycles,
            'avg_trades_per_cycle': round(sum(c['trades'] for c in cycles) / num_cycles, 1) if num_cycles > 0 else 0,
            'win_cycles': win_cycles,
            'loss_cycles': loss_cycles,
            'win_cycle_rate': round(win_cycles / num_cycles * 100, 1) if num_cycles > 0 else 0.0,
            'total_trades': len(executed),
            'incomplete_r': round(cum_r, 2),
            'cycles': cycles
        }
