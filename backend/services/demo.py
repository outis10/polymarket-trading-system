"""Demo data generators - ported from dashboard/data/demo.py."""

import random
from datetime import datetime, timedelta
from typing import Optional


def generate_price_history(
    base_price: float,
    volatility: float,
    points: int = 100,
    price_to_beat: Optional[float] = None,
) -> list[dict]:
    """Generate simulated price history for demo mode."""
    history = []
    price = base_price
    reference_price = price_to_beat if price_to_beat else base_price
    now = datetime.now()

    for i in range(points):
        timestamp = now - timedelta(seconds=(points - i) * 5)
        change = random.gauss(0, volatility * price)
        price = max(price + change, base_price * 0.95)
        price = min(price, base_price * 1.05)

        percent_change = ((price - reference_price) / reference_price) * 100
        probability_swing = (price - reference_price) / reference_price * 20
        yes_price = max(0.01, min(0.99, 0.50 + probability_swing))

        history.append({
            "timestamp": timestamp.isoformat(),
            "price": price,
            "yes_price": yes_price,
            "no_price": 1 - yes_price,
            "percent_change": percent_change,
            "price_to_beat": reference_price,
        })

    return history


def generate_order_book(mid_price: float, num_levels: int = 5, base_volume: float = 500.0, volatility: float = 0.3) -> dict:
    """Generate a realistic simulated order book (returns dict)."""
    bids = []
    asks = []

    spread = 0.01
    best_bid = max(0.01, min(0.98, mid_price - spread / 2))
    best_ask = max(0.02, min(0.99, mid_price + spread / 2))

    cumulative_total = 0.0
    for i in range(num_levels):
        price = best_ask + (i * 0.01)
        if price > 0.99:
            break
        shares = base_volume * (1 + random.uniform(-volatility, volatility)) * (1 + i * 0.3)
        cumulative_total += shares * price
        asks.append({"price": round(price, 2), "shares": round(shares, 2), "total": round(cumulative_total, 2)})

    cumulative_total = 0.0
    for i in range(num_levels):
        price = best_bid - (i * 0.01)
        if price < 0.01:
            break
        shares = base_volume * (1 + random.uniform(-volatility, volatility)) * (1 + i * 0.3)
        cumulative_total += shares * price
        bids.append({"price": round(price, 2), "shares": round(shares, 2), "total": round(cumulative_total, 2)})

    total_volume = sum(a["shares"] * a["price"] for a in asks) + sum(b["shares"] * b["price"] for b in bids)

    return {
        "bids": bids,
        "asks": asks,
        "last_price": round(mid_price, 2),
        "spread": round(best_ask - best_bid, 2),
        "volume": round(total_volume, 2),
    }


def update_order_book(order_book_dict: dict, mid_price: float, volatility: float = 0.1) -> dict:
    """Update an existing order book dict with small random changes."""
    bids = order_book_dict.get("bids", [])
    asks = order_book_dict.get("asks", [])

    for level in asks:
        change = random.gauss(0, level["shares"] * volatility * 0.1)
        level["shares"] = round(max(10, level["shares"] + change), 2)

    for level in bids:
        change = random.gauss(0, level["shares"] * volatility * 0.1)
        level["shares"] = round(max(10, level["shares"] + change), 2)

    cumulative = 0.0
    for level in asks:
        cumulative += level["shares"] * level["price"]
        level["total"] = round(cumulative, 2)

    cumulative = 0.0
    for level in bids:
        cumulative += level["shares"] * level["price"]
        level["total"] = round(cumulative, 2)

    spread = 0.01
    best_bid = mid_price - spread / 2
    best_ask = mid_price + spread / 2
    total_vol = sum(a["shares"] * a["price"] for a in asks) + sum(b["shares"] * b["price"] for b in bids)

    return {
        "bids": bids,
        "asks": asks,
        "last_price": round(mid_price, 2),
        "spread": round(best_ask - best_bid, 2),
        "volume": round(total_vol, 2),
    }


def update_demo_prices(event_dict: dict, config: dict) -> dict:
    """Update prices for a single demo event."""
    current_price = event_dict.get("current_price", 0)
    price_to_beat = event_dict.get("price_to_beat", current_price)

    change = random.gauss(0, config.get("volatility", 0.02) * current_price)
    new_price = current_price + change

    old_price = current_price
    event_dict["current_price"] = new_price
    event_dict["price_change"] = ((new_price - old_price) / old_price * 100) if old_price > 0 else 0

    probability_swing = (new_price - price_to_beat) / price_to_beat * 20 if price_to_beat > 0 else 0
    yes_price = max(0.01, min(0.99, 0.50 + probability_swing))
    no_price = 1 - yes_price
    event_dict["yes_price"] = yes_price
    event_dict["no_price"] = no_price

    percent_change_from_ref = ((new_price - price_to_beat) / price_to_beat) * 100 if price_to_beat > 0 else 0

    history = event_dict.get("price_history", [])
    history.append({
        "timestamp": datetime.now().isoformat(),
        "price": new_price,
        "yes_price": yes_price,
        "no_price": no_price,
        "percent_change": percent_change_from_ref,
        "price_to_beat": price_to_beat,
    })

    if len(history) > 500:
        history = history[-500:]
    event_dict["price_history"] = history

    ob_yes = event_dict.get("order_book_yes")
    ob_no = event_dict.get("order_book_no")

    if ob_yes and (ob_yes.get("bids") or ob_yes.get("asks")):
        event_dict["order_book_yes"] = update_order_book(ob_yes, yes_price)
    else:
        event_dict["order_book_yes"] = generate_order_book(yes_price)

    if ob_no and (ob_no.get("bids") or ob_no.get("asks")):
        event_dict["order_book_no"] = update_order_book(ob_no, no_price)
    else:
        event_dict["order_book_no"] = generate_order_book(no_price)

    event_dict["last_update"] = datetime.now().isoformat()

    return event_dict


def load_demo_events(config: dict) -> dict[str, dict]:
    """Load demo events from configuration."""
    events = {}
    demo_events = config.get("demo_events", [])

    for event_config in demo_events:
        event_id = event_config["name"].lower().replace(" ", "_")
        price_to_beat = event_config.get("price_to_beat", event_config["initial_price"])

        history = generate_price_history(
            event_config["initial_price"],
            event_config.get("volatility", 0.02),
            100,
            price_to_beat=price_to_beat,
        )

        yes_price = event_config.get("yes_price", 0.50)
        no_price = event_config.get("no_price", 0.50)

        ob_yes = generate_order_book(yes_price)
        ob_no = generate_order_book(no_price)

        events[event_id] = {
            "name": event_config["name"],
            "description": event_config["description"],
            "icon": event_config.get("icon", "generic"),
            "price_history": history,
            "yes_price": yes_price,
            "no_price": no_price,
            "current_price": event_config["initial_price"],
            "price_to_beat": price_to_beat,
            "last_update": datetime.now().isoformat(),
            "price_change": 0,
            "volume_24h": 0,
            "condition_id": "",
            "yes_token_id": "",
            "no_token_id": "",
            "order_book_yes": ob_yes,
            "order_book_no": ob_no,
            "event_end_utc": None,
        }

    return events
