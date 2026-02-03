"""Store -> update HTML order book (pattern-matching MATCH)."""

from dash import MATCH, Input, Output, State, callback_context, no_update

from dashboard.components.order_book import create_order_book_content


def register_orderbook_callbacks(app):
    """Register order book update callbacks."""

    @app.callback(
        Output({"type": "order-book", "index": MATCH}, "children"),
        Input("events-data-store", "data"),
        Input({"type": "ob-tab-up", "index": MATCH}, "n_clicks"),
        Input({"type": "ob-tab-down", "index": MATCH}, "n_clicks"),
        State({"type": "order-book", "index": MATCH}, "id"),
        prevent_initial_call=False,
    )
    def update_order_book(events_data, up_clicks, down_clicks, component_id):
        if not events_data or not component_id:
            return no_update

        event_id = component_id["index"]
        event_dict = events_data.get(event_id)
        if not event_dict:
            return no_update

        # Determine active tab based on which button was clicked last
        ctx = callback_context
        tab = "up"
        if ctx.triggered:
            trigger_id = ctx.triggered[0]["prop_id"]
            if "ob-tab-down" in trigger_id:
                tab = "down"

        if tab == "up":
            ob = event_dict.get("order_book_yes", {})
        else:
            ob = event_dict.get("order_book_no", {})

        return create_order_book_content(ob)
