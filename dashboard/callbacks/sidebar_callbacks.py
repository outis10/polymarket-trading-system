"""Sidebar callbacks: mode toggle, refresh rate, chart options."""

from dash import Input, Output, State, html, no_update


def register_sidebar_callbacks(app):
    """Register sidebar callbacks."""

    # Settings button -> toggle offcanvas
    @app.callback(
        Output("settings-offcanvas", "is_open"),
        Input("settings-btn", "n_clicks"),
        State("settings-offcanvas", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_sidebar(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return no_update

    # Mode toggle + refresh slider + chart options -> app-settings-store + interval
    @app.callback(
        Output("app-settings-store", "data"),
        Output("refresh-interval", "interval"),
        Output("connection-status", "children"),
        Input("mode-toggle", "value"),
        Input("refresh-rate-slider", "value"),
        Input("chart-options", "value"),
        State("app-settings-store", "data"),
        prevent_initial_call=False,
    )
    def update_settings(mode, refresh_rate, chart_options, current_settings):
        settings = current_settings or {}
        settings["mode"] = mode or "demo"
        settings["refresh_rate"] = refresh_rate or 5
        settings["chart_options"] = chart_options or []

        interval_ms = (refresh_rate or 5) * 1000

        if mode == "demo":
            status = html.Span([
                html.Span(className="status-dot status-demo"),
                "Demo Mode",
            ], style={"color": "#d29922"})
        else:
            status = html.Span([
                html.Span(className="status-dot status-live"),
                "Connected to Polymarket",
            ], style={"color": "#3fb950"})

        return settings, interval_ms, status
