"""Order execution and management"""
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from core.client_wrapper import PolymarketClient
from strategy.base_strategy import Signal, SignalAction
from risk.position_manager import PositionManager, Position


class OrderExecutor:
    """Executes trading signals with risk management"""
    
    def __init__(
        self,
        client: PolymarketClient,
        position_manager: PositionManager
    ):
        """
        Initialize order executor
        
        Args:
            client: Polymarket client instance
            position_manager: Position manager instance
        """
        self.client = client
        self.position_manager = position_manager
        self.logger = logging.getLogger(__name__)
    
    def execute_signal(
        self,
        signal: Signal,
        market_id: str
    ) -> tuple[bool, Optional[str]]:
        """
        Execute a trading signal
        
        Args:
            signal: Signal to execute
            market_id: Market ID for the trade
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        # Check if action is to close
        if signal.action == SignalAction.CLOSE:
            return self._close_position(signal.token_id)
        
        # Check if action is hold
        if signal.action == SignalAction.HOLD:
            return True, "Signal is HOLD, no action taken"
        
        # Validate we can open the position
        if not self.position_manager.can_open_position(signal.size):
            msg = "Cannot open position: risk limits exceeded"
            self.logger.warning(msg)
            return False, msg
        
        # Calculate stop-loss and take-profit
        stop_loss = self.position_manager.calculate_stop_loss(
            signal.price,
            signal.action.value
        )
        take_profit = self.position_manager.calculate_take_profit(
            signal.price,
            signal.action.value
        )
        
        # Execute the order
        order_result = self.client.place_order(
            token_id=signal.token_id,
            side=signal.action.value,
            price=signal.price,
            size=signal.size,
            order_type='LIMIT'
        )
        
        if not order_result:
            msg = "Failed to place order with Polymarket"
            self.logger.error(msg)
            return False, msg
        
        # Create position object
        position = Position(
            token_id=signal.token_id,
            market_id=market_id,
            side=signal.action.value,
            entry_price=signal.price,
            current_price=signal.price,
            size=signal.size,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_id=order_result.get('id'),
            metadata={
                'signal_confidence': signal.confidence,
                'signal_reason': signal.reason,
                'signal_metadata': signal.metadata
            }
        )
        
        # Add to position manager
        if self.position_manager.add_position(position):
            msg = (
                f"Position opened: {signal.action.value} {signal.size} @ {signal.price:.4f} "
                f"(SL: {stop_loss:.4f}, TP: {take_profit:.4f})"
            )
            self.logger.info(msg)
            return True, msg
        else:
            # If we can't add position, cancel the order
            if order_result.get('id'):
                self.client.cancel_order(order_result['id'])
            msg = "Failed to add position to position manager"
            self.logger.error(msg)
            return False, msg
    
    def _close_position(self, token_id: str) -> tuple[bool, Optional[str]]:
        """
        Close an existing position
        
        Args:
            token_id: Token ID of position to close
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        position = self.position_manager.get_position(token_id)
        if not position:
            msg = f"No position found for token {token_id}"
            self.logger.warning(msg)
            return False, msg
        
        # Determine opposite side for closing
        close_side = 'SELL' if position.side == 'BUY' else 'BUY'
        
        # Place closing order at market price
        current_price = self.client.get_market_price(token_id, close_side.lower())
        if not current_price:
            msg = "Could not get current market price for closing"
            self.logger.error(msg)
            return False, msg
        
        order_result = self.client.place_order(
            token_id=token_id,
            side=close_side,
            price=current_price,
            size=position.size,
            order_type='LIMIT'
        )
        
        if not order_result:
            msg = "Failed to place closing order"
            self.logger.error(msg)
            return False, msg
        
        # Remove position
        self.position_manager.remove_position(token_id)
        
        final_pnl = position.pnl
        msg = f"Position closed: PnL = {final_pnl:.2f} ({position.pnl_percentage:.2f}%)"
        self.logger.info(msg)
        return True, msg
    
    def check_and_close_positions(self) -> Dict[str, Any]:
        """
        Check all positions and close those that hit stop-loss or take-profit
        
        Returns:
            Dictionary with results of closed positions
        """
        positions_to_close = self.position_manager.get_positions_to_close()
        
        results = {
            'checked': len(self.position_manager.get_all_positions()),
            'closed': 0,
            'failed': 0,
            'details': []
        }
        
        for position, reason in positions_to_close:
            self.logger.info(f"Closing position for {position.token_id}: {reason}")
            
            success, message = self._close_position(position.token_id)
            
            result_detail = {
                'token_id': position.token_id,
                'reason': reason,
                'success': success,
                'message': message,
                'pnl': position.pnl if success else None
            }
            results['details'].append(result_detail)
            
            if success:
                results['closed'] += 1
            else:
                results['failed'] += 1
        
        if results['closed'] > 0:
            self.logger.info(
                f"Closed {results['closed']} positions, "
                f"{results['failed']} failed"
            )
        
        return results
    
    def update_all_position_prices(self):
        """Update current prices for all open positions"""
        for position in self.position_manager.get_all_positions():
            current_price = self.client.get_mid_price(position.token_id)
            if current_price:
                self.position_manager.update_position_price(
                    position.token_id,
                    current_price
                )
    
    def emergency_close_all(self) -> Dict[str, Any]:
        """
        Emergency close all positions (market orders)
        
        Returns:
            Dictionary with results
        """
        self.logger.warning("Emergency close initiated for all positions")
        
        positions = self.position_manager.get_all_positions()
        results = {
            'total': len(positions),
            'closed': 0,
            'failed': 0,
            'details': []
        }
        
        for position in positions:
            success, message = self._close_position(position.token_id)
            results['details'].append({
                'token_id': position.token_id,
                'success': success,
                'message': message
            })
            
            if success:
                results['closed'] += 1
            else:
                results['failed'] += 1
        
        self.logger.warning(
            f"Emergency close completed: {results['closed']}/{results['total']} successful"
        )
        return results
