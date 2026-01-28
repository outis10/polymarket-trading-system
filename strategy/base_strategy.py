"""Base strategy class and signal definition"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Any
from enum import Enum


class SignalAction(Enum):
    """Trading signal actions"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


@dataclass
class Signal:
    """Trading signal with metadata"""
    action: SignalAction
    token_id: str
    confidence: float  # 0-1
    price: float
    size: float
    reason: str
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate signal parameters"""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        if self.price <= 0:
            raise ValueError("Price must be positive")
        if self.size <= 0:
            raise ValueError("Size must be positive")
    
    def __str__(self) -> str:
        return (
            f"Signal({self.action.value} {self.size} @ {self.price:.4f}, "
            f"confidence={self.confidence:.2f}, reason='{self.reason}')"
        )


class BaseStrategy(ABC):
    """Base class for all trading strategies"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize strategy
        
        Args:
            name: Strategy name
            config: Strategy configuration dictionary
        """
        self.name = name
        self.config = config
        self.enabled = True
        self._validate_config()
    
    def _validate_config(self):
        """Validate strategy configuration - override in subclasses if needed"""
        pass
    
    @abstractmethod
    def analyze(self, market_data: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze market data and generate trading signal
        
        Args:
            market_data: Dictionary containing:
                - market: Market information
                - orderbook: Current order book
                - price: Current price
                - volume: Trading volume
                - historical_data: Historical price data (if available)
        
        Returns:
            Signal object if opportunity found, None otherwise
        """
        pass
    
    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate if signal meets minimum requirements
        
        Args:
            signal: The signal to validate
        
        Returns:
            True if signal is valid, False otherwise
        """
        # Check confidence threshold
        min_confidence = self.config.get('min_confidence', 0.7)
        if signal.confidence < min_confidence:
            return False
        
        # Check price bounds
        if signal.price <= 0 or signal.price > 1:  # Polymarket prices are 0-1
            return False
        
        # Check size
        min_size = self.config.get('min_size', 1.0)
        max_size = self.config.get('max_size', 1000.0)
        if not min_size <= signal.size <= max_size:
            return False
        
        return True
    
    def enable(self):
        """Enable the strategy"""
        self.enabled = True
    
    def disable(self):
        """Disable the strategy"""
        self.enabled = False
    
    def update_config(self, new_config: Dict[str, Any]):
        """
        Update strategy configuration
        
        Args:
            new_config: New configuration dictionary
        """
        self.config.update(new_config)
        self._validate_config()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current strategy status
        
        Returns:
            Status dictionary
        """
        return {
            'name': self.name,
            'enabled': self.enabled,
            'config': self.config
        }
    
    def __str__(self) -> str:
        return f"{self.name} (enabled={self.enabled})"
