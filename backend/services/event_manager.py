"""EventManager: orchestrates data updates and broadcasts via WebSocket."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import load_events_config
from ..ws.manager import manager
from .binance import (
    BinanceStreamer,
    fetch_binance_candle_open,
    fetch_binance_klines,
    fetch_binance_price,
    parse_event_start_ms,
)
from .demo import load_demo_events, update_demo_prices
from .polymarket import PolymarketStreamer, fetch_real_prices, get_client

logger = logging.getLogger(__name__)


class EventManager:
    """Singleton that manages event state and data streams."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.mode: str = "demo"
        self.settings: dict = {
            "mode": "demo",
            "refresh_rate": 5,
            "chart_options": ["show_chart", "show_probability", "show_price_change"],
        }
        self._config: dict = {}
        self._task: Optional[asyncio.Task] = None
        self._binance_streamers: list[BinanceStreamer] = []
        self._polymarket_streamers: list[PolymarketStreamer] = []
        self._running = False

    def load_config(self):
        self._config = load_events_config()

    async def start(self):
        """Start the event manager background loop."""
        self.load_config()
        self._running = True

        # Initialize with current mode
        if self.mode == "demo":
            self.events = load_demo_events(self._config)
        else:
            self.events = self._init_live_events()

        # Broadcast initial snapshot
        await self._broadcast_full_snapshot()

        # Start update loop
        self._task = asyncio.create_task(self._update_loop())

    async def stop(self):
        """Stop all streams and the update loop."""
        self._running = False
        for s in self._binance_streamers:
            await s.stop()
        for s in self._polymarket_streamers:
            await s.stop()
        self._binance_streamers.clear()
        self._polymarket_streamers.clear()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def switch_mode(self, new_mode: str):
        """Switch between demo and live mode."""
        # Stop existing streams
        for s in self._binance_streamers:
            await s.stop()
        for s in self._polymarket_streamers:
            await s.stop()
        self._binance_streamers.clear()
        self._polymarket_streamers.clear()

        self.mode = new_mode
        self.settings["mode"] = new_mode
        self.load_config()

        if new_mode == "demo":
            self.events = load_demo_events(self._config)
        else:
            self.events = self._init_live_events()

        await self._broadcast_full_snapshot()
        await manager.broadcast(
            {"type": "settings_update", "event_id": "", "data": self.settings}
        )

    async def _update_loop(self):
        """Periodic update loop."""
        while self._running:
            try:
                if self.mode == "demo":
                    self._update_demo()
                else:
                    self._update_live()

                # Broadcast all events
                await self._broadcast_full_snapshot()

                await asyncio.sleep(self.settings.get("refresh_rate", 5))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Update loop error: %s", e)
                await asyncio.sleep(5)

    def _update_demo(self):
        """Update all demo events with simulated data."""
        demo_configs = self._config.get("demo_events", [])
        for event_id, event_dict in self.events.items():
            dcfg = next(
                (
                    e
                    for e in demo_configs
                    if e["name"].lower().replace(" ", "_") == event_id
                ),
                {},
            )
            update_demo_prices(event_dict, dcfg)

    def _init_live_events(self) -> dict[str, dict]:
        """Initialize live events from config."""
        events = {}
        events_config = self._config.get("events", [])
        for event_config in events_config:
            event_id = event_config["name"].lower().replace(" ", "_")
            bsym = event_config.get("binance_symbol", "")
            est = event_config.get("event_start_time", "")

            event_end = None
            if est:
                start_ms = parse_event_start_ms(est)
                if start_ms:
                    event_end_dt = datetime.fromtimestamp(
                        start_ms / 1000, tz=timezone.utc
                    ) + timedelta(hours=1)
                    event_end = event_end_dt.isoformat()

            event_dict = {
                "name": event_config["name"],
                "description": event_config.get("description", ""),
                "icon": event_config.get("icon", "generic"),
                "price_history": [],
                "yes_price": 0.50,
                "no_price": 0.50,
                "current_price": 0,
                "price_to_beat": 0,
                "last_update": "",
                "price_change": 0,
                "volume_24h": 0,
                "condition_id": event_config.get("condition_id", ""),
                "yes_token_id": event_config.get("tokens", {}).get("yes", ""),
                "no_token_id": event_config.get("tokens", {}).get("no", ""),
                "order_book_yes": None,
                "order_book_no": None,
                "event_end_utc": event_end,
            }

            if bsym and est:
                start_ms = parse_event_start_ms(est)
                if start_ms:
                    kh = fetch_binance_klines(bsym, start_ms)
                    if kh:
                        event_dict["price_history"] = kh
                        event_dict["price_to_beat"] = kh[0]["price_to_beat"]
                        event_dict["current_price"] = kh[-1]["price"]
                    else:
                        op = fetch_binance_candle_open(bsym, start_ms)
                        if op:
                            event_dict["price_to_beat"] = op

            events[event_id] = event_dict
        return events

    def _update_live(self):
        """Update all live events (REST-based periodic update)."""
        events_config = self._config.get("events", [])
        client = get_client()

        for event_id, event_dict in self.events.items():
            ecfg = next(
                (
                    e
                    for e in events_config
                    if e["name"].lower().replace(" ", "_") == event_id
                ),
                None,
            )
            if not ecfg:
                continue

            bsym = ecfg.get("binance_symbol", "")
            if bsym:
                lp = fetch_binance_price(bsym)
                if lp:
                    old = event_dict.get("current_price", 0)
                    event_dict["current_price"] = lp
                    event_dict["price_change"] = (
                        ((lp - old) / old * 100) if old > 0 else 0
                    )

            polymarket_updated = False
            if client:
                pr = fetch_real_prices(client, ecfg)
                if pr:
                    event_dict["yes_price"] = pr["yes_price"]
                    event_dict["no_price"] = pr["no_price"]
                    if pr.get("order_book_yes"):
                        event_dict["order_book_yes"] = pr["order_book_yes"]
                    if pr.get("order_book_no"):
                        event_dict["order_book_no"] = pr["order_book_no"]
                    polymarket_updated = True

            if not polymarket_updated:
                cp = event_dict.get("current_price", 0)
                ptb = event_dict.get("price_to_beat", 0)
                if cp > 0 and ptb > 0:
                    swing = (cp - ptb) / ptb * 20
                    yes_p = max(0.01, min(0.99, 0.50 + swing))
                    event_dict["yes_price"] = yes_p
                    event_dict["no_price"] = 1 - yes_p

            event_dict["last_update"] = datetime.now(tz=timezone.utc).isoformat()

            event_end_str = event_dict.get("event_end_utc")
            candle_open = True
            if event_end_str:
                try:
                    event_end_dt = datetime.fromisoformat(event_end_str)
                    candle_open = datetime.now(tz=timezone.utc) < event_end_dt
                except Exception:
                    pass

            current_price = event_dict.get("current_price", 0)
            price_to_beat = event_dict.get("price_to_beat", 0)
            if current_price > 0 and candle_open:
                pct = (
                    ((current_price - price_to_beat) / price_to_beat * 100)
                    if price_to_beat > 0
                    else 0
                )
                history = event_dict.get("price_history", [])
                history.append(
                    {
                        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                        "price": current_price,
                        "yes_price": event_dict.get("yes_price", 0.50),
                        "no_price": event_dict.get("no_price", 0.50),
                        "percent_change": pct,
                        "price_to_beat": price_to_beat,
                    }
                )
                if len(history) > 500:
                    history = history[-500:]
                event_dict["price_history"] = history

    async def _broadcast_full_snapshot(self):
        """Send complete state to all connected clients."""
        msg = {
            "type": "full_snapshot",
            "event_id": "",
            "data": {
                "events": self.events,
                "settings": self.settings,
            },
        }
        await manager.broadcast(msg)


# Global singleton
event_manager = EventManager()
