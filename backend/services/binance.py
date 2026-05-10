"""Binance service: REST helpers + WebSocket stream for real-time trades/klines."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import websockets
from cachetools import TTLCache

from ..models.schemas import PriceHistoryPoint

logger = logging.getLogger(__name__)

BINANCE_API = "https://api.binance.com/api/v3"
BINANCE_WS = "wss://stream.binance.com:9443/ws"

_price_cache: TTLCache = TTLCache(maxsize=64, ttl=0.5)
_candle_open_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_klines_cache: TTLCache = TTLCache(maxsize=64, ttl=30)
_volume_cache: TTLCache = TTLCache(maxsize=64, ttl=30)


# --- REST helpers (sync, called during init) ---


def fetch_binance_price(symbol: str) -> Optional[float]:
    """Fetch current price for a Binance symbol."""
    import requests

    cache_key = symbol
    if cache_key in _price_cache:
        return _price_cache[cache_key]
    try:
        resp = requests.get(
            f"{BINANCE_API}/ticker/price", params={"symbol": symbol}, timeout=5
        )
        resp.raise_for_status()
        price = float(resp.json()["price"])
        _price_cache[cache_key] = price
        return price
    except Exception:
        return None


def fetch_binance_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch prices for multiple Binance symbols with a single REST call."""
    import requests

    unique_symbols = sorted({s for s in symbols if s})
    if not unique_symbols:
        return {}

    # If all requested symbols are still fresh in cache, return immediately.
    if all(sym in _price_cache for sym in unique_symbols):
        return {sym: _price_cache[sym] for sym in unique_symbols}

    try:
        resp = requests.get(f"{BINANCE_API}/ticker/price", timeout=5)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return {}

        all_prices: dict[str, float] = {}
        for row in rows:
            sym = row.get("symbol")
            if not sym:
                continue
            try:
                price = float(row["price"])
            except (KeyError, ValueError, TypeError):
                continue
            all_prices[sym] = price

        result: dict[str, float] = {}
        for sym in unique_symbols:
            price = all_prices.get(sym)
            if price is not None:
                _price_cache[sym] = price
                result[sym] = price
            elif sym in _price_cache:
                result[sym] = _price_cache[sym]
        return result
    except Exception:
        # Fallback to individual cached/single requests.
        out: dict[str, float] = {}
        for sym in unique_symbols:
            price = fetch_binance_price(sym)
            if price is not None:
                out[sym] = price
        return out


def fetch_binance_candle_open(
    symbol: str, start_time_ms: int, timeframe_minutes: int = 15
) -> Optional[float]:
    """Fetch the open price of the candle at the given start time and timeframe."""
    import requests

    interval_map = {1: "1m", 5: "5m", 15: "15m", 60: "1h"}
    interval = interval_map.get(int(timeframe_minutes), "15m")

    cache_key = (symbol, start_time_ms, interval)
    if cache_key in _candle_open_cache:
        return _candle_open_cache[cache_key]
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time_ms,
                "limit": 1,
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            price = float(data[0][1])
            _candle_open_cache[cache_key] = price
            return price
        return None
    except Exception:
        return None


def parse_event_start_ms(event_start_time: str) -> Optional[int]:
    """Parse ISO event_start_time string to epoch milliseconds."""
    if not event_start_time:
        return None
    try:
        dt = datetime.fromisoformat(event_start_time.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def fetch_binance_klines(symbol: str, start_time_ms: int) -> list[dict]:
    """Fetch 1-minute klines from Binance starting at the candle open."""
    import requests

    cache_key = (symbol, start_time_ms)
    if cache_key in _klines_cache:
        return _klines_cache[cache_key]
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={
                "symbol": symbol,
                "interval": "1m",
                "startTime": start_time_ms,
                "endTime": start_time_ms + 3_600_000,
                "limit": 60,
            },
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            return []

        open_price = float(raw[0][1])
        history = []
        for k in raw:
            ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
            close = float(k[4])
            pct = ((close - open_price) / open_price * 100) if open_price else 0
            prob_swing = (close - open_price) / open_price * 20 if open_price else 0
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


def fetch_binance_volatility_context(symbol: str, n: int = 10) -> dict:
    """Fetch realized volatility and shock ratio from last N completed 1m candles.

    Returns dict with:
      rv_5m: std of last 5 log-returns (percentage units, e.g. 0.05 ≈ 0.05%)
      shock_ratio: |last return| / median(|returns|), None if median ≈ 0
    Returns empty dict on error or insufficient data.
    """
    import math
    import requests

    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={"symbol": symbol, "interval": "1m", "limit": n + 2},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        # data[-1] is the current (incomplete) candle — skip it
        closes = [float(k[4]) for k in data[:-1]]
        if len(closes) < 6:
            return {}
        returns = [
            math.log(closes[i] / closes[i - 1]) * 100
            for i in range(1, len(closes))
            if closes[i - 1] > 0
        ]
        if len(returns) < 5:
            return {}
        last5 = returns[-5:]
        mean5 = sum(last5) / len(last5)
        rv_5m = math.sqrt(sum((r - mean5) ** 2 for r in last5) / len(last5))
        abs_returns = [abs(r) for r in returns]
        sorted_abs = sorted(abs_returns)
        mid = len(sorted_abs) // 2
        median_abs = (
            (sorted_abs[mid - 1] + sorted_abs[mid]) / 2
            if len(sorted_abs) % 2 == 0
            else sorted_abs[mid]
        )
        shock_ratio = (
            round(abs_returns[-1] / median_abs, 4) if median_abs > 1e-10 else None
        )
        # Efficiency Ratio: |net move| / sum of absolute moves (range 0-1)
        net_move = abs(closes[-1] - closes[0])
        total_path = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        er_14 = round(net_move / total_path, 4) if total_path > 1e-10 else None
        return {"rv_5m": round(rv_5m, 6), "shock_ratio": shock_ratio, "er_14": er_14}
    except Exception:
        return {}


def fetch_binance_volume_1m(symbol: str) -> Optional[float]:
    """Fetch USDT volume of the last completed 1-minute candle for a symbol.

    Returns quoteAssetVolume (k[7]) of the most recently closed 1m candle.
    Returns None on error or when data is unavailable.
    """
    import requests

    cache_key = symbol
    if cache_key in _volume_cache:
        return _volume_cache[cache_key]
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={"symbol": symbol, "interval": "1m", "limit": 2},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        # data[0] = last completed candle, data[1] = current (incomplete) candle
        if isinstance(data, list) and len(data) >= 1:
            vol = float(data[0][7])  # quoteAssetVolume in USDT
            _volume_cache[cache_key] = vol
            return vol
        return None
    except Exception:
        return None


# --- WebSocket stream ---


class BinanceStreamer:
    """Connects to Binance WebSocket for real-time trade prices."""

    def __init__(
        self, symbol: str, on_price: asyncio.coroutines = None, ping_interval: int = 20
    ):
        self.symbol = symbol.lower()
        self.on_price = on_price
        self.ping_interval = max(5, int(ping_interval))
        self.ping_timeout = max(10, self.ping_interval)
        self._ws = None
        self._running = False

    async def start(self):
        """Connect and stream trade events."""
        url = f"{BINANCE_WS}/{self.symbol}@trade"
        self._running = True
        while self._running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    logger.info("Binance WS connected: %s", url)
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            price = float(msg.get("p", 0))
                            if price > 0 and self.on_price:
                                await self.on_price(self.symbol.upper(), price)
                        except Exception:
                            pass
            except websockets.ConnectionClosed as exc:
                if self._running:
                    logger.warning(
                        "Binance WS disconnected for %s (%s), reconnecting...",
                        self.symbol.upper(),
                        exc,
                    )
                    await asyncio.sleep(2)
            except Exception as e:
                if self._running:
                    logger.error("Binance WS error for %s: %s", self.symbol.upper(), e)
                    await asyncio.sleep(5)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
