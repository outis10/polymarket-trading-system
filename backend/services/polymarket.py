"""Polymarket service: REST data fetching + WebSocket stream."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

import websockets

logger = logging.getLogger(__name__)

POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# Singleton client
_client_instance = None
POLYMARKET_AVAILABLE = False

try:
    from config.settings import Settings
    from core.client_wrapper import PolymarketClient

    POLYMARKET_AVAILABLE = True
except ImportError:
    pass


def get_client():
    """Get or create a singleton PolymarketClient."""
    global _client_instance
    if not POLYMARKET_AVAILABLE:
        return None
    if _client_instance is None:
        try:
            settings_obj = Settings()
            _client_instance = PolymarketClient(settings_obj.polymarket)
            logger.info("Polymarket client initialized successfully")
        except Exception as e:
            logger.error("Failed to connect to Polymarket: %s", e)
            return None
    return _client_instance


def reset_client():
    """Reset the singleton client to force re-initialization with new credentials."""
    global _client_instance
    _client_instance = None
    logger.info("Polymarket client reset - will reinitialize on next request")


def _convert_order_book(ob_summary, max_levels: int = 8) -> Optional[dict]:
    """Convert an OrderBookSummary from py_clob_client to our internal dict."""
    if ob_summary is None:
        return None

    safe_levels = max(1, int(max_levels))
    raw_bids = sorted(
        ob_summary.bids or [], key=lambda l: float(l.price), reverse=True
    )[:safe_levels]
    raw_asks = sorted(ob_summary.asks or [], key=lambda l: float(l.price))[:safe_levels]

    asks = []
    cumulative = 0.0
    for level in raw_asks:
        price = float(level.price)
        shares = float(level.size)
        cumulative += shares * price
        asks.append(
            {
                "price": round(price, 2),
                "shares": round(shares, 2),
                "total": round(cumulative, 2),
            }
        )

    bids = []
    cumulative = 0.0
    for level in raw_bids:
        price = float(level.price)
        shares = float(level.size)
        cumulative += shares * price
        bids.append(
            {
                "price": round(price, 2),
                "shares": round(shares, 2),
                "total": round(cumulative, 2),
            }
        )

    best_ask = asks[0]["price"] if asks else 0.50
    best_bid = bids[0]["price"] if bids else 0.49

    last_price = best_bid
    if ob_summary.last_trade_price:
        try:
            last_price = float(ob_summary.last_trade_price)
        except (ValueError, TypeError):
            pass

    total_volume = sum(a["shares"] * a["price"] for a in asks) + sum(
        b["shares"] * b["price"] for b in bids
    )

    return {
        "bids": bids,
        "asks": asks,
        "last_price": round(last_price, 2),
        "spread": round(max(0, best_ask - best_bid), 2),
        "volume": round(total_volume, 2),
    }


def fetch_real_prices(client, event_config: dict) -> Optional[dict]:
    """Fetch real prices and full order books from Polymarket API (REST)."""
    try:
        tokens = event_config.get("tokens", {})
        yes_token = tokens.get("yes")
        no_token = tokens.get("no")
        if not yes_token or not no_token:
            return None

        yes_ob = client.get_order_book(yes_token)
        no_ob = client.get_order_book(no_token)
        if not yes_ob or not no_ob:
            return None

        yes_bids = yes_ob.bids or []
        yes_asks = yes_ob.asks or []
        no_bids = no_ob.bids or []
        no_asks = no_ob.asks or []

        yes_bid = max((float(b.price) for b in yes_bids), default=0.50)
        yes_ask = min((float(a.price) for a in yes_asks), default=0.50)
        no_bid = max((float(b.price) for b in no_bids), default=0.50)
        no_ask = min((float(a.price) for a in no_asks), default=0.50)

        return {
            "yes_price": (yes_bid + yes_ask) / 2,
            "no_price": (no_bid + no_ask) / 2,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "order_book_yes": _convert_order_book(yes_ob, max_levels=8),
            "order_book_no": _convert_order_book(no_ob, max_levels=8),
        }
    except Exception as e:
        logger.error("Error fetching prices: %s", e)
        return None


# --- WebSocket stream ---


class PolymarketStreamer:
    """Connects to Polymarket WebSocket for real-time market data."""

    def __init__(self, assets_ids: list[str], on_book=None, on_price=None):
        self.assets_ids = assets_ids
        self.on_book = on_book
        self.on_price = on_price
        self._ws = None
        self._running = False

    async def start(self):
        """Connect and stream market events."""
        self._running = True
        while self._running:
            try:
                async with websockets.connect(POLYMARKET_WS_URL) as ws:
                    self._ws = ws
                    logger.info("Polymarket WS connected")

                    # Subscribe to market channel
                    sub_msg = {
                        "assets_ids": self.assets_ids,
                        "type": "market",
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info("Subscribed to market channel: %s", self.assets_ids)

                    # Ping task to keep connection alive
                    ping_task = asyncio.create_task(self._ping_loop(ws))

                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            try:
                                msgs = json.loads(raw)
                                if not isinstance(msgs, list):
                                    msgs = [msgs]
                                for msg in msgs:
                                    await self._handle_message(msg)
                            except Exception:
                                pass
                    finally:
                        ping_task.cancel()

            except websockets.ConnectionClosed:
                logger.warning("Polymarket WS disconnected, reconnecting...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error("Polymarket WS error: %s", e)
                await asyncio.sleep(5)

    async def _ping_loop(self, ws):
        """Send ping every 10s to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(10)
                await ws.ping()
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, msg: dict):
        """Process a single Polymarket WS message."""
        event_type = msg.get("event_type", "")

        if event_type == "book" and self.on_book:
            await self.on_book(msg)
        elif event_type in ("last_trade_price", "price_change") and self.on_price:
            await self.on_price(msg)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
