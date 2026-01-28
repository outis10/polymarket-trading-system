"""Backtest results storage and reporting"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

import pandas as pd

from backtest.config import BacktestConfig
from backtest.metrics import BacktestMetrics
from backtest.position_tracker import BacktestPosition


@dataclass
class BacktestResults:
    """Complete backtest results"""
    config: BacktestConfig
    strategy_name: str
    metrics: BacktestMetrics
    equity_curve: pd.Series
    trades: List[BacktestPosition]
    signals: List[Dict[str, Any]]
    price_data: pd.DataFrame
    simulated_market: List[Dict[str, Any]] = None  # YES/NO prices over time

    def __post_init__(self):
        if self.simulated_market is None:
            self.simulated_market = []

    def summary(self) -> str:
        """Generate text summary of results"""
        m = self.metrics
        lines = [
            "=" * 60,
            f"BACKTEST RESULTS: {self.strategy_name}",
            "=" * 60,
            "",
            "PERIOD:",
            f"  Start:      {self.config.start_date.strftime('%Y-%m-%d %H:%M')}",
            f"  End:        {self.config.end_date.strftime('%Y-%m-%d %H:%M')}",
            f"  Duration:   {len(self.price_data)} bars ({self.config.timeframe})",
            f"  Symbol:     {self.config.symbol}",
            "",
            "MARKET SIMULATION:",
            f"  Direction:  {self.config.market_direction or 'alternating'}",
            f"  Threshold:  {self.config.updown_threshold_pct}%",
            f"  Duration:   {self.config.updown_duration_minutes} min",
            "",
            "RETURNS:",
            f"  Total Return:      {m.total_return:+.2f}%",
            f"  Annualized Return: {m.annualized_return:+.2f}%",
            f"  Initial Capital:   ${m.initial_capital:,.2f}",
            f"  Final Capital:     ${m.final_capital:,.2f}",
            f"  Total P&L:         ${m.total_pnl:+,.2f}",
            "",
            "RISK:",
            f"  Volatility (ann.): {m.volatility:.2f}%",
            f"  Max Drawdown:      {m.max_drawdown:.2f}%",
            f"  Drawdown Duration: {m.max_drawdown_duration} days",
            "",
            "RISK-ADJUSTED:",
            f"  Sharpe Ratio:      {m.sharpe_ratio:.3f}",
            f"  Sortino Ratio:     {m.sortino_ratio:.3f}",
            f"  Calmar Ratio:      {m.calmar_ratio:.3f}",
            "",
            "TRADING:",
            f"  Total Trades:      {m.total_trades}",
            f"  Winning Trades:    {m.winning_trades} ({m.win_rate:.1f}%)",
            f"  Losing Trades:     {m.losing_trades}",
            f"  Profit Factor:     {m.profit_factor:.2f}",
            f"  Avg Win:           ${m.avg_win:,.2f}",
            f"  Avg Loss:          ${m.avg_loss:,.2f}",
            f"  Largest Win:       ${m.largest_win:+,.2f}",
            f"  Largest Loss:      ${m.largest_loss:+,.2f}",
            f"  Avg Duration:      {m.avg_trade_duration:.1f} min",
            "",
            f"  Signals Generated: {len(self.signals)}",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary for serialization"""
        return {
            'strategy_name': self.strategy_name,
            'config': {
                'start_date': self.config.start_date.isoformat(),
                'end_date': self.config.end_date.isoformat(),
                'initial_capital': self.config.initial_capital,
                'symbol': self.config.symbol,
                'timeframe': self.config.timeframe,
                'updown_threshold_pct': self.config.updown_threshold_pct,
                'updown_duration_minutes': self.config.updown_duration_minutes,
                'data_source': self.config.data_source,
                'slippage_pct': self.config.slippage_pct,
            },
            'metrics': {
                'total_return': self.metrics.total_return,
                'annualized_return': self.metrics.annualized_return,
                'volatility': self.metrics.volatility,
                'max_drawdown': self.metrics.max_drawdown,
                'sharpe_ratio': self.metrics.sharpe_ratio,
                'sortino_ratio': self.metrics.sortino_ratio,
                'calmar_ratio': self.metrics.calmar_ratio,
                'total_trades': self.metrics.total_trades,
                'winning_trades': self.metrics.winning_trades,
                'losing_trades': self.metrics.losing_trades,
                'win_rate': self.metrics.win_rate,
                'profit_factor': self.metrics.profit_factor,
                'total_pnl': self.metrics.total_pnl,
                'final_capital': self.metrics.final_capital,
            },
            'equity_curve': {
                'timestamps': [t.isoformat() for t in self.equity_curve.index],
                'values': self.equity_curve.tolist(),
            },
            'summary_stats': {
                'trades_count': len(self.trades),
                'signals_count': len(self.signals),
                'price_bars': len(self.price_data),
            }
        }

    def save_to_json(self, filepath: str):
        """Save results to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        print(f"Results saved to {filepath}")

    def save_equity_curve(self, filepath: str):
        """Save equity curve to CSV"""
        df = pd.DataFrame({
            'timestamp': self.equity_curve.index,
            'equity': self.equity_curve.values
        })
        df.to_csv(filepath, index=False)
        print(f"Equity curve saved to {filepath}")

    def save_trades(self, filepath: str):
        """Save trades to CSV"""
        trades_data = []
        for bt_pos in self.trades:
            pos = bt_pos.position
            trades_data.append({
                'entry_time': bt_pos.entry_timestamp,
                'exit_time': bt_pos.exit_timestamp,
                'token_id': pos.token_id,
                'side': pos.side,
                'entry_price': pos.entry_price,
                'exit_price': bt_pos.exit_price,
                'size': pos.size,
                'pnl': bt_pos.realized_pnl,
                'exit_reason': bt_pos.exit_reason,
            })

        df = pd.DataFrame(trades_data)
        df.to_csv(filepath, index=False)
        print(f"Trades saved to {filepath}")

    def get_trade_list(self) -> List[Dict[str, Any]]:
        """Get trades as list of dictionaries"""
        return [
            {
                'entry_time': bt_pos.entry_timestamp,
                'exit_time': bt_pos.exit_timestamp,
                'token_id': bt_pos.position.token_id,
                'side': bt_pos.position.side,
                'entry_price': bt_pos.position.entry_price,
                'exit_price': bt_pos.exit_price,
                'size': bt_pos.position.size,
                'pnl': bt_pos.realized_pnl,
                'exit_reason': bt_pos.exit_reason,
            }
            for bt_pos in self.trades
        ]

    def save_price_data(self, filepath: str):
        """Save historical price data to CSV"""
        if not self.price_data.empty:
            self.price_data.to_csv(filepath, index=False)
            print(f"Price data saved to {filepath}")
        else:
            print("No price data to save")

    def save_signals(self, filepath: str):
        """Save all generated signals to CSV"""
        if self.signals:
            df = pd.DataFrame(self.signals)
            df.to_csv(filepath, index=False)
            print(f"Signals saved to {filepath}")
        else:
            print("No signals to save")

    def save_all_data(self, output_dir: str = "backtest_output"):
        """
        Save all backtest data to multiple CSV files

        Creates:
        - {output_dir}/price_data.csv      - Historical OHLCV data
        - {output_dir}/equity_curve.csv    - Equity over time
        - {output_dir}/trades.csv          - All executed trades
        - {output_dir}/signals.csv         - All generated signals
        - {output_dir}/summary.json        - Complete results summary
        """
        import os

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Save price data
        if not self.price_data.empty:
            self.price_data.to_csv(f"{output_dir}/price_data.csv", index=False)
            print(f"  Saved: {output_dir}/price_data.csv ({len(self.price_data)} rows)")

        # Save equity curve
        if not self.equity_curve.empty:
            equity_df = pd.DataFrame({
                'timestamp': self.equity_curve.index,
                'equity': self.equity_curve.values
            })
            equity_df.to_csv(f"{output_dir}/equity_curve.csv", index=False)
            print(f"  Saved: {output_dir}/equity_curve.csv ({len(equity_df)} rows)")

        # Save trades
        if self.trades:
            trades_df = pd.DataFrame(self.get_trade_list())
            trades_df.to_csv(f"{output_dir}/trades.csv", index=False)
            print(f"  Saved: {output_dir}/trades.csv ({len(trades_df)} rows)")

        # Save signals
        if self.signals:
            signals_df = pd.DataFrame(self.signals)
            signals_df.to_csv(f"{output_dir}/signals.csv", index=False)
            print(f"  Saved: {output_dir}/signals.csv ({len(signals_df)} rows)")

        # Save simulated market data (YES/NO prices)
        if self.simulated_market:
            market_df = pd.DataFrame(self.simulated_market)
            market_df.to_csv(f"{output_dir}/simulated_market.csv", index=False)
            print(f"  Saved: {output_dir}/simulated_market.csv ({len(market_df)} rows)")

        # Save summary JSON
        self.save_to_json(f"{output_dir}/summary.json")

        print(f"\nAll data saved to: {output_dir}/")

    def print_trades(self, limit: int = 10):
        """Print recent trades"""
        print(f"\nRecent Trades (last {limit}):")
        print("-" * 80)

        for bt_pos in self.trades[-limit:]:
            pos = bt_pos.position
            pnl_str = f"${bt_pos.realized_pnl:+.2f}" if bt_pos.realized_pnl else "N/A"
            exit_price = bt_pos.exit_price if bt_pos.exit_price else 0
            print(f"  {bt_pos.entry_timestamp.strftime('%Y-%m-%d %H:%M')} | "
                  f"{pos.side:4} @ {pos.entry_price:.4f} -> "
                  f"{exit_price:.4f} | "
                  f"P&L: {pnl_str:>10} | {bt_pos.exit_reason or 'open'}")
