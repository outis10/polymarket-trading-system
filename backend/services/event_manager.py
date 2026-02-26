"""EventManager: orchestrates data updates and broadcasts via WebSocket."""

import asyncio
import bisect
import csv
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

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

_BOT_ORDERS_LOG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backtest_output")
)
_BOT_ORDERS_FIELDNAMES = [
    "placed_at_utc",
    "event_id",
    "ticker",
    "side",
    "token_id",
    "shares",
    "price",
    "notional_usd",
    "order_id",
    "quant_prob",
    "edge_pct",
    "price_source_at_send",
    "price_to_beat_at_send",
    "current_price_at_send",
    "diff_vs_ptb_at_send",
    "best_bid_at_send",
    "best_ask_at_send",
    "mid_at_send",
    "spread_at_send",
    "spread_pct_at_send",
    "fill_price_real",
    "edge_at_fill_pct",
    "kelly_pct",
    "bankroll_usd",
    "percentile_at_signal",
    "status",
]
_PAPER_TRADES_LOG_PATH = os.path.normpath(
    os.path.join(_BOT_ORDERS_LOG_DIR, "paper_trades.csv")
)
_PAPER_FEE_PCT_DEFAULT = 2.0
_PAPER_SLIPPAGE_BUFFER_PCT_DEFAULT = 3.0
_PAPER_TRADES_FIELDNAMES = [
    "decision_id",
    "decision_time",
    "event_id",
    "ticker",
    "event_end_utc",
    "price_to_beat_at_decision",
    "current_price_at_decision",
    "diff_vs_ptb_at_decision",
    "close_price_at_resolution",
    "stake_usd",
    "shares_simulated",
    "slot",
    "range",
    "prob_up",
    "marketProb_at_decision",
    "price_source_at_decision",
    "best_bid_at_decision",
    "best_ask_at_decision",
    "mid_at_decision",
    "spread_at_decision",
    "spread_pct_at_decision",
    "fill_price_real",
    "QuantumEdge",
    "edge_at_fill_pct",
    "friction_cost_usd",
    "pnl_sim_adjusted",
    "fee_pct_used",
    "slippage_buffer_pct_used",
    "side_taken",
    "event_outcome_real",
    "pnl_simulated",
    "status",
]


def _bot_orders_log_path() -> str:
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(_BOT_ORDERS_LOG_DIR, f"bot_orders_{date_str}.csv")


def _append_bot_order_log(row: dict) -> None:
    path = _bot_orders_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file_exists = os.path.exists(path)
    if file_exists:
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                existing_fields = reader.fieldnames or []
                if existing_fields != _BOT_ORDERS_FIELDNAMES:
                    # Migrate in-place to the latest schema to avoid malformed rows.
                    existing_rows = list(reader)
                    tmp_path = f"{path}.tmp"
                    with open(tmp_path, "w", newline="") as wf:
                        writer = csv.DictWriter(wf, fieldnames=_BOT_ORDERS_FIELDNAMES)
                        writer.writeheader()
                        for old_row in existing_rows:
                            writer.writerow(
                                {
                                    key: old_row.get(key, "")
                                    for key in _BOT_ORDERS_FIELDNAMES
                                }
                            )
                    os.replace(tmp_path, path)
        except Exception as exc:
            logger.warning(
                "Could not migrate bot orders log schema for %s: %s", path, exc
            )
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_BOT_ORDERS_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in _BOT_ORDERS_FIELDNAMES})


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_fill_price_from_result(result: Any) -> float | None:
    """Best-effort extraction of real fill/avg price from order response."""
    if result is None:
        return None

    # Object-like response -> dict-like view.
    if not isinstance(result, dict):
        obj_dict = getattr(result, "__dict__", None)
        if isinstance(obj_dict, dict):
            result = obj_dict
        else:
            return None

    # 1) Prefer explicit avg/fill fields.
    preferred_keys = [
        "filled_price",
        "fill_price",
        "avg_price",
        "average_price",
        "executed_price",
        "execution_price",
        "price_per_share",
    ]
    for key in preferred_keys:
        price = _as_float(result.get(key))
        if price is not None and price > 0:
            return price

    # 2) Look for fills list and compute weighted average.
    fills = result.get("fills")
    if isinstance(fills, list) and fills:
        weighted_num = 0.0
        weighted_den = 0.0
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            p = _as_float(
                fill.get("price")
                or fill.get("fill_price")
                or fill.get("executed_price")
            )
            # size/shares fallback priority
            q = _as_float(
                fill.get("size")
                or fill.get("shares")
                or fill.get("quantity")
                or fill.get("filled_size")
            )
            if p is None or p <= 0:
                continue
            if q is None or q <= 0:
                # If quantity is missing, treat as 1 unit.
                q = 1.0
            weighted_num += p * q
            weighted_den += q
        if weighted_den > 0:
            return weighted_num / weighted_den

    # 3) Nested common containers.
    for nested_key in ("data", "result", "order", "fill"):
        nested = result.get(nested_key)
        if isinstance(nested, dict):
            nested_price = _extract_fill_price_from_result(nested)
            if nested_price is not None:
                return nested_price

    # 4) Last resort: plain "price" from result payload.
    plain_price = _as_float(result.get("price"))
    if plain_price is not None and plain_price > 0:
        return plain_price

    return None


def _ensure_paper_trades_csv() -> None:
    os.makedirs(os.path.dirname(_PAPER_TRADES_LOG_PATH), exist_ok=True)
    if os.path.exists(_PAPER_TRADES_LOG_PATH):
        try:
            with open(_PAPER_TRADES_LOG_PATH, newline="") as f:
                reader = csv.DictReader(f)
                existing_fields = reader.fieldnames or []
                if existing_fields != _PAPER_TRADES_FIELDNAMES:
                    existing_rows = list(reader)
                    tmp_path = f"{_PAPER_TRADES_LOG_PATH}.tmp"
                    with open(tmp_path, "w", newline="") as wf:
                        writer = csv.DictWriter(wf, fieldnames=_PAPER_TRADES_FIELDNAMES)
                        writer.writeheader()
                        for old_row in existing_rows:
                            writer.writerow(
                                {
                                    key: old_row.get(key, "")
                                    for key in _PAPER_TRADES_FIELDNAMES
                                }
                            )
                    os.replace(tmp_path, _PAPER_TRADES_LOG_PATH)
        except Exception as exc:
            logger.warning(
                "Could not migrate paper trades log schema for %s: %s",
                _PAPER_TRADES_LOG_PATH,
                exc,
            )
        return
    with open(_PAPER_TRADES_LOG_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PAPER_TRADES_FIELDNAMES)
        writer.writeheader()


class EventManager:
    """Singleton that manages event state and data streams."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.mode: str = "live"
        self.settings: dict = {
            "mode": "live",
            "refresh_rate": 1,
            "timeframe_filter": "5m",
            "trading_mode": "bot",
            "chart_options": ["show_chart"],
            "kelly_enabled": True,
            "kelly_fraction": 0.25,
            "kelly_bankroll": 100.0,
            "kelly_live_bankroll_usd": 100.0,
            "kelly_paper_bankroll_usd": 100.0,
            "paper_compound_enabled": True,
            "paper_current_bankroll_usd": 100.0,
            "live_equity_start_bankroll_usd": 0.0,
            "live_equity_start_at_utc": "",
            "kelly_min_edge_pct": 0.5,
            "kelly_max_bet_pct": 25.0,
            "kelly_max_event_exposure_pct": 25.0,
            "quant_gate_enabled": True,
            "quant_gate_min_sample": 120,
            "quant_gate_min_edge_pct": 4.0,
            "quant_gate_min_diff_pct": 0.0,
            "quant_gate_use_percentile": True,
            "quant_gate_percentile_low": 15.0,
            "quant_gate_percentile_high": 85.0,
            "quant_gate_min_price_c": 10.0,
            "quant_gate_max_price_c": 90.0,
            "quant_gate_edge_vs_ask_enabled": False,
            "quant_gate_min_edge_vs_ask_pct": 2.0,
            "quant_gate_min_prob": 0.0,
            "quant_gate_min_sample_strong_signal": 20,
            "quant_gate_strong_signal_threshold": 0.72,
            "early_window_enabled": True,
            "early_window_start": 20,
            "early_window_end": 120,
            "early_quant_gate_min_sample": 90,
            "early_quant_gate_min_edge_pct": 4.0,
            "early_quant_gate_edge_vs_ask_enabled": False,
            "early_quant_gate_min_edge_vs_ask_pct": 2.0,
            "early_quant_gate_min_prob": 0.0,
            "early_quant_gate_min_diff_pct": 0.0,
            "late_window_enabled": True,
            "late_window_start": 180,
            "late_window_end": 280,
            "late_quant_gate_min_sample": 70,
            "late_quant_gate_min_edge_pct": 3.0,
            "late_quant_gate_edge_vs_ask_enabled": False,
            "late_quant_gate_min_edge_vs_ask_pct": 1.0,
            "late_quant_gate_min_prob": 0.0,
            "late_quant_gate_min_diff_pct": 0.0,
            "monitored_tickers": ["BTC", "ETH", "SOL", "XRP"],
            "bot_risk_enabled": True,
            "bot_max_buys_per_event_side": 1,
            "bot_cooldown_seconds_per_event_side": 60,
            "bot_global_min_seconds_between_orders": 2,
            "bot_max_event_exposure_pct": 15.0,
            "bot_max_ticker_exposure_pct": 25.0,
            "bot_order_notional_cap_usd": 5.0,
            "bot_paper_mode": False,
            "pm_min_shares": 5.0,
            "pm_min_notional_usd": 1.0,
            "order_book_max_levels": 8,
            "order_book_min_broadcast_ms": 120,
            "bot_enforce_timeframe_filter": True,
            "bot_block_opposite_side": True,
            "bot_min_seconds_before_end": 30,
        }
        self._config: dict = {}
        self._task: Optional[asyncio.Task] = None
        self._binance_streamers: list[BinanceStreamer] = []
        self._binance_stream_tasks: list[asyncio.Task] = []
        self._chainlink_streamers: list[ChainlinkPriceStreamer] = []
        self._chainlink_stream_tasks: list[asyncio.Task] = []
        self._polymarket_streamers: list[PolymarketStreamer] = []
        self._polymarket_stream_tasks: list[asyncio.Task] = []
        self._polymarket_asset_map: dict[str, tuple[str, str]] = {}
        self._polymarket_events_per_tick: int = 4
        self._polymarket_cursor: int = 0
        self._snapshot_every_n_ticks: int = 5
        self._tick_counter: int = 0
        self._orderbook_last_emit_ms: dict[tuple[str, str], int] = {}
        self._live_event_configs: dict[str, dict] = {}
        # Quantitative PM probability table: {ticker: {minute: [(inf, sup, prob_up, prob_down, count)]}}
        self._pm_ranges: dict[
            str, dict[int, list[tuple[float, float, float, float, int]]]
        ] = {}
        # 5m slot table (e.g. 10s slots): {ticker: {slot: [(inf, sup, prob_up, prob_down, count)]}}
        self._pm_5m_slot_ranges: dict[
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
        self._last_price_tick_at: datetime | None = (
            None  # last time _on_reference_price fired
        )
        self._streamer_stall_logged_at: datetime | None = (
            None  # throttle stall warning logs
        )
        self._price_broadcast_last_ms: dict[
            str, int
        ] = {}  # throttle price broadcasts per event
        self._order_guard_records: list[dict] = (
            self._load_order_guard_records_from_csv()
        )
        self._last_order_at_utc: datetime | None = None
        # Bot auto-order: track previous gate state to detect disabled→enabled transitions
        self._bot_prev_gate_enabled: dict[tuple[str, str], bool] = {}
        self._bot_pending_orders: set[tuple[str, str]] = set()
        # Position tracker: fuente de verdad para shares compradas por evento
        # {event_id: {"up": {"shares": float, "avg_price": float, "token_id": str, "placed_at_utc": str}, ...}}
        self._position_tracker: dict[str, dict] = {}
        tracker_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "backtest_output")
        )
        self._opportunity_tracker = OpportunityTracker(base_dir=tracker_dir)
        self._runtime_settings_path = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "config", "runtime_settings.json"
            )
        )
        self._persisted_setting_keys = set(self.settings.keys())
        self._last_paper_reconcile_at: datetime | None = None
        self._paper_event_cache: dict[str, dict[str, Any]] = {}

    def _load_order_guard_records_from_csv(self) -> list[dict]:
        """Seed _order_guard_records from today's bot_orders CSV so guards survive restarts."""
        records = []
        try:
            today_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
            csv_path = os.path.normpath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "..",
                    "backtest_output",
                    f"bot_orders_{today_str}.csv",
                )
            )
            if not os.path.exists(csv_path):
                return records
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") != "placed":
                        continue
                    try:
                        at_utc = datetime.fromisoformat(row["placed_at_utc"])
                        records.append(
                            {
                                "at_utc": at_utc,
                                "event_id": row.get("event_id", ""),
                                "ticker": row.get("ticker", ""),
                                "outcome": row.get("side", "").lower(),
                                "notional_usd": float(row.get("notional_usd", 0) or 0),
                            }
                        )
                    except Exception:
                        continue
            logger.info("Loaded %d order guard records from %s", len(records), csv_path)
        except Exception as e:
            logger.warning("Could not load order guard records from CSV: %s", e)
        return records

    def _load_runtime_settings(self) -> None:
        """Load persisted runtime mode/settings from disk, if available."""
        path = self._runtime_settings_path
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning("Could not read runtime settings from %s: %s", path, exc)
            return

        if not isinstance(payload, dict):
            return

        persisted_mode = str(payload.get("mode", "")).strip().lower()
        if persisted_mode in {"live", "demo"}:
            self.mode = persisted_mode
            self.settings["mode"] = persisted_mode

        persisted_settings = payload.get("settings")
        if isinstance(persisted_settings, dict):
            for key, value in persisted_settings.items():
                if key in self._persisted_setting_keys:
                    self.settings[key] = value
            # Backward-compat migration for old runtime_settings.json files.
            if (
                "kelly_bankroll" in persisted_settings
                and "kelly_live_bankroll_usd" not in persisted_settings
            ):
                self.settings["kelly_live_bankroll_usd"] = float(
                    persisted_settings.get("kelly_bankroll", 100.0) or 100.0
                )
            if (
                "kelly_bankroll" in persisted_settings
                and "kelly_paper_bankroll_usd" not in persisted_settings
            ):
                self.settings["kelly_paper_bankroll_usd"] = float(
                    persisted_settings.get("kelly_bankroll", 100.0) or 100.0
                )
            if (
                "kelly_paper_bankroll_usd" in persisted_settings
                and "paper_current_bankroll_usd" not in persisted_settings
            ):
                self.settings["paper_current_bankroll_usd"] = float(
                    persisted_settings.get("kelly_paper_bankroll_usd", 100.0) or 100.0
                )
            self.settings["mode"] = self.mode

    def _get_live_manual_bankroll_usd(self) -> float:
        live = self.settings.get("kelly_live_bankroll_usd")
        if isinstance(live, (int, float)) and float(live) > 0:
            return float(live)
        legacy = self.settings.get("kelly_bankroll", 100.0)
        return max(1.0, float(legacy) if isinstance(legacy, (int, float)) else 100.0)

    def _get_paper_manual_bankroll_usd(self) -> float:
        paper = self.settings.get("kelly_paper_bankroll_usd")
        if isinstance(paper, (int, float)) and float(paper) > 0:
            return float(paper)
        return self._get_live_manual_bankroll_usd()

    def _get_paper_effective_bankroll_usd(self) -> float:
        base = self._get_paper_manual_bankroll_usd()
        if not bool(self.settings.get("paper_compound_enabled", True)):
            return base
        current = self.settings.get("paper_current_bankroll_usd")
        if isinstance(current, (int, float)) and float(current) > 0:
            return float(current)
        self.settings["paper_current_bankroll_usd"] = base
        return base

    def persist_runtime_settings(self) -> None:
        """Persist current runtime mode/settings for restart continuity."""
        os.makedirs(os.path.dirname(self._runtime_settings_path), exist_ok=True)
        payload = {
            "mode": self.mode,
            "settings": {
                key: self.settings.get(key)
                for key in sorted(self._persisted_setting_keys)
            },
            "updated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            with open(self._runtime_settings_path, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
        except Exception as exc:
            logger.warning(
                "Could not persist runtime settings to %s: %s",
                self._runtime_settings_path,
                exc,
            )

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

    def _load_pm_5m_slot_ranges(
        self,
    ) -> dict[str, dict[int, list[tuple[float, float, float, float, int]]]]:
        """Load and index PM quantitative table for 5m slot-based model."""
        csv_path = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "backtest_output",
                "merged_pm_5m_slot_ranges_4cryptos.csv",
            )
        )
        table: dict[str, dict[int, list[tuple[float, float, float, float, int]]]] = {}
        if not os.path.exists(csv_path):
            logger.info("5m slot ranges CSV not found at %s (optional)", csv_path)
            return table
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                ticker = str(row.get("ticker", "")).strip().upper()
                if not ticker:
                    continue
                slot = int(row["slot"])
                entry = (
                    float(row["inf_range"]),
                    float(row["sup_range"]),
                    float(row["prob_up"]),
                    float(row["prob_down"]),
                    int(row["count_of_klines_inside_range"]),
                )
                table.setdefault(ticker, {}).setdefault(slot, []).append(entry)
        for ticker_data in table.values():
            for slot_list in ticker_data.values():
                slot_list.sort(key=lambda x: x[0])
        loaded = sum(len(r) for td in table.values() for r in td.values())
        logger.info(
            "PM 5m slot ranges loaded: %d rows for tickers %s",
            loaded,
            list(table.keys()),
        )
        return table

    def reload_quant_ranges(self) -> dict:
        """Hot-reload both PM range tables from disk. Safe to call while running."""
        try:
            new_ranges = self._load_pm_ranges()
            new_5m = self._load_pm_5m_slot_ranges()
            self._pm_ranges = new_ranges
            self._pm_5m_slot_ranges = new_5m
            tickers_ranges = list(new_ranges.keys())
            tickers_5m = list(new_5m.keys())
            logger.info(
                "Quant ranges hot-reloaded: ranges=%s 5m_slots=%s",
                tickers_ranges,
                tickers_5m,
            )
            return {
                "ok": True,
                "ranges_tickers": tickers_ranges,
                "slot_ranges_tickers": tickers_5m,
            }
        except Exception as exc:
            logger.exception("Failed to hot-reload quant ranges: %s", exc)
            return {"ok": False, "error": str(exc)}

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
            # price_diff below all known ranges → clamp to first bin
            inf_r, sup_r, prob_up, prob_down, count = ranges[0]
            return (prob_up, prob_down, count)
        if idx >= len(ranges):
            idx = len(ranges) - 1
        inf_r, sup_r, prob_up, prob_down, count = ranges[idx]
        if inf_r <= price_diff < sup_r:
            return (prob_up, prob_down, count)
        # price_diff above all known ranges → clamp to last bin
        if idx == len(ranges) - 1:
            return (prob_up, prob_down, count)
        return None

    def _lookup_quant_probs_5m_slot(
        self, ticker: str, slot: int, price_diff: float
    ) -> tuple[float, float, int] | None:
        """Lookup 5m slot-model probabilities. Returns (prob_up, prob_down, sample_size) or None."""
        ticker_data = self._pm_5m_slot_ranges.get(ticker)
        if not ticker_data:
            return None
        max_slot = max(ticker_data.keys())
        slot_key = max(1, min(max_slot, int(slot)))
        ranges = ticker_data.get(slot_key)
        if not ranges:
            return None
        idx = bisect.bisect_right([r[0] for r in ranges], price_diff) - 1
        if idx < 0:
            # price_diff below all known ranges → clamp to first bin
            inf_r, sup_r, prob_up, prob_down, count = ranges[0]
            return (prob_up, prob_down, count)
        if idx >= len(ranges):
            idx = len(ranges) - 1
        inf_r, sup_r, prob_up, prob_down, count = ranges[idx]
        if inf_r <= price_diff < sup_r:
            return (prob_up, prob_down, count)
        # price_diff above all known ranges → clamp to last bin
        if idx == len(ranges) - 1:
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

    def _build_quant_histogram_5m_slot(
        self, ticker: str, slot: int, price_diff: float
    ) -> dict | None:
        """Build histogram payload for current ticker/slot context (5m slot model)."""
        ticker_data = self._pm_5m_slot_ranges.get(ticker)
        if not ticker_data:
            return None
        max_slot = max(ticker_data.keys())
        slot_key = max(1, min(max_slot, int(slot)))
        ranges = ticker_data.get(slot_key)
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

        slot_seconds = max(1, int(300 / max_slot))
        minute_approx = max(1, min(5, int(((slot_key - 1) * slot_seconds) // 60) + 1))
        return {
            "ticker": ticker,
            "minute": minute_approx,
            "slot": slot_key,
            "slot_seconds": slot_seconds,
            "bucket_type": "slot_5m",
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
        if (
            not event_start_str
            or ptb <= 0
            or cp <= 0
            or (not self._pm_ranges and not self._pm_5m_slot_ranges)
        ):
            event_dict["quant_prob_up"] = None
            event_dict["quant_prob_down"] = None
            event_dict["quant_sample_size"] = None
            event_dict["quant_range_histogram"] = None
            event_dict["quant_source"] = None
            return

        try:
            event_start_dt = datetime.fromisoformat(event_start_str)
            elapsed_seconds = max(0, int((now_utc - event_start_dt).total_seconds()))
            current_minute = max(1, int(elapsed_seconds // 60) + 1)
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
                event_dict["quant_source"] = None
                return

            price_diff = cp - ptb
            timeframe_minutes = int(event_dict.get("timeframe_minutes", 15) or 15)
            use_5m_slot_model = (
                timeframe_minutes == 5 and ticker in self._pm_5m_slot_ranges
            )
            if use_5m_slot_model:
                max_slot = max(self._pm_5m_slot_ranges[ticker].keys())
                slot_seconds = max(1, int(300 / max_slot))
                current_slot = max(
                    1, min(max_slot, int(elapsed_seconds // slot_seconds) + 1)
                )
                quant = self._lookup_quant_probs_5m_slot(
                    ticker, current_slot, price_diff
                )
                histogram = self._build_quant_histogram_5m_slot(
                    ticker, current_slot, price_diff
                )
                event_dict["quant_source"] = "pm_5m_slot_ranges"
            else:
                quant = self._lookup_quant_probs(ticker, current_minute, price_diff)
                histogram = self._build_quant_histogram(
                    ticker, current_minute, price_diff
                )
                event_dict["quant_source"] = "pm_15m_minute_ranges"

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
            event_dict["quant_source"] = None

    def _compute_quant_buy_gate_side(
        self,
        *,
        side: str,
        quant_prob: float | None,
        market_prob: float,
        ask_price: float | None,
        ask_is_proxy: bool = False,
        sample_size: int | None,
        percentile: float | None,
        gate_params: dict | None = None,
        price_diff_abs: float | None = None,
        price_diff_pct: float | None = None,
        window_profile: str = "base",
    ) -> dict:
        settings = self.settings
        gp = gate_params or {}
        gate_enabled = bool(
            gp.get("gate_enabled", settings.get("quant_gate_enabled", True))
        )
        min_sample = int(
            gp.get("min_sample", settings.get("quant_gate_min_sample", 120))
        )
        min_edge_pct = float(
            gp.get("min_edge_pct", settings.get("quant_gate_min_edge_pct", 4.0))
        )
        use_percentile = bool(
            gp.get("use_percentile", settings.get("quant_gate_use_percentile", True))
        )
        percentile_low = float(
            gp.get("percentile_low", settings.get("quant_gate_percentile_low", 15.0))
        )
        percentile_high = float(
            gp.get("percentile_high", settings.get("quant_gate_percentile_high", 85.0))
        )
        min_price_c = float(
            gp.get("min_price_c", settings.get("quant_gate_min_price_c", 10.0))
        )
        max_price_c = float(
            gp.get("max_price_c", settings.get("quant_gate_max_price_c", 90.0))
        )
        edge_vs_ask_enabled = bool(
            gp.get(
                "edge_vs_ask_enabled",
                settings.get("quant_gate_edge_vs_ask_enabled", False),
            )
        )
        min_edge_vs_ask_pct = float(
            gp.get(
                "min_edge_vs_ask_pct",
                settings.get("quant_gate_min_edge_vs_ask_pct", 2.0),
            )
        )
        min_prob = float(gp.get("min_prob", settings.get("quant_gate_min_prob", 0.0)))
        min_diff_pct = float(gp.get("min_diff_pct", 0.0))
        min_sample_strong = int(settings.get("quant_gate_min_sample_strong_signal", 20))
        strong_signal_threshold = float(
            settings.get("quant_gate_strong_signal_threshold", 0.72)
        )

        reasons: list[str] = []
        edge_pct: float | None = None
        edge_vs_ask_pct: float | None = None

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
        else:
            if quant_prob < min_prob:
                reasons.append(f"prob<{min_prob:.2f}")

        # Strong-signal override: if quant_prob is high-confidence, use lower sample floor
        is_strong_signal = (
            quant_prob is not None and quant_prob >= strong_signal_threshold
        )
        effective_min_sample = min_sample_strong if is_strong_signal else min_sample
        if sample_size is None or sample_size < effective_min_sample:
            reasons.append(f"sample<{effective_min_sample}")
        # min_diff_pct: ticker-agnostic filter — |current_price - price_to_beat| / price_to_beat * 100
        # Replaces min_abs_diff_usd which discriminated against low-price tickers (ETH/SOL/XRP).
        # Example: BTC $27 diff on $67800 PTB = 0.04%; ETH $0.44 on $1964 PTB = 0.022%
        if min_diff_pct > 0:
            if price_diff_pct is None or price_diff_pct < min_diff_pct:
                reasons.append(f"diff_pct<{min_diff_pct:.3f}%")

        if quant_prob is not None:
            # edge_pct: informational — quant advantage vs mid-market
            edge_pct = (quant_prob - market_prob) * 100.0
            # edge_vs_ask_pct: quant advantage vs actual cost to buy (ask)
            if ask_price is not None and ask_price > 0:
                edge_vs_ask_pct = (quant_prob - ask_price) * 100.0
            # Primary edge check: use edge_vs_ask when ask is real, fallback to edge_pct when proxy
            effective_edge = edge_vs_ask_pct if not ask_is_proxy else edge_pct
            if effective_edge is None or effective_edge < min_edge_pct:
                reasons.append(f"edge<{min_edge_pct:.2f}%")
            # Optional secondary filter: explicit edge_vs_ask check (requires real ask)
            if edge_vs_ask_enabled:
                if ask_is_proxy or ask_price is None or ask_price <= 0:
                    reasons.append("no_ask_price")
                elif (
                    edge_vs_ask_pct is not None
                    and edge_vs_ask_pct < min_edge_vs_ask_pct
                ):
                    reasons.append(f"ask_edge<{min_edge_vs_ask_pct:.2f}%")

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
            "edge_vs_ask_pct": edge_vs_ask_pct,
            "ask_is_proxy": ask_is_proxy,
            "sample_size": sample_size,
            "percentile": percentile,
            "side": side,
            "window_profile": window_profile,
        }

    def _resolve_quant_gate_window_params(self, event_dict: dict) -> tuple[str, dict]:
        settings = self.settings
        params = {
            "gate_enabled": bool(settings.get("quant_gate_enabled", True)),
            "min_sample": int(settings.get("quant_gate_min_sample", 120)),
            "min_edge_pct": float(settings.get("quant_gate_min_edge_pct", 4.0)),
            "use_percentile": bool(settings.get("quant_gate_use_percentile", True)),
            "percentile_low": float(settings.get("quant_gate_percentile_low", 15.0)),
            "percentile_high": float(settings.get("quant_gate_percentile_high", 85.0)),
            "min_price_c": float(settings.get("quant_gate_min_price_c", 10.0)),
            "max_price_c": float(settings.get("quant_gate_max_price_c", 90.0)),
            "edge_vs_ask_enabled": bool(
                settings.get("quant_gate_edge_vs_ask_enabled", False)
            ),
            "min_edge_vs_ask_pct": float(
                settings.get("quant_gate_min_edge_vs_ask_pct", 2.0)
            ),
            "min_prob": float(settings.get("quant_gate_min_prob", 0.0)),
            "min_diff_pct": float(settings.get("quant_gate_min_diff_pct", 0.0)),
        }

        now_utc = datetime.now(tz=timezone.utc)
        start_dt = None
        end_dt = None
        try:
            start_raw = event_dict.get("event_start_utc")
            if isinstance(start_raw, str) and start_raw:
                start_dt = datetime.fromisoformat(start_raw)
        except Exception:
            start_dt = None
        try:
            end_raw = event_dict.get("event_end_utc")
            if isinstance(end_raw, str) and end_raw:
                end_dt = datetime.fromisoformat(end_raw)
        except Exception:
            end_dt = None

        elapsed_seconds = None
        time_left_seconds = None
        if start_dt is not None:
            elapsed_seconds = max(0, int((now_utc - start_dt).total_seconds()))
        if end_dt is not None:
            time_left_seconds = max(0, int((end_dt - now_utc).total_seconds()))

        # ── Min seconds before end ────────────────────────────────────────────
        min_secs_before_end = max(
            0, int(settings.get("bot_min_seconds_before_end", 30))
        )
        if time_left_seconds is not None and time_left_seconds < min_secs_before_end:
            return "blocked_end", {**params, "gate_enabled": False}

        # ── Early window ──────────────────────────────────────────────────────
        if (
            bool(settings.get("early_window_enabled", False))
            and elapsed_seconds is not None
        ):
            early_start = int(settings.get("early_window_start", 20))
            early_end = int(settings.get("early_window_end", 120))
            if elapsed_seconds < early_start:
                # Too early — block gate entirely
                return "blocked_early", {**params, "gate_enabled": False}
            if elapsed_seconds <= early_end:
                params.update(
                    {
                        "min_sample": int(
                            settings.get(
                                "early_quant_gate_min_sample", params["min_sample"]
                            )
                        ),
                        "min_edge_pct": float(
                            settings.get(
                                "early_quant_gate_min_edge_pct", params["min_edge_pct"]
                            )
                        ),
                        "edge_vs_ask_enabled": bool(
                            settings.get(
                                "early_quant_gate_edge_vs_ask_enabled",
                                params["edge_vs_ask_enabled"],
                            )
                        ),
                        "min_edge_vs_ask_pct": float(
                            settings.get(
                                "early_quant_gate_min_edge_vs_ask_pct",
                                params["min_edge_vs_ask_pct"],
                            )
                        ),
                        "min_prob": float(
                            settings.get("early_quant_gate_min_prob")
                            or params["min_prob"]
                        ),
                        "min_diff_pct": float(
                            settings.get("early_quant_gate_min_diff_pct", 0.0)
                        ),
                    }
                )
                return "early", params

        # ── Late window ───────────────────────────────────────────────────────
        if (
            bool(settings.get("late_window_enabled", False))
            and elapsed_seconds is not None
        ):
            late_start = int(settings.get("late_window_start", 180))
            late_end = int(settings.get("late_window_end", 280))
            if elapsed_seconds > late_end:
                # Too late — block gate entirely
                return "blocked_late", {**params, "gate_enabled": False}
            if elapsed_seconds >= late_start:
                params.update(
                    {
                        "min_sample": int(
                            settings.get(
                                "late_quant_gate_min_sample", params["min_sample"]
                            )
                        ),
                        "min_edge_pct": float(
                            settings.get(
                                "late_quant_gate_min_edge_pct", params["min_edge_pct"]
                            )
                        ),
                        "edge_vs_ask_enabled": bool(
                            settings.get(
                                "late_quant_gate_edge_vs_ask_enabled",
                                params["edge_vs_ask_enabled"],
                            )
                        ),
                        "min_edge_vs_ask_pct": float(
                            settings.get(
                                "late_quant_gate_min_edge_vs_ask_pct",
                                params["min_edge_vs_ask_pct"],
                            )
                        ),
                        "min_prob": float(
                            settings.get("late_quant_gate_min_prob")
                            or params["min_prob"]
                        ),
                        "min_diff_pct": float(
                            settings.get("late_quant_gate_min_diff_pct", 0.0)
                        ),
                    }
                )
                return "late", params

        return "base", params

    def _apply_quant_buy_gates(self, event_dict: dict) -> None:
        histogram = event_dict.get("quant_range_histogram")
        percentile: float | None = None
        if isinstance(histogram, dict):
            raw = histogram.get("current_percentile")
            percentile = float(raw) if isinstance(raw, (float, int)) else None

        quant_prob_up = event_dict.get("quant_prob_up")
        quant_prob_down = event_dict.get("quant_prob_down")
        sample_size = event_dict.get("quant_sample_size")
        ptb = event_dict.get("price_to_beat")
        cp = event_dict.get("current_price")
        price_diff_abs = None
        price_diff_pct = None
        if (
            isinstance(ptb, (int, float))
            and isinstance(cp, (int, float))
            and float(ptb) > 0
        ):
            try:
                price_diff_abs = abs(float(cp) - float(ptb))
                price_diff_pct = price_diff_abs / float(ptb) * 100.0
            except Exception:
                price_diff_abs = None
                price_diff_pct = None
        yes_price = float(event_dict.get("yes_price", 0.5) or 0.5)
        no_price = float(event_dict.get("no_price", 0.5) or 0.5)
        window_profile, gate_params = self._resolve_quant_gate_window_params(event_dict)
        ask_up_raw = None
        ask_down_raw = None
        if isinstance(event_dict.get("order_book_yes"), dict):
            asks = event_dict.get("order_book_yes", {}).get("asks", [])
            if isinstance(asks, list) and asks:
                raw = asks[0].get("price") if isinstance(asks[0], dict) else None
                try:
                    ask_up_raw = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    ask_up_raw = None
        if isinstance(event_dict.get("order_book_no"), dict):
            asks = event_dict.get("order_book_no", {}).get("asks", [])
            if isinstance(asks, list) and asks:
                raw = asks[0].get("price") if isinstance(asks[0], dict) else None
                try:
                    ask_down_raw = float(raw) if raw is not None else None
                except (TypeError, ValueError):
                    ask_down_raw = None

        # Fallback: use mid-price as ask proxy when order book is unavailable
        ask_up_is_proxy = ask_up_raw is None
        ask_down_is_proxy = ask_down_raw is None
        ask_up = ask_up_raw if ask_up_raw is not None else yes_price
        ask_down = ask_down_raw if ask_down_raw is not None else no_price

        event_dict["quant_buy_gate"] = {
            "up": self._compute_quant_buy_gate_side(
                side="up",
                quant_prob=quant_prob_up
                if isinstance(quant_prob_up, (float, int))
                else None,
                market_prob=yes_price,
                ask_price=ask_up,
                ask_is_proxy=ask_up_is_proxy,
                sample_size=int(sample_size) if isinstance(sample_size, int) else None,
                percentile=percentile,
                gate_params=gate_params,
                price_diff_abs=price_diff_abs,
                price_diff_pct=price_diff_pct,
                window_profile=window_profile,
            ),
            "down": self._compute_quant_buy_gate_side(
                side="down",
                quant_prob=quant_prob_down
                if isinstance(quant_prob_down, (float, int))
                else None,
                market_prob=no_price,
                ask_price=ask_down,
                ask_is_proxy=ask_down_is_proxy,
                sample_size=int(sample_size) if isinstance(sample_size, int) else None,
                percentile=percentile,
                gate_params=gate_params,
                price_diff_abs=price_diff_abs,
                price_diff_pct=price_diff_pct,
                window_profile=window_profile,
            ),
        }

    def _track_opportunities_for_event(
        self, event_id: str, event_dict: dict, now_utc: datetime
    ) -> None:
        if not self.is_event_trading_enabled(event_id, event_dict):
            return
        if not self._is_trackable_crypto_event(event_id, event_dict):
            return
        quant_gate = event_dict.get("quant_buy_gate")
        if not isinstance(quant_gate, dict):
            return
        for side in ("up", "down"):
            gate_side = quant_gate.get(side)
            evaluation = self._evaluate_trackable_side_for_tracking(
                event_id, event_dict, side, now_utc
            )
            self._opportunity_tracker.track_gate_transition(
                event_id=event_id,
                event_dict=event_dict,
                side=side,
                gate_side=gate_side if isinstance(gate_side, dict) else None,
                settings=self.settings,
                mode=self.mode,
                now_utc=now_utc,
                stake_usd_override=evaluation.get("stake_usd"),
                blocked_reason=(
                    None
                    if bool(evaluation.get("eligible"))
                    else evaluation.get("reason")
                ),
                estimated_shares=evaluation.get("shares"),
            )

    @staticmethod
    def _parse_timeframe_filter_to_minutes(raw: object) -> int | None:
        value = str(raw or "").strip().lower()
        if value == "5m":
            return 5
        if value == "15m":
            return 15
        if value == "1h":
            return 60
        return None

    @staticmethod
    def _quant_gate_reason_text(reasons: list[object]) -> str:
        cleaned = [str(r).strip() for r in reasons if str(r).strip()]
        return " | ".join(cleaned) if cleaned else "quant_gate_blocked"

    @staticmethod
    def _event_best_ask_price(event_dict: dict, side: str) -> tuple[float, bool, str]:
        side_price = (
            float(event_dict.get("yes_price", 0.5) or 0.5)
            if side == "up"
            else float(event_dict.get("no_price", 0.5) or 0.5)
        )
        asks = (
            (event_dict.get("order_book_yes") or {}).get("asks", [])
            if side == "up"
            else (event_dict.get("order_book_no") or {}).get("asks", [])
        )
        if isinstance(asks, list) and asks:
            raw = asks[0].get("price") if isinstance(asks[0], dict) else None
            if raw is not None:
                try:
                    return float(raw), False, "best_ask"
                except (TypeError, ValueError):
                    pass
        return side_price, True, "proxy_mid"

    @staticmethod
    def _event_best_bid_price(event_dict: dict, side: str) -> float | None:
        bids = (
            (event_dict.get("order_book_yes") or {}).get("bids", [])
            if side == "up"
            else (event_dict.get("order_book_no") or {}).get("bids", [])
        )
        if isinstance(bids, list) and bids:
            raw = bids[0].get("price") if isinstance(bids[0], dict) else None
            return _as_float(raw)
        return None

    def evaluate_bot_order_candidate(
        self,
        *,
        event_id: str,
        event_dict: dict,
        side: str,
        now_utc: datetime,
        bankroll_usd: float | None = None,
    ) -> dict:
        """
        Single source of truth for bot/tracking eligibility on one event side.
        Returns sizing + decision so tracking/paper/live stay aligned.
        """
        side_norm = "up" if str(side).lower() == "up" else "down"
        side_price = (
            float(event_dict.get("yes_price", 0.5) or 0.5)
            if side_norm == "up"
            else float(event_dict.get("no_price", 0.5) or 0.5)
        )
        ask_price, ask_is_proxy, price_source_at_send = self._event_best_ask_price(
            event_dict, side_norm
        )
        result = {
            "eligible": False,
            "reason": "unknown",
            "side": side_norm,
            "side_price": side_price,
            "ask_price": ask_price,
            "ask_is_proxy": ask_is_proxy,
            "price_source_at_send": price_source_at_send,
            "quant_prob": None,
            "stake_usd": 0.0,
            "shares": 0.0,
            "notional_usd": 0.0,
            "kelly_pct": None,
        }

        if bool(self.settings.get("bot_enforce_timeframe_filter", True)):
            selected_tf = self._parse_timeframe_filter_to_minutes(
                self.settings.get("timeframe_filter", "5m")
            )
            event_tf = int(event_dict.get("timeframe_minutes", 15) or 15)
            if selected_tf is not None and event_tf != selected_tf:
                result["reason"] = "timeframe_mismatch"
                return result

        min_secs_before_end = max(
            0, int(self.settings.get("bot_min_seconds_before_end", 30))
        )
        end_raw = event_dict.get("event_end_utc")
        if min_secs_before_end > 0 and end_raw:
            try:
                end_dt = datetime.fromisoformat(str(end_raw))
                secs_remaining = (end_dt - now_utc).total_seconds()
                if secs_remaining < min_secs_before_end:
                    result["reason"] = "too_close_to_end"
                    return result
            except Exception:
                pass

        quant_gate = event_dict.get("quant_buy_gate")
        if isinstance(quant_gate, dict):
            gate_side = quant_gate.get(side_norm)
            if isinstance(gate_side, dict) and not bool(
                gate_side.get("enabled", False)
            ):
                reasons = gate_side.get("reasons", [])
                reasons_list = reasons if isinstance(reasons, list) else [reasons]
                result["reason"] = (
                    f"quant_gate_blocked:{self._quant_gate_reason_text(reasons_list)}"
                )
                return result

        max_price_c = float(self.settings.get("quant_gate_max_price_c", 90.0))
        min_price_c = float(self.settings.get("quant_gate_min_price_c", 10.0))
        ask_price_c = ask_price * 100.0
        if ask_price_c > max_price_c or ask_price_c < min_price_c:
            result["reason"] = "ask_price_outside_range"
            return result

        if not bool(self.settings.get("kelly_enabled", True)):
            result["reason"] = "kelly_disabled"
            return result

        quant_prob_raw = (
            event_dict.get("quant_prob_up")
            if side_norm == "up"
            else event_dict.get("quant_prob_down")
        )
        if not isinstance(quant_prob_raw, (float, int)):
            result["reason"] = "no_quant_prob"
            return result
        quant_prob = float(quant_prob_raw)
        result["quant_prob"] = quant_prob

        min_edge_pct = max(0.0, float(self.settings.get("kelly_min_edge_pct", 0.5)))
        edge_pct = (quant_prob - ask_price) * 100.0
        if edge_pct < min_edge_pct:
            result["reason"] = "edge_below_min"
            return result

        denom = max(0.0001, 1.0 - ask_price)
        raw_kelly = max(0.0, (quant_prob - ask_price) / denom)
        kelly_fraction = max(0.0, float(self.settings.get("kelly_fraction", 0.25)))
        max_bet_pct = (
            max(0.0, float(self.settings.get("kelly_max_bet_pct", 25.0))) / 100.0
        )
        max_event_exposure_pct = (
            max(0.0, float(self.settings.get("kelly_max_event_exposure_pct", 25.0)))
            / 100.0
        )
        kelly_pct = min(raw_kelly * kelly_fraction, max_bet_pct, max_event_exposure_pct)
        result["kelly_pct"] = kelly_pct
        base_bankroll = (
            self._get_paper_effective_bankroll_usd()
            if bool(self.settings.get("bot_paper_mode", False))
            else self._get_live_manual_bankroll_usd()
        )
        base_bankroll = max(1.0, float(base_bankroll))
        stake_usd = kelly_pct * base_bankroll

        hard_cap = max(0.0, float(self.settings.get("bot_order_notional_cap_usd", 0.0)))
        if hard_cap > 0:
            stake_usd = min(stake_usd, hard_cap)

        if ask_price <= 0:
            result["reason"] = "invalid_side_price"
            return result
        shares = stake_usd / ask_price
        notional_usd = ask_price * shares
        result["stake_usd"] = stake_usd
        result["shares"] = shares
        result["notional_usd"] = notional_usd
        if stake_usd <= 0:
            result["reason"] = "stake_non_positive"
            return result

        guard_bankroll = bankroll_usd
        if guard_bankroll is None:
            guard_bankroll = (
                self._get_paper_effective_bankroll_usd()
                if bool(self.settings.get("bot_paper_mode", False))
                else self._get_live_manual_bankroll_usd()
            )
        allowed, guard_reason = self.validate_order_risk_guards(
            event_id=event_id,
            event=event_dict,
            outcome=side_norm,
            shares=shares,
            notional_usd=notional_usd,
            now_utc=now_utc,
            bankroll_usd=guard_bankroll,
        )
        if not allowed:
            result["reason"] = guard_reason or "risk_guard_blocked"
            return result

        result["eligible"] = True
        result["reason"] = None
        return result

    def _evaluate_trackable_side_for_tracking(
        self, event_id: str, event_dict: dict, side: str, now_utc: datetime
    ) -> dict:
        """Compatibility wrapper for tracker payload."""
        evaluation = self.evaluate_bot_order_candidate(
            event_id=event_id,
            event_dict=event_dict,
            side=side,
            now_utc=now_utc,
        )
        return {
            "eligible": bool(evaluation.get("eligible")),
            "reason": evaluation.get("reason"),
            "stake_usd": float(evaluation.get("stake_usd", 0.0) or 0.0),
            "shares": float(evaluation.get("shares", 0.0) or 0.0),
            "side_price": float(evaluation.get("side_price", 0.5) or 0.5),
        }

    def _extract_event_ticker(self, event_id: str, event_dict: dict) -> str:
        raw_symbol = normalize_symbol(
            str(
                event_dict.get("chainlink_symbol")
                or event_dict.get("binance_symbol", "")
            )
        )
        ticker = raw_symbol.upper().strip()
        if ticker.endswith("USDT"):
            ticker = ticker[:-4]
        if ticker:
            return ticker

        text = f"{event_id} {event_dict.get('name', '')}".lower()
        if re.search(r"\b(bitcoin|btc)\b", text):
            return "BTC"
        if re.search(r"\b(ethereum|eth)\b", text):
            return "ETH"
        if re.search(r"\b(sol|solana)\b", text):
            return "SOL"
        if re.search(r"\b(xrp|ripple)\b", text):
            return "XRP"
        return "OTHER"

    @staticmethod
    def _paper_current_slot_and_range(event_dict: dict) -> tuple[int | None, str]:
        histogram = event_dict.get("quant_range_histogram")
        if not isinstance(histogram, dict):
            return None, ""
        slot = None
        raw_slot = histogram.get("slot")
        raw_minute = histogram.get("minute")
        if isinstance(raw_slot, (int, float)):
            slot = int(raw_slot)
        elif isinstance(raw_minute, (int, float)):
            slot = int(raw_minute)

        range_label = ""
        idx = histogram.get("current_bin_index")
        bins = histogram.get("bins")
        resolved_idx: int | None = idx if isinstance(idx, int) else None
        if (
            resolved_idx is None
            and isinstance(bins, list)
            and bins
            and isinstance(histogram.get("current_diff"), (int, float))
        ):
            # Histogram percentiles handle out-of-range diffs, but index may be None.
            # Clamp to first/last bin so paper CSV keeps a concrete range label.
            current_diff = float(histogram.get("current_diff"))
            first = bins[0] if isinstance(bins[0], dict) else {}
            last = bins[-1] if isinstance(bins[-1], dict) else {}
            first_inf = first.get("inf_range")
            last_sup = last.get("sup_range")
            if isinstance(first_inf, (int, float)) and current_diff < float(first_inf):
                resolved_idx = 0
            elif isinstance(last_sup, (int, float)) and current_diff >= float(last_sup):
                resolved_idx = len(bins) - 1
        if (
            isinstance(resolved_idx, int)
            and isinstance(bins, list)
            and 0 <= resolved_idx < len(bins)
        ):
            row = bins[resolved_idx] if isinstance(bins[resolved_idx], dict) else {}
            inf_v = row.get("inf_range")
            sup_v = row.get("sup_range")
            if isinstance(inf_v, (int, float)) and isinstance(sup_v, (int, float)):
                range_label = f"[{float(inf_v):.2f},{float(sup_v):.2f})"
        return slot, range_label

    def _append_paper_trade_decision(
        self,
        *,
        event_id: str,
        event_dict: dict,
        side: str,
        stake_usd: float,
        market_prob_at_decision: float,
        quantum_edge: float,
        price_source_at_decision: str = "unknown",
        now_utc: datetime,
    ) -> None:
        _ensure_paper_trades_csv()
        decision_id = str(uuid.uuid4())
        ticker = self._extract_event_ticker(event_id, event_dict)
        slot, range_label = self._paper_current_slot_and_range(event_dict)
        prob_up = (
            float(event_dict.get("quant_prob_up"))
            if isinstance(event_dict.get("quant_prob_up"), (int, float))
            else None
        )
        q = max(0.0, float(market_prob_at_decision))
        stake = max(0.0, float(stake_usd))
        side_norm = "up" if str(side).lower() == "up" else "down"
        price_to_beat = float(event_dict.get("price_to_beat", 0) or 0)
        current_price = float(event_dict.get("current_price", 0) or 0)
        diff_vs_ptb = current_price - price_to_beat
        best_bid = None
        if side_norm == "up":
            bids = (event_dict.get("order_book_yes") or {}).get("bids", [])
        else:
            bids = (event_dict.get("order_book_no") or {}).get("bids", [])
        if isinstance(bids, list) and bids:
            raw_bid = bids[0].get("price") if isinstance(bids[0], dict) else None
            best_bid = _as_float(raw_bid)
        best_ask = q if q > 0 else None
        mid = None
        spread = None
        spread_pct = None
        if (
            best_bid is not None
            and best_ask is not None
            and best_bid > 0
            and best_ask > 0
        ):
            mid = (best_bid + best_ask) / 2.0
            spread = max(0.0, best_ask - best_bid)
            if mid > 0:
                spread_pct = spread / mid
        row = {
            "decision_id": decision_id,
            "decision_time": now_utc.isoformat(),
            "event_id": event_id,
            "ticker": ticker,
            "event_end_utc": str(event_dict.get("event_end_utc", "") or ""),
            "price_to_beat_at_decision": price_to_beat,
            "current_price_at_decision": round(current_price, 6),
            "diff_vs_ptb_at_decision": round(diff_vs_ptb, 6),
            "close_price_at_resolution": "",
            "stake_usd": round(stake, 6),
            "shares_simulated": round((stake / q), 6) if q > 0 else "",
            "slot": slot if slot is not None else "",
            "range": range_label,
            "prob_up": round(prob_up, 6) if prob_up is not None else "",
            "marketProb_at_decision": round(q, 6),
            "price_source_at_decision": str(price_source_at_decision or "unknown"),
            "best_bid_at_decision": round(best_bid, 6)
            if isinstance(best_bid, (int, float))
            else "",
            "best_ask_at_decision": round(q, 6),
            "mid_at_decision": round(mid, 6) if isinstance(mid, (int, float)) else "",
            "spread_at_decision": round(spread, 6)
            if isinstance(spread, (int, float))
            else "",
            "spread_pct_at_decision": round(spread_pct, 6)
            if isinstance(spread_pct, (int, float))
            else "",
            "fill_price_real": round(q, 6),
            "QuantumEdge": round(float(quantum_edge), 6),
            "edge_at_fill_pct": round(float(quantum_edge) * 100.0, 4),
            "friction_cost_usd": "",
            "pnl_sim_adjusted": "",
            "fee_pct_used": "",
            "slippage_buffer_pct_used": "",
            "side_taken": side,
            "event_outcome_real": "",
            "pnl_simulated": "",
            "status": "pending",
        }
        with open(_PAPER_TRADES_LOG_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_PAPER_TRADES_FIELDNAMES)
            writer.writerow(row)

    def _reconcile_paper_trades(self, now_utc: datetime) -> None:
        _ensure_paper_trades_csv()
        # Avoid rewriting CSV too often.
        if (
            self._last_paper_reconcile_at is not None
            and (now_utc - self._last_paper_reconcile_at).total_seconds() < 10
        ):
            return
        self._last_paper_reconcile_at = now_utc

        try:
            with open(_PAPER_TRADES_LOG_PATH, newline="") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            return
        if not rows:
            return

        changed = False
        resolved_pnl_delta = 0.0
        for row in rows:
            status = str(row.get("status", "")).strip().lower()
            if status == "resolved":
                continue
            event_id = str(row.get("event_id", "")).strip()
            if not event_id:
                continue
            end_raw = str(row.get("event_end_utc", "")).strip()
            try:
                end_dt = datetime.fromisoformat(end_raw) if end_raw else None
            except Exception:
                end_dt = None
            if end_dt is None or now_utc < end_dt:
                continue

            event = self.events.get(event_id)
            close_price = 0.0
            if isinstance(event, dict):
                close_price = float(event.get("current_price", 0) or 0)
            if close_price <= 0:
                cached = self._paper_event_cache.get(event_id, {})
                close_price = float(cached.get("close_price", 0) or 0)
            ptb = _as_float(row.get("price_to_beat_at_decision"))
            q = _as_float(row.get("marketProb_at_decision"))
            stake = _as_float(row.get("stake_usd"))
            side = str(row.get("side_taken", "")).strip().lower()
            if close_price <= 0 or ptb is None or q is None or q <= 0 or stake is None:
                continue

            event_outcome_real = "up" if close_price >= ptb else "down"
            won = event_outcome_real == side
            pnl = (stake * (1.0 / q - 1.0)) if won else (-stake)
            spread_pct = _as_float(row.get("spread_pct_at_decision"))
            fee_pct_used = _PAPER_FEE_PCT_DEFAULT
            slippage_buffer_pct_used = _PAPER_SLIPPAGE_BUFFER_PCT_DEFAULT
            spread_component = max(0.0, spread_pct or 0.0) * 0.5
            friction_rate = max(
                0.0,
                (float(fee_pct_used) / 100.0)
                + float(spread_component)
                + (float(slippage_buffer_pct_used) / 100.0),
            )
            friction_cost = stake * friction_rate
            pnl_adjusted = pnl - friction_cost

            row["close_price_at_resolution"] = f"{close_price:.6f}"
            row["event_outcome_real"] = event_outcome_real
            row["pnl_simulated"] = f"{pnl:.6f}"
            row["friction_cost_usd"] = f"{friction_cost:.6f}"
            row["pnl_sim_adjusted"] = f"{pnl_adjusted:.6f}"
            row["fee_pct_used"] = f"{fee_pct_used:.6f}"
            row["slippage_buffer_pct_used"] = f"{slippage_buffer_pct_used:.6f}"
            row["status"] = "resolved"
            changed = True
            resolved_pnl_delta += pnl

        if changed:
            with open(_PAPER_TRADES_LOG_PATH, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_PAPER_TRADES_FIELDNAMES)
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {k: row.get(k, "") for k in _PAPER_TRADES_FIELDNAMES}
                    )
            if bool(self.settings.get("paper_compound_enabled", True)):
                current = self.settings.get("paper_current_bankroll_usd")
                if not isinstance(current, (int, float)) or float(current) <= 0:
                    current = self._get_paper_manual_bankroll_usd()
                new_value = max(0.0, float(current) + float(resolved_pnl_delta))
                self.settings["paper_current_bankroll_usd"] = round(new_value, 6)
                self.persist_runtime_settings()

    @staticmethod
    def _clean_old_order_records(records: list[dict], now_utc: datetime) -> list[dict]:
        cutoff = now_utc - timedelta(days=2)
        return [
            r
            for r in records
            if isinstance(r.get("at_utc"), datetime) and r["at_utc"] >= cutoff
        ]

    def validate_order_risk_guards(
        self,
        *,
        event_id: str,
        event: dict,
        outcome: str,
        shares: float,
        notional_usd: float,
        now_utc: datetime,
        bankroll_usd: float | None,
    ) -> tuple[bool, str]:
        """Check configurable bot risk guards for a candidate order."""
        if not self.is_event_trading_enabled(event_id, event):
            return False, "ticker_disabled_by_monitored_tickers"
        if shares <= 0:
            return False, "invalid_shares"
        if notional_usd <= 0:
            return False, "invalid_notional"
        min_shares = max(0.0, float(self.settings.get("pm_min_shares", 5.0)))
        min_notional = max(0.0, float(self.settings.get("pm_min_notional_usd", 1.0)))
        if shares < min_shares:
            return False, f"shares_below_min_{min_shares:g}"
        if notional_usd < min_notional:
            return False, f"notional_below_min_{min_notional:g}"
        if not bool(self.settings.get("bot_risk_enabled", True)):
            return True, ""

        self._order_guard_records = self._clean_old_order_records(
            self._order_guard_records, now_utc
        )

        global_cooldown = max(
            0.0, float(self.settings.get("bot_global_min_seconds_between_orders", 2))
        )
        if (
            self._last_order_at_utc is not None
            and global_cooldown > 0
            and (now_utc - self._last_order_at_utc).total_seconds() < global_cooldown
        ):
            return False, "global_order_cooldown_active"

        side = "up" if str(outcome).lower() == "up" else "down"
        per_event_limit = max(
            0, int(self.settings.get("bot_max_buys_per_event_side", 1))
        )
        event_cooldown = max(
            0.0, float(self.settings.get("bot_cooldown_seconds_per_event_side", 60))
        )
        start_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        # Max buys and cooldown apply per event (any side), not per event+side
        event_records = [
            r
            for r in self._order_guard_records
            if r.get("event_id") == event_id and r.get("at_utc") >= start_day
        ]
        if per_event_limit > 0 and len(event_records) >= per_event_limit:
            return False, "max_buys_per_event_reached"
        if event_records and event_cooldown > 0:
            last_event_at = max(r["at_utc"] for r in event_records)
            if (now_utc - last_event_at).total_seconds() < event_cooldown:
                return False, "event_cooldown_active"

        # Block buying opposite side if already bought this event today (configurable)
        if bool(self.settings.get("bot_block_opposite_side", True)):
            opposite_side = "down" if side == "up" else "up"
            opposite_records = [
                r
                for r in self._order_guard_records
                if r.get("event_id") == event_id
                and r.get("outcome") == opposite_side
                and r.get("at_utc") >= start_day
            ]
            if opposite_records:
                return False, f"already_bought_{opposite_side}_this_event"

        ticker = self._extract_event_ticker(event_id, event)
        hard_order_cap = max(
            0.0, float(self.settings.get("bot_order_notional_cap_usd", 0.0))
        )
        if hard_order_cap > 0:
            if notional_usd > hard_order_cap:
                return False, f"order_notional_above_cap_{hard_order_cap:g}"
            return True, ""

        base_bankroll = (
            float(bankroll_usd)
            if bankroll_usd is not None and bankroll_usd > 0
            else self._get_live_manual_bankroll_usd()
        )
        base_bankroll = max(1.0, base_bankroll)
        event_cap_usd = (
            base_bankroll
            * max(0.0, float(self.settings.get("bot_max_event_exposure_pct", 15.0)))
            / 100.0
        )
        ticker_cap_usd = (
            base_bankroll
            * max(0.0, float(self.settings.get("bot_max_ticker_exposure_pct", 25.0)))
            / 100.0
        )

        event_spend = sum(
            float(r.get("notional_usd", 0.0))
            for r in self._order_guard_records
            if r.get("event_id") == event_id and r.get("at_utc") >= start_day
        )
        ticker_spend = sum(
            float(r.get("notional_usd", 0.0))
            for r in self._order_guard_records
            if r.get("ticker") == ticker and r.get("at_utc") >= start_day
        )
        if event_spend + notional_usd > event_cap_usd:
            return False, "event_exposure_cap_reached"
        if ticker_spend + notional_usd > ticker_cap_usd:
            return False, "ticker_exposure_cap_reached"

        return True, ""

    def format_risk_guard_block_reason(
        self,
        *,
        reason: str,
        event_id: str,
        event: dict,
        notional_usd: float,
        now_utc: datetime,
        bankroll_usd: float | None,
    ) -> str:
        """
        Expand compact risk-guard reason codes with actionable context.
        """
        if reason not in {"event_exposure_cap_reached", "ticker_exposure_cap_reached"}:
            return reason

        records = self._clean_old_order_records(self._order_guard_records, now_utc)
        start_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        ticker = self._extract_event_ticker(event_id, event)
        base_bankroll = (
            float(bankroll_usd)
            if bankroll_usd is not None and bankroll_usd > 0
            else self._get_live_manual_bankroll_usd()
        )
        base_bankroll = max(1.0, base_bankroll)
        event_cap_usd = (
            base_bankroll
            * max(0.0, float(self.settings.get("bot_max_event_exposure_pct", 15.0)))
            / 100.0
        )
        ticker_cap_usd = (
            base_bankroll
            * max(0.0, float(self.settings.get("bot_max_ticker_exposure_pct", 25.0)))
            / 100.0
        )
        event_spend = sum(
            float(r.get("notional_usd", 0.0))
            for r in records
            if r.get("event_id") == event_id and r.get("at_utc") >= start_day
        )
        ticker_spend = sum(
            float(r.get("notional_usd", 0.0))
            for r in records
            if r.get("ticker") == ticker and r.get("at_utc") >= start_day
        )
        new_notional = max(0.0, float(notional_usd))

        if reason == "event_exposure_cap_reached":
            return (
                "event_exposure_cap_reached "
                f"(event_spend=${event_spend:.2f}, new_notional=${new_notional:.2f}, "
                f"cap=${event_cap_usd:.2f}, bankroll=${base_bankroll:.2f})"
            )
        return (
            "ticker_exposure_cap_reached "
            f"(ticker={ticker}, ticker_spend=${ticker_spend:.2f}, "
            f"new_notional=${new_notional:.2f}, cap=${ticker_cap_usd:.2f}, "
            f"bankroll=${base_bankroll:.2f})"
        )

    def register_order_fill(
        self,
        *,
        event_id: str,
        event: dict,
        outcome: str,
        notional_usd: float,
        now_utc: datetime,
        bankroll_snapshot_usd: float | None = None,
    ) -> None:
        self._order_guard_records = self._clean_old_order_records(
            self._order_guard_records, now_utc
        )
        self._order_guard_records.append(
            {
                "at_utc": now_utc,
                "event_id": event_id,
                "ticker": self._extract_event_ticker(event_id, event),
                "outcome": "up" if str(outcome).lower() == "up" else "down",
                "notional_usd": max(0.0, float(notional_usd)),
            }
        )
        self._last_order_at_utc = now_utc

        # Capture a persistent baseline for live trading equity on first real live fill.
        if self.mode == "live" and not bool(self.settings.get("bot_paper_mode", False)):
            current_base = self.settings.get("live_equity_start_bankroll_usd")
            has_base = (
                isinstance(current_base, (int, float)) and float(current_base) > 0
            )
            if not has_base:
                candidate = (
                    float(bankroll_snapshot_usd)
                    if isinstance(bankroll_snapshot_usd, (int, float))
                    and float(bankroll_snapshot_usd) > 0
                    else self._get_live_manual_bankroll_usd()
                )
                candidate = max(1.0, float(candidate))
                self.settings["live_equity_start_bankroll_usd"] = round(candidate, 6)
                self.settings["live_equity_start_at_utc"] = now_utc.isoformat()
                self.persist_runtime_settings()

    # ------------------------------------------------------------------
    # Position Tracker — fuente de verdad para shares por evento
    # ------------------------------------------------------------------

    def record_position_buy(
        self,
        *,
        event_id: str,
        outcome: str,
        token_id: str,
        shares: float,
        price: float,
        placed_at_utc: str,
    ) -> None:
        """Registra una compra en el tracker. Promedia si ya hay posición."""
        outcome = outcome.lower()
        if event_id not in self._position_tracker:
            self._position_tracker[event_id] = {}
        existing = self._position_tracker[event_id].get(outcome)
        if existing:
            total_shares = existing["shares"] + shares
            avg_price = (
                existing["shares"] * existing["avg_price"] + shares * price
            ) / total_shares
            self._position_tracker[event_id][outcome] = {
                "shares": round(total_shares, 6),
                "avg_price": round(avg_price, 6),
                "token_id": token_id,
                "placed_at_utc": existing["placed_at_utc"],
            }
        else:
            self._position_tracker[event_id][outcome] = {
                "shares": round(shares, 6),
                "avg_price": round(price, 6),
                "token_id": token_id,
                "placed_at_utc": placed_at_utc,
            }
        logger.info(
            "[POSITION_TRACKER] buy event_id=%s outcome=%s shares=%.6f price=%.6f",
            event_id,
            outcome,
            shares,
            price,
        )

    def record_position_sell(
        self,
        *,
        event_id: str,
        outcome: str,
        shares_sold: float,
    ) -> None:
        """Reduce o elimina la posición trackeada tras una venta."""
        outcome = outcome.lower()
        pos = self._position_tracker.get(event_id, {}).get(outcome)
        if not pos:
            return
        remaining = max(0.0, round(pos["shares"] - shares_sold, 6))
        if remaining == 0.0:
            self._position_tracker.get(event_id, {}).pop(outcome, None)
        else:
            self._position_tracker[event_id][outcome]["shares"] = remaining
        logger.info(
            "[POSITION_TRACKER] sell event_id=%s outcome=%s sold=%.6f remaining=%.6f",
            event_id,
            outcome,
            shares_sold,
            remaining,
        )

    def get_tracked_positions(self, event_id: str) -> dict:
        """Retorna las posiciones trackeadas para un evento."""
        return self._position_tracker.get(event_id, {})

    def is_event_trading_enabled(
        self, event_id: str, event_dict: dict | None = None
    ) -> bool:
        event = (
            event_dict if isinstance(event_dict, dict) else self.events.get(event_id)
        )
        if not event:
            return False
        monitored = {
            str(t).strip().upper()
            for t in self.settings.get(
                "monitored_tickers", ["BTC", "ETH", "SOL", "XRP"]
            )
            if str(t).strip()
        }
        if not monitored:
            return False
        ticker = self._extract_event_ticker(event_id, event)
        return ticker in monitored

    def _is_trackable_crypto_event(self, event_id: str, event_dict: dict) -> bool:
        """Allow opportunity tracking only for supported crypto events."""
        monitored = {
            str(t).strip().upper()
            for t in self.settings.get(
                "monitored_tickers", ["BTC", "ETH", "SOL", "XRP"]
            )
            if str(t).strip()
        }
        if not monitored:
            monitored = {"BTC", "ETH", "SOL", "XRP"}

        raw_symbol = normalize_symbol(
            str(
                event_dict.get("chainlink_symbol")
                or event_dict.get("binance_symbol", "")
            )
        )
        ticker = raw_symbol.upper().strip()
        if ticker.endswith("USDT"):
            ticker = ticker[:-4]
        if ticker not in monitored:
            return False

        # Extra guard: ticker inferred from symbol must match event text.
        text = f"{event_id} {event_dict.get('name', '')}".lower()
        patterns = {
            "BTC": r"\b(bitcoin|btc)\b",
            "ETH": r"\b(ethereum|eth)\b",
            "SOL": r"\b(sol|solana)\b",
            "XRP": r"\b(xrp|ripple)\b",
        }
        pattern = patterns.get(ticker)
        return bool(pattern and re.search(pattern, text))

    async def start(self):
        """Start the event manager background loop."""
        self.load_config()
        self._load_runtime_settings()
        self._pm_ranges = self._load_pm_ranges()
        self._pm_5m_slot_ranges = self._load_pm_5m_slot_ranges()
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
        self.persist_runtime_settings()

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
                    await self._watchdog_price_streams()
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

    async def _watchdog_price_streams(self) -> None:
        """Restart any price stream tasks that have died unexpectedly."""
        # Chainlink tasks
        dead_chainlink: list[int] = []
        for i, task in enumerate(self._chainlink_stream_tasks):
            if task.done():
                exc = task.exception() if not task.cancelled() else None
                logger.warning(
                    "Chainlink stream task[%d] died (cancelled=%s, exc=%s) — restarting",
                    i,
                    task.cancelled(),
                    exc,
                )
                dead_chainlink.append(i)
        for i in reversed(dead_chainlink):
            streamer = self._chainlink_streamers[i]
            streamer._running = True
            self._chainlink_stream_tasks[i] = asyncio.create_task(streamer.start())

        # Binance tasks
        dead_binance: list[int] = []
        for i, task in enumerate(self._binance_stream_tasks):
            if task.done():
                exc = task.exception() if not task.cancelled() else None
                logger.warning(
                    "Binance stream task[%d] died (cancelled=%s, exc=%s) — restarting",
                    i,
                    task.cancelled(),
                    exc,
                )
                dead_binance.append(i)
        for i in reversed(dead_binance):
            streamer = self._binance_streamers[i]
            streamer._running = True
            self._binance_stream_tasks[i] = asyncio.create_task(streamer.start())

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
                "price_to_beat_source": "unknown",
                "last_update": "",
                "price_change": 0,
                "volume_24h": 0,
                "condition_id": event_config.get("condition_id", ""),
                "chainlink_symbol": event_config.get("chainlink_symbol", ""),
                "binance_symbol": bsym,
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
                "quant_source": None,
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
                event_dict["price_to_beat_source"] = (
                    "gamma" if str(event_config.get("slug", "")).strip() else "config"
                )

            if bsym and est:
                start_ms = parse_event_start_ms(est)
                if start_ms:
                    kh = fetch_binance_klines(bsym, start_ms)
                    if kh:
                        event_dict["price_history"] = kh
                        if event_dict.get("price_to_beat", 0) <= 0:
                            event_dict["price_to_beat"] = kh[0]["price_to_beat"]
                            event_dict["price_to_beat_source"] = "binance_klines"
                        event_dict["current_price"] = kh[-1]["price"]
                    else:
                        op = fetch_binance_candle_open(
                            bsym, start_ms, timeframe_minutes
                        )
                        if op and event_dict.get("price_to_beat", 0) <= 0:
                            event_dict["price_to_beat"] = op
                            event_dict["price_to_beat_source"] = "binance_open"

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
            if not self._is_supported_crypto_event_config(event_cfg):
                continue
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
                    if not self._is_supported_crypto_event_config(event_cfg):
                        continue
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
    def _is_supported_crypto_event_config(event_cfg: dict) -> bool:
        """
        Hard filter for supported universe. We only operate BTC/ETH/SOL/XRP.
        """
        raw_symbol = normalize_symbol(
            str(
                event_cfg.get("chainlink_symbol") or event_cfg.get("binance_symbol", "")
            )
        ).upper()
        if raw_symbol.endswith("USDT"):
            raw_symbol = raw_symbol[:-4]

        text = (
            f"{event_cfg.get('name', '')} "
            f"{event_cfg.get('description', '')} "
            f"{event_cfg.get('slug', '')}"
        ).lower()
        patterns = {
            "BTC": r"\b(bitcoin|btc)\b",
            "ETH": r"\b(ethereum|eth)\b",
            "SOL": r"\b(sol|solana)\b",
            "XRP": r"\b(xrp|ripple)\b",
        }
        text_matches = {
            symbol for symbol, pattern in patterns.items() if re.search(pattern, text)
        }

        if raw_symbol in {"BTC", "ETH", "SOL", "XRP"}:
            # If symbol is declared, text must also be consistent to avoid
            # accidental cross-category contamination.
            return raw_symbol in text_matches
        return bool(text_matches)

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
        has_active_event = False
        for event in self.events.values():
            end_raw = event.get("event_end_utc")
            if not isinstance(end_raw, str) or not end_raw:
                continue
            try:
                end_dt = datetime.fromisoformat(end_raw)
            except Exception:
                continue
            start_raw = event.get("event_start_utc")
            if isinstance(start_raw, str) and start_raw:
                try:
                    start_dt = datetime.fromisoformat(start_raw)
                    if start_dt <= now < end_dt:
                        has_active_event = True
                        break
                except Exception:
                    if now < end_dt:
                        has_active_event = True
                        break
            elif now < end_dt:
                has_active_event = True
                break

        # If no event is currently active, bypass cooldown so the next window
        # appears without waiting the full refresh_seconds.
        force_refresh = not has_active_event
        if self._last_discovery_refresh is not None:
            elapsed = (now - self._last_discovery_refresh).total_seconds()
            if elapsed < refresh_seconds and not force_refresh:
                return

        previous_events = self.events
        old_symbols = self._live_symbols()
        old_assets = self._live_polymarket_assets()
        self.load_config()
        new_events = self._init_live_events()
        self._last_discovery_refresh = now
        self.events = self._merge_live_state(previous_events, new_events)
        if (
            self._live_symbols() != old_symbols
            or self._live_polymarket_assets() != old_assets
        ):
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
        for task in self._polymarket_stream_tasks:
            task.cancel()
        self._binance_stream_tasks.clear()
        self._chainlink_stream_tasks.clear()
        self._polymarket_stream_tasks.clear()
        self._polymarket_asset_map.clear()

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
        if self.mode != "live":
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
        if symbols and source == "chainlink" and cl_url:
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
            await self._sync_polymarket_streams()
            return

        # Fallback to Binance streaming.
        if symbols:
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
        await self._sync_polymarket_streams()

    def _live_polymarket_assets(self) -> set[str]:
        assets: set[str] = set()
        for event_id, event in self.events.items():
            if not self._is_trackable_crypto_event(event_id, event):
                continue
            yes_token = str(event.get("yes_token_id", "")).strip()
            no_token = str(event.get("no_token_id", "")).strip()
            if yes_token:
                assets.add(yes_token)
            if no_token:
                assets.add(no_token)
        return assets

    async def _sync_polymarket_streams(self) -> None:
        """Ensure Polymarket book stream matches current live event token ids."""
        for s in self._polymarket_streamers:
            await s.stop()
        for task in self._polymarket_stream_tasks:
            task.cancel()
        self._polymarket_streamers.clear()
        self._polymarket_stream_tasks.clear()
        self._polymarket_asset_map.clear()

        if self.mode != "live":
            return

        assets = sorted(self._live_polymarket_assets())
        if not assets:
            return

        for event_id, event in self.events.items():
            if not self._is_trackable_crypto_event(event_id, event):
                continue
            yes_token = str(event.get("yes_token_id", "")).strip()
            no_token = str(event.get("no_token_id", "")).strip()
            if yes_token:
                self._polymarket_asset_map[yes_token] = (event_id, "yes")
            if no_token:
                self._polymarket_asset_map[no_token] = (event_id, "no")

        streamer = PolymarketStreamer(
            assets_ids=assets, on_book=self._on_polymarket_book
        )
        self._polymarket_streamers.append(streamer)
        self._polymarket_stream_tasks.append(asyncio.create_task(streamer.start()))
        logger.info("Started Polymarket WS stream for assets: %d", len(assets))

    @staticmethod
    def _parse_book_levels(
        levels: object, reverse: bool, max_levels: int
    ) -> list[dict]:
        parsed: list[tuple[float, float]] = []
        if not isinstance(levels, list):
            return []
        for level in levels:
            if not isinstance(level, dict):
                continue
            price = level.get("price")
            size = level.get("size", level.get("quantity", level.get("shares")))
            try:
                p = float(price)
                s = float(size)
            except (TypeError, ValueError):
                continue
            if p <= 0 or s <= 0:
                continue
            parsed.append((p, s))
        parsed.sort(key=lambda x: x[0], reverse=reverse)
        result: list[dict] = []
        cumulative = 0.0
        for idx, (p, s) in enumerate(parsed):
            if idx >= max_levels:
                break
            cumulative += p * s
            result.append(
                {
                    "price": round(p, 2),
                    "shares": round(s, 2),
                    "total": round(cumulative, 2),
                }
            )
        return result

    async def _on_polymarket_book(self, msg: dict) -> None:
        """Handle Polymarket realtime book updates and broadcast incrementally."""
        asset_id = str(
            msg.get("asset_id", msg.get("assetId", msg.get("market", "")))
        ).strip()
        if not asset_id:
            return
        mapping = self._polymarket_asset_map.get(asset_id)
        if not mapping:
            return
        event_id, side = mapping
        event = self.events.get(event_id)
        if not event:
            return

        max_levels = max(1, int(self.settings.get("order_book_max_levels", 8)))
        bids = self._parse_book_levels(
            msg.get("bids"), reverse=True, max_levels=max_levels
        )
        asks = self._parse_book_levels(
            msg.get("asks"), reverse=False, max_levels=max_levels
        )
        if not bids and not asks:
            return

        best_bid = bids[0]["price"] if bids else 0.0
        best_ask = asks[0]["price"] if asks else 0.0
        prev_ob = (
            event.get("order_book_yes") if side == "yes" else event.get("order_book_no")
        )
        prev_best_bid = 0.0
        prev_best_ask = 0.0
        if isinstance(prev_ob, dict):
            prev_bids = prev_ob.get("bids")
            prev_asks = prev_ob.get("asks")
            if isinstance(prev_bids, list) and prev_bids:
                try:
                    prev_best_bid = float(prev_bids[0].get("price", 0.0))
                except Exception:
                    prev_best_bid = 0.0
            if isinstance(prev_asks, list) and prev_asks:
                try:
                    prev_best_ask = float(prev_asks[0].get("price", 0.0))
                except Exception:
                    prev_best_ask = 0.0

        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        min_emit_ms = max(0, int(self.settings.get("order_book_min_broadcast_ms", 120)))
        emit_key = (event_id, side)
        last_emit = self._orderbook_last_emit_ms.get(emit_key, 0)
        top_unchanged = (
            abs(best_bid - prev_best_bid) < 1e-9
            and abs(best_ask - prev_best_ask) < 1e-9
        )
        if top_unchanged and (now_ms - last_emit) < min_emit_ms:
            return

        if best_bid > 0 and best_ask > 0:
            mid = (best_bid + best_ask) / 2.0
        else:
            mid = best_bid or best_ask or 0.5
        spread = max(0.0, best_ask - best_bid) if best_bid and best_ask else 0.0
        volume = sum(level["price"] * level["shares"] for level in asks) + sum(
            level["price"] * level["shares"] for level in bids
        )
        ob = {
            "bids": bids,
            "asks": asks,
            "last_price": round(mid, 2),
            "spread": round(spread, 2),
            "volume": round(volume, 2),
        }

        if side == "yes":
            event["order_book_yes"] = ob
            event["yes_price"] = mid
        else:
            event["order_book_no"] = ob
            event["no_price"] = mid

        if event.get("yes_price") is not None and event.get("no_price") is not None:
            total = float(event.get("yes_price", 0) or 0) + float(
                event.get("no_price", 0) or 0
            )
            if total > 0:
                event["yes_price"] = float(event.get("yes_price", 0) or 0) / total
                event["no_price"] = 1.0 - event["yes_price"]

        event["last_update"] = datetime.now(tz=timezone.utc).isoformat()
        self._orderbook_last_emit_ms[emit_key] = now_ms
        data: dict = {
            "yes_price": event.get("yes_price"),
            "no_price": event.get("no_price"),
            "last_update": event.get("last_update"),
        }
        if side == "yes":
            data["order_book_yes"] = event.get("order_book_yes")
        else:
            data["order_book_no"] = event.get("order_book_no")
        await manager.broadcast(
            {
                "type": "orderbook_update",
                "event_id": event_id,
                "data": data,
            }
        )

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
        self._last_price_tick_at = datetime.now(tz=timezone.utc)
        now_iso = self._last_price_tick_at.isoformat()

        for event_id, event_dict in self.events.items():
            ecfg = self._live_event_configs.get(event_id)
            if not ecfg:
                continue
            if not self._is_trackable_crypto_event(event_id, event_dict):
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

            # Always run state + bot logic on every tick
            self._apply_quant_metrics(event_dict, ecfg, datetime.now(tz=timezone.utc))
            self._apply_quant_buy_gates(event_dict)
            self._track_opportunities_for_event(
                event_id, event_dict, datetime.now(tz=timezone.utc)
            )

            # Throttle only the broadcast to frontend (max 1/s per event)
            now_ms = int(self._last_price_tick_at.timestamp() * 1000)
            last_broadcast_ms = self._price_broadcast_last_ms.get(event_id, 0)
            if now_ms - last_broadcast_ms < 1000:
                continue
            self._price_broadcast_last_ms[event_id] = now_ms

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
                        "quant_source": event_dict.get("quant_source"),
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
            "price_to_beat_source",
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

    async def _bot_maybe_place_order(
        self, event_id: str, event_dict: dict, side: str
    ) -> None:
        """Auto-place an order when gate transitions disabled→enabled in bot mode."""
        key = (event_id, side)
        quant_gate = event_dict.get("quant_buy_gate")
        if not isinstance(quant_gate, dict):
            self._bot_prev_gate_enabled[key] = False
            return

        gate_side = quant_gate.get(side)
        now_enabled = isinstance(gate_side, dict) and bool(gate_side.get("enabled"))
        prev_enabled = self._bot_prev_gate_enabled.get(key, False)
        self._bot_prev_gate_enabled[key] = now_enabled

        # Only fire on disabled→enabled transition, and not if already pending
        if not now_enabled or prev_enabled:
            return
        if key in self._bot_pending_orders:
            return

        self._bot_pending_orders.add(key)
        try:
            client = get_client()
            if not client:
                logger.warning("Bot auto-order: Polymarket client unavailable")
                return

            # Determine token
            token_id = (
                event_dict.get("yes_token_id")
                if side == "up"
                else event_dict.get("no_token_id")
            )
            if not token_id:
                logger.warning("Bot auto-order: no token_id for %s %s", event_id, side)
                return

            histogram = event_dict.get("quant_range_histogram")
            percentile_at_signal: float | None = None
            paper_mode_enabled = bool(self.settings.get("bot_paper_mode", False))
            if isinstance(histogram, dict):
                raw_pct = histogram.get("current_percentile")
                if isinstance(raw_pct, (float, int)):
                    percentile_at_signal = round(float(raw_pct), 4)
            now_utc = datetime.now(tz=timezone.utc)

            bankroll_usd: float | None = None
            # In paper mode, keep guardrails tied to paper bankroll only.
            # In live mode, prefer exchange balance for exposure-based caps.
            if not paper_mode_enabled:
                try:
                    bal = await asyncio.to_thread(client.get_balance)
                    if isinstance(bal, (int, float)) and bal > 0:
                        bankroll_usd = float(bal)
                except Exception:
                    pass

            evaluation = self.evaluate_bot_order_candidate(
                event_id=event_id,
                event_dict=event_dict,
                side=side,
                now_utc=now_utc,
                bankroll_usd=bankroll_usd,
            )
            if not bool(evaluation.get("eligible")):
                logger.info(
                    "Bot auto-order skipped by unified eligibility: %s | event=%s side=%s",
                    evaluation.get("reason"),
                    event_id,
                    side,
                )
                return
            ask_price = float(evaluation.get("ask_price", 0.0) or 0.0)
            notional_usd = float(evaluation.get("notional_usd", 0.0) or 0.0)
            shares = float(evaluation.get("shares", 0.0) or 0.0)
            quant_prob = float(evaluation.get("quant_prob", 0.0) or 0.0)
            kelly_pct_raw = evaluation.get("kelly_pct")
            kelly_pct = (
                float(kelly_pct_raw)
                if isinstance(kelly_pct_raw, (int, float))
                else None
            )
            price_source_at_send = str(
                evaluation.get("price_source_at_send") or "proxy_mid"
            )
            price_to_beat_at_send = _as_float(event_dict.get("price_to_beat"))
            current_price_at_send = _as_float(event_dict.get("current_price"))
            diff_vs_ptb_at_send = (
                float(current_price_at_send) - float(price_to_beat_at_send)
                if isinstance(current_price_at_send, float)
                and isinstance(price_to_beat_at_send, float)
                else None
            )
            best_bid_at_send = self._event_best_bid_price(event_dict, side)
            best_ask_at_send = ask_price if ask_price > 0 else None
            mid_at_send = None
            spread_at_send = None
            spread_pct_at_send = None
            if (
                isinstance(best_bid_at_send, float)
                and isinstance(best_ask_at_send, float)
                and best_bid_at_send > 0
                and best_ask_at_send > 0
            ):
                mid_at_send = (best_bid_at_send + best_ask_at_send) / 2.0
                spread_at_send = max(0.0, best_ask_at_send - best_bid_at_send)
                if mid_at_send > 0:
                    spread_pct_at_send = spread_at_send / mid_at_send

            if paper_mode_enabled:
                # Keep guard behavior aligned with live mode: once a paper decision is
                # accepted, register it as a fill for cooldown/max-buys/exposure memory.
                self.register_order_fill(
                    event_id=event_id,
                    event=event_dict,
                    outcome=side,
                    notional_usd=notional_usd,
                    now_utc=now_utc,
                    bankroll_snapshot_usd=bankroll_usd,
                )
                self._bot_prev_gate_enabled[key] = True
                self._append_paper_trade_decision(
                    event_id=event_id,
                    event_dict=event_dict,
                    side=side,
                    stake_usd=notional_usd,
                    market_prob_at_decision=ask_price,
                    quantum_edge=(quant_prob - ask_price),
                    price_source_at_decision=price_source_at_send,
                    now_utc=now_utc,
                )
                logger.info(
                    "Bot paper decision logged: event=%s side=%s stake=%.2f q=%.4f edge=%.4f src=%s",
                    event_id,
                    side,
                    notional_usd,
                    ask_price,
                    (quant_prob - ask_price),
                    price_source_at_send,
                )
                return

            logger.info(
                "Bot auto-order: placing FOK BUY $%.2f for %s %s (ask=%.4f shares=%.4f)",
                notional_usd,
                event_id,
                side,
                ask_price,
                shares,
            )
            result = await asyncio.to_thread(
                client.place_fok_order, token_id, "BUY", notional_usd
            )

            if result:
                # Lazy import to avoid circular dependency; invalidate stale cache
                try:
                    from ..routers.trading import invalidate_positions_cache

                    invalidate_positions_cache(event_id)
                except Exception:
                    pass
                self.register_order_fill(
                    event_id=event_id,
                    event=event_dict,
                    outcome=side,
                    notional_usd=notional_usd,
                    now_utc=now_utc,
                )
                # Lock gate for this key so a re-enable in the next tick
                # doesn't trigger a second order for the same event/side.
                self._bot_prev_gate_enabled[key] = True
                order_id = (
                    getattr(result, "id", None)
                    or getattr(result, "orderID", None)
                    or (result.get("id") if isinstance(result, dict) else None)
                    or (result.get("orderID") if isinstance(result, dict) else None)
                    or str(result)[:16]
                )
                fill_price_real = _extract_fill_price_from_result(result)
                edge_at_fill_pct = (
                    (quant_prob - fill_price_real) * 100.0
                    if isinstance(fill_price_real, float) and fill_price_real > 0
                    else None
                )
                _append_bot_order_log(
                    {
                        "placed_at_utc": now_utc.isoformat(),
                        "event_id": event_id,
                        "ticker": self._extract_event_ticker(event_id, event_dict),
                        "side": side,
                        "token_id": token_id,
                        "shares": round(shares, 6),
                        "price": round(ask_price, 6),
                        "notional_usd": round(notional_usd, 4),
                        "order_id": str(order_id),
                        "quant_prob": round(quant_prob, 6),
                        "edge_pct": round((quant_prob - ask_price) * 100, 4),
                        "price_source_at_send": price_source_at_send,
                        "price_to_beat_at_send": round(price_to_beat_at_send, 6)
                        if isinstance(price_to_beat_at_send, float)
                        else "",
                        "current_price_at_send": round(current_price_at_send, 6)
                        if isinstance(current_price_at_send, float)
                        else "",
                        "diff_vs_ptb_at_send": round(diff_vs_ptb_at_send, 6)
                        if isinstance(diff_vs_ptb_at_send, float)
                        else "",
                        "best_bid_at_send": round(best_bid_at_send, 6)
                        if isinstance(best_bid_at_send, float)
                        else "",
                        "best_ask_at_send": round(best_ask_at_send, 6)
                        if isinstance(best_ask_at_send, float)
                        else "",
                        "mid_at_send": round(mid_at_send, 6)
                        if isinstance(mid_at_send, float)
                        else "",
                        "spread_at_send": round(spread_at_send, 6)
                        if isinstance(spread_at_send, float)
                        else "",
                        "spread_pct_at_send": round(spread_pct_at_send, 6)
                        if isinstance(spread_pct_at_send, float)
                        else "",
                        "fill_price_real": round(fill_price_real, 6)
                        if isinstance(fill_price_real, float)
                        else "",
                        "edge_at_fill_pct": round(edge_at_fill_pct, 4)
                        if isinstance(edge_at_fill_pct, float)
                        else "",
                        "kelly_pct": round(kelly_pct * 100, 4)
                        if kelly_pct is not None
                        else "",
                        "bankroll_usd": round(bankroll_usd, 2)
                        if bankroll_usd is not None
                        else "",
                        "percentile_at_signal": percentile_at_signal
                        if percentile_at_signal is not None
                        else "",
                        "status": "placed",
                    }
                )
                logger.info("Bot auto-order placed: order_id=%s", order_id)
                self.record_position_buy(
                    event_id=event_id,
                    outcome=side,
                    token_id=token_id,
                    shares=shares,
                    price=ask_price,
                    placed_at_utc=now_utc.isoformat(),
                )
                # Broadcast bot_order event to frontend
                try:
                    refreshed_balance = await asyncio.to_thread(client.get_balance)
                except Exception:
                    refreshed_balance = None
                await manager.broadcast(
                    {
                        "type": "bot_order_placed",
                        "event_id": event_id,
                        "data": {
                            "side": side,
                            "shares": round(shares, 4),
                            "price": round(ask_price, 4),
                            "notional_usd": round(notional_usd, 2),
                            "order_id": str(order_id),
                            "balance": float(refreshed_balance)
                            if isinstance(refreshed_balance, (int, float))
                            else None,
                        },
                    }
                )
                if isinstance(refreshed_balance, (int, float)):
                    await manager.broadcast(
                        {
                            "type": "balance_update",
                            "event_id": "",
                            "data": {
                                "balance": float(refreshed_balance),
                                "source": "bot_auto_order",
                            },
                        }
                    )
            else:
                logger.error(
                    "Bot auto-order: place_order returned no result for %s %s",
                    event_id,
                    side,
                )
                _append_bot_order_log(
                    {
                        "placed_at_utc": now_utc.isoformat(),
                        "event_id": event_id,
                        "ticker": self._extract_event_ticker(event_id, event_dict),
                        "side": side,
                        "token_id": token_id,
                        "shares": round(shares, 6),
                        "price": round(ask_price, 6),
                        "notional_usd": round(notional_usd, 4),
                        "order_id": "",
                        "quant_prob": round(quant_prob, 6),
                        "edge_pct": round((quant_prob - ask_price) * 100, 4),
                        "price_source_at_send": price_source_at_send,
                        "price_to_beat_at_send": round(price_to_beat_at_send, 6)
                        if isinstance(price_to_beat_at_send, float)
                        else "",
                        "current_price_at_send": round(current_price_at_send, 6)
                        if isinstance(current_price_at_send, float)
                        else "",
                        "diff_vs_ptb_at_send": round(diff_vs_ptb_at_send, 6)
                        if isinstance(diff_vs_ptb_at_send, float)
                        else "",
                        "best_bid_at_send": round(best_bid_at_send, 6)
                        if isinstance(best_bid_at_send, float)
                        else "",
                        "best_ask_at_send": round(best_ask_at_send, 6)
                        if isinstance(best_ask_at_send, float)
                        else "",
                        "mid_at_send": round(mid_at_send, 6)
                        if isinstance(mid_at_send, float)
                        else "",
                        "spread_at_send": round(spread_at_send, 6)
                        if isinstance(spread_at_send, float)
                        else "",
                        "spread_pct_at_send": round(spread_pct_at_send, 6)
                        if isinstance(spread_pct_at_send, float)
                        else "",
                        "fill_price_real": "",
                        "edge_at_fill_pct": "",
                        "kelly_pct": round(kelly_pct * 100, 4)
                        if kelly_pct is not None
                        else "",
                        "bankroll_usd": round(bankroll_usd, 2)
                        if bankroll_usd is not None
                        else "",
                        "percentile_at_signal": percentile_at_signal
                        if percentile_at_signal is not None
                        else "",
                        "status": "failed",
                    }
                )

        except Exception as e:
            logger.error("Bot auto-order error for %s %s: %s", event_id, side, e)
        finally:
            self._bot_pending_orders.discard(key)

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
        # Use polling if no streamers exist, OR if streamer hasn't sent a tick in >10s (stall)
        streamer_stalled = (
            (self._binance_streamers or self._chainlink_streamers)
            and self._last_price_tick_at is not None
            and (
                datetime.now(tz=timezone.utc) - self._last_price_tick_at
            ).total_seconds()
            > 10
        )
        use_polling_prices = (
            not self._binance_streamers and not self._chainlink_streamers
        ) or streamer_stalled
        if streamer_stalled:
            now_check = datetime.now(tz=timezone.utc)
            if (
                self._streamer_stall_logged_at is None
                or (now_check - self._streamer_stall_logged_at).total_seconds() > 30
            ):
                logger.warning(
                    "Price streamer stalled (no tick >10s), falling back to REST polling"
                )
                self._streamer_stall_logged_at = now_check
        elif self._streamer_stall_logged_at is not None:
            logger.info("Price streamer recovered — resuming WS ticks")
            self._streamer_stall_logged_at = None
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
            if not self._is_trackable_crypto_event(event_id, event_dict):
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
            self._paper_event_cache[event_id] = {
                "event_end_utc": event_dict.get("event_end_utc"),
                "price_to_beat": float(event_dict.get("price_to_beat", 0) or 0),
                "close_price": float(event_dict.get("current_price", 0) or 0),
                "cached_at_utc": now_iso,
            }
            self._apply_quant_metrics(event_dict, ecfg, datetime.now(tz=timezone.utc))
            self._apply_quant_buy_gates(event_dict)
            self._track_opportunities_for_event(
                event_id, event_dict, datetime.now(tz=timezone.utc)
            )
            # Bot auto-order: fire-and-forget for each gate side
            if str(self.settings.get("trading_mode", "manual")).lower() == "bot":
                for side in ("up", "down"):
                    asyncio.create_task(
                        self._bot_maybe_place_order(event_id, event_dict, side)
                    )
            await manager.broadcast(
                {
                    "type": "quant_metrics_update",
                    "event_id": event_id,
                    "data": {
                        "quant_prob_up": event_dict.get("quant_prob_up"),
                        "quant_prob_down": event_dict.get("quant_prob_down"),
                        "quant_sample_size": event_dict.get("quant_sample_size"),
                        "quant_source": event_dict.get("quant_source"),
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
        self._reconcile_paper_trades(datetime.now(tz=timezone.utc))

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
            if not self._is_trackable_crypto_event(event_id, event_dict):
                continue

            pr = await asyncio.to_thread(fetch_real_prices, client, ecfg)
            if pr:
                event_dict["yes_price"] = pr["yes_price"]
                event_dict["no_price"] = pr["no_price"]
                if pr.get("order_book_yes"):
                    event_dict["order_book_yes"] = pr["order_book_yes"]
                if pr.get("order_book_no"):
                    event_dict["order_book_no"] = pr["order_book_no"]
                event_dict["last_update"] = datetime.now(tz=timezone.utc).isoformat()
                await manager.broadcast(
                    {
                        "type": "orderbook_update",
                        "event_id": event_id,
                        "data": {
                            "yes_price": event_dict["yes_price"],
                            "no_price": event_dict["no_price"],
                            "order_book_yes": event_dict.get("order_book_yes"),
                            "order_book_no": event_dict.get("order_book_no"),
                            "last_update": event_dict["last_update"],
                        },
                    }
                )

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
