"""Backtest configuration"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class BacktestConfig:
    """Configuration for backtesting"""

    # Time period
    start_date: datetime
    end_date: datetime

    # Capital
    initial_capital: float = 10000.0

    # UpDown market parameters
    updown_threshold_pct: float = 5.0      # e.g., "SOL goes up 5%"
    updown_duration_minutes: int = 15       # e.g., "in 15 minutes"

    # Simulation costs
    maker_fee: float = 0.0                  # Polymarket has no maker fee
    taker_fee: float = 0.0                  # Polymarket has no taker fee
    slippage_pct: float = 0.005             # 0.5% estimated slippage

    # Data source
    data_source: str = "binance"            # "binance" or "coingecko"
    timeframe: str = "1m"                   # Data granularity
    symbol: str = "SOLUSDT"                 # Trading pair

    # Market simulation
    base_spread: float = 0.02               # Base YES/NO spread
    liquidity_depth: float = 10000.0        # Simulated liquidity

    # Risk management
    stop_loss_pct: float = 0.05             # 5% stop loss
    take_profit_pct: float = 0.15           # 15% take profit

    # Optional
    market_direction: Optional[str] = None  # "up", "down", or None for alternating

    def __post_init__(self):
        """Validate configuration"""
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.updown_threshold_pct <= 0:
            raise ValueError("updown_threshold_pct must be positive")
        if self.updown_duration_minutes <= 0:
            raise ValueError("updown_duration_minutes must be positive")
        if self.data_source not in ["binance", "coingecko"]:
            raise ValueError("data_source must be 'binance' or 'coingecko'")
        if self.market_direction and self.market_direction not in ["up", "down"]:
            raise ValueError("market_direction must be 'up', 'down', or None")
