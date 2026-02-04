"""Order book component with HTML tables and CSS depth bars."""

from dash import html


def create_order_book_content(order_book_dict):
    """Render just the order book tables + midpoint (no card wrapper, no tabs).

    This is what the callback updates inside the order-book div.
    """
    if not order_book_dict:
        return html.Div(
            "Waiting for order book data...",
            style={"color": "#8b949e", "padding": "16px", "textAlign": "center"},
        )

    bids = order_book_dict.get("bids", [])
    asks = order_book_dict.get("asks", [])
    last_price = order_book_dict.get("last_price", 0.50)
    volume = order_book_dict.get("volume", 0)

    # Max shares for depth bar scaling
    max_shares = 1
    if asks:
        max_shares = max(max_shares, max(lvl["shares"] for lvl in asks))
    if bids:
        max_shares = max(max_shares, max(lvl["shares"] for lvl in bids))

    best_ask = asks[0]["price"] if asks else 0.50
    best_bid = bids[0]["price"] if bids else 0.49
    spread_cents = int((best_ask - best_bid) * 100)
    mid_price = (best_ask + best_bid) / 2

    # Build asks rows (reversed so highest price at top)
    asks_reversed = list(reversed(asks))
    ask_rows = []
    for i, lvl in enumerate(asks_reversed):
        depth_pct = (lvl["shares"] / max_shares) * 100
        is_best = (i == len(asks_reversed) - 1)
        row_class = "order-book-row order-book-ask-row"
        if is_best:
            row_class += " order-book-best-ask"
        ask_rows.append(
            html.Tr(
                className=row_class,
                style={"position": "relative"},
                children=[
                    html.Td(f"{int(lvl['price'] * 100)}\u00a2"),
                    html.Td(f"{lvl['shares']:,.2f}"),
                    html.Td(f"${lvl['total']:,.2f}"),
                    html.Td(
                        style={"position": "relative", "width": "50%"},
                        children=html.Div(
                            className="order-book-depth-bar order-book-depth-ask",
                            style={"width": f"{depth_pct}%"},
                        ),
                    ),
                ],
            )
        )

    # Build bids rows
    bid_rows = []
    for i, lvl in enumerate(bids):
        depth_pct = (lvl["shares"] / max_shares) * 100
        is_best = (i == 0)
        row_class = "order-book-row order-book-bid-row"
        if is_best:
            row_class += " order-book-best-bid"
        bid_rows.append(
            html.Tr(
                className=row_class,
                style={"position": "relative"},
                children=[
                    html.Td(f"{int(lvl['price'] * 100)}\u00a2"),
                    html.Td(f"{lvl['shares']:,.2f}"),
                    html.Td(f"${lvl['total']:,.2f}"),
                    html.Td(
                        style={"position": "relative", "width": "50%"},
                        children=html.Div(
                            className="order-book-depth-bar order-book-depth-bid",
                            style={"width": f"{depth_pct}%"},
                        ),
                    ),
                ],
            )
        )

    return html.Div([
        # Volume
        html.Div(
            f"${volume / 1000:,.1f}k Vol",
            className="order-book-volume",
            style={"textAlign": "right", "marginBottom": "8px"},
        ),
        # Asks label
        html.Span(
            "Asks (Sell Orders)",
            className="order-book-section-label order-book-asks-label",
        ),
        # Asks table
        html.Table(
            className="order-book-table",
            children=[
                html.Thead(
                    html.Tr([
                        html.Th("Price"),
                        html.Th("Shares"),
                        html.Th("Total"),
                        html.Th("Depth", style={"width": "50%"}),
                    ])
                ),
                html.Tbody(ask_rows if ask_rows else [
                    html.Tr(html.Td("No asks available", colSpan=4, style={"color": "#8b949e"}))
                ]),
            ],
        ),
        # Midpoint
        html.Div(
            className="order-book-midpoint",
            children=[
                html.Span([
                    html.Span("Last ", className="order-book-midpoint-label"),
                    html.Span(f"{int(last_price * 100)}\u00a2", className="order-book-midpoint-value"),
                ], className="order-book-midpoint-item"),
                html.Span([
                    html.Span("Spread ", className="order-book-midpoint-label"),
                    html.Span(f"{spread_cents}\u00a2", className="order-book-midpoint-value"),
                ], className="order-book-midpoint-item"),
                html.Span([
                    html.Span("Mid ", className="order-book-midpoint-label"),
                    html.Span(f"{int(mid_price * 100)}\u00a2", className="order-book-midpoint-value"),
                ], className="order-book-midpoint-item"),
            ],
        ),
        # Bids label
        html.Span(
            "Bids (Buy Orders)",
            className="order-book-section-label order-book-bids-label",
        ),
        # Bids table
        html.Table(
            className="order-book-table",
            children=[
                html.Thead(
                    html.Tr([
                        html.Th("Price"),
                        html.Th("Shares"),
                        html.Th("Total"),
                        html.Th("Depth", style={"width": "50%"}),
                    ])
                ),
                html.Tbody(bid_rows if bid_rows else [
                    html.Tr(html.Td("No bids available", colSpan=4, style={"color": "#8b949e"}))
                ]),
            ],
        ),
    ])
