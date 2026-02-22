"""REST endpoints for trading operations."""

import asyncio
import csv
import logging
import os
import time
from datetime import datetime, timezone

import requests as _requests

from fastapi import APIRouter, HTTPException

from ..models.schemas import OrderRequest, OrderResponse
from ..services.event_manager import event_manager
from ..services.polymarket import get_client, reset_client
from ..ws.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["trading"])
_POSITIONS_CACHE_TTL_SECONDS = 10.0
_positions_cache: dict[str, dict] = {}
_ORDER_BLOCKED_LOG_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "backtest_output",
        "order_blocked_log.csv",
    )
)


def _parse_timeframe_filter_to_minutes(raw: object) -> int | None:
    value = str(raw or "").strip().lower()
    if value == "5m":
        return 5
    if value == "15m":
        return 15
    if value == "1h":
        return 60
    return None


def _quant_gate_reason_text(reasons: list[object]) -> str:
    cleaned = [str(r).strip() for r in reasons if str(r).strip()]
    return " | ".join(cleaned) if cleaned else "quant_gate_blocked"


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_order_blocked_log(row: dict[str, object]) -> None:
    os.makedirs(os.path.dirname(_ORDER_BLOCKED_LOG_PATH), exist_ok=True)
    file_exists = os.path.exists(_ORDER_BLOCKED_LOG_PATH)
    fieldnames = [
        "blocked_at_utc",
        "event_id",
        "timeframe_minutes",
        "side",
        "reason",
        "detail",
        "requested_shares",
        "effective_shares",
        "requested_price",
        "order_price_ref",
        "requested_notional_usd",
        "effective_notional_usd",
        "hard_cap_usd",
        "quant_prob_at_check",
        "ask_price_at_check",
        "ask_is_proxy_at_check",
        "market_prob_at_check",
        "edge_pct_at_check",
        "edge_vs_ask_pct_at_check",
        "sample_size_at_check",
        "percentile_at_check",
    ]
    with open(_ORDER_BLOCKED_LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


def _build_quant_gate_debug(*, event: dict, side: str) -> dict[str, object]:
    quant_prob = _safe_float(
        event.get("quant_prob_up") if side == "up" else event.get("quant_prob_down")
    )
    market_prob = _safe_float(
        event.get("yes_price") if side == "up" else event.get("no_price")
    )
    ask_price_raw = None
    if side == "up":
        asks = (event.get("order_book_yes") or {}).get("asks", [])
    else:
        asks = (event.get("order_book_no") or {}).get("asks", [])
    if isinstance(asks, list) and asks:
        ask_price_raw = _safe_float(
            asks[0].get("price") if isinstance(asks[0], dict) else None
        )
    ask_is_proxy = ask_price_raw is None
    ask_price = ask_price_raw if ask_price_raw is not None else market_prob
    edge_pct = None
    edge_vs_ask_pct = None
    if quant_prob is not None and market_prob is not None:
        # edge_pct: vs mid (consistent with gate logic)
        edge_pct = (quant_prob - market_prob) * 100.0
        # edge_vs_ask_pct: vs actual ask (None if proxy)
        if not ask_is_proxy and ask_price is not None:
            edge_vs_ask_pct = (quant_prob - ask_price) * 100.0
    histogram = event.get("quant_range_histogram")
    percentile = None
    if isinstance(histogram, dict):
        percentile = _safe_float(histogram.get("current_percentile"))
    sample_size = event.get("quant_sample_size")
    return {
        "quant_prob_at_check": quant_prob,
        "ask_price_at_check": ask_price,
        "ask_is_proxy_at_check": ask_is_proxy,
        "market_prob_at_check": market_prob,
        "edge_pct_at_check": edge_pct,
        "edge_vs_ask_pct_at_check": edge_vs_ask_pct,
        "sample_size_at_check": sample_size if isinstance(sample_size, int) else None,
        "percentile_at_check": percentile,
    }


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
    quant_debug = _build_quant_gate_debug(event=event, side=outcome_side)

    def _blocked(detail: str, reason: str) -> HTTPException:
        _append_order_blocked_log(
            {
                "blocked_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                "event_id": order.event_id,
                "timeframe_minutes": int(event.get("timeframe_minutes", 15) or 15),
                "side": outcome_side,
                "reason": reason,
                "detail": detail,
                "requested_shares": requested_shares,
                "effective_shares": effective_shares,
                "requested_price": float(order.price),
                "order_price_ref": order_price_ref,
                "requested_notional_usd": requested_notional_usd,
                "effective_notional_usd": notional_usd,
                "hard_cap_usd": hard_cap_usd,
                **quant_debug,
            }
        )
        return HTTPException(status_code=403, detail=detail)

    selected_tf = _parse_timeframe_filter_to_minutes(
        event_manager.settings.get("timeframe_filter", "5m")
    )
    event_tf = int(event.get("timeframe_minutes", 15) or 15)
    if selected_tf is not None and event_tf != selected_tf:
        raise _blocked(
            detail=(
                f"Timeframe mismatch: selected={selected_tf}m, "
                f"event={event_tf}m for event_id={order.event_id}"
            ),
            reason="timeframe_mismatch",
        )

    quant_gate = event.get("quant_buy_gate")
    if isinstance(quant_gate, dict):
        gate_side = quant_gate.get(outcome_side)
        if isinstance(gate_side, dict) and not bool(gate_side.get("enabled", False)):
            reasons = gate_side.get("reasons", [])
            reasons_list = reasons if isinstance(reasons, list) else [reasons]
            ask_proxy_flag = " (proxy=mid)" if quant_debug.get("ask_is_proxy_at_check") else ""
            detail = (
                f"Quant gate blocked: {_quant_gate_reason_text(reasons_list)}"
                f" | quant_prob={quant_debug.get('quant_prob_at_check')}"
                f" ask={quant_debug.get('ask_price_at_check')}{ask_proxy_flag}"
                f" market_prob={quant_debug.get('market_prob_at_check')}"
                f" edge_pct={quant_debug.get('edge_pct_at_check')}"
                f" edge_vs_ask_pct={quant_debug.get('edge_vs_ask_pct_at_check')}"
                f" sample={quant_debug.get('sample_size_at_check')}"
                f" percentile={quant_debug.get('percentile_at_check')}"
            )
            raise _blocked(detail=detail, reason="quant_gate_blocked")

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
            raise _blocked(
                detail=f"Risk guard blocked: {detailed}",
                reason="risk_guard_blocked",
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
        raise _blocked(
            detail=f"Risk guard blocked: {detailed}",
            reason="risk_guard_blocked",
        )

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


_GAMMA_POSITIONS_URL = "https://gamma-api.polymarket.com/positions"
_CLAIMABLE_CACHE: dict = {"ts": 0.0, "data": None}
_CLAIMABLE_CACHE_TTL = 300.0  # 5 min — claimable changes only on market resolution


def _fetch_claimable_sync(wallet: str) -> dict:
    """Query Gamma API for resolved positions with redeemable value."""
    try:
        resp = _requests.get(
            _GAMMA_POSITIONS_URL,
            params={"user": wallet, "sizeThreshold": "0", "limit": "500"},
            timeout=5,
        )
        resp.raise_for_status()
        positions = resp.json()
    except Exception as e:
        return {"error": str(e), "claimable_usd": None}

    if not isinstance(positions, list):
        positions = positions.get("data", []) if isinstance(positions, dict) else []

    claimable_usd = 0.0
    claimable_positions = []
    for pos in positions:
        # redeemable: market resolved and position has value (outcome won)
        redeemable = pos.get("redeemable") or pos.get("isRedeemable") or False
        if not redeemable:
            continue
        size = float(pos.get("size", 0) or 0)
        # resolved winning tokens are worth $1 each
        value = float(pos.get("currentValue", size) or size)
        if value <= 0:
            continue
        claimable_usd += value
        claimable_positions.append({
            "market": pos.get("market") or pos.get("conditionId", ""),
            "title": pos.get("title") or pos.get("question", ""),
            "outcome": pos.get("outcome", ""),
            "size": round(size, 4),
            "value_usd": round(value, 4),
        })

    return {
        "claimable_usd": round(claimable_usd, 4),
        "positions": claimable_positions,
        "wallet": wallet,
    }


@router.get("/claimable")
async def get_claimable():
    """Get total redeemable USDC from resolved winning positions (via Gamma API)."""
    if event_manager.mode == "demo":
        return {"claimable_usd": 0.0, "positions": [], "message": "Demo mode"}

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    wallet = getattr(client.config, "funder", None)
    if not wallet:
        raise HTTPException(status_code=500, detail="POLYMARKET_FUNDER not configured")

    now = time.monotonic()
    if _CLAIMABLE_CACHE["data"] is not None and (now - _CLAIMABLE_CACHE["ts"]) < _CLAIMABLE_CACHE_TTL:
        return _CLAIMABLE_CACHE["data"]

    result = await asyncio.to_thread(_fetch_claimable_sync, wallet)
    _CLAIMABLE_CACHE["ts"] = now
    _CLAIMABLE_CACHE["data"] = result
    return result


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
        return {"positions": [], "message": "Event not found or not yet active"}

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


# ---------------------------------------------------------------------------
# Bot order history
# ---------------------------------------------------------------------------

_BOT_ORDERS_LOG_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "backtest_output",
        "bot_orders.csv",
    )
)


@router.get("/bot/orders")
async def get_bot_orders(limit: int = 200, ticker: str | None = None):
    """Return bot auto-order history from CSV (most recent first)."""
    if not os.path.exists(_BOT_ORDERS_LOG_PATH):
        return {"count": 0, "rows": []}
    rows: list[dict] = []
    try:
        with open(_BOT_ORDERS_LOG_PATH, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker and row.get("ticker", "").upper() != ticker.upper():
                    continue
                rows.append(row)
    except Exception as e:
        logger.error("Error reading bot orders log: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    rows = rows[-limit:]
    rows.reverse()
    return {"count": len(rows), "rows": rows}
