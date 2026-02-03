#!/usr/bin/env python3
"""
Polymarket Multi-Event Monitor GUI
==================================
Interactive dashboard for monitoring multiple Polymarket events simultaneously.

Run with: streamlit run monitor_gui.py

Features:
- Monitor multiple events simultaneously
- Real-time price charts
- Trading panel for each event (Buy/Sell)
- Demo mode with simulated data
- Live mode with real Polymarket data
"""

import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yaml
from plotly.subplots import make_subplots

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import Polymarket client (optional for demo mode)
try:
    from config.settings import Settings
    from core.client_wrapper import PolymarketClient

    POLYMARKET_AVAILABLE = True
except ImportError:
    POLYMARKET_AVAILABLE = False


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class OrderBookLevel:
    """Represents a single price level in the order book"""

    price: float  # Price in decimal (0.95 = 95¢)
    shares: float  # Number of shares at this level
    total: float  # Cumulative total in dollars


@dataclass
class OrderBook:
    """Order book data for an outcome"""

    bids: List[OrderBookLevel] = field(default_factory=list)  # Buy orders (green)
    asks: List[OrderBookLevel] = field(default_factory=list)  # Sell orders (red)
    last_price: float = 0.50
    spread: float = 0.01
    volume: float = 0.0


@dataclass
class EventData:
    """Holds real-time data for an event"""

    name: str
    description: str
    icon: str
    price_history: List[Dict] = field(default_factory=list)
    yes_price: float = 0.50
    no_price: float = 0.50
    current_price: float = 0.0
    price_to_beat: float = 0.0
    last_update: datetime = field(default_factory=datetime.now)
    price_change: float = 0.0
    volume_24h: float = 0.0
    condition_id: str = ""
    yes_token_id: str = ""
    no_token_id: str = ""
    order_book_yes: OrderBook = field(default_factory=OrderBook)
    order_book_no: OrderBook = field(default_factory=OrderBook)
    event_end_utc: Optional[datetime] = None


# =============================================================================
# PAGE CONFIG
# =============================================================================

st.set_page_config(
    page_title="Polymarket Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =============================================================================
# CUSTOM CSS - Polymarket-style dark theme
# =============================================================================

st.markdown(
    """
<style>
    /* Main background */
    .stApp {
        background-color: #0d1117;
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Event card container */
    .event-card {
        background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid #30363d;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    /* Event header */
    .event-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 15px;
    }

    .event-icon {
        width: 48px;
        height: 48px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
    }

    .event-icon-btc { background: linear-gradient(135deg, #f7931a, #ffab40); }
    .event-icon-eth { background: linear-gradient(135deg, #627eea, #8c9eff); }
    .event-icon-sol { background: linear-gradient(135deg, #9945ff, #14f195); }
    .event-icon-generic { background: linear-gradient(135deg, #58a6ff, #1f6feb); }

    .event-title {
        font-size: 18px;
        font-weight: 600;
        color: #e6edf3;
        margin: 0;
    }

    .event-subtitle {
        font-size: 13px;
        color: #8b949e;
        margin: 0;
    }

    /* Price display */
    .price-container {
        display: flex;
        gap: 40px;
        margin: 15px 0;
    }

    .price-box {
        display: flex;
        flex-direction: column;
    }

    .price-label {
        font-size: 12px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .price-value {
        font-size: 28px;
        font-weight: 700;
        color: #e6edf3;
    }

    .price-value-green {
        color: #3fb950;
    }

    .price-change {
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 4px;
    }

    .price-change-positive { color: #3fb950; }
    .price-change-negative { color: #f85149; }

    /* Countdown timer */
    .countdown {
        display: flex;
        gap: 8px;
        align-items: center;
    }

    .countdown-value {
        font-size: 32px;
        font-weight: 700;
        color: #f85149;
    }

    .countdown-label {
        font-size: 10px;
        color: #8b949e;
        text-transform: uppercase;
    }

    /* Trading panel */
    .trading-panel {
        background: #161b22;
        border-radius: 12px;
        padding: 16px;
        border: 1px solid #30363d;
    }

    .trading-tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
    }

    .tab-button {
        flex: 1;
        padding: 8px 16px;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
    }

    .tab-buy { background: #238636; color: white; }
    .tab-sell { background: #30363d; color: #8b949e; }

    /* Outcome buttons */
    .outcome-buttons {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
    }

    .outcome-btn {
        flex: 1;
        padding: 12px;
        border-radius: 8px;
        font-weight: 600;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s;
    }

    .outcome-up {
        background: #238636;
        color: white;
    }

    .outcome-down {
        background: #30363d;
        color: #8b949e;
        border: 1px solid #484f58;
    }

    /* Input fields */
    .input-group {
        margin-bottom: 12px;
    }

    .input-label {
        font-size: 13px;
        color: #8b949e;
        margin-bottom: 6px;
    }

    .input-row {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Quick amount buttons */
    .quick-amounts {
        display: flex;
        gap: 4px;
    }

    .quick-btn {
        padding: 6px 12px;
        background: #21262d;
        border: 1px solid #30363d;
        border-radius: 6px;
        color: #8b949e;
        font-size: 12px;
        cursor: pointer;
    }

    /* Trade button */
    .trade-btn {
        width: 100%;
        padding: 14px;
        background: linear-gradient(135deg, #1f6feb, #58a6ff);
        border: none;
        border-radius: 10px;
        color: white;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        margin-top: 16px;
    }

    .trade-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(31, 111, 235, 0.4);
    }

    /* Summary row */
    .summary-row {
        display: flex;
        justify-content: space-between;
        padding: 8px 0;
        border-top: 1px solid #21262d;
        margin-top: 8px;
    }

    .summary-label {
        color: #8b949e;
        font-size: 14px;
    }

    .summary-value {
        color: #e6edf3;
        font-weight: 600;
    }

    .summary-value-green {
        color: #3fb950;
    }

    /* Streamlit overrides */
    .stButton>button {
        width: 100%;
    }

    div[data-testid="stMetricValue"] {
        font-size: 24px;
    }

    .stRadio > label {
        background: #21262d;
        padding: 8px 16px;
        border-radius: 8px;
        margin-right: 8px;
    }

    /* Time filter buttons */
    .time-filters {
        display: flex;
        gap: 4px;
        padding: 8px 0;
    }

    .time-btn {
        padding: 6px 12px;
        background: transparent;
        border: none;
        color: #8b949e;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
    }

    .time-btn-active {
        background: #f85149;
        color: white;
    }

    /* =========================================
       ORDER BOOK STYLES
       ========================================= */

    .order-book-card {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
        border-radius: 12px;
        border: 1px solid #30363d;
        padding: 16px;
        margin-top: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    .order-book-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #21262d;
    }

    .order-book-title {
        font-size: 16px;
        font-weight: 600;
        color: #e6edf3;
        margin: 0;
    }

    .order-book-volume {
        font-size: 12px;
        color: #8b949e;
    }

    .order-book-tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
    }

    .order-book-tab {
        flex: 1;
        padding: 8px 16px;
        border: 1px solid #30363d;
        border-radius: 8px;
        font-weight: 500;
        font-size: 13px;
        cursor: pointer;
        transition: all 0.2s;
        text-align: center;
        background: #21262d;
        color: #8b949e;
    }

    .order-book-tab-active {
        background: linear-gradient(135deg, #1f6feb, #58a6ff);
        border-color: #1f6feb;
        color: white;
    }

    .order-book-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
        font-size: 12px;
    }

    .order-book-table th {
        text-align: right;
        padding: 6px 8px;
        color: #8b949e;
        font-weight: 500;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-bottom: 1px solid #21262d;
    }

    .order-book-table th:first-child {
        text-align: left;
    }

    .order-book-section-label {
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
        margin: 8px 0 4px 0;
    }

    .order-book-asks-label {
        background: rgba(248, 81, 73, 0.2);
        color: #f85149;
    }

    .order-book-bids-label {
        background: rgba(63, 185, 80, 0.2);
        color: #3fb950;
    }

    .order-book-row {
        position: relative;
        transition: background 0.15s;
    }

    .order-book-row:hover {
        background: rgba(48, 54, 61, 0.5);
        cursor: pointer;
    }

    .order-book-row td {
        padding: 6px 8px;
        text-align: right;
        position: relative;
        z-index: 1;
    }

    .order-book-row td:first-child {
        text-align: left;
    }

    .order-book-ask-row td:first-child {
        color: #f85149;
        font-weight: 600;
    }

    .order-book-bid-row td:first-child {
        color: #3fb950;
        font-weight: 600;
    }

    .order-book-row td:not(:first-child) {
        color: #e6edf3;
    }

    .order-book-depth-bar {
        position: absolute;
        top: 0;
        bottom: 0;
        opacity: 0.15;
        z-index: 0;
    }

    .order-book-depth-ask {
        right: 0;
        background: linear-gradient(to left, #f85149, transparent);
    }

    .order-book-depth-bid {
        left: 0;
        background: linear-gradient(to right, #3fb950, transparent);
    }

    .order-book-midpoint {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 8px;
        margin: 8px 0;
        background: #21262d;
        border-radius: 6px;
        border-left: 3px solid #58a6ff;
    }

    .order-book-midpoint-item {
        font-size: 12px;
    }

    .order-book-midpoint-label {
        color: #8b949e;
        margin-right: 4px;
    }

    .order-book-midpoint-value {
        color: #e6edf3;
        font-weight: 600;
        font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
    }

    .order-book-best-ask {
        box-shadow: inset 0 0 0 1px rgba(248, 81, 73, 0.5);
    }

    .order-book-best-bid {
        box-shadow: inset 0 0 0 1px rgba(63, 185, 80, 0.5);
    }
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def load_config() -> Dict:
    """Load events configuration from YAML"""
    config_path = os.path.join(os.path.dirname(__file__), "config", "events.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        st.error(f"Configuration file not found: {config_path}")
        return {}


def get_icon_html(icon: str) -> str:
    """Get icon HTML based on type"""
    icons = {
        "btc": '<div class="event-icon event-icon-btc">₿</div>',
        "eth": '<div class="event-icon event-icon-eth">Ξ</div>',
        "sol": '<div class="event-icon event-icon-sol">◎</div>',
        "generic": '<div class="event-icon event-icon-generic">📊</div>',
    }
    return icons.get(icon, icons["generic"])


def generate_price_history(
    base_price: float, volatility: float, points: int = 100, price_to_beat: float = None
) -> List[Dict]:
    """
    Generate simulated price history for demo mode with dual series data.

    Args:
        base_price: Starting price (e.g., BTC price)
        volatility: Price volatility factor
        points: Number of data points to generate
        price_to_beat: Reference price for calculating probability (defaults to base_price)

    Returns:
        List of dicts with: timestamp, price, yes_price, no_price, percent_change
    """
    history = []
    price = base_price
    reference_price = price_to_beat if price_to_beat else base_price
    now = datetime.now()

    for i in range(points):
        timestamp = now - timedelta(seconds=(points - i) * 5)
        change = random.gauss(0, volatility * price)
        price = max(price + change, base_price * 0.95)  # Prevent going too low
        price = min(price, base_price * 1.05)  # Prevent going too high

        # Calculate percentage change from reference price
        percent_change = ((price - reference_price) / reference_price) * 100

        # Calculate YES/NO probability based on price vs reference
        # If price > reference, YES probability increases
        # Scale: ±2% price change = ±40% probability swing from 50%
        probability_swing = (price - reference_price) / reference_price * 20
        yes_price = max(0.01, min(0.99, 0.50 + probability_swing))
        no_price = 1 - yes_price

        history.append(
            {
                "timestamp": timestamp,
                "price": price,
                "yes_price": yes_price,
                "no_price": no_price,
                "percent_change": percent_change,
                "price_to_beat": reference_price,
            }
        )

    return history


def generate_order_book(
    mid_price: float,
    num_levels: int = 5,
    base_volume: float = 500.0,
    volatility: float = 0.3,
) -> OrderBook:
    """
    Generate a realistic simulated order book.

    Args:
        mid_price: Current market price (0-1, e.g., 0.95 = 95¢)
        num_levels: Number of price levels on each side
        base_volume: Base volume for order sizes
        volatility: Randomness factor for order sizes

    Returns:
        OrderBook with bids and asks
    """
    bids = []
    asks = []

    # Calculate spread (1-2 cents typically)
    spread = 0.01
    best_bid = mid_price - spread / 2
    best_ask = mid_price + spread / 2

    # Ensure prices stay in valid range
    best_bid = max(0.01, min(0.98, best_bid))
    best_ask = max(0.02, min(0.99, best_ask))

    # Generate asks (sell orders) - from best ask going up
    cumulative_total = 0.0
    for i in range(num_levels):
        price = best_ask + (i * 0.01)
        if price > 0.99:
            break
        # Randomize shares with some clustering near best price
        shares = (
            base_volume * (1 + random.uniform(-volatility, volatility)) * (1 + i * 0.3)
        )
        cumulative_total += shares * price
        asks.append(
            OrderBookLevel(
                price=round(price, 2),
                shares=round(shares, 2),
                total=round(cumulative_total, 2),
            )
        )

    # Generate bids (buy orders) - from best bid going down
    cumulative_total = 0.0
    for i in range(num_levels):
        price = best_bid - (i * 0.01)
        if price < 0.01:
            break
        # Randomize shares
        shares = (
            base_volume * (1 + random.uniform(-volatility, volatility)) * (1 + i * 0.3)
        )
        cumulative_total += shares * price
        bids.append(
            OrderBookLevel(
                price=round(price, 2),
                shares=round(shares, 2),
                total=round(cumulative_total, 2),
            )
        )

    # Calculate total volume
    total_volume = sum(a.shares * a.price for a in asks) + sum(
        b.shares * b.price for b in bids
    )

    return OrderBook(
        bids=bids,
        asks=asks,
        last_price=round(mid_price, 2),
        spread=round(best_ask - best_bid, 2),
        volume=round(total_volume, 2),
    )


def update_order_book(
    order_book: OrderBook, mid_price: float, volatility: float = 0.1
) -> OrderBook:
    """
    Update an existing order book with small random changes.

    Args:
        order_book: Existing order book to update
        mid_price: Current market price
        volatility: How much to vary the order sizes

    Returns:
        Updated OrderBook
    """
    # Update asks
    for level in order_book.asks:
        # Small random change in shares
        change = random.gauss(0, level.shares * volatility * 0.1)
        level.shares = max(10, level.shares + change)
        level.shares = round(level.shares, 2)

    # Update bids
    for level in order_book.bids:
        change = random.gauss(0, level.shares * volatility * 0.1)
        level.shares = max(10, level.shares + change)
        level.shares = round(level.shares, 2)

    # Recalculate cumulative totals for asks
    cumulative = 0.0
    for level in order_book.asks:
        cumulative += level.shares * level.price
        level.total = round(cumulative, 2)

    # Recalculate cumulative totals for bids
    cumulative = 0.0
    for level in order_book.bids:
        cumulative += level.shares * level.price
        level.total = round(cumulative, 2)

    # Update spread based on new mid price
    spread = 0.01
    best_bid = mid_price - spread / 2
    best_ask = mid_price + spread / 2

    order_book.last_price = round(mid_price, 2)
    order_book.spread = round(best_ask - best_bid, 2)
    order_book.volume = round(
        sum(a.shares * a.price for a in order_book.asks)
        + sum(b.shares * b.price for b in order_book.bids),
        2,
    )

    return order_book


def update_demo_prices(event_data: EventData, config: Dict) -> EventData:
    """
    Update prices for demo mode with realistic simulation.

    Generates both price and percentage series data for dual-axis chart.
    """
    # Simulate price movement
    change = random.gauss(0, config.get("volatility", 0.02) * event_data.current_price)
    new_price = event_data.current_price + change

    # Calculate price change from start
    old_price = event_data.current_price
    event_data.current_price = new_price
    event_data.price_change = (
        ((new_price - old_price) / old_price) * 100 if old_price > 0 else 0
    )

    # Calculate percentage change from reference price (price_to_beat)
    percent_change_from_ref = (
        ((new_price - event_data.price_to_beat) / event_data.price_to_beat) * 100
        if event_data.price_to_beat > 0
        else 0
    )

    # Update YES/NO prices based on current vs target
    # Scale: ±2% price change = ±40% probability swing from 50%
    probability_swing = (
        (new_price - event_data.price_to_beat) / event_data.price_to_beat * 20
    )
    event_data.yes_price = max(0.01, min(0.99, 0.50 + probability_swing))
    event_data.no_price = 1 - event_data.yes_price

    # Update price history with all series data
    event_data.price_history.append(
        {
            "timestamp": datetime.now(),
            "price": new_price,
            "yes_price": event_data.yes_price,
            "no_price": event_data.no_price,
            "percent_change": percent_change_from_ref,
            "price_to_beat": event_data.price_to_beat,
        }
    )

    # Keep only last 500 points
    if len(event_data.price_history) > 500:
        event_data.price_history = event_data.price_history[-500:]

    # Update order books for both YES and NO outcomes
    if event_data.order_book_yes.bids or event_data.order_book_yes.asks:
        event_data.order_book_yes = update_order_book(
            event_data.order_book_yes, event_data.yes_price
        )
    else:
        event_data.order_book_yes = generate_order_book(event_data.yes_price)

    if event_data.order_book_no.bids or event_data.order_book_no.asks:
        event_data.order_book_no = update_order_book(
            event_data.order_book_no, event_data.no_price
        )
    else:
        event_data.order_book_no = generate_order_book(event_data.no_price)

    event_data.last_update = datetime.now()

    return event_data


def create_price_chart(
    price_history: List[Dict],
    height: int = 350,
    show_probability: bool = True,
    show_price_change: bool = True,
    chart_id: str = "",
) -> go.Figure:
    """
    Create a Polymarket-style price chart with dual series.

    Shows:
    - Price series (BTC price in dollars) - Orange line
    - Probability series (YES probability %) - Green/Red line
    - Price change series (% from reference) - Blue dotted line

    Args:
        price_history: List of dicts with timestamp, price, yes_price, percent_change
        height: Chart height in pixels
        show_probability: Whether to show the YES probability series
        show_price_change: Whether to show the price change % series
    """
    if not price_history:
        # Empty chart — use chart_id in title to make the figure unique per event
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            height=height,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            title=dict(text=chart_id, font=dict(size=1, color="rgba(0,0,0,0)")),
        )
        return fig

    df = pd.DataFrame(price_history)

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Main price line (left y-axis) - Orange
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["price"],
            mode="lines",
            name="BTC Price",
            line=dict(color="#f7931a", width=2),
            fill="tozeroy",
            fillcolor="rgba(247, 147, 26, 0.1)",
            hovertemplate="$%{y:,.2f}<extra>BTC Price</extra>",
        ),
        secondary_y=False,
    )

    # Probability series (right y-axis) - Show YES probability as percentage
    if show_probability and "yes_price" in df.columns:
        # Convert yes_price (0-1) to percentage (0-100)
        df["yes_percent"] = df["yes_price"] * 100

        # Determine color based on trend (green if above 50%, red if below)
        avg_yes = df["yes_percent"].mean()
        percent_color = "#3fb950" if avg_yes >= 50 else "#f85149"

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["yes_percent"],
                mode="lines",
                name="UP Probability",
                line=dict(color=percent_color, width=2, dash="solid"),
                hovertemplate="%{y:.1f}%<extra>UP Probability</extra>",
            ),
            secondary_y=True,
        )

    # Price change percentage series (if available)
    if show_price_change and "percent_change" in df.columns:
        # Color based on positive/negative
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["percent_change"],
                mode="lines",
                name="Price Change %",
                line=dict(color="#58a6ff", width=1.5, dash="dot"),
                hovertemplate="%{y:+.2f}%<extra>Price Change</extra>",
            ),
            secondary_y=True,
        )

    # Style the chart
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            showticklabels=True,
            tickfont=dict(color="#8b949e", size=10),
            tickformat="%H:%M:%S",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, color="#8b949e"),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=True,
        hovermode="x unified",
    )

    # Configure primary y-axis (Price - left side)
    fig.update_yaxes(
        title_text="BTC Price",
        title_font=dict(color="#f7931a", size=11),
        showgrid=True,
        gridcolor="rgba(48, 54, 61, 0.5)",
        tickfont=dict(color="#f7931a", size=10),
        tickprefix="$",
        tickformat=",.0f",
        secondary_y=False,
    )

    # Configure secondary y-axis (Percentage - right side)
    fig.update_yaxes(
        title_text="Probability %",
        title_font=dict(color="#3fb950", size=11),
        showgrid=False,
        tickfont=dict(color="#3fb950", size=10),
        ticksuffix="%",
        range=[0, 100],
        secondary_y=True,
    )

    # Add horizontal line at reference price if available
    if price_history and "price_to_beat" in price_history[0]:
        fig.add_hline(
            y=price_history[0].get("price_to_beat", df["price"].iloc[0]),
            line_dash="dash",
            line_color="rgba(139, 148, 158, 0.5)",
            annotation_text="Target",
            annotation_position="bottom right",
            secondary_y=False,
        )

    # Add 50% reference line for probability
    if show_probability:
        fig.add_hline(
            y=50,
            line_dash="dash",
            line_color="rgba(139, 148, 158, 0.3)",
            annotation_text="50%",
            annotation_position="left",
            secondary_y=True,
        )

    return fig


def format_price_change(change: float) -> str:
    """Format price change with color"""
    if change >= 0:
        return f'<span class="price-change price-change-positive">▲ ${abs(change):,.2f}</span>'
    else:
        return f'<span class="price-change price-change-negative">▼ ${abs(change):,.2f}</span>'


# =============================================================================
# INITIALIZE SESSION STATE
# =============================================================================


def init_session_state():
    """Initialize session state variables"""
    if "events_data" not in st.session_state:
        st.session_state.events_data = {}

    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = datetime.now()

    if "selected_outcomes" not in st.session_state:
        st.session_state.selected_outcomes = {}

    if "shares" not in st.session_state:
        st.session_state.shares = {}

    if "limit_prices" not in st.session_state:
        st.session_state.limit_prices = {}


def load_demo_events(config: Dict) -> Dict[str, EventData]:
    """Load demo events from configuration"""
    events = {}
    demo_events = config.get("demo_events", [])

    for event_config in demo_events:
        event_id = event_config["name"].lower().replace(" ", "_")

        # Get price_to_beat (reference price for probability calculation)
        price_to_beat = event_config.get("price_to_beat", event_config["initial_price"])

        # Generate initial price history with dual series data
        history = generate_price_history(
            event_config["initial_price"],
            event_config.get("volatility", 0.02),
            100,
            price_to_beat=price_to_beat,
        )

        # Get initial YES/NO prices
        yes_price = event_config.get("yes_price", 0.50)
        no_price = event_config.get("no_price", 0.50)

        # Generate initial order books
        order_book_yes = generate_order_book(yes_price)
        order_book_no = generate_order_book(no_price)

        events[event_id] = EventData(
            name=event_config["name"],
            description=event_config["description"],
            icon=event_config.get("icon", "generic"),
            price_history=history,
            yes_price=yes_price,
            no_price=no_price,
            current_price=event_config["initial_price"],
            price_to_beat=price_to_beat,
            price_change=0,
            order_book_yes=order_book_yes,
            order_book_no=order_book_no,
        )

    return events


# =============================================================================
# ORDER BOOK COMPONENT
# =============================================================================


def render_order_book(
    event_id: str, order_book_yes: OrderBook, order_book_no: OrderBook
):
    """
    Render the order book component with tabs for UP/DOWN outcomes.
    Uses Streamlit's st.dataframe with column_config for professional styling.

    Args:
        event_id: Unique identifier for the event
        order_book_yes: Order book for YES (Up) outcome
        order_book_no: Order book for NO (Down) outcome
    """
    # Initialize tab state if needed
    tab_key = f"order_book_tab_{event_id}"
    if tab_key not in st.session_state:
        st.session_state[tab_key] = "up"

    # Get the active order book based on selected tab
    active_tab = st.session_state.get(tab_key, "up")
    order_book = order_book_yes if active_tab == "up" else order_book_no

    # Calculate total volume for display (convert to thousands)
    total_volume = (order_book_yes.volume + order_book_no.volume) / 1000

    # Order Book Container with styled header
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
                    border-radius: 12px; border: 1px solid #30363d; padding: 16px; margin-top: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center;
                        margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #21262d;">
                <span style="font-size: 16px; font-weight: 600; color: #e6edf3;">Order Book</span>
                <span style="font-size: 12px; color: #8b949e;">${total_volume:,.1f}k Vol</span>
            </div>
        </div>
    """,
        unsafe_allow_html=True,
    )

    # Tabs for UP/DOWN using Streamlit buttons
    tab_col1, tab_col2 = st.columns(2)
    with tab_col1:
        if st.button(
            f"▲ Trade Up",
            key=f"{event_id}_ob_tab_up",
            type="primary" if active_tab == "up" else "secondary",
            use_container_width=True,
        ):
            st.session_state[tab_key] = "up"
            st.rerun()

    with tab_col2:
        if st.button(
            f"▼ Trade Down",
            key=f"{event_id}_ob_tab_down",
            type="primary" if active_tab == "down" else "secondary",
            use_container_width=True,
        ):
            st.session_state[tab_key] = "down"
            st.rerun()

    # Calculate max shares for depth bar scaling (used for progress columns)
    max_shares = 1
    if order_book.asks:
        max_shares = max(max_shares, max(level.shares for level in order_book.asks))
    if order_book.bids:
        max_shares = max(max_shares, max(level.shares for level in order_book.bids))

    # Midpoint calculations
    best_ask = order_book.asks[0].price if order_book.asks else 0.50
    best_bid = order_book.bids[0].price if order_book.bids else 0.49
    spread_cents = int((best_ask - best_bid) * 100)
    last_price_cents = int(order_book.last_price * 100)

    # ASKS Section (Sell orders)
    st.markdown(
        """
        <span style="color: #f85149; font-size: 11px; font-weight: 600;
                     text-transform: uppercase; background: rgba(248,81,73,0.2);
                     padding: 2px 8px; border-radius: 4px;">🔴 Asks (Sell Orders)</span>
    """,
        unsafe_allow_html=True,
    )

    # Build asks dataframe with numeric values for proper formatting
    asks_reversed = list(reversed(order_book.asks)) if order_book.asks else []
    if asks_reversed:
        asks_df = pd.DataFrame(
            [
                {
                    "Price (¢)": int(level.price * 100),
                    "Shares": level.shares,
                    "Total ($)": level.total,
                    "Depth": level.shares / max_shares,  # Normalized for progress bar
                }
                for level in asks_reversed
            ]
        )

        st.dataframe(
            asks_df,
            use_container_width=True,
            hide_index=True,
            height=min(35 * len(asks_df) + 38, 200),
            column_config={
                "Price (¢)": st.column_config.NumberColumn(
                    "Price (¢)",
                    help="Price in cents",
                    format="%d¢",
                ),
                "Shares": st.column_config.NumberColumn(
                    "Shares",
                    help="Number of shares available",
                    format="%.2f",
                ),
                "Total ($)": st.column_config.NumberColumn(
                    "Total ($)",
                    help="Cumulative dollar value",
                    format="$%.2f",
                ),
                "Depth": st.column_config.ProgressColumn(
                    "Depth",
                    help="Order depth visualization",
                    format="%.0f%%",
                    min_value=0,
                    max_value=1,
                ),
            },
        )
    else:
        st.caption("No asks available")

    # Midpoint divider with spread info
    col_last, col_spread, col_mid = st.columns(3)
    with col_last:
        st.metric("Last Price", f"{last_price_cents}¢")
    with col_spread:
        st.metric("Spread", f"{spread_cents}¢")
    with col_mid:
        mid_price = (best_ask + best_bid) / 2
        st.metric("Mid", f"{int(mid_price * 100)}¢")

    # BIDS Section (Buy orders)
    st.markdown(
        """
        <span style="color: #3fb950; font-size: 11px; font-weight: 600;
                     text-transform: uppercase; background: rgba(63,185,80,0.2);
                     padding: 2px 8px; border-radius: 4px;">🟢 Bids (Buy Orders)</span>
    """,
        unsafe_allow_html=True,
    )

    # Build bids dataframe with numeric values
    if order_book.bids:
        bids_df = pd.DataFrame(
            [
                {
                    "Price (¢)": int(level.price * 100),
                    "Shares": level.shares,
                    "Total ($)": level.total,
                    "Depth": level.shares / max_shares,  # Normalized for progress bar
                }
                for level in order_book.bids
            ]
        )

        st.dataframe(
            bids_df,
            use_container_width=True,
            hide_index=True,
            height=min(35 * len(bids_df) + 38, 200),
            column_config={
                "Price (¢)": st.column_config.NumberColumn(
                    "Price (¢)",
                    help="Price in cents",
                    format="%d¢",
                ),
                "Shares": st.column_config.NumberColumn(
                    "Shares",
                    help="Number of shares available",
                    format="%.2f",
                ),
                "Total ($)": st.column_config.NumberColumn(
                    "Total ($)",
                    help="Cumulative dollar value",
                    format="$%.2f",
                ),
                "Depth": st.column_config.ProgressColumn(
                    "Depth",
                    help="Order depth visualization",
                    format="%.0f%%",
                    min_value=0,
                    max_value=1,
                ),
            },
        )
    else:
        st.caption("No bids available")

    # Order book summary stats
    with st.expander("📊 Order Book Stats", expanded=False):
        stats_col1, stats_col2, stats_col3 = st.columns(3)

        total_ask_volume = (
            sum(level.shares for level in order_book.asks) if order_book.asks else 0
        )
        total_bid_volume = (
            sum(level.shares for level in order_book.bids) if order_book.bids else 0
        )
        imbalance = (
            (total_bid_volume - total_ask_volume)
            / max(total_bid_volume + total_ask_volume, 1)
            * 100
        )

        with stats_col1:
            st.metric("Ask Volume", f"{total_ask_volume:,.0f}")
        with stats_col2:
            st.metric("Bid Volume", f"{total_bid_volume:,.0f}")
        with stats_col3:
            st.metric(
                "Imbalance",
                f"{imbalance:+.1f}%",
                delta="Bullish"
                if imbalance > 0
                else "Bearish"
                if imbalance < 0
                else "Neutral",
                delta_color="normal"
                if imbalance > 0
                else "inverse"
                if imbalance < 0
                else "off",
            )


# =============================================================================
# EVENT WIDGET COMPONENT
# =============================================================================


def render_event_dynamic(event_id: str, event_data: EventData, config: Dict):
    """Render only the dynamic parts of an event: prices, countdown, chart.
    This function is meant to be called inside a @st.fragment so only
    these widgets re-render on each tick."""

    # Price difference vs price_to_beat
    price_diff = event_data.current_price - event_data.price_to_beat
    price_up = price_diff >= 0
    price_change_class = (
        "price-change-positive" if price_up else "price-change-negative"
    )
    price_change_symbol = "▲" if price_up else "▼"

    col_p1, col_p2, col_p3 = st.columns([1, 1, 1])

    with col_p1:
        st.markdown(
            f"""
        <div class="price-box">
            <span class="price-label">PRICE TO BEAT</span>
            <span class="price-value">${event_data.price_to_beat:,.2f}</span>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_p2:
        st.markdown(
            f"""
        <div class="price-box">
            <span class="price-label">CURRENT PRICE</span>
            <span class="price-value price-value-green">${event_data.current_price:,.2f}</span>
            <span class="price-change {price_change_class}">{price_change_symbol} ${abs(price_diff):,.2f}</span>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_p3:
        # Countdown: real time remaining until candle close
        if event_data.event_end_utc:
            from datetime import timezone as tz

            now_utc = datetime.now(tz=tz.utc)
            remaining = event_data.event_end_utc - now_utc
            total_secs = max(0, int(remaining.total_seconds()))
            minutes = total_secs // 60
            seconds = total_secs % 60
        else:
            minutes, seconds = 0, 0

        st.markdown(
            f"""
        <div class="countdown">
            <div>
                <span class="countdown-value">{minutes:02d}</span>
                <span class="countdown-label">MINS</span>
            </div>
            <div>
                <span class="countdown-value">{seconds:02d}</span>
                <span class="countdown-label">SECS</span>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # Price chart with dual series (price + percentage)
    chart = create_price_chart(
        event_data.price_history,
        height=config.get("ui", {}).get("chart_height", 350),
        show_probability=st.session_state.get("show_percentage", True),
        show_price_change=st.session_state.get("show_price_change", True),
        chart_id=event_id,
    )
    st.plotly_chart(
        chart,
        use_container_width=True,
        config={"displayModeBar": False},
        key=f"{event_id}_price_chart",
    )


def render_event_static(event_id: str, event_data: EventData, config: Dict):
    """Render the static/interactive parts: header, time filters, order book, trading panel.
    These are rendered once and don't need periodic refresh."""

    # Main container with two columns: left (time filters + order book) and right (trading)
    col_left, col_trading = st.columns([2, 1])

    with col_left:
        # Time filter buttons
        time_cols = st.columns(8)
        time_options = ["Past", "9 AM", "10 AM", "11 AM", "12 PM", "More"]
        for i, opt in enumerate(time_options):
            if i < len(time_cols):
                time_cols[i].button(
                    opt, key=f"{event_id}_time_{opt}", use_container_width=True
                )

        # Order Book section (below chart)
        if st.session_state.get("show_order_book", True):
            render_order_book(
                event_id, event_data.order_book_yes, event_data.order_book_no
            )

    with col_trading:
        # Trading panel
        st.markdown('<div class="trading-panel">', unsafe_allow_html=True)

        # Buy/Sell tabs
        trade_type = st.radio(
            "Trade Type",
            ["Buy", "Sell"],
            horizontal=True,
            key=f"{event_id}_trade_type",
            label_visibility="collapsed",
        )

        # Order type selector
        order_type = st.selectbox(
            "Order Type",
            ["Limit", "Market"],
            key=f"{event_id}_order_type",
            label_visibility="collapsed",
        )

        st.markdown(
            "<hr style='border-color: #30363d; margin: 10px 0;'>",
            unsafe_allow_html=True,
        )

        # Outcome selection (Up/Down)
        outcome_col1, outcome_col2 = st.columns(2)

        with outcome_col1:
            up_selected = st.button(
                f"Up {event_data.yes_price * 100:.0f}c",
                key=f"{event_id}_up",
                type="primary",
                use_container_width=True,
            )
            if up_selected:
                st.session_state.selected_outcomes[event_id] = "up"

        with outcome_col2:
            down_selected = st.button(
                f"Down {event_data.no_price * 100:.0f}c",
                key=f"{event_id}_down",
                use_container_width=True,
            )
            if down_selected:
                st.session_state.selected_outcomes[event_id] = "down"

        # Get current selection
        current_outcome = st.session_state.selected_outcomes.get(event_id, "up")
        current_price = (
            event_data.yes_price if current_outcome == "up" else event_data.no_price
        )

        # Limit price input
        st.markdown("<br>", unsafe_allow_html=True)
        limit_price = st.number_input(
            "Limit Price",
            min_value=0.01,
            max_value=0.99,
            value=st.session_state.limit_prices.get(event_id, current_price),
            step=0.01,
            format="%.2f",
            key=f"{event_id}_limit_price",
        )
        st.session_state.limit_prices[event_id] = limit_price

        # Shares input with quick buttons
        shares = st.number_input(
            "Shares",
            min_value=0,
            max_value=10000,
            value=st.session_state.shares.get(event_id, 0),
            step=1,
            key=f"{event_id}_shares",
        )
        st.session_state.shares[event_id] = shares

        # Quick amount buttons
        quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)

        with quick_col1:
            if st.button("-100", key=f"{event_id}_minus100", use_container_width=True):
                st.session_state.shares[event_id] = max(0, shares - 100)
                st.rerun()

        with quick_col2:
            if st.button("-10", key=f"{event_id}_minus10", use_container_width=True):
                st.session_state.shares[event_id] = max(0, shares - 10)
                st.rerun()

        with quick_col3:
            if st.button("+10", key=f"{event_id}_plus10", use_container_width=True):
                st.session_state.shares[event_id] = shares + 10
                st.rerun()

        with quick_col4:
            if st.button("+100", key=f"{event_id}_plus100", use_container_width=True):
                st.session_state.shares[event_id] = shares + 100
                st.rerun()

        # Set expiration toggle
        set_expiration = st.toggle("Set Expiration", key=f"{event_id}_expiration")

        st.markdown(
            "<hr style='border-color: #30363d; margin: 10px 0;'>",
            unsafe_allow_html=True,
        )

        # Calculate totals
        total_cost = shares * limit_price
        potential_win = shares * (1 - limit_price) if shares > 0 else 0

        # Summary
        col_total, col_win = st.columns(2)

        with col_total:
            st.metric("Total", f"${total_cost:.2f}")

        with col_win:
            st.metric("To Win", f"${potential_win:.2f}", delta=None)

        # Trade button
        if st.button(
            "Trade",
            key=f"{event_id}_trade",
            type="primary",
            use_container_width=True,
            disabled=(shares == 0),
        ):
            st.success(
                f"Order placed: {trade_type} {shares} shares of {current_outcome.upper()} @ ${limit_price:.2f}"
            )

        st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# BINANCE PRICE HELPERS
# =============================================================================

BINANCE_API = "https://api.binance.com/api/v3"


@st.cache_data(ttl=2)
def fetch_binance_price(symbol: str) -> Optional[float]:
    """Fetch the current price for a Binance symbol (e.g. BTCUSDT)."""
    try:
        resp = requests.get(
            f"{BINANCE_API}/ticker/price",
            params={"symbol": symbol},
            timeout=5,
        )
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception:
        return None


@st.cache_data(ttl=60)
def fetch_binance_candle_open(symbol: str, start_time_ms: int) -> Optional[float]:
    """Fetch the open price of the 1h candle at the given start time."""
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={
                "symbol": symbol,
                "interval": "1h",
                "startTime": start_time_ms,
                "limit": 1,
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0][1])  # Open price
        return None
    except Exception:
        return None


def parse_event_start_ms(event_start_time: str) -> Optional[int]:
    """Parse ISO event_start_time string to epoch milliseconds."""
    if not event_start_time:
        return None
    try:
        from datetime import timezone

        dt = datetime.fromisoformat(event_start_time.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


@st.cache_data(ttl=30)
def fetch_binance_klines(symbol: str, start_time_ms: int) -> List[Dict]:
    """Fetch 1-minute klines from Binance starting at the candle open.

    Returns a list of dicts compatible with price_history:
        timestamp, price, yes_price, no_price, percent_change, price_to_beat
    """
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={
                "symbol": symbol,
                "interval": "1m",
                "startTime": start_time_ms,
                "endTime": start_time_ms + 3_600_000,  # 1 hour window only
                "limit": 60,
            },
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            return []

        open_price = float(raw[0][1])  # price_to_beat = first candle open
        history = []
        for k in raw:
            ts = datetime.utcfromtimestamp(k[0] / 1000)  # naive UTC
            close = float(k[4])
            pct = ((close - open_price) / open_price * 100) if open_price else 0
            # Estimate YES probability: price above open → higher YES
            prob_swing = (close - open_price) / open_price * 20 if open_price else 0
            yes_p = max(0.01, min(0.99, 0.50 + prob_swing))
            history.append(
                {
                    "timestamp": ts,
                    "price": close,
                    "yes_price": yes_p,
                    "no_price": 1 - yes_p,
                    "percent_change": pct,
                    "price_to_beat": open_price,
                }
            )
        return history
    except Exception:
        return []


# =============================================================================
# MAIN APPLICATION
# =============================================================================


def fetch_real_prices(client, event_config: Dict) -> Optional[Dict]:
    """
    Fetch real prices from Polymarket API.

    Args:
        client: PolymarketClient instance
        event_config: Event configuration with token IDs

    Returns:
        Dictionary with prices or None if error
    """
    try:
        tokens = event_config.get("tokens", {})
        yes_token = tokens.get("yes")
        no_token = tokens.get("no")

        if not yes_token or not no_token:
            return None

        # Fetch order books (returns OrderBookSummary dataclass)
        yes_ob = client.get_order_book(yes_token)
        no_ob = client.get_order_book(no_token)

        if not yes_ob or not no_ob:
            return None

        # Extract prices from OrderBookSummary/OrderSummary dataclasses
        yes_bid = float(yes_ob.bids[0].price) if yes_ob.bids else 0.50
        yes_ask = float(yes_ob.asks[0].price) if yes_ob.asks else 0.50
        no_bid = float(no_ob.bids[0].price) if no_ob.bids else 0.50
        no_ask = float(no_ob.asks[0].price) if no_ob.asks else 0.50

        return {
            "yes_price": (yes_bid + yes_ask) / 2,
            "no_price": (no_bid + no_ask) / 2,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
        }

    except Exception as e:
        st.error(f"Error fetching prices: {e}")
        return None


def main():
    """Main application entry point"""

    # Initialize
    init_session_state()
    config = load_config()

    if not config:
        st.error("Failed to load configuration. Please check config/events.yaml")
        return

    # Header
    st.markdown(
        """
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #30363d; margin-bottom: 20px;">
        <div style="display: flex; align-items: center; gap: 12px;">
            <span style="font-size: 28px;">📈</span>
            <span style="font-size: 24px; font-weight: 700; color: #e6edf3;">Polymarket Monitor</span>
        </div>
        <div style="display: flex; gap: 16px; align-items: center;">
            <span style="color: #8b949e; font-size: 14px;">Real-time multi-event monitoring</span>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # Check if demo mode
    demo_mode = config.get("demo_mode", True)

    # Sidebar for settings
    with st.sidebar:
        st.header("Settings")

        # Mode selector
        mode = st.radio(
            "Mode",
            ["Demo", "Live"],
            index=0 if demo_mode else 1,
            help="Demo uses simulated data. Live connects to Polymarket API.",
        )
        demo_mode = mode == "Demo"

        if mode == "Live" and not POLYMARKET_AVAILABLE:
            st.warning(
                "Polymarket client not available. Install dependencies and configure .env"
            )
            demo_mode = True

        st.markdown("---")

        refresh_rate = st.slider(
            "Refresh Rate (seconds)",
            min_value=1,
            max_value=30,
            value=1,
            key="refresh_rate",
        )

        # Auto-refresh toggle
        auto_refresh = st.toggle("Auto Refresh", value=True, key="auto_refresh")

        st.markdown("---")

        # Chart display options
        st.subheader("Chart Options")
        show_percentage = st.toggle(
            "Show Probability %", value=True, key="show_percentage"
        )
        show_price_change = st.toggle(
            "Show Price Change %", value=True, key="show_price_change"
        )
        show_order_book = st.toggle(
            "Show Order Book", value=True, key="show_order_book"
        )

        st.markdown("---")

        st.subheader("Events")
        for event_id, event_data in st.session_state.events_data.items():
            st.checkbox(event_data.name, value=True, key=f"show_{event_id}")

        st.markdown("---")

        if st.button("Refresh Now", use_container_width=True):
            st.session_state.last_refresh = datetime.now()
            st.rerun()

        st.caption(f"Last update: {st.session_state.last_refresh.strftime('%H:%M:%S')}")

        # Connection status
        st.markdown("---")
        if demo_mode:
            st.markdown("**Status:** 🟡 Demo Mode")
        else:
            st.markdown("**Status:** 🟢 Connected to Polymarket")

    # =================================================================
    # One-time initialisation (runs once per full page load)
    # =================================================================
    if demo_mode:
        if not st.session_state.events_data:
            st.session_state.events_data = load_demo_events(config)
    else:
        # Live mode — connect to Polymarket client once
        if "polymarket_client" not in st.session_state:
            try:
                settings_obj = Settings()
                st.session_state.polymarket_client = PolymarketClient(
                    settings_obj.polymarket
                )
            except Exception as e:
                st.error(f"Failed to connect to Polymarket: {e}")
                demo_mode = True

        if not demo_mode and "polymarket_client" in st.session_state:
            events_config = config.get("events", [])

            # Clean up stale events no longer in config
            config_ids = {e["name"].lower().replace(" ", "_") for e in events_config}
            for eid in [k for k in st.session_state.events_data if k not in config_ids]:
                del st.session_state.events_data[eid]

            # Initialise new events and load Binance history
            for event_config in events_config:
                event_id = event_config["name"].lower().replace(" ", "_")
                bsym = event_config.get("binance_symbol", "")
                est = event_config.get("event_start_time", "")

                existing = st.session_state.events_data.get(event_id)
                if existing and existing.price_to_beat > 0:
                    continue  # already fully initialised

                # Candle end = start + 1 h
                event_end = None
                if est:
                    start_ms = parse_event_start_ms(est)
                    if start_ms:
                        from datetime import timezone as tz

                        event_end = datetime.fromtimestamp(
                            start_ms / 1000, tz=tz.utc
                        ) + timedelta(hours=1)

                st.session_state.events_data[event_id] = EventData(
                    name=event_config["name"],
                    description=event_config.get("description", ""),
                    icon=event_config.get("icon", "generic"),
                    current_price=0,
                    price_to_beat=0,
                    condition_id=event_config.get("condition_id", ""),
                    yes_token_id=event_config.get("tokens", {}).get("yes", ""),
                    no_token_id=event_config.get("tokens", {}).get("no", ""),
                    event_end_utc=event_end,
                )

                # Pre-load 1-min klines for this candle window
                if bsym and est:
                    start_ms = parse_event_start_ms(est)
                    if start_ms:
                        kh = fetch_binance_klines(bsym, start_ms)
                        if kh:
                            ev = st.session_state.events_data[event_id]
                            ev.price_history = kh
                            ev.price_to_beat = kh[0]["price_to_beat"]
                            ev.current_price = kh[-1]["price"]
                        else:
                            op = fetch_binance_candle_open(bsym, start_ms)
                            if op:
                                st.session_state.events_data[
                                    event_id
                                ].price_to_beat = op

    # =================================================================
    # Helper: update data for all events (called inside each fragment)
    # =================================================================
    def _update_event(target_eid: str):
        """Fetch fresh prices for a single event and append to history."""
        if target_eid not in st.session_state.events_data:
            return

        if demo_mode:
            edata = st.session_state.events_data[target_eid]
            dcfg = next(
                (
                    e
                    for e in config.get("demo_events", [])
                    if e["name"].lower().replace(" ", "_") == target_eid
                ),
                {},
            )
            st.session_state.events_data[target_eid] = update_demo_prices(edata, dcfg)
        else:
            from datetime import timezone as _tz

            ecfg = next(
                (
                    e
                    for e in config.get("events", [])
                    if e["name"].lower().replace(" ", "_") == target_eid
                ),
                None,
            )
            if not ecfg:
                return

            bsym = ecfg.get("binance_symbol", "")
            ev = st.session_state.events_data[target_eid]

            # Binance live price
            if bsym:
                lp = fetch_binance_price(bsym)
                if lp:
                    old = ev.current_price
                    ev.current_price = lp
                    ev.price_change = ((lp - old) / old * 100) if old > 0 else 0

            # Polymarket probabilities
            if "polymarket_client" in st.session_state:
                pr = fetch_real_prices(st.session_state.polymarket_client, ecfg)
                if pr:
                    ev.yes_price = pr["yes_price"]
                    ev.no_price = pr["no_price"]
                    ev.last_update = datetime.utcnow()

            # Append while candle is open
            candle_open = (
                ev.event_end_utc is None or datetime.now(tz=_tz.utc) < ev.event_end_utc
            )
            if ev.current_price > 0 and candle_open:
                pct = (
                    ((ev.current_price - ev.price_to_beat) / ev.price_to_beat * 100)
                    if ev.price_to_beat > 0
                    else 0
                )
                ev.price_history.append(
                    {
                        "timestamp": datetime.utcnow(),
                        "price": ev.current_price,
                        "yes_price": ev.yes_price,
                        "no_price": ev.no_price,
                        "percent_change": pct,
                        "price_to_beat": ev.price_to_beat,
                    }
                )
                if len(ev.price_history) > 500:
                    ev.price_history = ev.price_history[-500:]

        st.session_state.last_refresh = datetime.now()

    # =================================================================
    # Show demo banner (static, rendered once)
    # =================================================================
    if demo_mode:
        st.info(
            "Running in **DEMO MODE** with simulated data. "
            "Switch to **Live** in the sidebar to connect to Polymarket."
        )

    # =================================================================
    # Per-event rendering: static header + dynamic fragment per event
    # =================================================================
    refresh_secs = st.session_state.get("refresh_rate", 1)

    for eid, edata in st.session_state.events_data.items():
        if not st.session_state.get(f"show_{eid}", True):
            continue

        st.markdown('<div class="event-card">', unsafe_allow_html=True)

        # --- Static: event header (rendered once, no flicker) ---
        col_header, _col_spacer = st.columns([2, 1])
        with col_header:
            st.markdown(
                f"""
            <div class="event-header">
                {get_icon_html(edata.icon)}
                <div>
                    <p class="event-title">{edata.name}</p>
                    <p class="event-subtitle">{edata.description}</p>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

        # --- Dynamic fragment: prices, countdown, chart ---
        # Each event gets its own fragment so only its dynamic area refreshes.
        # We use a factory to capture eid/config per-event in the closure.
        def _make_event_fragment(_eid, _config):
            @st.fragment(run_every=timedelta(seconds=refresh_secs))
            def _event_frag():
                _update_event(_eid)
                _edata = st.session_state.events_data.get(_eid)
                if _edata:
                    render_event_dynamic(_eid, _edata, _config)

            return _event_frag

        _make_event_fragment(eid, config)()

        # --- Static: time filters, order book, trading panel ---
        render_event_static(eid, edata, config)

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
