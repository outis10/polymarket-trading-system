"""Pydantic models for API responses and WebSocket messages."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OrderBookLevel(BaseModel):
    price: float
    shares: float
    total: float


class OrderBookData(BaseModel):
    bids: list[OrderBookLevel] = []
    asks: list[OrderBookLevel] = []
    last_price: float = 0.50
    spread: float = 0.01
    volume: float = 0.0


class PriceHistoryPoint(BaseModel):
    timestamp: str
    price: float
    yes_price: float = 0.50
    no_price: float = 0.50
    percent_change: float = 0.0
    price_to_beat: float = 0.0


class EventData(BaseModel):
    name: str
    description: str
    icon: str = "generic"
    price_history: list[PriceHistoryPoint] = []
    yes_price: float = 0.50
    no_price: float = 0.50
    current_price: float = 0.0
    price_to_beat: float = 0.0
    price_to_beat_source: Optional[str] = None
    last_update: str = ""
    price_change: float = 0.0
    volume_24h: float = 0.0
    condition_id: str = ""
    yes_token_id: str = ""
    no_token_id: str = ""
    order_book_yes: Optional[OrderBookData] = None
    order_book_no: Optional[OrderBookData] = None
    event_start_utc: Optional[str] = None
    event_end_utc: Optional[str] = None
    timeframe_minutes: int = 15
    timeframe_label: str = "15m"
    quant_prob_up: Optional[float] = None
    quant_prob_down: Optional[float] = None
    quant_sample_size: Optional[int] = None
    quant_range_histogram: Optional[dict] = None
    quant_buy_gate: Optional[dict] = None


# --- WebSocket message envelopes ---


class PriceUpdatePayload(BaseModel):
    current_price: float = 0.0
    price_change: float = 0.0
    yes_price: float = 0.50
    no_price: float = 0.50
    price_history_point: Optional[PriceHistoryPoint] = None
    quant_prob_up: Optional[float] = None
    quant_prob_down: Optional[float] = None
    quant_sample_size: Optional[int] = None
    quant_range_histogram: Optional[dict] = None
    quant_buy_gate: Optional[dict] = None


class OrderBookUpdatePayload(BaseModel):
    order_book_yes: Optional[OrderBookData] = None
    order_book_no: Optional[OrderBookData] = None


class WSMessage(BaseModel):
    type: str  # "price_update" | "orderbook_update" | "quant_metrics_update" | "full_snapshot" | "settings_update"
    event_id: str = ""
    data: dict = {}


# --- REST request/response ---


class OrderRequest(BaseModel):
    event_id: str
    side: str  # "Buy" | "Sell"
    outcome: str  # "up" | "down"
    order_type: str = "limit"  # "market" | "limit"
    price: float = 0.50
    shares: float = 0


class OrderResponse(BaseModel):
    order_id: str = ""
    status: str = "PENDING"
    message: str = ""


class SettingsData(BaseModel):
    mode: str = "live"
    refresh_rate: int = 1
    timeframe_filter: str = "5m"
    trading_mode: str = "bot"
    chart_options: list[str] = ["show_chart"]
    kelly_enabled: bool = True
    kelly_fraction: float = 0.25
    kelly_bankroll: float = 100.0
    kelly_min_edge_pct: float = 0.5
    kelly_max_bet_pct: float = 25.0
    kelly_max_event_exposure_pct: float = 25.0
    quant_gate_enabled: bool = True
    quant_gate_min_sample: int = 120
    quant_gate_min_edge_pct: float = 4.0
    quant_gate_use_percentile: bool = True
    quant_gate_percentile_low: float = 15.0
    quant_gate_percentile_high: float = 85.0
    quant_gate_min_price_c: float = 10.0
    quant_gate_max_price_c: float = 90.0
    quant_gate_edge_vs_ask_enabled: bool = False
    quant_gate_min_edge_vs_ask_pct: float = 2.0
    quant_gate_min_prob: float = 0.0
    quant_gate_min_diff_pct: float = 0.0
    quant_gate_min_sample_strong_signal: int = 20
    quant_gate_strong_signal_threshold: float = 0.72
    early_window_enabled: bool = True
    early_window_seconds: int = 50
    early_quant_gate_min_sample: int = 90
    early_quant_gate_min_edge_pct: float = 4.0
    early_quant_gate_edge_vs_ask_enabled: bool = False
    early_quant_gate_min_edge_vs_ask_pct: float = 2.0
    early_quant_gate_min_prob: float = 0.0
    early_quant_gate_min_diff_pct: float = 0.0
    late_window_enabled: bool = True
    late_window_seconds: int = 120
    late_quant_gate_min_sample: int = 70
    late_quant_gate_min_edge_pct: float = 3.0
    late_quant_gate_edge_vs_ask_enabled: bool = False
    late_quant_gate_min_edge_vs_ask_pct: float = 1.0
    late_quant_gate_min_prob: float = 0.0
    late_quant_gate_min_diff_pct: float = 0.0
    monitored_tickers: list[str] = ["BTC", "ETH", "SOL", "XRP"]
    bot_risk_enabled: bool = True
    bot_max_buys_per_event_side: int = 1
    bot_cooldown_seconds_per_event_side: int = 60
    bot_global_min_seconds_between_orders: int = 2
    bot_max_event_exposure_pct: float = 15.0
    bot_max_ticker_exposure_pct: float = 25.0
    bot_order_notional_cap_usd: float = 5.0
    pm_min_shares: float = 5.0
    pm_min_notional_usd: float = 1.0
