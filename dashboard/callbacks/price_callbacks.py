"""Store -> update price display divs (pattern-matching MATCH)."""

from dash import ALL, MATCH, Input, Output, State, callback, html, no_update

from dashboard.components.price_display import create_price_display


def register_price_callbacks(app):
    """Register price update callbacks."""

    @app.callback(
        Output({"type": "price-display", "index": MATCH}, "children"),
        Input("events-data-store", "data"),
        State({"type": "price-display", "index": MATCH}, "id"),
        prevent_initial_call=False,
    )
    def update_price_display(events_data, component_id):
        if not events_data or not component_id:
            return no_update

        event_id = component_id["index"]
        event_dict = events_data.get(event_id)
        if not event_dict:
            return no_update

        return create_price_display(event_id, event_dict)
