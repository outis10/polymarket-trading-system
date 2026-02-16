"""EventManager: orchestrates data updates and broadcasts via WebSocket."""

import asyncio
import bisect
import csv
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..config import load_events_config
from ..ws.manager import manager
from .binance import (
    BinanceStreamer,
    fetch_binance_candle_open,
    fetch_binance_klines,
    fetch_binance_price,
    fetch_binance_prices,
    parse_event_start_ms,
)
from .chainlink import (
    ChainlinkPriceStreamer,
    normalize_symbol,
)
from .demo import load_demo_events, update_demo_prices
from .event_discovery import discover_live_events
from .opportunity_tracker import OpportunityTracker
from .polymarket import PolymarketStreamer, fetch_real_prices, get_client

logger = logging.getLogger(__name__)


class EventManager:
    """Singleton that manages event state and data streams."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.mode: str = "live"
        self.settings: dict = {
            "mode": "live",
            "refresh_rate": 1,
            "timeframe_filter": "15m",
            "trading_mode": "bot",
            "chart_options": ["show_chart"],
            "kelly_enabled": True,
            "kelly_fraction": 0.25,
            "kelly_bankroll": 100.0,
            "kelly_min_edge_pct": 0.5,
            "kelly_max_bet_pct": 25.0,
            "kelly_max_event_exposure_pct": 25.0,
            "quant_gate_enabled": True,
            "quant_gate_min_sample": 120,
            "quant_gate_min_edge_pct": 4.0,
            "quant_gate_use_percentile": True,
            "quant_gate_percentile_low": 15.0,
            "quant_gate_percentile_high": 85.0,
            "quant_gate_min_price_c": 10.0,
            "quant_gate_max_price_c": 90.0,
            "monitored_tickers": ["BTC", "ETH", "SOL", "XRP"],
        }
        self._config: dict = {}
        self._task: Optional[asyncio.Task] = None
        self._binance_streamers: list[BinanceStreamer] = []
        self._binance_stream_tasks: list[asyncio.Task] = []
        self._chainlink_streamers: list[ChainlinkPriceStreamer] = []
        self._chainlink_stream_tasks: list[asyncio.Task] = []
        self._polymarket_streamers: list[PolymarketStreamer] = []
        self._polymarket_events_per_tick: int = 4
        self._polymarket_cursor: int = 0
        self._snapshot_every_n_ticks: int = 5
        self._tick_counter: int = 0
        self._live_event_configs: dict[str, dict] = {}
        # Quantitative PM probability table: {ticker: {minute: [(inf, sup, prob_up, prob_down, count)]}}
        self._pm_ranges: dict[
            str, dict[int, list[tuple[float, float, float, float, int]]]
        ] = {}
        self._live_discovery: dict = {
            "enabled": False,
            "symbols": ["BTC", "ETH", "SOL", "XRP"],
            "lookahead_days": 7,
            "refresh_seconds": 60,
            "max_events": 80,
            "require_15m": True,
            "min_minutes": 10,
            "max_minutes": 20,
        }
        self._live_pricing: dict = {
            "source": "chainlink",  # chainlink | binance
            "chainlink_stream_url": "",
            "chainlink_subscribe": {},
            "chainlink_ping_interval": 20,
        }
        self._last_discovery_refresh: datetime | None = None
        self._running = False
        tracker_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "backtest_output")
        )
        self._opportunity_tracker = OpportunityTracker(base_dir=tracker_dir)

    def load_config(self):
        self._config = load_events_config()
        live_discovery = self._config.get("live_discovery", {})
        if isinstance(live_discovery, dict):
            merged = self._live_discovery.copy()
            merged.update(live_discovery)
            self._live_discovery = merged
        live_pricing = self._config.get("live_pricing", {})
        if isinstance(live_pricing, dict):
            merged = self._live_pricing.copy()
            merged.update(live_pricing)
            self._live_pricing = merged

    def _load_pm_ranges(
        self,
    ) -> dict[str, dict[int, list[tuple[float, float, float, float, int]]]]:
        """Load and index PM quantitative probability table from CSV."""
        csv_path = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "backtest_output",
                "merged_pm_ranges_4cryptos.csv",
            )
        )
        table: dict[str, dict[int, list[tuple[float, float, float, float, int]]]] = {}
        if not os.path.exists(csv_path):
            logger.warning("PM ranges CSV not found at %s", csv_path)
            return table
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                ticker = row["ticker"].strip().upper()
                minute = int(row["minute"])
                entry = (
                    float(row["inf_range"]),
                    float(row["sup_range"]),
                    float(row["prob_up"]),
                    float(row["prob_down"]),
                    int(row["count_of_klines_inside_range"]),
                )
                table.setdefault(ticker, {}).setdefault(minute, []).append(entry)
        for ticker_data in table.values():
            for minute_list in ticker_data.values():
                minute_list.sort(key=lambda x: x[0])
        loaded = sum(len(r) for td in table.values() for r in td.values())
        logger.info(
            "PM ranges loaded: %d rows for tickers %s", loaded, list(table.keys())
        )
        return table

    def _lookup_quant_probs(
        self, ticker: str, minute: int, price_diff: float
    ) -> tuple[float, float, int] | None:
        """Lookup quantitative probabilities. Returns (prob_up, prob_down, sample_size) or None."""
        ticker_data = self._pm_ranges.get(ticker)
        if not ticker_data:
            return None
        ranges = ticker_data.get(max(1, min(14, minute)))
        if not ranges:
            return None
        idx = bisect.bisect_right([r[0] for r in ranges], price_diff) - 1
        if idx < 0:
            return None
        inf_r, sup_r, prob_up, prob_down, count = ranges[idx]
        if inf_r <= price_diff < sup_r:
            return (prob_up, prob_down, count)
        return None

    def _build_quant_histogram(
        self, ticker: str, minute: int, price_diff: float
    ) -> dict | None:
        """Build histogram payload for current ticker/minute context."""
        ticker_data = self._pm_ranges.get(ticker)
        if not ticker_data:
            return None
        minute_key = max(1, min(14, minute))
        ranges = ticker_data.get(minute_key)
        if not ranges:
            return None

        bins: list[dict] = []
        total_count = 0
        current_bin_index: int | None = None
        cumulative_before = 0
        current_count = 0

        for idx, (inf_r, sup_r, prob_up, prob_down, count) in enumerate(ranges):
            safe_count = max(0, int(count))
            bins.append(
                {
                    "inf_range": inf_r,
                    "sup_range": sup_r,
                    "prob_up": prob_up,
                    "prob_down": prob_down,
                    "count": safe_count,
                }
            )
            if current_bin_index is None and inf_r <= price_diff < sup_r:
                current_bin_index = idx
                cumulative_before = total_count
                current_count = safe_count
            total_count += safe_count

        current_percentile: float | None = None
        if total_count > 0:
            if current_bin_index is not None:
                midpoint = cumulative_before + (current_count * 0.5)
                current_percentile = (midpoint / total_count) * 100.0
            elif price_diff < ranges[0][0]:
                current_percentile = 0.0
            else:
                current_percentile = 100.0

        return {
            "ticker": ticker,
            "minute": minute_key,
            "current_diff": price_diff,
            "total_count": total_count,
            "current_bin_index": current_bin_index,
            "current_percentile": current_percentile,
            "bins": bins,
        }

    def _apply_quant_metrics(
        self, event_dict: dict, event_config: dict, now_utc: datetime
    ) -> None:
        """Update event quant probabilities + range histogram in-place."""
        event_start_str = event_dict.get("event_start_utc")
        ptb = event_dict.get("price_to_beat", 0)
        cp = event_dict.get("current_price", 0)
        if not event_start_str or ptb <= 0 or cp <= 0 or not self._pm_ranges:
            event_dict["quant_prob_up"] = None
            event_dict["quant_prob_down"] = None
            event_dict["quant_sample_size"] = None
            event_dict["quant_range_histogram"] = None
            return

        try:
            event_start_dt = datetime.fromisoformat(event_start_str)
            current_minute = max(
                1, int((now_utc - event_start_dt).total_seconds() // 60) + 1
            )
            ticker = normalize_symbol(
                str(
                    event_config.get("chainlink_symbol")
                    or event_config.get("binance_symbol", "")
                )
            )
            if not ticker:
                event_dict["quant_prob_up"] = None
                event_dict["quant_prob_down"] = None
                event_dict["quant_sample_size"] = None
                event_dict["quant_range_histogram"] = None
                return

            price_diff = cp - ptb
            quant = self._lookup_quant_probs(ticker, current_minute, price_diff)
            histogram = self._build_quant_histogram(ticker, current_minute, price_diff)

            if quant:
                event_dict["quant_prob_up"] = quant[0]
                event_dict["quant_prob_down"] = quant[1]
                event_dict["quant_sample_size"] = quant[2]
            else:
                event_dict["quant_prob_up"] = None
                event_dict["quant_prob_down"] = None
                event_dict["quant_sample_size"] = None

            event_dict["quant_range_histogram"] = histogram
        except Exception:
            event_dict["quant_prob_up"] = None
            event_dict["quant_prob_down"] = None
            event_dict["quant_sample_size"] = None
            event_dict["quant_range_histogram"] = None

    def _compute_quant_buy_gate_side(
        self,
        *,
        side: str,
        quant_prob: float | None,
        market_prob: float,
        sample_size: int | None,
        percentile: float | None,
    ) -> dict:
        settings = self.settings
        gate_enabled = bool(settings.get("quant_gate_enabled", True))
        min_sample = int(settings.get("quant_gate_min_sample", 120))
        min_edge_pct = float(settings.get("quant_gate_min_edge_pct", 4.0))
        use_percentile = bool(settings.get("quant_gate_use_percentile", True))
        percentile_low = float(settings.get("quant_gate_percentile_low", 15.0))
        percentile_high = float(settings.get("quant_gate_percentile_high", 85.0))
        min_price_c = float(settings.get("quant_gate_min_price_c", 10.0))
        max_price_c = float(settings.get("quant_gate_max_price_c", 90.0))

        reasons: list[str] = []
        edge_pct: float | None = None

        if not gate_enabled:
            return {
                "enabled": True,
                "reasons": [],
                "edge_pct": None,
                "sample_size": sample_size,
                "percentile": percentile,
            }

        if quant_prob is None:
            reasons.append("no_quant_data")
        if sample_size is None or sample_size < min_sample:
            reasons.append(f"sample<{min_sample}")

        if quant_prob is not None:
            edge_pct = (quant_prob - market_prob) * 100.0
            if edge_pct < min_edge_pct:
                reasons.append(f"edge<{min_edge_pct:.2f}%")

        price_c = market_prob * 100.0
        if price_c < min_price_c or price_c > max_price_c:
            reasons.append(f"price_outside_{min_price_c:.0f}-{max_price_c:.0f}c")

        if use_percentile:
            if percentile is None:
                reasons.append("no_percentile")
            elif percentile_low < percentile < percentile_high:
                reasons.append(
                    f"percentile_inside_{percentile_low:.0f}-{percentile_high:.0f}"
                )

        return {
            "enabled": len(reasons) == 0,
            "reasons": reasons,
            "edge_pct": edge_pct,
            "sample_size": sample_size,
            "percentile": percentile,
            "side": side,
        }

    def _apply_quant_buy_gates(self, event_dict: dict) -> None:
        histogram = event_dict.get("quant_range_histogram")
        percentile: float | None = None
        if isinstance(histogram, dict):
            raw = histogram.get("current_percentile")
            percentile = float(raw) if isinstance(raw, (float, int)) else None

        quant_prob_up = event_dict.get("quant_prob_up")
        quant_prob_down = event_dict.get("quant_prob_down")
        sample_size = event_dict.get("quant_sample_size")
        yes_price = float(event_dict.get("yes_price", 0.5) or 0.5)
        no_price = float(event_dict.get("no_price", 0.5) or 0.5)

        event_dict["quant_buy_gate"] = {
            "up": self._compute_quant_buy_gate_side(
                side="up",
                quant_prob=quant_prob_up
                if isinstance(quant_prob_up, (float, int))
                else None,
                market_prob=yes_price,
                sample_size=int(sample_size) if isinstance(sample_size, int) else None,
                percentile=percentile,
            ),
            "down": self._compute_quant_buy_gate_side(
                side="down",
                quant_prob=quant_prob_down
                if isinstance(quant_prob_down, (float, int))
                else None,
                market_prob=no_price,
                sample_size=int(sample_size) if isinstance(sample_size, int) else None,
                percentile=percentile,
            ),
        }

    def _track_opportunities_for_event(
        self, event_id: str, event_dict: dict, now_utc: datetime
    ) -> None:
        quant_gate = event_dict.get("quant_buy_gate")
        if not isinstance(quant_gate, dict):
            return
        for side in ("up", "down"):
            gate_side = quant_gate.get(side)
            self._opportunity_tracker.track_gate_transition(
                event_id=event_id,
                event_dict=event_dict,
                side=side,
                gate_side=gate_side if isinstance(gate_side, dict) else None,
                settings=self.settings,
                mode=self.mode,
                now_utc=now_utc,
            )

    async def start(self):
        """Start the event manager background loop."""
        self.load_config()
        self._pm_ranges = self._load_pm_ranges()
        self._running = True

        # Initialize with current mode
        if self.mode == "demo":
            self.events = load_demo_events(self._config)
        else:
            self.events = self._init_live_events()
            await self._sync_price_streams()

        # Broadcast initial snapshot
        await self._broadcast_full_snapshot()

        # Start update loop
        self._task = asyncio.create_task(self._update_loop())

    async def stop(self):
        """Stop all streams and the update loop."""
        self._running = False
        await self._stop_streams()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def switch_mode(self, new_mode: str):
        """Switch between demo and live mode."""
        # Stop existing streams
        await self._stop_streams()

        self.mode = new_mode
        self.settings["mode"] = new_mode
        self.load_config()

        if new_mode == "demo":
            self.events = load_demo_events(self._config)
        else:
            self.events = self._init_live_events()
            await self._sync_price_streams()

        await self._broadcast_full_snapshot()
        await manager.broadcast(
            {"type": "settings_update", "event_id": "", "data": self.settings}
        )

    async def refresh_live_events(self, force: bool = True) -> dict:
        """Manually refresh live events discovery and broadcast a new snapshot."""
        self.load_config()

        if self.mode != "live":
            return {
                "ok": False,
                "refreshed": False,
                "reason": "mode_not_live",
                "mode": self.mode,
            }

        if not self._live_discovery.get("enabled"):
            return {
                "ok": False,
                "refreshed": False,
                "reason": "live_discovery_disabled",
                "mode": self.mode,
            }

        previous_events = self.events
        old_conditions = {
            str(e.get("condition_id", "")).strip()
            for e in previous_events.values()
            if str(e.get("condition_id", "")).strip()
        }

        if force:
            new_events = self._init_live_events()
            self.events = self._merge_live_state(previous_events, new_events)
            self._last_discovery_refresh = datetime.now(tz=timezone.utc)
            await self._sync_price_streams()
            refreshed = True
        else:
            before = len(self.events)
            self._maybe_refresh_live_events()
            refreshed = len(self.events) != before

        new_conditions = {
            str(e.get("condition_id", "")).strip()
            for e in self.events.values()
            if str(e.get("condition_id", "")).strip()
        }

        await self._broadcast_full_snapshot()
        return {
            "ok": True,
            "refreshed": refreshed,
            "mode": self.mode,
            "events_count": len(self.events),
            "added": len(new_conditions - old_conditions),
            "removed": len(old_conditions - new_conditions),
            "discovery_refresh_seconds": int(
                self._live_discovery.get("refresh_seconds", 60)
            ),
        }

    async def _update_loop(self):
        """Periodic update loop."""
        while self._running:
            try:
                if self.mode == "demo":
                    self._update_demo()
                    await self._broadcast_full_snapshot()
                else:
                    self._maybe_refresh_live_events()
                    await self._update_live()
                    self._tick_counter += 1
                    # Live mode uses incremental WS updates; send full snapshots less often.
                    if self._tick_counter % self._snapshot_every_n_ticks == 0:
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
        self._live_event_configs = {}
        events_config = self._resolve_live_events_config()
        used_ids: set[str] = set()

        for event_config in events_config:
            event_id = self._build_event_id(event_config["name"], used_ids)
            used_ids.add(event_id)
            bsym = event_config.get("binance_symbol", "")
            est = event_config.get("event_start_time", "")
            eet = event_config.get("event_end_time", "")
            timeframe_minutes = self._infer_timeframe_minutes(event_config, None)

            event_end = None
            event_start = None
            if eet:
                parsed_end = parse_event_start_ms(eet)
                if parsed_end:
                    event_end = datetime.fromtimestamp(
                        parsed_end / 1000, tz=timezone.utc
                    ).isoformat()
            if est:
                parsed_start = parse_event_start_ms(est)
                if parsed_start:
                    event_start = datetime.fromtimestamp(
                        parsed_start / 1000, tz=timezone.utc
                    ).isoformat()
            if not event_end and est:
                start_ms = parse_event_start_ms(est)
                if start_ms:
                    event_end_dt = datetime.fromtimestamp(
                        start_ms / 1000, tz=timezone.utc
                    ) + timedelta(minutes=timeframe_minutes)
                    event_end = event_end_dt.isoformat()

            timeframe_minutes = self._infer_timeframe_minutes(event_config, event_end)
            timeframe_label = (
                "1h" if timeframe_minutes == 60 else f"{timeframe_minutes}m"
            )

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
                "chainlink_symbol": event_config.get("chainlink_symbol", ""),
                "yes_token_id": event_config.get("tokens", {}).get("yes", ""),
                "no_token_id": event_config.get("tokens", {}).get("no", ""),
                "order_book_yes": None,
                "order_book_no": None,
                "event_start_utc": event_start,
                "event_end_utc": event_end,
                "timeframe_minutes": timeframe_minutes,
                "timeframe_label": timeframe_label,
                "is_15m": timeframe_minutes == 15,
                "quant_prob_up": None,
                "quant_prob_down": None,
                "quant_sample_size": None,
                "quant_range_histogram": None,
                "quant_buy_gate": {
                    "up": {
                        "enabled": True,
                        "reasons": [],
                        "edge_pct": None,
                        "sample_size": None,
                        "percentile": None,
                        "side": "up",
                    },
                    "down": {
                        "enabled": True,
                        "reasons": [],
                        "edge_pct": None,
                        "sample_size": None,
                        "percentile": None,
                        "side": "down",
                    },
                },
            }

            configured_ptb = (
                event_config.get("settings", {}).get("price_to_beat")
                if isinstance(event_config.get("settings", {}), dict)
                else None
            )
            if isinstance(configured_ptb, (int, float)) and float(configured_ptb) > 0:
                event_dict["price_to_beat"] = float(configured_ptb)

            if bsym and est:
                start_ms = parse_event_start_ms(est)
                if start_ms:
                    kh = fetch_binance_klines(bsym, start_ms)
                    if kh:
                        event_dict["price_history"] = kh
                        if event_dict.get("price_to_beat", 0) <= 0:
                            event_dict["price_to_beat"] = kh[0]["price_to_beat"]
                        event_dict["current_price"] = kh[-1]["price"]
                    else:
                        op = fetch_binance_candle_open(
                            bsym, start_ms, timeframe_minutes
                        )
                        if op and event_dict.get("price_to_beat", 0) <= 0:
                            event_dict["price_to_beat"] = op

            events[event_id] = event_dict
            self._live_event_configs[event_id] = event_config

        if self._live_discovery.get("enabled"):
            self._last_discovery_refresh = datetime.now(tz=timezone.utc)
        return events

    @staticmethod
    def _infer_timeframe_minutes(event_config: dict, event_end_iso: str | None) -> int:
        explicit = event_config.get("timeframe_minutes")
        if explicit is not None:
            try:
                value = int(explicit)
                if value in (5, 15, 60):
                    return value
            except (TypeError, ValueError):
                pass

        name = str(event_config.get("name", "")).lower()
        desc = str(event_config.get("description", "")).lower()
        text = f"{name} {desc}"
        if any(k in text for k in ("5m", "5 min", "5-minute")):
            return 5
        if any(k in text for k in ("15m", "15 min", "15-minute")):
            return 15
        if any(k in text for k in ("1h", "60m", "1 hour", "hourly")):
            return 60

        est = event_config.get("event_start_time", "")
        start_ms = parse_event_start_ms(est) if est else None
        if start_ms and event_end_iso:
            try:
                end_dt = datetime.fromisoformat(event_end_iso)
                start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
                duration_min = (end_dt - start_dt).total_seconds() / 60
                if 3 <= duration_min <= 7:
                    return 5
                if 10 <= duration_min <= 20:
                    return 15
                if 50 <= duration_min <= 70:
                    return 60
            except Exception:
                pass

        if isinstance(event_config.get("is_15m"), bool) and event_config.get("is_15m"):
            return 15
        return 15

    def _resolve_live_events_config(self) -> list[dict]:
        static_events = self._config.get("events", []) or []
        if not isinstance(static_events, list):
            static_events = []

        merged: list[dict] = []
        seen: set[str] = set()
        for event_cfg in static_events:
            cid = str(event_cfg.get("condition_id", "")).strip()
            key = cid or str(event_cfg.get("name", "")).strip().lower()
            if not key or key in seen:
                continue
            merged.append(event_cfg)
            seen.add(key)

        if self._live_discovery.get("enabled"):
            try:
                discovered = discover_live_events(self._live_discovery)
                for event_cfg in discovered:
                    cid = str(event_cfg.get("condition_id", "")).strip()
                    key = cid or str(event_cfg.get("name", "")).strip().lower()
                    if not key or key in seen:
                        continue
                    merged.append(event_cfg)
                    seen.add(key)
            except Exception as exc:
                logger.error("Live discovery failed: %s", exc)

        logger.info(
            "Live events loaded: %d static + %d auto-discovered = %d total",
            len(static_events),
            max(0, len(merged) - len(static_events)),
            len(merged),
        )
        return merged

    @staticmethod
    def _build_event_id(name: str, used: set[str]) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if not base:
            base = "event"
        candidate = base
        seq = 2
        while candidate in used:
            candidate = f"{base}_{seq}"
            seq += 1
        return candidate

    def _maybe_refresh_live_events(self) -> None:
        if not self._live_discovery.get("enabled"):
            return

        refresh_seconds = int(self._live_discovery.get("refresh_seconds", 60))
        now = datetime.now(tz=timezone.utc)
        if self._last_discovery_refresh is not None:
            elapsed = (now - self._last_discovery_refresh).total_seconds()
            if elapsed < refresh_seconds:
                return

        previous_events = self.events
        old_symbols = self._live_symbols()
        self.load_config()
        new_events = self._init_live_events()
        self._last_discovery_refresh = now
        self.events = self._merge_live_state(previous_events, new_events)
        if self._live_symbols() != old_symbols:
            asyncio.create_task(self._sync_price_streams())

    async def _stop_streams(self) -> None:
        """Stop all WS streamers and their tasks."""
        for s in self._binance_streamers:
            await s.stop()
        for s in self._chainlink_streamers:
            await s.stop()
        for s in self._polymarket_streamers:
            await s.stop()
        self._binance_streamers.clear()
        self._chainlink_streamers.clear()
        self._polymarket_streamers.clear()

        for task in self._binance_stream_tasks:
            task.cancel()
        for task in self._chainlink_stream_tasks:
            task.cancel()
        self._binance_stream_tasks.clear()
        self._chainlink_stream_tasks.clear()

    def _live_symbols(self) -> set[str]:
        return {
            normalize_symbol(
                str(cfg.get("chainlink_symbol") or cfg.get("binance_symbol", ""))
            )
            for cfg in self._live_event_configs.values()
            if str(cfg.get("chainlink_symbol") or cfg.get("binance_symbol", "")).strip()
        }

    async def _sync_price_streams(self) -> None:
        """Ensure price streamers match current live symbols/source config."""
        symbols = sorted(self._live_symbols())
        if self.mode != "live" or not symbols:
            return

        # Stop any existing price streamers first.
        for s in self._chainlink_streamers:
            await s.stop()
        for s in self._binance_streamers:
            await s.stop()
        for task in self._chainlink_stream_tasks:
            task.cancel()
        for task in self._binance_stream_tasks:
            task.cancel()
        self._chainlink_streamers.clear()
        self._chainlink_stream_tasks.clear()
        self._binance_streamers.clear()
        self._binance_stream_tasks.clear()

        source = str(self._live_pricing.get("source", "chainlink")).lower()
        cl_url = str(self._live_pricing.get("chainlink_stream_url", "")).strip()
        if source == "chainlink" and cl_url:
            subscribe_message = self._live_pricing.get("chainlink_subscribe", {})
            ping_interval = int(self._live_pricing.get("chainlink_ping_interval", 20))
            streamer = ChainlinkPriceStreamer(
                url=cl_url,
                symbols=symbols,
                on_price=self._on_chainlink_price,
                subscribe_message=subscribe_message
                if isinstance(subscribe_message, dict)
                else {},
                ping_interval=ping_interval,
            )
            self._chainlink_streamers.append(streamer)
            self._chainlink_stream_tasks.append(asyncio.create_task(streamer.start()))
            logger.info("Started Chainlink WS stream for symbols: %s", symbols)
            return

        # Fallback to Binance streaming.
        for symbol in symbols:
            # Binance streamer expects market symbol format (e.g. BTCUSDT).
            market_symbol = f"{symbol}USDT"
            streamer = BinanceStreamer(
                symbol=market_symbol,
                on_price=self._on_binance_price,
            )
            self._binance_streamers.append(streamer)
            self._binance_stream_tasks.append(asyncio.create_task(streamer.start()))

        logger.info("Started Binance WS streams for symbols: %s", symbols)

    async def _on_binance_price(self, symbol: str, price: float) -> None:
        """Handle Binance tick updates and patch matching live events."""
        await self._on_reference_price(normalize_symbol(symbol), price)

    async def _on_chainlink_price(self, symbol: str, price: float) -> None:
        """Handle Chainlink tick updates and patch matching live events."""
        await self._on_reference_price(normalize_symbol(symbol), price)

    async def _on_reference_price(self, symbol: str, price: float) -> None:
        """Apply tick to all matching events and broadcast incremental update."""
        if self.mode != "live":
            return
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        for event_id, event_dict in self.events.items():
            ecfg = self._live_event_configs.get(event_id)
            if not ecfg:
                continue
            ref_symbol = normalize_symbol(
                str(ecfg.get("chainlink_symbol") or ecfg.get("binance_symbol", ""))
            )
            if ref_symbol != symbol:
                continue

            old = event_dict.get("current_price", 0)
            event_dict["current_price"] = price
            event_dict["price_change"] = ((price - old) / old * 100) if old > 0 else 0

            ptb = event_dict.get("price_to_beat", 0)
            if ptb > 0:
                swing = (price - ptb) / ptb * 20
                yes_p = max(0.01, min(0.99, 0.50 + swing))
                event_dict["yes_price"] = yes_p
                event_dict["no_price"] = 1 - yes_p

            event_dict["last_update"] = now_iso

            self._apply_quant_metrics(event_dict, ecfg, datetime.now(tz=timezone.utc))
            self._apply_quant_buy_gates(event_dict)
            self._track_opportunities_for_event(
                event_id, event_dict, datetime.now(tz=timezone.utc)
            )

            await manager.broadcast(
                {
                    "type": "price_update",
                    "event_id": event_id,
                    "data": {
                        "current_price": event_dict["current_price"],
                        "price_change": event_dict["price_change"],
                        "yes_price": event_dict["yes_price"],
                        "no_price": event_dict["no_price"],
                        "last_update": event_dict["last_update"],
                        "quant_prob_up": event_dict.get("quant_prob_up"),
                        "quant_prob_down": event_dict.get("quant_prob_down"),
                        "quant_sample_size": event_dict.get("quant_sample_size"),
                        "quant_range_histogram": event_dict.get(
                            "quant_range_histogram"
                        ),
                        "quant_buy_gate": event_dict.get("quant_buy_gate"),
                    },
                }
            )

    @staticmethod
    def _merge_live_state(
        old_events: dict[str, dict], new_events: dict[str, dict]
    ) -> dict[str, dict]:
        old_by_condition: dict[str, dict] = {}
        for old_event in old_events.values():
            cid = str(old_event.get("condition_id", "")).strip()
            if cid:
                old_by_condition[cid] = old_event

        state_fields = [
            "price_history",
            "yes_price",
            "no_price",
            "current_price",
            "price_to_beat",
            "last_update",
            "price_change",
            "volume_24h",
            "order_book_yes",
            "order_book_no",
        ]

        merged: dict[str, dict] = {}
        for event_id, new_event in new_events.items():
            old_event = old_by_condition.get(
                str(new_event.get("condition_id", "")).strip()
            )
            if old_event:
                for field in state_fields:
                    if field in old_event:
                        new_event[field] = old_event[field]
            merged[event_id] = new_event
        return merged

    async def _update_live(self):
        """Update all live events (REST-based periodic update)."""
        client = get_client()
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        event_ids = list(self.events.keys())
        append_history_this_tick = (self._tick_counter % 5) == 0

        symbols = []
        for event_id in event_ids:
            ecfg = self._live_event_configs.get(event_id)
            if not ecfg:
                continue
            ref = normalize_symbol(
                str(ecfg.get("chainlink_symbol") or ecfg.get("binance_symbol", ""))
            )
            if ref:
                symbols.append(ref)
        use_polling_prices = (
            not self._binance_streamers and not self._chainlink_streamers
        )
        market_symbols = [f"{s}USDT" for s in symbols]
        prices_by_symbol = (
            fetch_binance_prices(market_symbols) if use_polling_prices else {}
        )

        # 1) Fast path every tick: update Binance current_price for all events.
        for event_id in event_ids:
            event_dict = self.events[event_id]
            ecfg = self._live_event_configs.get(event_id)
            if not ecfg:
                continue

            bsym = str(ecfg.get("binance_symbol", ""))
            ref_symbol = normalize_symbol(
                str(ecfg.get("chainlink_symbol") or ecfg.get("binance_symbol", ""))
            )
            market_symbol = bsym or (f"{ref_symbol}USDT" if ref_symbol else "")
            if market_symbol and use_polling_prices:
                lp = prices_by_symbol.get(market_symbol)
                if lp is None:
                    lp = fetch_binance_price(market_symbol)
                if lp:
                    old = event_dict.get("current_price", 0)
                    event_dict["current_price"] = lp
                    event_dict["price_change"] = (
                        ((lp - old) / old * 100) if old > 0 else 0
                    )

            cp = event_dict.get("current_price", 0)
            ptb = event_dict.get("price_to_beat", 0)
            if cp > 0 and ptb > 0:
                swing = (cp - ptb) / ptb * 20
                yes_p = max(0.01, min(0.99, 0.50 + swing))
                event_dict["yes_price"] = yes_p
                event_dict["no_price"] = 1 - yes_p

            event_dict["last_update"] = now_iso
            self._apply_quant_metrics(event_dict, ecfg, datetime.now(tz=timezone.utc))
            self._apply_quant_buy_gates(event_dict)
            self._track_opportunities_for_event(
                event_id, event_dict, datetime.now(tz=timezone.utc)
            )
            await manager.broadcast(
                {
                    "type": "quant_metrics_update",
                    "event_id": event_id,
                    "data": {
                        "quant_prob_up": event_dict.get("quant_prob_up"),
                        "quant_prob_down": event_dict.get("quant_prob_down"),
                        "quant_sample_size": event_dict.get("quant_sample_size"),
                        "quant_range_histogram": event_dict.get(
                            "quant_range_histogram"
                        ),
                        "quant_buy_gate": event_dict.get("quant_buy_gate"),
                    },
                }
            )

            event_end_str = event_dict.get("event_end_utc")
            candle_open = True
            if event_end_str:
                try:
                    event_end_dt = datetime.fromisoformat(event_end_str)
                    candle_open = datetime.now(tz=timezone.utc) < event_end_dt
                except Exception:
                    pass

            if cp > 0 and candle_open and append_history_this_tick:
                pct = ((cp - ptb) / ptb * 100) if ptb > 0 else 0
                history = event_dict.get("price_history", [])
                history.append(
                    {
                        "timestamp": now_iso,
                        "price": cp,
                        "yes_price": event_dict.get("yes_price", 0.50),
                        "no_price": event_dict.get("no_price", 0.50),
                        "percent_change": pct,
                        "price_to_beat": ptb,
                    }
                )
                if len(history) > 500:
                    history = history[-500:]
                event_dict["price_history"] = history

        self._opportunity_tracker.resolve_closed_events(
            self.events, datetime.now(tz=timezone.utc)
        )

        # 2) Slow path in round-robin: refresh Polymarket books/prices for a subset.
        if not client or not event_ids:
            return

        n = len(event_ids)
        step = max(1, min(self._polymarket_events_per_tick, n))
        start = self._polymarket_cursor % n
        selected_ids = [event_ids[(start + i) % n] for i in range(step)]
        self._polymarket_cursor = (start + step) % n

        for event_id in selected_ids:
            event_dict = self.events[event_id]
            ecfg = self._live_event_configs.get(event_id)
            if not ecfg:
                continue

            pr = fetch_real_prices(client, ecfg)
            if pr:
                event_dict["yes_price"] = pr["yes_price"]
                event_dict["no_price"] = pr["no_price"]
                if pr.get("order_book_yes"):
                    event_dict["order_book_yes"] = pr["order_book_yes"]
                if pr.get("order_book_no"):
                    event_dict["order_book_no"] = pr["order_book_no"]

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
