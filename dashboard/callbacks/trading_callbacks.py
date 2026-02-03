"""Trading panel callbacks: quick amounts, trade summary, trade execution."""

import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, callback, callback_context, html, no_update


def register_trading_callbacks(app):
    """Register trading panel callbacks."""

    # Quick amount buttons -> update shares input
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

        # Find which button was clicked
        trigger = ctx.triggered[0]
        trigger_id = trigger["prop_id"]

        # Parse the amount from the trigger ID
        import json
        id_str = trigger_id.rsplit(".", 1)[0]
        id_dict = json.loads(id_str)
        amount = id_dict.get("amount", 0)

        new_value = max(0, (current_shares or 0) + amount)
        return new_value

    # Shares/Limit change -> update trade summary
    @app.callback(
        Output({"type": "trade-summary", "index": MATCH}, "children"),
        Output({"type": "trade-btn", "index": MATCH}, "disabled"),
        Input({"type": "shares-input", "index": MATCH}, "value"),
        Input({"type": "limit-price-input", "index": MATCH}, "value"),
        prevent_initial_call=False,
    )
    def update_trade_summary(shares, limit_price):
        shares = shares or 0
        limit_price = limit_price or 0.50

        total_cost = shares * limit_price
        potential_win = shares * (1 - limit_price) if shares > 0 else 0

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

    # Trade button click -> show toast
    @app.callback(
        Output({"type": "trade-result", "index": MATCH}, "children"),
        Input({"type": "trade-btn", "index": MATCH}, "n_clicks"),
        State({"type": "trade-type-radio", "index": MATCH}, "value"),
        State({"type": "shares-input", "index": MATCH}, "value"),
        State({"type": "limit-price-input", "index": MATCH}, "value"),
        State({"type": "trade-btn", "index": MATCH}, "id"),
        prevent_initial_call=True,
    )
    def execute_trade(n_clicks, trade_type, shares, limit_price, btn_id):
        if not n_clicks or not shares:
            return no_update

        event_id = btn_id["index"]
        msg = f"Order placed: {trade_type} {shares} shares @ ${limit_price:.2f}"

        return dbc.Alert(
            msg,
            color="success",
            dismissable=True,
            duration=4000,
            style={"marginTop": "8px"},
        )
