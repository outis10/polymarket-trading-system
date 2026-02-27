"""Price provider factory — abstracts price source (Binance, Kraken, Chainlink).

Usage in event_manager.py:
    from .price_provider import get_price_fetcher, get_price_streamer

    fetch_prices = get_price_fetcher(source)       # fetch_prices(symbols) -> dict[str, float]
    streamer     = get_price_streamer(source, ...) # .start() / .stop()

Adding a new source:
  1. Create backend/services/<source>.py with REST + WS classes.
  2. Add an elif branch in get_price_fetcher() and get_price_streamer().
  3. Set price_source in runtime_settings.json.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported sources
# ---------------------------------------------------------------------------
SUPPORTED_SOURCES = {"binance", "kraken", "chainlink"}
DEFAULT_SOURCE = "binance"


# ---------------------------------------------------------------------------
# Protocols (structural — no ABC overhead needed)
# ---------------------------------------------------------------------------

class PriceStreamer:
    """Common interface expected by event_manager for any WS price streamer."""

    async def start(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Factory: REST price fetcher
# ---------------------------------------------------------------------------

def get_price_fetcher(source: str = DEFAULT_SOURCE) -> Callable[[list[str]], dict[str, float]]:
    """Return a callable fetch_prices(symbols: list[str]) -> dict[str, float].

    The returned function accepts Binance-style market symbols (e.g. "BTCUSDT")
    and returns a dict mapping each symbol to its current price.
    All providers normalize internally so callers stay source-agnostic.
    """
    source = (source or DEFAULT_SOURCE).lower().strip()

    if source == "binance":
        from .binance import fetch_binance_prices
        return fetch_binance_prices

    if source == "kraken":
        from .kraken import fetch_kraken_prices  # type: ignore[import]
        return fetch_kraken_prices

    if source == "chainlink":
        raise NotImplementedError(
            "Chainlink REST price fetcher not implemented. "
            "Use chainlink as a streamer source only."
        )

    logger.warning("Unknown price_source %r — falling back to binance", source)
    from .binance import fetch_binance_prices
    return fetch_binance_prices


def get_single_price_fetcher(source: str = DEFAULT_SOURCE) -> Callable[[str], Optional[float]]:
    """Return a callable fetch_price(symbol: str) -> Optional[float].

    Used as a single-symbol fallback when bulk fetch misses a symbol.
    """
    source = (source or DEFAULT_SOURCE).lower().strip()

    if source == "binance":
        from .binance import fetch_binance_price
        return fetch_binance_price

    if source == "kraken":
        from .kraken import fetch_kraken_price  # type: ignore[import]
        return fetch_kraken_price

    logger.warning("Unknown price_source %r — falling back to binance single", source)
    from .binance import fetch_binance_price
    return fetch_binance_price


# ---------------------------------------------------------------------------
# Factory: WebSocket streamer
# ---------------------------------------------------------------------------

def get_price_streamer(
    source: str,
    symbol: str,
    on_price: Callable[[str, float], Coroutine[Any, Any, None]],
    **kwargs: Any,
) -> PriceStreamer:
    """Return a PriceStreamer for the given source and symbol.

    Args:
        source:   "binance" | "kraken" | "chainlink"
        symbol:   Market symbol in Binance format (e.g. "BTCUSDT").
                  Each provider normalises internally.
        on_price: Async callback(symbol_upper, price).
        **kwargs: Forwarded to the underlying streamer constructor.
    """
    source = (source or DEFAULT_SOURCE).lower().strip()

    if source == "binance":
        from .binance import BinanceStreamer
        return BinanceStreamer(symbol=symbol, on_price=on_price, **kwargs)

    if source == "kraken":
        from .kraken import KrakenStreamer  # type: ignore[import]
        return KrakenStreamer(symbol=symbol, on_price=on_price, **kwargs)

    if source == "chainlink":
        from .chainlink import ChainlinkPriceStreamer
        # chainlink_url and subscribe_message must be in kwargs or config.
        url = kwargs.pop("url", "")
        subscribe_message = kwargs.pop("subscribe_message", {})
        symbols = [symbol]
        return ChainlinkPriceStreamer(
            url=url,
            symbols=symbols,
            on_price=on_price,
            subscribe_message=subscribe_message,
            **kwargs,
        )

    logger.warning("Unknown price_source %r — falling back to binance streamer", source)
    from .binance import BinanceStreamer
    return BinanceStreamer(symbol=symbol, on_price=on_price, **kwargs)
