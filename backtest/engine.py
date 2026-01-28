"""Main backtesting engine"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging
import asyncio

import pandas as pd

from strategy.base_strategy import BaseStrategy, Signal, SignalAction
from backtest.config import BacktestConfig
from backtest.data_provider import DataProviderFactory, BaseDataProvider
from backtest.market_simulator import UpDownMarketSimulator, UpDownMarketConfig, SimulatedMarketData
from backtest.order_simulator import OrderSimulator
from backtest.position_tracker import PositionTracker
from backtest.metrics import MetricsCalculator, BacktestMetrics
from backtest.results import BacktestResults


class BacktestEngine:
    """
    Main backtesting engine

    Workflow:
    1. Load historical price data (e.g., SOL from Binance)
    2. For each timestamp:
       a. Simulate UpDown market based on price
       b. Generate market_data compatible with BaseStrategy
       c. Call strategy.analyze(market_data)
       d. If signal, execute simulated order
       e. Check SL/TP for open positions
       f. Record equity
    3. Calculate performance metrics
    4. Generate report
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        config: BacktestConfig
    ):
        """
        Initialize backtest engine

        Args:
            strategy: Trading strategy to backtest
            config: Backtest configuration
        """
        self.strategy = strategy
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.data_provider: BaseDataProvider = DataProviderFactory.create(config.data_source)
        self.order_simulator = OrderSimulator(
            slippage_pct=config.slippage_pct,
            maker_fee=config.maker_fee,
            taker_fee=config.taker_fee,
            available_liquidity=config.liquidity_depth
        )
        self.position_tracker = PositionTracker(config.initial_capital)

        # State
        self.price_data: Optional[pd.DataFrame] = None
        self.equity_curve: List[float] = []
        self.timestamps: List[datetime] = []
        self.signals_generated: List[Dict[str, Any]] = []
        self.market_simulator: Optional[UpDownMarketSimulator] = None

        # Track simulated market data for export
        self.simulated_market_history: List[Dict[str, Any]] = []

        # Current market direction for alternating
        self._current_direction = config.market_direction or "up"

    async def run(self) -> BacktestResults:
        """
        Execute the complete backtest

        Returns:
            BacktestResults with metrics and data
        """
        self.logger.info(f"Starting backtest: {self.config.start_date} to {self.config.end_date}")
        self.logger.info(f"Strategy: {self.strategy.name}")
        self.logger.info(f"Symbol: {self.config.symbol}, Timeframe: {self.config.timeframe}")

        # 1. Load historical data
        await self._load_price_data()

        if self.price_data.empty:
            self.logger.error("No price data loaded")
            return self._create_empty_results()

        # 2. Initialize market simulator
        self._initialize_market_simulator()

        # 3. Main backtest loop
        total_bars = len(self.price_data)
        self.logger.info(f"Processing {total_bars} price bars...")

        for idx, row in self.price_data.iterrows():
            timestamp = row['timestamp']
            price = row['close']

            # Progress logging every 1000 bars
            if idx % 1000 == 0:
                self.logger.debug(f"Processing bar {idx}/{total_bars}")

            # Generate simulated market data
            market_data = self._generate_market_data(price, timestamp)

            # Update open positions with current prices
            self._update_positions(market_data)

            # Check stop-loss and take-profit
            self._check_stop_loss_take_profit(market_data, timestamp)

            # Run strategy
            strategy_input = self._to_strategy_format(market_data)
            signal = self.strategy.analyze(strategy_input)

            if signal:
                self._process_signal(signal, market_data, timestamp)

            # Record equity
            self._record_equity(market_data, timestamp)

        # 4. Close all open positions at end
        self._close_all_positions_at_end()

        # 5. Calculate metrics
        metrics = self._calculate_metrics()

        # 6. Generate results
        self.logger.info("Backtest completed")
        self.logger.info(f"Total trades: {metrics.total_trades}")
        self.logger.info(f"Total return: {metrics.total_return:.2f}%")

        return BacktestResults(
            config=self.config,
            strategy_name=self.strategy.name,
            metrics=metrics,
            equity_curve=pd.Series(self.equity_curve, index=self.timestamps),
            trades=self.position_tracker.closed_positions,
            signals=self.signals_generated,
            price_data=self.price_data,
            simulated_market=self.simulated_market_history
        )

    async def _load_price_data(self):
        """Load historical price data"""
        self.logger.info(f"Loading data from {self.config.data_source}...")

        self.price_data = await self.data_provider.fetch_historical_data(
            symbol=self.config.symbol,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            timeframe=self.config.timeframe
        )

        if not self.price_data.empty:
            self.logger.info(f"Loaded {len(self.price_data)} price bars")
            self.logger.info(f"Price range: ${self.price_data['close'].min():.2f} - "
                           f"${self.price_data['close'].max():.2f}")

    def _initialize_market_simulator(self):
        """Initialize the UpDown market simulator"""
        if self.price_data.empty:
            return

        # Use first price as base
        base_price = self.price_data.iloc[0]['close']
        start_time = self.price_data.iloc[0]['timestamp']

        self._create_new_market(base_price, start_time)

    def _create_new_market(self, base_price: float, start_time: datetime):
        """Create a new UpDown market"""
        # Alternate direction if not fixed
        if not self.config.market_direction:
            if self.market_simulator:
                current_dir = self.market_simulator.config.direction
                self._current_direction = "down" if current_dir == "up" else "up"

        market_config = UpDownMarketConfig(
            base_price=base_price,
            threshold_pct=self.config.updown_threshold_pct,
            direction=self._current_direction,
            duration_minutes=self.config.updown_duration_minutes,
            market_start_time=start_time
        )

        self.market_simulator = UpDownMarketSimulator(
            config=market_config,
            spread=self.config.base_spread
        )

        self.logger.debug(f"New market created: {self._current_direction} {self.config.updown_threshold_pct}% "
                         f"from {base_price:.2f}")

    def _generate_market_data(
        self,
        price: float,
        timestamp: datetime
    ) -> SimulatedMarketData:
        """Generate simulated market data"""
        # Check if market has expired
        market_end = (self.market_simulator.config.market_start_time +
                     timedelta(minutes=self.market_simulator.config.duration_minutes))

        if timestamp >= market_end:
            # Create new market with current price as base
            self._create_new_market(price, timestamp)

        return self.market_simulator.generate_market_data(price, timestamp)

    def _to_strategy_format(self, market_data: SimulatedMarketData) -> Dict[str, Any]:
        """
        Convert SimulatedMarketData to format expected by BaseStrategy.analyze()
        """
        return {
            # Standard fields expected by strategies
            'market': market_data.market,
            'yes_price': market_data.yes_price,
            'no_price': market_data.no_price,
            'yes_token_id': market_data.yes_token_id,
            'no_token_id': market_data.no_token_id,
            'orderbook': market_data.orderbook,

            # Compatibility aliases
            'price': market_data.yes_price,
            'token_id': market_data.yes_token_id,

            # Additional context
            'sol_price': market_data.sol_price,
            'underlying_price': market_data.sol_price,
            'time_remaining': market_data.time_remaining_minutes,
            'timestamp': market_data.timestamp,

            # Volume (simulated)
            'volume': 1000.0,
            'liquidity': self.config.liquidity_depth,
        }

    def _update_positions(self, market_data: SimulatedMarketData):
        """Update prices for open positions"""
        self.position_tracker.update_position_price(
            market_data.yes_token_id,
            market_data.yes_price
        )
        self.position_tracker.update_position_price(
            market_data.no_token_id,
            market_data.no_price
        )

    def _check_stop_loss_take_profit(
        self,
        market_data: SimulatedMarketData,
        timestamp: datetime
    ):
        """Check and execute SL/TP for open positions"""
        # Check YES token position
        self.position_tracker.check_stop_loss_take_profit(
            market_data.yes_token_id,
            market_data.yes_price,
            timestamp
        )

        # Check NO token position
        self.position_tracker.check_stop_loss_take_profit(
            market_data.no_token_id,
            market_data.no_price,
            timestamp
        )

    def _process_signal(
        self,
        signal: Signal,
        market_data: SimulatedMarketData,
        timestamp: datetime
    ):
        """Process a trading signal"""
        # Record signal
        self.signals_generated.append({
            'timestamp': timestamp,
            'action': signal.action.value,
            'token_id': signal.token_id,
            'price': signal.price,
            'size': signal.size,
            'confidence': signal.confidence,
            'reason': signal.reason,
        })

        # Handle different actions
        if signal.action == SignalAction.HOLD:
            return

        if signal.action == SignalAction.CLOSE:
            self.position_tracker.close_position(
                signal.token_id,
                signal.price,
                timestamp,
                reason="signal_close"
            )
            return

        # BUY or SELL
        if signal.action in [SignalAction.BUY, SignalAction.SELL]:
            # Check if we already have a position
            if self.position_tracker.has_open_position(signal.token_id):
                self.logger.debug(f"Already have position for {signal.token_id}")
                return

            # Validate strategy signal
            if not self.strategy.validate_signal(signal):
                self.logger.debug(f"Signal validation failed: {signal}")
                return

            # Check capital
            if self.position_tracker.current_capital < signal.price * signal.size:
                self.logger.debug("Insufficient capital for trade")
                return

            # Execute order
            fill_result = self.order_simulator.execute_order(
                token_id=signal.token_id,
                side=signal.action.value,
                price=signal.price,
                size=signal.size,
                order_type='MARKET',
                timestamp=timestamp
            )

            if not fill_result.success:
                self.logger.debug(f"Order failed: {fill_result.message}")
                return

            # Calculate SL/TP
            if signal.action == SignalAction.BUY:
                stop_loss = fill_result.fill_price * (1 - self.config.stop_loss_pct)
                take_profit = fill_result.fill_price * (1 + self.config.take_profit_pct)
            else:
                stop_loss = fill_result.fill_price * (1 + self.config.stop_loss_pct)
                take_profit = fill_result.fill_price * (1 - self.config.take_profit_pct)

            # Open position
            self.position_tracker.open_position(
                token_id=signal.token_id,
                market_id=market_data.market['id'],
                side=signal.action.value,
                entry_price=fill_result.fill_price,
                size=fill_result.fill_size,
                timestamp=timestamp,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    'signal_confidence': signal.confidence,
                    'signal_reason': signal.reason,
                    'slippage': fill_result.slippage_cost,
                }
            )

    def _record_equity(self, market_data: SimulatedMarketData, timestamp: datetime):
        """Record current equity and market state"""
        current_prices = {
            market_data.yes_token_id: market_data.yes_price,
            market_data.no_token_id: market_data.no_price
        }
        equity = self.position_tracker.get_equity(current_prices)
        self.equity_curve.append(equity)
        self.timestamps.append(timestamp)

        # Record simulated market data for export
        self.simulated_market_history.append({
            'timestamp': timestamp,
            'underlying_price': market_data.sol_price,
            'yes_price': market_data.yes_price,
            'no_price': market_data.no_price,
            'time_remaining_min': market_data.time_remaining_minutes,
            'market_direction': market_data.market.get('direction', ''),
            'market_threshold': market_data.market.get('threshold_pct', 0),
            'equity': equity,
        })

    def _close_all_positions_at_end(self):
        """Close all open positions at backtest end"""
        if self.price_data.empty:
            return

        final_row = self.price_data.iloc[-1]
        final_timestamp = final_row['timestamp']
        final_price = final_row['close']

        # Generate final market data
        final_market = self.market_simulator.generate_market_data(final_price, final_timestamp)

        # Close all open positions
        for token_id in list(self.position_tracker.open_positions.keys()):
            if 'yes' in token_id:
                price = final_market.yes_price
            else:
                price = final_market.no_price

            self.position_tracker.close_position(
                token_id,
                price,
                final_timestamp,
                reason="backtest_end"
            )

    def _calculate_metrics(self) -> BacktestMetrics:
        """Calculate performance metrics"""
        equity_series = pd.Series(self.equity_curve, index=self.timestamps)

        # Convert closed positions to trade format
        trades = [
            {
                'entry_time': pos.entry_timestamp,
                'exit_time': pos.exit_timestamp,
                'pnl': pos.realized_pnl,
                'entry_price': pos.position.entry_price,
                'exit_price': pos.exit_price,
                'side': pos.position.side,
                'reason': pos.exit_reason
            }
            for pos in self.position_tracker.closed_positions
        ]

        # Get timeframe in minutes
        timeframe_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480,
            '12h': 720, '1d': 1440, '3d': 4320, '1w': 10080
        }
        timeframe_minutes = timeframe_map.get(self.config.timeframe, 1)

        return MetricsCalculator.calculate(
            equity_curve=equity_series,
            trades=trades,
            initial_capital=self.config.initial_capital,
            timeframe_minutes=timeframe_minutes
        )

    def _create_empty_results(self) -> BacktestResults:
        """Create empty results for error cases"""
        return BacktestResults(
            config=self.config,
            strategy_name=self.strategy.name,
            metrics=MetricsCalculator._empty_metrics(self.config.initial_capital),
            equity_curve=pd.Series(dtype=float),
            trades=[],
            signals=[],
            price_data=pd.DataFrame(),
            simulated_market=[]
        )


def run_backtest(
    strategy: BaseStrategy,
    config: BacktestConfig
) -> BacktestResults:
    """
    Convenience function to run a backtest synchronously

    Args:
        strategy: Strategy to backtest
        config: Backtest configuration

    Returns:
        BacktestResults
    """
    engine = BacktestEngine(strategy, config)
    return asyncio.run(engine.run())
