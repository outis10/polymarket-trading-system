"""Momentum-based strategy for UpDown markets"""

from typing import Dict, Any, Optional, List
from strategy.base_strategy import BaseStrategy, Signal, SignalAction


class MomentumStrategy(BaseStrategy):
    """
    Simple momentum strategy for UpDown prediction markets

    Logic:
    - If price is trending towards threshold, buy YES
    - If price is trending away from threshold, buy NO
    - Uses time remaining as a factor in confidence
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize momentum strategy

        Config parameters:
        - position_size: Size of positions (default: 100)
        - min_confidence: Minimum confidence to trade (default: 0.5)
        - price_threshold_buy: Buy YES if price > this (default: 0.4)
        - price_threshold_sell: Buy NO if price < this (default: 0.6)
        """
        super().__init__("MomentumUpDown", config)
        self._price_history: List[float] = []

    def _validate_config(self):
        """Validate configuration"""
        # Set defaults
        self.config.setdefault('position_size', 100.0)
        self.config.setdefault('min_confidence', 0.5)
        self.config.setdefault('price_threshold_buy', 0.4)
        self.config.setdefault('price_threshold_sell', 0.6)

    def analyze(self, market_data: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze market and generate signal

        Strategy:
        - If YES price > threshold_sell and trending up -> BUY YES
        - If YES price < threshold_buy and trending down -> BUY NO
        """
        if not self.enabled:
            return None

        yes_price = market_data.get('yes_price')
        no_price = market_data.get('no_price')
        yes_token_id = market_data.get('yes_token_id')
        no_token_id = market_data.get('no_token_id')
        time_remaining = market_data.get('time_remaining', 15)

        if None in [yes_price, no_price, yes_token_id, no_token_id]:
            return None

        # Track price history for momentum
        self._price_history.append(yes_price)
        if len(self._price_history) > 10:
            self._price_history.pop(0)

        # Need at least 3 data points for momentum
        if len(self._price_history) < 3:
            return None

        # Calculate momentum (simple moving average comparison)
        recent_avg = sum(self._price_history[-3:]) / 3
        older_avg = sum(self._price_history[:3]) / 3 if len(self._price_history) >= 6 else recent_avg

        momentum = recent_avg - older_avg

        # Get thresholds
        buy_threshold = self.config.get('price_threshold_buy', 0.4)
        sell_threshold = self.config.get('price_threshold_sell', 0.6)
        position_size = self.config.get('position_size', 100.0)

        # Time factor: more confidence with more time remaining
        time_factor = min(1.0, time_remaining / 15.0)

        signal = None

        # Strong YES signal: price is high and momentum is positive
        if yes_price > sell_threshold and momentum > 0.01:
            confidence = min(0.95, 0.6 + momentum * 2 + time_factor * 0.1)
            signal = Signal(
                action=SignalAction.BUY,
                token_id=yes_token_id,
                confidence=confidence,
                price=yes_price,
                size=position_size,
                reason=f"Momentum BUY YES: price={yes_price:.3f}, momentum={momentum:.4f}",
                metadata={
                    'momentum': momentum,
                    'time_remaining': time_remaining,
                    'yes_price': yes_price,
                    'no_price': no_price,
                }
            )

        # Strong NO signal: YES price is low and momentum is negative
        elif yes_price < buy_threshold and momentum < -0.01:
            confidence = min(0.95, 0.6 + abs(momentum) * 2 + time_factor * 0.1)
            signal = Signal(
                action=SignalAction.BUY,
                token_id=no_token_id,
                confidence=confidence,
                price=no_price,
                size=position_size,
                reason=f"Momentum BUY NO: yes_price={yes_price:.3f}, momentum={momentum:.4f}",
                metadata={
                    'momentum': momentum,
                    'time_remaining': time_remaining,
                    'yes_price': yes_price,
                    'no_price': no_price,
                }
            )

        # Validate signal if generated
        if signal and self.validate_signal(signal):
            return signal

        return None
