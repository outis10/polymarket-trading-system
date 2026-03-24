"""Kraken service: REST helpers + WebSocket stream for real-time trades.

Drop-in replacement for binance.py when running on AWS EC2 (Binance blocks AWS IPs).

Symbol mapping (Binance → Kraken):
  BTCUSDT  → XBTUSD  (internal key: XXBTZUSD)
  ETHUSDT  → ETHUSD  (internal key: XETHZUSD)
  SOLUSDT  → SOLUSD
  XRPUSDT  → XRPUSD  (internal key: XXRPZUSD)

To activate: set price_source = "kraken" in runtime_settings.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

import websockets
from cachetools import TTLCache

logger = logging.getLogger(__name__)

KRAKEN_REST_API = "https://api.kraken.com/0/public"
KRAKEN_WS_V2 = "wss://ws.kraken.com/v2"

_price_cache: TTLCache = TTLCache(maxsize=64, ttl=0.5)
_candle_open_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_klines_cache: TTLCache = TTLCache(maxsize=64, ttl=30)
_volume_cache: TTLCache = TTLCache(maxsize=64, ttl=30)

# ---------------------------------------------------------------------------
# Symbol conversion helpers
# ---------------------------------------------------------------------------

# Binance-style (e.g. BTCUSDT) → Kraken pair query param (e.g. XBTUSD)
_BINANCE_TO_KRAKEN: dict[str, str] = {
    "BTCUSDT": "XBTUSD",
    "ETHUSDT": "ETHUSD",
    "SOLUSDT": "SOLUSD",
    "XRPUSDT": "XRPUSD",
}

# Kraken internal result key → Binance-style symbol (for response parsing)
_KRAKEN_KEY_TO_BINANCE: dict[str, str] = {
    "XXBTZUSD": "BTCUSDT",
    "XBTUSD": "BTCUSDT",
    "XETHZUSD": "ETHUSDT",
    "ETHUSD": "ETHUSDT",
    "SOLUSD": "SOLUSDT",
    "XXRPZUSD": "XRPUSDT",
    "XRPUSD": "XRPUSDT",
}

# Kraken WS symbol (BTC/USD) → Binance-style symbol
_KRAKEN_WS_TO_BINANCE: dict[str, str] = {
    "BTC/USD": "BTCUSDT",
    "ETH/USD": "ETHUSDT",
    "SOL/USD": "SOLUSDT",
    "XRP/USD": "XRPUSDT",
}

# Binance-style → Kraken WS symbol
_BINANCE_TO_KRAKEN_WS: dict[str, str] = {v: k for k, v in _KRAKEN_WS_TO_BINANCE.items()}


def _to_kraken_pair(binance_symbol: str) -> str:
    """Convert BTCUSDT → XBTUSD for Kraken REST."""
    return _BINANCE_TO_KRAKEN.get(binance_symbol.upper(), binance_symbol.upper())


def _to_kraken_ws_symbol(binance_symbol: str) -> str:
    """Convert BTCUSDT → BTC/USD for Kraken WS v2."""
    return _BINANCE_TO_KRAKEN_WS.get(binance_symbol.upper(), binance_symbol.upper())


def _kraken_key_to_binance(key: str) -> str:
    """Convert Kraken result key (XXBTZUSD) → BTCUSDT."""
    return _KRAKEN_KEY_TO_BINANCE.get(key.upper(), key.upper())


def _ws_symbol_to_binance(ws_symbol: str) -> str:
    """Convert BTC/USD → BTCUSDT."""
    return _KRAKEN_WS_TO_BINANCE.get(ws_symbol, ws_symbol)


# ---------------------------------------------------------------------------
# REST helpers (sync, same signature as binance.py)
# ---------------------------------------------------------------------------


def fetch_kraken_price(symbol: str) -> Optional[float]:
    """Fetch current price for a symbol (Binance-style, e.g. BTCUSDT)."""
    import requests

    cache_key = symbol.upper()
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    pair = _to_kraken_pair(symbol)
    try:
        resp = requests.get(
            f"{KRAKEN_REST_API}/Ticker",
            params={"pair": pair},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            logger.warning("Kraken ticker error for %s: %s", pair, data["error"])
            return None
        result = data.get("result", {})
        for key, ticker in result.items():
            price = float(ticker["c"][0])  # c[0] = last trade price
            _price_cache[cache_key] = price
            return price
    except Exception as exc:
        logger.debug("fetch_kraken_price(%s) failed: %s", symbol, exc)
    return None


def fetch_kraken_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch prices for multiple symbols (Binance-style).

    Returns dict keyed by Binance-style symbol (e.g. BTCUSDT → 94250.5).
    """
    import requests

    unique_symbols = sorted({s.upper() for s in symbols if s})
    if not unique_symbols:
        return {}

    if all(sym in _price_cache for sym in unique_symbols):
        return {sym: _price_cache[sym] for sym in unique_symbols}

    kraken_pairs = [_to_kraken_pair(s) for s in unique_symbols]
    pair_param = ",".join(kraken_pairs)

    try:
        resp = requests.get(
            f"{KRAKEN_REST_API}/Ticker",
            params={"pair": pair_param},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            logger.warning("Kraken bulk ticker error: %s", data["error"])
            raise ValueError(data["error"])

        result: dict[str, float] = {}
        for key, ticker in data.get("result", {}).items():
            binance_sym = _kraken_key_to_binance(key)
            if binance_sym not in unique_symbols:
                continue
            price = float(ticker["c"][0])
            _price_cache[binance_sym] = price
            result[binance_sym] = price

        # Fallback for any symbol not returned in bulk
        for sym in unique_symbols:
            if sym not in result:
                if sym in _price_cache:
                    result[sym] = _price_cache[sym]
                else:
                    p = fetch_kraken_price(sym)
                    if p is not None:
                        result[sym] = p
        return result

    except Exception as exc:
        logger.debug("fetch_kraken_prices bulk failed (%s), falling back", exc)
        out: dict[str, float] = {}
        for sym in unique_symbols:
            p = fetch_kraken_price(sym)
            if p is not None:
                out[sym] = p
        return out


def fetch_kraken_candle_open(
    symbol: str, start_time_ms: int, timeframe_minutes: int = 15
) -> Optional[float]:
    """Fetch candle open price from Kraken OHLC at event start."""
    import requests

    interval = (
        int(timeframe_minutes) if int(timeframe_minutes) in (1, 5, 15, 60) else 15
    )
    cache_key = (symbol.upper(), int(start_time_ms), interval)
    if cache_key in _candle_open_cache:
        return _candle_open_cache[cache_key]

    pair = _to_kraken_pair(symbol)
    since_sec = max(0, int(start_time_ms // 1000) - (interval * 60))
    try:
        resp = requests.get(
            f"{KRAKEN_REST_API}/OHLC",
            params={"pair": pair, "interval": interval, "since": since_sec},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return None
        result = data.get("result", {})
        rows = result.get(pair) or []
        if not rows:
            # Kraken may return a canonical pair key (e.g. XXBTZUSD).
            for key, value in result.items():
                if key != "last" and isinstance(value, list):
                    rows = value
                    if rows:
                        break
        if not rows:
            return None

        start_sec = int(start_time_ms // 1000)
        selected = None
        for row in rows:
            try:
                t0 = int(float(row[0]))
            except Exception:
                continue
            if t0 <= start_sec < (t0 + interval * 60):
                selected = row
                break
        if selected is None:
            selected = rows[0]

        price = float(selected[1])  # open
        _candle_open_cache[cache_key] = price
        return price
    except Exception:
        return None


def fetch_kraken_klines(symbol: str, start_time_ms: int) -> list[dict]:
    """Fetch 1-minute OHLC from Kraken and normalize to PriceHistoryPoint-like rows."""
    import requests

    cache_key = (symbol.upper(), int(start_time_ms))
    if cache_key in _klines_cache:
        return _klines_cache[cache_key]

    pair = _to_kraken_pair(symbol)
    since_sec = max(0, int(start_time_ms // 1000) - 60)
    try:
        resp = requests.get(
            f"{KRAKEN_REST_API}/OHLC",
            params={"pair": pair, "interval": 1, "since": since_sec},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return []
        result = data.get("result", {})
        rows = result.get(pair) or []
        if not rows:
            for key, value in result.items():
                if key != "last" and isinstance(value, list):
                    rows = value
                    if rows:
                        break
        if not rows:
            return []

        start_sec = int(start_time_ms // 1000)
        window_end = start_sec + 3600
        filtered: list[list[Any]] = []
        for row in rows:
            try:
                t0 = int(float(row[0]))
            except Exception:
                continue
            if start_sec <= t0 < window_end:
                filtered.append(row)
        if not filtered:
            return []

        open_price = float(filtered[0][1])
        history = []
        for row in filtered:
            ts = datetime.fromtimestamp(float(row[0]), tz=timezone.utc)
            close = float(row[4])
            pct = ((close - open_price) / open_price * 100) if open_price else 0.0
            prob_swing = (close - open_price) / open_price * 20 if open_price else 0.0
            yes_p = max(0.01, min(0.99, 0.50 + prob_swing))
            history.append(
                {
                    "timestamp": ts.isoformat(),
                    "price": close,
                    "yes_price": yes_p,
                    "no_price": 1 - yes_p,
                    "percent_change": pct,
                    "price_to_beat": open_price,
                }
            )
        _klines_cache[cache_key] = history
        return history
    except Exception:
        return []


def fetch_kraken_volume_1m(symbol: str) -> Optional[float]:
    """Fetch volume of the last completed 1-minute candle for a symbol.

    Kraken OHLC rows: [time, open, high, low, close, vwap, volume, count]
    Returns volume (index 6) of the most recently closed 1m candle.
    Returns None on error or when data is unavailable.
    """
    import requests

    cache_key = symbol
    if cache_key in _volume_cache:
        return _volume_cache[cache_key]
    kraken_pair = _BINANCE_TO_KRAKEN.get(symbol.upper())
    if not kraken_pair:
        return None
    try:
        resp = requests.get(
            f"{KRAKEN_REST_API}/OHLC",
            params={"pair": kraken_pair, "interval": 1},
            timeout=5,
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})
        rows = None
        for key, val in result.items():
            if key != "last" and isinstance(val, list):
                rows = val
                break
        if not rows or len(rows) < 2:
            return None
        # rows[-2] = last completed candle (rows[-1] is current/incomplete)
        vol = float(rows[-2][6])
        _volume_cache[cache_key] = vol
        return vol
    except Exception:
        return None


# ---------------------------------------------------------------------------
# WebSocket streamer (same interface as BinanceStreamer)
# ---------------------------------------------------------------------------


class KrakenStreamer:
    """Connects to Kraken WebSocket v2 for real-time trade prices.

    Exposes the same .start() / .stop() / ._running interface as BinanceStreamer
    so price_provider.py can use either transparently.
    """

    def __init__(
        self,
        symbol: str,
        on_price: Callable[[str, float], Coroutine[Any, Any, None]],
        ping_interval: int = 20,
    ):
        # Accept Binance-style symbol (BTCUSDT) and convert internally
        self.symbol = symbol.upper()
        self._ws_symbol = _to_kraken_ws_symbol(self.symbol)
        self.on_price = on_price
        self.ping_interval = max(5, int(ping_interval))
        self._ws = None
        self._running = False

    async def _ping_loop(self, ws):
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                await ws.ping()
        except asyncio.CancelledError:
            pass

    async def start(self):
        """Connect and stream trade events."""
        self._running = True
        subscribe_msg = json.dumps(
            {
                "method": "subscribe",
                "params": {
                    "channel": "trade",
                    "symbol": [self._ws_symbol],
                    "snapshot": False,
                },
            }
        )

        while self._running:
            try:
                async with websockets.connect(KRAKEN_WS_V2) as ws:
                    self._ws = ws
                    logger.info(
                        "Kraken WS connected: %s (%s)", KRAKEN_WS_V2, self._ws_symbol
                    )
                    await ws.send(subscribe_msg)
                    ping_task = asyncio.create_task(self._ping_loop(ws))
                    try:
                        async for raw in ws:
                            if not self._running:
                                break
                            try:
                                msg = json.loads(raw)
                                # Skip subscription ack and heartbeat frames
                                if msg.get("channel") != "trade":
                                    continue
                                for trade in msg.get("data", []):
                                    price = float(trade.get("price", 0))
                                    if price > 0 and self.on_price:
                                        # Emit Binance-style symbol so event_manager
                                        # doesn't need to know about the source.
                                        ws_sym = trade.get("symbol", self._ws_symbol)
                                        binance_sym = _ws_symbol_to_binance(ws_sym)
                                        await self.on_price(binance_sym, price)
                            except Exception:
                                pass
                    finally:
                        ping_task.cancel()
            except websockets.ConnectionClosed:
                if self._running:
                    logger.warning("Kraken WS disconnected, reconnecting...")
                    await asyncio.sleep(2)
            except Exception as exc:
                if self._running:
                    logger.error("Kraken WS error: %s", exc)
                    await asyncio.sleep(5)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
