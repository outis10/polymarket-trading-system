"""Interval 1s -> update countdown display (pattern-matching MATCH)."""

from datetime import datetime, timezone

from dash import ALL, Input, Output, State, callback, no_update

from dashboard.components.countdown import create_countdown


def register_countdown_callbacks(app):
    """Register countdown update callbacks."""

    @app.callback(
        Output({"type": "countdown-display", "index": ALL}, "children"),
        Input("countdown-interval", "n_intervals"),
        State("events-data-store", "data"),
        State({"type": "countdown-display", "index": ALL}, "id"),
        prevent_initial_call=False,
    )
    def update_countdowns(n_intervals, events_data, component_ids):
        if not events_data or not component_ids:
            return [no_update] * max(len(component_ids), 1)

        results = []
        for comp_id in component_ids:
            event_id = comp_id["index"]
            event_dict = events_data.get(event_id, {})
            event_end_str = event_dict.get("event_end_utc")

            minutes, seconds = 0, 0
            if event_end_str:
                try:
                    event_end = datetime.fromisoformat(event_end_str)
                    if event_end.tzinfo is None:
                        event_end = event_end.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(tz=timezone.utc)
                    remaining = event_end - now_utc
                    total_secs = max(0, int(remaining.total_seconds()))
                    minutes = total_secs // 60
                    seconds = total_secs % 60
                except Exception:
                    pass

            results.append(create_countdown(minutes, seconds))

        return results
