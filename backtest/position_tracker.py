"""Position tracking during backtest"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

# Import Position from existing risk module
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.position_manager import Position


@dataclass
class BacktestPosition:
    """Position with backtest-specific tracking"""
    position: Position
    entry_timestamp: datetime
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    exit_reason: Optional[str] = None


@dataclass
class TradeRecord:
    """Record of a trade action"""
    timestamp: datetime
    action: str                    # "OPEN" or "CLOSE"
    token_id: str
    side: str
    price: float
    size: float
    pnl: Optional[float] = None
    reason: Optional[str] = None
    capital_after: float = 0.0


class PositionTracker:
    """
    Track positions during backtest

    Differences from live PositionManager:
    - No API communication
    - Tracks complete history of all positions
    - Allows post-backtest analysis
    - Manages virtual capital
    """

    def __init__(self, initial_capital: float):
        """
        Initialize position tracker

        Args:
            initial_capital: Starting capital
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.open_positions: Dict[str, BacktestPosition] = {}
        self.closed_positions: List[BacktestPosition] = []
        self.trade_history: List[TradeRecord] = []
        self.logger = logging.getLogger(__name__)

    def open_position(
        self,
        token_id: str,
        market_id: str,
        side: str,
        entry_price: float,
        size: float,
        timestamp: datetime,
        stop_loss: float,
        take_profit: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Open a new position

        Args:
            token_id: Token identifier
            market_id: Market identifier
            side: "BUY" or "SELL"
            entry_price: Entry price
            size: Position size in USD
            timestamp: Entry timestamp
            stop_loss: Stop loss price
            take_profit: Take profit price
            metadata: Additional metadata

        Returns:
            True if position opened successfully
        """
        # Check if position already exists
        if token_id in self.open_positions:
            self.logger.warning(f"Position already exists for {token_id}")
            return False

        # Check if we have enough capital
        cost = entry_price * size
        if cost > self.current_capital:
            self.logger.warning(f"Insufficient capital: need {cost}, have {self.current_capital}")
            return False

        # Create Position object (from existing module)
        position = Position(
            token_id=token_id,
            market_id=market_id,
            side=side,
            entry_price=entry_price,
            current_price=entry_price,
            size=size,
            entry_time=timestamp,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata or {}
        )

        # Wrap in BacktestPosition
        bt_position = BacktestPosition(
            position=position,
            entry_timestamp=timestamp
        )

        self.open_positions[token_id] = bt_position

        # Deduct cost from capital
        self.current_capital -= cost

        # Record trade
        self.trade_history.append(TradeRecord(
            timestamp=timestamp,
            action="OPEN",
            token_id=token_id,
            side=side,
            price=entry_price,
            size=size,
            capital_after=self.current_capital
        ))

        self.logger.debug(f"Opened position: {side} {size} @ {entry_price}")
        return True

    def close_position(
        self,
        token_id: str,
        exit_price: float,
        timestamp: datetime,
        reason: str = "manual"
    ) -> Optional[float]:
        """
        Close a position

        Args:
            token_id: Token identifier
            exit_price: Exit price
            timestamp: Exit timestamp
            reason: Reason for closing

        Returns:
            Realized P&L or None if position doesn't exist
        """
        if token_id not in self.open_positions:
            self.logger.warning(f"No position found for {token_id}")
            return None

        bt_position = self.open_positions.pop(token_id)
        position = bt_position.position

        # Calculate P&L
        if position.side == "BUY":
            pnl = (exit_price - position.entry_price) * position.size
        else:
            pnl = (position.entry_price - exit_price) * position.size

        # Update position record
        bt_position.exit_timestamp = timestamp
        bt_position.exit_price = exit_price
        bt_position.realized_pnl = pnl
        bt_position.exit_reason = reason

        # Add to closed positions
        self.closed_positions.append(bt_position)

        # Update capital (return the position value + P&L)
        proceeds = exit_price * position.size
        self.current_capital += proceeds

        # Record trade
        self.trade_history.append(TradeRecord(
            timestamp=timestamp,
            action="CLOSE",
            token_id=token_id,
            side="SELL" if position.side == "BUY" else "BUY",
            price=exit_price,
            size=position.size,
            pnl=pnl,
            reason=reason,
            capital_after=self.current_capital
        ))

        self.logger.debug(f"Closed position: {reason}, P&L={pnl:.2f}")
        return pnl

    def update_position_price(self, token_id: str, new_price: float):
        """Update current price for an open position"""
        if token_id in self.open_positions:
            self.open_positions[token_id].position.update_price(new_price)

    def check_stop_loss_take_profit(
        self,
        token_id: str,
        current_price: float,
        timestamp: datetime
    ) -> Optional[str]:
        """
        Check if position should be closed due to SL/TP

        Args:
            token_id: Token identifier
            current_price: Current price
            timestamp: Current timestamp

        Returns:
            Close reason or None
        """
        if token_id not in self.open_positions:
            return None

        position = self.open_positions[token_id].position

        if position.side == "BUY":
            if current_price <= position.stop_loss:
                self.close_position(token_id, current_price, timestamp, "stop_loss")
                return "stop_loss"
            if current_price >= position.take_profit:
                self.close_position(token_id, current_price, timestamp, "take_profit")
                return "take_profit"
        else:  # SELL
            if current_price >= position.stop_loss:
                self.close_position(token_id, current_price, timestamp, "stop_loss")
                return "stop_loss"
            if current_price <= position.take_profit:
                self.close_position(token_id, current_price, timestamp, "take_profit")
                return "take_profit"

        return None

    def get_equity(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate total equity (capital + unrealized P&L)

        Args:
            current_prices: Dict of token_id -> current_price

        Returns:
            Total equity value
        """
        equity = self.current_capital

        for token_id, bt_position in self.open_positions.items():
            position = bt_position.position

            # Use provided price or last known price
            if current_prices and token_id in current_prices:
                price = current_prices[token_id]
            else:
                price = position.current_price

            # Add position value
            equity += price * position.size

        return equity

    def get_unrealized_pnl(self, current_prices: Optional[Dict[str, float]] = None) -> float:
        """Calculate total unrealized P&L"""
        total_pnl = 0.0

        for token_id, bt_position in self.open_positions.items():
            position = bt_position.position

            if current_prices and token_id in current_prices:
                position.update_price(current_prices[token_id])

            total_pnl += position.pnl

        return total_pnl

    def get_realized_pnl(self) -> float:
        """Calculate total realized P&L from closed positions"""
        return sum(p.realized_pnl or 0 for p in self.closed_positions)

    def get_total_trades(self) -> int:
        """Get total number of completed trades"""
        return len(self.closed_positions)

    def get_open_position_count(self) -> int:
        """Get number of open positions"""
        return len(self.open_positions)

    def has_open_position(self, token_id: str) -> bool:
        """Check if token has an open position"""
        return token_id in self.open_positions

    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of all positions"""
        return {
            'initial_capital': self.initial_capital,
            'current_capital': self.current_capital,
            'open_positions': self.get_open_position_count(),
            'closed_positions': len(self.closed_positions),
            'realized_pnl': self.get_realized_pnl(),
            'total_trades': len([t for t in self.trade_history if t.action == "CLOSE"]),
        }
