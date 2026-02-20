"""REST endpoints for trading operations."""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..models.schemas import OrderRequest, OrderResponse
from ..services.event_manager import event_manager
from ..services.polymarket import get_client, reset_client
from ..ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["trading"])
_POSITIONS_CACHE_TTL_SECONDS = 10.0
_positions_cache: dict[str, dict] = {}


@router.post("/orders", response_model=OrderResponse)
async def place_order(order: OrderRequest):
    """Place a trade order."""
    event = event_manager.events.get(order.event_id)
    if not event:
        raise HTTPException(
            status_code=404, detail=f"Event '{order.event_id}' not found"
        )
    if not event_manager.is_event_trading_enabled(order.event_id, event):
        raise HTTPException(
            status_code=403,
            detail="Trading disabled for this event ticker by monitored_tickers setting",
        )
    outcome_side = "up" if order.outcome == "up" else "down"
    reference_price = (
        float(event.get("yes_price") or 0.5)
        if outcome_side == "up"
        else float(event.get("no_price") or 0.5)
    )
    order_price_ref = (
        float(order.price) if order.order_type == "limit" else float(reference_price)
    )
    requested_shares = max(0.0, float(order.shares))
    requested_notional_usd = order_price_ref * requested_shares
    hard_cap_usd = max(
        0.0, float(event_manager.settings.get("bot_order_notional_cap_usd", 5.0))
    )
    effective_shares = requested_shares
    cap_applied = False
    if (
        hard_cap_usd > 0
        and requested_notional_usd > hard_cap_usd
        and order_price_ref > 0
    ):
        effective_shares = hard_cap_usd / order_price_ref
        cap_applied = True
    notional_usd = order_price_ref * effective_shares
    bankroll_usd: float | None = None

    # Demo mode: simulate
    if event_manager.mode == "demo":
        allowed, reason = event_manager.validate_order_risk_guards(
            event_id=order.event_id,
            event=event,
            outcome=outcome_side,
            shares=float(effective_shares),
            notional_usd=notional_usd,
            now_utc=datetime.now(tz=timezone.utc),
            bankroll_usd=bankroll_usd,
        )
        if not allowed:
            detailed = event_manager.format_risk_guard_block_reason(
                reason=reason,
                event_id=order.event_id,
                event=event,
                notional_usd=notional_usd,
                now_utc=datetime.now(tz=timezone.utc),
                bankroll_usd=bankroll_usd,
            )
            raise HTTPException(
                status_code=403, detail=f"Risk guard blocked: {detailed}"
            )
        event_manager.register_order_fill(
            event_id=order.event_id,
            event=event,
            outcome=outcome_side,
            notional_usd=notional_usd,
            now_utc=datetime.now(tz=timezone.utc),
        )
        outcome_label = "Up" if order.outcome == "up" else "Down"
        order_label = order.order_type.capitalize()
        if order.order_type == "market":
            msg = (
                f"{order.side} {effective_shares:.4f} shares of "
                f"{outcome_label} ({order_label} order)"
            )
        else:
            msg = (
                f"{order.side} {effective_shares:.4f} shares of {outcome_label} "
                f"@ ${order.price:.2f} ({order_label} order)"
            )
        if cap_applied:
            msg += f" [notional capped to ${hard_cap_usd:.2f}]"
        try:
            await manager.broadcast(
                {
                    "type": "balance_update",
                    "event_id": "",
                    "data": {"balance": 1000.00, "source": "demo"},
                }
            )
        except Exception:
            pass
        return OrderResponse(
            order_id="demo-" + order.event_id[:8], status="FILLED", message=msg
        )

    # Live mode: execute via Polymarket
    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")
    try:
        balance = client.get_balance()
        if isinstance(balance, (int, float)) and float(balance) > 0:
            bankroll_usd = float(balance)
    except Exception:
        bankroll_usd = None

    allowed, reason = event_manager.validate_order_risk_guards(
        event_id=order.event_id,
        event=event,
        outcome=outcome_side,
        shares=float(effective_shares),
        notional_usd=notional_usd,
        now_utc=datetime.now(tz=timezone.utc),
        bankroll_usd=bankroll_usd,
    )
    if not allowed:
        detailed = event_manager.format_risk_guard_block_reason(
            reason=reason,
            event_id=order.event_id,
            event=event,
            notional_usd=notional_usd,
            now_utc=datetime.now(tz=timezone.utc),
            bankroll_usd=bankroll_usd,
        )
        raise HTTPException(status_code=403, detail=f"Risk guard blocked: {detailed}")

    token_id = (
        event.get("yes_token_id") if order.outcome == "up" else event.get("no_token_id")
    )
    if not token_id:
        raise HTTPException(
            status_code=400, detail="Token ID not found for this outcome"
        )

    try:
        side = order.side.upper()
        if order.order_type == "market":
            result = client.place_market_order(token_id, side, effective_shares)
        else:
            result = client.place_order(token_id, side, order.price, effective_shares)

        if result:
            # SignedOrder object - access attributes directly
            order_id = (
                getattr(result, "id", None)
                or getattr(result, "orderID", None)
                or str(result)[:16]
            )
            status = getattr(result, "status", "OPEN")
            event_manager.register_order_fill(
                event_id=order.event_id,
                event=event,
                outcome=outcome_side,
                notional_usd=notional_usd,
                now_utc=datetime.now(tz=timezone.utc),
            )
            try:
                refreshed_balance = client.get_balance()
            except Exception:
                refreshed_balance = None
            try:
                await manager.broadcast(
                    {
                        "type": "balance_update",
                        "event_id": "",
                        "data": {
                            "balance": float(refreshed_balance)
                            if isinstance(refreshed_balance, (int, float))
                            else None,
                            "source": "post_order_fill",
                        },
                    }
                )
            except Exception:
                pass
            return OrderResponse(
                order_id=str(order_id),
                status=str(status) if status else "OPEN",
                message=(
                    f"Order placed successfully"
                    + (
                        f" (notional capped to ${hard_cap_usd:.2f})"
                        if cap_applied
                        else ""
                    )
                ),
            )
        raise HTTPException(
            status_code=500, detail="Order placement returned no result"
        )

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
                "message": "Balance not available - L2 API credentials may be required. Check your .env file for POLYMARKET_API_KEY, POLYMARKET_SECRET, and POLYMARKET_PASSPHRASE",
            }
        return {"balance": balance}
    except Exception as e:
        logger.error("Error getting balance: %s", e)
        return {
            "balance": None,
            "error": str(e),
            "message": "Balance check failed - this usually means L2 API credentials are not configured",
        }


@router.get("/debug/client")
async def debug_client():
    """Debug: show available client methods."""
    client = get_client()
    if not client:
        return {"error": "No client"}

    methods = [m for m in dir(client.client) if not m.startswith("_")]
    return {
        "client_methods": methods,
        "has_create_and_post": hasattr(client.client, "create_and_post_order"),
    }


@router.get("/diagnostics/auth")
async def diagnostics_auth():
    """
    Diagnose Polymarket auth/config state without exposing secret values.
    """
    required_env = [
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_FUNDER",
        "POLYMARKET_SIGNATURE_TYPE",
        "CHAIN_ID",
        "USE_TESTNET",
    ]
    l2_env = [
        "POLYMARKET_API_KEY",
        "POLYMARKET_SECRET",
        "POLYMARKET_PASSPHRASE",
    ]

    env_presence = {k: bool(os.getenv(k)) for k in required_env + l2_env}

    diagnostics = {
        "mode": event_manager.mode,
        "environment": env_presence,
        "checks": {
            "l1_minimum_present": all(
                env_presence.get(k, False)
                for k in ("POLYMARKET_PRIVATE_KEY", "POLYMARKET_FUNDER")
            ),
            "l2_triplet_present": all(env_presence.get(k, False) for k in l2_env),
        },
    }

    # Load typed settings to confirm parsed runtime config.
    try:
        from config.settings import Settings

        settings_obj = Settings()
        diagnostics["runtime"] = {
            "use_testnet": settings_obj.polymarket.use_testnet,
            "chain_id": settings_obj.polymarket.chain_id,
            "signature_type": settings_obj.polymarket.signature_type,
            "host": settings_obj.polymarket.host,
        }
    except Exception as e:
        diagnostics["runtime_error"] = str(e)

    # Validate current singleton client state.
    client = get_client()
    diagnostics["client_initialized"] = bool(client)
    if client:
        diagnostics["client_checks"] = {
            "has_clob_client": hasattr(client, "client"),
            "has_balance_allowance_method": hasattr(
                client.client, "get_balance_allowance"
            ),
        }
    else:
        diagnostics["client_hint"] = (
            "Client failed to initialize. Verify L1 vars and chain/network settings. "
            "If credentials changed, call POST /api/reset-client."
        )

    return diagnostics


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
                    "return_pct": ((10 * event.get("yes_price", 0.5) - 4.50) / 4.50)
                    * 100
                    if event.get("yes_price")
                    else 0,
                },
            ],
            "message": "Demo mode - simulated positions",
        }

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    try:
        yes_token = event.get("yes_token_id")
        no_token = event.get("no_token_id")

        if not yes_token or not no_token:
            return {
                "positions": [],
                "message": "Token IDs not configured for this event",
            }

        now_ts = time.time()
        cached = _positions_cache.get(event_id)
        if (
            cached
            and (now_ts - float(cached.get("ts", 0.0))) < _POSITIONS_CACHE_TTL_SECONDS
        ):
            return cached["payload"]

        # Get all trades
        trades = await asyncio.to_thread(client.get_trades)

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
                current_price = (
                    event.get("yes_price", 0.5)
                    if outcome == "Up"
                    else event.get("no_price", 0.5)
                )
                value = total_qty * current_price
                return_value = value - total_cost
                return_pct = (return_value / total_cost * 100) if total_cost > 0 else 0

                positions.append(
                    {
                        "outcome": outcome,
                        "qty": round(total_qty, 2),
                        "avg_price": round(avg_price, 4),
                        "current_price": round(current_price, 4),
                        "cost": round(total_cost, 2),
                        "value": round(value, 2),
                        "return_value": round(return_value, 2),
                        "return_pct": round(return_pct, 2),
                    }
                )

        payload = {
            "positions": positions,
            "cached_for_seconds": _POSITIONS_CACHE_TTL_SECONDS,
        }
        _positions_cache[event_id] = {"ts": now_ts, "payload": payload}
        return payload

    except Exception as e:
        logger.error("Error getting positions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
