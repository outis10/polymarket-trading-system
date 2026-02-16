"""Chainlink price streaming helpers (config-driven WebSocket client)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional

import websockets

logger = logging.getLogger(__name__)


def normalize_symbol(value: str | None) -> str:
    """Normalize symbol/pair string to base asset symbol (BTC/ETH/SOL/XRP)."""
    if not value:
        return ""
    text = str(value).upper().strip()
    text = text.replace("-", "/").replace("_", "/")
    if "/" in text:
        return text.split("/")[0]
    # Examples: BTCUSDT, ETHUSD
    for suffix in ("USDT", "USD"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


class ChainlinkPriceStreamer:
    """
    Generic WS streamer for Chainlink/RTDS-like payloads.

    Expected config:
      - url: wss://...
      - subscribe: optional JSON payload sent after connect
      - ping_interval: optional seconds (default 20)
    """

    def __init__(
        self,
        url: str,
        symbols: list[str],
        on_price: Callable[[str, float], Any],
        subscribe_message: Optional[dict[str, Any]] = None,
        ping_interval: int = 20,
    ):
        self.url = url
        self.symbols = sorted({normalize_symbol(s) for s in symbols if s})
        self.on_price = on_price
        self.subscribe_message = subscribe_message or {}
        self.ping_interval = max(5, int(ping_interval))
        self._running = False
        self._ws = None

    async def start(self):
        """Connect and stream price updates with auto-reconnect."""
        self._running = True
        while self._running:
            try:
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    logger.info("Chainlink WS connected: %s", self.url)
                    await self._send_subscribe(ws)
                    ping_task = asyncio.create_task(self._ping_loop(ws))
                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            await self._handle_raw(raw)
                    finally:
                        ping_task.cancel()
            except websockets.ConnectionClosed:
                if self._running:
                    logger.warning("Chainlink WS disconnected, reconnecting...")
                    await asyncio.sleep(2)
            except Exception as exc:
                if self._running:
                    logger.error("Chainlink WS error: %s", exc)
                    await asyncio.sleep(5)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _send_subscribe(self, ws):
        if not self.subscribe_message:
            return
        payload = json.loads(json.dumps(self.subscribe_message))
        payload_str = json.dumps(payload)
        # Convenience token replacement if user sets "__symbols__" placeholder.
        payload_str = payload_str.replace('"__symbols__"', json.dumps(self.symbols))
        await ws.send(payload_str)

    async def _ping_loop(self, ws):
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                await ws.ping()
        except asyncio.CancelledError:
            pass

    async def _handle_raw(self, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        for symbol, price in self._extract_prices(msg):
            if self.symbols and symbol not in self.symbols:
                continue
            await self.on_price(symbol, price)

    def _extract_prices(self, msg: Any) -> list[tuple[str, float]]:
        """Extract (symbol, price) pairs from flexible JSON payloads."""
        out: list[tuple[str, float]] = []

        def walk(node: Any):
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return

            if not isinstance(node, dict):
                return

            symbol_raw = (
                node.get("symbol")
                or node.get("pair")
                or node.get("asset")
                or node.get("instrument")
                or node.get("s")
                or node.get("base")
            )
            price_raw = (
                node.get("price")
                or node.get("value")
                or node.get("p")
                or node.get("latest")
                or node.get("mid")
            )
            if symbol_raw is not None and price_raw is not None:
                symbol = normalize_symbol(str(symbol_raw))
                try:
                    price = float(price_raw)
                except (TypeError, ValueError):
                    price = 0.0
                if symbol and price > 0:
                    out.append((symbol, price))

            # Common nested payload keys.
            for key in ("data", "payload", "result", "prices", "updates", "items"):
                child = node.get(key)
                if child is not None:
                    walk(child)

            # Parse pairs embedded as strings, e.g. "BTC/USD @ 68321.4"
            text = json.dumps(node)
            pair_match = re.findall(r"([A-Z]{3,5})\s*/\s*(USD|USDT)", text)
            if pair_match and price_raw is not None:
                for base, _ in pair_match:
                    try:
                        price = float(price_raw)
                    except (TypeError, ValueError):
                        continue
                    if price > 0:
                        out.append((normalize_symbol(base), price))

        walk(msg)
        # Deduplicate by symbol keeping latest in message traversal order.
        dedup: dict[str, float] = {}
        for symbol, price in out:
            dedup[symbol] = price
        return list(dedup.items())
