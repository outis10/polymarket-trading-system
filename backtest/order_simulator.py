"""Order execution simulator"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class OrderStatus(Enum):
    """Order status"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class SimulatedOrder:
    """Simulated order"""
    order_id: str
    token_id: str
    side: str                        # "BUY" or "SELL"
    order_type: str                  # "LIMIT" or "MARKET"
    requested_price: float
    requested_size: float
    filled_price: Optional[float] = None
    filled_size: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    slippage: float = 0.0
    fees: float = 0.0


@dataclass
class FillResult:
    """Result of an order fill"""
    order: SimulatedOrder
    fill_price: float
    fill_size: float
    total_cost: float               # Including fees
    slippage_cost: float
    success: bool
    message: str = ""


class OrderSimulator:
    """
    Simulates order execution with realistic market impact

    Considers:
    - Slippage based on order size vs available liquidity
    - Fees (Polymarket currently has 0% fees, but configurable)
    - Partial fills when liquidity is insufficient
    - Price impact from large orders
    """

    def __init__(
        self,
        slippage_pct: float = 0.005,
        maker_fee: float = 0.0,
        taker_fee: float = 0.0,
        available_liquidity: float = 10000.0
    ):
        """
        Initialize order simulator

        Args:
            slippage_pct: Base slippage percentage (0.005 = 0.5%)
            maker_fee: Maker fee percentage
            taker_fee: Taker fee percentage
            available_liquidity: Simulated available liquidity in USD
        """
        self.slippage_pct = slippage_pct
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.available_liquidity = available_liquidity
        self._order_counter = 0

    def execute_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        order_type: str,
        timestamp: datetime
    ) -> FillResult:
        """
        Simulate order execution

        Args:
            token_id: Token to trade
            side: "BUY" or "SELL"
            price: Requested price
            size: Requested size in USD
            order_type: "LIMIT" or "MARKET"
            timestamp: Execution timestamp

        Returns:
            FillResult with execution details
        """
        self._order_counter += 1
        order_id = f"sim_order_{self._order_counter}"

        # Validate inputs
        if side not in ["BUY", "SELL"]:
            return self._create_rejected_result(
                order_id, token_id, side, order_type, price, size, timestamp,
                "Invalid side"
            )

        if price <= 0 or price > 1:
            return self._create_rejected_result(
                order_id, token_id, side, order_type, price, size, timestamp,
                "Invalid price (must be 0-1)"
            )

        if size <= 0:
            return self._create_rejected_result(
                order_id, token_id, side, order_type, price, size, timestamp,
                "Invalid size"
            )

        # Calculate slippage based on order size vs liquidity
        # Larger orders relative to liquidity = more slippage
        size_ratio = size / self.available_liquidity
        impact = size_ratio * self.slippage_pct

        # Apply slippage
        if side == "BUY":
            fill_price = price * (1 + impact)  # Pay more when buying
        else:
            fill_price = price * (1 - impact)  # Receive less when selling

        # Ensure price stays in valid range
        fill_price = max(0.01, min(0.99, fill_price))

        # Calculate fill size (may be partial if insufficient liquidity)
        max_fill = min(size, self.available_liquidity * 0.1)  # Max 10% of liquidity per order
        fill_size = min(size, max_fill)

        # Determine fee rate
        fee_rate = self.taker_fee if order_type == "MARKET" else self.maker_fee
        fees = fill_price * fill_size * fee_rate

        # Calculate total cost
        if side == "BUY":
            total_cost = fill_price * fill_size + fees
        else:
            total_cost = -(fill_price * fill_size - fees)  # Negative = we receive money

        slippage_cost = abs(fill_price - price) * fill_size

        # Determine order status
        if fill_size == size:
            status = OrderStatus.FILLED
        elif fill_size > 0:
            status = OrderStatus.PARTIALLY_FILLED
        else:
            status = OrderStatus.REJECTED

        # Create order record
        order = SimulatedOrder(
            order_id=order_id,
            token_id=token_id,
            side=side,
            order_type=order_type,
            requested_price=price,
            requested_size=size,
            filled_price=fill_price,
            filled_size=fill_size,
            status=status,
            created_at=timestamp,
            filled_at=timestamp,
            slippage=impact,
            fees=fees
        )

        return FillResult(
            order=order,
            fill_price=fill_price,
            fill_size=fill_size,
            total_cost=total_cost,
            slippage_cost=slippage_cost,
            success=status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED],
            message=f"Order {status.value}"
        )

    def _create_rejected_result(
        self,
        order_id: str,
        token_id: str,
        side: str,
        order_type: str,
        price: float,
        size: float,
        timestamp: datetime,
        reason: str
    ) -> FillResult:
        """Create a rejected order result"""
        order = SimulatedOrder(
            order_id=order_id,
            token_id=token_id,
            side=side,
            order_type=order_type,
            requested_price=price,
            requested_size=size,
            filled_price=None,
            filled_size=0,
            status=OrderStatus.REJECTED,
            created_at=timestamp,
            filled_at=None,
            slippage=0,
            fees=0
        )

        return FillResult(
            order=order,
            fill_price=0,
            fill_size=0,
            total_cost=0,
            slippage_cost=0,
            success=False,
            message=reason
        )

    def estimate_fill_price(
        self,
        side: str,
        price: float,
        size: float
    ) -> float:
        """
        Estimate fill price without executing

        Args:
            side: "BUY" or "SELL"
            price: Requested price
            size: Order size

        Returns:
            Estimated fill price
        """
        size_ratio = size / self.available_liquidity
        impact = size_ratio * self.slippage_pct

        if side == "BUY":
            return min(0.99, price * (1 + impact))
        else:
            return max(0.01, price * (1 - impact))
