"""Event card component."""

from dash import dcc, html

from dashboard.components.order_book import create_order_book_content

ICON_MAP = {
    "btc": ("event-icon event-icon-btc", "\u20bf"),
    "eth": ("event-icon event-icon-eth", "\u039e"),
    "sol": ("event-icon event-icon-sol", "\u25ce"),
    "generic": ("event-icon event-icon-generic", "\U0001f4ca"),
}


def create_event_card(event_id, event_data):
    """Create a full event card layout.

    The dynamic parts (price, chart, countdown, order book) have IDs using
    pattern-matching dict syntax: {"type": "...", "index": event_id}
    """
    icon_info = ICON_MAP.get(event_data.get("icon", "generic"), ICON_MAP["generic"])

    # Pre-render initial order book content (may be empty for live events)
    ob_yes = event_data.get("order_book_yes")
    initial_ob_content = create_order_book_content(ob_yes)

    return html.Div(
        className="event-card",
        children=[
            # Header
            html.Div(
                className="event-header",
                children=[
                    html.Div(icon_info[1], className=icon_info[0]),
                    html.Div(children=[
                        html.P(event_data.get("name", ""), className="event-title"),
                        html.P(event_data.get("description", ""), className="event-subtitle"),
                    ]),
                ],
            ),
            # Row: prices + countdown
            html.Div(
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
                children=[
                    html.Div(
                        id={"type": "price-display", "index": event_id},
                    ),
                    html.Div(
                        id={"type": "countdown-display", "index": event_id},
                    ),
                ],
            ),
            # Chart
            dcc.Graph(
                id={"type": "price-chart", "index": event_id},
                config={"displayModeBar": False},
                style={"height": "350px"},
            ),
            # Bottom row: order book + trading panel
            html.Div(
                style={"display": "flex", "gap": "20px", "marginTop": "16px"},
                children=[
                    # Order book area (left, 2/3 width)
                    html.Div(
                        style={"flex": "2"},
                        className="order-book-card",
                        children=[
                            # Header (static)
                            html.Div(
                                className="order-book-header",
                                children=[
                                    html.Span("Order Book", className="order-book-title"),
                                ],
                            ),
                            # Tab buttons (static — always in the DOM)
                            html.Div(
                                className="order-book-tabs",
                                children=[
                                    html.Button(
                                        "\u25b2 Trade Up",
                                        id={"type": "ob-tab-up", "index": event_id},
                                        className="order-book-tab order-book-tab-active",
                                        n_clicks=0,
                                    ),
                                    html.Button(
                                        "\u25bc Trade Down",
                                        id={"type": "ob-tab-down", "index": event_id},
                                        className="order-book-tab",
                                        n_clicks=0,
                                    ),
                                ],
                            ),
                            # Order book content (dynamic — updated by callback)
                            html.Div(
                                id={"type": "order-book", "index": event_id},
                                children=initial_ob_content,
                            ),
                        ],
                    ),
                    # Trading panel (right, 1/3 width)
                    html.Div(
                        style={"flex": "1"},
                        children=_create_trading_panel(event_id, event_data),
                    ),
                ],
            ),
        ],
    )


def _create_trading_panel(event_id, event_data):
    """Create the trading panel with stable inputs."""
    yes_price = event_data.get("yes_price", 0.50)

    return html.Div(
        className="trading-panel",
        children=[
            # Buy/Sell radio
            dcc.RadioItems(
                id={"type": "trade-type-radio", "index": event_id},
                options=[
                    {"label": "Buy", "value": "Buy"},
                    {"label": "Sell", "value": "Sell"},
                ],
                value="Buy",
                inline=True,
                style={"marginBottom": "12px"},
                inputStyle={"marginRight": "4px"},
                labelStyle={
                    "background": "#21262d",
                    "padding": "8px 16px",
                    "borderRadius": "8px",
                    "marginRight": "8px",
                    "color": "#e6edf3",
                    "cursor": "pointer",
                },
            ),
            # Outcome buttons
            html.Div(
                className="outcome-buttons",
                children=[
                    html.Button(
                        id={"type": "outcome-up-btn", "index": event_id},
                        className="outcome-btn outcome-up",
                        children=f"\u25b2 Up {yes_price * 100:.0f}c",
                    ),
                    html.Button(
                        id={"type": "outcome-down-btn", "index": event_id},
                        className="outcome-btn outcome-down",
                        children=f"\u25bc Down {(1 - yes_price) * 100:.0f}c",
                    ),
                ],
            ),
            # Limit price input
            html.Div(
                className="input-group",
                children=[
                    html.Label("Limit Price", className="input-label"),
                    dcc.Input(
                        id={"type": "limit-price-input", "index": event_id},
                        type="number",
                        min=0.01,
                        max=0.99,
                        step=0.01,
                        value=round(yes_price, 2),
                        style={
                            "width": "100%",
                            "padding": "8px",
                            "background": "#0d1117",
                            "border": "1px solid #30363d",
                            "borderRadius": "8px",
                            "color": "#e6edf3",
                            "fontSize": "16px",
                        },
                    ),
                ],
            ),
            # Shares input
            html.Div(
                className="input-group",
                children=[
                    html.Label("Shares", className="input-label"),
                    dcc.Input(
                        id={"type": "shares-input", "index": event_id},
                        type="number",
                        min=0,
                        max=10000,
                        step=1,
                        value=0,
                        style={
                            "width": "100%",
                            "padding": "8px",
                            "background": "#0d1117",
                            "border": "1px solid #30363d",
                            "borderRadius": "8px",
                            "color": "#e6edf3",
                            "fontSize": "16px",
                        },
                    ),
                ],
            ),
            # Quick amount buttons
            html.Div(
                className="quick-amounts",
                children=[
                    html.Button(
                        "-100",
                        id={"type": "quick-btn", "index": event_id, "amount": -100},
                        className="quick-btn",
                    ),
                    html.Button(
                        "-10",
                        id={"type": "quick-btn", "index": event_id, "amount": -10},
                        className="quick-btn",
                    ),
                    html.Button(
                        "+10",
                        id={"type": "quick-btn", "index": event_id, "amount": 10},
                        className="quick-btn",
                    ),
                    html.Button(
                        "+100",
                        id={"type": "quick-btn", "index": event_id, "amount": 100},
                        className="quick-btn",
                    ),
                ],
            ),
            html.Hr(style={"borderColor": "#30363d", "margin": "12px 0"}),
            # Trade summary (updated by callback)
            html.Div(
                id={"type": "trade-summary", "index": event_id},
                children=[
                    html.Div(
                        className="summary-row",
                        children=[
                            html.Span("Total", className="summary-label"),
                            html.Span("$0.00", className="summary-value"),
                        ],
                    ),
                    html.Div(
                        className="summary-row",
                        children=[
                            html.Span("To Win", className="summary-label"),
                            html.Span("$0.00", className="summary-value-green"),
                        ],
                    ),
                ],
            ),
            # Trade button
            html.Button(
                "Trade",
                id={"type": "trade-btn", "index": event_id},
                className="trade-btn",
                disabled=True,
            ),
            # Trade result toast area
            html.Div(id={"type": "trade-result", "index": event_id}),
        ],
    )
