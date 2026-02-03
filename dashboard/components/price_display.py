"""Price display component."""

from dash import html


def create_price_display(event_id, event_data):
    """Create the price display section for an event.

    Args:
        event_id: Unique event identifier
        event_data: Dict with current_price, price_to_beat, price_change, yes_price, no_price
    """
    current_price = event_data.get("current_price", 0)
    price_to_beat = event_data.get("price_to_beat", 0)
    price_diff = current_price - price_to_beat
    price_up = price_diff >= 0
    change_class = "price-change-positive" if price_up else "price-change-negative"
    change_symbol = "\u25b2" if price_up else "\u25bc"

    yes_price = event_data.get("yes_price", 0.50)
    no_price = event_data.get("no_price", 0.50)

    return html.Div(
        className="price-container",
        children=[
            html.Div(
                className="price-box",
                children=[
                    html.Span("PRICE TO BEAT", className="price-label"),
                    html.Span(f"${price_to_beat:,.2f}", className="price-value"),
                ],
            ),
            html.Div(
                className="price-box",
                children=[
                    html.Span("CURRENT PRICE", className="price-label"),
                    html.Span(
                        f"${current_price:,.2f}",
                        className="price-value price-value-green",
                    ),
                    html.Span(
                        f"{change_symbol} ${abs(price_diff):,.2f}",
                        className=f"price-change {change_class}",
                    ),
                ],
            ),
            html.Div(
                className="price-box",
                children=[
                    html.Span("UP PROBABILITY", className="price-label"),
                    html.Span(
                        f"{yes_price * 100:.1f}%",
                        className="price-value price-change-positive",
                    ),
                ],
            ),
            html.Div(
                className="price-box",
                children=[
                    html.Span("DOWN PROBABILITY", className="price-label"),
                    html.Span(
                        f"{no_price * 100:.1f}%",
                        className="price-value price-change-negative",
                    ),
                ],
            ),
        ],
    )
