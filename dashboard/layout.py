"""Layout builder: header, sidebar, event grid, stores, intervals."""

import os

import dash_bootstrap_components as dbc
import yaml
from dash import dcc, html

from dashboard.components.event_card import create_event_card
from dashboard.components.sidebar import create_sidebar
from dashboard.data.demo import load_demo_events

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_config():
    config_path = os.path.join(_project_root, "config", "events.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def _init_live_events(config):
    """Thin wrapper so layout can call the live initializer without circular imports."""
    from dashboard.callbacks.data_updates import _init_live_events as init_live
    return init_live(config)


def build_layout():
    """Build the full Dash layout."""
    config = _load_config()

    # Respect demo_mode flag from config (default True)
    demo_mode = config.get("demo_mode", True)
    initial_mode = "demo" if demo_mode else "live"

    # Load initial events matching the configured mode
    if demo_mode:
        initial_events = load_demo_events(config)
    else:
        initial_events = _init_live_events(config)

    banner_style = {} if demo_mode else {"display": "none"}

    return html.Div(
        style={"backgroundColor": "#0d1117", "minHeight": "100vh"},
        children=[
            # --- Stores ---
            dcc.Store(id="events-data-store", data=initial_events),
            dcc.Store(
                id="app-settings-store",
                data={
                    "mode": initial_mode,
                    "refresh_rate": 5,
                    "chart_options": ["show_probability", "show_price_change", "show_order_book"],
                },
            ),

            # --- Intervals ---
            dcc.Interval(
                id="refresh-interval",
                interval=5 * 1000,
                n_intervals=0,
            ),
            dcc.Interval(
                id="countdown-interval",
                interval=1000,
                n_intervals=0,
            ),

            # --- Header ---
            html.Div(
                className="dash-header",
                children=[
                    html.Div(
                        className="dash-header-left",
                        children=[
                            html.Span("\U0001f4c8", style={"fontSize": "28px"}),
                            html.Span("Polymarket Monitor", className="dash-header-title"),
                        ],
                    ),
                    html.Div(
                        style={"display": "flex", "gap": "16px", "alignItems": "center"},
                        children=[
                            html.Span(
                                "Real-time multi-event monitoring",
                                className="dash-header-subtitle",
                            ),
                            dbc.Button(
                                "\u2699 Settings",
                                id="settings-btn",
                                color="secondary",
                                size="sm",
                                n_clicks=0,
                                style={
                                    "background": "#21262d",
                                    "border": "1px solid #30363d",
                                    "color": "#e6edf3",
                                },
                            ),
                        ],
                    ),
                ],
            ),

            # --- Demo banner ---
            html.Div(
                id="demo-banner",
                className="demo-banner",
                style=banner_style,
                children=[
                    "Running in ",
                    html.Strong("DEMO MODE"),
                    " with simulated data. Open Settings to switch to Live.",
                ],
            ),

            # --- Sidebar offcanvas (pass initial mode) ---
            create_sidebar(initial_mode=initial_mode),

            # --- Event grid ---
            html.Div(
                id="event-grid",
                className="event-grid",
                children=[
                    create_event_card(event_id, event_data)
                    for event_id, event_data in initial_events.items()
                ],
            ),
        ],
    )
