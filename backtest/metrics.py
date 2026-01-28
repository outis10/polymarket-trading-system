"""Performance metrics calculation"""

from dataclasses import dataclass
from typing import List, Dict, Any
import math

import pandas as pd
import numpy as np


@dataclass
class BacktestMetrics:
    """Comprehensive backtest performance metrics"""

    # Returns
    total_return: float              # Total return (%)
    annualized_return: float         # Annualized return (%)

    # Risk
    volatility: float                # Annualized volatility (%)
    max_drawdown: float              # Maximum drawdown (%)
    max_drawdown_duration: int       # Max drawdown duration (days)

    # Risk-adjusted
    sharpe_ratio: float              # Sharpe ratio (assuming rf=0)
    sortino_ratio: float             # Sortino ratio
    calmar_ratio: float              # Calmar ratio (return/max_dd)

    # Trading statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float                  # Win rate (%)
    avg_win: float                   # Average winning trade
    avg_loss: float                  # Average losing trade
    profit_factor: float             # Gross profit / Gross loss
    avg_trade_duration: float        # Average trade duration (minutes)

    # P&L
    total_pnl: float
    gross_profit: float
    gross_loss: float
    largest_win: float
    largest_loss: float

    # Capital
    initial_capital: float
    final_capital: float
    peak_capital: float


class MetricsCalculator:
    """Calculate backtest performance metrics"""

    # Crypto trades 24/7/365
    TRADING_DAYS_PER_YEAR = 365
    MINUTES_PER_YEAR = 365 * 24 * 60

    @classmethod
    def calculate(
        cls,
        equity_curve: pd.Series,
        trades: List[Dict[str, Any]],
        initial_capital: float,
        timeframe_minutes: int = 1
    ) -> BacktestMetrics:
        """
        Calculate all metrics from equity curve and trades

        Args:
            equity_curve: Time series of portfolio equity
            trades: List of trade dictionaries with 'pnl', 'entry_time', 'exit_time'
            initial_capital: Starting capital
            timeframe_minutes: Timeframe in minutes (for annualization)

        Returns:
            BacktestMetrics object with all metrics
        """
        # Handle empty data
        if equity_curve.empty or len(equity_curve) < 2:
            return cls._empty_metrics(initial_capital)

        # Calculate returns
        returns = equity_curve.pct_change().dropna()

        # Total return
        total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) * 100

        # Annualization factor
        periods_per_year = cls.MINUTES_PER_YEAR / timeframe_minutes
        num_periods = len(equity_curve)

        # Annualized return (CAGR)
        if num_periods > 1:
            years = num_periods / periods_per_year
            if years > 0:
                annualized_return = ((equity_curve.iloc[-1] / equity_curve.iloc[0]) **
                                    (1 / years) - 1) * 100
            else:
                annualized_return = total_return
        else:
            annualized_return = total_return

        # Volatility (annualized)
        if len(returns) > 1:
            volatility = returns.std() * math.sqrt(periods_per_year) * 100
        else:
            volatility = 0.0

        # Drawdown analysis
        max_drawdown, max_dd_duration = cls._calculate_drawdown(equity_curve, timeframe_minutes)

        # Risk-adjusted ratios
        sharpe = cls._calculate_sharpe(returns, periods_per_year)
        sortino = cls._calculate_sortino(returns, periods_per_year)
        calmar = annualized_return / max_drawdown if max_drawdown > 0 else 0.0

        # Trade statistics
        trade_stats = cls._calculate_trade_stats(trades)

        # Capital stats
        peak_capital = equity_curve.max()
        final_capital = equity_curve.iloc[-1]

        return BacktestMetrics(
            total_return=round(total_return, 2),
            annualized_return=round(annualized_return, 2),
            volatility=round(volatility, 2),
            max_drawdown=round(max_drawdown, 2),
            max_drawdown_duration=max_dd_duration,
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=round(sortino, 3),
            calmar_ratio=round(calmar, 3),
            total_trades=trade_stats['total_trades'],
            winning_trades=trade_stats['winning_trades'],
            losing_trades=trade_stats['losing_trades'],
            win_rate=round(trade_stats['win_rate'], 2),
            avg_win=round(trade_stats['avg_win'], 2),
            avg_loss=round(trade_stats['avg_loss'], 2),
            profit_factor=round(trade_stats['profit_factor'], 2),
            avg_trade_duration=round(trade_stats['avg_duration'], 1),
            total_pnl=round(final_capital - initial_capital, 2),
            gross_profit=round(trade_stats['gross_profit'], 2),
            gross_loss=round(trade_stats['gross_loss'], 2),
            largest_win=round(trade_stats['largest_win'], 2),
            largest_loss=round(trade_stats['largest_loss'], 2),
            initial_capital=initial_capital,
            final_capital=round(final_capital, 2),
            peak_capital=round(peak_capital, 2)
        )

    @classmethod
    def _calculate_drawdown(
        cls,
        equity_curve: pd.Series,
        timeframe_minutes: int
    ) -> tuple[float, int]:
        """Calculate maximum drawdown and duration"""
        # Running maximum
        cummax = equity_curve.cummax()

        # Drawdown series
        drawdown = (equity_curve - cummax) / cummax * 100
        max_drawdown = abs(drawdown.min())

        # Calculate duration of max drawdown period
        in_drawdown = drawdown < 0
        max_duration = 0
        current_duration = 0

        for is_dd in in_drawdown:
            if is_dd:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        # Convert to days
        duration_days = int(max_duration * timeframe_minutes / (60 * 24))

        return max_drawdown, duration_days

    @classmethod
    def _calculate_sharpe(
        cls,
        returns: pd.Series,
        periods_per_year: float,
        risk_free_rate: float = 0.0
    ) -> float:
        """Calculate Sharpe ratio"""
        if len(returns) < 2 or returns.std() == 0:
            return 0.0

        excess_returns = returns - risk_free_rate / periods_per_year
        return (excess_returns.mean() * math.sqrt(periods_per_year)) / returns.std()

    @classmethod
    def _calculate_sortino(
        cls,
        returns: pd.Series,
        periods_per_year: float,
        risk_free_rate: float = 0.0
    ) -> float:
        """Calculate Sortino ratio (only penalizes downside volatility)"""
        if len(returns) < 2:
            return 0.0

        excess_returns = returns - risk_free_rate / periods_per_year
        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0 or downside_returns.std() == 0:
            return 0.0

        return (excess_returns.mean() * math.sqrt(periods_per_year)) / downside_returns.std()

    @classmethod
    def _calculate_trade_stats(cls, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate trading statistics"""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_duration': 0.0,
                'gross_profit': 0.0,
                'gross_loss': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0,
            }

        # Extract P&Ls
        pnls = [t.get('pnl', 0) for t in trades if t.get('pnl') is not None]

        if not pnls:
            return cls._calculate_trade_stats([])

        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]

        total_trades = len(pnls)
        winning_trades = len(winning)
        losing_trades = len(losing)

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(winning)
        gross_loss = abs(sum(losing))

        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0.0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0.0

        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        largest_win = max(pnls) if pnls else 0.0
        largest_loss = min(pnls) if pnls else 0.0

        # Calculate average duration
        durations = []
        for trade in trades:
            entry = trade.get('entry_time')
            exit_time = trade.get('exit_time')
            if entry and exit_time:
                duration = (exit_time - entry).total_seconds() / 60
                durations.append(duration)

        avg_duration = np.mean(durations) if durations else 0.0

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_duration': avg_duration,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
        }

    @classmethod
    def _empty_metrics(cls, initial_capital: float) -> BacktestMetrics:
        """Return empty metrics for edge cases"""
        return BacktestMetrics(
            total_return=0.0,
            annualized_return=0.0,
            volatility=0.0,
            max_drawdown=0.0,
            max_drawdown_duration=0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            avg_trade_duration=0.0,
            total_pnl=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            largest_win=0.0,
            largest_loss=0.0,
            initial_capital=initial_capital,
            final_capital=initial_capital,
            peak_capital=initial_capital
        )
