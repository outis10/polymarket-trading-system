"""Sidebar / Offcanvas component for settings."""

import dash_bootstrap_components as dbc
from dash import dcc, html


def create_sidebar(initial_mode="demo"):
    """Create the sidebar offcanvas with settings."""
    return dbc.Offcanvas(
        id="settings-offcanvas",
        title="Settings",
        is_open=False,
        placement="end",
        style={"backgroundColor": "#161b22", "color": "#e6edf3"},
        children=[
            html.Div(
                className="sidebar-content",
                children=[
                    # Mode selector
                    html.Div(
                        className="sidebar-section",
                        children=[
                            html.Div("MODE", className="sidebar-section-title"),
                            dcc.RadioItems(
                                id="mode-toggle",
                                options=[
                                    {"label": " Demo", "value": "demo"},
                                    {"label": " Live", "value": "live"},
                                ],
                                value=initial_mode,
                                inputStyle={"marginRight": "6px"},
                                labelStyle={
                                    "display": "block",
                                    "padding": "8px 12px",
                                    "background": "#21262d",
                                    "borderRadius": "8px",
                                    "marginBottom": "4px",
                                    "color": "#e6edf3",
                                    "cursor": "pointer",
                                },
                            ),
                            # Status indicator
                            html.Div(
                                id="connection-status",
                                style={"marginTop": "8px", "fontSize": "13px"},
                            ),
                        ],
                    ),
                    html.Hr(style={"borderColor": "#30363d"}),
                    # Refresh rate
                    html.Div(
                        className="sidebar-section",
                        children=[
                            html.Div("REFRESH RATE", className="sidebar-section-title"),
                            dcc.Slider(
                                id="refresh-rate-slider",
                                min=1,
                                max=30,
                                step=1,
                                value=5,
                                marks={1: "1s", 5: "5s", 10: "10s", 20: "20s", 30: "30s"},
                                tooltip={"placement": "bottom"},
                            ),
                        ],
                    ),
                    html.Hr(style={"borderColor": "#30363d"}),
                    # Chart options
                    html.Div(
                        className="sidebar-section",
                        children=[
                            html.Div("CHART OPTIONS", className="sidebar-section-title"),
                            dbc.Checklist(
                                id="chart-options",
                                options=[
                                    {"label": " Show Probability %", "value": "show_probability"},
                                    {"label": " Show Price Change %", "value": "show_price_change"},
                                    {"label": " Show Order Book", "value": "show_order_book"},
                                ],
                                value=["show_probability", "show_price_change", "show_order_book"],
                                switch=True,
                                style={"color": "#e6edf3"},
                            ),
                        ],
                    ),
                    html.Hr(style={"borderColor": "#30363d"}),
                    # Refresh now button
                    dbc.Button(
                        "Refresh Now",
                        id="refresh-now-btn",
                        color="primary",
                        className="w-100",
                        n_clicks=0,
                    ),
                    html.Div(
                        id="last-update-text",
                        style={"marginTop": "8px", "fontSize": "12px", "color": "#8b949e"},
                    ),
                ],
            ),
        ],
    )
