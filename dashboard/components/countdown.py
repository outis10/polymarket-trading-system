"""Countdown timer component."""

from dash import html


def create_countdown(minutes=0, seconds=0):
    """Create a countdown timer display."""
    return html.Div(
        className="countdown",
        children=[
            html.Div(
                className="countdown-unit",
                children=[
                    html.Span(f"{minutes:02d}", className="countdown-value"),
                    html.Span("MINS", className="countdown-label"),
                ],
            ),
            html.Div(
                className="countdown-unit",
                children=[
                    html.Span(f"{seconds:02d}", className="countdown-value"),
                    html.Span("SECS", className="countdown-label"),
                ],
            ),
        ],
    )
