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
    vol_rv_current: Optional[float] = None
    vol_rv_avg: Optional[float] = None
    vol_rv_pct_of_avg: Optional[float] = None
    vol_noise_ratio: Optional[float] = None
    vol_range_pct: Optional[float] = None
    vol_gate_enabled: Optional[bool] = None
    vol_gate_blocked: Optional[bool] = None
    vol_gate_reason: Optional[str] = None
    vol_gate_history_size: Optional[int] = None
    vol_gate_avg_rv: Optional[float] = None
    vol_gate_prev_rv: Optional[float] = None
    vol_gate_threshold_rv: Optional[float] = None
    vol_gate_prev_pct_of_avg: Optional[float] = None
    vol_gate_min_pct_of_avg: Optional[float] = None


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
    vol_rv_current: Optional[float] = None
    vol_rv_avg: Optional[float] = None
    vol_rv_pct_of_avg: Optional[float] = None
    vol_noise_ratio: Optional[float] = None
    vol_range_pct: Optional[float] = None
    vol_gate_enabled: Optional[bool] = None
    vol_gate_blocked: Optional[bool] = None
    vol_gate_reason: Optional[str] = None
    vol_gate_history_size: Optional[int] = None
    vol_gate_avg_rv: Optional[float] = None
    vol_gate_prev_rv: Optional[float] = None
    vol_gate_threshold_rv: Optional[float] = None
    vol_gate_prev_pct_of_avg: Optional[float] = None
    vol_gate_min_pct_of_avg: Optional[float] = None


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
    # Legacy fallback bankroll (kept for backward compatibility).
    kelly_bankroll: float = 100.0
    # Manual bankroll used for live sizing when API balance is unavailable.
    kelly_live_bankroll_usd: float = 100.0
    # Manual bankroll used for paper-mode sizing.
    kelly_paper_bankroll_usd: float = 100.0
    # If true, paper bankroll compounds with resolved pnl_simulated.
    paper_compound_enabled: bool = True
    # Current bankroll used by paper compounding mode.
    paper_current_bankroll_usd: float = 100.0
    # Baseline bankroll captured on first real live fill for live equity curve.
    live_equity_start_bankroll_usd: float = 0.0
    # UTC timestamp when live equity baseline was captured.
    live_equity_start_at_utc: str = ""
    kelly_min_edge_pct: float = 0.5
    kelly_max_bet_pct: float = 25.0
    kelly_max_event_exposure_pct: float = 25.0
    quant_gate_enabled: bool = True
    quant_gate_min_sample: int = 120
    quant_gate_min_edge_pct: float = 4.0
    quant_gate_min_price_c: float = 10.0
    quant_gate_max_price_c: float = 90.0
    quant_gate_edge_vs_ask_enabled: bool = False
    quant_gate_min_edge_vs_ask_pct: float = 2.0
    quant_gate_min_ask_price: float = 0.0
    quant_gate_max_ask_price: float = 0.0
    quant_gate_min_prob: float = 0.0
    quant_gate_min_diff_pct: float = 0.0
    quant_gate_min_sample_strong_signal: int = 20
    quant_gate_strong_signal_threshold: float = 0.72
    vol_gate_enabled: bool = False
    vol_gate_lookback_n: int = 20
    vol_gate_min_pct_of_avg: float = 0.8
    monitored_tickers: list[str] = ["BTC", "ETH", "SOL", "XRP"]
    bot_risk_enabled: bool = True
    bot_max_buys_per_event_side: int = 1
    bot_cooldown_seconds_per_event_side: int = 60
    bot_global_min_seconds_between_orders: int = 2
    bot_max_event_exposure_pct: float = 15.0
    bot_drawdown_enabled: bool = True
    bot_drawdown_stop_pct: float = 50.0
    bot_order_notional_cap_usd: float = 5.0
    bot_order_mode: str = "fak"
    bot_limit_ttl_secs: float = 2.0
    bot_paper_mode: bool = False
    bot_second_entry_opposite_enabled: bool = False
    bot_second_entry_max_ask_price: float = 0.0
    bot_second_entry_min_edge_pct: float = 5.0
    bot_trade_ladder: list[dict] = []
    pm_min_shares: float = 5.0
    pm_min_notional_usd: float = 1.0
    # Order book streaming controls
    order_book_max_levels: int = 8
    order_book_min_broadcast_ms: int = 120
    # Bot order controls
    bot_enforce_timeframe_filter: bool = True
    bot_min_seconds_before_end: int = 30
    take_profit_enabled: bool = False
    take_profit_trigger_price: float = 0.95
    take_profit_min_price: float = 0.90
