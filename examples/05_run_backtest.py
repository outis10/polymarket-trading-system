#!/usr/bin/env python3
"""
Example: Run a backtest on SOL UpDown markets

This script demonstrates how to:
1. Configure a backtest for SOL price movements
2. Use the existing SimpleArbitrageStrategy
3. Run the backtest and analyze results

No credentials required - uses public Binance API for historical data.
"""

import asyncio
import logging
from datetime import datetime, timedelta

# Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.config import BacktestConfig
from backtest.engine import BacktestEngine
from strategy.arbitrage import SimpleArbitrageStrategy


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_simple_backtest():
    """
    Run a simple backtest using the arbitrage strategy
    """
    print("\n" + "=" * 60)
    print("POLYMARKET BACKTEST - SOL UpDown Markets")
    print("=" * 60 + "\n")

    # 1. Configure the backtest
    config = BacktestConfig(
        # Time period: Last 7 days of available data
        start_date=datetime(2026, 1, 10, 0, 0),
        end_date=datetime(2026, 1, 17, 0, 0),

        # Capital
        initial_capital=10000.0,

        # UpDown market parameters
        updown_threshold_pct=5.0,      # "Will SOL move 5%?"
        updown_duration_minutes=15,     # "In 15 minutes"

        # Data source
        data_source="binance",
        symbol="SOLUSDT",
        timeframe="5m",                 # 5-minute candles for faster backtest

        # Simulation parameters
        slippage_pct=0.005,            # 0.5% slippage
        base_spread=0.02,               # 2% spread

        # Risk management
        stop_loss_pct=0.05,            # 5% stop loss
        take_profit_pct=0.15,          # 15% take profit
    )

    print("Configuration:")
    print(f"  Period: {config.start_date.strftime('%Y-%m-%d %H:%M')} to {config.end_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Symbol: {config.symbol}")
    print(f"  Timeframe: {config.timeframe}")
    print(f"  Initial Capital: ${config.initial_capital:,.2f}")
    print(f"  UpDown Threshold: {config.updown_threshold_pct}%")
    print(f"  Market Duration: {config.updown_duration_minutes} min")
    print()

    # 2. Create the strategy
    strategy = SimpleArbitrageStrategy({
        'min_spread': 0.02,            # Minimum spread to trigger
        'max_spread': 0.10,            # Maximum spread to consider
        'position_size': 100.0,        # Position size in USD
        'min_confidence': 0.6,         # Minimum confidence
        'min_size': 10.0,
        'max_size': 500.0,
    })

    print(f"Strategy: {strategy.name}")
    print(f"  Min Spread: {strategy.config['min_spread']*100}%")
    print(f"  Position Size: ${strategy.config['position_size']}")
    print()

    # 3. Run the backtest
    print("Running backtest...")
    print("-" * 40)

    engine = BacktestEngine(strategy=strategy, config=config)
    results = await engine.run()

    # 4. Display results
    print("\n" + results.summary())

    # 5. Show recent trades
    if results.trades:
        results.print_trades(limit=5)

    # 6. Save results (optional)
    # results.save_to_json('backtest_results.json')
    # results.save_equity_curve('equity_curve.csv')
    # results.save_trades('trades.csv')

    return results


async def run_comparison_backtest():
    """
    Run backtests with different configurations to compare
    """
    print("\n" + "=" * 60)
    print("STRATEGY COMPARISON BACKTEST")
    print("=" * 60 + "\n")

    base_config = {
        'start_date': datetime(2026, 1, 10, 0, 0),
        'end_date': datetime(2026, 1, 17, 0, 0),
        'initial_capital': 10000.0,
        'data_source': 'binance',
        'symbol': 'SOLUSDT',
        'timeframe': '15m',
    }

    # Test different threshold values
    thresholds = [3.0, 5.0, 7.0]
    results_list = []

    for threshold in thresholds:
        print(f"\nTesting threshold: {threshold}%")
        print("-" * 40)

        config = BacktestConfig(
            **base_config,
            updown_threshold_pct=threshold,
            updown_duration_minutes=15,
        )

        strategy = SimpleArbitrageStrategy({
            'min_spread': 0.02,
            'max_spread': 0.10,
            'position_size': 100.0,
            'min_confidence': 0.6,
        })

        engine = BacktestEngine(strategy=strategy, config=config)
        results = await engine.run()

        results_list.append({
            'threshold': threshold,
            'total_return': results.metrics.total_return,
            'sharpe': results.metrics.sharpe_ratio,
            'max_dd': results.metrics.max_drawdown,
            'trades': results.metrics.total_trades,
            'win_rate': results.metrics.win_rate,
        })

        print(f"  Return: {results.metrics.total_return:+.2f}%")
        print(f"  Sharpe: {results.metrics.sharpe_ratio:.3f}")
        print(f"  Trades: {results.metrics.total_trades}")

    # Summary comparison
    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"{'Threshold':>10} | {'Return':>10} | {'Sharpe':>8} | {'Max DD':>8} | {'Trades':>6} | {'Win%':>6}")
    print("-" * 60)

    for r in results_list:
        print(f"{r['threshold']:>9.1f}% | {r['total_return']:>+9.2f}% | {r['sharpe']:>8.3f} | "
              f"{r['max_dd']:>7.2f}% | {r['trades']:>6} | {r['win_rate']:>5.1f}%")

    return results_list


def main():
    """Main entry point"""
    print("\nPolymarket Backtesting Framework")
    print("================================\n")

    print("Choose backtest type:")
    print("  1. Simple backtest (recommended for first run)")
    print("  2. Strategy comparison")
    print()

    choice = input("Enter choice (1 or 2, default=1): ").strip() or "1"

    if choice == "1":
        asyncio.run(run_simple_backtest())
    elif choice == "2":
        asyncio.run(run_comparison_backtest())
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
