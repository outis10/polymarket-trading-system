"""REST endpoints for trading operations."""

import logging

from fastapi import APIRouter, HTTPException

from ..models.schemas import OrderRequest, OrderResponse
from ..services.event_manager import event_manager
from ..services.polymarket import get_client, reset_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["trading"])


@router.post("/orders", response_model=OrderResponse)
async def place_order(order: OrderRequest):
    """Place a trade order."""
    event = event_manager.events.get(order.event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{order.event_id}' not found")

    # Demo mode: simulate
    if event_manager.mode == "demo":
        outcome_label = "Up" if order.outcome == "up" else "Down"
        order_label = order.order_type.capitalize()
        if order.order_type == "market":
            msg = f"{order.side} {order.shares} shares of {outcome_label} ({order_label} order)"
        else:
            msg = f"{order.side} {order.shares} shares of {outcome_label} @ ${order.price:.2f} ({order_label} order)"
        return OrderResponse(order_id="demo-" + order.event_id[:8], status="FILLED", message=msg)

    # Live mode: execute via Polymarket
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    token_id = event.get("yes_token_id") if order.outcome == "up" else event.get("no_token_id")
    if not token_id:
        raise HTTPException(status_code=400, detail="Token ID not found for this outcome")

    try:
        side = order.side.upper()
        if order.order_type == "market":
            result = client.place_market_order(token_id, side, order.shares)
        else:
            result = client.place_order(token_id, side, order.price, order.shares)

        if result:
            # SignedOrder object - access attributes directly
            order_id = getattr(result, 'id', None) or getattr(result, 'orderID', None) or str(result)[:16]
            status = getattr(result, 'status', 'OPEN')
            return OrderResponse(
                order_id=str(order_id),
                status=str(status) if status else "OPEN",
                message="Order placed successfully",
            )
        raise HTTPException(status_code=500, detail="Order placement returned no result")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error placing order: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def get_open_orders():
    """Get all open orders."""
    if event_manager.mode == "demo":
        return {"orders": [], "message": "Demo mode - no real orders"}

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    try:
        orders = client.get_open_orders()
        return {"orders": orders}
    except Exception as e:
        logger.error("Error getting orders: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def get_trades():
    """Get trade history."""
    if event_manager.mode == "demo":
        return {"trades": [], "message": "Demo mode - no real trades"}

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    try:
        trades = client.get_trades()
        return {"trades": trades}
    except Exception as e:
        logger.error("Error getting trades: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance")
async def get_balance():
    """Get account balance."""
    if event_manager.mode == "demo":
        return {"balance": 1000.00, "message": "Demo mode - simulated balance"}

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    try:
        balance = client.get_balance()
        if balance is None:
            return {
                "balance": None,
                "message": "Balance not available - L2 API credentials may be required. Check your .env file for POLYMARKET_API_KEY, POLYMARKET_SECRET, and POLYMARKET_PASSPHRASE"
            }
        return {"balance": balance}
    except Exception as e:
        logger.error("Error getting balance: %s", e)
        return {
            "balance": None,
            "error": str(e),
            "message": "Balance check failed - this usually means L2 API credentials are not configured"
        }


@router.get("/debug/client")
async def debug_client():
    """Debug: show available client methods."""
    client = get_client()
    if not client:
        return {"error": "No client"}

    methods = [m for m in dir(client.client) if not m.startswith('_')]
    return {
        "client_methods": methods,
        "has_create_and_post": hasattr(client.client, 'create_and_post_order'),
    }


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an existing order."""
    if event_manager.mode == "demo":
        return {"status": "cancelled", "order_id": order_id}

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    success = client.cancel_order(order_id)
    if success:
        return {"status": "cancelled", "order_id": order_id}
    raise HTTPException(status_code=500, detail="Failed to cancel order")


@router.post("/reset-client")
async def reset_polymarket_client():
    """Reset the Polymarket client to reload credentials from .env."""
    reset_client()
    # Try to reinitialize
    client = get_client()
    if client:
        return {"status": "success", "message": "Client reinitialized successfully"}
    return {"status": "warning", "message": "Client reset but failed to reinitialize"}


@router.get("/positions/{event_id}")
async def get_positions(event_id: str):
    """Get positions for a specific event, calculated from trades."""
    event = event_manager.events.get(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    if event_manager.mode == "demo":
        # Demo positions
        return {
            "positions": [
                {
                    "outcome": "Up",
                    "qty": 10,
                    "avg_price": 0.45,
                    "current_price": event.get("yes_price", 0.5),
                    "cost": 4.50,
                    "value": 10 * event.get("yes_price", 0.5),
                    "return_value": 10 * event.get("yes_price", 0.5) - 4.50,
                    "return_pct": ((10 * event.get("yes_price", 0.5) - 4.50) / 4.50) * 100 if event.get("yes_price") else 0,
                },
            ],
            "message": "Demo mode - simulated positions"
        }

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    try:
        yes_token = event.get("yes_token_id")
        no_token = event.get("no_token_id")

        if not yes_token or not no_token:
            return {"positions": [], "message": "Token IDs not configured for this event"}

        # Get all trades
        trades = client.get_trades()

        # Calculate positions per token
        positions = []

        for outcome, token_id in [("Up", yes_token), ("Down", no_token)]:
            # Filter trades for this token
            token_trades = [t for t in trades if t.get("asset_id") == token_id]

            if not token_trades:
                continue

            # Calculate net position
            total_qty = 0
            total_cost = 0

            for trade in token_trades:
                side = trade.get("side", "").upper()
                size = float(trade.get("size", 0))
                price = float(trade.get("price", 0))

                if side == "BUY":
                    total_qty += size
                    total_cost += size * price
                elif side == "SELL":
                    total_qty -= size
                    total_cost -= size * price

            if total_qty > 0:
                avg_price = total_cost / total_qty if total_qty > 0 else 0
                current_price = event.get("yes_price", 0.5) if outcome == "Up" else event.get("no_price", 0.5)
                value = total_qty * current_price
                return_value = value - total_cost
                return_pct = (return_value / total_cost * 100) if total_cost > 0 else 0

                positions.append({
                    "outcome": outcome,
                    "qty": round(total_qty, 2),
                    "avg_price": round(avg_price, 4),
                    "current_price": round(current_price, 4),
                    "cost": round(total_cost, 2),
                    "value": round(value, 2),
                    "return_value": round(return_value, 2),
                    "return_pct": round(return_pct, 2),
                })

        return {"positions": positions}

    except Exception as e:
        logger.error("Error getting positions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
