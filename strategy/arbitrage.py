"""
Simple arbitrage strategy example
Detects price discrepancies between YES and NO tokens
"""
from typing import Dict, Any, Optional
from strategy.base_strategy import BaseStrategy, Signal, SignalAction


class SimpleArbitrageStrategy(BaseStrategy):
    """
    Detects arbitrage opportunities when YES + NO price != 1.0
    
    In prediction markets, YES + NO should always equal 1.0 (or very close).
    If YES + NO < 0.98, there might be an arbitrage opportunity to buy both.
    If YES + NO > 1.02, there might be an opportunity to sell both.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize arbitrage strategy
        
        Config parameters:
        - min_spread: Minimum spread to trigger (default: 0.02)
        - max_spread: Maximum spread to consider valid (default: 0.10)
        - position_size: Size of each leg (default: 10.0)
        """
        super().__init__("SimpleArbitrage", config)
    
    def _validate_config(self):
        """Validate strategy configuration"""
        required = ['min_spread', 'position_size']
        for param in required:
            if param not in self.config:
                raise ValueError(f"Missing required config parameter: {param}")
    
    def analyze(self, market_data: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze market for arbitrage opportunities
        
        Args:
            market_data: Dictionary containing:
                - market: Market info with tokens
                - yes_price: Current YES token price
                - no_price: Current NO token price
                - yes_token_id: YES token ID
                - no_token_id: NO token ID
        
        Returns:
            Signal if opportunity found, None otherwise
        """
        if not self.enabled:
            return None
        
        # Extract data
        yes_price = market_data.get('yes_price')
        no_price = market_data.get('no_price')
        yes_token_id = market_data.get('yes_token_id')
        no_token_id = market_data.get('no_token_id')
        
        # Validate data
        if None in [yes_price, no_price, yes_token_id, no_token_id]:
            return None
        
        # Calculate total and spread
        total = yes_price + no_price
        spread = abs(1.0 - total)
        
        min_spread = self.config.get('min_spread', 0.02)
        max_spread = self.config.get('max_spread', 0.10)
        
        # Check if spread is significant enough
        if spread < min_spread or spread > max_spread:
            return None
        
        # Determine action
        if total < 0.98:
            # Both tokens are underpriced - buy opportunity
            action = SignalAction.BUY
            # Buy the cheaper token for better ROI
            token_id = yes_token_id if yes_price < no_price else no_token_id
            price = min(yes_price, no_price)
            reason = f"Arbitrage: YES+NO={total:.4f} < 1.0, spread={spread:.4f}"
        
        elif total > 1.02:
            # Both tokens are overpriced - sell opportunity
            action = SignalAction.SELL
            # Sell the more expensive token
            token_id = yes_token_id if yes_price > no_price else no_token_id
            price = max(yes_price, no_price)
            reason = f"Arbitrage: YES+NO={total:.4f} > 1.0, spread={spread:.4f}"
        
        else:
            return None
        
        # Calculate confidence based on spread size
        # Larger spreads = higher confidence
        confidence = min(spread / max_spread, 1.0)
        
        # Create signal
        signal = Signal(
            action=action,
            token_id=token_id,
            confidence=confidence,
            price=price,
            size=self.config.get('position_size', 10.0),
            reason=reason,
            metadata={
                'yes_price': yes_price,
                'no_price': no_price,
                'total': total,
                'spread': spread
            }
        )
        
        # Validate signal
        if not self.validate_signal(signal):
            return None
        
        return signal


class PriceInefficacyStrategy(BaseStrategy):
    """
    Detects when a token is significantly mispriced based on simple criteria
    
    For example:
    - Token price < 0.10 for an event that seems likely
    - Token price > 0.90 for an event that seems unlikely
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize price inefficacy strategy
        
        Config parameters:
        - underpriced_threshold: Consider buying below this (default: 0.15)
        - overpriced_threshold: Consider selling above this (default: 0.85)
        - position_size: Position size (default: 20.0)
        """
        super().__init__("PriceInefficacy", config)
    
    def analyze(self, market_data: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze market for mispricing
        
        Args:
            market_data: Dictionary containing:
                - price: Current token price
                - token_id: Token ID
                - volume: Trading volume
                - liquidity: Available liquidity
        
        Returns:
            Signal if opportunity found, None otherwise
        """
        if not self.enabled:
            return None
        
        price = market_data.get('price')
        token_id = market_data.get('token_id')
        volume = market_data.get('volume', 0)
        
        if None in [price, token_id]:
            return None
        
        underpriced = self.config.get('underpriced_threshold', 0.15)
        overpriced = self.config.get('overpriced_threshold', 0.85)
        min_volume = self.config.get('min_volume', 100)
        
        # Check if there's enough volume
        if volume < min_volume:
            return None
        
        # Check for underpriced
        if price < underpriced:
            action = SignalAction.BUY
            confidence = 1 - (price / underpriced)
            reason = f"Underpriced: {price:.4f} < {underpriced}"
        
        # Check for overpriced
        elif price > overpriced:
            action = SignalAction.SELL
            confidence = (price - overpriced) / (1 - overpriced)
            reason = f"Overpriced: {price:.4f} > {overpriced}"
        
        else:
            return None
        
        signal = Signal(
            action=action,
            token_id=token_id,
            confidence=min(confidence, 1.0),
            price=price,
            size=self.config.get('position_size', 20.0),
            reason=reason,
            metadata={
                'volume': volume,
                'threshold': underpriced if action == SignalAction.BUY else overpriced
            }
        )
        
        if not self.validate_signal(signal):
            return None
        
        return signal
