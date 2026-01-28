"""Market simulator for UpDown prediction markets"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, List
import math


@dataclass
class UpDownMarketConfig:
    """Configuration for an UpDown market"""
    base_price: float              # Initial price when market was created
    threshold_pct: float           # Percentage change threshold (e.g., 5%)
    direction: str                 # "up" or "down"
    duration_minutes: int          # Market duration
    market_start_time: datetime    # When the market started


@dataclass
class SimulatedMarketData:
    """
    Simulated market data compatible with BaseStrategy.analyze()

    This structure matches what strategies expect from real Polymarket data.
    """
    timestamp: datetime
    market: Dict[str, Any]         # Market information
    yes_price: float               # YES token price (0-1)
    no_price: float                # NO token price (0-1)
    yes_token_id: str              # YES token ID (simulated)
    no_token_id: str               # NO token ID (simulated)
    orderbook: Dict[str, Any]      # Simulated orderbook
    sol_price: float               # Current underlying price
    time_remaining_minutes: float  # Time remaining until resolution


class UpDownMarketSimulator:
    """
    Simulates YES/NO prices for UpDown prediction markets

    The model calculates probability based on:
    1. Distance to threshold - how close is current price to the target
    2. Time remaining - less time = more certainty
    3. Implied volatility - expected price movement

    For example, if SOL is at $100 and the market is "SOL up 5% in 15min":
    - If SOL is at $104, YES has high probability (close to threshold)
    - If SOL is at $95, NO has high probability (far from threshold)
    - As time decreases, prices converge to 0 or 1
    """

    def __init__(self, config: UpDownMarketConfig, spread: float = 0.02):
        """
        Initialize market simulator

        Args:
            config: Market configuration
            spread: Base spread between YES and NO prices
        """
        self.config = config
        self.spread = spread
        self.market_id = f"sim_updown_{config.direction}_{config.threshold_pct}pct"
        self.yes_token_id = f"{self.market_id}_yes"
        self.no_token_id = f"{self.market_id}_no"

        # Volatility per minute (approximately 0.1% for SOL)
        # This can be calibrated with historical data
        self.volatility_per_minute = 0.1

    def calculate_probability(
        self,
        current_price: float,
        current_time: datetime
    ) -> float:
        """
        Calculate probability of YES outcome

        Uses a simplified binary option pricing model inspired by Black-Scholes.

        Args:
            current_price: Current price of underlying asset
            current_time: Current timestamp

        Returns:
            Probability of YES (0-1)
        """
        # Calculate current percentage change from base
        price_change_pct = ((current_price - self.config.base_price) /
                           self.config.base_price) * 100

        # Calculate time remaining
        market_end = (self.config.market_start_time +
                     timedelta(minutes=self.config.duration_minutes))
        time_remaining = (market_end - current_time).total_seconds() / 60
        time_remaining = max(0, time_remaining)

        # If market has expired, return binary result
        if time_remaining <= 0:
            if self.config.direction == "up":
                return 1.0 if price_change_pct >= self.config.threshold_pct else 0.0
            else:
                return 1.0 if price_change_pct <= -self.config.threshold_pct else 0.0

        # Calculate distance to threshold
        if self.config.direction == "up":
            target_pct = self.config.threshold_pct
            distance_to_threshold = target_pct - price_change_pct
        else:
            target_pct = -self.config.threshold_pct
            distance_to_threshold = target_pct - price_change_pct

        # Expected move based on volatility and time
        expected_move = self.volatility_per_minute * math.sqrt(time_remaining)

        # Prevent division by zero
        if expected_move < 0.001:
            expected_move = 0.001

        # Calculate z-score (negative because we want P(price reaches threshold))
        z_score = -distance_to_threshold / expected_move

        # Convert to probability using normal CDF approximation
        probability = self._normal_cdf(z_score)

        # Clamp to realistic bounds (never 0% or 100% certainty)
        return max(0.01, min(0.99, probability))

    def _normal_cdf(self, x: float) -> float:
        """
        Approximate standard normal CDF

        Uses a fast approximation that's accurate to ~0.001
        """
        # Approximation using tanh
        return 0.5 * (1 + math.tanh(math.sqrt(2 / math.pi) * (x + 0.044715 * x**3)))

    def generate_market_data(
        self,
        current_price: float,
        current_time: datetime
    ) -> SimulatedMarketData:
        """
        Generate simulated market data compatible with BaseStrategy.analyze()

        Args:
            current_price: Current price of underlying (e.g., SOL)
            current_time: Current timestamp

        Returns:
            SimulatedMarketData that can be passed to strategy.analyze()
        """
        # Calculate YES probability
        yes_prob = self.calculate_probability(current_price, current_time)
        no_prob = 1 - yes_prob

        # Apply spread (market maker takes a cut)
        half_spread = self.spread / 2
        yes_price = yes_prob - half_spread
        no_price = no_prob - half_spread

        # Ensure prices are valid (0.01 to 0.99)
        yes_price = max(0.01, min(0.99, yes_price))
        no_price = max(0.01, min(0.99, no_price))

        # Calculate time remaining
        market_end = (self.config.market_start_time +
                     timedelta(minutes=self.config.duration_minutes))
        time_remaining = max(0, (market_end - current_time).total_seconds() / 60)

        # Generate simulated orderbook
        orderbook = self._generate_orderbook(yes_price, no_price)

        # Build market info dict
        market_info = {
            'id': self.market_id,
            'question': (f"Will {self.config.direction.upper()} move "
                        f"{self.config.threshold_pct}% in {self.config.duration_minutes}min?"),
            'base_price': self.config.base_price,
            'threshold_pct': self.config.threshold_pct,
            'direction': self.config.direction,
            'duration_minutes': self.config.duration_minutes,
            'start_time': self.config.market_start_time.isoformat(),
            'end_time': market_end.isoformat(),
            'resolved': time_remaining <= 0,
        }

        return SimulatedMarketData(
            timestamp=current_time,
            market=market_info,
            yes_price=yes_price,
            no_price=no_price,
            yes_token_id=self.yes_token_id,
            no_token_id=self.no_token_id,
            orderbook=orderbook,
            sol_price=current_price,
            time_remaining_minutes=time_remaining
        )

    def _generate_orderbook(
        self,
        yes_price: float,
        no_price: float,
        depth: int = 5
    ) -> Dict[str, Any]:
        """
        Generate a simulated orderbook with depth

        Args:
            yes_price: Current YES price
            no_price: Current NO price
            depth: Number of price levels

        Returns:
            Orderbook dictionary
        """
        # Generate bids and asks around the price
        yes_bids = []
        yes_asks = []

        for i in range(depth):
            # Bids below current price
            bid_price = max(0.01, yes_price - 0.01 * (i + 1))
            bid_size = 100 * (depth - i)  # More size at better prices
            yes_bids.append({'price': round(bid_price, 4), 'size': bid_size})

            # Asks above current price
            ask_price = min(0.99, yes_price + 0.01 * (i + 1))
            ask_size = 100 * (depth - i)
            yes_asks.append({'price': round(ask_price, 4), 'size': ask_size})

        return {
            'yes': {
                'bids': yes_bids,
                'asks': yes_asks,
                'best_bid': yes_bids[0]['price'] if yes_bids else 0,
                'best_ask': yes_asks[0]['price'] if yes_asks else 1,
            },
            'no': {
                'bids': [{'price': round(no_price - 0.01 * (i + 1), 4), 'size': 100}
                        for i in range(depth)],
                'asks': [{'price': round(no_price + 0.01 * (i + 1), 4), 'size': 100}
                        for i in range(depth)],
            }
        }

    def get_market_outcome(self, final_price: float) -> bool:
        """
        Determine if YES wins based on final price

        Args:
            final_price: Final price of underlying at market resolution

        Returns:
            True if YES wins, False if NO wins
        """
        price_change_pct = ((final_price - self.config.base_price) /
                           self.config.base_price) * 100

        if self.config.direction == "up":
            return price_change_pct >= self.config.threshold_pct
        else:
            return price_change_pct <= -self.config.threshold_pct
