"""Store -> update chart figures (pattern-matching MATCH)."""

from dash import MATCH, Input, Output, State, callback, no_update

from dashboard.components.chart import create_price_chart


def register_chart_callbacks(app):
    """Register chart update callbacks."""

    @app.callback(
        Output({"type": "price-chart", "index": MATCH}, "figure"),
        Input("events-data-store", "data"),
        State({"type": "price-chart", "index": MATCH}, "id"),
        State("app-settings-store", "data"),
        prevent_initial_call=False,
    )
    def update_chart(events_data, component_id, settings):
        if not events_data or not component_id:
            return no_update

        event_id = component_id["index"]
        event_dict = events_data.get(event_id)
        if not event_dict:
            return no_update

        chart_options = (settings or {}).get("chart_options", [
            "show_probability", "show_price_change", "show_order_book",
        ])

        return create_price_chart(
            event_dict.get("price_history", []),
            height=350,
            show_probability="show_probability" in chart_options,
            show_price_change="show_price_change" in chart_options,
            chart_id=event_id,
        )
