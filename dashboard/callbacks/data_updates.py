"""Central data update callback: Interval -> fetch data -> dcc.Store."""

import os
import sys
from datetime import datetime, timezone

import yaml
from dash import Input, Output, State, html, no_update

# Add project root to path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dashboard.data.binance import (
    fetch_binance_candle_open,
    fetch_binance_klines,
    fetch_binance_price,
    parse_event_start_ms,
)
from dashboard.data.demo import load_demo_events, update_demo_prices
from dashboard.data.polymarket import fetch_real_prices, get_client


def _load_config():
    """Load events configuration from YAML."""
    config_path = os.path.join(_project_root, "config", "events.yaml")
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def register_data_callbacks(app):
    """Register the central data update callback."""

    # ---- Periodic data update (interval ticks) ----
    @app.callback(
        Output("events-data-store", "data"),
        Input("refresh-interval", "n_intervals"),
        Input("refresh-now-btn", "n_clicks"),
        State("events-data-store", "data"),
        State("app-settings-store", "data"),
        prevent_initial_call=False,
    )
    def update_events_data(n_intervals, n_clicks, current_data, settings):
        config = _load_config()
        if not config:
            return no_update

        mode = (settings or {}).get("mode", "demo")

        # Initialize if store is empty
        if not current_data:
            if mode == "demo":
                return load_demo_events(config)
            else:
                return _init_live_events(config)

        # Normal periodic update
        if mode == "demo":
            return _update_demo(current_data, config)
        else:
            return _update_live(current_data, config)

    # ---- Mode switch: re-init data + rebuild event grid + toggle banner ----
    @app.callback(
        Output("events-data-store", "data", allow_duplicate=True),
        Output("event-grid", "children"),
        Output("demo-banner", "style"),
        Input("mode-toggle", "value"),
        prevent_initial_call=True,
    )
    def switch_mode(mode):
        from dashboard.components.event_card import create_event_card

        config = _load_config()
        if not config:
            return no_update, no_update, no_update

        # Initialize events for the selected mode
        if mode == "demo":
            events = load_demo_events(config)
            banner_style = {}
        else:
            events = _init_live_events(config)
            banner_style = {"display": "none"}

        # Build new event cards
        cards = [
            create_event_card(eid, edata)
            for eid, edata in events.items()
        ]

        return events, cards, banner_style

    # ---- Last update text ----
    @app.callback(
        Output("last-update-text", "children"),
        Input("events-data-store", "data"),
    )
    def update_last_update_text(data):
        return f"Last update: {datetime.now().strftime('%H:%M:%S')}"


def _update_demo(events_data, config):
    """Update all demo events."""
    demo_configs = config.get("demo_events", [])
    for event_id, event_dict in events_data.items():
        dcfg = next(
            (e for e in demo_configs if e["name"].lower().replace(" ", "_") == event_id),
            {},
        )
        update_demo_prices(event_dict, dcfg)
    return events_data


def _init_live_events(config):
    """Initialize live events from config."""
    events = {}
    events_config = config.get("events", [])
    for event_config in events_config:
        event_id = event_config["name"].lower().replace(" ", "_")
        bsym = event_config.get("binance_symbol", "")
        est = event_config.get("event_start_time", "")

        event_end = None
        if est:
            start_ms = parse_event_start_ms(est)
            if start_ms:
                from datetime import timedelta
                event_end_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc) + timedelta(hours=1)
                event_end = event_end_dt.isoformat()

        event_dict = {
            "name": event_config["name"],
            "description": event_config.get("description", ""),
            "icon": event_config.get("icon", "generic"),
            "price_history": [],
            "yes_price": 0.50,
            "no_price": 0.50,
            "current_price": 0,
            "price_to_beat": 0,
            "last_update": "",
            "price_change": 0,
            "volume_24h": 0,
            "condition_id": event_config.get("condition_id", ""),
            "yes_token_id": event_config.get("tokens", {}).get("yes", ""),
            "no_token_id": event_config.get("tokens", {}).get("no", ""),
            "order_book_yes": None,
            "order_book_no": None,
            "event_end_utc": event_end,
        }

        # Pre-load Binance klines
        if bsym and est:
            start_ms = parse_event_start_ms(est)
            if start_ms:
                kh = fetch_binance_klines(bsym, start_ms)
                if kh:
                    event_dict["price_history"] = kh
                    event_dict["price_to_beat"] = kh[0]["price_to_beat"]
                    event_dict["current_price"] = kh[-1]["price"]
                else:
                    op = fetch_binance_candle_open(bsym, start_ms)
                    if op:
                        event_dict["price_to_beat"] = op

        events[event_id] = event_dict
    return events


def _update_live(events_data, config):
    """Update all live events."""
    events_config = config.get("events", [])
    client = get_client()

    for event_id, event_dict in events_data.items():
        ecfg = next(
            (e for e in events_config if e["name"].lower().replace(" ", "_") == event_id),
            None,
        )
        if not ecfg:
            continue

        bsym = ecfg.get("binance_symbol", "")

        # Binance live price
        if bsym:
            lp = fetch_binance_price(bsym)
            if lp:
                old = event_dict.get("current_price", 0)
                event_dict["current_price"] = lp
                event_dict["price_change"] = ((lp - old) / old * 100) if old > 0 else 0

        # Polymarket probabilities + order books (preferred) or derive from Binance price
        polymarket_updated = False
        if client:
            pr = fetch_real_prices(client, ecfg)
            if pr:
                event_dict["yes_price"] = pr["yes_price"]
                event_dict["no_price"] = pr["no_price"]
                if pr.get("order_book_yes"):
                    event_dict["order_book_yes"] = pr["order_book_yes"]
                if pr.get("order_book_no"):
                    event_dict["order_book_no"] = pr["order_book_no"]
                polymarket_updated = True

        if not polymarket_updated:
            # Derive probability from price vs price_to_beat
            cp = event_dict.get("current_price", 0)
            ptb = event_dict.get("price_to_beat", 0)
            if cp > 0 and ptb > 0:
                swing = (cp - ptb) / ptb * 20
                yes_p = max(0.01, min(0.99, 0.50 + swing))
                event_dict["yes_price"] = yes_p
                event_dict["no_price"] = 1 - yes_p

        event_dict["last_update"] = datetime.now(tz=timezone.utc).isoformat()

        # Append to history while candle is open
        event_end_str = event_dict.get("event_end_utc")
        candle_open = True
        if event_end_str:
            try:
                event_end_dt = datetime.fromisoformat(event_end_str)
                candle_open = datetime.now(tz=timezone.utc) < event_end_dt
            except Exception:
                pass

        current_price = event_dict.get("current_price", 0)
        price_to_beat = event_dict.get("price_to_beat", 0)
        if current_price > 0 and candle_open:
            pct = ((current_price - price_to_beat) / price_to_beat * 100) if price_to_beat > 0 else 0
            history = event_dict.get("price_history", [])
            history.append({
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "price": current_price,
                "yes_price": event_dict.get("yes_price", 0.50),
                "no_price": event_dict.get("no_price", 0.50),
                "percent_change": pct,
                "price_to_beat": price_to_beat,
            })
            if len(history) > 500:
                history = history[-500:]
            event_dict["price_history"] = history

    return events_data
