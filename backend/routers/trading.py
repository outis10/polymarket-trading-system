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


def invalidate_positions_cache(event_id: str) -> None:
    """Remove cached positions for an event so the next request fetches fresh data."""
    _positions_cache.pop(event_id, None)


_ORDER_BLOCKED_LOG_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "backtest_output",
        "order_blocked_log.csv",
    )
)


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
    is_sell = order.side.strip().upper() == "SELL"
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
    ladder = event_manager.settings.get("bot_trade_ladder", [])
    ladder_active = isinstance(ladder, list) and len(ladder) > 0
    hard_cap_usd = (
        0.0
        if ladder_active
        else max(
            0.0, float(event_manager.settings.get("bot_order_notional_cap_usd", 5.0))
        )
    )
    cap_applied = False
    # Notional cap only applies to buys — sells should exit the full position.
    # Cap is applied directly in USD (not derived from shares × ref_price) so that
    # market orders sent as notional match exactly the cap regardless of fill price.
    if not is_sell and hard_cap_usd > 0 and requested_notional_usd > hard_cap_usd:
        notional_usd = hard_cap_usd
        cap_applied = True
    else:
        notional_usd = requested_notional_usd
    effective_shares = (
        notional_usd / order_price_ref if order_price_ref > 0 else requested_shares
    )
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

    # Resolve bankroll early so evaluate_bot_order_candidate uses the real live balance.
    # In demo mode the bankroll comes from event_manager internals; in live mode we
    # fetch it from the Polymarket client before running eligibility checks.
    live_client = None
    if event_manager.mode != "demo":
        live_client = get_client()
        if not live_client:
            raise HTTPException(status_code=503, detail="Polymarket client unavailable")
        try:
            balance = live_client.get_balance()
            if isinstance(balance, (int, float)) and float(balance) > 0:
                bankroll_usd = float(balance)
        except Exception:
            bankroll_usd = None

    if not is_sell:
        now_utc = datetime.now(tz=timezone.utc)
        evaluation = event_manager.evaluate_bot_order_candidate(
            event_id=order.event_id,
            event_dict=event,
            side=outcome_side,
            now_utc=now_utc,
            bankroll_usd=bankroll_usd,
        )
        if not evaluation["eligible"]:
            reason_code = evaluation.get("reason") or "eligibility_blocked"
            # Build a detailed message for quant_gate_blocked using existing debug info
            if reason_code.startswith("quant_gate_blocked"):
                ask_proxy_flag = (
                    " (proxy=mid)" if quant_debug.get("ask_is_proxy_at_check") else ""
                )
                gate_reasons = (
                    reason_code.split(":", 1)[1] if ":" in reason_code else reason_code
                )
                detail = (
                    f"Quant gate blocked: {gate_reasons}"
                    f" | quant_prob={quant_debug.get('quant_prob_at_check')}"
                    f" ask={quant_debug.get('ask_price_at_check')}{ask_proxy_flag}"
                    f" market_prob={quant_debug.get('market_prob_at_check')}"
                    f" edge_pct={quant_debug.get('edge_pct_at_check')}"
                    f" edge_vs_ask_pct={quant_debug.get('edge_vs_ask_pct_at_check')}"
                    f" sample={quant_debug.get('sample_size_at_check')}"
                    f" percentile={quant_debug.get('percentile_at_check')}"
                )
                raise _blocked(detail=detail, reason="quant_gate_blocked")
            elif reason_code in (
                "timeframe_mismatch",
                "too_close_to_end",
                "ask_price_outside_range",
                "kelly_disabled",
                "no_quant_prob",
                "edge_below_min",
                "stake_non_positive",
                "invalid_side_price",
            ):
                raise _blocked(detail=reason_code, reason=reason_code)
            else:
                # risk_guard_blocked and any other guard reason
                detailed = event_manager.format_risk_guard_block_reason(
                    reason=reason_code,
                    event_id=order.event_id,
                    event=event,
                    notional_usd=notional_usd,
                    now_utc=now_utc,
                    bankroll_usd=bankroll_usd,
                )
                raise _blocked(
                    detail=f"Risk guard blocked: {detailed}",
                    reason="risk_guard_blocked",
                )

    # Demo mode: simulate
    if event_manager.mode == "demo":
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

    # Live mode: execute via Polymarket (client already obtained above)
    client = live_client

    token_id = (
        event.get("yes_token_id") if order.outcome == "up" else event.get("no_token_id")
    )
    if not token_id:
        raise HTTPException(
            status_code=400, detail="Token ID not found for this outcome"
        )

    try:
        side = order.side.upper()
        logger.info(
            "[ORDER] event_id=%s outcome=%s side=%s order_type=%s "
            "requested_shares=%.4f effective_shares=%.4f order_price=%.4f "
            "token_id=%s",
            order.event_id,
            outcome_side,
            side,
            order.order_type,
            requested_shares,
            effective_shares,
            order_price_ref,
            token_id,
        )
        if is_sell:
            # Ensure the CLOB has allowance to move conditional tokens (shares) from wallet.
            # Without this, sells fail with "not enough balance / allowance".
            try:
                from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

                cond_params = BalanceAllowanceParams(
                    asset_type=AssetType.CONDITIONAL,
                    token_id=token_id,
                    signature_type=client.config.signature_type,
                )
                client.client.update_balance_allowance(cond_params)
                logger.info(
                    "[SELL] conditional allowance updated for token=%s", token_id
                )
            except Exception as e:
                logger.warning("[SELL] could not update conditional allowance: %s", e)

        if order.order_type == "market" and is_sell:
            # For sell market orders, derive the best bid from the in-memory order book
            # (already fetched by the price poller). Falls back to mid-price then the
            # caller-supplied price so we never send a None price to the CLOB.
            ob_key = "order_book_yes" if outcome_side == "up" else "order_book_no"
            ob = event.get(ob_key) or {}
            bids = ob.get("bids") or []
            asks = ob.get("asks") or []
            if bids and isinstance(bids[0], dict):
                sell_price = float(bids[0]["price"])
                price_source = "best_bid"
            else:
                # Fallback: mid-price from event, then caller-supplied price
                mid_key = "yes_price" if outcome_side == "up" else "no_price"
                sell_price = float(event.get(mid_key) or order.price or 0.50)
                price_source = "mid_price_fallback"
            logger.info(
                "[SELL] token=%s price=%.4f shares=%.4f price_source=%s "
                "bids_top3=%s asks_top3=%s yes_price=%.4f no_price=%.4f",
                token_id,
                sell_price,
                effective_shares,
                price_source,
                [b.get("price") for b in bids[:3]] if bids else "none",
                [a.get("price") for a in asks[:3]] if asks else "none",
                float(event.get("yes_price") or 0),
                float(event.get("no_price") or 0),
            )
            result = client.place_order(token_id, side, sell_price, effective_shares)
        elif order.order_type == "market":
            # BUY market orders use place_fok_order (notional USD) — same as the bot
            # auto-order path — so the cap is enforced at the exact USD amount
            # regardless of fill price. SELL market orders stay share-based (exit full position).
            if not is_sell:
                ask_price = quant_debug.get("ask_price_at_check")
                result = client.place_fok_order(
                    token_id, "BUY", notional_usd, ask_price
                )
            else:
                result = client.place_market_order(token_id, side, effective_shares)
        else:
            result = client.place_order(token_id, side, order.price, effective_shares)

        logger.info(
            "Raw CLOB result type=%s value=%s",
            type(result).__name__,
            repr(result)[:200],
        )

        # Detect CLOB error responses (dict with errorCode/error key)
        if isinstance(result, dict) and (
            result.get("errorCode") or result.get("error")
        ):
            err_msg = result.get("error") or result.get("errorCode") or str(result)
            logger.error(
                "CLOB returned error for %s %s: %s", side, outcome_side, err_msg
            )
            raise HTTPException(status_code=500, detail=f"CLOB error: {err_msg}")

        if result:
            # SignedOrder object - access attributes directly
            order_id = (
                getattr(result, "id", None)
                or getattr(result, "orderID", None)
                or (result.get("orderID") if isinstance(result, dict) else None)
                or str(result)[:16]
            )
            status = (
                getattr(result, "status", None)
                or (result.get("status") if isinstance(result, dict) else None)
                or "OPEN"
            )
            now_fill = datetime.now(tz=timezone.utc)
            if not is_sell:
                event_manager.register_order_fill(
                    event_id=order.event_id,
                    event=event,
                    outcome=outcome_side,
                    notional_usd=notional_usd,
                    now_utc=now_fill,
                    bankroll_snapshot_usd=bankroll_usd,
                )
                # Extraer shares reales del resultado (takingAmount del CLOB)
                taking_amount = (
                    result.get("takingAmount") if isinstance(result, dict) else None
                )
                real_shares = (
                    float(taking_amount) if taking_amount else effective_shares
                )
                event_manager.record_position_buy(
                    event_id=order.event_id,
                    outcome=outcome_side,
                    token_id=token_id,
                    shares=real_shares,
                    price=order_price_ref,
                    placed_at_utc=now_fill.isoformat(),
                )
            else:
                event_manager.record_position_sell(
                    event_id=order.event_id,
                    outcome=outcome_side,
                    shares_sold=effective_shares,
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
        logger.error(
            "[ORDER ERROR] event_id=%s outcome=%s side=%s order_type=%s "
            "token_id=%s effective_shares=%.4f error=%s",
            order.event_id,
            outcome_side,
            order.side.upper(),
            order.order_type,
            token_id,
            effective_shares,
            e,
        )
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


@router.get("/balance/matic")
async def get_matic_balance():
    """Get native MATIC balance of the wallet on Polygon."""
    if event_manager.mode == "demo":
        return {"matic": None, "message": "Demo mode"}
    client = get_client()
    if not client:
        return {"matic": None, "message": "Client unavailable"}
    try:
        from web3 import Web3
        wallet = getattr(client.config, "funder", None)
        if not wallet:
            return {"matic": None, "message": "Wallet address not configured"}
        rpc_url = _DEFAULT_RPC_URL.get(137, "https://rpc-mainnet.matic.quiknode.pro")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        balance_wei = await asyncio.to_thread(w3.eth.get_balance, Web3.to_checksum_address(wallet))
        matic = round(balance_wei / 1e18, 4)
        return {"matic": matic}
    except Exception as exc:
        logger.warning("MATIC balance error: %s", exc)
        return {"matic": None, "error": str(exc)}


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


_POSITIONS_URL = "https://data-api.polymarket.com/positions"
_CLAIMABLE_CACHE: dict = {"ts": 0.0, "data": None}
_CLAIMABLE_CACHE_TTL = 300.0  # 5 min — claimable changes only on market resolution
# condition_ids redeemed recently: {condition_id: monotonic_ts} — TTL 3 min
# prevents re-redeeming while data-api lags behind on-chain state;
# short TTL so failed on-chain txs (reverts) can be retried quickly
_RECENTLY_REDEEMED: dict[str, float] = {}
_RECENTLY_REDEEMED_TTL = 180.0  # 3 min

# --- Redeem (on-chain) constants ---
_CTF_ABI = [
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]
_CTF_ADDRESS = {
    137: "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",  # mainnet Polygon
    80002: "0x69308FB512518e39F9b16112fA8d994F4e2Bf8bB",  # testnet Amoy
}
_GNOSIS_SAFE_ABI = [
    {
        "inputs": [],
        "name": "nonce",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "data", "type": "bytes"},
            {"name": "operation", "type": "uint8"},
            {"name": "safeTxGas", "type": "uint256"},
            {"name": "baseGas", "type": "uint256"},
            {"name": "gasPrice", "type": "uint256"},
            {"name": "gasToken", "type": "address"},
            {"name": "refundReceiver", "type": "address"},
            {"name": "signatures", "type": "bytes"},
        ],
        "name": "execTransaction",
        "outputs": [{"name": "success", "type": "bool"}],
        "stateMutability": "payable",
        "type": "function",
    },
]
_COLLATERAL_ADDRESS = {
    137: "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC PoS mainnet
    80002: "0x9c4e1703476e875070ee25b56a58b008cfb8fa78",  # USDC testnet
}
_DEFAULT_RPC_URL = {
    137: "https://rpc-mainnet.matic.quiknode.pro",
    80002: "https://rpc-amoy.polygon.technology",
}
_PARENT_COLLECTION_ID = b"\x00" * 32  # root-level positions


def _fetch_claimable_sync(wallet: str) -> dict:
    """Query data-api for resolved positions with redeemable value (currentValue > 0).
    Paginates automatically — the API returns max 100 per call by default.
    """
    _PAGE_SIZE = 100  # data-api caps at 100 regardless of limit param
    all_positions: list = []
    offset = 0
    try:
        while True:
            resp = _requests.get(
                _POSITIONS_URL,
                params={
                    "user": wallet,
                    "limit": _PAGE_SIZE,
                    "offset": offset,
                    "redeemable": "true",
                },
                timeout=5,
            )
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            page = resp.json()
            if not isinstance(page, list):
                page = page.get("data", []) if isinstance(page, dict) else []
            all_positions.extend(page)
            # Stop when we get an empty page or fewer results than requested
            if not page or len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    except Exception as e:
        return {"error": str(e), "claimable_usd": None}

    positions = all_positions

    # Purge expired entries from the recently-redeemed cache
    import time as _time_mod

    _now = _time_mod.monotonic()
    expired = [
        k for k, ts in _RECENTLY_REDEEMED.items() if _now - ts > _RECENTLY_REDEEMED_TTL
    ]
    for k in expired:
        del _RECENTLY_REDEEMED[k]

    claimable_usd = 0.0
    claimable_positions = []
    for pos in positions:
        if not pos.get("redeemable"):
            continue
        value = float(pos.get("currentValue", 0) or 0)
        if value <= 0:
            continue
        cid = pos.get("conditionId", "")
        if cid and cid in _RECENTLY_REDEEMED:
            continue
        size = float(pos.get("size", 0) or 0)
        claimable_usd += value
        claimable_positions.append(
            {
                "condition_id": pos.get("conditionId", ""),
                "title": pos.get("title", ""),
                "outcome": pos.get("outcome", ""),
                "outcome_index": int(pos.get("outcomeIndex", 0)),
                "neg_risk": bool(pos.get("negativeRisk", False)),
                "size": round(size, 4),
                "value_usd": round(value, 4),
            }
        )

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
    if (
        _CLAIMABLE_CACHE["data"] is not None
        and (now - _CLAIMABLE_CACHE["ts"]) < _CLAIMABLE_CACHE_TTL
    ):
        return _CLAIMABLE_CACHE["data"]

    result = await asyncio.to_thread(_fetch_claimable_sync, wallet)
    _CLAIMABLE_CACHE["ts"] = now
    _CLAIMABLE_CACHE["data"] = result
    return result


_POSITIONS_VALUE_CACHE: dict = {"ts": 0.0, "data": None}
_POSITIONS_VALUE_CACHE_TTL = 60.0  # 1 min


def _fetch_positions_value_sync(wallet: str) -> dict:
    """Query data-api for all open positions and sum their current market value."""
    _PAGE_SIZE = 100
    all_positions: list = []
    offset = 0
    try:
        while True:
            resp = _requests.get(
                _POSITIONS_URL,
                params={"user": wallet, "limit": _PAGE_SIZE, "offset": offset},
                timeout=5,
            )
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            page = resp.json()
            if not isinstance(page, list):
                page = page.get("data", []) if isinstance(page, dict) else []
            all_positions.extend(page)
            if not page or len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    except Exception as e:
        return {"error": str(e), "positions_value_usd": None}

    positions_value = sum(
        float(p.get("currentValue", 0) or 0)
        for p in all_positions
        if not p.get("redeemable")
    )
    return {"positions_value_usd": round(positions_value, 4)}


@router.get("/positions_value")
async def get_positions_value():
    """Get total current market value of open (non-redeemable) positions."""
    if event_manager.mode == "demo":
        return {"positions_value_usd": 0.0}

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    wallet = getattr(client.config, "funder", None)
    if not wallet:
        raise HTTPException(status_code=500, detail="POLYMARKET_FUNDER not configured")

    now = time.monotonic()
    if (
        _POSITIONS_VALUE_CACHE["data"] is not None
        and (now - _POSITIONS_VALUE_CACHE["ts"]) < _POSITIONS_VALUE_CACHE_TTL
    ):
        return _POSITIONS_VALUE_CACHE["data"]

    result = await asyncio.to_thread(_fetch_positions_value_sync, wallet)
    _POSITIONS_VALUE_CACHE["ts"] = now
    _POSITIONS_VALUE_CACHE["data"] = result
    return result


@router.get("/equity")
async def get_equity():
    """Return consolidated equity: bankroll + open positions + claimable, plus net PnL vs start."""
    if event_manager.mode == "demo":
        return {
            "bankroll_usd": 1000.0,
            "positions_value_usd": 0.0,
            "claimable_usd": 0.0,
            "equity_usd": 1000.0,
            "equity_start_usd": None,
            "net_pnl_usd": None,
        }

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    wallet = getattr(client.config, "funder", None)
    if not wallet:
        raise HTTPException(status_code=500, detail="POLYMARKET_FUNDER not configured")

    # Run balance + claimable + positions_value in parallel
    import asyncio as _asyncio

    balance_task = _asyncio.to_thread(lambda: client.get_balance())
    claimable_task = _asyncio.to_thread(_fetch_claimable_sync, wallet)
    posval_task = _asyncio.to_thread(_fetch_positions_value_sync, wallet)
    balance_raw, claimable_data, posval_data = await _asyncio.gather(
        balance_task, claimable_task, posval_task
    )

    bankroll = float(balance_raw or 0.0)
    claimable = float((claimable_data or {}).get("claimable_usd") or 0.0)
    positions_val = float((posval_data or {}).get("positions_value_usd") or 0.0)
    equity = bankroll + claimable + positions_val

    equity_start = float(
        event_manager.settings.get("live_equity_start_bankroll_usd") or 0.0
    )
    net_pnl = round(equity - equity_start, 4) if equity_start > 0 else None

    return {
        "bankroll_usd": round(bankroll, 4),
        "positions_value_usd": round(positions_val, 4),
        "claimable_usd": round(claimable, 4),
        "equity_usd": round(equity, 4),
        "equity_start_usd": round(equity_start, 4) if equity_start > 0 else None,
        "net_pnl_usd": net_pnl,
    }


_EQUITY_SNAPSHOT_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "backtest_output",
        "equity_snapshots.csv",
    )
)
_EQUITY_SNAPSHOT_FIELDS = [
    "timestamp_utc",
    "bankroll_usdc",
    "positions_value_usd",
    "claimable_usd",
    "equity_usd",
    "net_pnl_usd",
]


async def save_equity_snapshot() -> None:
    """Fetch current equity and append a row to equity_snapshots.csv."""
    if event_manager.mode == "demo":
        return
    client = get_client()
    if not client:
        return
    wallet = getattr(client.config, "funder", None)
    if not wallet:
        return

    import asyncio as _asyncio

    try:
        balance_raw, claimable_data, posval_data = await _asyncio.gather(
            _asyncio.to_thread(lambda: client.get_balance()),
            _asyncio.to_thread(_fetch_claimable_sync, wallet),
            _asyncio.to_thread(_fetch_positions_value_sync, wallet),
        )
    except Exception as exc:
        logger.warning("equity_snapshot: fetch failed: %s", exc)
        return

    bankroll = float(balance_raw or 0.0)
    claimable = float((claimable_data or {}).get("claimable_usd") or 0.0)
    positions_val = float((posval_data or {}).get("positions_value_usd") or 0.0)
    equity = bankroll + claimable + positions_val
    equity_start = float(
        event_manager.settings.get("live_equity_start_bankroll_usd") or 0.0
    )
    net_pnl = round(equity - equity_start, 4) if equity_start > 0 else None

    row = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bankroll_usdc": round(bankroll, 4),
        "positions_value_usd": round(positions_val, 4),
        "claimable_usd": round(claimable, 4),
        "equity_usd": round(equity, 4),
        "net_pnl_usd": net_pnl,
    }
    os.makedirs(os.path.dirname(_EQUITY_SNAPSHOT_PATH), exist_ok=True)
    file_exists = os.path.exists(_EQUITY_SNAPSHOT_PATH)
    with open(_EQUITY_SNAPSHOT_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_EQUITY_SNAPSHOT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    logger.debug(
        "equity_snapshot saved: equity=%.2f net_pnl=%s",
        equity,
        f"{net_pnl:+.2f}" if net_pnl is not None else "n/a",
    )


def _outcome_index_to_index_sets(outcome_index: int) -> list[int]:
    """Convert outcomeIndex (0-based) to CTF indexSets (1-based bitmask)."""
    return [1 << outcome_index]  # outcomeIndex=0 → [1], outcomeIndex=1 → [2]


def _gnosis_exec_transaction(
    w3,
    private_key: str,
    eoa_address: str,
    safe_address: str,
    to: str,
    calldata: bytes,
    chain_id: int,
    eoa_nonce: int | None = None,
    safe_nonce: int | None = None,
) -> str:
    """
    Sign and execute a transaction through a Gnosis Safe proxy.

    The EOA (eoa_address) is an owner of the Safe (safe_address).  The Safe
    will perform a CALL to `to` with `calldata`, so msg.sender seen by the
    target contract is the Safe address (the actual token holder).

    Returns the submitted tx hash as '0x...' hex string.
    """
    import eth_abi
    from eth_keys import keys as eth_keys_mod

    safe_cs = w3.to_checksum_address(safe_address)
    to_cs = w3.to_checksum_address(to)
    eoa_cs = w3.to_checksum_address(eoa_address)
    zero_addr = "0x0000000000000000000000000000000000000000"

    safe = w3.eth.contract(address=safe_cs, abi=_GNOSIS_SAFE_ABI)
    if safe_nonce is None:
        safe_nonce = safe.functions.nonce().call()

    # --- EIP-712 type hashes ---
    domain_th = bytes(
        w3.keccak(text="EIP712Domain(uint256 chainId,address verifyingContract)")
    )
    safe_tx_th = bytes(
        w3.keccak(
            text=(
                "SafeTx(address to,uint256 value,bytes data,uint8 operation,"
                "uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,"
                "address gasToken,address refundReceiver,uint256 nonce)"
            )
        )
    )

    # --- Domain separator ---
    domain_sep = bytes(
        w3.keccak(
            eth_abi.encode(
                ["bytes32", "uint256", "address"],
                [domain_th, chain_id, safe_cs],
            )
        )
    )

    # --- Safe tx hash (all numeric fields are 0 = no refund/no gas payment) ---
    safe_tx_hash_bytes = bytes(
        w3.keccak(
            eth_abi.encode(
                [
                    "bytes32",
                    "address",
                    "uint256",
                    "bytes32",
                    "uint8",
                    "uint256",
                    "uint256",
                    "uint256",
                    "address",
                    "address",
                    "uint256",
                ],
                [
                    safe_tx_th,
                    to_cs,
                    0,  # ETH value
                    bytes(w3.keccak(calldata)),  # keccak256(data)
                    0,  # operation = CALL
                    0,  # safeTxGas
                    0,  # baseGas
                    0,  # gasPrice (Safe-level)
                    zero_addr,  # gasToken
                    zero_addr,  # refundReceiver
                    safe_nonce,
                ],
            )
        )
    )

    # --- Final EIP-712 hash ---
    final_hash = bytes(w3.keccak(b"\x19\x01" + domain_sep + safe_tx_hash_bytes))

    # --- Sign with EOA private key (raw ECDSA, no eth_sign prefix) ---
    pk_bytes = bytes.fromhex(private_key.removeprefix("0x"))
    pk = eth_keys_mod.PrivateKey(pk_bytes)
    sig = pk.sign_msg_hash(final_hash)
    v_val, r_val, s_val = sig.vrs
    # Gnosis Safe expects packed r || s || v with v = recovery_id + 27
    signature = (
        r_val.to_bytes(32, "big") + s_val.to_bytes(32, "big") + bytes([v_val + 27])
    )

    # --- Build execTransaction from EOA ---
    fn = safe.functions.execTransaction(
        to_cs,
        0,  # ETH value
        calldata,
        0,  # operation = CALL
        0,  # safeTxGas
        0,  # baseGas
        0,  # gasPrice (Safe-level)
        zero_addr,  # gasToken
        zero_addr,  # refundReceiver
        signature,
    )
    if eoa_nonce is None:
        eoa_nonce = w3.eth.get_transaction_count(eoa_cs)
    try:
        gas = fn.estimate_gas({"from": eoa_cs})
        gas_limit = int(gas * 1.3)
    except Exception:
        gas_limit = 400_000  # conservative fallback

    tx = fn.build_transaction(
        {
            "from": eoa_cs,
            "nonce": eoa_nonce,
            "gas": gas_limit,
            "gasPrice": w3.eth.gas_price,
        }
    )
    signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return "0x" + tx_hash.hex()


def _redeem_positions_sync(
    private_key: str,
    wallet: str,
    chain_id: int,
    positions: list[dict],
) -> list[dict]:
    """
    Execute redeemPositions on-chain for each position.

    If `wallet` is a Gnosis Safe proxy (has contract code), we route through
    execTransaction so the Safe itself is msg.sender (it holds the tokens).
    If it's a plain EOA, we call the CTF contract directly.
    """
    try:
        import eth_abi
        from eth_account import Account
        from web3 import Web3
    except ImportError as exc:
        return [{"error": f"Missing dependency: {exc}", "skipped": True}]

    rpc_url = os.getenv("POLYGON_RPC_URL") or _DEFAULT_RPC_URL.get(
        chain_id, "https://rpc-mainnet.matic.quiknode.pro"
    )
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        return [{"error": f"Cannot connect to Polygon RPC: {rpc_url}"}]

    # Derive the true EOA address from the private key
    eoa_address = Account.from_key(private_key).address
    safe_address = Web3.to_checksum_address(wallet)

    # Detect whether wallet is a contract (Gnosis Safe proxy) or a plain EOA
    code = w3.eth.get_code(safe_address)
    is_safe = len(bytes(code)) > 2  # b'' or b'0x' → no code → plain EOA
    logger.info(
        "Redeem: wallet=%s eoa=%s is_safe=%s chain=%s",
        safe_address,
        eoa_address,
        is_safe,
        chain_id,
    )

    ctf_address = Web3.to_checksum_address(_CTF_ADDRESS[chain_id])
    collateral = Web3.to_checksum_address(_COLLATERAL_ADDRESS[chain_id])
    contract = w3.eth.contract(address=ctf_address, abi=_CTF_ABI)

    # Pre-compute redeemPositions function selector for calldata encoding
    fn_selector = bytes(
        w3.keccak(text="redeemPositions(address,bytes32,bytes32,uint256[])")
    )[:4]

    results = []
    eoa_nonce = w3.eth.get_transaction_count(eoa_address)
    safe_nonce = None
    if is_safe:
        safe_contract = w3.eth.contract(
            address=w3.to_checksum_address(safe_address), abi=_GNOSIS_SAFE_ABI
        )
        safe_nonce = safe_contract.functions.nonce().call()

    for pos in positions:
        condition_id_hex = pos.get("condition_id", "")
        title = pos.get("title", "")

        try:
            raw = condition_id_hex.removeprefix("0x").zfill(64)
            condition_id_bytes = bytes.fromhex(raw)
            if len(condition_id_bytes) != 32:
                raise ValueError("condition_id must be 32 bytes")
        except Exception as e:
            results.append(
                {
                    "title": title,
                    "condition_id": condition_id_hex,
                    "error": str(e),
                    "skipped": True,
                }
            )
            continue

        index_sets = _outcome_index_to_index_sets(pos.get("outcome_index", 0))

        try:
            if is_safe:
                # Encode redeemPositions calldata (ABI-encoded args after selector)
                calldata = fn_selector + eth_abi.encode(
                    ["address", "bytes32", "bytes32", "uint256[]"],
                    [collateral, _PARENT_COLLECTION_ID, condition_id_bytes, index_sets],
                )
                tx_hash_hex = _gnosis_exec_transaction(
                    w3,
                    private_key,
                    eoa_address,
                    safe_address,
                    ctf_address,
                    calldata,
                    chain_id,
                    eoa_nonce=eoa_nonce,
                    safe_nonce=safe_nonce,
                )
                eoa_nonce += 1
                safe_nonce += 1
            else:
                # Direct EOA call
                fn = contract.functions.redeemPositions(
                    collateral, _PARENT_COLLECTION_ID, condition_id_bytes, index_sets
                )
                gas_estimate = fn.estimate_gas({"from": eoa_address})
                tx = fn.build_transaction(
                    {
                        "from": eoa_address,
                        "nonce": eoa_nonce,
                        "gas": int(gas_estimate * 1.2),
                        "gasPrice": w3.eth.gas_price,
                    }
                )
                signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
                raw_tx = w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hash_hex = "0x" + raw_tx.hex()
                eoa_nonce += 1

            results.append(
                {
                    "title": title,
                    "condition_id": condition_id_hex,
                    "outcome": pos.get("outcome", ""),
                    "value_usd": pos.get("value_usd", 0.0),
                    "tx_hash": tx_hash_hex,
                    "status": "sent",
                }
            )
            logger.info("Redeem sent: %s tx=%s", title, tx_hash_hex)
            if condition_id_hex:
                import time as _time_mod

                _RECENTLY_REDEEMED[condition_id_hex] = _time_mod.monotonic()

        except Exception as e:
            logger.error("Redeem failed for %s: %s", condition_id_hex, e)
            results.append(
                {
                    "title": title,
                    "condition_id": condition_id_hex,
                    "outcome": pos.get("outcome", ""),
                    "error": str(e),
                    "status": "failed",
                }
            )

    return results


@router.post("/redeem")
async def execute_redeem():
    """Execute redeemPositions on-chain for all claimable resolved positions."""
    if event_manager.mode == "demo":
        return {
            "redeemed": [],
            "total_usd": 0.0,
            "message": "Demo mode — no on-chain tx",
        }

    client = get_client()
    if not client:
        raise HTTPException(status_code=503, detail="Polymarket client unavailable")

    wallet = getattr(client.config, "funder", None)
    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    chain_id = int(os.getenv("CHAIN_ID", "137"))

    if not wallet or not private_key:
        raise HTTPException(
            status_code=500,
            detail="POLYMARKET_FUNDER or POLYMARKET_PRIVATE_KEY not configured",
        )
    if chain_id not in _CTF_ADDRESS:
        raise HTTPException(status_code=400, detail=f"Unsupported chain_id: {chain_id}")

    # Always fetch fresh (bypass cache) before redeeming
    claimable = await asyncio.to_thread(_fetch_claimable_sync, wallet)
    if claimable.get("error"):
        raise HTTPException(
            status_code=502, detail=f"Gamma API error: {claimable['error']}"
        )

    positions = [p for p in claimable.get("positions", []) if p.get("condition_id")]
    if not positions:
        return {
            "redeemed": [],
            "summary": {"sent": 0, "failed": 0, "skipped": 0, "total_usd_sent": 0.0},
            "message": "No redeemable positions found",
        }

    results = await asyncio.to_thread(
        _redeem_positions_sync, private_key, wallet, chain_id, positions
    )

    # Invalidate cache so next GET /claimable reflects updated state
    _CLAIMABLE_CACHE["data"] = None
    _CLAIMABLE_CACHE["ts"] = 0.0

    sent = [r for r in results if r.get("status") == "sent"]
    failed = [r for r in results if r.get("status") == "failed"]
    skipped = [r for r in results if r.get("skipped")]
    total_usd = sum(r.get("value_usd", 0.0) for r in sent)

    return {
        "redeemed": results,
        "summary": {
            "sent": len(sent),
            "failed": len(failed),
            "skipped": len(skipped),
            "total_usd_sent": round(total_usd, 4),
        },
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
    """Get positions for a specific event. Uses in-memory tracker as source of truth."""
    event = event_manager.events.get(event_id)
    if not event:
        return {"positions": [], "message": "Event not found or not yet active"}

    if event_manager.mode == "demo":
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

    # --- Tracker path (fuente de verdad) ---
    tracked = event_manager.get_tracked_positions(event_id)
    if tracked:
        positions = []
        for outcome_key, pos in tracked.items():
            outcome_label = "Up" if outcome_key == "up" else "Down"
            current_price = float(
                event.get("yes_price", pos["avg_price"])
                if outcome_key == "up"
                else event.get("no_price", pos["avg_price"])
            )
            qty = pos["shares"]
            avg_price = pos["avg_price"]
            cost = round(qty * avg_price, 2)
            value = round(qty * current_price, 2)
            return_value = round(value - cost, 2)
            return_pct = round((return_value / cost * 100) if cost > 0 else 0, 2)
            positions.append(
                {
                    "outcome": outcome_label,
                    "qty": round(qty, 4),
                    "avg_price": round(avg_price, 4),
                    "current_price": round(current_price, 4),
                    "cost": cost,
                    "value": value,
                    "return_value": return_value,
                    "return_pct": return_pct,
                    "token_id": pos.get("token_id", ""),
                    "placed_at_utc": pos.get("placed_at_utc", ""),
                }
            )
        return {"positions": positions, "source": "tracker"}

    # Sin posiciones trackeadas para este evento
    return {"positions": [], "source": "tracker"}


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
