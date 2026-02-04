"""Trading panel callbacks: buy/sell tabs, order type, outcome toggle, quick amounts, trade summary, trade execution."""

import json

import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, callback_context, html, no_update


def register_trading_callbacks(app):
    """Register trading panel callbacks."""

    # ---- Update outcome button prices from live data ----
    @app.callback(
        Output({"type": "outcome-up-btn", "index": MATCH}, "children"),
        Output({"type": "outcome-down-btn", "index": MATCH}, "children"),
        Input("events-data-store", "data"),
        State({"type": "outcome-up-btn", "index": MATCH}, "id"),
        prevent_initial_call=False,
    )
    def update_outcome_prices(events_data, component_id):
        if not events_data or not component_id:
            return no_update, no_update

        event_id = component_id["index"]
        event_dict = events_data.get(event_id)
        if not event_dict:
            return no_update, no_update

        yes_price = event_dict.get("yes_price", 0.50)
        no_price = event_dict.get("no_price", 0.50)

        up_children = [
            html.Span("Up ", style={"marginRight": "4px"}),
            html.Span(f"{yes_price * 100:.0f}\u00a2", style={"fontWeight": "700"}),
        ]
        down_children = [
            html.Span("Down ", style={"marginRight": "4px"}),
            html.Span(f"{no_price * 100:.0f}\u00a2", style={"fontWeight": "700"}),
        ]
        return up_children, down_children

    # ---- Buy/Sell tab toggle ----
    @app.callback(
        Output({"type": "buy-tab", "index": MATCH}, "className"),
        Output({"type": "sell-tab", "index": MATCH}, "className"),
        Output({"type": "trade-side-store", "index": MATCH}, "data"),
        Input({"type": "buy-tab", "index": MATCH}, "n_clicks"),
        Input({"type": "sell-tab", "index": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_buy_sell(buy_clicks, sell_clicks):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        trigger_id = ctx.triggered[0]["prop_id"]
        if "buy-tab" in trigger_id:
            return (
                "buy-sell-tab buy-tab-active",
                "buy-sell-tab",
                "Buy",
            )
        else:
            return (
                "buy-sell-tab",
                "buy-sell-tab sell-tab-active",
                "Sell",
            )

    # ---- Order type dropdown -> show/hide limit price ----
    @app.callback(
        Output({"type": "limit-price-section", "index": MATCH}, "style"),
        Input({"type": "order-type-dropdown", "index": MATCH}, "value"),
        prevent_initial_call=True,
    )
    def toggle_limit_price_section(order_type):
        if order_type == "market":
            return {"display": "none"}
        return {}

    # ---- Outcome button toggle ----
    @app.callback(
        Output({"type": "outcome-up-btn", "index": MATCH}, "className"),
        Output({"type": "outcome-down-btn", "index": MATCH}, "className"),
        Output({"type": "selected-outcome-store", "index": MATCH}, "data"),
        Input({"type": "outcome-up-btn", "index": MATCH}, "n_clicks"),
        Input({"type": "outcome-down-btn", "index": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_outcome(up_clicks, down_clicks):
        ctx = callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        trigger_id = ctx.triggered[0]["prop_id"]
        if "outcome-up-btn" in trigger_id:
            return (
                "outcome-btn outcome-up outcome-btn-active",
                "outcome-btn outcome-down",
                "up",
            )
        else:
            return (
                "outcome-btn outcome-up",
                "outcome-btn outcome-down outcome-btn-active",
                "down",
            )

    # ---- Quick amount buttons -> update shares input ----
    @app.callback(
        Output({"type": "shares-input", "index": MATCH}, "value"),
        Input({"type": "quick-btn", "index": MATCH, "amount": ALL}, "n_clicks"),
        State({"type": "shares-input", "index": MATCH}, "value"),
        prevent_initial_call=True,
    )
    def quick_amount_click(n_clicks_list, current_shares):
        ctx = callback_context
        if not ctx.triggered or not any(n_clicks_list):
            return no_update

        trigger = ctx.triggered[0]
        trigger_id = trigger["prop_id"]
        id_str = trigger_id.rsplit(".", 1)[0]
        id_dict = json.loads(id_str)
        amount = id_dict.get("amount", 0)

        new_value = max(0, (current_shares or 0) + amount)
        return new_value

    # ---- Shares/Limit/OrderType change -> update trade summary ----
    @app.callback(
        Output({"type": "trade-summary", "index": MATCH}, "children"),
        Output({"type": "trade-btn", "index": MATCH}, "disabled"),
        Input({"type": "shares-input", "index": MATCH}, "value"),
        Input({"type": "limit-price-input", "index": MATCH}, "value"),
        Input({"type": "order-type-dropdown", "index": MATCH}, "value"),
        prevent_initial_call=False,
    )
    def update_trade_summary(shares, limit_price, order_type):
        shares = shares or 0
        limit_price = limit_price or 0.50

        if order_type == "market":
            # For market orders, estimate at current mid price (limit_price holds last value)
            price = limit_price
        else:
            price = limit_price

        total_cost = shares * price
        potential_win = shares * (1 - price) if shares > 0 else 0

        summary = [
            html.Div(
                className="summary-row",
                children=[
                    html.Span("Total", className="summary-label"),
                    html.Span(f"${total_cost:.2f}", className="summary-value"),
                ],
            ),
            html.Div(
                className="summary-row",
                children=[
                    html.Span("To Win", className="summary-label"),
                    html.Span(f"${potential_win:.2f}", className="summary-value-green"),
                ],
            ),
        ]

        return summary, (shares == 0)

    # ---- Trade button click -> show toast ----
    @app.callback(
        Output({"type": "trade-result", "index": MATCH}, "children"),
        Input({"type": "trade-btn", "index": MATCH}, "n_clicks"),
        State({"type": "trade-side-store", "index": MATCH}, "data"),
        State({"type": "selected-outcome-store", "index": MATCH}, "data"),
        State({"type": "order-type-dropdown", "index": MATCH}, "value"),
        State({"type": "shares-input", "index": MATCH}, "value"),
        State({"type": "limit-price-input", "index": MATCH}, "value"),
        State({"type": "trade-btn", "index": MATCH}, "id"),
        prevent_initial_call=True,
    )
    def execute_trade(n_clicks, side, outcome, order_type, shares, limit_price, btn_id):
        if not n_clicks or not shares:
            return no_update

        outcome_label = "Up" if outcome == "up" else "Down"
        order_label = order_type.capitalize()

        if order_type == "market":
            msg = f"{side} {shares} shares of {outcome_label} ({order_label} order)"
        else:
            msg = f"{side} {shares} shares of {outcome_label} @ ${limit_price:.2f} ({order_label} order)"

        return dbc.Alert(
            msg,
            color="success" if side == "Buy" else "warning",
            dismissable=True,
            duration=4000,
            style={"marginTop": "8px"},
        )
