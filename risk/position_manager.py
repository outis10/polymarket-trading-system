"""Position and risk management"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging


@dataclass
class Position:
    """Represents an open trading position"""
    token_id: str
    market_id: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    current_price: float
    size: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    order_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def pnl(self) -> float:
        """Calculate current profit/loss"""
        if self.side == 'BUY':
            return (self.current_price - self.entry_price) * self.size
        else:  # SELL
            return (self.entry_price - self.current_price) * self.size
    
    @property
    def pnl_percentage(self) -> float:
        """Calculate P&L as percentage"""
        if self.entry_price == 0:
            return 0.0
        return (self.pnl / (self.entry_price * self.size)) * 100
    
    @property
    def is_profitable(self) -> bool:
        """Check if position is currently profitable"""
        return self.pnl > 0
    
    def update_price(self, new_price: float):
        """Update current price"""
        self.current_price = new_price
    
    def __str__(self) -> str:
        return (
            f"Position({self.side} {self.size} @ {self.entry_price:.4f}, "
            f"current={self.current_price:.4f}, PnL={self.pnl:.2f})"
        )


class PositionManager:
    """Manages trading positions and risk"""
    
    def __init__(
        self,
        max_position_size: float,
        max_total_exposure: float,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.15
    ):
        """
        Initialize position manager
        
        Args:
            max_position_size: Maximum size for a single position
            max_total_exposure: Maximum total exposure across all positions
            stop_loss_pct: Default stop-loss percentage (0.05 = 5%)
            take_profit_pct: Default take-profit percentage (0.15 = 15%)
        """
        self.max_position_size = max_position_size
        self.max_total_exposure = max_total_exposure
        self.default_stop_loss_pct = stop_loss_pct
        self.default_take_profit_pct = take_profit_pct
        
        self.positions: Dict[str, Position] = {}  # token_id -> Position
        self.logger = logging.getLogger(__name__)
    
    def add_position(self, position: Position) -> bool:
        """
        Add a new position
        
        Args:
            position: Position to add
        
        Returns:
            True if position added successfully, False otherwise
        """
        if position.token_id in self.positions:
            self.logger.warning(f"Position for {position.token_id} already exists")
            return False
        
        self.positions[position.token_id] = position
        self.logger.info(f"Position added: {position}")
        return True
    
    def remove_position(self, token_id: str) -> bool:
        """
        Remove a position
        
        Args:
            token_id: Token ID of position to remove
        
        Returns:
            True if removed, False if not found
        """
        if token_id in self.positions:
            position = self.positions.pop(token_id)
            self.logger.info(f"Position removed: {position}")
            return True
        return False
    
    def get_position(self, token_id: str) -> Optional[Position]:
        """Get position by token ID"""
        return self.positions.get(token_id)
    
    def get_all_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self.positions.values())
    
    def update_position_price(self, token_id: str, new_price: float):
        """Update the current price of a position"""
        if token_id in self.positions:
            self.positions[token_id].update_price(new_price)
    
    def can_open_position(self, size: float) -> bool:
        """
        Check if a new position can be opened
        
        Args:
            size: Size of the proposed position
        
        Returns:
            True if position can be opened, False otherwise
        """
        # Check single position limit
        if size > self.max_position_size:
            self.logger.warning(
                f"Position size {size} exceeds max {self.max_position_size}"
            )
            return False
        
        # Check total exposure
        current_exposure = sum(p.size for p in self.positions.values())
        if current_exposure + size > self.max_total_exposure:
            self.logger.warning(
                f"Total exposure would exceed limit: "
                f"{current_exposure + size} > {self.max_total_exposure}"
            )
            return False
        
        return True
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        side: str,
        custom_pct: Optional[float] = None
    ) -> float:
        """
        Calculate stop-loss price
        
        Args:
            entry_price: Entry price of the position
            side: 'BUY' or 'SELL'
            custom_pct: Custom stop-loss percentage (overrides default)
        
        Returns:
            Stop-loss price
        """
        pct = custom_pct if custom_pct is not None else self.default_stop_loss_pct
        
        if side == 'BUY':
            return entry_price * (1 - pct)
        else:  # SELL
            return entry_price * (1 + pct)
    
    def calculate_take_profit(
        self,
        entry_price: float,
        side: str,
        custom_pct: Optional[float] = None
    ) -> float:
        """
        Calculate take-profit price
        
        Args:
            entry_price: Entry price of the position
            side: 'BUY' or 'SELL'
            custom_pct: Custom take-profit percentage (overrides default)
        
        Returns:
            Take-profit price
        """
        pct = custom_pct if custom_pct is not None else self.default_take_profit_pct
        
        if side == 'BUY':
            return entry_price * (1 + pct)
        else:  # SELL
            return entry_price * (1 - pct)
    
    def should_close_position(self, position: Position) -> tuple[bool, str]:
        """
        Determine if a position should be closed
        
        Args:
            position: Position to evaluate
        
        Returns:
            Tuple of (should_close: bool, reason: str)
        """
        if position.side == 'BUY':
            # Check stop-loss
            if position.current_price <= position.stop_loss:
                return True, "Stop-loss triggered"
            
            # Check take-profit
            if position.current_price >= position.take_profit:
                return True, "Take-profit triggered"
        
        else:  # SELL
            # Check stop-loss
            if position.current_price >= position.stop_loss:
                return True, "Stop-loss triggered"
            
            # Check take-profit
            if position.current_price <= position.take_profit:
                return True, "Take-profit triggered"
        
        return False, ""
    
    def get_total_exposure(self) -> float:
        """Get total exposure across all positions"""
        return sum(p.size for p in self.positions.values())
    
    def get_total_pnl(self) -> float:
        """Get total P&L across all positions"""
        return sum(p.pnl for p in self.positions.values())
    
    def get_positions_to_close(self) -> List[tuple[Position, str]]:
        """
        Get positions that should be closed
        
        Returns:
            List of (position, reason) tuples
        """
        to_close = []
        for position in self.positions.values():
            should_close, reason = self.should_close_position(position)
            if should_close:
                to_close.append((position, reason))
        return to_close
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        Get current risk metrics
        
        Returns:
            Dictionary with risk metrics
        """
        positions = self.get_all_positions()
        
        return {
            'total_positions': len(positions),
            'total_exposure': self.get_total_exposure(),
            'max_exposure': self.max_total_exposure,
            'exposure_utilization': self.get_total_exposure() / self.max_total_exposure,
            'total_pnl': self.get_total_pnl(),
            'profitable_positions': sum(1 for p in positions if p.is_profitable),
            'losing_positions': sum(1 for p in positions if not p.is_profitable),
            'positions': [
                {
                    'token_id': p.token_id,
                    'side': p.side,
                    'size': p.size,
                    'pnl': p.pnl,
                    'pnl_pct': p.pnl_percentage
                }
                for p in positions
            ]
        }
