"""Dash app factory + entry point."""

import os
import sys

import dash
import dash_bootstrap_components as dbc

# Ensure project root is on the path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dashboard.callbacks.chart_callbacks import register_chart_callbacks
from dashboard.callbacks.countdown_callbacks import register_countdown_callbacks
from dashboard.callbacks.data_updates import register_data_callbacks
from dashboard.callbacks.orderbook_callbacks import register_orderbook_callbacks
from dashboard.callbacks.price_callbacks import register_price_callbacks
from dashboard.callbacks.sidebar_callbacks import register_sidebar_callbacks
from dashboard.callbacks.trading_callbacks import register_trading_callbacks
from dashboard.layout import build_layout


def create_app():
    """Create and configure the Dash application."""
    assets_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        assets_folder=assets_folder,
        title="Polymarket Monitor",
        update_title=None,  # Prevent "Updating..." in title during callbacks
        suppress_callback_exceptions=True,
    )

    app.layout = build_layout()

    # Register all callbacks
    register_data_callbacks(app)
    register_price_callbacks(app)
    register_chart_callbacks(app)
    register_countdown_callbacks(app)
    register_orderbook_callbacks(app)
    register_trading_callbacks(app)
    register_sidebar_callbacks(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=8050)
