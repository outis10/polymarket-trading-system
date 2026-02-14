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


# --- WebSocket message envelopes ---


class PriceUpdatePayload(BaseModel):
    current_price: float = 0.0
    price_change: float = 0.0
    yes_price: float = 0.50
    no_price: float = 0.50
    price_history_point: Optional[PriceHistoryPoint] = None


class OrderBookUpdatePayload(BaseModel):
    order_book_yes: Optional[OrderBookData] = None
    order_book_no: Optional[OrderBookData] = None


class WSMessage(BaseModel):
    type: (
        str  # "price_update" | "orderbook_update" | "full_snapshot" | "settings_update"
    )
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
    mode: str = "demo"
    refresh_rate: int = 1
    timeframe_filter: str = "15m"
    chart_options: list[str] = [
        "show_chart",
        "show_probability",
        "show_price_change",
    ]
